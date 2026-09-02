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
import math
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread
from types import TracebackType
from typing import Any, cast

from attest.benchmark.measurement import (
    ARM_ATTEST_PRODUCT,
    CURRENT_MEASUREMENT_SCHEMA_VERSION,
    CURRENT_MEASUREMENT_SEMANTICS,
    AccuracyStatus,
    DeliveryStatus,
    DeliveryTranscriptReceipt,
    FindingAuthority,
    FindingOutcome,
    FindingStatus,
    MeasurementRecord,
    PublicationChannel,
    PublicationEvent,
    PublicationMember,
    PublicationOutcome,
    PublicationPlacement,
    TaskDeliveryEvent,
    TaskDeliveryTerminalStatus,
    TaskStatus,
    TruthStatus,
    derive_stop_kind,
    derive_task_status,
    empty_delivery_transcript_receipt,
    semantic_measurement_sha256,
)
from attest.benchmark.schema import Placement, Prediction, RunRecord, is_scored_placement
from attest.github.client import GitHubClient
from attest.github.context import PullRequestContext
from attest.review.budget import Budget
from attest.review.candidates import CandidateStore, StoredCandidate
from attest.review.ci import (
    CiDeliveryTranscript,
    CiPublicationEvent,
    CiTaskDeliveryEvent,
    build_delivery_transcript,
    reconcile_delivery_rows,
    run_ci,
)
from attest.review.config import ReviewConfig
from attest.review.executor import (
    EvidenceClass,
    ExecutorLimits,
    ReproSpec,
    execute_differential,
    generate_repro,
)
from attest.review.ledger import Ledger, ci_final_decisions_from_rows
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
    EvidenceClass.UNBOUND.value: "unbound",  # V-02: head failed, base passed, no changed line ran
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
    return ci_final_decisions_from_rows(Ledger(repo).entries_strict(), task_id)


def product_evidence_classes(repo: Path, task_id: str) -> dict[str, str]:
    """Per-finding evidence class exactly as the product ledger recorded it."""
    return product_evidence_classes_from_rows(Ledger(repo).entries_strict(), task_id)


def product_evidence_classes_from_rows(
    ledger_rows: Sequence[Mapping[str, Any]], task_id: str
) -> dict[str, str]:
    """Decode evidence classes from one already-frozen ledger snapshot."""

    classes: dict[str, str] = {}
    for row in ledger_rows:
        if row.get("kind") != "verification" or row.get("task_id") != task_id:
            continue
        finding_id = row.get("finding_id")
        evidence_class = row.get("evidence_class", EvidenceClass.INDETERMINATE.value)
        if isinstance(finding_id, str) and isinstance(evidence_class, str):
            classes[finding_id] = evidence_class
    return classes


def product_candidate_evidence_from_rows(
    ledger_rows: Sequence[Mapping[str, Any]], task_id: str
) -> tuple[dict[str, Any], ...]:
    """Preserve every candidate's structured verification evidence."""

    evidence: list[dict[str, Any]] = []
    finding_ids: set[str] = set()
    for row in ledger_rows:
        if row.get("kind") != "verification" or row.get("task_id") != task_id:
            continue
        finding_id = row.get("finding_id")
        if not isinstance(finding_id, str):
            raise ValueError("verification row requires a finding_id")
        if finding_id in finding_ids:
            raise ValueError("duplicate verification finding_id")
        finding_ids.add(finding_id)
        runs = row.get("run_evidence", [])
        if not isinstance(runs, list) or not all(isinstance(run, dict) for run in runs):
            raise ValueError("verification run_evidence must be a list of mappings")
        evidence.append(
            {
                "finding_id": finding_id,
                "outcome": row.get("outcome"),
                "evidence_class": row.get(
                    "evidence_class", EvidenceClass.INDETERMINATE.value
                ),
                "reason": row.get("reason"),
                "runs": [dict(run) for run in runs],
            }
        )
    return tuple(evidence)


def extract_predictions(
    repo: Path,
    *,
    task_id: str,
    case_id: str,
    repro_status: Mapping[str, str] | None = None,
    evidence_class: Mapping[str, str] | None = None,
    publication_events: Sequence[CiPublicationEvent] = (),
    repository: str | None = None,
    pull_request_number: int | None = None,
    head_sha: str | None = None,
) -> tuple[Prediction, ...]:
    """Join persisted candidate anchors to the authoritative ``ci_final`` row."""
    return extract_predictions_from_rows(
        repo,
        ledger_rows=Ledger(repo).entries_strict(),
        task_id=task_id,
        case_id=case_id,
        repro_status=repro_status,
        evidence_class=evidence_class,
        publication_events=publication_events,
        repository=repository,
        pull_request_number=pull_request_number,
        head_sha=head_sha,
    )


def extract_predictions_from_rows(
    repo: Path,
    *,
    ledger_rows: Sequence[Mapping[str, Any]],
    task_id: str,
    case_id: str,
    repro_status: Mapping[str, str] | None = None,
    evidence_class: Mapping[str, str] | None = None,
    publication_events: Sequence[CiPublicationEvent] = (),
    repository: str | None = None,
    pull_request_number: int | None = None,
    head_sha: str | None = None,
) -> tuple[Prediction, ...]:
    """Join candidates to ci_final and delivery from one ledger snapshot."""

    decisions = ci_final_decisions_from_rows(ledger_rows, task_id)
    if not decisions:
        return ()
    candidates = CandidateStore(repo).load(task_id)
    anchors = {candidate.finding.finding_id: candidate for candidate in candidates}
    if len(anchors) != len(candidates):
        raise ValueError("duplicate candidate finding_id")
    decision_ids = {str(decision["finding_id"]) for decision in decisions}
    if decision_ids != set(anchors):
        raise ValueError("ci_final references an unknown or missing candidate finding_id")
    published_ids = _published_finding_ids(
        decisions,
        publication_events,
        repository=repository,
        pull_request_number=pull_request_number,
        head_sha=head_sha,
    )
    statuses = dict(repro_status or {})
    classes = dict(evidence_class or {})
    predictions: list[Prediction] = []
    for decision in decisions:
        finding_id = decision.get("finding_id")
        if not isinstance(finding_id, str) or finding_id not in published_ids:
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


def _published_finding_ids(
    decisions: Sequence[Mapping[str, Any]],
    publication_events: Sequence[CiPublicationEvent],
    *,
    repository: str | None,
    pull_request_number: int | None,
    head_sha: str | None,
) -> frozenset[str]:
    """Derive visibility only from typed, settled, exact-member API events."""

    event_ids = tuple(event.event_id for event in publication_events)
    if len(set(event_ids)) != len(event_ids):
        raise ValueError("duplicate publication event_id")
    decisions_by_id = {str(decision["finding_id"]): decision for decision in decisions}
    published: set[str] = set()
    for event in publication_events:
        if repository is not None and event.repository != repository:
            raise ValueError("publication event repository binding mismatch")
        if (
            pull_request_number is not None
            and event.pull_request_number != pull_request_number
        ):
            raise ValueError("publication event pull-request binding mismatch")
        if head_sha is not None and event.head_sha != head_sha:
            raise ValueError("publication event head binding mismatch")
        member_ids: set[str] = set()
        for finding_id, placement_value in event.members:
            if finding_id in member_ids:
                raise ValueError("duplicate publication member finding_id")
            member_ids.add(finding_id)
            decision = decisions_by_id.get(finding_id)
            if decision is None:
                raise ValueError("publication event references an unknown finding_id")
            if decision.get("action") != "surface":
                raise ValueError("publication event member is not a ci_final surface decision")
            if placement_value != decision["placement"]:
                raise ValueError("publication event placement does not match ci_final")
            if event.channel == "inline_review" and placement_value != "inline":
                raise ValueError("inline publication event contains a non-inline member")
            if event.outcome == "succeeded":
                published.add(finding_id)
    return frozenset(published)


def _delivery_terminal_status(
    publication_events: Sequence[CiPublicationEvent],
    task_events: Sequence[CiTaskDeliveryEvent],
) -> TaskDeliveryTerminalStatus:
    """Return one typed terminal status; a missing status is an execution failure."""

    if any(event.outcome == PublicationOutcome.FAILED.value for event in publication_events):
        return TaskDeliveryTerminalStatus.FAILED
    values = {event.terminal_status for event in task_events}
    if len(values) > 1:
        raise ValueError("fresh outcome contains conflicting terminal task statuses")
    if not values:
        return TaskDeliveryTerminalStatus.FAILED
    try:
        return TaskDeliveryTerminalStatus(next(iter(values)))
    except ValueError as exc:
        raise ValueError("fresh outcome contains an unknown terminal task status") from exc


def _execution_measurement(
    repo: Path,
    *,
    task_id: str | None,
    case_id: str,
    arm: str,
    repeat: int,
    repository: str,
    head_sha: str,
    pull_request_number: int,
    deadline_s: float,
    terminal_status: TaskDeliveryTerminalStatus,
    candidate_count: int,
    decisions: Sequence[Mapping[str, Any]],
    predictions: Sequence[Prediction],
    publication_events: Sequence[CiPublicationEvent],
    task_delivery_events: Sequence[CiTaskDeliveryEvent],
    delivery_transcript: CiDeliveryTranscript | None,
) -> MeasurementRecord:
    """Build the unadjudicated execution layer from exact API events and candidates."""

    candidates = CandidateStore(repo).load(task_id) if task_id is not None else []
    if len(candidates) != candidate_count:
        raise ValueError("candidate count does not match the persisted candidate store")
    candidate_ids = tuple(candidate.finding.finding_id for candidate in candidates)
    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("duplicate persisted candidate finding_id")
    decisions_by_id = {str(decision["finding_id"]): decision for decision in decisions}
    if decisions and set(decisions_by_id) != set(candidate_ids):
        raise ValueError("ci_final candidate join is incomplete")
    prediction_ids = {prediction.finding_id for prediction in predictions}
    if (
        _published_finding_ids(
            decisions,
            publication_events,
            repository=repository,
            pull_request_number=pull_request_number,
            head_sha=head_sha,
        )
        != prediction_ids
    ):
        raise ValueError("predictions do not equal authorized publication event members")

    typed_events: list[PublicationEvent] = []
    successful_events_by_finding: dict[str, list[PublicationEvent]] = {}
    ambiguous_events_by_finding: dict[str, list[PublicationEvent]] = {}
    for event in publication_events:
        if (
            event.repository != repository
            or event.pull_request_number != pull_request_number
            or event.head_sha != head_sha
        ):
            raise ValueError("publication event target does not match the evaluation")
        if event.deadline_s != deadline_s:
            raise ValueError("publication event deadline does not match the evaluation")
        try:
            outcome = PublicationOutcome(event.outcome)
            channel = PublicationChannel(event.channel)
        except ValueError as exc:
            raise ValueError("unknown publication event outcome or channel") from exc
        members = tuple(
            PublicationMember(
                finding_id=finding_id,
                placement=PublicationPlacement(placement),
            )
            for finding_id, placement in event.members
        )
        typed = PublicationEvent(
            event_id=event.event_id,
            attempt_id=event.attempt_id,
            attempt_ordinal=event.attempt_ordinal,
            repository=event.repository,
            pull_request_number=event.pull_request_number,
            head_sha=event.head_sha,
            members=members,
            channel=channel,
            outcome=outcome,
            body_sha256=event.body_sha256,
            request_sha256=event.request_sha256,
            remote_response_id=event.remote_response_id,
            delivered_at_s=event.delivered_at_s,
            deadline_s=deadline_s,
        )
        typed_events.append(typed)
        for member in members:
            if outcome is PublicationOutcome.SUCCEEDED:
                successful_events_by_finding.setdefault(member.finding_id, []).append(typed)
            elif outcome is PublicationOutcome.AMBIGUOUS:
                ambiguous_events_by_finding.setdefault(member.finding_id, []).append(
                    typed
                )
    findings: list[FindingOutcome] = []
    for candidate in candidates:
        finding_id = candidate.finding.finding_id
        successful_event_ids = tuple(
            event.event_id
            for event in sorted(
                successful_events_by_finding.get(finding_id, ()),
                key=lambda event: event.attempt_ordinal,
            )
        )
        decision = decisions_by_id.get(finding_id)
        placement = None if decision is None else str(decision["placement"])
        if successful_event_ids:
            finding_status = FindingStatus.PUBLISHED
            accuracy_status = AccuracyStatus.UNADJUDICATED
        elif placement == Placement.DISCARD.value:
            finding_status = FindingStatus.CERTIFIED_SUPPRESSED
            accuracy_status = AccuracyStatus.NOT_APPLICABLE
        else:
            finding_status = FindingStatus.UNRESOLVED
            accuracy_status = AccuracyStatus.UNADJUDICATED
        findings.append(
            FindingOutcome(
                finding_id=finding_id,
                finding_status=finding_status,
                accuracy_status=accuracy_status,
                defect_id=None,
                publication_event_ids=successful_event_ids,
                authority=FindingAuthority.AUTOMATED,
            )
        )

    unresolved_count = sum(
        finding.finding_status is FindingStatus.UNRESOLVED for finding in findings
    )
    stop_kind = derive_stop_kind(terminal_status, findings)
    published_count = len(prediction_ids)
    if published_count:
        on_time_by_finding = {
            finding_id: any(
                event.outcome is PublicationOutcome.SUCCEEDED
                and event.delivered_on_time is True
                and any(member.finding_id == finding_id for member in event.members)
                for event in typed_events
            )
            for finding_id in prediction_ids
        }
        delivery_status = (
            DeliveryStatus.PUBLISHED_ON_TIME
            if all(on_time_by_finding.values())
            else DeliveryStatus.PUBLISHED_LATE
        )
    else:
        delivery_status = DeliveryStatus.NO_PUBLICATION
    ambiguous_unresolved = set(ambiguous_events_by_finding) - prediction_ids
    delivery_ambiguous = {
        finding_id
        for finding_id, ambiguous_events in ambiguous_events_by_finding.items()
        if not successful_events_by_finding.get(finding_id)
        or min(event.attempt_ordinal for event in ambiguous_events)
        < min(
            event.attempt_ordinal
            for event in successful_events_by_finding[finding_id]
        )
    }
    typed_task_events: list[TaskDeliveryEvent] = []
    for task_event in task_delivery_events:
        if (
            task_event.repository != repository
            or task_event.pull_request_number != pull_request_number
            or task_event.head_sha != head_sha
        ):
            raise ValueError("task delivery target does not match the evaluation")
        if task_event.deadline_s != deadline_s:
            raise ValueError("task delivery deadline does not match the evaluation")
        try:
            outcome = PublicationOutcome(task_event.outcome)
            terminal_status = TaskDeliveryTerminalStatus(task_event.terminal_status)
        except ValueError as exc:
            raise ValueError("unknown task delivery outcome or terminal status") from exc
        typed_task_events.append(
            TaskDeliveryEvent(
                event_id=task_event.event_id,
                attempt_id=task_event.attempt_id,
                attempt_ordinal=task_event.attempt_ordinal,
                repository=task_event.repository,
                pull_request_number=task_event.pull_request_number,
                head_sha=task_event.head_sha,
                channel=PublicationChannel(task_event.channel),
                members=tuple(
                    PublicationMember(
                        finding_id=finding_id,
                        placement=PublicationPlacement(placement),
                    )
                    for finding_id, placement in task_event.members
                ),
                terminal_status=terminal_status,
                outcome=outcome,
                body_sha256=task_event.body_sha256,
                request_sha256=task_event.request_sha256,
                remote_response_id=task_event.remote_response_id,
                delivered_at_s=task_event.delivered_at_s,
                deadline_s=deadline_s,
            )
        )
    task_success_ordinals = tuple(
        event.attempt_ordinal for event in typed_task_events if event.succeeded
    )
    task_ambiguous_ordinals = tuple(
        event.attempt_ordinal
        for event in typed_task_events
        if event.outcome is PublicationOutcome.AMBIGUOUS
    )
    task_ambiguous = bool(task_ambiguous_ordinals) and (
        not task_success_ordinals
        or min(task_ambiguous_ordinals) < min(task_success_ordinals)
    )
    if delivery_transcript is None:
        if task_id is not None or publication_events or task_delivery_events:
            raise ValueError("current execution requires a sealed delivery transcript")
        typed_transcript = empty_delivery_transcript_receipt()
    else:
        if type(delivery_transcript) is not CiDeliveryTranscript:
            raise ValueError("current execution requires an exact delivery transcript")
        if task_id != delivery_transcript.task_id:
            raise ValueError("delivery transcript task binding mismatch")
        typed_transcript = DeliveryTranscriptReceipt(
            schema_version=delivery_transcript.schema_version,
            protocol=delivery_transcript.protocol,
            task_id=delivery_transcript.task_id,
            expected_attempt_count=delivery_transcript.expected_attempt_count,
            last_attempt_ordinal=delivery_transcript.last_attempt_ordinal,
            transcript_sha256=delivery_transcript.transcript_sha256,
        )
    return MeasurementRecord(
        schema_version=CURRENT_MEASUREMENT_SCHEMA_VERSION,
        scoring_semantics=CURRENT_MEASUREMENT_SEMANTICS,
        case_id=case_id,
        arm=arm,
        repeat=repeat,
        stop_kind=stop_kind,
        task_status=derive_task_status(stop_kind, findings),
        findings=tuple(findings),
        eligible_defect_ids=(),
        pull_request_number=pull_request_number,
        truth_status=TruthStatus.UNADJUDICATED,
        delivery_status=delivery_status,
        candidate_count=len(findings),
        published_count=published_count,
        unresolved_count=unresolved_count,
        publication_events=tuple(typed_events),
        task_delivery_events=tuple(typed_task_events),
        delivery_transcript=typed_transcript,
        metrics_withheld_reason=(
            "ambiguous_publication" if ambiguous_unresolved else None
        ),
        delivery_withheld_reason=(
            "ambiguous_publication" if delivery_ambiguous else None
        ),
        task_delivery_withheld_reason=(
            "ambiguous_task_delivery" if task_ambiguous else None
        ),
    )


def rebuild_case_run_from_ledger(
    repo: Path,
    run: CaseRunResult,
    ledger_rows: Sequence[Mapping[str, Any]],
    *,
    repository: str,
    head_sha: str,
    pull_request_number: int,
    deadline_s: float,
    expected_authority: ExecutionResultAuthority,
) -> CaseRunResult:
    """Freshly reconstruct current delivery and publication from one strict snapshot."""

    rows = [dict(row) for row in ledger_rows]
    if type(expected_authority) is not ExecutionResultAuthority:
        raise ValueError("fresh outcome requires an exact execution-result authority")
    expected = expected_authority.measurement
    if type(expected) is not MeasurementRecord:
        raise ValueError("fresh outcome requires an exact current measurement")
    transcript = expected.delivery_transcript
    authoritative_task_id = transcript.task_id
    if run.oracle_receipts != expected_authority.oracle_receipts:
        raise ValueError("fresh outcome oracle receipt mismatch")
    if dict(run.product_evidence_classes) != dict(
        expected_authority.product_evidence_classes
    ):
        raise ValueError("fresh outcome product evidence mismatch")
    if run.run.predictions != expected_authority.predictions:
        raise ValueError("fresh outcome prediction authority mismatch")
    if run.measurement.publication_events != expected.publication_events:
        raise ValueError("fresh outcome publication mismatch")
    if run.measurement.task_delivery_events != expected.task_delivery_events:
        raise ValueError("fresh outcome task delivery mismatch")
    if run.measurement != expected:
        raise ValueError("fresh outcome measurement mismatch")
    if (
        run.case_id != expected.case_id
        or run.run.case_id != expected.case_id
        or run.run.repeat != expected.repeat
    ):
        raise ValueError("fresh outcome run binding mismatch")
    if run.candidate_count != expected_authority.candidate_count:
        raise ValueError("fresh outcome candidate count mismatch")
    if run.surfaced_count != expected_authority.surfaced_count:
        raise ValueError("fresh outcome surfaced count mismatch")
    if (
        run.spend_usd != expected_authority.spend_usd
        or run.oracle_spend_usd != expected_authority.oracle_spend_usd
        or run.elapsed_s != expected_authority.elapsed_s
    ):
        raise ValueError("fresh outcome operational totals mismatch")
    current_delivery_kinds = {
        "delivery_attempt_intent",
        "delivery_attempt_settlement",
        "delivery_journal_finalization",
    }
    if authoritative_task_id is None:
        if any(row.get("kind") in current_delivery_kinds for row in rows):
            raise ValueError("taskless outcome conflicts with fresh delivery ledger")
        if run.task_id is not None:
            raise ValueError("taskless outcome conflicts with caller run state")
        if (
            expected_authority.predictions
            or expected_authority.oracle_receipts
            or expected_authority.product_evidence_classes
            or expected_authority.candidate_count != 0
            or expected_authority.surfaced_count != 0
            or expected.findings
            or expected.publication_events
            or expected.task_delivery_events
            or expected.candidate_count != 0
            or expected.published_count != 0
            or expected.unresolved_count != 0
        ):
            raise ValueError("taskless fresh outcome authority is not empty")
        return replace(
            run,
            case_id=expected.case_id,
            task_id=None,
            run=RunRecord(
                run_id=f"{expected.case_id}-deferred",
                case_id=expected.case_id,
                repeat=expected.repeat,
                predictions=expected_authority.predictions,
                delivery_at_s=None,
                deadline_s=deadline_s,
            ),
            candidate_count=expected_authority.candidate_count,
            surfaced_count=expected_authority.surfaced_count,
            deferred_reason=(
                None
                if expected.task_status is TaskStatus.COMPLETED
                else f"measurement task status was {expected.task_status.value}"
            ),
            delivered=False,
            spend_usd=expected_authority.spend_usd,
            oracle_spend_usd=expected_authority.oracle_spend_usd,
            elapsed_s=expected_authority.elapsed_s,
            product_evidence_classes=dict(
                expected_authority.product_evidence_classes
            ),
            oracle_receipts=expected_authority.oracle_receipts,
            measurement=expected,
        )
    if run.task_id != authoritative_task_id:
        raise ValueError("fresh outcome task binding mismatch")

    publication_events, task_delivery_events = reconcile_delivery_rows(
        rows,
        authoritative_task_id,
        expected_transcript_sha256=transcript.transcript_sha256,
    )
    fresh_transcript = build_delivery_transcript(
        [
            row
            for row in rows
            if not (
                row.get("task_id") == authoritative_task_id
                and row.get("kind") == "delivery_journal_finalization"
            )
        ],
        authoritative_task_id,
    )
    fresh_receipt = DeliveryTranscriptReceipt(
        schema_version=fresh_transcript.schema_version,
        protocol=fresh_transcript.protocol,
        task_id=fresh_transcript.task_id,
        expected_attempt_count=fresh_transcript.expected_attempt_count,
        last_attempt_ordinal=fresh_transcript.last_attempt_ordinal,
        transcript_sha256=fresh_transcript.transcript_sha256,
    )
    if fresh_receipt != transcript:
        raise ValueError("fresh outcome delivery transcript mismatch")

    terminal_status = _delivery_terminal_status(
        publication_events, task_delivery_events
    )
    fresh_deferred_reason = _deferred_reason_from_rows(
        rows, authoritative_task_id, terminal_status
    )

    decisions = ci_final_decisions_from_rows(rows, authoritative_task_id)
    classes = product_evidence_classes_from_rows(rows, authoritative_task_id)
    statuses = {
        receipt.finding_id: receipt.repro_status
        for receipt in expected_authority.oracle_receipts
    }
    receipt_classes = {
        receipt.finding_id: receipt.evidence_class
        for receipt in expected_authority.oracle_receipts
    }
    for finding_id, evidence_class in classes.items():
        receipt_classes.setdefault(finding_id, evidence_class)
    predictions = extract_predictions_from_rows(
        repo,
        ledger_rows=rows,
        task_id=authoritative_task_id,
        case_id=run.case_id,
        repro_status=statuses,
        evidence_class=receipt_classes,
        publication_events=publication_events,
        repository=repository,
        pull_request_number=pull_request_number,
        head_sha=head_sha,
    )
    candidate_count = len(CandidateStore(repo).load(authoritative_task_id))
    fresh_measurement = _execution_measurement(
        repo,
        task_id=authoritative_task_id,
        case_id=run.case_id,
        arm=ARM_ATTEST_PRODUCT,
        repeat=run.run.repeat,
        repository=repository,
        head_sha=head_sha,
        pull_request_number=pull_request_number,
        deadline_s=deadline_s,
        terminal_status=terminal_status,
        candidate_count=candidate_count,
        decisions=decisions,
        predictions=predictions,
        publication_events=publication_events,
        task_delivery_events=task_delivery_events,
        delivery_transcript=fresh_transcript,
    )
    if fresh_measurement.publication_events != expected.publication_events:
        raise ValueError("fresh outcome publication mismatch")
    if fresh_measurement.task_delivery_events != expected.task_delivery_events:
        raise ValueError("fresh outcome task delivery mismatch")
    if fresh_measurement != expected:
        raise ValueError("fresh outcome measurement mismatch")
    if predictions != expected_authority.predictions:
        raise ValueError("fresh outcome prediction authority mismatch")
    if run.run.predictions != predictions:
        raise ValueError("fresh outcome prediction mismatch")
    if (
        run.candidate_count != candidate_count
        or run.candidate_count != expected_authority.candidate_count
    ):
        raise ValueError("fresh outcome candidate count mismatch")
    successful_task_deliveries = tuple(
        event
        for event in fresh_measurement.task_delivery_events
        if event.succeeded and event.delivered_at_s is not None
    )
    delivery_at_s = (
        min(cast(float, event.delivered_at_s) for event in successful_task_deliveries)
        if successful_task_deliveries
        and fresh_measurement.task_delivery_withheld_reason is None
        else None
    )
    fresh_run = RunRecord(
        run_id=authoritative_task_id,
        case_id=run.case_id,
        repeat=run.run.repeat,
        predictions=predictions,
        delivery_at_s=delivery_at_s,
        deadline_s=deadline_s,
    )
    return replace(
        run,
        run=fresh_run,
        candidate_count=candidate_count,
        surfaced_count=fresh_measurement.published_count,
        deferred_reason=fresh_deferred_reason,
        delivered=delivery_at_s is not None,
        spend_usd=expected_authority.spend_usd,
        oracle_spend_usd=expected_authority.oracle_spend_usd,
        elapsed_s=expected_authority.elapsed_s,
        product_evidence_classes=dict(
            expected_authority.product_evidence_classes
        ),
        oracle_receipts=expected_authority.oracle_receipts,
        measurement=fresh_measurement,
    )


def _deferred_reason_from_rows(
    rows: Sequence[Mapping[str, Any]],
    task_id: str,
    terminal_status: TaskDeliveryTerminalStatus,
) -> str | None:
    """Recover the detailed terminal reason from the strict ledger snapshot."""

    if terminal_status is TaskDeliveryTerminalStatus.COMPLETED:
        return None
    verification_reasons = [
        str(row["reason"])
        for row in rows
        if row.get("kind") == "verification"
        and row.get("task_id") == task_id
        and row.get("outcome") == "deferred"
        and type(row.get("reason")) is str
        and row["reason"]
    ]
    if verification_reasons:
        counts = Counter(verification_reasons)
        details = []
        for reason, count in counts.items():
            candidate_word = "candidate" if count == 1 else "candidates"
            suffix = (
                ""
                if len(verification_reasons) == 1
                else f" ({count} {candidate_word})"
            )
            details.append(reason + suffix)
        return "verification deferred: " + "; ".join(details)
    defer_reasons = [
        str(row["reason"])
        for row in rows
        if row.get("kind") == "defer"
        and row.get("task_id") == task_id
        and type(row.get("reason")) is str
        and row["reason"]
    ]
    if defer_reasons:
        return defer_reasons[-1]
    github_reasons = [
        str(row["reason"])
        for row in rows
        if row.get("kind") == "github_comment"
        and row.get("task_id") == task_id
        and row.get("outcome") == "failed"
        and type(row.get("reason")) is str
        and row["reason"]
    ]
    if github_reasons:
        return github_reasons[-1]
    return f"terminal task status was {terminal_status.value}"


@dataclass(frozen=True)
class CaseRunResult:
    """Everything one replayed case produced, product record and oracle apart."""

    case_id: str
    task_id: str | None
    run: RunRecord
    candidate_count: int
    surfaced_count: int
    spend_usd: float
    oracle_spend_usd: float
    elapsed_s: float
    deferred_reason: str | None
    delivered: bool
    product_evidence_classes: Mapping[str, str]
    oracle_receipts: tuple[ReproReceipt, ...]
    measurement: MeasurementRecord

    def scored_payload(self) -> dict[str, object]:
        """Deterministic scored view, with task identity and timings excluded.

        Re-running the same cassette against the same tree must reproduce this
        mapping byte for byte; ``task_id``, ``run_id`` and every elapsed value
        are excluded because they are timestamps, not measurements.
        """
        return {
            "schema_version": 2,
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
            "measurement": self.measurement.to_json_dict(),
            "semantic_measurement_sha256": semantic_measurement_sha256(
                self.measurement
            ),
        }


@dataclass(frozen=True)
class ExecutionResultAuthority:
    """Controller-frozen execution result captured before caller mutation."""

    measurement: MeasurementRecord
    oracle_receipts: tuple[ReproReceipt, ...]
    product_evidence_classes: tuple[tuple[str, str], ...]
    predictions: tuple[Prediction, ...]
    candidate_count: int
    surfaced_count: int
    spend_usd: float
    oracle_spend_usd: float
    elapsed_s: float

    def __post_init__(self) -> None:
        if type(self.measurement) is not MeasurementRecord:
            raise ValueError("execution authority requires an exact measurement")
        if type(self.oracle_receipts) is not tuple or any(
            type(receipt) is not ReproReceipt for receipt in self.oracle_receipts
        ):
            raise ValueError("execution authority requires exact oracle receipts")
        if type(self.product_evidence_classes) is not tuple or any(
            type(row) is not tuple
            or len(row) != 2
            or any(type(value) is not str or not value for value in row)
            for row in self.product_evidence_classes
        ):
            raise ValueError("execution authority requires exact product evidence rows")
        if type(self.predictions) is not tuple or any(
            type(prediction) is not Prediction for prediction in self.predictions
        ):
            raise ValueError("execution authority requires exact predictions")
        if type(self.candidate_count) is not int or self.candidate_count < 0:
            raise ValueError("execution authority candidate_count is invalid")
        if type(self.surfaced_count) is not int or self.surfaced_count < 0:
            raise ValueError("execution authority surfaced_count is invalid")
        for name in ("spend_usd", "oracle_spend_usd", "elapsed_s"):
            value = getattr(self, name)
            if (
                type(value) not in {int, float}
                or not math.isfinite(float(value))
                or value < 0
            ):
                raise ValueError(f"execution authority {name} is invalid")
            number = float(value)
            object.__setattr__(self, name, 0.0 if number == 0.0 else number)

    @classmethod
    def from_case_run(cls, run: CaseRunResult) -> ExecutionResultAuthority:
        return cls(
            measurement=run.measurement,
            oracle_receipts=run.oracle_receipts,
            product_evidence_classes=tuple(
                sorted(run.product_evidence_classes.items())
            ),
            predictions=run.run.predictions,
            candidate_count=run.candidate_count,
            surfaced_count=run.surfaced_count,
            spend_usd=run.spend_usd,
            oracle_spend_usd=run.oracle_spend_usd,
            elapsed_s=run.elapsed_s,
        )


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
        execution_result_sink: Callable[[ExecutionResultAuthority], None] | None = None,
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
            publication_deadline_s=deadline_s,
            # historical pairs are replayed in reverse (head is an ancestor of
            # the base), so the harness declares the counterfactual it built
            merge_base_sha=base_sha,
        )
        task_id = ci.task_id
        product_classes = product_evidence_classes(repo, task_id) if task_id else {}
        decisions = ci_final_decisions(repo, task_id) if task_id else ()
        visible_predictions = (
            extract_predictions(
                repo,
                task_id=task_id,
                case_id=case_id,
                evidence_class=product_classes,
                publication_events=ci.publication_events,
                repository=repository,
                pull_request_number=pull_request_number,
                head_sha=head_sha,
            )
            if task_id
            else ()
        )
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
                finding_ids=frozenset(
                    prediction.finding_id for prediction in visible_predictions
                ),
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
                publication_events=ci.publication_events,
                repository=repository,
                pull_request_number=pull_request_number,
                head_sha=head_sha,
            )
            if task_id
            else ()
        )
        measurement = _execution_measurement(
            repo,
            task_id=task_id,
            case_id=case_id,
            arm=ARM_ATTEST_PRODUCT,
            repeat=repeat,
            repository=repository,
            head_sha=head_sha,
            pull_request_number=pull_request_number,
            deadline_s=deadline_s,
            terminal_status=_delivery_terminal_status(
                ci.publication_events, ci.task_delivery_events
            ),
            candidate_count=ci.candidate_count,
            decisions=decisions,
            predictions=predictions,
            publication_events=ci.publication_events,
            task_delivery_events=ci.task_delivery_events,
            delivery_transcript=ci.delivery_transcript,
        )
        successful_task_deliveries = tuple(
            event
            for event in ci.task_delivery_events
            if event.outcome == "succeeded" and event.delivered_at_s is not None
        )
        delivery_at_s = (
            min(
                cast(float, event.delivered_at_s)
                for event in successful_task_deliveries
            )
            if successful_task_deliveries
            and measurement.task_delivery_withheld_reason is None
            else None
        )
        delivered = delivery_at_s is not None
        run = RunRecord(
            run_id=task_id or f"{case_id}-deferred",
            case_id=case_id,
            repeat=repeat,
            predictions=predictions,
            delivery_at_s=delivery_at_s,
            deadline_s=deadline_s,
        )
        result = CaseRunResult(
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
            measurement=measurement,
        )
        if execution_result_sink is not None:
            execution_result_sink(ExecutionResultAuthority.from_case_run(result))
        return result

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
        finding_ids: frozenset[str],
    ) -> tuple[tuple[ReproReceipt, ...], float]:
        """Independently re-run reproductions for every author-visible finding.

        Only scored placements are executed: drawer and discarded candidates
        are invisible to the pull-request author and are never matched against
        truth, so paying for their reproduction would buy nothing.
        """
        if not finding_ids:
            return (), 0.0
        budget = Budget(limit_usd=config.budget_usd, model=config.model)
        receipts: list[ReproReceipt] = []
        for candidate in CandidateStore(repo).load(task_id):
            if candidate.finding.finding_id not in finding_ids:
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
