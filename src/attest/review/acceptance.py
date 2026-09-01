"""Pure validation helpers shared by Phase 3 acceptance and CI tests."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from attest.github.client import STATUS_MARKER

REGRESSION_COMMENT_PHASES = ("running", "candidate_count", "review", "complete")
BUG_COMMENT_PHASES = REGRESSION_COMMENT_PHASES
CONTROL_COMMENT_PHASES = ("running", "candidate_count", "complete")
NEW_CODE_COMMENT_PHASES = ("running", "candidate_count", "defer")
REGRESSION_EVIDENCE_CLASS = "regression_reproduced"
NEW_CODE_EVIDENCE_CLASS = "new_code_candidate"
DEFERRED_OUTCOME = "deferred"


class AcceptanceError(RuntimeError):
    """A sanitized local or remote acceptance failure."""


@dataclass(frozen=True)
class CommentClassification:
    sticky: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    finding_ids: tuple[str, ...]


@dataclass(frozen=True)
class LedgerArtifact:
    rows: tuple[dict[str, Any], ...]

    @property
    def task_ids(self) -> frozenset[str]:
        return frozenset(
            str(row["task_id"])
            for row in self.rows
            if isinstance(row.get("task_id"), str) and row["task_id"]
        )

    @property
    def spend_usd(self) -> float:
        final_runs = [
            float(row["spend_usd"])
            for row in self.rows
            if row.get("kind") == "ci_final" and _is_number(row.get("spend_usd"))
        ]
        if final_runs:
            return round(final_runs[-1], 6)
        review_runs = [
            float(row["spend_usd"])
            for row in self.rows
            if row.get("kind") == "review_run" and _is_number(row.get("spend_usd"))
        ]
        if review_runs:
            return round(sum(review_runs), 6)
        return round(
            sum(
                float(row["spend"])
                for row in self.rows
                if row.get("kind") == "review" and _is_number(row.get("spend"))
            ),
            6,
        )

    def assert_event_coverage(
        self,
        *,
        expected_comment_phases: tuple[str, ...],
        inline_finding_ids: Sequence[str],
    ) -> None:
        review_rows = [row for row in self.rows if row.get("kind") == "review"]
        verification_rows = [row for row in self.rows if row.get("kind") == "verification"]
        comment_rows = [row for row in self.rows if row.get("kind") == "github_comment"]
        if any(row.get("outcome") != "posted" for row in comment_rows):
            raise AcceptanceError("ledger requires successful GitHub comment rows")
        phases = tuple(str(row["phase"]) for row in comment_rows)
        if phases != expected_comment_phases:
            raise AcceptanceError(
                f"ledger comment phases {phases!r} do not match {expected_comment_phases!r}"
            )

        reviewed_ids = {str(row["finding_id"]) for row in review_rows}
        reproduced_ids = {
            str(row["finding_id"])
            for row in verification_rows
            if row.get("outcome") == "reproduced"
        }
        if not reproduced_ids.issubset(reviewed_ids):
            raise AcceptanceError("ledger verification references an unreviewed candidate")

        inline_ids = tuple(inline_finding_ids)
        inline_set = set(inline_ids)
        if len(inline_ids) != len(inline_set) or not inline_set.issubset(reproduced_ids):
            raise AcceptanceError(
                "inline finding identities do not match reproduced ledger rows"
            )
        final_rows = [row for row in self.rows if row.get("kind") == "ci_final"]
        if final_rows:
            decisions = final_rows[-1].get("decisions", [])
            surfaced_ids = {
                str(decision.get("finding_id"))
                for decision in decisions
                if isinstance(decision, dict) and decision.get("action") == "surface"
            }
            if not inline_set.issubset(surfaced_ids):
                raise AcceptanceError(
                    "inline finding identities are not final surfaced decisions"
                )

    def evidence_class_of(self, finding_id: str) -> str | None:
        """Return the last differential evidence class recorded for a candidate."""
        classes = [
            str(row["evidence_class"])
            for row in self.rows
            if row.get("kind") == "verification"
            and row.get("finding_id") == finding_id
            and isinstance(row.get("evidence_class"), str)
        ]
        return classes[-1] if classes else None

    def assert_regression_evidence(self, inline_finding_ids: Sequence[str]) -> None:
        """Require head-fail/base-pass evidence for every inline finding."""
        for finding_id in inline_finding_ids:
            recorded = self.evidence_class_of(finding_id)
            if recorded != REGRESSION_EVIDENCE_CLASS:
                raise AcceptanceError(
                    f"inline finding {finding_id} recorded evidence class {recorded!r}, "
                    f"expected {REGRESSION_EVIDENCE_CLASS!r}"
                )

    def assert_new_code_recorded(self) -> None:
        """Require new-code defects to be recorded as unpriced deferrals."""
        rows = [
            row
            for row in self.rows
            if row.get("kind") == "verification"
            and row.get("evidence_class") == NEW_CODE_EVIDENCE_CLASS
        ]
        if not rows:
            raise AcceptanceError(
                f"ledger has no {NEW_CODE_EVIDENCE_CLASS} verification row: the new-code "
                "defect was missed rather than deliberately left unpriced"
            )
        if any(row.get("outcome") != DEFERRED_OUTCOME for row in rows):
            raise AcceptanceError(
                f"{NEW_CODE_EVIDENCE_CLASS} verification rows must stay deferred and unpriced"
            )


def classify_comments(
    issue_comments: Sequence[object], review_comments: Sequence[object]
) -> CommentClassification:
    """Classify sticky status and verified inline comments from API payloads."""
    sticky: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    finding_ids: list[str] = []
    for raw in issue_comments:
        comment = _comment_object(raw, "issue comment")
        if STATUS_MARKER in comment["body"]:
            if not isinstance(comment.get("created_at"), str):
                raise AcceptanceError("issue comment has invalid created_at")
            sticky.append(comment)
    for raw in review_comments:
        comment = _comment_object(raw, "review comment")
        body = comment["body"]
        if "Evidence purchases:" in body and re.search(r"\bV\s+x20(?:\.0+)?\b", body):
            if not isinstance(comment.get("path"), str) or not isinstance(
                comment.get("line"), int
            ):
                raise AcceptanceError("finding review comment has invalid anchor")
            match = re.search(r"(?:^|\n)Finding ID: ([0-9a-f]{10})(?:\n|$)", body)
            if match is None:
                raise AcceptanceError(
                    "verified review comment is missing a stable finding ID"
                )
            findings.append(comment)
            finding_ids.append(match.group(1))
    return CommentClassification(tuple(sticky), tuple(findings), tuple(finding_ids))


def parse_ledger(text: str) -> LedgerArtifact:
    """Parse and validate one downloaded Phase 3 JSONL ledger artifact."""
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            raise AcceptanceError(f"ledger line {number} is invalid JSON") from None
        if not isinstance(raw, dict):
            raise AcceptanceError(f"ledger line {number} is not a JSON object")
        _validate_ledger_row(raw, number)
        rows.append(raw)
    if not rows:
        raise AcceptanceError("ledger artifact is empty")
    artifact = LedgerArtifact(tuple(rows))
    if len(artifact.task_ids) != 1:
        raise AcceptanceError("ledger rows must share one common nonempty task_id")
    return artifact


def _comment_object(raw: object, description: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), int) or not isinstance(
        raw.get("body"), str
    ):
        raise AcceptanceError(f"{description} payload is malformed")
    return raw


def _validate_ledger_row(row: dict[str, Any], number: int) -> None:
    kind = row.get("kind")
    if not isinstance(kind, str) or not kind:
        raise AcceptanceError(f"ledger line {number} is missing kind")
    event_required = {
        "review": ("task_id", "finding_id", "action"),
        "review_run": ("task_id", "spend_usd"),
        "verification": ("task_id", "finding_id", "outcome"),
        "github_comment": ("task_id", "phase", "outcome"),
        "ci_final": ("task_id", "decisions", "spend_usd"),
    }
    for field_name in event_required.get(kind, ("task_id",)):
        if field_name not in row or row[field_name] in (None, ""):
            raise AcceptanceError(f"ledger line {number} is missing {field_name}")
    if kind == "verification" and "evidence_class" in row:
        evidence_class = row["evidence_class"]
        if not isinstance(evidence_class, str) or not evidence_class:
            raise AcceptanceError(f"ledger line {number} has invalid evidence_class")
    if kind == "review" and "spend" in row and not _is_number(row["spend"]):
        raise AcceptanceError(f"ledger line {number} has invalid spend")
    if kind == "review_run" and not _is_number(row["spend_usd"]):
        raise AcceptanceError(f"ledger line {number} has invalid spend_usd")
    if kind == "ci_final" and (
        not isinstance(row["decisions"], list) or not _is_number(row["spend_usd"])
    ):
        raise AcceptanceError(f"ledger line {number} has invalid final accounting")


def _is_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )
