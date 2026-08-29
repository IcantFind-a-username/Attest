"""Greedy value-of-information purchase allocation.

Before each purchase: estimated expected log-e (posterior-weighted symmetric KL
between the two conditional plug-in distributions) per unit price; buy the max;
stop when the best value drops below tau. tau must sit BELOW the plug-in noise
floor of thin conditioning cells or good judges get starved (RESULTS §5).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np

from attest.core.tables import Tables


def kl(a: float, b: float) -> float:
    """Bernoulli KL divergence KL(a || b), clipped for numerical safety."""
    eps = 1e-12
    a = min(max(a, eps), 1 - eps)
    b = min(max(b, eps), 1 - eps)
    return float(a * np.log(a / b) + (1 - a) * np.log((1 - a) / (1 - b)))


def expected_info(tables: Tables, j: str, seen: Mapping[str, int], p1post: float) -> float:
    """Posterior-weighted expected log-e for buying judge j given verdicts seen."""
    q1 = tables.p1(j, seen, 1)
    q0 = tables.p1(j, seen, 0)
    return p1post * kl(q1, q0) + (1 - p1post) * kl(q0, q1)


def choose_next(
    tables: Tables,
    candidates: Sequence[str],
    seen: Mapping[str, int],
    wealth: float,
    prices: Mapping[str, float],
    price_aware: bool,
    tau: float,
) -> tuple[str | None, float]:
    """Pick the next judge to buy, or (None, best_value) if below tau.

    Candidate iteration order is significant (first-seen wins ties) and matches
    the seed prototype exactly.
    """
    p1post = wealth / (1.0 + wealth)
    best, bestval = None, -1.0
    for j in candidates:
        info = expected_info(tables, j, seen, p1post)
        val = info / prices[j] if price_aware else info
        if val > bestval:
            best, bestval = j, val
    if bestval < tau:
        return None, bestval
    return best, bestval
