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

from collections.abc import Mapping, Sequence

from attest.certification.types import CertifiedFinding
from attest.review.finding_evidence import FindingEvidence, render_markdown
from attest.review.impact import ImpactNote
from attest.review.output_contract import LEVEL_MARKERS, claim_line, silence_line
from attest.review.output_contract import check as contract_check
from attest.review.output_contract import collapsed as contract_collapsed
from attest.review.structural import CATEGORY as STRUCTURAL_CATEGORY
from attest.review.structural import StructuralNote

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
    "Impact scope — counted over the call graph; no defect is claimed and no coverage "
    "was measured:"
)
IMPACT_MAX_COMMENTS = 2
IMPACT_MAX_CALLERS_LISTED = 8


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
    if not certified and not notes and not scope:
        # D-142: a wholly silent review owes exactly one line, and it says over
        # how many change units the silence holds.
        read, planned = units if units is not None else (0, 0)
        return silence_line(
            units_read=read,
            units_planned=planned,
            spend_usd=spend_usd,
            elapsed_s=elapsed_s,
        )
    lines = ["Review complete."]
    if certified:
        lines.append("Verified findings (each backed by a reproduction receipt):")
        for finding in certified:
            lines.append(_summary_line(finding))
            block = (evidence or {}).get(finding.accepted_receipt.receipt.candidate_id)
            if block is not None:
                lines.append("")
                lines.append(render_markdown(block))
                lines.append("")
    else:
        lines.append("No finding was verified by a reproduction; abstained.")
    for note in notes[:MAX_STRUCTURAL_COMMENTS]:
        if lines[-1] != "":
            lines.append("")
        lines.append(STRUCTURAL_HEADING)
        lines.append(structural_line(note))
        if note.advice:
            lines.append("")
            lines.append(contract_collapsed(note.advice, summary=STRUCTURAL_ADVICE_HEADING))
    for index, scoped in enumerate(scope[:IMPACT_MAX_COMMENTS]):
        if lines[-1] != "":
            lines.append("")
        if index == 0:
            lines.append(IMPACT_HEADING)
        lines.append(f"- {impact_line(scoped)}")
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


def structural_comments(notes: Sequence[StructuralNote]) -> list[dict[str, object]]:
    """D-133: at most two green comments per pull request, in the caller's order.

    Each is anchored on the coordinate this change touched, marked `structural`,
    and says in its first words that it claims no defect.
    """
    admitted = [note for note in _structural_only(notes) if _admits_note(note)]
    return [_structural_comment(note) for note in admitted[:MAX_STRUCTURAL_COMMENTS]]


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
    if note.advice:
        parts.extend(["", contract_collapsed(note.advice, summary=STRUCTURAL_ADVICE_HEADING)])
    return {"path": path, "line": line, "side": "RIGHT", "body": "\n".join(parts)}


def structural_line(note: StructuralNote, *, bullet: str = "- ") -> str:
    """One green note as one contract line (D-142).

    The claim is the deterministic measurement and nothing else; the model's
    paragraph never enters this line and lives collapsed below it."""
    return f"{bullet}{LEVEL_MARKERS['green']} {STRUCTURAL_PREFIX} {_one_line(note.evidence)}"


def impact_line(note: ImpactNote) -> str:
    """One yellow (a) note as one contract line (D-143, narrowed by D-145).

    Every clause is a count this level computed: how the interface moved, how
    many call sites name the function, and how many of those are named by no
    test. Both halves are always present -- the level does not speak otherwise --
    and the evidence coordinate is the first untested caller, which is the place
    the author would look first.
    """
    changed = note.changed
    definition = changed.definition
    moved = (
        f"`{definition.qualname}` changed signature"
        if changed.signature_changed
        else f"`{definition.qualname}` changed its return annotation"
    )
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


def impact_comments(notes: Sequence[ImpactNote]) -> list[dict[str, object]]:
    """The yellow (a) notes one pull request may show, each anchored on the
    changed function and each admitted by the format adjudicator (D-142)."""
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
        out.append(
            {
                "path": definition.path,
                "line": definition.line,
                "side": "RIGHT",
                "body": "\n".join(
                    [
                        f"{IMPACT_MARKER_PREFIX}{impact_member_id(note)} -->",
                        line,
                        "",
                        "Call sites, by name, in this repository:",
                        callers,
                        "",
                        "Static reachability over names: a caller reached only through a "
                        "registry or `getattr` is invisible here, so this says *named by no "
                        "test*, never *not covered*.",
                    ]
                ),
            }
        )
    return out


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
    under every red line: coordinates, the node that ran, and the two outcomes."""
    receipt = finding.accepted_receipt.receipt
    return (
        f"the generated test {receipt.test_node} fails on head in "
        f"{len(receipt.head_runs)}/{len(receipt.head_runs)} runs and passes on the "
        f"merge base in {len(receipt.base_runs)}/{len(receipt.base_runs)}"
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
    ]
    if evidence is not None:
        parts.extend(["", render_markdown(evidence)])
    body = "\n".join(parts)
    return {"path": anchor.path, "line": anchor.line, "side": "RIGHT", "body": body}


def _finding_id_marker(finding_id: str) -> str:
    return f"{FINDING_ID_MARKER_PREFIX}{finding_id} -->"


def _one_line(value: str) -> str:
    return " ".join(value.splitlines())
