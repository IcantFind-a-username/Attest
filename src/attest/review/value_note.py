"""The value-class observation, as one yellow line — shadow only (D-218).

D-127 and its successors decided that a differential about a **changed value**
may not publish as a defect unless the base tree specified the value it moved.
That decision stands and nothing here touches it: what it produces is a drawer,
and the drawer is the right verdict for *"this is a defect"*.

But the drawer throws away a fact the run measured and paid for. On a candidate
labelled ``value change confirmed, intent unknown`` the product has executed the
same call on both revisions, three times each side, and watched them disagree.
It cannot say the change is wrong. It can say, exactly and with coordinates,
**what moved** — and that nothing in the tree pinned it, which is precisely why
the intent clause could not read the author's intent.

That is a yellow claim in this product's own grammar (`docs/mainline.md` §1):
red is *this is a defect and here is the receipt*, yellow is *here is a fact you
should look at*, and the fact here is not an inference. Every number in the line
was measured by this process minutes earlier.

**This module reaches no author.** `ci.py` does not import it; nothing posts it.
It writes a ledger row and renders a line, and whether that line becomes
author-visible is the owner's decision, taken on the census this shadow run
produces (`docs/acceptance/2026-09-11-value-note-shadow.md`) rather than on an
argument.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from attest.certification.intent import (
    INTENT_UNKNOWN_LABEL,
    VALUE_CHANGE_LABEL,
    IntentObservation,
)
from attest.review.output_contract import claim_line

VALUE_NOTE_POLICY_VERSION = "attest.value-note.v1"

# The two drawers this note is written from. Both mean *the differential is
# real and the intent is unreadable*; the third drawer, "intent stated in the
# change itself", means the opposite and is deliberately absent -- there the
# author already said what they meant, and a note would be telling them so.
NOTE_DRAWERS = (VALUE_CHANGE_LABEL, INTENT_UNKNOWN_LABEL)


def drawered_for_unknown_intent(reason: str) -> bool:
    """Does this verification reason carry one of the two drawers?"""
    return any(label in (reason or "") for label in NOTE_DRAWERS)


@dataclass(frozen=True)
class ValueNote:
    """What the two revisions did, and what the tree says about it."""

    policy_version: str
    path: str
    line: int
    expression: str
    base_kind: str  # "value" | "exception"
    base_detail: str
    head_kind: str
    head_detail: str
    head_runs: int
    base_runs: int
    # D-132/D-174's own answer, carried verbatim: the values the failing
    # assertion pinned, and the base-tree sites that specify each of them.
    pinned_values: tuple[str, ...]
    specified_by: tuple[tuple[str, str], ...]
    drawer_reason: str
    candidate_id: str

    @property
    def nothing_pins_it(self) -> bool:
        return not self.specified_by

    def note_id(self) -> str:
        """A stable name for this note, so the line can point at the row.

        A drawered differential has **no receipt** -- that is what drawered
        means -- so the line cannot honestly end in one. It ends in the digest
        of the note itself, which an operator finds in the ledger by grep.
        """
        body = {k: v for k, v in asdict(self).items() if k != "policy_version"}
        return hashlib.sha256(
            json.dumps(body, sort_keys=True, default=list).encode("utf-8")
        ).hexdigest()[:12]

    def sentence(self) -> str:
        """The fact clause: what each revision produced, and how many times."""
        base = (
            f"raised {self.base_detail}"
            if self.base_kind == "exception"
            else f"returned {self.base_detail}"
        )
        head = (
            f"raises {self.head_detail}"
            if self.head_kind == "exception"
            else f"returns {self.head_detail}"
        )
        pins = (
            "no base test, docstring or changelog pins either"
            if self.nothing_pins_it
            else "the base tree pins it at "
            + ", ".join(site for _value, site in self.specified_by[:2])
            + ", and this change moved it"
        )
        return (
            f"for {self.expression}, the merge base {base} and head {head} "
            f"({self.head_runs}/{self.head_runs} and {self.base_runs}/{self.base_runs} "
            f"runs each side); {pins}"
        )


def render(note: ValueNote) -> str:
    """The one contract line this note would be, if it were ever shown."""
    return claim_line(
        "yellow",
        path=note.path,
        line=note.line,
        fact=note.sentence(),
        evidence=f"note {note.note_id()}",
    )


def note_from(
    *,
    intent: IntentObservation,
    expression: str,
    base_kind: str,
    base_detail: str,
    head_kind: str,
    head_detail: str,
    head_runs: int,
    base_runs: int,
    reason: str,
    candidate_id: str,
    anchor_line: int,
) -> ValueNote | None:
    """The note for one drawered differential, or None when there is none.

    None is the common answer and is not a failure: a differential that
    certified, one drawered for a reason other than unreadable intent, and one
    whose probe recorded nothing on the head revision all return it. **The head
    observation is required**: a note that could not say what head produced
    would be a claim with half its evidence missing, and this level's whole
    argument is that every number in it was measured.
    """
    if not drawered_for_unknown_intent(reason):
        return None
    if not expression or not head_kind:
        return None
    return ValueNote(
        policy_version=VALUE_NOTE_POLICY_VERSION,
        path=intent.path,
        line=intent.failing_assertion_line or anchor_line,
        expression=expression,
        base_kind=base_kind,
        base_detail=base_detail,
        head_kind=head_kind,
        head_detail=head_detail,
        head_runs=head_runs,
        base_runs=base_runs,
        pinned_values=tuple(intent.pinned_values),
        specified_by=tuple((str(a), str(b)) for a, b in intent.value_specified),
        drawer_reason=reason,
        candidate_id=candidate_id,
    )
