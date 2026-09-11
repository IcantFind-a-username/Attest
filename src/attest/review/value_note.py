"""The value-class observation, as one yellow line (D-218; author-visible
behind `value_notes_visible` since owner instruction 4 of 2026-09-11).

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

**Where it reaches an author, and where it does not.** The note is always
written to the ledger. It is rendered to a pull request only when the
base-owned policy sets ``value_notes_visible`` (off by default), and then under
four rules the 2026-09-11 census and the paid run of the same day asked for:
one note per ``(path, expression)``; a value over ``VALUE_VERBATIM_CHARS`` is
written as ``<type len=N sha256 hhhhhhhh>`` rather than cut; a banned phrase
inside a measured literal does not refuse the line; and a note anchored inside
``tests/`` is not shown. D-234 adds a fifth: when both values are containers of
at most ``MAX_DIFF_ELEMENTS`` elements, the line names the **first element
that differs** -- ``first differ at index i (3/3 and 3/3 runs): base <element> →
head <element>`` -- and digests only when an element is too long to quote or the
line would still not fit the contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass

from attest.certification.intent import (
    INTENT_UNKNOWN_LABEL,
    VALUE_CHANGE_LABEL,
    IntentObservation,
)
from attest.review.output_contract import MAX_LINE_CHARS, ContractVerdict, check, claim_line

VALUE_NOTE_POLICY_VERSION = "attest.value-note.v3"  # D-234

# A measured value is quoted whole up to this many characters (owner
# instruction 4 of 2026-09-11); over it, or when the line would still not fit
# the contract, it is written as a digest of the recorded `repr`.
VALUE_VERBATIM_CHARS = 200
# The probe's expression is quoted whole up to this many characters
EXPRESSION_VERBATIM_CHARS = 120
# D-234: when both values are a sequence, a mapping or a record list of at
# most this many elements, the line names the first element that differs
# rather than digesting both wholes -- `python-dotenv#640` moved one key from
# `'\ufeffFOO'` to `'FOO'` inside a 198-character list and the v2 line showed
# two digests. Each element is quoted whole up to ELEMENT_VERBATIM_CHARS;
# a longer element falls back to the whole-value rendering.
MAX_DIFF_ELEMENTS = 50
ELEMENT_VERBATIM_CHARS = 120
_BRACKETS = {"[": ("]", "list"), "(": (")", "tuple"), "{": ("}", "mapping")}
# the same rule the gate level applies to a path (D-166)
TEST_PATH = re.compile(r"(^|/)(tests?/|test_[^/]*\.py$|[^/]*_test\.py$)")

# The two drawers this note is written from. Both mean *the differential is
# real and the intent is unreadable*; the third drawer, "intent stated in the
# change itself", means the opposite and is deliberately absent -- there the
# author already said what they meant, and a note would be telling them so.
NOTE_DRAWERS = (VALUE_CHANGE_LABEL, INTENT_UNKNOWN_LABEL)


def drawered_for_unknown_intent(reason: str) -> bool:
    """Does this verification reason carry one of the two drawers?"""
    return any(label in (reason or "") for label in NOTE_DRAWERS)


@dataclass(frozen=True)
class FirstDifference:
    """The first element at which two recorded container values disagree."""

    kind: str  # list | tuple | mapping | set, read off the repr's brackets
    base_len: int
    head_len: int
    index: int
    base: str  # the element's repr, or "" when base has no element there
    head: str

    @property
    def label(self) -> str:
        return f"index {self.index}"


def split_top_level(text: str) -> tuple[str, list[str]] | None:
    """The top-level elements of a bracketed `repr` -- a list, tuple, dict or
    set -- split at depth-zero commas outside string literals. ``None`` when
    the text is not one bracketed value, is unbalanced, or a quote never
    closes: a reading of the text, never a claim about the object."""
    stripped = text.strip()
    if not stripped or stripped[0] not in _BRACKETS:
        return None
    closer, kind = _BRACKETS[stripped[0]]
    if stripped[-1] != closer:
        return None
    body = stripped[1:-1]
    elements: list[str] = []
    depth = 0
    quote: str | None = None
    start = 0
    i = 0
    while i < len(body):
        char = body[i]
        if quote is not None:
            if char == "\\":
                i += 2
                continue
            if char == quote:
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif char in "([{":
            depth += 1
        elif char in ")]}":
            depth -= 1
            if depth < 0:
                return None
        elif char == "," and depth == 0:
            elements.append(body[start:i].strip())
            start = i + 1
        i += 1
    if quote is not None or depth != 0:
        return None
    tail = body[start:].strip()
    if tail:
        elements.append(tail)
    if kind == "mapping" and not any(":" in element for element in elements):
        kind = "set"
    return kind, elements


def first_difference(base: str, head: str) -> FirstDifference | None:
    """D-234: where two container values first differ, when both are
    containers of the same kind with at most MAX_DIFF_ELEMENTS elements and
    the differing elements each fit ELEMENT_VERBATIM_CHARS. ``None`` sends the
    line back to the whole-value rendering."""
    base_split, head_split = split_top_level(base), split_top_level(head)
    if base_split is None or head_split is None:
        return None
    (base_kind, base_items), (head_kind, head_items) = base_split, head_split
    if base_kind != head_kind:
        return None
    if max(len(base_items), len(head_items)) > MAX_DIFF_ELEMENTS:
        return None
    for index in range(max(len(base_items), len(head_items))):
        left = base_items[index] if index < len(base_items) else ""
        right = head_items[index] if index < len(head_items) else ""
        if left == right:
            continue
        if len(left) > ELEMENT_VERBATIM_CHARS or len(right) > ELEMENT_VERBATIM_CHARS:
            return None
        return FirstDifference(
            kind=base_kind,
            base_len=len(base_items),
            head_len=len(head_items),
            index=index,
            base=left,
            head=right,
        )
    return None


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

    def difference(self) -> FirstDifference | None:
        """D-234: the first differing element, when both revisions returned a
        container this line can name an element of."""
        if self.base_kind != "value" or self.head_kind != "value":
            return None
        return first_difference(self.base_detail, self.head_detail)

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

    def sentence(self, *, digested: Sequence[str] = ()) -> str:
        """The fact clause: what each revision produced, and how many times.

        ``digested`` names the parts written as a digest rather than whole:
        ``"expression"``, ``"base"``, ``"head"``."""
        expression = (
            expression_digest(self.expression)
            if "expression" in digested
            else self.expression
        )
        pins = (
            "no base test, docstring or changelog pins either"
            if self.nothing_pins_it
            else "the base tree pins it at "
            + ", ".join(site for _value, site in self.specified_by[:2])
            + ", and this change moved it"
        )
        runs = (
            f"{self.head_runs}/{self.head_runs} and {self.base_runs}/{self.base_runs} "
            "runs each side"
        )
        difference = self.difference() if not {"base", "head"} & set(digested) else None
        if difference is not None:
            # D-234: name the element that moved, not two digests of the wholes.
            # The prose is as short as it honestly can be: two 120-character
            # elements leave the contract's 400 characters little room.
            absent = "(no element there)"
            counted = (
                f"{self.head_runs}/{self.head_runs} and {self.base_runs}/{self.base_runs} runs"
            )
            sides = (
                f"base and head {difference.kind}s of {difference.base_len}"
                if difference.base_len == difference.head_len
                else (
                    f"a base {difference.kind} of {difference.base_len} and a head "
                    f"{difference.kind} of {difference.head_len}"
                )
            )
            short_pins = "nothing in the base tree pins it" if self.nothing_pins_it else pins
            return (
                f"for {expression}, {sides} first differ at {difference.label} ({counted}): "
                f"base {difference.base or absent} → head {difference.head or absent}; "
                f"{short_pins}"
            )
        base_detail = (
            value_digest(self.base_detail) if "base" in digested else self.base_detail
        )
        head_detail = (
            value_digest(self.head_detail) if "head" in digested else self.head_detail
        )
        base = (
            f"raised {base_detail}" if self.base_kind == "exception" else f"returned {base_detail}"
        )
        head = (
            f"raises {head_detail}" if self.head_kind == "exception" else f"returns {head_detail}"
        )
        return f"for {expression}, the merge base {base} and head {head} ({runs}); {pins}"

    def digested_parts(self) -> tuple[str, ...]:
        """Which of the three quoted parts are written as digests.

        A part is quoted whole when it is inside its verbatim cap **and** the
        assembled line fits the contract. Otherwise parts are digested longest
        first until the line fits -- a different rendering of the same
        measurement, never a cut `repr` (D-142). An exception's type name is
        never digested: it is short by construction."""
        difference = self.difference()
        lengths = {
            "expression": len(self.expression),
            # D-234: in the element form the measured parts are the elements
            "base": (
                0
                if self.base_kind == "exception"
                else len(difference.base) if difference is not None else len(self.base_detail)
            ),
            "head": (
                0
                if self.head_kind == "exception"
                else len(difference.head) if difference is not None else len(self.head_detail)
            ),
        }
        caps = {
            "expression": EXPRESSION_VERBATIM_CHARS,
            "base": VALUE_VERBATIM_CHARS,
            "head": VALUE_VERBATIM_CHARS,
        }
        digested = [part for part, length in lengths.items() if length > caps[part]]
        remaining = sorted(
            (part for part in lengths if part not in digested),
            key=lambda part: -lengths[part],
        )
        while len(self._line(digested)) > MAX_LINE_CHARS and remaining:
            digested.append(remaining.pop(0))
        return tuple(digested)

    def _line(self, digested: Sequence[str]) -> str:
        return claim_line(
            "yellow",
            path=self.path,
            line=self.line,
            fact=self.sentence(digested=digested),
            evidence=f"note {self.note_id()}",
        )

    def measured_literals(self) -> tuple[str, ...]:
        """The spans of the rendered line that are measurements, not prose:
        the two observations as they appear in it."""
        digested = self.digested_parts()
        difference = self.difference() if not {"base", "head"} & set(digested) else None
        if difference is not None:
            return (difference.base, difference.head)
        return (
            value_digest(self.base_detail) if "base" in digested else self.base_detail,
            value_digest(self.head_detail) if "head" in digested else self.head_detail,
        )


def _type_of_repr(text: str) -> str:
    """The type a `repr` announces in its first characters -- a heuristic read
    of the recorded text, named as such, never a claim about the object."""
    stripped = text.lstrip()
    if not stripped:
        return "value"
    first = stripped[0]
    if first == "[":
        return "list"
    if first == "(":
        return "tuple"
    if first == "{":
        return "dict" if re.match(r"\{\s*['\"\w.-]+\s*:", stripped) else "set"
    if first in "'\"":
        return "str"
    if stripped.startswith("<class "):
        return "class"
    if first == "<":
        return re.match(r"<([\w.]+)", stripped).group(1).split(".")[-1]  # type: ignore[union-attr]
    call = re.match(r"([A-Za-z_][\w.]*)\(", stripped)
    if call:
        return call.group(1).split(".")[-1]
    if re.fullmatch(r"-?\d+", stripped):
        return "int"
    if re.fullmatch(r"-?\d+\.\d*(e-?\d+)?", stripped):
        return "float"
    if stripped in ("True", "False"):
        return "bool"
    if stripped == "None":
        return "NoneType"
    return "value"


def value_digest(detail: str) -> str:
    """`<type len=N sha256 hhhhhhhh>` for a recorded value: the type its `repr`
    announces, the length of the `repr`, and the first eight hex digits of its
    SHA-256, which an operator matches against the ledger row."""
    digest = hashlib.sha256(detail.encode("utf-8")).hexdigest()[:8]
    return f"<{_type_of_repr(detail)} len={len(detail)} sha256 {digest}>"


def expression_digest(expression: str) -> str:
    digest = hashlib.sha256(expression.encode("utf-8")).hexdigest()[:8]
    return f"the recorded call <expression len={len(expression)} sha256 {digest}>"


def render(note: ValueNote) -> str:
    """The one contract line this note is, when it is shown."""
    return note._line(note.digested_parts())


def admitted(note: ValueNote) -> ContractVerdict:
    """The contract's verdict on this note's line, with the two measured
    literals exempt from the banned-phrase rule and from nothing else."""
    return check(render(note), measured=note.measured_literals())


def anchored_in_tests(note: ValueNote) -> bool:
    """Would the line point an author at their own test?"""
    return TEST_PATH.search(note.path) is not None


def distinct(notes: Iterable[ValueNote]) -> list[ValueNote]:
    """One note per `(path, expression)`, the first kept: the same call
    recorded twice is one fact."""
    seen: set[tuple[str, str]] = set()
    kept: list[ValueNote] = []
    for note in notes:
        key = (note.path, note.expression)
        if key in seen:
            continue
        seen.add(key)
        kept.append(note)
    return kept


def visible(notes: Iterable[ValueNote]) -> list[ValueNote]:
    """The notes an author may be shown, in order: not in tests/, one per
    `(path, expression)`, and admitted by the contract."""
    return [
        note
        for note in distinct(notes)
        if not anchored_in_tests(note) and admitted(note).admitted
    ]


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
    # The coordinate is the candidate's anchor -- a changed line of the anchored
    # file. `intent.failing_assertion_line` is the line of the *generated test*
    # the head runs failed on (D-132), and D-218 paired it with the source path:
    # 13 of the 16 lines of the 2026-09-11 run pointed at a test-file line
    # number on a source file. The assertion line stays in the ledger row.
    return ValueNote(
        policy_version=VALUE_NOTE_POLICY_VERSION,
        path=intent.path,
        line=anchor_line,
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
