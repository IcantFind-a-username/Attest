#!/usr/bin/env python3
"""Backfill the D-063 pricing instrument onto every per-candidate record we hold.

The instrument asks one question per candidate: did multiplying the purchased
evidence channels together decide anything the strongest single purchased
channel would not have decided on its own? It changes nothing; it records.

Three sources, none of which needs a model call or an execution:

1. **The whole reachable channel grid.** The factory tables are frozen, so the
   set of wealths any candidate can ever hold is finite and can be enumerated
   exhaustively. This answers the question for every candidate any run at these
   constants could produce, which subsumes the specific runs below.
2. **The 26 candidates of the 2026-09-01 history counterfactual**, whose S, T
   and final wealth are recorded per candidate.
3. **The four findings D-059 surfaced**, each of which purchased V after S.
"""

from __future__ import annotations

import argparse
import json
from itertools import product
from pathlib import Path

from attest.benchmark.artifacts import write_canonical_json
from attest.core.betting import decide
from attest.review.channels import S_CAP, T_CAP, V_CAP, V_FAILED, VOTE_LR, tier0_lr

ALPHA = 0.1
COUNTERFACTUAL = Path(
    "docs/acceptance/evidence/2026-09-01-wave5-history-counterfactual/result.json"
)
D059_SURFACED = ("fdbff9370c", "b1e7f57dc2", "ed1d3ea89b", "20d686ba82")


def _changed(wealth: float, lrs: tuple[float, ...], alpha: float) -> bool:
    return decide(wealth, alpha) != decide(max(lrs, default=1.0), alpha)


def _grid(alpha: float) -> dict[str, object]:
    """Every purchasable channel combination the frozen tables allow."""
    s_values = sorted(set(VOTE_LR))
    t_values = sorted({1.0, tier0_lr(1), tier0_lr(2)})
    v_values: tuple[float | None, ...] = (None, V_CAP, V_FAILED)
    rows = []
    changed = 0
    for s, t, v in product(s_values, t_values, v_values):
        lrs = [s]
        wealth = s
        if t > 1.0:
            lrs.append(t)
            wealth *= t
        if v is not None:
            lrs.append(v)
            wealth *= v
        differs = _changed(wealth, tuple(lrs), alpha)
        changed += differs
        rows.append(
            {
                "S": s,
                "T": t,
                "V": v,
                "wealth": round(wealth, 6),
                "strongest_channel_lr": round(max(lrs), 6),
                "full_decision": decide(wealth, alpha),
                "strongest_only_decision": decide(max(lrs), alpha),
                "pricing_changed_decision": differs,
            }
        )
    return {
        "alpha": alpha,
        "threshold_surface": 1.0 / alpha,
        "threshold_discard": alpha,
        "caps": {"S": S_CAP, "T": T_CAP, "V_reproduced": V_CAP, "V_failed": V_FAILED},
        "combinations": len(rows),
        "pricing_changed_decision": changed,
        "reachable_max_without_v": round(S_CAP * T_CAP, 6),
        "note": (
            "S*T maxes out at 9, below the surfacing threshold of 10, and the "
            "smallest reachable wealth is 0.5, above the discard threshold of "
            "0.1. Only V reaches the threshold, and V alone already reaches it."
        ),
        "rows": rows,
    }


def _counterfactual(path: Path, alpha: float) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    changed = 0
    for case in payload["cases"]:
        for candidate in case["candidates"]:
            lrs = tuple(
                value
                for value in (float(candidate["S"]), float(candidate["T"]))
                if value > 1.0
            ) or (float(candidate["S"]),)
            wealth = float(candidate["wealth"])
            differs = _changed(wealth, lrs, alpha)
            changed += differs
            rows.append(
                {
                    "case_id": case["case_id"],
                    "finding_id": candidate["finding_id"],
                    "S": candidate["S"],
                    "T": candidate["T"],
                    "wealth": wealth,
                    "strongest_channel_lr": max(lrs),
                    "pricing_changed_decision": differs,
                }
            )
    return {
        "source": str(path),
        "candidates": len(rows),
        "pricing_changed_decision": changed,
        "rows": rows,
    }


def _d059(alpha: float) -> dict[str, object]:
    """The four surfaced findings; each purchased S then V at the reproduced LR.

    The exact S differs per finding and is not needed: S is capped at 3, so
    S * 20 is at least 20 and V alone is 20. Both are at or above the threshold
    of 10, so both decisions are `surface` whatever S was.
    """
    rows = []
    changed = 0
    for finding_id in D059_SURFACED:
        for s in sorted(set(VOTE_LR)):
            wealth = s * V_CAP
            differs = _changed(wealth, (s, V_CAP), alpha)
            changed += differs
            rows.append(
                {
                    "finding_id": finding_id,
                    "S": s,
                    "V": V_CAP,
                    "wealth": round(wealth, 6),
                    "pricing_changed_decision": differs,
                }
            )
    return {
        "surfaced_findings": len(D059_SURFACED),
        "s_values_enumerated": len(set(VOTE_LR)),
        "pricing_changed_decision": changed,
        "note": (
            "S is unknown per finding in the frozen D-059 artifact, so every "
            "reachable S is enumerated; the answer does not depend on it."
        ),
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--alpha", type=float, default=ALPHA)
    parser.add_argument("--counterfactual", type=Path, default=COUNTERFACTUAL)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    grid = _grid(args.alpha)
    counterfactual = _counterfactual(args.counterfactual, args.alpha)
    d059 = _d059(args.alpha)
    total = (
        int(grid["pricing_changed_decision"])
        + int(counterfactual["pricing_changed_decision"])
        + int(d059["pricing_changed_decision"])
    )
    artifact = {
        "schema_version": "attest.pricing-instrument-backfill.v1",
        "alpha": args.alpha,
        "paid_calls": 0,
        "spend_usd": 0.0,
        "reachable_grid": grid,
        "history_counterfactual_run": counterfactual,
        "d059_surfaced_findings": d059,
        "total_pricing_changed_decision": total,
        "limitations": [
            "Records only: nothing here changed or would have changed a decision.",
            "The grid is exhaustive for the frozen factory tables at this alpha; "
            "a different alpha or a changed cap needs its own enumeration.",
            "This is not an accuracy statement of any kind.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.out, artifact)
    print(
        f"grid: {grid['pricing_changed_decision']}/{grid['combinations']} combinations; "
        f"counterfactual run: {counterfactual['pricing_changed_decision']}/"
        f"{counterfactual['candidates']} candidates; "
        f"D-059 surfaced: {d059['pricing_changed_decision']}/{len(d059['rows'])} rows; "
        f"total {total}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
