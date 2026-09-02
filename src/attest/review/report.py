"""Terminal report: receipt-backed findings first, S/T-ranked candidates after.

Only a ``CertifiedFinding`` is reported as a finding. Every other candidate is
listed as a drawer entry with its S/T wealth as ranking information; that
wealth is never speech authority.
"""

from __future__ import annotations

from collections.abc import Sequence

from attest.certification.types import CertifiedFinding
from attest.review.gate import GateOutcome, GateResult
from attest.review.status import RunStatus


def _fmt_finding(idx: int, finding: CertifiedFinding) -> str:
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    lines = [
        f"  {idx}. [{receipt.candidate_id}] {anchor.path}:{anchor.line}",
        f"     {finding.claim}",
        f"     certified:   head FAIL {len(receipt.head_runs)}/{len(receipt.head_runs)}, "
        f"base PASS {len(receipt.base_runs)}/{len(receipt.base_runs)} ({receipt.test_node})",
        f"     receipt:     {receipt.provenance_digest}",
    ]
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
) -> str:
    out: list[str] = []
    threshold = 1.0 / alpha

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
        out.append("certified findings (each backed by one accepted receipt):")
        for i, finding in enumerate(certified, 1):
            out.append(_fmt_finding(i, finding))
    elif not deferred_reason:
        if n_total == 0:
            out.append("no candidates proposed — saying nothing.")
        else:
            out.append(
                f"checked {n_total} candidate(s); no findings cleared the evidence bar "
                "(an accepted differential receipt) — saying nothing."
            )

    if drawer:
        out.append(
            f"drawer ({len(drawer)} candidate(s) awaiting a receipt; "
            f"S/T wealth ranks only, threshold {threshold:.0f} is not speech):"
        )
        for r in sorted(drawer, key=lambda r: r.wealth, reverse=True):
            f = r.finding
            out.append(
                f"  - [{f.finding_id}] {f.file}:{f.line} wealth {r.wealth:.1f} "
                f"({r.action}): {f.claim}"
            )

    if status is not None:
        # operational status, not a finding: counts and failure reasons only,
        # never the content or location of an uncertified candidate
        out.append("run status:")
        out.extend(f"  {line}" for line in status.lines())

    for note in notes or []:
        out.append(f"note: {note}")

    out.append(
        f"spend ${spend_usd:.4f} of ${budget_usd:.2f} budget; {elapsed_s:.1f}s; "
        f"{n_total} candidate(s): {n_certified} certified, {n_drawer} in drawer, "
        f"{n_discarded} discarded."
    )
    return "\n".join(out)
