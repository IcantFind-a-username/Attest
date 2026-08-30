"""Generic project-evaluation service over any caller-owned Git repository.

This is the only public entry point for evaluating a project. It knows nothing
about BugsInPy or any other corpus: a request names a repository, two immutable
references, an opaque case identifier, a review configuration, execution
limits, and -- optionally -- hidden truth together with the fixed reference
that truth is defined against. Corpus adapters and the CLI are parameter
adaptation over this service and never reach into runner internals.

Two rules shape the whole module:

* every reference is resolved to an immutable SHA, and every structural refusal
  is decided, **before** the provider is touched; and
* without truth there is no score. The service reports what it measured and
  leaves ``score`` as ``None`` rather than inventing a negative label.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from attest.benchmark.artifacts import ArtifactRecord, ArtifactStore
from attest.benchmark.matcher import MatchResult, match_findings
from attest.benchmark.runner import (
    BenchmarkRunner,
    CaseRunResult,
    LoopbackGitHub,
    ReproReceipt,
    ci_final_decisions,
)
from attest.benchmark.schema import (
    Prediction,
    RunRecord,
    TruthDefect,
    is_scored_placement,
)
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits
from attest.review.ledger import Ledger
from attest.review.proposer import Provider

GIT_TIMEOUT_S = 60.0
OPAQUE_CASE_PREFIX = "case-"
_OPAQUE_BODY_LENGTH = 12
_HEX_DIGITS = frozenset("0123456789abcdef")
#: Words that would leak the hidden role of a case to the reviewed product.
_LEAKING_TERMS = ("bug", "clean", "fix", "defect", "broken", "buggy", "control", "truth")


class ProjectEvaluationError(ValueError):
    """A request was refused before any model, GitHub, or head-code execution."""


@dataclass(frozen=True)
class ProjectTruth:
    """Hidden defect locations and the immutable reference they are defined against."""

    defects: tuple[TruthDefect, ...]
    fixed_ref: str | None = None


@dataclass(frozen=True)
class ProjectEvaluationRequest:
    """One evaluation of one immutable base/head pair in a caller-owned repository."""

    case_id: str
    repo: Path
    base_ref: str
    head_ref: str
    workspace_root: Path
    config: ReviewConfig = field(default_factory=ReviewConfig)
    limits: ExecutorLimits = field(default_factory=ExecutorLimits)
    verification_timeout_s: float = 600.0
    repeats: int = 3
    deadline_s: float = 60.0
    line_slack: int = 0
    truth: ProjectTruth | None = None
    repository: str = "local/project"
    pull_request_number: int = 1
    repeat: int = 0


@dataclass(frozen=True)
class ProjectEvaluationScore:
    """Matching outcome for the findings this run made visible to the author."""

    surfaced: int
    matched: int
    unmatched: int
    matches: tuple[MatchResult, ...]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "surfaced": self.surfaced,
            "matched": self.matched,
            "unmatched": self.unmatched,
            "matches": [
                {
                    "finding_id": match.finding_id,
                    "defect_id": match.defect_id,
                    "matched": match.matched,
                }
                for match in self.matches
            ],
        }


@dataclass(frozen=True)
class ProjectEvaluationResult:
    """Frozen, JSON-serializable outcome of one project evaluation."""

    case_id: str
    status: str
    task_id: str | None
    base_sha: str | None
    head_sha: str | None
    predictions: tuple[Prediction, ...]
    final_decisions: tuple[Mapping[str, Any], ...]
    abstain_reason: str | None
    latency_s: float
    spend_usd: float
    oracle_spend_usd: float
    artifacts: tuple[ArtifactRecord, ...]
    evidence_class_counts: Mapping[str, int]
    oracle_receipts: tuple[ReproReceipt, ...]
    run: RunRecord
    score: ProjectEvaluationScore | None

    def to_json_dict(self) -> dict[str, object]:
        """Deterministic mapping suitable for direct JSON serialization."""
        return {
            "case_id": self.case_id,
            "status": self.status,
            "task_id": self.task_id,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "predictions": [
                {
                    "finding_id": prediction.finding_id,
                    "file": prediction.file,
                    "line": prediction.line,
                    "placement": prediction.placement.value,
                    "action": prediction.action,
                    "repro_status": prediction.repro_status,
                    "evidence_class": prediction.evidence_class,
                }
                for prediction in self.predictions
            ],
            "final_decisions": [dict(decision) for decision in self.final_decisions],
            "abstain_reason": self.abstain_reason,
            "latency_s": round(self.latency_s, 6),
            "spend_usd": round(self.spend_usd, 6),
            "oracle_spend_usd": round(self.oracle_spend_usd, 6),
            "artifacts": [record.to_json_dict() for record in self.artifacts],
            "evidence_class_counts": dict(sorted(self.evidence_class_counts.items())),
            "oracle_receipts": [receipt.to_json_dict() for receipt in self.oracle_receipts],
            "delivery_at_s": self.run.delivery_at_s,
            "deadline_s": self.run.deadline_s,
            "repeat": self.run.repeat,
            "score": None if self.score is None else self.score.to_json_dict(),
        }


def evaluate_project(
    request: ProjectEvaluationRequest,
    *,
    provider: Provider,
    artifact_store: ArtifactStore | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ProjectEvaluationResult:
    """Evaluate one immutable base/head pair and return frozen, typed results."""
    resolved = _resolve(request)
    started = clock()
    workspace = _own_worktree(request, resolved.head_sha)
    try:
        with LoopbackGitHub() as github:
            runner = BenchmarkRunner(
                limits=request.limits,
                verification_timeout_s=request.verification_timeout_s,
                repeats=request.repeats,
                clock=clock,
            )
            run = runner.run_case(
                workspace,
                case_id=request.case_id,
                base_sha=resolved.base_sha,
                head_sha=resolved.head_sha,
                config=request.config,
                provider=provider,
                client=github.client(),
                fixed_sha=resolved.fixed_sha,
                repository=request.repository,
                pull_request_number=request.pull_request_number,
                deadline_s=request.deadline_s,
                repeat=request.repeat,
            )
            summary = github.status_bodies[-1] if github.status_bodies else ""
        decisions = tuple(
            ci_final_decisions(workspace, run.task_id) if run.task_id else ()
        )
        records = _persist(artifact_store, request, run, workspace, summary)
    finally:
        _release_worktree(request.repo, workspace)
    return _result(
        request,
        resolved=resolved,
        run=run,
        decisions=decisions,
        records=records,
        latency_s=clock() - started,
    )


def evaluate_projects(
    requests: Sequence[ProjectEvaluationRequest],
    *,
    provider_factory: Callable[[ProjectEvaluationRequest], Provider],
    artifact_store: ArtifactStore | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[ProjectEvaluationResult, ...]:
    """Evaluate many projects in input order, isolating each case's failure.

    One case's refusal or crash becomes that case's explicit DEFER. It never
    aborts the batch and never hides the cases that already completed.
    """
    results: list[ProjectEvaluationResult] = []
    for request in requests:
        try:
            results.append(
                evaluate_project(
                    request,
                    provider=provider_factory(request),
                    artifact_store=artifact_store,
                    clock=clock,
                )
            )
        except Exception as exc:  # noqa: BLE001 - a per-case failure is a DEFER
            results.append(_deferred(request, f"{type(exc).__name__}: {exc}"))
    return tuple(results)


@dataclass(frozen=True)
class _Resolved:
    base_sha: str
    head_sha: str
    fixed_sha: str | None


def _resolve(request: ProjectEvaluationRequest) -> _Resolved:
    """Validate identity, repository, and references before any provider use."""
    _require_opaque_case_id(request.case_id)
    repo = request.repo
    if not repo.is_dir() or _git(repo, "rev-parse", "--git-dir") is None:
        raise ProjectEvaluationError(f"{repo} is not an existing git repository")
    status = _git(repo, "status", "--porcelain", "--untracked-files=no")
    if status is None or status.strip():
        raise ProjectEvaluationError(
            "the repository working tree must be clean; evaluation needs immutable revisions"
        )
    base_sha = _commit(repo, request.base_ref, "base_ref")
    head_sha = _commit(repo, request.head_ref, "head_ref")
    if base_sha == head_sha:
        raise ProjectEvaluationError("base_ref and head_ref resolve to identical revisions")
    fixed_sha: str | None = None
    truth = request.truth
    if truth is not None:
        if not truth.defects:
            raise ProjectEvaluationError("truth must contain at least one defect")
        if not truth.fixed_ref:
            raise ProjectEvaluationError(
                "truth requires a fixed reference to score differential evidence against"
            )
        if any(defect.case_id != request.case_id for defect in truth.defects):
            raise ProjectEvaluationError("truth defects must belong to the requested case")
        fixed_sha = _commit(repo, truth.fixed_ref, "fixed_ref")
        if fixed_sha == head_sha:
            raise ProjectEvaluationError("fixed_ref and head_ref resolve to identical revisions")
    return _Resolved(base_sha=base_sha, head_sha=head_sha, fixed_sha=fixed_sha)


def _require_opaque_case_id(case_id: str) -> None:
    lowered = case_id.lower()
    if any(term in lowered for term in _LEAKING_TERMS):
        raise ProjectEvaluationError(
            "case_id must be opaque: it must not name a role or defect term"
        )
    body = case_id[len(OPAQUE_CASE_PREFIX) :]
    if (
        not case_id.startswith(OPAQUE_CASE_PREFIX)
        or len(body) != _OPAQUE_BODY_LENGTH
        or not set(body) <= _HEX_DIGITS
    ):
        raise ProjectEvaluationError(
            "case_id must be opaque: 'case-' followed by 12 hexadecimal characters"
        )


def _commit(repo: Path, ref: str, label: str) -> str:
    if not ref:
        raise ProjectEvaluationError(f"{label} must name a revision")
    resolved = _git(repo, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if resolved is None or not resolved.strip():
        raise ProjectEvaluationError(f"{label} does not resolve to an immutable commit")
    return resolved.strip()


def _git(repo: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=False,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _own_worktree(request: ProjectEvaluationRequest, head_sha: str) -> Path:
    """Materialize an isolated worktree the service exclusively owns."""
    workspace = request.workspace_root / request.case_id
    if workspace.exists():
        raise ProjectEvaluationError(f"workspace {workspace} already exists")
    workspace.parent.mkdir(parents=True, exist_ok=True)
    if _git(request.repo, "worktree", "add", "--detach", str(workspace), head_sha) is None:
        raise ProjectEvaluationError("could not materialize an isolated worktree at head")
    return workspace


def _release_worktree(repo: Path, workspace: Path) -> None:
    """Remove only the worktree this service created, then prune its record."""
    with suppress(OSError, subprocess.SubprocessError):
        _git(repo, "worktree", "remove", "--force", str(workspace))
    shutil.rmtree(workspace, ignore_errors=True)
    with suppress(OSError, subprocess.SubprocessError):
        _git(repo, "worktree", "prune")


def _persist(
    store: ArtifactStore | None,
    request: ProjectEvaluationRequest,
    run: CaseRunResult,
    workspace: Path,
    summary: str,
) -> tuple[ArtifactRecord, ...]:
    """Write this case's evidence into its own namespace inside the store.

    An artifact refusal is never swallowed: a payload that still looks like a
    secret, or a name that escapes the store, is a security event. It
    propagates, and ``evaluate_projects`` turns it into an explicit per-case
    DEFER rather than a quietly incomplete evidence set.
    """
    if store is None or run.task_id is None:
        return ()
    prefix = f"cases/{request.case_id}/repeat-{request.repeat}"
    ledger_rows = [row for row in Ledger(workspace).entries() if row.get("task_id")]
    records: list[ArtifactRecord] = [
        store.write(f"{prefix}/ledger.jsonl", "product_ledger", ledger_rows)
    ]
    records.append(
        store.write(
            f"{prefix}/predictions.json",
            "predictions",
            [
                {
                    "finding_id": prediction.finding_id,
                    "file": prediction.file,
                    "line": prediction.line,
                    "placement": prediction.placement.value,
                    "action": prediction.action,
                    "repro_status": prediction.repro_status,
                    "evidence_class": prediction.evidence_class,
                }
                for prediction in run.run.predictions
            ],
        )
    )
    records.append(
        store.write(f"{prefix}/scored_run.json", "scored_run", run.scored_payload())
    )
    repro_output = "\n".join(
        f"{row.get('finding_id')}: {row.get('evidence', '')}"
        for row in ledger_rows
        if row.get("kind") == "verification"
    )
    if repro_output:
        records.append(store.write(f"{prefix}/repro.txt", "repro_output", repro_output))
    if summary:
        records.append(store.write(f"{prefix}/summary.md", "github_summary", summary))
    return tuple(records)


def _result(
    request: ProjectEvaluationRequest,
    *,
    resolved: _Resolved,
    run: CaseRunResult,
    decisions: tuple[Mapping[str, Any], ...],
    records: tuple[ArtifactRecord, ...],
    latency_s: float,
) -> ProjectEvaluationResult:
    counts: dict[str, int] = {}
    for prediction in run.run.predictions:
        counts[prediction.evidence_class] = counts.get(prediction.evidence_class, 0) + 1
    return ProjectEvaluationResult(
        case_id=request.case_id,
        status="deferred" if run.deferred_reason is not None else "completed",
        task_id=run.task_id,
        base_sha=resolved.base_sha,
        head_sha=resolved.head_sha,
        predictions=run.run.predictions,
        final_decisions=decisions,
        abstain_reason=run.deferred_reason,
        latency_s=latency_s,
        spend_usd=run.spend_usd,
        oracle_spend_usd=run.oracle_spend_usd,
        artifacts=records,
        evidence_class_counts=counts,
        oracle_receipts=run.oracle_receipts,
        run=run.run,
        score=_score(request, run.run.predictions),
    )


def _score(
    request: ProjectEvaluationRequest, predictions: tuple[Prediction, ...]
) -> ProjectEvaluationScore | None:
    """Score only when the caller supplied truth; silence is not a negative label."""
    truth = request.truth
    if truth is None:
        return None
    matches = match_findings(truth.defects, predictions, line_slack=request.line_slack)
    matched = sum(match.matched for match in matches)
    surfaced = sum(
        1 for prediction in predictions if is_scored_placement(prediction.placement)
    )
    return ProjectEvaluationScore(
        surfaced=surfaced,
        matched=matched,
        unmatched=len(matches) - matched,
        matches=matches,
    )


def _deferred(request: ProjectEvaluationRequest, reason: str) -> ProjectEvaluationResult:
    """An explicit per-case DEFER that hides nothing and invents no label."""
    run = RunRecord(
        run_id=f"{request.case_id}-deferred",
        case_id=request.case_id,
        repeat=request.repeat,
        predictions=(),
        delivery_at_s=None,
        deadline_s=request.deadline_s,
    )
    return ProjectEvaluationResult(
        case_id=request.case_id,
        status="deferred",
        task_id=None,
        base_sha=None,
        head_sha=None,
        predictions=(),
        final_decisions=(),
        abstain_reason=reason,
        latency_s=0.0,
        spend_usd=0.0,
        oracle_spend_usd=0.0,
        artifacts=(),
        evidence_class_counts={},
        oracle_receipts=(),
        run=run,
        score=None,
    )
