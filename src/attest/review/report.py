"""Terminal report: verified findings first, unverified candidates after.

Only a ``CertifiedFinding`` is reported as a finding. Every other candidate is
listed as a drawer entry with its ranking score as information only; the
score is never speech authority. User-facing wording (owner item 10,
2026-09-03): verified / evidence / abstained / reproduction failed; the
statistical terms stay in the ledger and the decision log.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from attest.certification.types import CertifiedFinding
from attest.review.finding_evidence import FindingEvidence, render_text
from attest.review.gate import GateOutcome, GateResult
from attest.review.status import RunStatus


def _fmt_finding(
    idx: int, finding: CertifiedFinding, evidence: FindingEvidence | None = None
) -> str:
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    lines = [
        f"  {idx}. [{receipt.candidate_id}] {anchor.path}:{anchor.line}",
        f"     {finding.claim}",
        f"     verified:    the test failed on head {len(receipt.head_runs)}/"
        f"{len(receipt.head_runs)} times and passed on base {len(receipt.base_runs)}/"
        f"{len(receipt.base_runs)} times ({receipt.test_node})",
        f"     receipt:     {receipt.provenance_digest}",
    ]
    if evidence is not None:
        lines.append(render_text(evidence))
    return "\n".join(lines)


def _candidates(outcome: GateOutcome) -> list[GateResult]:
    return [*outcome.formal, *outcome.drawer_overflow, *outcome.drawer]


def render(
    outcome: GateOutcome,
    alpha: float,
    spend_usd: float,
    budget_usd: float,
    elapsed_s: float,
    deferred_reason: str | None = None,
    notes: list[str] | None = None,
    certified: Sequence[CertifiedFinding] = (),
    status: RunStatus | None = None,
    evidence: Mapping[str, FindingEvidence] | None = None,
) -> str:
    out: list[str] = []
    certified_ids = {finding.accepted_receipt.receipt.candidate_id for finding in certified}
    drawer = [
        result for result in _candidates(outcome) if result.finding.finding_id not in certified_ids
    ]
    n_certified = len(certified)
    n_drawer = len(drawer)
    n_discarded = len(outcome.discarded)
    n_total = n_certified + n_drawer + n_discarded

    if deferred_reason:
        out.append(f"DEFER: {deferred_reason}")

    if certified:
        out.append("verified findings (each backed by one accepted receipt):")
        for i, finding in enumerate(certified, 1):
            block = (evidence or {}).get(finding.accepted_receipt.receipt.candidate_id)
            out.append(_fmt_finding(i, finding, block))
    elif not deferred_reason:
        if n_total == 0:
            out.append("no candidates proposed — saying nothing.")
        else:
            out.append(
                f"checked {n_total} candidate(s); none was verified by a reproduction "
                "(a test that fails on head and passes on base) — abstained."
            )

    if drawer:
        out.append(
            f"unverified candidates ({len(drawer)}; ranked by internal score, "
            "not evidence; `attest stats --drawer` shows why each reproduction failed):"
        )
        for r in sorted(drawer, key=lambda r: r.wealth, reverse=True):
            f = r.finding
            out.append(f"  - [{f.finding_id}] {f.file}:{f.line} ({r.action}): {f.claim}")

    if status is not None:
        # operational status, not a finding: counts and failure reasons only,
        # never the content or location of an uncertified candidate
        out.append("run status:")
        out.extend(f"  {line}" for line in status.lines())

    for note in notes or []:
        out.append(f"note: {note}")

    out.append(
        f"spend ${spend_usd:.4f} of ${budget_usd:.2f} budget; {elapsed_s:.1f}s; "
        f"{n_total} candidate(s): {n_certified} verified, {n_drawer} unverified, "
        f"{n_discarded} discarded."
    )
    return "\n".join(out)
