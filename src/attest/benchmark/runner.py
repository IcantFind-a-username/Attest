"""Replay one benchmark case through the real product review path.

Nothing in this module reimplements review logic. External uncertainty -- the
model -- is frozen into a cassette and GitHub is bound to a loopback HTTP
server, but the gate, the candidate store, the differential executor, the
ledger, the pytest subprocess and the GitHub adapter are the shipped code. The
runner only observes what those produce.

Two differential records are kept side by side and never merged:

* the **product ledger status**, written by ``verify_candidate`` during the
  review, which is what the tool actually decided at the time; and
* the **benchmark oracle receipt**, produced here by re-running the same
  reproduction against the corpus's fixed reference through the product's own
  ``execute_differential`` classifier.

Scoring reads the oracle receipt. It never rewrites a historical product
decision.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from types import TracebackType
from typing import Any

from attest.benchmark.schema import Placement, Prediction, RunRecord, is_scored_placement
from attest.github.client import GitHubClient
from attest.github.context import PullRequestContext
from attest.review.budget import Budget
from attest.review.candidates import CandidateStore, StoredCandidate
from attest.review.ci import run_ci
from attest.review.config import ReviewConfig
from attest.review.executor import (
    EvidenceClass,
    ExecutorLimits,
    ReproSpec,
    execute_differential,
    generate_repro,
)
from attest.review.ledger import Ledger
from attest.review.proposer import Provider, ProviderResult

GENERATOR_MARKER = "focused pytest reproduction"

#: Differential evidence class -> the benchmark's scoreable reproduction status.
#: Only ``buggy_fail_fixed_pass`` may participate in matching; a new-code
#: candidate is recorded signal that is unpriced by design (D-022) and must
#: never be reported as a failure.
REPRO_STATUS_BY_EVIDENCE_CLASS: Mapping[str, str] = {
    EvidenceClass.REGRESSION_REPRODUCED.value: "buggy_fail_fixed_pass",
    EvidenceClass.UNFAITHFUL.value: "buggy_fail_fixed_fail",
    EvidenceClass.NOT_REPRODUCED.value: "buggy_pass",
    EvidenceClass.NEW_CODE_CANDIDATE.value: "new_code_candidate",
    EvidenceClass.INDETERMINATE.value: "deferred",
}

NOT_EXECUTED = "not_executed"


@dataclass(frozen=True)
class Cassette:
    """One recorded proposer response and one recorded generator response."""

    proposal: str
    repro: str
    input_tokens: int = 0
    output_tokens: int = 0


def load_cassette(root: Path, case_id: str) -> Cassette:
    """Load the recorded responses for one opaque case, failing closed."""
    path = root / f"{case_id}.json"
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cassette for {case_id} is missing or unreadable") from exc
    if not isinstance(document, dict):
        raise ValueError(f"cassette for {case_id} must be an object")
    proposal = document.get("proposal")
    repro = document.get("repro")
    if not isinstance(proposal, str) or not isinstance(repro, str):
        raise ValueError(f"cassette for {case_id} must record a proposal and a reproduction")
    return Cassette(
        proposal=proposal,
        repro=repro,
        input_tokens=_count(document.get("input_tokens", 0), case_id),
        output_tokens=_count(document.get("output_tokens", 0), case_id),
    )


def _count(value: object, case_id: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"cassette for {case_id} has an invalid token count")
    return value


class ReplayProvider:
    """A :class:`Provider` that answers from recorded bytes and nothing else.

    It never constructs an API client, reads a credential, or opens a socket,
    so replay is offline by construction even where credentials exist.
    """

    def __init__(self, cassette: Cassette) -> None:
        self._cassette = cassette
        self._lock = Lock()
        self.proposal_calls = 0
        self.generator_calls = 0

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        """Return the recorded response for whichever product prompt asked."""
        with self._lock:
            if GENERATOR_MARKER in system:
                self.generator_calls += 1
                text = self._cassette.repro
            else:
                self.proposal_calls += 1
                text = self._cassette.proposal
        return ProviderResult(
            text=text,
            input_tokens=self._cassette.input_tokens,
            output_tokens=self._cassette.output_tokens,
        )


class LoopbackGitHub:
    """An in-process GitHub endpoint bound to 127.0.0.1 for delivery observation.

    The product's real :class:`GitHubClient` speaks to it over HTTP, so comment
    upserts and inline reviews exercise the shipped adapter without any remote
    call being possible.
    """

    def __init__(self) -> None:
        self.status_bodies: list[str] = []
        self.review_comments: list[dict[str, object]] = []
        self.reviews: list[dict[str, object]] = []
        self.requests: list[dict[str, object]] = []
        self._comment: dict[str, object] | None = None
        self._lock = Lock()
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self._thread = Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def url(self) -> str:
        host, port = self._server.server_address[0], self._server.server_address[1]
        if isinstance(host, (bytes, bytearray)):
            host = host.decode("ascii")
        return f"http://{host}:{port}"

    def client(self, token: str = "loopback-token") -> GitHubClient:
        """A real product GitHub client pointed at this loopback endpoint."""
        return GitHubClient(token, self.url)

    def close(self) -> None:
        self._server.shutdown()
        self._thread.join()
        self._server.server_close()

    def __enter__(self) -> LoopbackGitHub:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        endpoint = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
                self._respond()

            def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
                self._respond()

            def do_PATCH(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
                self._respond()

            def _respond(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8")
                body = json.loads(raw) if raw else None
                with endpoint._lock:
                    endpoint.requests.append(
                        {"method": self.command, "path": self.path, "body": body}
                    )
                    response = endpoint._record(self.command, self.path, body)
                encoded = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler

    def _record(self, method: str, path: str, body: object) -> object:
        if method == "GET":
            return [] if self._comment is None else [self._comment]
        if not isinstance(body, dict):
            return {"id": 0}
        if path.endswith("/comments") or "/issues/comments/" in path:
            text = str(body.get("body", ""))
            self.status_bodies.append(text)
            self._comment = {"id": 101, "body": text, "user": {"type": "Bot"}}
            return {"id": 101}
        self.reviews.append(body)
        comments = body.get("comments")
        if isinstance(comments, list):
            self.review_comments.extend(
                comment for comment in comments if isinstance(comment, dict)
            )
        return {"id": 202}


@dataclass(frozen=True)
class ReproReceipt:
    """The benchmark's independent differential oracle result for one finding."""

    finding_id: str
    buggy_sha: str
    fixed_sha: str
    repeats: int
    outcome: str
    evidence_class: str
    repro_status: str
    reason: str
    buggy_runs: tuple[str, ...]
    fixed_runs: tuple[str, ...]

    @property
    def confirmed(self) -> bool:
        """Whether the same test failed on the buggy tree and passed on the fixed tree."""
        return self.repro_status == "buggy_fail_fixed_pass"

    def to_json_dict(self) -> dict[str, object]:
        """Deterministic mapping for artifacts and reports."""
        return {
            "finding_id": self.finding_id,
            "buggy_sha": self.buggy_sha,
            "fixed_sha": self.fixed_sha,
            "repeats": self.repeats,
            "outcome": self.outcome,
            "evidence_class": self.evidence_class,
            "repro_status": self.repro_status,
            "reason": self.reason,
            "buggy_runs": list(self.buggy_runs),
            "fixed_runs": list(self.fixed_runs),
            "confirmed": self.confirmed,
        }


def run_differential_repro(
    repo: Path,
    candidate: StoredCandidate,
    spec: ReproSpec,
    limits: ExecutorLimits,
    *,
    buggy_sha: str,
    fixed_sha: str,
    repeats: int = 3,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> ReproReceipt:
    """Score one generated reproduction with the product's own classifier.

    The buggy tree is the reviewed head and the fixed tree is the corpus's
    developer-fix reference. Both sides run under the identical limits and the
    identical interpreter because ``execute_differential`` is the only thing
    that runs them.
    """
    execution = execute_differential(
        repo,
        candidate,
        spec,
        limits,
        base_sha=fixed_sha,
        head_sha=buggy_sha,
        repeats=repeats,
        deadline=deadline,
        clock=clock,
    )
    evidence_class = execution.evidence_class.value
    return ReproReceipt(
        finding_id=candidate.finding.finding_id,
        buggy_sha=execution.head_sha,
        fixed_sha=execution.base_sha,
        repeats=execution.repeats,
        outcome=execution.outcome.value,
        evidence_class=evidence_class,
        repro_status=REPRO_STATUS_BY_EVIDENCE_CLASS[evidence_class],
        reason=execution.reason,
        buggy_runs=tuple(run.outcome.value for run in execution.head_runs),
        fixed_runs=tuple(run.outcome.value for run in execution.base_runs),
    )


def ci_final_decisions(repo: Path, task_id: str) -> tuple[dict[str, Any], ...]:
    """The authoritative post-verification decisions recorded for one task."""
    rows = [
        row
        for row in Ledger(repo).entries()
        if row.get("kind") == "ci_final" and row.get("task_id") == task_id
    ]
    if not rows:
        return ()
    decisions = rows[-1].get("decisions")
    if not isinstance(decisions, list):
        return ()
    return tuple(decision for decision in decisions if isinstance(decision, dict))


def product_evidence_classes(repo: Path, task_id: str) -> dict[str, str]:
    """Per-finding evidence class exactly as the product ledger recorded it."""
    classes: dict[str, str] = {}
    for row in Ledger(repo).entries():
        if row.get("kind") != "verification" or row.get("task_id") != task_id:
            continue
        finding_id = row.get("finding_id")
        evidence_class = row.get("evidence_class", EvidenceClass.INDETERMINATE.value)
        if isinstance(finding_id, str) and isinstance(evidence_class, str):
            classes[finding_id] = evidence_class
    return classes


def extract_predictions(
    repo: Path,
    *,
    task_id: str,
    case_id: str,
    repro_status: Mapping[str, str] | None = None,
    evidence_class: Mapping[str, str] | None = None,
) -> tuple[Prediction, ...]:
    """Join persisted candidate anchors to the authoritative ``ci_final`` row."""
    decisions = ci_final_decisions(repo, task_id)
    if not decisions:
        return ()
    anchors = {
        candidate.finding.finding_id: candidate
        for candidate in CandidateStore(repo).load(task_id)
    }
    statuses = dict(repro_status or {})
    classes = dict(evidence_class or {})
    predictions: list[Prediction] = []
    for decision in decisions:
        finding_id = decision.get("finding_id")
        if not isinstance(finding_id, str) or finding_id not in anchors:
            continue
        candidate = anchors[finding_id]
        predictions.append(
            Prediction.from_joined_ci_final(
                {
                    "finding_id": finding_id,
                    "file": candidate.finding.file,
                    "line": candidate.finding.line,
                },
                decision,
                case_id=case_id,
                repro_status=statuses.get(finding_id, NOT_EXECUTED),
                evidence_class=classes.get(
                    finding_id, EvidenceClass.INDETERMINATE.value
                ),
            )
        )
    return tuple(predictions)


@dataclass(frozen=True)
class CaseRunResult:
    """Everything one replayed case produced, product record and oracle apart."""

    case_id: str
    task_id: str | None
    run: RunRecord
    candidate_count: int
    surfaced_count: int
    deferred_reason: str | None
    spend_usd: float
    oracle_spend_usd: float
    elapsed_s: float
    delivered: bool
    product_evidence_classes: Mapping[str, str]
    oracle_receipts: tuple[ReproReceipt, ...]

    def scored_payload(self) -> dict[str, object]:
        """Deterministic scored view, with task identity and timings excluded.

        Re-running the same cassette against the same tree must reproduce this
        mapping byte for byte; ``task_id``, ``run_id`` and every elapsed value
        are excluded because they are timestamps, not measurements.
        """
        return {
            "case_id": self.case_id,
            "candidate_count": self.candidate_count,
            "surfaced_count": self.surfaced_count,
            "deferred_reason": self.deferred_reason,
            "spend_usd": round(self.spend_usd, 6),
            "oracle_spend_usd": round(self.oracle_spend_usd, 6),
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
                for prediction in self.run.predictions
            ],
            "product_evidence_classes": dict(sorted(self.product_evidence_classes.items())),
            "oracle_receipts": [
                {
                    key: value
                    for key, value in receipt.to_json_dict().items()
                    if key != "reason"
                }
                for receipt in self.oracle_receipts
            ],
        }


class BenchmarkRunner:
    """Drive one benchmark case through ``run_ci`` and score its evidence."""

    def __init__(
        self,
        *,
        limits: ExecutorLimits | None = None,
        verification_timeout_s: float = 600.0,
        repeats: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if repeats < 1:
            raise ValueError("repeats must be at least one")
        self.limits = limits or ExecutorLimits()
        self.verification_timeout_s = verification_timeout_s
        self.repeats = repeats
        self.clock = clock

    def run_case(
        self,
        repo: Path,
        *,
        case_id: str,
        base_sha: str,
        head_sha: str,
        config: ReviewConfig,
        provider: Provider,
        client: GitHubClient,
        fixed_sha: str | None = None,
        oracle_provider: Provider | None = None,
        repository: str = "local/project",
        pull_request_number: int = 1,
        deadline_s: float = 60.0,
        repeat: int = 0,
    ) -> CaseRunResult:
        """Run the real product path, then score it against the fixed reference."""
        context = PullRequestContext(
            repository=repository,
            number=pull_request_number,
            base_sha=base_sha,
            head_sha=head_sha,
            is_fork=False,
        )
        ci = run_ci(
            repo,
            context,
            client,
            config,
            provider,
            verification_timeout_s=self.verification_timeout_s,
            limits=self.limits,
            clock=self.clock,
        )
        task_id = ci.task_id
        product_classes = product_evidence_classes(repo, task_id) if task_id else {}
        receipts: tuple[ReproReceipt, ...] = ()
        oracle_spend = 0.0
        if task_id and fixed_sha is not None:
            receipts, oracle_spend = self._score_evidence(
                repo,
                task_id=task_id,
                case_id=case_id,
                config=config,
                provider=oracle_provider or provider,
                buggy_sha=head_sha,
                fixed_sha=fixed_sha,
            )
        statuses = {receipt.finding_id: receipt.repro_status for receipt in receipts}
        classes = {receipt.finding_id: receipt.evidence_class for receipt in receipts}
        for finding_id, evidence_class in product_classes.items():
            classes.setdefault(finding_id, evidence_class)
        predictions = (
            extract_predictions(
                repo,
                task_id=task_id,
                case_id=case_id,
                repro_status=statuses,
                evidence_class=classes,
            )
            if task_id
            else ()
        )
        delivered = ci.deferred_reason is None
        run = RunRecord(
            run_id=task_id or f"{case_id}-deferred",
            case_id=case_id,
            repeat=repeat,
            predictions=predictions,
            delivery_at_s=ci.elapsed_s if delivered else None,
            deadline_s=deadline_s,
        )
        return CaseRunResult(
            case_id=case_id,
            task_id=task_id,
            run=run,
            candidate_count=ci.candidate_count,
            surfaced_count=ci.surfaced_count,
            deferred_reason=ci.deferred_reason,
            spend_usd=ci.spend_usd,
            oracle_spend_usd=oracle_spend,
            elapsed_s=ci.elapsed_s,
            delivered=delivered,
            product_evidence_classes=product_classes,
            oracle_receipts=receipts,
        )

    def _score_evidence(
        self,
        repo: Path,
        *,
        task_id: str,
        case_id: str,
        config: ReviewConfig,
        provider: Provider,
        buggy_sha: str,
        fixed_sha: str,
    ) -> tuple[tuple[ReproReceipt, ...], float]:
        """Independently re-run reproductions for every author-visible finding.

        Only scored placements are executed: drawer and discarded candidates
        are invisible to the pull-request author and are never matched against
        truth, so paying for their reproduction would buy nothing.
        """
        scored = {
            decision["finding_id"]
            for decision in ci_final_decisions(repo, task_id)
            if isinstance(decision.get("finding_id"), str)
            and _scored(decision.get("placement"))
        }
        if not scored:
            return (), 0.0
        budget = Budget(limit_usd=config.budget_usd, model=config.model)
        receipts: list[ReproReceipt] = []
        for candidate in CandidateStore(repo).load(task_id):
            if candidate.finding.finding_id not in scored:
                continue
            oracle_candidate = replace(candidate, task_id=f"{task_id}-oracle")
            try:
                spec = generate_repro(repo, oracle_candidate, provider, budget)
            except Exception as exc:  # noqa: BLE001 - oracle failures are ternary DEFER
                receipts.append(
                    _deferred_receipt(
                        candidate.finding.finding_id,
                        buggy_sha,
                        fixed_sha,
                        self.repeats,
                        f"benchmark oracle generation failed: {type(exc).__name__}",
                    )
                )
                continue
            receipts.append(
                run_differential_repro(
                    repo,
                    oracle_candidate,
                    spec,
                    self.limits,
                    buggy_sha=buggy_sha,
                    fixed_sha=fixed_sha,
                    repeats=self.repeats,
                )
            )
        return tuple(receipts), budget.spent_usd


def _deferred_receipt(
    finding_id: str, buggy_sha: str, fixed_sha: str, repeats: int, reason: str
) -> ReproReceipt:
    return ReproReceipt(
        finding_id=finding_id,
        buggy_sha=buggy_sha,
        fixed_sha=fixed_sha,
        repeats=repeats,
        outcome="deferred",
        evidence_class=EvidenceClass.INDETERMINATE.value,
        repro_status=REPRO_STATUS_BY_EVIDENCE_CLASS[EvidenceClass.INDETERMINATE.value],
        reason=reason,
        buggy_runs=(),
        fixed_runs=(),
    )


def _scored(placement: object) -> bool:
    if not isinstance(placement, str):
        return False
    try:
        return is_scored_placement(Placement(placement))
    except ValueError:
        return False


def surfaced_predictions(predictions: Sequence[Prediction]) -> tuple[Prediction, ...]:
    """Predictions the pull-request author could actually see."""
    return tuple(
        prediction for prediction in predictions if is_scored_placement(prediction.placement)
    )
