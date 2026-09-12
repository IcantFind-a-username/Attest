"""GitHub-safe renderers for certified review results.

Every author-visible **finding** rendered here is a ``CertifiedFinding``, which
can only be constructed from a validator-accepted receipt. Operational status
(running, deferred) is rendered separately and never names a candidate.

D-133 adds the second author-visible channel, and keeps it apart from the first.
A **structural note** (mainline's green level) is not a finding: it claims no
defect, carries no receipt, and is rendered in its own section under its own
heading, marked `structural`. Its claim line is the deterministic sentence --
coordinates and a measure and nothing else -- and the model's paragraph, when
there is one, follows it under a separate "Suggested fix" heading, so a reader
can see at a glance which half a machine measured and which half a model wrote.
At most two reach one pull request.

D-142 adds the **output contract** over both channels: every author-visible line
is one line carrying a level marker, a `file:line` coordinate, one sentence of
fact and an evidence reference, adjudicated by `review.output_contract` with no
model in the path. A line that does not conform is not published -- for a
certified finding the deterministic sentence is published in its place, so
wording never silences evidence; for a green note, which has no receipt to fall
back on, the note is dropped. A wholly silent review says exactly one line, and
that line names the change units it read.

D-145 makes yellow (a) author-visible on the same terms: its own marker, its own
section, its own cap of two, and a rule narrow enough that on the 79 units it was
measured over it says nothing at all. A yellow note is a count over an abstract
syntax tree; it claims no defect, and when the level is silent nothing about it
reaches the author.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from typing import cast

from attest.certification.types import CertifiedFinding
from attest.review.finding_evidence import FindingEvidence, render_markdown
from attest.review.gate_note import GateNote
from attest.review.gate_note import admitted as gate_admitted
from attest.review.gate_note import render as gate_line
from attest.review.impact import CONDITION_ARITY, CONDITION_FANOUT, ImpactNote, fanout_of
from attest.review.output_contract import (
    ACTION_PREFIX,
    LEVEL_MARKERS,
    check_comment,
    claim_line,
    receipt_sentence,
    silence_line,
)
from attest.review.output_contract import check as contract_check
from attest.review.output_contract import collapsed as contract_collapsed
from attest.review.structural import CATEGORY as STRUCTURAL_CATEGORY
from attest.review.structural import StructuralNote
from attest.review.value_note import ValueNote
from attest.review.value_note import admitted as value_admitted
from attest.review.value_note import render as value_line

FINDING_ID_MARKER_PREFIX = "<!-- attest:finding-id:"
RECEIPT_LINE_PREFIX = "Receipt:"
BEHAVIOR_CHANGE_CLASS = "behavior_change"  # D-102
BEHAVIOR_CHANGE_PREFIX = "Behavior change (intent to confirm):"
# D-133: the green channel, partitioned from the red one at every level
STRUCTURAL_MARKER_PREFIX = "<!-- attest:structural:"
STRUCTURAL_PREFIX = "Structural (no defect claimed):"
STRUCTURAL_HEADING = "Structural observations — measured, not reproduced; no defect is claimed:"
STRUCTURAL_ADVICE_HEADING = "Suggested fix (written by a model, not part of the claim):"
MAX_STRUCTURAL_COMMENTS = 2
# D-143: yellow (a), the impact scope. Same cap as green, its own marker.
IMPACT_MARKER_PREFIX = "<!-- attest:impact:"
IMPACT_HEADING = (
    "Impact scope — counted over the call graph; no defect is claimed and no coverage was measured:"
)
IMPACT_MAX_COMMENTS = 2
# D-153: what a reader runs, one click below the line that claims it.
EVIDENCE_HEADING = "Reproduce it yourself — command, test and the six runs"
# Yellow's cap is shared by every yellow class: the author reads one yellow
# section, not two, and two notes is the whole of it however many levels spoke.
# (Yellow (b)'s two classes -- null/Optional, closed at 0 of 79 by D-169, and
# exception propagation, a shadow at 0 of 68 -- were deleted on 2026-09-11.)
# Owner instruction 4 of 2026-09-11: the value-class note (D-218), its own
# marker and its own section; it shares yellow's cap, after (a).
VALUE_MARKER_PREFIX = "<!-- attest:value:"
VALUE_HEADING = (
    "Observed behaviour changes — the same call run on both revisions; no defect "
    "is claimed and nothing in the base tree pins either value:"
)
YELLOW_MAX_COMMENTS = 2
IMPACT_MAX_CALLERS_LISTED = 8
# Owner instruction 5 of 2026-09-11: the gate level's yellow line. Its own
# marker and its own section (design §5: never inside red's, never counted in
# red's totals); at most one per pull request, and none when red published.
GATE_MARKER_PREFIX = "<!-- attest:gate:"
GATE_HEADING = "Gate — new code, nothing to compare against:"
# D-227: the one sentence the value line gains when the base-owned
# `intent_replies` switch is on. A reply is read by the next review and written
# to the ledger; nothing publishes or drawers on it.
REPLY_PROMPT = " Reply `intended` or `unintended` to record it."
GATE_DISCLAIMER = (
    "There is no base revision to compare against; this is not a claim that the change "
    "broke something that worked."
)


def render_running(candidate_count: int | None = None) -> str:
    """Render a status update without identifying any unverified candidate."""
    if candidate_count is None:
        return "Review running; candidates are under verification."
    return f"Review running; {candidate_count} candidates are under verification."


def render_deferred(reason: str) -> str:
    """Render the supplied deferral reason without review details."""
    return reason


def render_complete(
    findings: Sequence[CertifiedFinding],
    spend_usd: float,
    elapsed_s: float,
    evidence: Mapping[str, FindingEvidence] | None = None,
    structural: Sequence[StructuralNote] = (),
    units: tuple[int, int] | None = None,
    impact: Sequence[ImpactNote] = (),
    value_notes: Sequence[ValueNote] = (),
    gate_notes: Sequence[GateNote] = (),
    unverified: int = 0,
    executor_unavailable: str = "",
    unsupported_executor: int = 0,
    refusal: tuple[str, str] | None = None,
    ledger_url: str = "",
) -> str:
    """Render only receipt-backed findings, in the caller's order; with
    ``evidence`` each finding is followed by its runnable test (item 7).

    Structural notes, when there are any, follow in their own section (D-133),
    and yellow (a)'s impact notes in a third (D-145). The sections never merge
    and neither of the two lower ones borrows red's words: nothing there is
    "verified" and nothing there is a "finding".

    **A level with nothing to say contributes no line at all** -- there is no
    "no impact notes" line, because a level's silence is not a claim."""
    certified = _certified_only(findings)
    notes = [note for note in _structural_only(structural) if _admits_note(note)]
    scope = [note for note in _impact_only(impact) if contract_check(impact_line(note))]
    values = [note for note in _value_only(value_notes) if value_admitted(note)]
    # Every yellow class shares one cap, (a) first; the value-class note has
    # its own section because its claim has a different shape (a measurement
    # on two revisions, not a count over a call graph).
    yellow: list[ImpactNote | ValueNote] = [*scope, *values]
    yellow = yellow[:YELLOW_MAX_COMMENTS]
    # the gate line is not red and not counted with yellow's cap; zero when red
    # published anything (design §5: a receipt is strictly stronger)
    gates = [] if certified else [note for note in _gate_only(gate_notes) if gate_admitted(note)]
    if not certified and not notes and not yellow and not gates:
        # D-142: a wholly silent review owes exactly one line, and it says over
        # how many change units the silence holds.
        read, planned = units if units is not None else (0, 0)
        return silence_line(
            units_read=read,
            units_planned=planned,
            spend_usd=spend_usd,
            elapsed_s=elapsed_s,
            # D-177: an executor this host could not run judged nothing, so the
            # silence names the reason instead of claiming a clean bill of health
            unverified=unsupported_executor if executor_unavailable else unverified,
            executor_unavailable=executor_unavailable,
            # D-190: and a refusal names itself, above both of those
            refusal=refusal,
            ledger_url=ledger_url,
        )
    # D-204: the body is contract lines, the headings the product owns,
    # collapsed blocks and one spend footer. `Review complete.` and `No finding
    # was verified by a reproduction; abstained.` were preamble -- which
    # condition 7 forbids in those words -- published on every review and never
    # adjudicated, because `check` was applied to the lines inside the body and
    # never to the body itself. `check_summary` now decides the whole thing.
    lines: list[str] = []
    if certified:
        lines.append("Verified findings (each backed by a reproduction receipt):")
        for finding in certified:
            lines.append(_summary_line(finding))
            block = (evidence or {}).get(finding.accepted_receipt.receipt.candidate_id)
            if block is not None:
                # D-153: the claim is one line; everything a reader *runs* -- the
                # command, the generated test, the six run outcomes and the logs
                # -- lives one click below it. A summary whose first screen is
                # three pytest transcripts is a summary nobody reads to the end,
                # and the receipt line above is what the finding actually says.
                lines.append("")
                lines.append(
                    # the product's own evidence markdown, whose nested
                    # `Full logs` block is meant to be a block
                    contract_collapsed(
                        render_markdown(block), summary=EVIDENCE_HEADING, trusted=True
                    )
                )
                lines.append("")
    for note in notes[:MAX_STRUCTURAL_COMMENTS]:
        if lines and lines[-1] != "":
            lines.append("")
        lines.append(STRUCTURAL_HEADING)
        lines.append(structural_line(note))
        if note.advice:
            lines.append("")
            lines.append(contract_collapsed(note.advice, summary=STRUCTURAL_ADVICE_HEADING))
    graph_notes = [note for note in yellow if isinstance(note, ImpactNote)]
    value_shown = [note for note in yellow if isinstance(note, ValueNote)]
    for index, scoped in enumerate(graph_notes):
        if lines and lines[-1] != "":
            lines.append("")
        if index == 0:
            lines.append(IMPACT_HEADING)
        lines.append("- " + impact_line(scoped))
    for index, observed in enumerate(value_shown):
        if lines and lines[-1] != "":
            lines.append("")
        if index == 0:
            lines.append(VALUE_HEADING)
        lines.append("- " + value_line(observed))
    for index, reached in enumerate(gates):
        if lines and lines[-1] != "":
            lines.append("")
        if index == 0:
            lines.append(GATE_HEADING)
        lines.append("- " + gate_line(reached))
    lines.append(f"Spend ${spend_usd:.4f}; {elapsed_s:.1f}s.")
    return "\n".join(lines)


def inline_comments(
    findings: Sequence[CertifiedFinding],
    evidence: Mapping[str, FindingEvidence] | None = None,
) -> list[dict[str, object]]:
    """Build the top-three GitHub review comments, in the caller's order."""
    return [
        _inline_comment(
            finding, (evidence or {}).get(finding.accepted_receipt.receipt.candidate_id)
        )
        for finding in _certified_only(findings)[:3]
    ]


def structural_comments(
    notes: Sequence[StructuralNote],
    changed_lines: Mapping[str, Collection[int]] | None = None,
) -> list[dict[str, object]]:
    """D-133: at most two green comments per pull request, in the caller's order.

    Each is anchored on the coordinate this change touched, marked `structural`,
    and says in its first words that it claims no defect.

    D-147: with ``changed_lines`` a note whose anchor is not a line the diff
    changed produces **no inline comment**. GitHub refuses a review comment on a
    line outside the diff, and it refuses the *whole review* -- so one
    unanchorable green note used to take every other comment down with it. The
    note is not lost: it still appears in the summary, which is not anchored.
    """
    admitted = [note for note in _structural_only(notes) if _admits_note(note)]
    out: list[dict[str, object]] = []
    for note in admitted[:MAX_STRUCTURAL_COMMENTS]:
        comment = _structural_comment(note)
        if _anchored(comment, changed_lines) and check_comment(str(comment["body"])):
            out.append(comment)
    return out


def _anchored(
    comment: Mapping[str, object], changed_lines: Mapping[str, Collection[int]] | None
) -> bool:
    """Is this comment placed on a line the diff changed? (D-147)

    ``None`` means the caller did not supply the diff -- every offline renderer
    and every test that builds comments without a repository -- and then nothing
    is filtered, because a filter with no data is a silent drop."""
    if changed_lines is None:
        return True
    lines = changed_lines.get(str(comment["path"]))
    if not lines:
        return False
    return int(cast(int, comment["line"])) in lines


def _structural_only(notes: Sequence[StructuralNote]) -> list[StructuralNote]:
    if any(type(note) is not StructuralNote for note in notes):
        raise TypeError("the structural channel accepts only StructuralNote values")
    return list(notes)


def structural_member_id(note: StructuralNote) -> str:
    """The delivery journal identifies every author-visible comment. A green note
    has no receipt and no candidate, so it is identified by the pair of
    coordinates it is about -- which is unique per note and stable across runs."""
    finding = note.finding
    return f"{finding.path_a}:{finding.line_a}|{finding.path_b}:{finding.line_b}"


def _structural_comment(note: StructuralNote) -> dict[str, object]:
    finding = note.finding
    # anchor on the side this change touched; "both" and "a" anchor on a
    anchored_on_b = finding.changed_side == "b"
    path = finding.path_b if anchored_on_b else finding.path_a
    line = finding.line_b if anchored_on_b else finding.line_a
    parts = [
        f"{STRUCTURAL_MARKER_PREFIX}{structural_member_id(note)} -->",
        structural_line(note, bullet=""),
        "",
        f"Category: {STRUCTURAL_CATEGORY}. This is a measurement over the two "
        "coordinates above, not a reproduction: no test was generated and no "
        "receipt backs it.",
    ]
    # D-178: green's currency is the pair. The measure does not say which copy
    # should survive, so the clause names both and leaves that to the author.
    parts.extend(
        [
            "",
            f"{ACTION_PREFIX} keep one of `{finding.path_a}:{finding.line_a}` and "
            f"`{finding.path_b}:{finding.line_b}`, and call it from the other.",
        ]
    )
    if note.advice:
        parts.extend(["", contract_collapsed(note.advice, summary=STRUCTURAL_ADVICE_HEADING)])
    return {"path": path, "line": line, "side": "RIGHT", "body": "\n".join(parts)}


def structural_line(note: StructuralNote, *, bullet: str = "- ") -> str:
    """One green note as one contract line (D-142).

    The claim is the deterministic measurement and nothing else; the model's
    paragraph never enters this line and lives collapsed below it."""
    return f"{bullet}{LEVEL_MARKERS['green']} {STRUCTURAL_PREFIX} {_one_line(note.evidence)}"


def impact_line(note: ImpactNote) -> str:
    """One yellow (a) note as one contract line (D-143, D-145, widened by D-150).

    Every clause is a count this level computed, and which counts appear depends
    on the condition that fired:

    - **a1/a2** how the interface moved, how many call sites name the function,
      and how many of those are named by no test. The evidence coordinate is the
      first untested caller -- where the author would look first.
    - **a3** how many call sites pass fewer positional arguments than the
      function now takes. This one names no coverage at all, because the claim
      does not rest on any: the evidence coordinate is the first broken call.
    - **a4** how many call sites in how many files, and that no test names the
      function. The evidence coordinate is the first call site: with no test
      naming the function there is no untested *caller* to point at, and the
      fact the author acts on is the fan-out.
    """
    changed = note.changed
    definition = changed.definition
    if note.condition == CONDITION_ARITY:
        witness = note.arity_breaks[0]
        fact = (
            f"`{definition.qualname}` gained a required parameter; "
            f"{len(note.arity_breaks)} call site(s) pass fewer than "
            f"{definition.required} positional argument(s)"
        )
        return claim_line(
            "yellow",
            path=definition.path,
            line=definition.line,
            fact=fact,
            evidence=f"{witness.path}:{witness.line}",
        )
    if note.condition == CONDITION_FANOUT:
        sites, files = fanout_of(note.callers)
        witness = note.callers[0].site
        return claim_line(
            "yellow",
            path=definition.path,
            line=definition.line,
            fact=(
                f"`{definition.qualname}` changed; {sites} call site(s) in {files} file(s) "
                "name it and no test names it"
            ),
            evidence=f"{witness.path}:{witness.line}",
        )
    if changed.signature_changed:
        moved = f"`{definition.qualname}` changed signature"
    elif changed.added_raise:
        moved = f"`{definition.qualname}` raises an exception type the base did not"
    else:
        moved = f"`{definition.qualname}` changed its return annotation"
    fact = (
        f"{moved}; {len(note.callers)} call site(s) name it, "
        f"{len(note.untested)} of them named by no test"
    )
    witness = note.untested[0].site
    return claim_line(
        "yellow",
        path=definition.path,
        line=definition.line,
        fact=fact,
        evidence=f"{witness.path}:{witness.line}",
    )


def impact_member_id(note: ImpactNote) -> str:
    """The delivery journal identifies every author-visible comment. A yellow (a)
    note has no receipt and no candidate, so it is identified by the coordinate
    of the function it is about -- unique per note within one pull request."""
    definition = note.changed.definition
    return f"{definition.path}:{definition.line}"


def impact_comments(
    notes: Sequence[ImpactNote],
    changed_lines: Mapping[str, Collection[int]] | None = None,
) -> list[dict[str, object]]:
    """The yellow (a) notes one pull request may show, each anchored on a line
    the diff changed and each admitted by the format adjudicator (D-142).

    The *sentence* names the function's `def` line, which is its identity; the
    *comment* is placed on the first changed line inside it, because a `def`
    line is often only context in the hunk and GitHub refuses a comment there
    (D-147). ``changed_lines``, when supplied, is the last check on that."""
    out: list[dict[str, object]] = []
    for note in _impact_only(notes)[:IMPACT_MAX_COMMENTS]:
        line = impact_line(note)
        if not contract_check(line):
            continue
        definition = note.changed.definition
        callers = "\n".join(
            f"- {caller.site.path}:{caller.site.line}"
            + ("" if caller.named_by_test else " — named by no test")
            for caller in note.callers[:IMPACT_MAX_CALLERS_LISTED]
        )
        untested = next(
            (caller for caller in note.callers if not caller.named_by_test), None
        )
        # D-178: yellow's currency is the caller. Two things close this note and
        # the level does not choose between them; it names both and the place.
        target = (
            f"`{untested.site.path}:{untested.site.line}`"
            if untested is not None
            else f"`{definition.path}:{definition.line}`"
        )
        action = (
            f"{ACTION_PREFIX} add a test that names {target}, or change the caller there to "
            f"match the new interface."
        )
        comment = {
            "path": definition.path,
            "line": note.changed.anchor_line or definition.line,
            "side": "RIGHT",
            "body": "\n".join(
                [
                    f"{IMPACT_MARKER_PREFIX}{impact_member_id(note)} -->",
                    line,
                    "",
                    # D-174 made a call site the thing a name **resolves to**;
                    # this copy said "by name", which describes the rule the
                    # product stopped running.
                    "Call sites that resolve to this definition:",
                    callers,
                    "",
                    "Resolved statically: a call reached only through inheritance, a "
                    "decorator, a package re-export, a variable or `getattr` does not "
                    "resolve and is not listed, so this says *named by no test*, never "
                    "*not covered*.",
                    "",
                    action,
                ]
            ),
        }
        if _anchored(comment, changed_lines) and check_comment(str(comment["body"])):
            out.append(comment)
    return out


def value_comments(
    notes: Sequence[ValueNote],
    changed_lines: Mapping[str, Collection[int]] | None = None,
    *,
    ask_for_reply: bool = False,
) -> list[dict[str, object]]:
    """The value-class notes one pull request may show, each anchored on the
    failing assertion's line and each admitted by the format adjudicator with
    its two measured literals exempt from the banned-phrase rule (owner
    instruction 4 of 2026-09-11).

    The collapsed block carries what the line could not: the whole expression
    and both observations as recorded (less an object's ` at 0x…` address,
    D-235 c; the ledger keeps it), the drawer's own reason, and what the intent
    clause found pinned. The action clause names both ways to close it,
    because the level does not choose between them. With ``ask_for_reply``
    (D-227: the base-owned `intent_replies` switch) the clause ends by asking
    the author to reply `intended` or `unintended`, which the next review
    records to the ledger and to nowhere else."""
    out: list[dict[str, object]] = []
    for note in _value_only(notes)[:YELLOW_MAX_COMMENTS]:
        if not value_admitted(note):
            continue
        line = value_line(note)
        base = "raised" if note.base_kind == "exception" else "returned"
        head = "raises" if note.head_kind == "exception" else "returns"
        pinned = (
            "\n".join(f"- {value} is pinned at {site}" for value, site in note.specified_by)
            or "- nothing in the base tree pins either value"
        )
        detail = (
            f"Expression: `{note.expression}`\n\n"
            f"Merge base {base}, {note.base_runs}/{note.base_runs} runs:\n\n"
            f"```\n{note.base_shown}\n```\n\n"
            f"Head {head}, {note.head_runs}/{note.head_runs} runs:\n\n"
            f"```\n{note.head_shown}\n```\n\n"
            f"What the intent clause found:\n{pinned}\n\n"
            f"Why this is not a red finding: {note.drawer_reason}"
        )
        comment = {
            "path": note.path,
            "line": note.line,
            "side": "RIGHT",
            "body": "\n".join(
                [
                    f"{VALUE_MARKER_PREFIX}{value_member_id(note)} -->",
                    line,
                    "",
                    contract_collapsed(
                        detail, summary="The two observations, verbatim, and the drawer's reason"
                    ),
                    "",
                    f"{ACTION_PREFIX} if the new value is intended, add a test that pins it at "
                    f"`{note.path}:{note.line}`; otherwise restore what the merge base "
                    f"{base} there."
                    + (REPLY_PROMPT if ask_for_reply else ""),
                ]
            ),
        }
        if _anchored(comment, changed_lines) and check_comment(str(comment["body"])):
            out.append(comment)
    return out


def gate_comments(
    notes: Sequence[GateNote],
    changed_lines: Mapping[str, Collection[int]] | None = None,
) -> list[dict[str, object]]:
    """The gate line as an inline comment, anchored on the **added line** the
    exception was raised from (the caller's line is not in the diff, by
    construction). The collapsed block carries the design's own disclaimer and
    the three coordinates; the action names both ways to close it."""
    out: list[dict[str, object]] = []
    for note in _gate_only(notes)[:1]:
        if not gate_admitted(note):
            continue
        detail = (
            f"{GATE_DISCLAIMER}\n\n"
            f"- caller: `{note.call_site}` (`{note.caller}`), a line the change did not add\n"
            f"- added line: `{note.path}:{note.origin_line}`\n"
            f"- exception: `{note.exception_type}`, {note.runs}/{note.repeats} runs agreeing\n"
            f"- the reproduction entered with `{note.entry}`; a pre-existing test of the "
            "same caller passed in the same image"
        )
        comment = {
            "path": note.path,
            "line": note.origin_line,
            "side": "RIGHT",
            "body": "\n".join(
                [
                    f"{GATE_MARKER_PREFIX}{gate_member_id(note)} -->",
                    gate_line(note),
                    "",
                    contract_collapsed(detail, summary="What was witnessed, and what was not"),
                    "",
                    f"{ACTION_PREFIX} handle `{note.exception_type}` at "
                    f"`{note.path}:{note.origin_line}`, or reject that input at "
                    f"`{note.call_site}` before it reaches the new code.",
                ]
            ),
        }
        if _anchored(comment, changed_lines) and check_comment(str(comment["body"])):
            out.append(comment)
    return out


def gate_member_id(note: GateNote) -> str:
    return note.note_id()


def _gate_only(notes: Sequence[GateNote]) -> list[GateNote]:
    if any(type(note) is not GateNote for note in notes):
        raise TypeError("the gate channel accepts only GateNote values")
    return list(notes)


def value_member_id(note: ValueNote) -> str:
    """A value-class note carries no receipt; the journal identifies it by the
    note's own digest, which is what the line ends in."""
    return note.note_id()


def _value_only(notes: Sequence[ValueNote]) -> list[ValueNote]:
    if any(type(note) is not ValueNote for note in notes):
        raise TypeError("the value channel accepts only ValueNote values")
    return list(notes)


def _impact_only(notes: Sequence[ImpactNote]) -> list[ImpactNote]:
    if any(type(note) is not ImpactNote for note in notes):
        raise TypeError("the impact channel accepts only ImpactNote values")
    return list(notes)


def _admits_note(note: StructuralNote) -> bool:
    """Format non-conformance is not publication (D-142). A green note has no
    receipt to fall back on, so a line that does not conform is dropped whole."""
    return bool(contract_check(structural_line(note)))


def _certified_only(findings: Sequence[CertifiedFinding]) -> list[CertifiedFinding]:
    if any(type(finding) is not CertifiedFinding for finding in findings):
        raise TypeError("presentation accepts only CertifiedFinding values")
    return list(findings)


def _summary_line(finding: CertifiedFinding) -> str:
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    label = f"{BEHAVIOR_CHANGE_PREFIX} " if receipt.evidence_class == BEHAVIOR_CHANGE_CLASS else ""
    head = (
        f"- {_finding_id_marker(receipt.candidate_id)} {LEVEL_MARKERS['red']} "
        f"Finding ID: {receipt.candidate_id}; {anchor.path}:{anchor.line} — "
    )
    tail = f" (receipt {receipt.provenance_digest[:12]})"
    line = f"{head}{label}{_one_line(finding.claim)}{tail}"
    if contract_check(line):
        return line
    # D-142: a certified finding is never silenced by its phrasing. The claim
    # the model wrote did not conform, so the receipt states the finding itself.
    return f"{head}{label}{_receipt_sentence(finding)}{tail}"


def _receipt_sentence(finding: CertifiedFinding) -> str:
    """What the receipt says on its own, with no model in it. This is the floor
    under every red line: coordinates, the node that ran, and the two outcomes.
    One sentence for every renderer (D-235 d): `attest.review.report` uses it too."""
    receipt = finding.accepted_receipt.receipt
    return receipt_sentence(
        test_node=receipt.test_node,
        head_runs=len(receipt.head_runs),
        base_runs=len(receipt.base_runs),
    )


def _inline_comment(
    finding: CertifiedFinding, evidence: FindingEvidence | None = None
) -> dict[str, object]:
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    behavior_change = receipt.evidence_class == BEHAVIOR_CHANGE_CLASS
    runs = (
        f"the generated test failed on head in {len(receipt.head_runs)}/"
        f"{len(receipt.head_runs)} runs and passed on the merge base in "
        f"{len(receipt.base_runs)}/{len(receipt.base_runs)} runs."
    )
    label = f"{BEHAVIOR_CHANGE_PREFIX} " if behavior_change else ""
    claim_head = f"{LEVEL_MARKERS['red']} {anchor.path}:{anchor.line} — {label}"
    claim_tail = f" (receipt {receipt.provenance_digest[:12]})"
    claim = f"{claim_head}{_one_line(finding.claim)}{claim_tail}"
    if not contract_check(claim):
        claim = f"{claim_head}{_receipt_sentence(finding)}{claim_tail}"
    parts = [
        _finding_id_marker(receipt.candidate_id),
        claim,
        f"Finding ID: {receipt.candidate_id}",
        (
            # D-102: the published words say exactly what the receipt proves
            f"Verified behavior change: {runs} This change rejects an input the merge "
            "base accepted; the input appears in the base tree's own tests, fixtures or "
            "documentation, so the rejection is reported for you to confirm."
            if behavior_change
            else f"Verified: {runs}"
        ),
        f"Test: {receipt.test_node}",
        f"{RECEIPT_LINE_PREFIX} {receipt.provenance_digest}",
        # D-178: red's currency is the reproduction. Both halves are the
        # receipt's own strings, so this clause can never be the thing that
        # suppresses a certified finding.
        (
            f"{ACTION_PREFIX} reproduce it — `{_one_line(evidence.command)}` — then check the "
            f"receipt offline with `{_one_line(evidence.verify_command)}`."
            if evidence is not None
            else (
                f"{ACTION_PREFIX} reproduce it — run `{receipt.test_node}` on this head and on "
                f"the merge base — then check the receipt offline with "
                f"`attest verify --bundle <this run's evidence bundle> --require-seal`."
            )
        ),
    ]
    if evidence is not None:
        parts.extend(["", render_markdown(evidence)])
    body = "\n".join(parts)
    return {"path": anchor.path, "line": anchor.line, "side": "RIGHT", "body": body}


def _finding_id_marker(finding_id: str) -> str:
    return f"{FINDING_ID_MARKER_PREFIX}{finding_id} -->"


def _one_line(value: str) -> str:
    return " ".join(value.splitlines())
