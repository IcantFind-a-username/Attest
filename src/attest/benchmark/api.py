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

import hashlib
import importlib.metadata
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass, field, replace
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
from attest.review.executor import (
    GENERATOR_SYSTEM,
    REPRO_SCHEMA,
    ExecutorLimits,
)
from attest.review.ledger import Ledger
from attest.review.proposer import SYSTEM_PROMPT, Provider
from attest.review.schema import PROPOSAL_SCHEMA

GIT_TIMEOUT_S = 60.0
OPAQUE_CASE_PREFIX = "case-"
_OPAQUE_BODY_LENGTH = 12
_HEX_DIGITS = frozenset("0123456789abcdef")
#: Words that would leak the hidden role of a case to the reviewed product.
_LEAKING_TERMS = ("bug", "clean", "fix", "defect", "broken", "buggy", "control", "truth")
_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}")
ABSENT_BINDING_SHA256 = hashlib.sha256(b"absent").hexdigest()
EVALUATION_BINDING_SCHEMA_VERSION = "1"


class ProjectEvaluationError(ValueError):
    """A request was refused before any model, GitHub, or head-code execution."""


@dataclass(frozen=True)
class ProjectEvaluationBinding:
    """Immutable inputs that make a paid evaluation one reproducible stratum."""

    repository: str
    base_sha: str
    head_sha: str
    fixed_sha: str | None
    diff_sha256: str
    truth_sha256: str
    receipt_sha256: str
    policy_sha256: str
    provider_id: str
    model_id: str
    prompt_sha256: str
    schema_sha256: str
    interpreter_id: str
    environment_sha256: str
    code_sha256: str
    budget_usd: float

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": EVALUATION_BINDING_SCHEMA_VERSION,
            "repository": self.repository,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "fixed_sha": self.fixed_sha,
            "diff_sha256": self.diff_sha256,
            "truth_sha256": self.truth_sha256,
            "receipt_sha256": self.receipt_sha256,
            "policy_sha256": self.policy_sha256,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "prompt_sha256": self.prompt_sha256,
            "schema_sha256": self.schema_sha256,
            "interpreter_id": self.interpreter_id,
            "environment_sha256": self.environment_sha256,
            "code_sha256": self.code_sha256,
            "budget_usd": self.budget_usd,
        }


@dataclass(frozen=True)
class RuntimeIdentity:
    """Version identity for the controller interpreter, environment, and code."""

    interpreter_id: str
    environment_sha256: str
    code_sha256: str


def current_runtime_identity() -> RuntimeIdentity:
    """Return stable digests that change when the supported runtime strata change."""
    interpreter_id = (
        f"{sys.implementation.name}-{sys.version_info.major}.{sys.version_info.minor}."
        f"{sys.version_info.micro}-{platform.system().lower()}-{platform.machine().lower()}"
    )
    distributions = sorted(
        (
            str(distribution.metadata["Name"]).lower(),
            distribution.version,
        )
        for distribution in importlib.metadata.distributions()
    )
    package_root = Path(__file__).resolve().parents[1]
    repository_root = Path(__file__).resolve().parents[3]
    return RuntimeIdentity(
        interpreter_id=interpreter_id,
        environment_sha256=_json_digest(distributions),
        code_sha256=_code_sha256(package_root, repository_root),
    )


def _code_sha256(package_root: Path, repository_root: Path) -> str:
    """Digest package behavior, data, and the paid-study controller entrypoints."""
    code_rows = []
    package_paths = (
        candidate
        for candidate in package_root.rglob("*")
        if candidate.is_file() and candidate.suffix in {".json", ".py", ".toml"}
    )
    controller_paths = (
        repository_root / "scripts" / "benchmark.py",
        repository_root / "scripts" / "acceptance" / "phase3.py",
    )
    for path in sorted((*package_paths, *(path for path in controller_paths if path.is_file()))):
        code_rows.append(
            {
                "path": (
                    path.relative_to(repository_root).as_posix()
                    if path.is_relative_to(repository_root)
                    else path.relative_to(package_root).as_posix()
                ),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return _json_digest(code_rows)


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

    @property
    def total_spend_usd(self) -> float:
        return self.spend_usd + self.oracle_spend_usd

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
            "total_spend_usd": round(self.total_spend_usd, 6),
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
    oracle_provider: Provider | None = None,
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
                oracle_provider=oracle_provider,
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


def build_evaluation_binding(
    request: ProjectEvaluationRequest,
    *,
    provider_id: str,
    interpreter_id: str,
    environment_sha256: str,
    code_sha256: str,
    receipt_sha256: str | None = None,
) -> ProjectEvaluationBinding:
    """Resolve and bind every input that may change a paid-study outcome.

    This runs before a provider is constructed. A caller that cannot name its
    provider, interpreter, environment, or exact code is not allowed to create
    a resumable paid-study predeclaration.
    """
    if not request.repository.strip():
        raise ProjectEvaluationError("repository must be a non-empty identity")
    for label, value in (
        ("provider_id", provider_id),
        ("interpreter_id", interpreter_id),
    ):
        if not value:
            raise ProjectEvaluationError(f"{label} must be a non-empty versioned identifier")
    for label, value in (
        ("environment_sha256", environment_sha256),
        ("code_sha256", code_sha256),
    ):
        _require_digest(value, label)
    if receipt_sha256 is not None:
        _require_digest(receipt_sha256, "receipt_sha256")

    resolved = _resolve(request)
    diff = _git_bytes(
        request.repo,
        "diff",
        "--binary",
        "--no-ext-diff",
        resolved.base_sha,
        resolved.head_sha,
        "--",
    )
    if diff is None:
        raise ProjectEvaluationError("could not digest the resolved base/head diff")
    truth_payload: object = None
    if request.truth is not None:
        truth_payload = {
            "fixed_sha": resolved.fixed_sha,
            "defects": [
                asdict(defect)
                for defect in sorted(request.truth.defects, key=lambda item: item.defect_id)
            ],
        }
    config = request.config
    policy = {
        "alpha": config.alpha,
        "budget_usd": config.budget_usd,
        "k_samples": config.k_samples,
        "max_findings": config.max_findings,
        "auto_tighten_alpha": config.auto_tighten_alpha,
        "tier0_commands": list(config.tier0_commands),
        "limits": asdict(request.limits),
        "verification_timeout_s": request.verification_timeout_s,
        "repeats": request.repeats,
        "deadline_s": request.deadline_s,
    }
    prompt_bundle = {"proposal": SYSTEM_PROMPT, "generator": GENERATOR_SYSTEM}
    schema_bundle = {"proposal": PROPOSAL_SCHEMA, "generator": REPRO_SCHEMA}
    return ProjectEvaluationBinding(
        repository=request.repository,
        base_sha=resolved.base_sha,
        head_sha=resolved.head_sha,
        fixed_sha=resolved.fixed_sha,
        diff_sha256=hashlib.sha256(diff).hexdigest(),
        truth_sha256=(
            ABSENT_BINDING_SHA256 if truth_payload is None else _json_digest(truth_payload)
        ),
        receipt_sha256=receipt_sha256 or ABSENT_BINDING_SHA256,
        policy_sha256=_json_digest(policy),
        provider_id=provider_id,
        model_id=config.model,
        prompt_sha256=_json_digest(prompt_bundle),
        schema_sha256=_json_digest(schema_bundle),
        interpreter_id=interpreter_id,
        environment_sha256=environment_sha256,
        code_sha256=code_sha256,
        budget_usd=config.budget_usd,
    )


def freeze_evaluation_request(
    request: ProjectEvaluationRequest, binding: ProjectEvaluationBinding
) -> ProjectEvaluationRequest:
    """Replace movable refs with the SHAs already sealed by a predeclaration."""
    if binding.repository != request.repository:
        raise ProjectEvaluationError("binding repository does not match the request")
    if binding.model_id != request.config.model or binding.budget_usd != request.config.budget_usd:
        raise ProjectEvaluationError("binding model or budget does not match the request")
    truth = request.truth
    frozen_truth = (
        None
        if truth is None
        else replace(truth, fixed_ref=binding.fixed_sha)
    )
    return replace(
        request,
        base_ref=binding.base_sha,
        head_ref=binding.head_sha,
        truth=frozen_truth,
    )


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


def _git_bytes(repo: Path, *args: str) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            check=False,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _require_digest(value: str, label: str) -> None:
    if _DIGEST_PATTERN.fullmatch(value) is None:
        raise ProjectEvaluationError(f"{label} must be a lowercase SHA-256 digest")


def _json_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


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
