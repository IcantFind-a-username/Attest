"""Terminal report: the four levels, one line each, then one line of accounting.

Only a ``CertifiedFinding`` is reported as a finding. Every other candidate is
listed as a drawer entry with its ranking score as information only; the
score is never speech authority. User-facing wording (owner item 10,
2026-09-03): verified / evidence / abstained / reproduction failed; the
statistical terms stay in the ledger and the decision log.

D-152 makes the local report obey the same contract the pull-request comment
does (D-142): every author-visible claim is **one line** carrying a level
marker, a coordinate, one sentence of fact and its evidence, and the levels are
printed in the order red, gate, yellow, green -- so a developer reading a
terminal and a reviewer reading a comment are reading the same four sentences.

Two things the comment does not owe, and the terminal does:

- **the accounting line**, always last and always present: how many change
  units were read of how many, how many candidates there were, how many are in
  the drawer, and *why* they are, as a distribution. A silence over one of
  thirteen units and a silence over thirteen of thirteen are different claims.
- **``--explain``**, which prints one line per silent candidate: its
  coordinate and the reason the drawer holds it. It is off by default because a
  drawer reason is not a claim about the code, and it is available because
  "nothing found" without a reason is not a report.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence

from attest.certification.types import CertifiedFinding
from attest.review.finding_evidence import FindingEvidence, render_text
from attest.review.gate import GateOutcome, GateResult
from attest.review.output_contract import claim_line, silence_line
from attest.review.status import RunStatus


def _fmt_finding(
    idx: int, finding: CertifiedFinding, evidence: FindingEvidence | None = None
) -> str:
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    label = (
        "behavior change (intent to confirm): "
        if receipt.evidence_class == "behavior_change"
        else ""
    )
    lines = [
        f"  {idx}. [{receipt.candidate_id}] {anchor.path}:{anchor.line}",
        f"     {label}{finding.claim}",
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


DRAWER_REASON_PREFIXES = (
    # The reason strings the drawer carries, reduced to the class a distribution
    # is worth counting by. Longest first: `probe deferred` must not be counted
    # as `probe refused`'s sibling by a prefix that matches both.
    ("intent: intent stated in the change itself", "intent-stated-in-diff"),
    ("intent: behavior change confirmed", "behavior-change-intent-unknown"),
    ("intent: value change confirmed", "value-change-intent-unknown"),
    ("intent: constant change confirmed", "constant-change-intent-unknown"),
    ("intent:", "intent-other"),
    ("probe deferred", "probe-deferred"),
    ("probe refused", "probe-refused"),
    ("probe reported no observation", "probe-no-observation"),
    ("probe replay failed", "probe-replay-failed-on-base"),
    ("probe ", "probe-other"),
    ("generation failed: BudgetExceeded", "budget-exhausted"),
    ("generation failed", "generation-failed"),
    ("unfaithful generated test", "unfaithful-reproduction"),
    ("isolation backend unavailable", "host-blocked"),
    ("collection deferred", "host-blocked"),
    ("executor failure", "host-blocked"),
    ("shared verification deadline", "deadline"),
    ("pytest passed on head", "not-reproduced-on-head"),
    ("ineligible", "ineligible"),
)


def drawer_reason_class(reason: str) -> str:
    """The class a drawer reason belongs to, for the accounting line's histogram.

    `no-reproduction-bought` is the honest name for the empty string, and it is
    the largest class on ordinary traffic: a candidate that never reached
    verification has no verification reason to record, because the ranking never
    put it in a position for a reproduction to be bought. Calling that
    "unrecorded" reads like a bookkeeping failure; it is a decision."""
    text = (reason or "").strip()
    for prefix, name in DRAWER_REASON_PREFIXES:
        if text.startswith(prefix):
            return name
    return "other" if text else "no-reproduction-bought"


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
    *,
    impact: Sequence[object] = (),
    nullability: Sequence[object] = (),
    structural: Sequence[object] = (),
    gate: Sequence[str] = (),
    explain: bool = False,
    reasons: Mapping[str, str] | None = None,
) -> str:
    from attest.github.presentation import (
        impact_line,
        nullability_line,
        structural_line,
    )

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

    # --- the four levels, red first, one contract line each -----------------
    spoke = False
    for finding in certified:
        out.append(_certified_line(finding))
        spoke = True
        block = (evidence or {}).get(finding.accepted_receipt.receipt.candidate_id)
        if block is not None:
            out.append(render_text(block))
    for line in gate:
        out.append(line)
        spoke = True
    for note in impact:
        out.append(impact_line(note))  # type: ignore[arg-type]
        spoke = True
    for note in nullability:
        out.append(nullability_line(note))  # type: ignore[arg-type]
        spoke = True
    for note in structural:
        # no bullet: the terminal is a list of lines, not a markdown list, and a
        # leading "- " puts a character before the level marker that the contract
        # says begins the line
        out.append(structural_line(note, bullet=""))  # type: ignore[arg-type]
        spoke = True
    if not spoke and not deferred_reason and status is not None:
        out.append(
            silence_line(
                units_read=status.units_read,
                units_planned=status.units_planned or status.units_read,
                spend_usd=spend_usd,
                elapsed_s=elapsed_s,
            )
        )

    # --- --explain: one line per silent candidate, with the drawer's reason --
    if explain and drawer:
        out.append("silent candidates, with the reason the drawer holds each:")
        for result in sorted(drawer, key=lambda r: r.wealth, reverse=True):
            silent = result.finding
            reason = (reasons or {}).get(silent.finding_id, "")
            out.append(
                f"  [{silent.finding_id}] {silent.file}:{silent.line} — "
                f"{drawer_reason_class(reason)}" + (f": {reason}" if reason else "")
            )

    for note in notes or []:
        out.append(f"note: {note}")

    # --- the accounting line, always last -----------------------------------
    read = status.units_read if status is not None else 0
    planned = (status.units_planned or status.units_read) if status is not None else 0
    histogram = Counter(
        drawer_reason_class((reasons or {}).get(r.finding.finding_id, "")) for r in drawer
    )
    distribution = ", ".join(f"{name} {count}" for name, count in sorted(histogram.items()))
    out.append(
        f"read {read}/{planned} units, candidates {n_total}, drawer {n_drawer}"
        + (f" ({distribution})" if distribution else "")
        + f"; verified {n_certified}, discarded {n_discarded}; "
        f"spend ${spend_usd:.4f} of ${budget_usd:.2f}; {elapsed_s:.1f}s."
    )
    return "\n".join(out)


def _certified_line(finding: CertifiedFinding) -> str:
    """One certified finding as one D-142 contract line, with its receipt as evidence."""
    receipt = finding.accepted_receipt.receipt
    anchor = finding.anchors[0]
    label = (
        "behavior change (intent to confirm): "
        if receipt.evidence_class == "behavior_change"
        else ""
    )
    return claim_line(
        "red",
        path=anchor.path,
        line=anchor.line,
        fact=f"{label}{finding.claim}",
        evidence=f"receipt {receipt.provenance_digest[:12]}",
    )
