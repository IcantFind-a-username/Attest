"""GitHub-safe renderers for certified review results.

Every author-visible finding rendered here is a ``CertifiedFinding``, which can
only be constructed from a validator-accepted receipt. Operational status
(running, deferred) is rendered separately and never names a candidate.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from attest.certification.types import CertifiedFinding
from attest.review.finding_evidence import FindingEvidence, render_markdown

FINDING_ID_MARKER_PREFIX = "<!-- attest:finding-id:"
RECEIPT_LINE_PREFIX = "Receipt:"


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
) -> str:
    """Render only receipt-backed findings, in the caller's order; with
    ``evidence`` each finding is followed by its runnable test (item 7)."""
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


def _certified_only(findings: Sequence[CertifiedFinding]) -> list[CertifiedFinding]:
    if any(type(finding) is not CertifiedFinding for finding in findings):
        raise TypeError("presentation accepts only CertifiedFinding values")
    return list(findings)


def _summary_line(finding: CertifiedFinding) -> str:
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    return (
        f"- {_finding_id_marker(receipt.candidate_id)} Finding ID: {receipt.candidate_id}; "
        f"{anchor.path}:{anchor.line} — {_one_line(finding.claim)} "
        f"(receipt {receipt.provenance_digest[:12]})"
    )


def _inline_comment(
    finding: CertifiedFinding, evidence: FindingEvidence | None = None
) -> dict[str, object]:
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    parts = [
        _finding_id_marker(receipt.candidate_id),
        finding.claim,
        f"Finding ID: {receipt.candidate_id}",
        "Verified: the generated test failed on head in "
        f"{len(receipt.head_runs)}/{len(receipt.head_runs)} runs and passed on the "
        f"merge base in {len(receipt.base_runs)}/{len(receipt.base_runs)} runs.",
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
