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
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from attest.certification.types import CertifiedFinding
from attest.review.finding_evidence import FindingEvidence, render_markdown
from attest.review.structural import CATEGORY as STRUCTURAL_CATEGORY
from attest.review.structural import StructuralNote

FINDING_ID_MARKER_PREFIX = "<!-- attest:finding-id:"
RECEIPT_LINE_PREFIX = "Receipt:"
BEHAVIOR_CHANGE_CLASS = "behavior_change"  # D-102
BEHAVIOR_CHANGE_PREFIX = "Behavior change (intent to confirm):"
# D-133: the green channel, partitioned from the red one at every level
STRUCTURAL_MARKER_PREFIX = "<!-- attest:structural:"
STRUCTURAL_PREFIX = "Structural (no defect claimed):"
STRUCTURAL_HEADING = (
    "Structural observations — measured, not reproduced; no defect is claimed:"
)
STRUCTURAL_ADVICE_HEADING = "Suggested fix (written by a model, not part of the claim):"
MAX_STRUCTURAL_COMMENTS = 2


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
) -> str:
    """Render only receipt-backed findings, in the caller's order; with
    ``evidence`` each finding is followed by its runnable test (item 7).

    Structural notes, when there are any, follow in their own section (D-133).
    The two sections never merge and the green one never borrows the red one's
    words: nothing there is "verified" and nothing there is a "finding"."""
    certified = _certified_only(findings)
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
    for note in _structural_only(structural)[:MAX_STRUCTURAL_COMMENTS]:
        if lines[-1] != "":
            lines.append("")
        lines.append(STRUCTURAL_HEADING)
        lines.append(f"- {STRUCTURAL_PREFIX} {_one_line(note.evidence)}")
        if note.advice:
            lines.append(f"  {STRUCTURAL_ADVICE_HEADING} {_one_line(note.advice)}")
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
    return [
        _structural_comment(note)
        for note in _structural_only(notes)[:MAX_STRUCTURAL_COMMENTS]
    ]


def _structural_only(notes: Sequence[StructuralNote]) -> list[StructuralNote]:
    if any(type(note) is not StructuralNote for note in notes):
        raise TypeError("the structural channel accepts only StructuralNote values")
    return list(notes)


def structural_member_id(note: StructuralNote) -> str:
    """The delivery journal identifies every author-visible comment. A green note
    has no receipt and no candidate, so it is identified by the pair of
    coordinates it is about -- which is unique per note and stable across runs."""
    finding = note.finding
    return (
        f"{finding.path_a}:{finding.line_a}|{finding.path_b}:{finding.line_b}"
    )


def _structural_comment(note: StructuralNote) -> dict[str, object]:
    finding = note.finding
    # anchor on the side this change touched; "both" and "a" anchor on a
    anchored_on_b = finding.changed_side == "b"
    path = finding.path_b if anchored_on_b else finding.path_a
    line = finding.line_b if anchored_on_b else finding.line_a
    parts = [
        f"{STRUCTURAL_MARKER_PREFIX}{structural_member_id(note)} -->",
        f"{STRUCTURAL_PREFIX} {note.evidence}",
        "",
        f"Category: {STRUCTURAL_CATEGORY}. This is a measurement over the two "
        "coordinates above, not a reproduction: no test was generated and no "
        "receipt backs it.",
    ]
    if note.advice:
        parts.extend(["", STRUCTURAL_ADVICE_HEADING, note.advice])
    return {"path": path, "line": line, "side": "RIGHT", "body": "\n".join(parts)}


def _certified_only(findings: Sequence[CertifiedFinding]) -> list[CertifiedFinding]:
    if any(type(finding) is not CertifiedFinding for finding in findings):
        raise TypeError("presentation accepts only CertifiedFinding values")
    return list(findings)


def _summary_line(finding: CertifiedFinding) -> str:
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    label = (
        f"{BEHAVIOR_CHANGE_PREFIX} "
        if receipt.evidence_class == BEHAVIOR_CHANGE_CLASS
        else ""
    )
    return (
        f"- {_finding_id_marker(receipt.candidate_id)} Finding ID: {receipt.candidate_id}; "
        f"{anchor.path}:{anchor.line} — {label}{_one_line(finding.claim)} "
        f"(receipt {receipt.provenance_digest[:12]})"
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
    parts = [
        _finding_id_marker(receipt.candidate_id),
        f"{BEHAVIOR_CHANGE_PREFIX} {finding.claim}" if behavior_change else finding.claim,
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
