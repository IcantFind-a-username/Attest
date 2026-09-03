"""Intent of a head failure: regression or a new rejection (owner decision 2026-09-03, D-102).

A differential result plus changed-line binding proves that the changed code
made the test fail on head where it passed on base. It does not say whether
head *misbehaves* or *refuses on purpose*: a validation tightened on an existing
definition rejects every input it newly refuses, and each such input yields a
valid ``head_fail_base_pass`` receipt (``RISK-INTENT-01``, observed on E-01).

The intent observation records where the head failure was raised. When the
exception came from a ``raise`` or ``assert`` statement on a changed line of
the anchored file, the receipt is a **behavior change**: head rejects an input
the base accepted. Such a receipt may publish only when the rejected input is
attested by the base tree -- it occurs verbatim in the base tree's tests,
fixtures or documentation examples -- and otherwise goes to the drawer with the
label "behavior change confirmed, intent unknown". Pure: values in, verdict out.

A second shape reaches the same drawer (D-120): when every literal constant the
failing assertion rests on is a constant the change **substituted** -- a version
string, a tuned constant, changelog copy: removed from the anchored file and
replaced by another of the same type -- the differential proves that the author
edited a literal and that the test restates the old one. That is a behaviour
change by construction, not a regression, and no witness publishes it.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

INTENT_POLICY_VERSION = "attest.intent.v2"
EVIDENCE_CLASS_REGRESSION = "regression_reproduced"
EVIDENCE_CLASS_BEHAVIOR_CHANGE = "behavior_change"
INTENT_UNKNOWN_LABEL = "behavior change confirmed, intent unknown"
INTENT_UNKNOWN_LABEL_ZH = "行为变化已证实，意图未知"
CONSTANT_CHANGE_LABEL = "constant change confirmed, intent unknown"
CONSTANT_CHANGE_LABEL_ZH = "常量改动已证实，意图未知"
REJECTING_STATEMENTS = ("raise", "assert")


@dataclass(frozen=True)
class IntentObservation:
    """What the head runs showed about where and on what input they failed."""

    policy_version: str
    path: str  # the anchored file
    changed_lines: tuple[int, ...]
    origin_line: int  # line of the anchored file the failure was raised from; 0 = none
    origin_statement: str  # "raise" | "assert" | "other" | ""
    exception_type: str  # e.g. "ValueError"; "" when no origin was recorded
    new_rejection: bool  # origin is a raise/assert on a changed line, on every head run
    rejected_inputs: tuple[str, ...]  # test string literals that reached the raising frame
    witnesses: tuple[tuple[str, str], ...]  # (rejected input, base-tree path it occurs in)
    head_runs_observed: int
    # D-120: every constant the generated test's assertions rest on is one the
    # change substituted in the anchored file (removed, and one of the same type
    # added in its place)
    constant_substitution: bool = False
    asserted_constants: tuple[str, ...] = ()  # repr() of those constants

    def digest(self) -> str:
        return hashlib.sha256(
            json.dumps(
                asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()


def constant_change(observation: IntentObservation) -> bool:
    """D-120: the failing assertion rests only on constants the change substituted."""
    return observation.constant_substitution and bool(observation.asserted_constants)


def evidence_class_for(observation: IntentObservation) -> str:
    """The evidence class the observation supports."""
    return (
        EVIDENCE_CLASS_BEHAVIOR_CHANGE
        if observation.new_rejection or constant_change(observation)
        else EVIDENCE_CLASS_REGRESSION
    )


def intent_verdict(observation: IntentObservation) -> str | None:
    """None when the receipt may publish under its evidence class; otherwise why
    a behavior-change receipt stays in the drawer."""
    if observation.policy_version != INTENT_POLICY_VERSION:
        return "unknown intent policy"
    if observation.head_runs_observed < 1:
        return "no head run observed"
    if observation.new_rejection and (
        observation.origin_statement not in REJECTING_STATEMENTS
        or observation.origin_line not in observation.changed_lines
    ):
        return "new rejection recorded without a rejecting statement on a changed line"
    # D-120 precedes the witness rule: when everything the assertion pins is a
    # literal the change replaced, no base-tree witness can tell a defect from a
    # deliberate edit -- the test restates the old constant and nothing else.
    if constant_change(observation):
        return (
            f"{CONSTANT_CHANGE_LABEL}: every literal the failing assertion rests on is "
            f"a constant this change replaced ({CONSTANT_CHANGE_LABEL_ZH})"
        )
    if not observation.new_rejection:
        return None
    # The verdict is what an author reads in the run status and the drawer, so
    # it names neither the anchored line nor the rejected input (D-091); the
    # observation itself keeps both for the ledger and the bundle.
    raised = (
        f"head raises {observation.exception_type} from a {observation.origin_statement} "
        "statement on a changed line"
    )
    if not observation.rejected_inputs:
        return (
            f"{INTENT_UNKNOWN_LABEL}: {raised}; no rejected input could be identified "
            f"from the test's literals ({INTENT_UNKNOWN_LABEL_ZH})"
        )
    witnessed = {literal for literal, _path in observation.witnesses}
    if any(literal not in witnessed for literal in observation.rejected_inputs):
        return (
            f"{INTENT_UNKNOWN_LABEL}: {raised}; the rejected input is not in the base "
            f"tree's tests, fixtures or documentation ({INTENT_UNKNOWN_LABEL_ZH})"
        )
    return None
