"""Faithful replication of the seed prototype's strategies and metrics.

This module exists so regression tests can pin the exact numbers in the seed
experiment record (RESULTS.md): same tables, same RNG usage, same iteration
order, same defaults. Do not "improve" anything here — behavioral fidelity is
the point. New development happens in engine.py.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

import numpy as np

from attest.core.allocation import expected_info
from attest.core.betting import task_lr_canonical, task_lr_purchase_order
from attest.core.stream import Stream
from attest.core.tables import Tables

JUDGES = ["A", "B", "C"]
PRICE = {"A": 1.00, "B": 0.50, "C": 0.15}
TAU = 0.05
LAST = 500  # window for spend-share stats

Record = tuple[int, int | None, dict[str, float]]


def run(
    stream: Stream, strategy: str, alpha: float, tau: float = TAU
) -> tuple[list[Record], Tables]:
    """Strategies: engine (canonical, price-aware), engine_po (purchase-order),
    priceblind (canonical, prices ignored), uniform (always all three)."""
    theta_arr, v, explore = stream
    thresh = 1.0 / alpha
    tables = Tables()
    po = strategy == "engine_po"
    shuffle_rng = np.random.default_rng(777)
    recs: list[Record] = []
    for t in range(len(theta_arr)):
        theta = int(theta_arr[t])
        bought: dict[str, int] = {}
        order: list[str] = []
        spend_j: dict[str, float] = defaultdict(float)

        if strategy == "uniform" or explore[t]:
            order = list(JUDGES)
            if po:
                shuffle_rng.shuffle(order)
            for j in order:
                bought[j] = int(v[j][t])
                spend_j[j] += PRICE[j]
            lr = (
                task_lr_purchase_order(tables, order, bought)
                if po
                else task_lr_canonical(tables, bought)
            )
        else:
            lr = 1.0
            while True:
                if lr >= thresh or lr <= 1.0 / thresh:
                    break
                cand = [j for j in JUDGES if j not in bought]
                if not cand:
                    break
                p1post = lr / (1.0 + lr)
                best, bestval = None, -1.0
                for j in cand:
                    info = expected_info(tables, j, bought, p1post)
                    val = info if strategy == "priceblind" else info / PRICE[j]
                    if val > bestval:
                        best, bestval = j, val
                if bestval < tau:
                    break
                assert best is not None
                bought[best] = int(v[best][t])
                order.append(best)
                spend_j[best] += PRICE[best]
                lr = (
                    task_lr_purchase_order(tables, order, bought)
                    if po
                    else task_lr_canonical(tables, bought)
                )

        dec = 1 if lr >= thresh else (0 if lr <= 1.0 / thresh else None)
        if po:
            tables.update_po(theta, order, bought)
        else:
            tables.update(theta, bought)
        recs.append((theta, dec, dict(spend_j)))
    return recs, tables


def metrics(recs: list[Record], tables: Tables) -> dict[str, Any]:
    n = len(recs)
    certed = [(th, d) for th, d, _ in recs if d is not None]
    ncert = len(certed)
    nwrong = sum(1 for th, d in certed if d != th)
    spend = sum(sum(s.values()) for _, _, s in recs)
    spend_last: dict[str, float] = defaultdict(float)
    for _, _, s in recs[-LAST:]:
        for j, x in s.items():
            spend_last[j] += x
    tot_last = sum(spend_last.values())
    cert_last1000 = sum(1 for _, d, _ in recs[-1000:] if d is not None) / 1000
    return dict(
        cert_rate=ncert / n,
        cert_rate_last1000=cert_last1000,
        defer_rate=1 - ncert / n,
        false_cert_rate=nwrong / n,
        cert_acc=(ncert - nwrong) / ncert if ncert else float("nan"),
        avg_cost=spend / n,
        cost_per_cert=spend / ncert if ncert else float("inf"),
        share_a=spend_last["A"] / tot_last if tot_last else 0,
        share_b=spend_last["B"] / tot_last if tot_last else 0,
        share_c=spend_last["C"] / tot_last if tot_last else 0,
        agree_bc=tables.agree("B", "C"),
    )


def theo_max_lr(gamma: float) -> tuple[float, float]:
    """Exact best-case LR (all judges correct) with true parameters
    (acc A=0.8, B=0.75, C=0.7)."""
    lr_a, lr_b = 0.8 / 0.2, 0.75 / 0.25
    pc1 = gamma + (1 - gamma) * 0.7
    pc0 = gamma + (1 - gamma) * 0.3
    full = lr_a * lr_b * pc1 / pc0
    m1 = gamma * 0.75 + (1 - gamma) * 0.7
    m0 = gamma * 0.25 + (1 - gamma) * 0.3
    ac = lr_a * m1 / m0
    return full, ac
