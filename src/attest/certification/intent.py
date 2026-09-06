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

A third shape reaches the drawer under ``attest.intent.v3`` (D-127). D-102 asks
whether the author meant a new *rejection*; nothing asked whether the author
meant a new *returned value*, and on `G-NULL-001a` control ``jinja ac3ac6c9``
the product published a defect claim about a deliberate, commented, four-year-old
change of a function's ``__name__``. So the mirror of D-102: when every head run
failed on an assertion of the generated test rather than on a crash or a
rejection -- a **value mismatch** -- the receipt publishes only when the base
tree **specifies** each value that assertion pins (a base test asserts it, or a
docstring or documentation file writes it down) **and this change leaves every
one of those specifications standing**. A value nothing specified, or a
specification the same diff rewrote, is a behaviour change: the author moved the
value and the generated test restates the old one.

The recall cost is deliberate and is the decision, not a side effect: a
reproduction that invents its own expected value -- which most generated
reproductions do -- can no longer certify a value regression. D-102 paid the
same price on the rejection class.

``attest.intent.v4`` (D-132) narrows that rule in three places, after
`G-NULL-001a` published a second wrong claim under v3. (a) The pinned set is the
assertion that **failed** -- located from the head runs' JUnit longrepr -- and
not every ``assert`` in the generated test; a failure raised from anywhere but an
``assert`` statement pins nothing. (b) A **generic constant** (``None``,
``True``, ``False``, ``0``, ``1``, ``-1``, ``""``, ``b""``, ``0.0``, ``1.0``) is
not a specification: it is asserted somewhere in almost any tree, so a receipt
needs at least one *distinctive* value. (c) A diff that also changes a test, a
docstring, a documentation or changelog line, or an inline comment **touching the
anchored symbol** has said what it meant; that is **intent evidence**, and it
drawers the receipt whatever the base tree specifies.

So the composite rule for a value mismatch: **the base tree specifies every
distinctive value the failing assertion pins, this change leaves every one of
those specifications standing, and the diff carries no intent evidence** --
publish; anything else, the drawer. Deterministic end to end: file reads and an
AST walk, no model anywhere. (c) is this version's answer to the *third* of the
recall cost that pins no literal at all -- it does not recover those receipts,
but it is the reason the remaining ones can be trusted without one: what the
pinned literal cannot say about the author's intent, the author's own prose in
the same diff does.

``attest.intent.v4.2`` (D-174) adds one word to the value rule: the base tree
must specify the value **about the symbol this change touched**. v4.1 asked only
whether some file in the tree pinned the same value, so a repository holding
``assert len("weekday") == 7`` anywhere specified ``7`` for every function that
returns it, and the receipt published against a sentence that was never about the
code under test. Under v4.2 an ``assert`` counts only when its own scope -- the
test function holding it, or the module top level -- writes an anchored symbol as
a name, an attribute or an import; a docstring counts only when it is that
symbol's own docstring or names it; a documentation paragraph counts only when
that paragraph names it. A change that touches no def or class at all anchors no
symbol, nothing can be a specification of it, and the receipt is drawered with
that as its reason. The observation's fields are v4's, unchanged: what moved is
which sites `find_specifications` is allowed to return.

``attest.intent.v4.1`` (D-134) narrows clause (c) and nothing else. v4 read a
symbol name as intent wherever it appeared as a word, so a comment saying "back
to main" or "the snapshot is taken lazily" was a statement about a function named
``main`` or ``snapshot``. Under v4.1 a name is a mention only in a **recognisable
form**: inside backticks, dot-qualified, or a bare name of at least eight
characters that is not ordinary English
(:mod:`attest.review.vocabulary`). Position is untouched -- prose the change moved
*inside the body of a touched symbol* is still intent, because there the link is
where the line sits and not what it is called, and that is the clause that stops
``urllib3 c7b9adcb``.

A receipt is judged under the policy version **it records**, not under the one
in force today (D-121). Bumping the version is a promise to future readers of
the audit chain, not a way to void every receipt already issued: an observation
written under ``attest.intent.new-rejection.v1`` still names its own fields, its
own digest and its own rules here, and D-120's constant rule -- which did not
exist then -- is not applied to it, nor is D-127's value rule applied to either.
A version this module does not know still fails closed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

INTENT_POLICY_VERSION = "attest.intent.v4.2"  # D-174
INTENT_POLICY_V1 = "attest.intent.new-rejection.v1"  # D-102, before D-120
INTENT_POLICY_V2 = "attest.intent.v2"  # D-120, before D-127
INTENT_POLICY_V3 = "attest.intent.v3"  # D-127, before D-132
INTENT_POLICY_V4 = "attest.intent.v4"  # D-132, before D-134
INTENT_POLICY_V41 = "attest.intent.v4.1"  # D-134, before D-174
EVIDENCE_CLASS_REGRESSION = "regression_reproduced"
EVIDENCE_CLASS_BEHAVIOR_CHANGE = "behavior_change"
INTENT_UNKNOWN_LABEL = "behavior change confirmed, intent unknown"
INTENT_UNKNOWN_LABEL_ZH = "行为变化已证实，意图未知"
CONSTANT_CHANGE_LABEL = "constant change confirmed, intent unknown"
CONSTANT_CHANGE_LABEL_ZH = "常量改动已证实，意图未知"
VALUE_CHANGE_LABEL = "value change confirmed, intent unknown"
VALUE_CHANGE_LABEL_ZH = "返回值变化已证实，意图未知"
UNANCHORED_LABEL = "value change confirmed, no symbol to specify"
UNANCHORED_LABEL_ZH = "返回值变化已证实，无可关联符号"
INTENT_STATED_LABEL = "intent stated in the change itself"
INTENT_STATED_LABEL_ZH = "改动自身已陈述意图"
REJECTING_STATEMENTS = ("raise", "assert")
# D-132 (b): values a tree asserts by the hundred, so that finding one is a
# coincidence of vocabulary rather than a statement about the function under
# test. Held as ``repr`` strings, which is how an observation records a pinned
# value; ``0``/``1``/``-1`` cover their float spellings by value, not by text.
GENERIC_VALUE_REPRS = frozenset(
    {
        "None",
        "True",
        "False",
        "0",
        "1",
        "-1",
        "0.0",
        "1.0",
        "-1.0",
        "''",
        'b\'\'',
        "()",
        "[]",
        "{}",
    }
)


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
    # D-127: every head run failed on an assertion of the generated test -- not a
    # crash, not a rejection -- so what the differential shows is a changed value
    value_mismatch: bool = False
    pinned_values: tuple[str, ...] = ()  # repr() of the constants those assertions pin
    # (pinned value, base-tree path that specifies it): a base test asserts it, or
    # a docstring or documentation file writes it down. First site per value.
    value_specified: tuple[tuple[str, str], ...] = ()
    # the specifying sites this change no longer specifies at head
    value_respecified: tuple[tuple[str, str], ...] = ()
    # D-132 (a): the line of the generated test the head runs failed on, agreed
    # across every run; 0 when it could not be read or the runs disagreed. Under
    # v4 ``pinned_values`` is that assertion's, and empty when this is not one.
    failing_assertion_line: int = 0
    # D-132 (c): the def/class names of the anchored file this change touched --
    # those whose head body intersects a changed line, plus those the change
    # removed outright
    anchored_symbols: tuple[str, ...] = ()
    # (symbol, changed file whose prose or test body touches it): a test, a
    # docstring, a documentation or changelog line, or an inline comment the same
    # diff moved. First site per file, so the record stays bounded.
    intent_evidence: tuple[tuple[str, str], ...] = ()

    def digest(self) -> str:
        """Over exactly the fields the recorded policy version defines, so that a
        receipt's digest never moves when a later version adds a field. An
        unknown version is digested whole; it cannot publish either way."""
        values = asdict(self)
        fields = POLICY_FIELDS.get(self.policy_version)
        if fields is not None:
            values = {name: values[name] for name in values if name in fields}
        return hashlib.sha256(
            json.dumps(
                values, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")
        ).hexdigest()


_V1_FIELDS = (
    "policy_version",
    "path",
    "changed_lines",
    "origin_line",
    "origin_statement",
    "exception_type",
    "new_rejection",
    "rejected_inputs",
    "witnesses",
    "head_runs_observed",
)
_V2_FIELDS = (*_V1_FIELDS, "constant_substitution", "asserted_constants")
_V3_FIELDS = (
    *_V2_FIELDS,
    "value_mismatch",
    "pinned_values",
    "value_specified",
    "value_respecified",
)
# The observation each policy version records. v2 adds D-120's two constant
# fields, v3 adds D-127's four value fields, v4 adds D-132's three; a version
# absent from this table is unknown and never publishes.
_V4_FIELDS = (
    *_V3_FIELDS,
    "failing_assertion_line",
    "anchored_symbols",
    "intent_evidence",
)
POLICY_FIELDS: dict[str, tuple[str, ...]] = {
    INTENT_POLICY_V1: _V1_FIELDS,
    INTENT_POLICY_V2: _V2_FIELDS,
    INTENT_POLICY_V3: _V3_FIELDS,
    INTENT_POLICY_V4: _V4_FIELDS,
    # v4.1 and v4.2 record exactly v4's fields: D-134 changes what counts as a
    # mention and D-174 what counts as a specification, neither of them what an
    # observation is made of. A v4 or v4.1 receipt therefore keeps its own
    # digest and its own answer, and each version is a promise about the rule.
    INTENT_POLICY_V41: _V4_FIELDS,
    INTENT_POLICY_VERSION: _V4_FIELDS,
}
_CONSTANT_RULE_VERSIONS = frozenset(
    {
        INTENT_POLICY_V2,
        INTENT_POLICY_V3,
        INTENT_POLICY_V4,
        INTENT_POLICY_V41,
        INTENT_POLICY_VERSION,
    }
)
_VALUE_RULE_VERSIONS = frozenset(
    {INTENT_POLICY_V3, INTENT_POLICY_V4, INTENT_POLICY_V41, INTENT_POLICY_VERSION}
)
# D-132 (b) and (c) arrived together and neither reaches a v1, v2 or v3 receipt.
_V4_RULE_VERSIONS = frozenset(
    {INTENT_POLICY_V4, INTENT_POLICY_V41, INTENT_POLICY_VERSION}
)
# D-174's association rule reaches v4.2 and nothing earlier.
_V42_RULE_VERSIONS = frozenset({INTENT_POLICY_VERSION})


def constant_change(observation: IntentObservation) -> bool:
    """D-120: the failing assertion rests only on constants the change
    substituted. The rule arrived with v2; a v1 receipt was never judged by it."""
    if observation.policy_version not in _CONSTANT_RULE_VERSIONS:
        return False
    return observation.constant_substitution and bool(observation.asserted_constants)


def value_change(observation: IntentObservation) -> bool:
    """D-127: the head failure is a value mismatch, so the value rule applies.
    The rule arrived with v3; a v1 or v2 receipt was never judged by it."""
    return observation.policy_version in _VALUE_RULE_VERSIONS and observation.value_mismatch


def distinctive_pinned_values(observation: IntentObservation) -> tuple[str, ...]:
    """D-132 (b): the pinned values a base tree can meaningfully specify.

    Under v4 and v4.1 that is the pinned set minus :data:`GENERIC_VALUE_REPRS`;
    under every earlier version it is the pinned set itself, because the rule did
    not exist when those receipts were written.
    """
    if observation.policy_version not in _V4_RULE_VERSIONS:
        return observation.pinned_values
    return tuple(
        value for value in observation.pinned_values if value not in GENERIC_VALUE_REPRS
    )


def value_change_reason(observation: IntentObservation) -> str | None:
    """D-127: why a value mismatch may not publish, or ``None`` when it may.

    It may when the base tree specified every value the failing assertion pins
    -- a base test asserted it, or a docstring or documentation file wrote it
    down -- and this change left every one of those specifications standing.
    Everything else, an unpinned assertion included, is a behaviour change whose
    intent this product cannot read.
    """
    if not value_change(observation):
        return None
    distinctive = distinctive_pinned_values(observation)
    # Most specific first: the change rewrote the very sentence the receipt would
    # have contradicted. Then D-132 (c): the change said what it meant somewhere
    # else in the same diff. Then what the pinned set itself cannot support.
    if any(value in set(distinctive) for value, _site in observation.value_respecified):
        return (
            f"{VALUE_CHANGE_LABEL}: this change also rewrites the base tree's own "
            f"specification of that value ({VALUE_CHANGE_LABEL_ZH})"
        )
    if observation.policy_version in _V4_RULE_VERSIONS and observation.intent_evidence:
        return (
            f"{INTENT_STATED_LABEL}: the same change also updates a test, a docstring, "
            f"documentation, a changelog entry or an inline comment about the symbol "
            f"under test ({INTENT_STATED_LABEL_ZH})"
        )
    if not observation.pinned_values:
        return (
            f"{VALUE_CHANGE_LABEL}: the failing assertion pins no value the base tree "
            f"could have specified ({VALUE_CHANGE_LABEL_ZH})"
        )
    if not distinctive:
        return (
            f"{VALUE_CHANGE_LABEL}: the failing assertion pins only a generic constant, "
            f"which almost any tree asserts somewhere and which therefore specifies "
            f"nothing about the code under test ({VALUE_CHANGE_LABEL_ZH})"
        )
    # D-174: with no anchored symbol there is nothing a specification could be
    # *about*, so the absence of one says nothing. Named apart from the ordinary
    # "not specified" reason because it is a different fact about the change.
    if observation.policy_version in _V42_RULE_VERSIONS and not observation.anchored_symbols:
        return (
            f"{UNANCHORED_LABEL}: this change touches no function or class of the "
            f"anchored file, so no test, docstring or document can specify the value "
            f"for it ({UNANCHORED_LABEL_ZH})"
        )
    specified = {value for value, _path in observation.value_specified}
    if any(value not in specified for value in distinctive):
        about = (
            " about the symbol this change touched"
            if observation.policy_version in _V42_RULE_VERSIONS
            else ""
        )
        return (
            f"{VALUE_CHANGE_LABEL}: the base tree does not specify the value this "
            f"assertion pins{about} -- no base test asserts it and no docstring or "
            f"documentation writes it down ({VALUE_CHANGE_LABEL_ZH})"
        )
    return None


def evidence_class_for(observation: IntentObservation) -> str:
    """The evidence class the observation supports."""
    return (
        EVIDENCE_CLASS_BEHAVIOR_CHANGE
        if observation.new_rejection
        or constant_change(observation)
        or value_change_reason(observation) is not None
        else EVIDENCE_CLASS_REGRESSION
    )


def intent_verdict(observation: IntentObservation) -> str | None:
    """None when the receipt may publish under its evidence class; otherwise why
    a behavior-change receipt stays in the drawer."""
    if observation.policy_version not in POLICY_FIELDS:
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
    # D-127: a value mismatch is not a new rejection, so it is judged here and
    # the rejection rules below never see it.
    value_reason = value_change_reason(observation)
    if value_reason is not None:
        return value_reason
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
