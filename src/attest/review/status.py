"""Run status for silent and non-silent runs alike (owner item 6, 2026-09-03).

A status is operational information about one review task, computed from the
ledger rows the task wrote: how many change units were read, how many
candidates were proposed, how many were eligible, how many reproductions were
attempted and why each attempt failed, by category. It is not a finding and is
not bound by receipt-only publication, so it may be shown on every run --
but it never carries the claim, file or line of an uncertified candidate.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from attest.certification.intent import INTENT_UNKNOWN_LABEL, INTENT_UNKNOWN_LABEL_ZH

STATUS_SCHEMA_VERSION = "attest.run-status.v1"

FAILURE_CATEGORIES = (
    "behavior change, intent unknown",
    "environment bootstrap failed",
    "no text returned",
    "unfaithful test",
    "environment or import failure",
    "timeout",
    "changed lines not executed",
    "collection failure",
    "other",
)


def _as_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def categorise_failure(reason: str) -> str:
    """The category of one reproduction failure, from its recorded reason."""
    text = reason.lower()
    if "intent unknown" in text:
        # D-102: head rejects an input the base accepted, and the base tree
        # does not attest that input as legitimate
        return "behavior change, intent unknown"
    if "environment bootstrap failed" in text or "isolation backend unavailable" in text:
        return "environment bootstrap failed"
    if "generation_no_text" in text:
        return "no text returned"
    if "timed out" in text or "deadline" in text:
        return "timeout"
    if "unfaithful" in text or "stale" in text or "absent from head" in text:
        return "unfaithful test"
    if "imported from outside" in text or "none of the changed lines" in text:
        return "changed lines not executed"
    if "binding:" in text:
        return "changed lines not executed"
    if "collection" in text:
        return "collection failure"
    if any(
        marker in text
        for marker in (
            "modulenotfounderror",
            "importerror",
            "interpreter",
            "executor",
            "process guard",
            "containment",
            "network guard",
            "junit",
        )
    ):
        return "environment or import failure"
    return "other"


@dataclass(frozen=True)
class RunStatus:
    task_id: str
    units_read: int
    candidates: int
    eligible: int
    attempts: int
    certified: int
    published: int
    units_planned: int = 0  # change units the plan held, read or not
    budget_limited: bool = False  # the per-unit budget stopped the proposal
    failures: tuple[tuple[str, str], ...] = ()  # (category, bounded reason), attempt order
    counts: Mapping[str, int] = field(default_factory=dict)
    prompt_tokens: int = 0  # proposal prompt tokens: uncached + cache writes + cache reads
    cache_read_input_tokens: int = 0  # of which served from the prompt cache
    behavior_changes: int = 0  # D-102: accepted receipts of the behavior-change class

    def lines(self) -> list[str]:
        # A silence covers exactly the change units it read, so it says so
        # always -- not only when the budget was what stopped it (owner
        # instruction 5 of 2026-09-04). "read 1 of 13 units" and "read 13 of 13
        # units" are different claims, and the reader cannot infer which from a
        # bare count.
        planned = self.units_planned or self.units_read
        read = f"read {self.units_read} of {planned} units"
        if self.budget_limited:
            read += ", budget-limited"
        out = [
            f"{read}; candidates: {self.candidates}; "
            f"eligible: {self.eligible}; reproductions attempted: {self.attempts}; "
            f"certified: {self.certified}; published: {self.published}"
            + (
                f"; behavior changes verified: {self.behavior_changes}"
                if self.behavior_changes
                else ""
            ),
            f"proposal prompt tokens: {self.prompt_tokens}; cache_read_input_tokens: "
            f"{self.cache_read_input_tokens}",
        ]
        for index, (category, reason) in enumerate(self.failures, 1):
            out.append(f"reproduction {index}: {category} — {reason}")
        return out

    def render(self) -> str:
        return "\n".join(self.lines())

    def render_collapsed(self) -> str:
        """A GitHub-collapsed section for the pull-request status comment."""
        body = "\n".join(f"- {line}" for line in self.lines())
        return f"<details>\n<summary>Run status</summary>\n\n{body}\n\n</details>"


# The default bound on a reproduction reason. A bootstrap failure is the one
# category whose reason is *the evidence*: `failure-modes.md` tells the operator
# to read the build log's tail there, and the fixed prefix
# `isolation backend unavailable: ` alone spends 31 of the 200, so ~9% of the
# 1,200-character tail arrived. That category gets a bound sized to the tail it
# is documented to carry (2026-09-03 backlog, D-105 review finding 7).
REASON_LIMIT = 200
BOOTSTRAP_REASON_LIMIT = 1_400
_BOOTSTRAP_MARKERS = ("environment bootstrap failed", "isolation backend unavailable")


def _bounded(reason: str, limit: int | None = None) -> str:
    reason = " ".join(str(reason).split())
    if limit is None:
        limit = (
            BOOTSTRAP_REASON_LIMIT
            if any(marker in reason for marker in _BOOTSTRAP_MARKERS)
            else REASON_LIMIT
        )
    return reason if len(reason) <= limit else reason[: limit - 3] + "..."


def status_from_rows(rows: Iterable[Mapping[str, object]], task_id: str) -> RunStatus:
    """Compute the status of one task from its ledger rows; unknown rows are
    ignored, so an older ledger still yields a status."""
    mine = [row for row in rows if row.get("task_id") == task_id]
    units = 0
    planned = 0
    budget_limited = False
    for row in mine:
        if row.get("kind") == "review_plan":
            plan_units = row.get("units")
            units = len(plan_units) if isinstance(plan_units, list) else 0
            planned = units
        if row.get("kind") == "proposal_coverage":
            # the proposal knows how many units the budget funded; the plan row
            # only knows how many it held
            units = _as_int(row.get("units_read"))
            planned = _as_int(row.get("units_planned")) or units
            budget_limited = bool(row.get("budget_limited"))
    candidates = {
        str(row.get("finding_id"))
        for row in mine
        if row.get("kind") == "eligibility" and row.get("finding_id")
    }
    eligible = {
        str(row.get("finding_id"))
        for row in mine
        if row.get("kind") == "eligibility" and row.get("eligibility") == "regression"
    }
    failures: list[tuple[str, str]] = []
    attempts = 0
    for row in mine:
        if row.get("kind") != "verification":
            continue
        attempts += 1
        outcome = str(row.get("outcome") or "")
        if outcome == "reproduced":
            continue
        reason = _bounded(str(row.get("reason") or ""))
        if outcome == "not_reproduced":
            failures.append(("unfaithful test", reason or "the test passed on head"))
        else:
            category = categorise_failure(reason)
            if category == "behavior change, intent unknown":
                # the recorded reason names the anchored line and the rejected
                # input; the status never carries an uncertified candidate's
                # location or content (D-091), only the label
                reason = f"{INTENT_UNKNOWN_LABEL} ({INTENT_UNKNOWN_LABEL_ZH})"
            failures.append((category, reason))
    certified = sum(
        1 for row in mine if row.get("kind") == "certification" and row.get("outcome") == "accepted"
    )
    behavior_changes = sum(
        1
        for row in mine
        if row.get("kind") == "certification"
        and row.get("outcome") == "accepted"
        and row.get("evidence_class") == "behavior_change"
    )
    published = 0
    for row in mine:
        if row.get("kind") == "publication_policy":
            listed = row.get("published")
            published = len(listed) if isinstance(listed, list) else 0
    prompt_tokens = 0
    cache_reads = 0
    for row in mine:
        if row.get("kind") != "review_run":
            continue
        samples = row.get("provider_samples")
        if not isinstance(samples, list):
            continue
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            uncached = sample.get("input_tokens") or 0
            created = sample.get("cache_creation_input_tokens") or 0
            read = sample.get("cache_read_input_tokens") or 0
            prompt_tokens += int(uncached) + int(created) + int(read)
            cache_reads += int(read)
    counts: dict[str, int] = {}
    for category, _reason in failures:
        counts[category] = counts.get(category, 0) + 1
    return RunStatus(
        task_id=task_id,
        units_read=units,
        units_planned=planned,
        budget_limited=budget_limited,
        candidates=len(candidates),
        eligible=len(eligible),
        attempts=attempts,
        certified=certified,
        published=published,
        failures=tuple(failures),
        counts=counts,
        prompt_tokens=prompt_tokens,
        cache_read_input_tokens=cache_reads,
        behavior_changes=behavior_changes,
    )
