"""Terminal report: at most 3 formal findings, each with clickable evidence."""

from __future__ import annotations

from attest.review.gate import GateOutcome, GateResult


def _fmt_finding(idx: int, r: GateResult) -> str:
    f = r.finding
    lines = [
        f"  {idx}. [{f.finding_id}] {f.file}:{f.line}  (wealth {r.wealth:.1f})",
        f"     {f.claim}",
        f"     breaks when: {f.failure_scenario}",
        f"     check it:    {f.falsification_plan}",
        "     evidence:    "
        + "; ".join(f"{p.channel} x{p.lr:.2f} ({p.detail})" for p in r.purchases),
    ]
    return "\n".join(lines)


def render(
    outcome: GateOutcome,
    alpha: float,
    spend_usd: float,
    budget_usd: float,
    elapsed_s: float,
    deferred_reason: str | None = None,
    notes: list[str] | None = None,
) -> str:
    out: list[str] = []
    threshold = 1.0 / alpha

    n_surfaced = len(outcome.formal) + len(outcome.drawer_overflow)
    n_drawer = len(outcome.drawer)
    n_discarded = len(outcome.discarded)
    n_total = n_surfaced + n_drawer + n_discarded

    if deferred_reason:
        out.append(f"DEFER: {deferred_reason}")

    if outcome.formal:
        out.append(f"findings (wealth >= {threshold:.0f}, alpha={alpha}):")
        for i, r in enumerate(outcome.formal, 1):
            out.append(_fmt_finding(i, r))
    elif not deferred_reason:
        if n_total == 0:
            out.append("no candidates proposed — saying nothing.")
        else:
            out.append(
                f"checked {n_total} candidate(s); no findings cleared the evidence bar "
                f"(wealth >= {threshold:.0f}) — saying nothing."
            )

    extra = outcome.drawer_overflow + outcome.drawer
    if extra:
        out.append(f"drawer ({len(extra)} candidate(s) below the bar or beyond the cap):")
        for r in sorted(extra, key=lambda r: r.wealth, reverse=True):
            f = r.finding
            out.append(
                f"  - [{f.finding_id}] {f.file}:{f.line} wealth {r.wealth:.1f} "
                f"({r.action}): {f.claim}"
            )

    for note in notes or []:
        out.append(f"note: {note}")

    out.append(
        f"spend ${spend_usd:.4f} of ${budget_usd:.2f} budget; {elapsed_s:.1f}s; "
        f"{n_total} candidate(s): {n_surfaced} surfaced, {n_drawer} in drawer, "
        f"{n_discarded} discarded."
    )
    return "\n".join(out)
