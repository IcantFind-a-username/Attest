"""Versioned author-visible benchmark outcome and denominator ownership.

This module deliberately separates task completion from finding publication and
accuracy.  Current measurement records are strict, versioned documents.  The
legacy adapter is explicit and can preserve historical integrity only; it never
confers current scoring semantics.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

CURRENT_MEASUREMENT_SCHEMA_VERSION = 2
CURRENT_MEASUREMENT_SEMANTICS = "author_visible_v2"
LEGACY_MEASUREMENT_SEMANTICS = "legacy_v1_scoring"
LEGACY_V1_METRICS_WITHHELD = "legacy_v1_scoring_metrics_withheld"
ARM_ATTEST_PRODUCT = "attest_product"
DELIVERY_TRANSCRIPT_SCHEMA_VERSION = 1
DELIVERY_TRANSCRIPT_PROTOCOL = "attest.delivery-transcript.v1"
EMPTY_DELIVERY_TRANSCRIPT_SHA256 = hashlib.sha256(
    json.dumps(
        {
            "schema_version": DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
            "protocol": DELIVERY_TRANSCRIPT_PROTOCOL,
            "task_id": None,
            "expected_attempt_count": 0,
            "last_attempt_ordinal": None,
            "attempts": [],
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
).hexdigest()


class TaskStatus(StrEnum):
    """Task-level completion, independent from individual finding outcomes."""

    COMPLETED = "completed"
    PARTIALLY_DEFERRED = "partially_deferred"
    FULLY_DEFERRED = "fully_deferred"
    FAILED = "failed"


class FindingStatus(StrEnum):
    """Lifecycle status of one candidate/finding."""

    PUBLISHED = "published"
    CERTIFIED_SUPPRESSED = "certified_suppressed"
    UNRESOLVED = "unresolved"
    REJECTED = "rejected"


class AccuracyStatus(StrEnum):
    """Adjudication status, which is independent from publication."""

    CORRECT = "correct"
    WRONG = "wrong"
    UNADJUDICATED = "unadjudicated"
    NOT_APPLICABLE = "not_applicable"


class StopKind(StrEnum):
    """Why execution stopped after retaining every outcome already resolved."""

    NONE = "none"
    CANDIDATE_DEFER = "candidate_defer"
    TASK_DEFER = "task_defer"
    FAILURE = "failure"


class FindingAuthority(StrEnum):
    """Whether a finding belongs to automated product measurement."""

    AUTOMATED = "automated"
    SELF_REPORTED = "self_reported"


class TruthStatus(StrEnum):
    """Adjudicated truth class of one semantic pull-request unit."""

    POSITIVE = "positive"
    NULL = "null"
    UNADJUDICATED = "unadjudicated"


class DeliveryStatus(StrEnum):
    """Semantic publication delivery, excluding nondeterministic elapsed time."""

    PUBLISHED_ON_TIME = "published_on_time"
    PUBLISHED_LATE = "published_late"
    NO_PUBLICATION = "no_publication"


class PublicationPlacement(StrEnum):
    """Canonical author-visible placement of a finding."""

    INLINE = "inline"
    OVERFLOW = "overflow"


class PublicationChannel(StrEnum):
    """Actual API channel on which one finding was attempted."""

    INLINE_REVIEW = "inline_review"
    STATUS_SUMMARY = "status_summary"


class PublicationOutcome(StrEnum):
    """Observed API outcome of one finding-level publication attempt."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    AMBIGUOUS = "ambiguous"


class TaskDeliveryTerminalStatus(StrEnum):
    """Terminal task message carried by a delivery attempt."""

    COMPLETED = "completed"
    DEFERRED = "deferred"
    FAILED = "failed"


@dataclass(frozen=True)
class DeliveryTranscriptReceipt:
    """Sealed binding to the fresh ordered delivery-attempt transcript."""

    schema_version: int
    protocol: str
    task_id: str | None
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
        if self.task_id is not None:
            _require_nonempty_string(self.task_id, "delivery transcript task_id")
        if (
            type(self.expected_attempt_count) is not int
            or self.expected_attempt_count < 0
        ):
            raise ValueError(
                "expected_attempt_count must be an exact non-negative integer"
            )
        expected_last = (
            self.expected_attempt_count - 1
            if self.expected_attempt_count
            else None
        )
        if self.last_attempt_ordinal != expected_last:
            raise ValueError("delivery transcript last ordinal mismatch")
        _require_sha256(self.transcript_sha256, "delivery transcript_sha256")
        if self.task_id is None and (
            self.expected_attempt_count != 0
            or self.transcript_sha256 != EMPTY_DELIVERY_TRANSCRIPT_SHA256
        ):
            raise ValueError("taskless delivery transcript must be the exact empty receipt")

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protocol": self.protocol,
            "task_id": self.task_id,
            "expected_attempt_count": self.expected_attempt_count,
            "last_attempt_ordinal": self.last_attempt_ordinal,
            "transcript_sha256": self.transcript_sha256,
        }


def empty_delivery_transcript_receipt() -> DeliveryTranscriptReceipt:
    """Return the exact no-task/no-attempt transcript sentinel."""

    return DeliveryTranscriptReceipt(
        schema_version=DELIVERY_TRANSCRIPT_SCHEMA_VERSION,
        protocol=DELIVERY_TRANSCRIPT_PROTOCOL,
        task_id=None,
        expected_attempt_count=0,
        last_attempt_ordinal=None,
        transcript_sha256=EMPTY_DELIVERY_TRANSCRIPT_SHA256,
    )


@dataclass(frozen=True)
class PublicationMember:
    """One finding and its canonical placement within a batched API call."""

    finding_id: str
    placement: PublicationPlacement

    def __post_init__(self) -> None:
        _require_nonempty_string(self.finding_id, "finding_id")
        if type(self.placement) is not PublicationPlacement:
            raise ValueError("placement must be an exact PublicationPlacement")

    def to_json_dict(self) -> dict[str, object]:
        return {"finding_id": self.finding_id, "placement": self.placement.value}


@dataclass(frozen=True)
class PublicationEvent:
    """One actual batched API attempt, including exact finding membership."""

    event_id: str
    attempt_id: str
    attempt_ordinal: int
    repository: str
    pull_request_number: int
    head_sha: str
    members: tuple[PublicationMember, ...]
    channel: PublicationChannel
    outcome: PublicationOutcome
    body_sha256: str
    request_sha256: str
    remote_response_id: str | None
    delivered_at_s: float | None
    deadline_s: float

    def __post_init__(self) -> None:
        _require_nonempty_string(self.event_id, "event_id")
        _require_nonempty_string(self.attempt_id, "attempt_id")
        if type(self.attempt_ordinal) is not int or self.attempt_ordinal < 0:
            raise ValueError("attempt_ordinal must be an exact non-negative integer")
        _require_nonempty_string(self.repository, "repository")
        if type(self.pull_request_number) is not int or self.pull_request_number < 1:
            raise ValueError("pull_request_number must be an exact positive integer")
        _require_nonempty_string(self.head_sha, "head_sha")
        if type(self.members) is not tuple or not self.members or any(
            type(member) is not PublicationMember for member in self.members
        ):
            raise ValueError("publication members must be a non-empty exact tuple")
        member_ids = tuple(member.finding_id for member in self.members)
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("duplicate publication member finding_id")
        if type(self.channel) is not PublicationChannel:
            raise ValueError("channel must be an exact PublicationChannel")
        if type(self.outcome) is not PublicationOutcome:
            raise ValueError("outcome must be an exact PublicationOutcome")
        _require_sha256(self.body_sha256, "body_sha256")
        _require_sha256(self.request_sha256, "request_sha256")
        object.__setattr__(
            self,
            "deadline_s",
            _exact_number(self.deadline_s, "deadline_s", minimum=0.0),
        )
        if self.outcome is PublicationOutcome.SUCCEEDED:
            if self.remote_response_id is None:
                raise ValueError("successful publication requires remote_response_id")
            _require_response_id(self.remote_response_id)
            if self.delivered_at_s is None:
                raise ValueError("successful publication requires delivered_at_s")
            object.__setattr__(
                self,
                "delivered_at_s",
                _exact_number(self.delivered_at_s, "delivered_at_s", minimum=0.0),
            )
        elif self.delivered_at_s is not None or self.remote_response_id is not None:
            raise ValueError(
                "failed or ambiguous publication has no response or delivery identity"
            )
        if self.channel is PublicationChannel.INLINE_REVIEW and any(
            member.placement is PublicationPlacement.OVERFLOW for member in self.members
        ):
            raise ValueError("overflow publication requires the status-summary channel")

    @property
    def succeeded(self) -> bool:
        return self.outcome is PublicationOutcome.SUCCEEDED

    @property
    def delivered_on_time(self) -> bool | None:
        if self.delivered_at_s is None:
            return None
        return self.delivered_at_s <= self.deadline_s

    def to_json_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "attempt_id": self.attempt_id,
            "attempt_ordinal": self.attempt_ordinal,
            "repository": self.repository,
            "pull_request_number": self.pull_request_number,
            "head_sha": self.head_sha,
            "members": [member.to_json_dict() for member in self.members],
            "channel": self.channel.value,
            "outcome": self.outcome.value,
            "body_sha256": self.body_sha256,
            "request_sha256": self.request_sha256,
            "remote_response_id": self.remote_response_id,
            "delivered_at_s": self.delivered_at_s,
            "deadline_s": self.deadline_s,
        }


@dataclass(frozen=True)
class TaskDeliveryEvent:
    """One terminal task-status API attempt, independent of finding speech."""

    event_id: str
    attempt_id: str
    attempt_ordinal: int
    repository: str
    pull_request_number: int
    head_sha: str
    channel: PublicationChannel
    members: tuple[PublicationMember, ...]
    terminal_status: TaskDeliveryTerminalStatus
    outcome: PublicationOutcome
    body_sha256: str
    request_sha256: str
    remote_response_id: str | None
    delivered_at_s: float | None
    deadline_s: float

    def __post_init__(self) -> None:
        _require_nonempty_string(self.event_id, "event_id")
        _require_nonempty_string(self.attempt_id, "attempt_id")
        if type(self.attempt_ordinal) is not int or self.attempt_ordinal < 0:
            raise ValueError("attempt_ordinal must be an exact non-negative integer")
        _require_nonempty_string(self.repository, "repository")
        if type(self.pull_request_number) is not int or self.pull_request_number < 1:
            raise ValueError("pull_request_number must be an exact positive integer")
        _require_nonempty_string(self.head_sha, "head_sha")
        if self.channel is not PublicationChannel.STATUS_SUMMARY:
            raise ValueError("task delivery requires the status-summary channel")
        if type(self.members) is not tuple or any(
            type(member) is not PublicationMember for member in self.members
        ):
            raise ValueError("task delivery members must be an exact tuple")
        member_ids = tuple(member.finding_id for member in self.members)
        if len(set(member_ids)) != len(member_ids):
            raise ValueError("duplicate task delivery member finding_id")
        if type(self.terminal_status) is not TaskDeliveryTerminalStatus:
            raise ValueError("terminal_status must be an exact TaskDeliveryTerminalStatus")
        if type(self.outcome) is not PublicationOutcome:
            raise ValueError("outcome must be an exact PublicationOutcome")
        _require_sha256(self.body_sha256, "body_sha256")
        _require_sha256(self.request_sha256, "request_sha256")
        object.__setattr__(
            self,
            "deadline_s",
            _exact_number(self.deadline_s, "deadline_s", minimum=0.0),
        )
        if self.outcome is PublicationOutcome.SUCCEEDED:
            if self.remote_response_id is None:
                raise ValueError("successful task delivery requires remote_response_id")
            _require_response_id(self.remote_response_id)
            if self.delivered_at_s is None:
                raise ValueError("successful task delivery requires delivered_at_s")
            object.__setattr__(
                self,
                "delivered_at_s",
                _exact_number(self.delivered_at_s, "delivered_at_s", minimum=0.0),
            )
        elif self.remote_response_id is not None or self.delivered_at_s is not None:
            raise ValueError("non-success task delivery has no delivery identity")

    @property
    def succeeded(self) -> bool:
        return self.outcome is PublicationOutcome.SUCCEEDED

    @property
    def delivered_on_time(self) -> bool | None:
        if self.delivered_at_s is None:
            return None
        return self.delivered_at_s <= self.deadline_s

    def to_json_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "attempt_id": self.attempt_id,
            "attempt_ordinal": self.attempt_ordinal,
            "repository": self.repository,
            "pull_request_number": self.pull_request_number,
            "head_sha": self.head_sha,
            "channel": self.channel.value,
            "members": [member.to_json_dict() for member in self.members],
            "terminal_status": self.terminal_status.value,
            "outcome": self.outcome.value,
            "body_sha256": self.body_sha256,
            "request_sha256": self.request_sha256,
            "remote_response_id": self.remote_response_id,
            "delivered_at_s": self.delivered_at_s,
            "deadline_s": self.deadline_s,
        }


@dataclass(frozen=True)
class FindingOutcome:
    """One immutable finding lifecycle and adjudication outcome."""

    finding_id: str
    finding_status: FindingStatus
    accuracy_status: AccuracyStatus
    defect_id: str | None
    publication_event_ids: tuple[str, ...]
    authority: FindingAuthority

    def __post_init__(self) -> None:
        _require_nonempty_string(self.finding_id, "finding_id")
        if type(self.finding_status) is not FindingStatus:
            raise ValueError("finding_status must be an exact FindingStatus")
        if type(self.accuracy_status) is not AccuracyStatus:
            raise ValueError("accuracy_status must be an exact AccuracyStatus")
        if type(self.authority) is not FindingAuthority:
            raise ValueError("authority must be an exact FindingAuthority")
        if self.defect_id is not None:
            _require_nonempty_string(self.defect_id, "defect_id")
        if type(self.publication_event_ids) is not tuple:
            raise ValueError("publication_event_ids must be an exact tuple")
        for event_id in self.publication_event_ids:
            _require_nonempty_string(event_id, "publication_event_id")
        if len(set(self.publication_event_ids)) != len(self.publication_event_ids):
            raise ValueError("duplicate publication_event_id")

        if self.finding_status is FindingStatus.PUBLISHED:
            if not self.publication_event_ids:
                raise ValueError("published finding requires publication_event_ids")
            if self.accuracy_status is AccuracyStatus.NOT_APPLICABLE:
                raise ValueError("published finding accuracy cannot be not_applicable")
        else:
            if self.publication_event_ids:
                raise ValueError("non-published finding cannot have publication_event_ids")
            if self.accuracy_status in {AccuracyStatus.CORRECT, AccuracyStatus.WRONG}:
                raise ValueError("non-published finding cannot enter accuracy counts")
        if self.accuracy_status is AccuracyStatus.CORRECT and self.defect_id is None:
            raise ValueError("correct finding requires defect_id")

    @property
    def author_visible(self) -> bool:
        """Publication is the sole source of author visibility."""

        return self.finding_status is FindingStatus.PUBLISHED

    def to_json_dict(self) -> dict[str, object]:
        """Return the exact current nested-record representation."""

        return {
            "finding_id": self.finding_id,
            "finding_status": self.finding_status.value,
            "accuracy_status": self.accuracy_status.value,
            "defect_id": self.defect_id,
            "publication_event_ids": list(self.publication_event_ids),
            "authority": self.authority.value,
        }


@dataclass(frozen=True)
class MeasurementRecord:
    """Current semantic measurement for one case, arm, and operational repeat."""

    schema_version: int
    scoring_semantics: str
    case_id: str
    arm: str
    repeat: int
    stop_kind: StopKind
    task_status: TaskStatus
    findings: tuple[FindingOutcome, ...]
    eligible_defect_ids: tuple[str, ...]
    pull_request_number: int
    truth_status: TruthStatus
    delivery_status: DeliveryStatus
    candidate_count: int
    published_count: int
    unresolved_count: int
    publication_events: tuple[PublicationEvent, ...]
    task_delivery_events: tuple[TaskDeliveryEvent, ...]
    delivery_transcript: DeliveryTranscriptReceipt
    metrics_withheld_reason: str | None
    delivery_withheld_reason: str | None
    task_delivery_withheld_reason: str | None

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or (
            self.schema_version != CURRENT_MEASUREMENT_SCHEMA_VERSION
        ):
            raise ValueError("unsupported measurement schema_version")
        if type(self.scoring_semantics) is not str or (
            self.scoring_semantics != CURRENT_MEASUREMENT_SEMANTICS
        ):
            raise ValueError("unsupported measurement scoring_semantics")
        _require_nonempty_string(self.case_id, "case_id")
        _require_nonempty_string(self.arm, "arm")
        if type(self.repeat) is not int or self.repeat < 0:
            raise ValueError("repeat must be an exact non-negative integer")
        if type(self.stop_kind) is not StopKind:
            raise ValueError("stop_kind must be an exact StopKind")
        if type(self.task_status) is not TaskStatus:
            raise ValueError("task_status must be an exact TaskStatus")
        if type(self.findings) is not tuple or any(
            type(finding) is not FindingOutcome for finding in self.findings
        ):
            raise ValueError("findings must be an exact tuple of FindingOutcome")
        if type(self.eligible_defect_ids) is not tuple:
            raise ValueError("eligible_defect_ids must be an exact tuple")
        for defect_id in self.eligible_defect_ids:
            _require_nonempty_string(defect_id, "eligible_defect_id")
        if len(set(self.eligible_defect_ids)) != len(self.eligible_defect_ids):
            raise ValueError("duplicate eligible_defect_id")
        if type(self.pull_request_number) is not int or self.pull_request_number < 1:
            raise ValueError("pull_request_number must be an exact positive integer")
        if type(self.truth_status) is not TruthStatus:
            raise ValueError("truth_status must be an exact TruthStatus")
        if type(self.delivery_status) is not DeliveryStatus:
            raise ValueError("delivery_status must be an exact DeliveryStatus")
        if type(self.publication_events) is not tuple or any(
            type(event) is not PublicationEvent for event in self.publication_events
        ):
            raise ValueError("publication_events must be an exact tuple")
        if type(self.task_delivery_events) is not tuple or any(
            type(event) is not TaskDeliveryEvent for event in self.task_delivery_events
        ):
            raise ValueError("task_delivery_events must be an exact tuple")
        if type(self.delivery_transcript) is not DeliveryTranscriptReceipt:
            raise ValueError(
                "delivery_transcript must be an exact DeliveryTranscriptReceipt"
            )
        for label, value in (
            ("candidate_count", self.candidate_count),
            ("published_count", self.published_count),
            ("unresolved_count", self.unresolved_count),
        ):
            if type(value) is not int or value < 0:
                raise ValueError(f"{label} must be an exact non-negative integer")

        finding_ids = tuple(finding.finding_id for finding in self.findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("duplicate finding_id")
        event_ids = tuple(event.event_id for event in self.publication_events)
        if len(set(event_ids)) != len(event_ids):
            raise ValueError("duplicate publication event_id")
        publication_attempt_ids = tuple(
            event.attempt_id for event in self.publication_events
        )
        publication_ordinals = tuple(
            event.attempt_ordinal for event in self.publication_events
        )
        if len(set(publication_attempt_ids)) != len(publication_attempt_ids) or len(
            set(publication_ordinals)
        ) != len(publication_ordinals):
            raise ValueError("duplicate publication attempt identity or ordinal")
        task_event_ids = tuple(event.event_id for event in self.task_delivery_events)
        if len(set(task_event_ids)) != len(task_event_ids):
            raise ValueError("duplicate task delivery event_id")
        task_attempt_ids = tuple(event.attempt_id for event in self.task_delivery_events)
        task_ordinals = tuple(
            event.attempt_ordinal for event in self.task_delivery_events
        )
        if len(set(task_attempt_ids)) != len(task_attempt_ids) or len(
            set(task_ordinals)
        ) != len(task_ordinals):
            raise ValueError("duplicate task delivery attempt identity or ordinal")
        attempt_pairs = {
            (event.attempt_ordinal, event.attempt_id)
            for event in self.publication_events
        } | {
            (event.attempt_ordinal, event.attempt_id)
            for event in self.task_delivery_events
        }
        ordinal_to_attempt: dict[int, str] = {}
        attempt_to_ordinal: dict[str, int] = {}
        for ordinal, attempt_id in attempt_pairs:
            prior_attempt = ordinal_to_attempt.setdefault(ordinal, attempt_id)
            prior_ordinal = attempt_to_ordinal.setdefault(attempt_id, ordinal)
            if prior_attempt != attempt_id or prior_ordinal != ordinal:
                raise ValueError(
                    "delivery attempt ordinal and attempt_id must form a global bijection"
                )
        if set(ordinal_to_attempt) != set(
            range(self.delivery_transcript.expected_attempt_count)
        ):
            raise ValueError(
                "delivery events do not cover the sealed transcript attempt ordinals"
            )
        if any(
            event.pull_request_number != self.pull_request_number
            for event in self.publication_events
        ):
            raise ValueError("publication event pull request does not match measurement")
        publication_targets = {
            (event.repository, event.pull_request_number, event.head_sha)
            for event in self.publication_events
        }
        if len(publication_targets) > 1:
            raise ValueError("publication events must share one exact repository target")
        if any(
            event.pull_request_number != self.pull_request_number
            for event in self.task_delivery_events
        ):
            raise ValueError("task delivery pull request does not match measurement")
        task_targets = {
            (event.repository, event.pull_request_number, event.head_sha)
            for event in self.task_delivery_events
        }
        if len(task_targets) > 1 or (
            publication_targets and task_targets and publication_targets != task_targets
        ):
            raise ValueError("delivery events must share one exact repository target")
        task_by_attempt = {
            event.attempt_id: event for event in self.task_delivery_events
        }
        for publication in self.publication_events:
            task_event = task_by_attempt.get(publication.attempt_id)
            if publication.channel is PublicationChannel.STATUS_SUMMARY:
                if task_event is None:
                    raise ValueError(
                        "status-summary publication must share its task delivery attempt"
                    )
                paired_publication_signature = (
                    publication.attempt_ordinal,
                    publication.repository,
                    publication.pull_request_number,
                    publication.head_sha,
                    publication.channel,
                    publication.members,
                    publication.outcome,
                    publication.body_sha256,
                    publication.request_sha256,
                    publication.remote_response_id,
                    publication.delivered_at_s,
                    publication.deadline_s,
                )
                paired_task_signature = (
                    task_event.attempt_ordinal,
                    task_event.repository,
                    task_event.pull_request_number,
                    task_event.head_sha,
                    task_event.channel,
                    task_event.members,
                    task_event.outcome,
                    task_event.body_sha256,
                    task_event.request_sha256,
                    task_event.remote_response_id,
                    task_event.delivered_at_s,
                    task_event.deadline_s,
                )
                if paired_publication_signature != paired_task_signature:
                    raise ValueError(
                        "publication and task delivery views must share one exact attempt"
                    )
        if any(
            member.finding_id not in set(finding_ids)
            for event in self.publication_events
            for member in event.members
        ):
            raise ValueError("publication event references an unknown finding_id")
        if any(
            member.finding_id not in set(finding_ids)
            for event in self.task_delivery_events
            for member in event.members
        ):
            raise ValueError("task delivery event references an unknown finding_id")
        publication_by_attempt = {
            event.attempt_id: event for event in self.publication_events
        }
        for task_event in self.task_delivery_events:
            matching_publication = publication_by_attempt.get(task_event.attempt_id)
            if task_event.members and matching_publication is None:
                raise ValueError(
                    "task delivery members require the matching publication attempt"
                )
            if matching_publication is not None:
                shared_publication = (
                    matching_publication.attempt_ordinal,
                    matching_publication.repository,
                    matching_publication.pull_request_number,
                    matching_publication.head_sha,
                    matching_publication.channel,
                    matching_publication.members,
                    matching_publication.outcome,
                    matching_publication.body_sha256,
                    matching_publication.request_sha256,
                    matching_publication.remote_response_id,
                    matching_publication.delivered_at_s,
                    matching_publication.deadline_s,
                )
                shared_task = (
                    task_event.attempt_ordinal,
                    task_event.repository,
                    task_event.pull_request_number,
                    task_event.head_sha,
                    task_event.channel,
                    task_event.members,
                    task_event.outcome,
                    task_event.body_sha256,
                    task_event.request_sha256,
                    task_event.remote_response_id,
                    task_event.delivered_at_s,
                    task_event.deadline_s,
                )
                if shared_publication != shared_task:
                    raise ValueError(
                        "task delivery and publication must share one exact attempt"
                    )
        successful_by_finding: dict[str, list[PublicationEvent]] = {}
        ambiguous_by_finding: dict[str, list[PublicationEvent]] = {}
        for event in self.publication_events:
            if event.succeeded:
                for member in event.members:
                    successful_by_finding.setdefault(member.finding_id, []).append(event)
            elif event.outcome is PublicationOutcome.AMBIGUOUS:
                for member in event.members:
                    ambiguous_by_finding.setdefault(member.finding_id, []).append(event)
        published_ids = {
            finding.finding_id for finding in self.findings if finding.author_visible
        }
        if set(successful_by_finding) != published_ids:
            raise ValueError("published findings must equal successful publication events")
        for finding in self.findings:
            ordered_success_ids = tuple(
                event.event_id
                for event in sorted(
                    successful_by_finding.get(finding.finding_id, ()),
                    key=lambda event: event.attempt_ordinal,
                )
            )
            if finding.author_visible and finding.publication_event_ids != ordered_success_ids:
                raise ValueError(
                    "publication_event_ids must order every successful finding attempt"
                )
        ambiguous_unresolved = set(ambiguous_by_finding) - set(successful_by_finding)
        expected_withheld = "ambiguous_publication" if ambiguous_unresolved else None
        if self.metrics_withheld_reason != expected_withheld:
            raise ValueError("metrics_withheld_reason does not match publication ambiguity")
        delivery_ambiguous = {
            finding_id
            for finding_id, ambiguous_events in ambiguous_by_finding.items()
            if not successful_by_finding.get(finding_id)
            or min(event.attempt_ordinal for event in ambiguous_events)
            < min(
                event.attempt_ordinal
                for event in successful_by_finding[finding_id]
            )
        }
        expected_delivery_withheld = (
            "ambiguous_publication" if delivery_ambiguous else None
        )
        if self.delivery_withheld_reason != expected_delivery_withheld:
            raise ValueError(
                "delivery_withheld_reason does not match publication ambiguity"
            )
        task_success_ordinals = tuple(
            event.attempt_ordinal for event in self.task_delivery_events if event.succeeded
        )
        task_ambiguous_ordinals = tuple(
            event.attempt_ordinal
            for event in self.task_delivery_events
            if event.outcome is PublicationOutcome.AMBIGUOUS
        )
        task_ambiguous = bool(task_ambiguous_ordinals) and (
            not task_success_ordinals
            or min(task_ambiguous_ordinals) < min(task_success_ordinals)
        )
        expected_task_withheld = "ambiguous_task_delivery" if task_ambiguous else None
        if self.task_delivery_withheld_reason != expected_task_withheld:
            raise ValueError(
                "task_delivery_withheld_reason does not match task delivery ambiguity"
            )
        actual_published = sum(finding.author_visible for finding in self.findings)
        actual_unresolved = sum(
            finding.finding_status is FindingStatus.UNRESOLVED
            for finding in self.findings
        )
        if self.candidate_count != len(self.findings):
            raise ValueError("candidate_count does not match finding outcomes")
        if self.published_count != actual_published:
            raise ValueError("published_count does not match finding outcomes")
        if self.unresolved_count != actual_unresolved:
            raise ValueError("unresolved_count does not match finding outcomes")
        successful_events = tuple(
            event for event in self.publication_events if event.succeeded
        )
        if actual_published:
            on_time_by_finding = {
                finding_id: any(
                    event.succeeded
                    and event.delivered_on_time is True
                    and any(
                        member.finding_id == finding_id for member in event.members
                    )
                    for event in successful_events
                )
                for finding_id in published_ids
            }
            expected_delivery = (
                DeliveryStatus.PUBLISHED_ON_TIME
                if all(on_time_by_finding.values())
                else DeliveryStatus.PUBLISHED_LATE
            )
            if self.delivery_status is not expected_delivery:
                raise ValueError("delivery_status does not match publication events")
        elif self.delivery_status is not DeliveryStatus.NO_PUBLICATION:
            raise ValueError("no-publication outcome requires no_publication delivery")
        if self.task_status is not derive_task_status(self.stop_kind, self.findings):
            raise ValueError("task_status does not match stop_kind and finding outcomes")
        if self.stop_kind is StopKind.NONE and actual_unresolved:
            raise ValueError("stop none cannot contain unresolved outcomes")
        eligible = set(self.eligible_defect_ids)
        if any(
            finding.accuracy_status is AccuracyStatus.CORRECT
            and finding.defect_id not in eligible
            for finding in self.findings
        ):
            raise ValueError("correct finding references an ineligible defect_id")
        if self.truth_status is TruthStatus.POSITIVE and not eligible:
            raise ValueError("positive truth requires at least one eligible defect")
        if self.truth_status is not TruthStatus.POSITIVE and eligible:
            raise ValueError("only positive truth can carry eligible defects")
        automated = tuple(
            finding
            for finding in self.findings
            if finding.authority is FindingAuthority.AUTOMATED
        )
        if self.truth_status is TruthStatus.NULL and any(
            finding.author_visible
            and finding.accuracy_status is not AccuracyStatus.WRONG
            for finding in automated
        ):
            raise ValueError("null truth automated publications must be wrong")
        if self.truth_status is TruthStatus.UNADJUDICATED and any(
            finding.accuracy_status in {AccuracyStatus.CORRECT, AccuracyStatus.WRONG}
            for finding in automated
        ):
            raise ValueError("unadjudicated truth cannot assert automated accuracy")

    def to_json_dict(self) -> dict[str, object]:
        """Return the exact current persisted representation."""

        return {
            "schema_version": self.schema_version,
            "scoring_semantics": self.scoring_semantics,
            "case_id": self.case_id,
            "arm": self.arm,
            "repeat": self.repeat,
            "stop_kind": self.stop_kind.value,
            "task_status": self.task_status.value,
            "findings": [finding.to_json_dict() for finding in self.findings],
            "eligible_defect_ids": list(self.eligible_defect_ids),
            "pull_request_number": self.pull_request_number,
            "truth_status": self.truth_status.value,
            "delivery_status": self.delivery_status.value,
            "candidate_count": self.candidate_count,
            "published_count": self.published_count,
            "unresolved_count": self.unresolved_count,
            "publication_events": [
                event.to_json_dict() for event in self.publication_events
            ],
            "task_delivery_events": [
                event.to_json_dict() for event in self.task_delivery_events
            ],
            "delivery_transcript": self.delivery_transcript.to_json_dict(),
            "metrics_withheld_reason": self.metrics_withheld_reason,
            "delivery_withheld_reason": self.delivery_withheld_reason,
            "task_delivery_withheld_reason": self.task_delivery_withheld_reason,
        }

    @property
    def task_delivered(self) -> bool:
        return any(event.succeeded for event in self.task_delivery_events)


@dataclass(frozen=True)
class MeasurementSummary:
    """Author-visible denominators over primary semantic units."""

    operational_repeats: int
    operational_published: int | None
    operational_unresolved: int
    operational_correct: int | None
    operational_wrong: int | None
    operational_unadjudicated: int | None
    unique_semantic_outcome_digests: tuple[str, ...]
    semantic_agreement_rate: float | None
    semantic_agreement_by_unit: tuple[tuple[str, str, float], ...]
    semantic_n: int
    published: int | None
    automated_published: int | None
    unresolved: int
    correct: int | None
    wrong: int | None
    unadjudicated: int | None
    metrics_withheld_reason: str | None
    delivery_withheld_reason: str | None
    task_delivery_withheld_reason: str | None
    task_delivered: int | None
    finding_precision: float | None
    eligible_defects: int
    detected_defects: int | None
    missed_defects: int | None
    detection_rate: float | None
    null_pull_requests: int
    pr_false_positive_events: int | None
    pr_false_positive_rate: float | None
    adjudicated_pull_requests: int
    pr_any_wrong_events: int | None
    pr_any_wrong_rate: float | None
    pr_any_wrong_withheld_reason: str | None
    completed: int
    partially_deferred: int
    fully_deferred: int
    failed: int


@dataclass(frozen=True)
class LegacyV1ScoringRecord:
    """Integrity-only legacy record that can never authorize current metrics."""

    run_id: str
    case_id: str
    repeat: int
    prediction_count: int
    payload_sha256: str
    scoring_semantics: str = LEGACY_MEASUREMENT_SEMANTICS
    metrics_withheld_reason: str = LEGACY_V1_METRICS_WITHHELD


def derive_task_status(
    stop_kind: StopKind | str,
    findings: Sequence[FindingOutcome],
) -> TaskStatus:
    """Derive task status without erasing resolved or published finding outcomes."""

    try:
        normalized_stop = (
            stop_kind if type(stop_kind) is StopKind else StopKind(stop_kind)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("unknown stop_kind") from exc
    if any(type(finding) is not FindingOutcome for finding in findings):
        raise ValueError("findings must contain exact FindingOutcome values")
    if normalized_stop is StopKind.FAILURE:
        return TaskStatus.FAILED
    if normalized_stop is StopKind.NONE:
        return TaskStatus.COMPLETED
    has_resolved_outcome = any(
        finding.finding_status is not FindingStatus.UNRESOLVED for finding in findings
    )
    return (
        TaskStatus.PARTIALLY_DEFERRED
        if has_resolved_outcome
        else TaskStatus.FULLY_DEFERRED
    )


def derive_stop_kind(
    terminal_status: TaskDeliveryTerminalStatus,
    findings: Sequence[FindingOutcome],
) -> StopKind:
    """Derive execution stop state from typed terminal and finding outcomes."""

    if type(terminal_status) is not TaskDeliveryTerminalStatus:
        raise ValueError("terminal_status must be an exact TaskDeliveryTerminalStatus")
    if any(type(finding) is not FindingOutcome for finding in findings):
        raise ValueError("findings must contain exact FindingOutcome values")
    if terminal_status is TaskDeliveryTerminalStatus.FAILED:
        return StopKind.FAILURE
    unresolved = sum(
        finding.finding_status is FindingStatus.UNRESOLVED for finding in findings
    )
    if unresolved:
        return (
            StopKind.CANDIDATE_DEFER
            if unresolved < len(findings)
            else StopKind.TASK_DEFER
        )
    if terminal_status is TaskDeliveryTerminalStatus.DEFERRED:
        return StopKind.TASK_DEFER
    return StopKind.NONE


def reduce_measurements(records: Sequence[MeasurementRecord]) -> MeasurementSummary:
    """Reduce repeat-zero semantic units while retaining repeat operational count."""

    if any(type(record) is not MeasurementRecord for record in records):
        raise ValueError("records must contain exact MeasurementRecord values")
    slots = [(record.case_id, record.arm, record.repeat) for record in records]
    if len(set(slots)) != len(slots):
        raise ValueError("duplicate measurement record slot")
    arms = {record.arm for record in records}
    if len(arms) > 1:
        raise ValueError("measurement reducer accepts a single arm, not mixed arms")
    semantic_slots = {(record.case_id, record.arm) for record in records}
    primary = tuple(record for record in records if record.repeat == 0)
    if {(record.case_id, record.arm) for record in primary} != semantic_slots:
        raise ValueError("every semantic measurement requires repeat zero")
    digest_counts = Counter(semantic_measurement_sha256(record) for record in records)
    digest_counts_by_unit: dict[tuple[str, str], Counter[str]] = {}
    for record in records:
        digest_counts_by_unit.setdefault((record.case_id, record.arm), Counter()).update(
            (semantic_measurement_sha256(record),)
        )
    agreement_by_unit = tuple(
        (
            case_id,
            arm,
            max(counts.values()) / counts.total(),
        )
        for (case_id, arm), counts in sorted(digest_counts_by_unit.items())
    )

    published = unresolved = automated_published = 0
    correct = wrong = unadjudicated = 0
    eligible: set[tuple[str, str, str]] = set()
    detected: set[tuple[str, str, str]] = set()
    null_pull_requests = pr_false_positive_events = 0
    adjudicated_pull_requests = pr_any_wrong_events = 0
    incomplete_pr_accuracy = False
    statuses = {status: 0 for status in TaskStatus}

    operational_visible = tuple(
        finding
        for record in records
        for finding in record.findings
        if finding.author_visible
    )
    operational_automated = tuple(
        finding
        for finding in operational_visible
        if finding.authority is FindingAuthority.AUTOMATED
    )
    operational_unresolved = sum(
        finding.finding_status is FindingStatus.UNRESOLVED
        for record in records
        for finding in record.findings
    )

    for record in primary:
        statuses[record.task_status] += 1
        eligible.update(
            (record.case_id, record.arm, defect_id)
            for defect_id in record.eligible_defect_ids
        )
        visible = tuple(finding for finding in record.findings if finding.author_visible)
        published += len(visible)
        unresolved += sum(
            finding.finding_status is FindingStatus.UNRESOLVED
            for finding in record.findings
        )
        automated = tuple(
            finding
            for finding in visible
            if finding.authority is FindingAuthority.AUTOMATED
        )
        automated_published += len(automated)
        correct_findings = tuple(
            finding
            for finding in automated
            if finding.accuracy_status is AccuracyStatus.CORRECT
        )
        correct += len(correct_findings)
        wrong_findings = tuple(
            finding
            for finding in automated
            if finding.accuracy_status is AccuracyStatus.WRONG
        )
        wrong += len(wrong_findings)
        unadjudicated += sum(
            finding.accuracy_status is AccuracyStatus.UNADJUDICATED
            for finding in automated
        )
        detected.update(
            (record.case_id, record.arm, finding.defect_id)
            for finding in correct_findings
            if finding.defect_id is not None
        )
        if record.truth_status is TruthStatus.NULL:
            null_pull_requests += 1
            if wrong_findings:
                pr_false_positive_events += 1
        if record.truth_status in {TruthStatus.POSITIVE, TruthStatus.NULL}:
            if any(
                finding.accuracy_status is AccuracyStatus.UNADJUDICATED
                for finding in automated
            ):
                incomplete_pr_accuracy = True
            else:
                adjudicated_pull_requests += 1
                if wrong_findings:
                    pr_any_wrong_events += 1

    adjudicated = correct + wrong
    eligible_count = len(eligible)
    detected_count = len(detected & eligible)
    metrics_withheld_reason = next(
        (
            record.metrics_withheld_reason
            for record in primary
            if record.metrics_withheld_reason is not None
        ),
        None,
    )
    delivery_withheld_reason = next(
        (
            record.delivery_withheld_reason
            for record in primary
            if record.delivery_withheld_reason is not None
        ),
        None,
    )
    task_delivery_withheld_reason = next(
        (
            record.task_delivery_withheld_reason
            for record in primary
            if record.task_delivery_withheld_reason is not None
        ),
        None,
    )
    task_delivery_known = all(
        record.task_delivery_withheld_reason is None for record in primary
    )
    quality_known = metrics_withheld_reason is None
    return MeasurementSummary(
        operational_repeats=len(records),
        operational_published=(len(operational_visible) if quality_known else None),
        operational_unresolved=operational_unresolved,
        operational_correct=(
            sum(
                finding.accuracy_status is AccuracyStatus.CORRECT
                for finding in operational_automated
            )
            if quality_known
            else None
        ),
        operational_wrong=(
            sum(
                finding.accuracy_status is AccuracyStatus.WRONG
                for finding in operational_automated
            )
            if quality_known
            else None
        ),
        operational_unadjudicated=(
            sum(
                finding.accuracy_status is AccuracyStatus.UNADJUDICATED
                for finding in operational_automated
            )
            if quality_known
            else None
        ),
        unique_semantic_outcome_digests=tuple(sorted(digest_counts)),
        semantic_agreement_rate=(
            sum(max(counts.values()) for counts in digest_counts_by_unit.values())
            / len(records)
            if records
            else None
        ),
        semantic_agreement_by_unit=agreement_by_unit,
        semantic_n=len(primary),
        published=published if quality_known else None,
        automated_published=automated_published if quality_known else None,
        unresolved=unresolved,
        correct=correct if quality_known else None,
        wrong=wrong if quality_known else None,
        unadjudicated=unadjudicated if quality_known else None,
        metrics_withheld_reason=metrics_withheld_reason,
        delivery_withheld_reason=delivery_withheld_reason,
        task_delivery_withheld_reason=task_delivery_withheld_reason,
        task_delivered=(
            sum(record.task_delivered for record in primary)
            if task_delivery_known
            else None
        ),
        finding_precision=(
            correct / adjudicated
            if adjudicated and metrics_withheld_reason is None
            else None
        ),
        eligible_defects=eligible_count,
        detected_defects=detected_count if quality_known else None,
        missed_defects=(
            eligible_count - detected_count
            if metrics_withheld_reason is None
            else None
        ),
        detection_rate=(
            detected_count / eligible_count
            if eligible_count and metrics_withheld_reason is None
            else None
        ),
        null_pull_requests=null_pull_requests,
        pr_false_positive_events=(
            pr_false_positive_events if quality_known else None
        ),
        pr_false_positive_rate=(
            pr_false_positive_events / null_pull_requests
            if null_pull_requests and metrics_withheld_reason is None
            else None
        ),
        adjudicated_pull_requests=adjudicated_pull_requests,
        pr_any_wrong_events=(
            pr_any_wrong_events
            if quality_known and not incomplete_pr_accuracy
            else None
        ),
        pr_any_wrong_rate=(
            pr_any_wrong_events / adjudicated_pull_requests
            if (
                adjudicated_pull_requests
                and metrics_withheld_reason is None
                and not incomplete_pr_accuracy
            )
            else None
        ),
        pr_any_wrong_withheld_reason=(
            "visible_finding_accuracy_incomplete"
            if incomplete_pr_accuracy
            else metrics_withheld_reason
        ),
        completed=statuses[TaskStatus.COMPLETED],
        partially_deferred=statuses[TaskStatus.PARTIALLY_DEFERRED],
        fully_deferred=statuses[TaskStatus.FULLY_DEFERRED],
        failed=statuses[TaskStatus.FAILED],
    )


def decode_measurement_record(payload: Mapping[str, object]) -> MeasurementRecord:
    """Decode only the exact current schema; legacy data needs its named adapter."""

    row = _exact_mapping(payload, _MEASUREMENT_FIELDS, "measurement record")
    findings_value = row["findings"]
    eligible_value = row["eligible_defect_ids"]
    if type(findings_value) is not list:
        raise ValueError("findings must be an exact list")
    if type(eligible_value) is not list:
        raise ValueError("eligible_defect_ids must be an exact list")
    try:
        stop_kind = StopKind(_exact_string(row["stop_kind"], "stop_kind"))
        task_status = TaskStatus(_exact_string(row["task_status"], "task_status"))
    except ValueError as exc:
        raise ValueError("unknown measurement status") from exc
    return MeasurementRecord(
        schema_version=_exact_int(row["schema_version"], "schema_version", minimum=0),
        scoring_semantics=_exact_string(row["scoring_semantics"], "scoring_semantics"),
        case_id=_exact_string(row["case_id"], "case_id"),
        arm=_exact_string(row["arm"], "arm"),
        repeat=_exact_int(row["repeat"], "repeat", minimum=0),
        stop_kind=stop_kind,
        task_status=task_status,
        findings=tuple(_decode_finding(value) for value in findings_value),
        eligible_defect_ids=tuple(
            _exact_string(value, "eligible_defect_id") for value in eligible_value
        ),
        pull_request_number=_exact_int(
            row["pull_request_number"], "pull_request_number", minimum=1
        ),
        truth_status=_truth_status(row["truth_status"]),
        delivery_status=_delivery_status(row["delivery_status"]),
        candidate_count=_exact_int(
            row["candidate_count"], "candidate_count", minimum=0
        ),
        published_count=_exact_int(
            row["published_count"], "published_count", minimum=0
        ),
        unresolved_count=_exact_int(
            row["unresolved_count"], "unresolved_count", minimum=0
        ),
        publication_events=tuple(
            _decode_publication_event(value)
            for value in _exact_list(row["publication_events"], "publication_events")
        ),
        task_delivery_events=tuple(
            _decode_task_delivery_event(value)
            for value in _exact_list(
                row["task_delivery_events"], "task_delivery_events"
            )
        ),
        delivery_transcript=_decode_delivery_transcript(
            row["delivery_transcript"]
        ),
        metrics_withheld_reason=_optional_string(
            row["metrics_withheld_reason"], "metrics_withheld_reason"
        ),
        delivery_withheld_reason=_optional_string(
            row["delivery_withheld_reason"], "delivery_withheld_reason"
        ),
        task_delivery_withheld_reason=_optional_string(
            row["task_delivery_withheld_reason"], "task_delivery_withheld_reason"
        ),
    )


def decode_legacy_v1_scoring(payload: Mapping[str, object]) -> LegacyV1ScoringRecord:
    """Decode a legacy RunRecord only for historical, metrics-withheld inspection."""

    row = _exact_mapping(payload, _LEGACY_RUN_FIELDS, "legacy RunRecord")
    predictions = row["predictions"]
    if type(predictions) is not list:
        raise ValueError("legacy predictions must be an exact list")
    for prediction in predictions:
        _decode_legacy_prediction(prediction)
    repeat = _exact_int(row["repeat"], "repeat", minimum=0)
    _exact_number(row["deadline_s"], "deadline_s", minimum=0.0)
    delivery = row["delivery_at_s"]
    if delivery is not None:
        _exact_number(delivery, "delivery_at_s", minimum=0.0)
    canonical = json.dumps(
        dict(row), sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return LegacyV1ScoringRecord(
        run_id=_exact_string(row["run_id"], "run_id"),
        case_id=_exact_string(row["case_id"], "case_id"),
        repeat=repeat,
        prediction_count=len(predictions),
        payload_sha256=hashlib.sha256(canonical).hexdigest(),
    )


_MEASUREMENT_FIELDS = frozenset(
    {
        "schema_version",
        "scoring_semantics",
        "case_id",
        "arm",
        "repeat",
        "stop_kind",
        "task_status",
        "findings",
        "eligible_defect_ids",
        "pull_request_number",
        "truth_status",
        "delivery_status",
        "candidate_count",
        "published_count",
        "unresolved_count",
        "publication_events",
        "task_delivery_events",
        "delivery_transcript",
        "metrics_withheld_reason",
        "delivery_withheld_reason",
        "task_delivery_withheld_reason",
    }
)
_FINDING_FIELDS = frozenset(
    {
        "finding_id",
        "finding_status",
        "accuracy_status",
        "defect_id",
        "publication_event_ids",
        "authority",
    }
)
_LEGACY_RUN_FIELDS = frozenset(
    {"run_id", "case_id", "repeat", "predictions", "delivery_at_s", "deadline_s"}
)
_LEGACY_PREDICTION_FIELDS = frozenset(
    {
        "finding_id",
        "case_id",
        "file",
        "line",
        "placement",
        "action",
        "repro_status",
        "evidence_class",
    }
)
_PUBLICATION_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "attempt_id",
        "attempt_ordinal",
        "repository",
        "pull_request_number",
        "head_sha",
        "members",
        "channel",
        "outcome",
        "body_sha256",
        "request_sha256",
        "remote_response_id",
        "delivered_at_s",
        "deadline_s",
    }
)

_TASK_DELIVERY_EVENT_FIELDS = frozenset(
    {
        "event_id",
        "attempt_id",
        "attempt_ordinal",
        "repository",
        "pull_request_number",
        "head_sha",
        "channel",
        "members",
        "terminal_status",
        "outcome",
        "body_sha256",
        "request_sha256",
        "remote_response_id",
        "delivered_at_s",
        "deadline_s",
    }
)
_PUBLICATION_MEMBER_FIELDS = frozenset({"finding_id", "placement"})
_DELIVERY_TRANSCRIPT_FIELDS = frozenset(
    {
        "schema_version",
        "protocol",
        "task_id",
        "expected_attempt_count",
        "last_attempt_ordinal",
        "transcript_sha256",
    }
)


def _decode_delivery_transcript(value: object) -> DeliveryTranscriptReceipt:
    row = _exact_mapping(
        value, _DELIVERY_TRANSCRIPT_FIELDS, "delivery transcript receipt"
    )
    last_ordinal = row["last_attempt_ordinal"]
    return DeliveryTranscriptReceipt(
        schema_version=_exact_int(
            row["schema_version"], "delivery transcript schema_version", minimum=0
        ),
        protocol=_exact_string(row["protocol"], "delivery transcript protocol"),
        task_id=_optional_string(row["task_id"], "delivery transcript task_id"),
        expected_attempt_count=_exact_int(
            row["expected_attempt_count"], "expected_attempt_count", minimum=0
        ),
        last_attempt_ordinal=(
            None
            if last_ordinal is None
            else _exact_int(last_ordinal, "last_attempt_ordinal", minimum=0)
        ),
        transcript_sha256=_sha256(
            row["transcript_sha256"], "delivery transcript_sha256"
        ),
    )


def _decode_finding(value: object) -> FindingOutcome:
    row = _exact_mapping(value, _FINDING_FIELDS, "finding outcome")
    try:
        status = FindingStatus(_exact_string(row["finding_status"], "finding_status"))
        accuracy = AccuracyStatus(
            _exact_string(row["accuracy_status"], "accuracy_status")
        )
        authority = FindingAuthority(_exact_string(row["authority"], "authority"))
    except ValueError as exc:
        raise ValueError("unknown finding outcome enum") from exc
    return FindingOutcome(
        finding_id=_exact_string(row["finding_id"], "finding_id"),
        finding_status=status,
        accuracy_status=accuracy,
        defect_id=_optional_string(row["defect_id"], "defect_id"),
        publication_event_ids=tuple(
            _exact_string(value, "publication_event_id")
            for value in _exact_list(
                row["publication_event_ids"], "publication_event_ids"
            )
        ),
        authority=authority,
    )


def _decode_legacy_prediction(value: object) -> None:
    row = _exact_mapping(value, _LEGACY_PREDICTION_FIELDS, "legacy prediction")
    for field in (
        "finding_id",
        "case_id",
        "file",
        "placement",
        "action",
        "repro_status",
        "evidence_class",
    ):
        _exact_string(row[field], field)
    _exact_int(row["line"], "line", minimum=1)


def _decode_publication_event(value: object) -> PublicationEvent:
    row = _exact_mapping(value, _PUBLICATION_EVENT_FIELDS, "publication event")
    try:
        channel = PublicationChannel(
            _exact_string(row["channel"], "publication channel")
        )
        outcome = PublicationOutcome(
            _exact_string(row["outcome"], "publication outcome")
        )
    except ValueError as exc:
        raise ValueError("unknown publication event enum") from exc
    delivered = row["delivered_at_s"]
    return PublicationEvent(
        event_id=_exact_string(row["event_id"], "event_id"),
        attempt_id=_exact_string(row["attempt_id"], "attempt_id"),
        attempt_ordinal=_exact_int(
            row["attempt_ordinal"], "attempt_ordinal", minimum=0
        ),
        repository=_exact_string(row["repository"], "repository"),
        pull_request_number=_exact_int(
            row["pull_request_number"], "pull_request_number", minimum=1
        ),
        head_sha=_exact_string(row["head_sha"], "head_sha"),
        members=tuple(
            _decode_publication_member(member)
            for member in _exact_list(row["members"], "publication members")
        ),
        channel=channel,
        outcome=outcome,
        body_sha256=_sha256(row["body_sha256"], "body_sha256"),
        request_sha256=_sha256(row["request_sha256"], "request_sha256"),
        remote_response_id=_optional_string(
            row["remote_response_id"], "remote_response_id"
        ),
        delivered_at_s=(
            None
            if delivered is None
            else _exact_number(delivered, "delivered_at_s", minimum=0.0)
        ),
        deadline_s=_exact_number(row["deadline_s"], "deadline_s", minimum=0.0),
    )


def _decode_task_delivery_event(value: object) -> TaskDeliveryEvent:
    row = _exact_mapping(value, _TASK_DELIVERY_EVENT_FIELDS, "task delivery event")
    try:
        channel = PublicationChannel(
            _exact_string(row["channel"], "task delivery channel")
        )
        terminal_status = TaskDeliveryTerminalStatus(
            _exact_string(row["terminal_status"], "terminal_status")
        )
        outcome = PublicationOutcome(_exact_string(row["outcome"], "outcome"))
    except ValueError as exc:
        raise ValueError("unknown task delivery status or outcome") from exc
    delivered = row["delivered_at_s"]
    return TaskDeliveryEvent(
        event_id=_exact_string(row["event_id"], "event_id"),
        attempt_id=_exact_string(row["attempt_id"], "attempt_id"),
        attempt_ordinal=_exact_int(
            row["attempt_ordinal"], "attempt_ordinal", minimum=0
        ),
        repository=_exact_string(row["repository"], "repository"),
        pull_request_number=_exact_int(
            row["pull_request_number"], "pull_request_number", minimum=1
        ),
        head_sha=_exact_string(row["head_sha"], "head_sha"),
        channel=channel,
        members=tuple(
            _decode_publication_member(member)
            for member in _exact_list(row["members"], "task delivery members")
        ),
        terminal_status=terminal_status,
        outcome=outcome,
        body_sha256=_sha256(row["body_sha256"], "body_sha256"),
        request_sha256=_sha256(row["request_sha256"], "request_sha256"),
        remote_response_id=_optional_string(
            row["remote_response_id"], "remote_response_id"
        ),
        delivered_at_s=(
            None
            if delivered is None
            else _exact_number(delivered, "delivered_at_s", minimum=0.0)
        ),
        deadline_s=_exact_number(row["deadline_s"], "deadline_s", minimum=0.0),
    )


def _decode_publication_member(value: object) -> PublicationMember:
    row = _exact_mapping(value, _PUBLICATION_MEMBER_FIELDS, "publication member")
    try:
        placement = PublicationPlacement(
            _exact_string(row["placement"], "publication placement")
        )
    except ValueError as exc:
        raise ValueError("unknown publication placement") from exc
    return PublicationMember(
        finding_id=_exact_string(row["finding_id"], "finding_id"),
        placement=placement,
    )


def _exact_mapping(
    value: object,
    fields: frozenset[str],
    label: str,
) -> Mapping[str, object]:
    if type(value) is not dict:
        raise ValueError(f"{label} must be an exact object")
    if set(value) != fields:
        raise ValueError(f"{label} fields do not match the supported schema")
    return value


def _require_nonempty_string(value: object, label: str) -> None:
    if type(value) is not str or not value:
        raise ValueError(f"{label} must be a non-empty exact string")


def _require_sha256(value: object, label: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be an exact lowercase SHA-256 digest")


def _require_response_id(value: object) -> None:
    _require_nonempty_string(value, "remote_response_id")
    assert isinstance(value, str)
    if (
        not value.isascii()
        or not value.isdecimal()
        or str(int(value)) != value
        or int(value) < 1
    ):
        raise ValueError("remote_response_id must be a canonical positive integer")


def _sha256(value: object, label: str) -> str:
    _require_sha256(value, label)
    return cast(str, value)


def _exact_string(value: object, label: str) -> str:
    _require_nonempty_string(value, label)
    return cast(str, value)


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _exact_string(value, label)


def _exact_list(value: object, label: str) -> list[object]:
    if type(value) is not list:
        raise ValueError(f"{label} must be an exact list")
    return value


def _exact_int(value: object, label: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an exact integer >= {minimum}")
    return value


def _exact_number(value: object, label: str, *, minimum: float) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} must be an exact finite number")
    number = float(cast(int | float, value))
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{label} must be finite and >= {minimum}")
    return number


def _truth_status(value: object) -> TruthStatus:
    try:
        return TruthStatus(_exact_string(value, "truth_status"))
    except ValueError as exc:
        raise ValueError("unknown truth_status") from exc


def _delivery_status(value: object) -> DeliveryStatus:
    try:
        return DeliveryStatus(_exact_string(value, "delivery_status"))
    except ValueError as exc:
        raise ValueError("unknown delivery_status") from exc


def semantic_measurement_sha256(record: MeasurementRecord) -> str:
    """Digest repeat-invariant semantics while excluding publication identity.

    The publication identifier is a runtime/API identity and the repeat index is
    operational.  Task/truth/finding lifecycle, adjudication, delivery class,
    and redundant outcome counts remain bound.
    """

    if type(record) is not MeasurementRecord:
        raise ValueError("record must be an exact MeasurementRecord")
    payload = {
        "scoring_semantics": record.scoring_semantics,
        "case_id": record.case_id,
        "arm": record.arm,
        "stop_kind": record.stop_kind.value,
        "task_status": record.task_status.value,
        "truth_status": record.truth_status.value,
        "eligible_defect_ids": sorted(record.eligible_defect_ids),
        "pull_request_number": record.pull_request_number,
        "delivery_status": record.delivery_status.value,
        "candidate_count": record.candidate_count,
        "published_count": record.published_count,
        "unresolved_count": record.unresolved_count,
        "metrics_withheld_reason": record.metrics_withheld_reason,
        "delivery_withheld_reason": record.delivery_withheld_reason,
        "task_delivery_withheld_reason": record.task_delivery_withheld_reason,
        "publication_events": [
            {
                "members": [
                    {
                        "finding_id": member.finding_id,
                        "placement": member.placement.value,
                    }
                    for member in sorted(
                        event.members,
                        key=lambda item: (item.finding_id, item.placement.value),
                    )
                ],
                "repository": event.repository,
                "pull_request_number": event.pull_request_number,
                "head_sha": event.head_sha,
                "channel": event.channel.value,
                "outcome": event.outcome.value,
                "deadline_s": event.deadline_s,
                "delivered_on_time": event.delivered_on_time,
            }
            for event in sorted(
                record.publication_events,
                key=lambda item: (
                    tuple(
                        (member.finding_id, member.placement.value)
                        for member in item.members
                    ),
                    item.channel.value,
                    item.outcome.value,
                ),
            )
        ],
        "task_delivery_events": [
            {
                "repository": event.repository,
                "pull_request_number": event.pull_request_number,
                "head_sha": event.head_sha,
                "terminal_status": event.terminal_status.value,
                "outcome": event.outcome.value,
                "deadline_s": event.deadline_s,
                "delivered_on_time": event.delivered_on_time,
            }
            for event in sorted(
                record.task_delivery_events,
                key=lambda item: (
                    item.terminal_status.value,
                    item.outcome.value,
                    item.request_sha256,
                ),
            )
        ],
        "findings": [
            {
                "finding_id": finding.finding_id,
                "finding_status": finding.finding_status.value,
                "accuracy_status": finding.accuracy_status.value,
                "defect_id": finding.defect_id,
                "authority": finding.authority.value,
            }
            for finding in sorted(record.findings, key=lambda item: item.finding_id)
        ],
    }
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()
