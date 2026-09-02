"""Two-stage GitHub CI review orchestration."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from attest.certification.types import CertifiedFinding
from attest.github.client import (
    STATUS_MARKER,
    GitHubApiError,
    GitHubClient,
    PreparedGitHubWrite,
)
from attest.github.context import PullRequestContext
from attest.github.presentation import (
    inline_comments,
    render_complete,
    render_deferred,
    render_running,
)
from attest.review.config import ReviewConfig, resolve_review_policy
from attest.review.diffs import resolve_merge_base
from attest.review.executor import ExecutorLimits
from attest.review.ledger import Ledger
from attest.review.proposer import Provider
from attest.review.run import ReviewExecutionError, ReviewSetupError, make_task_id, run_review
from attest.review.status import status_from_rows
from attest.review.verification import CERTIFICATION_REPEATS, run_verification_stage

DELIVERY_TRANSCRIPT_SCHEMA_VERSION = 1
DELIVERY_TRANSCRIPT_PROTOCOL = "attest.delivery-transcript.v1"
__all__ = ["CERTIFICATION_REPEATS", "run_ci"]


@dataclass
class CiRun:
    task_id: str | None
    candidate_count: int
    surfaced_count: int
    deferred_reason: str | None
    spend_usd: float
    elapsed_s: float
    publication_events: tuple[CiPublicationEvent, ...] = ()
    task_delivery_events: tuple[CiTaskDeliveryEvent, ...] = ()
    delivery_transcript: CiDeliveryTranscript | None = None


@dataclass(frozen=True)
class CiPublicationEvent:
    """Settled or ambiguous batched finding-publication attempt."""

    event_id: str
    attempt_id: str
    attempt_ordinal: int
    repository: str
    pull_request_number: int
    head_sha: str
    channel: str
    members: tuple[tuple[str, str], ...]
    body_sha256: str
    request_sha256: str
    outcome: str
    remote_response_id: str | None
    delivered_at_s: float | None
    deadline_s: float | None


@dataclass(frozen=True)
class CiTaskDeliveryEvent:
    """Settled or ambiguous terminal task-status delivery attempt."""

    event_id: str
    attempt_id: str
    attempt_ordinal: int
    repository: str
    pull_request_number: int
    head_sha: str
    channel: str
    members: tuple[tuple[str, str], ...]
    terminal_status: str
    body_sha256: str
    request_sha256: str
    outcome: str
    remote_response_id: str | None
    delivered_at_s: float | None
    deadline_s: float | None


@dataclass(frozen=True)
class CiDeliveryTranscript:
    """Versioned digest receipt for one ordered delivery-attempt transcript."""

    schema_version: int
    protocol: str
    task_id: str
    expected_attempt_count: int
    last_attempt_ordinal: int | None
    transcript_sha256: str

    def __post_init__(self) -> None:
        if (
            type(self.schema_version) is not int
            or self.schema_version != DELIVERY_TRANSCRIPT_SCHEMA_VERSION
        ):
            raise ValueError("unsupported delivery transcript schema_version")
        if type(self.protocol) is not str or self.protocol != DELIVERY_TRANSCRIPT_PROTOCOL:
            raise ValueError("unsupported delivery transcript protocol")
        _delivery_string(self.task_id, "task_id")
        _delivery_nonnegative_int(self.expected_attempt_count, "expected_attempt_count")
        expected_last = self.expected_attempt_count - 1 if self.expected_attempt_count else None
        if self.last_attempt_ordinal != expected_last:
            raise ValueError("delivery transcript last ordinal mismatch")
        _delivery_sha(self.transcript_sha256, "transcript_sha256")

    def to_finalization_dict(self) -> dict[str, object]:
        return {
            "kind": "delivery_journal_finalization",
            "task_id": self.task_id,
            "schema_version": self.schema_version,
            "protocol": self.protocol,
            "expected_attempt_count": self.expected_attempt_count,
            "last_attempt_ordinal": self.last_attempt_ordinal,
            "transcript_sha256": self.transcript_sha256,
        }


def _record_comment(
    ledger: Ledger,
    task_id: str | None,
    phase: str,
    *,
    outcome: str = "posted",
    reason: str | None = None,
) -> None:
    entry: dict[str, object] = {
        "kind": "github_comment",
        "task_id": task_id,
        "phase": phase,
        "outcome": outcome,
    }
    if reason is not None:
        entry["reason"] = reason
    ledger.append(entry)


def _github_reason(exc: GitHubApiError) -> str:
    return f"GitHub comment: {exc}"


def _ci_run(
    *,
    repo: Path,
    task_id: str | None,
    candidate_count: int,
    surfaced_count: int,
    deferred_reason: str | None,
    spend_usd: float,
    started: float,
    clock: Callable[[], float],
) -> CiRun:
    ledger = Ledger(repo)
    rows = ledger.entries()
    delivery_transcript: CiDeliveryTranscript | None = None
    if task_id is not None:
        if any(
            row.get("kind") == "delivery_journal_finalization" and row.get("task_id") == task_id
            for row in rows
        ):
            raise ValueError("duplicate delivery journal finalization")
        delivery_transcript = build_delivery_transcript(rows, task_id)
        ledger.append_durable(delivery_transcript.to_finalization_dict())
        rows = ledger.entries()
    publication_events, task_delivery_events = reconcile_delivery_rows(
        rows,
        task_id,
        expected_transcript_sha256=(
            None if delivery_transcript is None else delivery_transcript.transcript_sha256
        ),
    )
    return CiRun(
        task_id=task_id,
        candidate_count=candidate_count,
        surfaced_count=surfaced_count,
        deferred_reason=deferred_reason,
        spend_usd=spend_usd,
        elapsed_s=clock() - started,
        publication_events=publication_events,
        task_delivery_events=task_delivery_events,
        delivery_transcript=delivery_transcript,
    )


def _canonical_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


_INLINE_FINDING_MARKER_RE = re.compile(r"<!-- attest:finding-id:([0-9a-f]{10}) -->")
_SUMMARY_FINDING_MARKER_RE = re.compile(
    r"- <!-- attest:finding-id:([0-9a-f]{10}) --> Finding ID: \1; .+"
)


@dataclass
class _DeliveryJournal:
    context: PullRequestContext
    ledger: Ledger
    task_id: str
    deadline_s: float | None
    started: float
    clock: Callable[[], float]
    next_ordinal: int = 0

    def attempt(
        self,
        *,
        channel: str,
        members: tuple[tuple[str, str], ...],
        body: object,
        terminal_status: str | None,
        method: str,
        path: str,
        publish: Callable[[], dict],
    ) -> GitHubApiError | None:
        """Persist exact intent before transport and a typed settlement after it."""

        ordinal = self.next_ordinal
        self.next_ordinal += 1
        member_rows = [
            {"finding_id": finding_id, "placement": placement} for finding_id, placement in members
        ]
        request = {
            "method": method,
            "path": path,
            "repository": self.context.repository,
            "pull_request_number": self.context.number,
            "head_sha": self.context.head_sha,
            "channel": channel,
            "members": member_rows,
            "body": body,
            "terminal_status": terminal_status,
            "deadline_s": self.deadline_s,
            "attempt_ordinal": ordinal,
        }
        body_sha256 = _canonical_sha256(body)
        request_sha256 = _canonical_sha256(request)
        attempt_id = hashlib.sha256(
            f"{self.task_id}:{ordinal}:{request_sha256}".encode()
        ).hexdigest()
        self.ledger.append_durable(
            {
                "kind": "delivery_attempt_intent",
                "task_id": self.task_id,
                "attempt_id": attempt_id,
                "attempt_ordinal": ordinal,
                "repository": self.context.repository,
                "pull_request_number": self.context.number,
                "head_sha": self.context.head_sha,
                "channel": channel,
                "members": member_rows,
                "terminal_status": terminal_status,
                "request": request,
                "body_sha256": body_sha256,
                "request_sha256": request_sha256,
                "deadline_s": self.deadline_s,
            }
        )

        error: GitHubApiError | None = None
        outcome = "ambiguous"
        remote_response_id: str | None = None
        delivered_at_s: float | None = None
        try:
            response = publish()
        except GitHubApiError as exc:
            error = exc
            if exc.definitive_rejection:
                outcome = "failed"
        else:
            response_id = response.get("id")
            if type(response_id) is int and response_id >= 1:
                outcome = "succeeded"
                remote_response_id = str(response_id)
                delivered_at_s = self.clock() - self.started
            else:
                error = GitHubApiError("GitHub API publication response was ambiguous")
        self.ledger.append_durable(
            {
                "kind": "delivery_attempt_settlement",
                "task_id": self.task_id,
                "attempt_id": attempt_id,
                "outcome": outcome,
                "remote_response_id": remote_response_id,
                "delivered_at_s": delivered_at_s,
            }
        )
        return error


@dataclass(frozen=True)
class _PreparedDelivery:
    method: str
    path: str
    body: dict[str, object]
    publish: Callable[[], dict]


def _prepare_status_delivery(
    client: GitHubClient,
    context: PullRequestContext,
    body: str,
) -> _PreparedDelivery:
    prepare = getattr(client, "prepare_issue_comment", None)
    execute = getattr(client, "execute_prepared_write", None)
    if not callable(prepare) or not callable(execute):
        raise GitHubApiError("GitHub client lacks the exact prepared-write protocol")
    request = prepare(
        context.repository,
        context.number,
        STATUS_MARKER,
        body,
    )
    if type(request) is not PreparedGitHubWrite:
        raise GitHubApiError("GitHub client returned an invalid prepared write")
    expected_body = f"{STATUS_MARKER}\n{body}"
    if (
        not _status_write_method_path_is_valid(
            context.repository, context.number, request.method, request.path
        )
        or type(request.payload) is not dict
        or set(request.payload) != {"body"}
        or type(request.payload["body"]) is not str
        or request.payload["body"] != expected_body
    ):
        raise GitHubApiError("GitHub client returned an invalid prepared method/path/payload")
    return _PreparedDelivery(
        method=request.method,
        path=request.path,
        body=request.payload,
        publish=lambda: execute(request),
    )


def build_delivery_transcript(rows: list[dict[str, object]], task_id: str) -> CiDeliveryTranscript:
    """Build the canonical ordered transcript receipt before finalization.

    This receipt is still only a digest of the supplied rows.  Current authority
    comes from persisting it in the write-once measurement outcome and comparing
    later fresh ledger reads against that sealed value.
    """

    _delivery_string(task_id, "task_id")
    intents: dict[str, dict[str, object]] = {}
    settlements: dict[str, dict[str, object]] = {}
    physically_seen_intents: set[str] = set()
    next_physical_ordinal = 0
    for row in rows:
        if row.get("task_id") != task_id:
            continue
        kind = row.get("kind")
        if kind == "delivery_journal_finalization":
            raise ValueError("cannot build a transcript after finalization")
        if kind not in {"delivery_attempt_intent", "delivery_attempt_settlement"}:
            continue
        attempt_id = _delivery_string(row.get("attempt_id"), "attempt_id")
        if kind == "delivery_attempt_intent":
            ordinal = _delivery_nonnegative_int(row.get("attempt_ordinal"), "attempt_ordinal")
            if ordinal != next_physical_ordinal:
                raise ValueError("delivery intent physical ordinals must be contiguous and ordered")
            next_physical_ordinal += 1
            physically_seen_intents.add(attempt_id)
            destination = intents
        else:
            if attempt_id not in physically_seen_intents:
                raise ValueError(
                    "orphan delivery attempt settlement appears before its physical intent"
                )
            destination = settlements
        if attempt_id in destination:
            record_kind = "intent" if destination is intents else "settlement"
            raise ValueError(f"duplicate delivery attempt {record_kind}")
        destination[attempt_id] = row
    if set(settlements) - set(intents):
        raise ValueError("orphan delivery attempt settlement")

    ordinal_attempts: dict[int, str] = {}
    canonical_attempts: list[dict[str, object]] = []
    for attempt_id, intent in intents.items():
        _validate_delivery_intent(intent)
        ordinal = _delivery_nonnegative_int(intent["attempt_ordinal"], "attempt_ordinal")
        prior = ordinal_attempts.setdefault(ordinal, attempt_id)
        if prior != attempt_id:
            raise ValueError("delivery attempt ordinal was reused")
        settlement = settlements.get(attempt_id)
        if settlement is not None:
            _validate_delivery_settlement(settlement, intent)
        canonical_attempts.append(
            {
                "attempt_id": attempt_id,
                "attempt_ordinal": ordinal,
                "intent": {
                    "repository": intent["repository"],
                    "pull_request_number": intent["pull_request_number"],
                    "head_sha": intent["head_sha"],
                    "channel": intent["channel"],
                    "members": intent["members"],
                    "terminal_status": intent["terminal_status"],
                    "request": intent["request"],
                    "body_sha256": intent["body_sha256"],
                    "request_sha256": intent["request_sha256"],
                    "deadline_s": intent["deadline_s"],
                },
                "settlement": (
                    None
                    if settlement is None
                    else {
                        "outcome": settlement["outcome"],
                        "remote_response_id": settlement["remote_response_id"],
                        "delivered_at_s": settlement["delivered_at_s"],
                    }
                ),
            }
        )
    expected_count = len(intents)
    if set(ordinal_attempts) != set(range(expected_count)):
        raise ValueError("delivery attempt ordinals must be contiguous from zero")
    canonical_attempts.sort(
        key=lambda row: _delivery_nonnegative_int(row["attempt_ordinal"], "attempt_ordinal")
    )
    last_ordinal = expected_count - 1 if expected_count else None
    payload = {
        "schema_version": DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
        "protocol": DELIVERY_TRANSCRIPT_PROTOCOL,
        "task_id": task_id,
        "expected_attempt_count": expected_count,
        "last_attempt_ordinal": last_ordinal,
        "attempts": canonical_attempts,
    }
    return CiDeliveryTranscript(
        schema_version=DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
        protocol=DELIVERY_TRANSCRIPT_PROTOCOL,
        task_id=task_id,
        expected_attempt_count=expected_count,
        last_attempt_ordinal=last_ordinal,
        transcript_sha256=_canonical_sha256(payload),
    )


def reconcile_delivery_rows(
    rows: list[dict[str, object]],
    task_id: str | None,
    *,
    expected_transcript_sha256: str | None = None,
) -> tuple[tuple[CiPublicationEvent, ...], tuple[CiTaskDeliveryEvent, ...]]:
    """Strictly join delivery intents and settlements for one task.

    An intent without a settlement is durably ambiguous. A settlement without
    exactly one intent, or any duplicate row, is corrupt rather than evidence.
    """

    if task_id is None:
        return (), ()
    intents: dict[str, dict[str, object]] = {}
    settlements: dict[str, dict[str, object]] = {}
    finalizations: list[dict[str, object]] = []
    physically_seen_intents: set[str] = set()
    next_physical_ordinal = 0
    physically_finalized = False
    for row in rows:
        if row.get("task_id") != task_id:
            continue
        kind = row.get("kind")
        if kind not in {
            "delivery_attempt_intent",
            "delivery_attempt_settlement",
            "delivery_journal_finalization",
        }:
            continue
        if physically_finalized:
            raise ValueError("delivery row appears after its physical finalization")
        if kind == "delivery_journal_finalization":
            physically_finalized = True
            finalizations.append(row)
            continue
        attempt_id = _delivery_string(row.get("attempt_id"), "attempt_id")
        if kind == "delivery_attempt_intent":
            ordinal = _delivery_nonnegative_int(row.get("attempt_ordinal"), "attempt_ordinal")
            if ordinal != next_physical_ordinal:
                raise ValueError("delivery intent physical ordinals must be contiguous and ordered")
            next_physical_ordinal += 1
            physically_seen_intents.add(attempt_id)
        elif attempt_id not in physically_seen_intents:
            raise ValueError(
                "orphan delivery attempt settlement appears before its physical intent"
            )
        destination = intents if kind == "delivery_attempt_intent" else settlements
        if attempt_id in destination:
            record_kind = "intent" if destination is intents else "settlement"
            raise ValueError(f"duplicate delivery attempt {record_kind}")
        destination[attempt_id] = row
    orphan = set(settlements) - set(intents)
    if orphan:
        raise ValueError("orphan delivery attempt settlement")
    if len(finalizations) != 1:
        raise ValueError("delivery journal requires one exact finalization")
    finalization = finalizations[0]
    if set(finalization) != {
        "ts",
        "kind",
        "task_id",
        "schema_version",
        "protocol",
        "expected_attempt_count",
        "last_attempt_ordinal",
        "transcript_sha256",
    }:
        raise ValueError("delivery journal finalization has an invalid field set")
    rebuilt_transcript = build_delivery_transcript(
        [
            row
            for row in rows
            if not (
                row.get("task_id") == task_id and row.get("kind") == "delivery_journal_finalization"
            )
        ],
        task_id,
    )
    finalization_transcript = CiDeliveryTranscript(
        schema_version=_delivery_nonnegative_int(finalization["schema_version"], "schema_version"),
        protocol=_delivery_string(finalization["protocol"], "protocol"),
        task_id=_delivery_string(finalization["task_id"], "task_id"),
        expected_attempt_count=_delivery_nonnegative_int(
            finalization["expected_attempt_count"], "expected_attempt_count"
        ),
        last_attempt_ordinal=(
            None
            if finalization["last_attempt_ordinal"] is None
            else _delivery_nonnegative_int(
                finalization["last_attempt_ordinal"], "last_attempt_ordinal"
            )
        ),
        transcript_sha256=_delivery_sha(finalization["transcript_sha256"], "transcript_sha256"),
    )
    if finalization_transcript != rebuilt_transcript:
        raise ValueError("delivery finalization transcript mismatch")
    if expected_transcript_sha256 is not None:
        expected_digest = _delivery_sha(expected_transcript_sha256, "expected_transcript_sha256")
        if rebuilt_transcript.transcript_sha256 != expected_digest:
            raise ValueError("sealed delivery transcript mismatch")
    expected_attempt_count = finalization_transcript.expected_attempt_count
    if expected_attempt_count != len(intents):
        raise ValueError("delivery journal does not match its expected attempt count")
    ordinal_attempts: dict[int, str] = {}
    reconciled: list[dict[str, object]] = []
    for attempt_id, intent in intents.items():
        _validate_delivery_intent(intent)
        ordinal = _delivery_nonnegative_int(intent["attempt_ordinal"], "attempt_ordinal")
        prior = ordinal_attempts.setdefault(ordinal, attempt_id)
        if prior != attempt_id:
            raise ValueError("delivery attempt ordinal was reused")
        settlement = settlements.get(attempt_id)
        if settlement is None:
            settlement = {
                "attempt_id": attempt_id,
                "outcome": "ambiguous",
                "remote_response_id": None,
                "delivered_at_s": None,
            }
        else:
            _validate_delivery_settlement(settlement, intent)
        reconciled.append({**intent, **settlement})
    if set(ordinal_attempts) != set(range(expected_attempt_count)):
        raise ValueError("delivery attempt ordinals must be contiguous from zero")
    ordered = sorted(
        reconciled,
        key=lambda row: _delivery_nonnegative_int(row["attempt_ordinal"], "attempt_ordinal"),
    )
    return (
        tuple(_publication_from_reconciled(row) for row in ordered if row["members"]),
        tuple(
            _task_delivery_from_reconciled(row)
            for row in ordered
            if row["terminal_status"] is not None
        ),
    )


def _validate_delivery_intent(row: dict[str, object]) -> None:
    fields = {
        "ts",
        "kind",
        "task_id",
        "attempt_id",
        "attempt_ordinal",
        "repository",
        "pull_request_number",
        "head_sha",
        "request",
        "body_sha256",
        "request_sha256",
        "deadline_s",
        "members",
        "channel",
        "terminal_status",
    }
    if set(row) != fields or row["kind"] != "delivery_attempt_intent":
        raise ValueError("delivery attempt intent has an invalid field set")
    ordinal = row["attempt_ordinal"]
    if type(ordinal) is not int or ordinal < 0:
        raise ValueError("attempt_ordinal must be an exact non-negative integer")
    request = row["request"]
    if type(request) is not dict:
        raise ValueError("delivery request must be an exact object")
    request_fields = {
        "method",
        "path",
        "repository",
        "pull_request_number",
        "head_sha",
        "channel",
        "members",
        "body",
        "terminal_status",
        "deadline_s",
        "attempt_ordinal",
    }
    if set(request) != request_fields:
        raise ValueError("delivery request has an invalid field set")
    for field in (
        "repository",
        "pull_request_number",
        "head_sha",
        "deadline_s",
        "attempt_ordinal",
    ):
        if request[field] != row[field]:
            raise ValueError(f"delivery request {field} binding mismatch")
    if row["body_sha256"] != _canonical_sha256(request["body"]):
        raise ValueError("delivery body_sha256 mismatch")
    if row["request_sha256"] != _canonical_sha256(request):
        raise ValueError("delivery request_sha256 mismatch")
    for field in ("channel", "members", "terminal_status"):
        if _canonical_sha256(request[field]) != _canonical_sha256(row[field]):
            raise ValueError(f"delivery request {field} binding mismatch")
    channel = _delivery_string(row["channel"], "channel")
    method = _delivery_string(request["method"], "method")
    path = _delivery_string(request["path"], "path")
    expected_review_path = f"/repos/{row['repository']}/pulls/{row['pull_request_number']}/reviews"
    if channel == "inline_review":
        if method != "POST" or path != expected_review_path:
            raise ValueError("inline review request method/path mismatch")
    elif channel == "status_summary":
        repository = _delivery_string(row["repository"], "repository")
        pull_request_number = _delivery_positive_int(
            row["pull_request_number"], "pull_request_number"
        )
        if not _status_write_method_path_is_valid(repository, pull_request_number, method, path):
            raise ValueError("status summary request method/path mismatch")
    else:
        raise ValueError("unknown delivery channel")
    members = _delivery_members(row["members"], allow_empty=True)
    body_ids = _body_finding_ids(request["body"], channel)
    if sorted(body_ids) != sorted(finding_id for finding_id, _placement in members):
        raise ValueError("publication body does not match declared members")
    terminal_value = row["terminal_status"]
    if channel == "inline_review" and (not members or terminal_value is not None):
        raise ValueError("inline review requires members and cannot carry terminal task status")
    if channel == "status_summary" and terminal_value is None:
        raise ValueError("status summary requires a terminal task status")
    if terminal_value is not None:
        terminal_status = _delivery_string(terminal_value, "terminal_status")
        if terminal_status not in {"completed", "deferred", "failed"}:
            raise ValueError("unknown terminal task delivery status")
    expected_attempt = hashlib.sha256(
        f"{row['task_id']}:{ordinal}:{row['request_sha256']}".encode()
    ).hexdigest()
    if row["attempt_id"] != expected_attempt:
        raise ValueError("delivery attempt_id mismatch")


def _status_write_method_path_is_valid(
    repository: str, pull_request_number: int, method: object, path: object
) -> bool:
    if type(method) is not str or type(path) is not str:
        return False
    post_path = f"/repos/{repository}/issues/{pull_request_number}/comments"
    patch_prefix = f"/repos/{repository}/issues/comments/"
    patch_suffix = path[len(patch_prefix) :] if path.startswith(patch_prefix) else ""
    canonical_patch = (
        bool(patch_suffix)
        and patch_suffix.isascii()
        and patch_suffix.isdecimal()
        and str(int(patch_suffix)) == patch_suffix
        and int(patch_suffix) >= 1
    )
    return (method == "POST" and path == post_path) or (method == "PATCH" and canonical_patch)


def _validate_delivery_settlement(row: dict[str, object], intent: dict[str, object]) -> None:
    if set(row) != {
        "ts",
        "kind",
        "task_id",
        "attempt_id",
        "outcome",
        "remote_response_id",
        "delivered_at_s",
    }:
        raise ValueError("delivery attempt settlement has an invalid field set")
    if row["kind"] != "delivery_attempt_settlement":
        raise ValueError("delivery attempt settlement kind is invalid")
    if row["attempt_id"] != intent["attempt_id"]:
        raise ValueError("delivery attempt settlement binding mismatch")
    outcome = row["outcome"]
    if outcome not in {"succeeded", "failed", "ambiguous"}:
        raise ValueError("unknown delivery attempt settlement outcome")
    response_id = row["remote_response_id"]
    delivered_at_s = row["delivered_at_s"]
    if outcome == "succeeded":
        _delivery_response_id(response_id)
        _delivery_number(delivered_at_s, "delivered_at_s")
    elif response_id is not None or delivered_at_s is not None:
        raise ValueError("non-success delivery attempt has delivery identity")


def _publication_from_reconciled(row: dict[str, object]) -> CiPublicationEvent:
    attempt_id = _delivery_string(row["attempt_id"], "attempt_id")
    return CiPublicationEvent(
        event_id=hashlib.sha256(f"{attempt_id}:publication".encode()).hexdigest(),
        attempt_id=attempt_id,
        attempt_ordinal=_delivery_nonnegative_int(row["attempt_ordinal"], "attempt_ordinal"),
        repository=_delivery_string(row["repository"], "repository"),
        pull_request_number=_delivery_positive_int(
            row["pull_request_number"], "pull_request_number"
        ),
        head_sha=_delivery_string(row["head_sha"], "head_sha"),
        channel=_delivery_string(row["channel"], "channel"),
        members=_delivery_members(row["members"]),
        body_sha256=_delivery_sha(row["body_sha256"], "body_sha256"),
        request_sha256=_delivery_sha(row["request_sha256"], "request_sha256"),
        outcome=_delivery_string(row["outcome"], "outcome"),
        remote_response_id=_delivery_optional_response_id(row["remote_response_id"]),
        delivered_at_s=_delivery_optional_number(row["delivered_at_s"]),
        deadline_s=_delivery_optional_number(row["deadline_s"]),
    )


def _task_delivery_from_reconciled(row: dict[str, object]) -> CiTaskDeliveryEvent:
    attempt_id = _delivery_string(row["attempt_id"], "attempt_id")
    return CiTaskDeliveryEvent(
        event_id=hashlib.sha256(f"{attempt_id}:task_delivery".encode()).hexdigest(),
        attempt_id=attempt_id,
        attempt_ordinal=_delivery_nonnegative_int(row["attempt_ordinal"], "attempt_ordinal"),
        repository=_delivery_string(row["repository"], "repository"),
        pull_request_number=_delivery_positive_int(
            row["pull_request_number"], "pull_request_number"
        ),
        head_sha=_delivery_string(row["head_sha"], "head_sha"),
        channel=_delivery_string(row["channel"], "channel"),
        members=_delivery_members(row["members"], allow_empty=True),
        terminal_status=_delivery_string(row["terminal_status"], "terminal_status"),
        body_sha256=_delivery_sha(row["body_sha256"], "body_sha256"),
        request_sha256=_delivery_sha(row["request_sha256"], "request_sha256"),
        outcome=_delivery_string(row["outcome"], "outcome"),
        remote_response_id=_delivery_optional_response_id(row["remote_response_id"]),
        delivered_at_s=_delivery_optional_number(row["delivered_at_s"]),
        deadline_s=_delivery_optional_number(row["deadline_s"]),
    )


def _delivery_members(value: object, *, allow_empty: bool = False) -> tuple[tuple[str, str], ...]:
    if type(value) is not list or (not value and not allow_empty):
        requirement = "an exact list" if allow_empty else "a non-empty exact list"
        raise ValueError(f"publication members must be {requirement}")
    members: list[tuple[str, str]] = []
    for member in value:
        if type(member) is not dict or set(member) != {"finding_id", "placement"}:
            raise ValueError("publication member has an invalid field set")
        members.append(
            (
                _delivery_string(member["finding_id"], "finding_id"),
                _delivery_string(member["placement"], "placement"),
            )
        )
    if len({finding_id for finding_id, _placement in members}) != len(members):
        raise ValueError("duplicate publication member finding_id")
    return tuple(members)


def _body_finding_ids(value: object, channel: str) -> tuple[str, ...]:
    if type(value) is not dict:
        raise ValueError("publication body must be an exact object")
    if channel == "inline_review":
        comments = value.get("comments")
        if type(comments) is not list:
            raise ValueError("inline review body has no exact comments list")
        finding_ids: list[str] = []
        for comment in comments:
            if type(comment) is not dict or type(comment.get("body")) is not str:
                raise ValueError("inline review comment has no exact body")
            lines = comment["body"].splitlines()
            match = _INLINE_FINDING_MARKER_RE.fullmatch(lines[0]) if lines else None
            if match is None:
                raise ValueError("inline review comment has no finding marker")
            finding_ids.append(match.group(1))
        return tuple(finding_ids)
    if channel == "status_summary":
        body = value.get("body")
        if type(body) is not str:
            raise ValueError("status summary has no exact body")
        return tuple(
            match.group(1)
            for line in body.splitlines()
            if (match := _SUMMARY_FINDING_MARKER_RE.fullmatch(line)) is not None
        )
    raise ValueError("unknown publication body channel")


def _delivery_string(value: object, field: str) -> str:
    if type(value) is not str or not value:
        raise ValueError(f"{field} must be a non-empty exact string")
    return value


def _delivery_optional_string(value: object) -> str | None:
    return None if value is None else _delivery_string(value, "remote_response_id")


def _delivery_response_id(value: object) -> str:
    text = _delivery_string(value, "remote_response_id")
    if not text.isascii() or not text.isdecimal() or str(int(text)) != text or int(text) < 1:
        raise ValueError("remote_response_id must be a canonical positive integer")
    return text


def _delivery_optional_response_id(value: object) -> str | None:
    return None if value is None else _delivery_response_id(value)


def _delivery_number(value: object, field: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{field} must be a finite non-negative exact number")
    number = float(cast(int | float, value))
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{field} must be a finite non-negative exact number")
    return number


def _delivery_optional_number(value: object) -> float | None:
    return None if value is None else _delivery_number(value, "delivery number")


def _delivery_positive_int(value: object, field: str) -> int:
    if type(value) is not int or value < 1:
        raise ValueError(f"{field} must be an exact positive integer")
    return value


def _delivery_nonnegative_int(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{field} must be an exact non-negative integer")
    return value


def _delivery_sha(value: object, field: str) -> str:
    text = _delivery_string(value, field)
    if len(text) != 64 or any(char not in "0123456789abcdef" for char in text):
        raise ValueError(f"{field} must be a lowercase SHA-256")
    return text


def _post_deferred(
    *,
    context: PullRequestContext,
    client: GitHubClient,
    ledger: Ledger,
    task_id: str | None,
    journal: _DeliveryJournal,
    reason: str,
    surfaced: list[CertifiedFinding] | None = None,
    spend_usd: float = 0.0,
    elapsed_s: float = 0.0,
    inline: list[CertifiedFinding] | None = None,
    overflow: list[CertifiedFinding] | None = None,
) -> str:
    body = render_deferred(f"DEFER: {reason}")
    if surfaced:
        body = render_complete(surfaced, spend_usd, elapsed_s).replace("Review complete.", body, 1)
    body = _with_run_status(ledger, task_id, body)
    members = tuple(
        (_candidate_id(finding), placement)
        for placement, findings in (
            ("inline", inline or []),
            ("overflow", overflow or []),
        )
        for finding in findings
    )
    try:
        prepared = _prepare_status_delivery(client, context, body)
    except GitHubApiError as exc:
        github_reason = _github_reason(exc)
        _record_comment(ledger, task_id, "defer", outcome="failed", reason=github_reason)
        return f"{reason}; {github_reason}"
    error = journal.attempt(
        channel="status_summary",
        members=members,
        body=prepared.body,
        terminal_status="deferred",
        method=prepared.method,
        path=prepared.path,
        publish=prepared.publish,
    )
    if error is not None:
        github_reason = _github_reason(error)
        _record_comment(ledger, task_id, "defer", outcome="failed", reason=github_reason)
        return f"{reason}; {github_reason}"
    _record_comment(ledger, task_id, "defer")
    return reason


def _candidate_id(finding: CertifiedFinding) -> str:
    return finding.accepted_receipt.receipt.candidate_id


def _with_run_status(ledger: Ledger, task_id: str | None, body: str) -> str:
    """Owner item 6: every final status comment, silent or not, carries a
    collapsed run-status section (counts and reproduction failure categories,
    never an uncertified candidate's content or location)."""
    if task_id is None:
        return body
    try:
        status = status_from_rows(ledger.entries(), task_id)
    except (OSError, RuntimeError, ValueError):
        return body
    return f"{body}\n\n{status.render_collapsed()}"


def _workspace_head(repo: Path) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    )
    return proc.stdout.strip() if proc.returncode == 0 else None


HEAD_DRIFT_REASON = "workspace HEAD drifted from the reviewed head before publication"
MERGE_BASE_REASON = "merge-base unavailable: fetch the base branch history (fetch-depth 0)"


def run_ci(
    repo: Path,
    context: PullRequestContext,
    client: GitHubClient,
    config: ReviewConfig | None,
    provider: Provider,
    *,
    verification_timeout_s: float = 600.0,
    limits: ExecutorLimits | None = None,
    clock: Callable[[], float] = time.monotonic,
    publication_deadline_s: float | None = None,
    config_overrides: Mapping[str, object] | None = None,
    merge_base_sha: str | None = None,
) -> CiRun:
    """Run a review whose candidate details remain private until verified.

    ``config`` is the caller's protected policy layer; pass ``None`` to load the
    base-owned ``.attest.toml`` at the resolved merge-base with
    ``config_overrides`` (protected Action inputs) applied on top. The head
    checkout's policy file is never read.

    ``merge_base_sha`` lets a trusted harness that constructs its own task
    (the benchmark's reverse historical pairs, whose head is an ancestor of
    the base) declare the counterfactual it owns. The Action/CLI path never
    passes it: a pull request's counterfactual is always resolved.
    """
    started = clock()
    ledger = Ledger(repo)
    task_id = make_task_id(f"{context.repository}:{context.number}:{context.head_sha}:{started}")
    journal = _DeliveryJournal(
        context=context,
        ledger=ledger,
        task_id=task_id,
        deadline_s=publication_deadline_s,
        started=started,
        clock=clock,
    )
    if context.is_fork:
        reason = "fork pull requests are skipped before model or head-code execution"
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            journal=journal,
            reason=reason,
        )
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=0.0,
            started=started,
            clock=clock,
        )

    try:
        client.upsert_issue_comment(
            context.repository,
            context.number,
            STATUS_MARKER,
            render_running(),
        )
    except GitHubApiError as exc:
        reason = _github_reason(exc)
        _record_comment(ledger, task_id, "running", outcome="failed", reason=reason)
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=0.0,
            started=started,
            clock=clock,
        )

    _record_comment(ledger, task_id, "running")

    # INV-TASK-001 / INV-POLICY-001: the counterfactual is the merge-base and the
    # policy is whatever the destination owns there, never the head's file.
    merge_base = (
        merge_base_sha
        if merge_base_sha is not None
        else resolve_merge_base(repo, context.base_sha, context.head_sha)
    )
    resolved = None
    if merge_base is not None:
        try:
            resolved = resolve_review_policy(repo, merge_base, config, config_overrides)
        except (ValueError, TypeError) as exc:
            policy_reason = f"base policy invalid: {str(exc)[:160]}"
    if merge_base is None or resolved is None:
        reason = MERGE_BASE_REASON if merge_base is None else policy_reason
        ledger.append({"kind": "defer", "task_id": task_id, "reason": reason})
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            journal=journal,
            reason=reason,
        )
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=0.0,
            started=started,
            clock=clock,
        )
    config = resolved.config
    ledger.append(
        {
            "kind": "certification_task",
            "task_id": task_id,
            "repository": context.repository,
            "event_base_sha": context.base_sha,
            "merge_base_sha": merge_base,
            "head_sha": context.head_sha,
            "policy_source": resolved.source,
            "policy_source_sha": merge_base,
            "policy_source_digest": resolved.source_digest,
            "review_policy_digest": resolved.policy_digest,
        }
    )
    try:
        review = run_review(
            repo,
            merge_base,
            config,
            provider,
            clock=clock,
            task_id=task_id,
        )
    except ReviewSetupError as exc:
        reason = f"review setup failed: {type(exc).__name__}"
        ledger.append({"kind": "defer", "task_id": task_id, "reason": reason})
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            journal=journal,
            reason=reason,
        )
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=0.0,
            started=started,
            clock=clock,
        )
    except ReviewExecutionError as exc:
        reason = str(exc)
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=exc.task_id,
            journal=journal,
            reason=reason,
        )
        return _ci_run(
            repo=repo,
            task_id=exc.task_id,
            candidate_count=exc.candidate_count,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=exc.budget.spent_usd,
            started=started,
            clock=clock,
        )
    try:
        client.upsert_issue_comment(
            context.repository,
            context.number,
            STATUS_MARKER,
            render_running(len(review.results)),
        )
    except GitHubApiError as exc:
        reason = _github_reason(exc)
        _record_comment(
            ledger,
            task_id,
            "candidate_count",
            outcome="failed",
            reason=reason,
        )
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )
    _record_comment(ledger, task_id, "candidate_count")

    if review.deferred_reason is not None:
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            journal=journal,
            reason=review.deferred_reason,
        )
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )

    stage = run_verification_stage(
        repo,
        task_id=task_id,
        repository_id=context.repository,
        base_sha=merge_base,
        head_sha=context.head_sha,
        review=review,
        review_policy_digest=resolved.policy_digest,
        config=config,
        provider=provider,
        limits=limits,
        verification_timeout_s=verification_timeout_s,
        clock=clock,
    )
    results_by_id = stage.results_by_id
    verification_defers = stage.verification_defers
    updated_results = list(results_by_id.values())
    selection_published = stage.published
    finding_evidence = stage.evidence
    inline_results = list(selection_published)
    overflow_results: list[CertifiedFinding] = []  # the cap is author-visible, not layout
    surfaced = [*inline_results, *overflow_results]
    published_ids = {_candidate_id(finding) for finding in inline_results}
    ledger.record_ci_final(
        task_id=task_id,
        decisions=[
            {
                "finding_id": result.finding.finding_id,
                # `surface` is now a receipt decision; the S/T/V wealth is kept
                # beside it for analysis only
                "action": (
                    "surface"
                    if result.finding.finding_id in published_ids
                    else "discard"
                    if result.decision == 0
                    else "drawer"
                ),
                "wealth_final": round(result.wealth, 4),
                "placement": (
                    "inline"
                    if result.finding.finding_id in published_ids
                    else "discard"
                    if result.decision == 0
                    else "drawer"
                ),
            }
            for result in updated_results
        ],
        spend_usd=review.budget.spent_usd,
        elapsed_s=clock() - started,
    )
    if surfaced and _workspace_head(repo) != context.head_sha:
        # revalidate the task immediately before the first author-visible write
        ledger.append({"kind": "defer", "task_id": task_id, "reason": HEAD_DRIFT_REASON})
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            journal=journal,
            reason=HEAD_DRIFT_REASON,
        )
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )
    if surfaced:
        review_comments = inline_comments(inline_results, finding_evidence)
        review_error = journal.attempt(
            channel="inline_review",
            members=tuple((_candidate_id(finding), "inline") for finding in inline_results),
            body={
                "commit_id": context.head_sha,
                "body": "Attest review.",
                "event": "COMMENT",
                "comments": review_comments,
            },
            terminal_status=None,
            method="POST",
            path=f"/repos/{context.repository}/pulls/{context.number}/reviews",
            publish=lambda: client.create_review(
                context.repository,
                context.number,
                context.head_sha,
                review_comments,
            ),
        )
        if review_error is not None:
            reason = _github_reason(review_error)
            _record_comment(ledger, task_id, "review", outcome="failed", reason=reason)
            reason = _post_deferred(
                context=context,
                client=client,
                ledger=ledger,
                task_id=task_id,
                journal=journal,
                reason=reason,
                surfaced=surfaced,
                spend_usd=review.budget.spent_usd,
                elapsed_s=clock() - started,
                inline=inline_results,
                overflow=overflow_results,
            )
            return _ci_run(
                repo=repo,
                task_id=task_id,
                candidate_count=len(review.results),
                surfaced_count=len(surfaced),
                deferred_reason=reason,
                spend_usd=review.budget.spent_usd,
                started=started,
                clock=clock,
            )
        _record_comment(ledger, task_id, "review")

    if verification_defers:
        reason = f"verification deferred: {verification_defers[0]}"
        if len(verification_defers) > 1:
            reason += f" ({len(verification_defers)} candidates)"
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            journal=journal,
            reason=reason,
            surfaced=surfaced,
            spend_usd=review.budget.spent_usd,
            elapsed_s=clock() - started,
            inline=inline_results,
            overflow=overflow_results,
        )
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=len(surfaced),
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )

    elapsed_s = clock() - started
    complete_body = _with_run_status(
        ledger,
        task_id,
        render_complete(surfaced, review.budget.spent_usd, elapsed_s, finding_evidence),
    )
    try:
        prepared = _prepare_status_delivery(client, context, complete_body)
    except GitHubApiError as exc:
        reason = _github_reason(exc)
        _record_comment(ledger, task_id, "complete", outcome="failed", reason=reason)
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=len(surfaced),
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )
    complete_error = journal.attempt(
        channel="status_summary",
        members=tuple(
            (_candidate_id(finding), placement)
            for placement, findings in (
                ("inline", inline_results),
                ("overflow", overflow_results),
            )
            for finding in findings
        ),
        body=prepared.body,
        terminal_status="completed",
        method=prepared.method,
        path=prepared.path,
        publish=prepared.publish,
    )
    if complete_error is not None:
        reason = _github_reason(complete_error)
        _record_comment(ledger, task_id, "complete", outcome="failed", reason=reason)
        return _ci_run(
            repo=repo,
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=len(surfaced),
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )
    _record_comment(ledger, task_id, "complete")
    return _ci_run(
        repo=repo,
        task_id=task_id,
        candidate_count=len(review.results),
        surfaced_count=len(surfaced),
        deferred_reason=None,
        spend_usd=review.budget.spent_usd,
        started=started,
        clock=clock,
    )
