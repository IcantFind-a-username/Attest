"""Laplace-smoothed conditional frequency tables over binary judge verdicts.

Faithful port of the validated seed prototype: marginal [theta, v], pairwise
[theta, v_first, v_second] (key = sorted pair), and for exactly three judges a
triple joint [theta, vA, vB, vC]. Probabilities are plug-in Laplace-smoothed
frequencies conditioned on the verdicts already seen.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from itertools import combinations

import numpy as np

PairKey = tuple[str, str]


class Tables:
    """Conditional frequency tables learned from truth-labeled tasks."""

    def __init__(self, judges: Sequence[str] = ("A", "B", "C"), smoothing: float = 1.0):
        if len(set(judges)) != len(judges):
            raise ValueError("duplicate judge names")
        self.judges: list[str] = list(judges)
        self.s = float(smoothing)
        self.idx: dict[str, int] = {j: i for i, j in enumerate(self.judges)}
        self.marg: dict[str, np.ndarray] = {j: np.zeros((2, 2)) for j in self.judges}
        self.pairs: list[PairKey] = [
            (a, b) if a < b else (b, a) for a, b in combinations(self.judges, 2)
        ]
        self.pair: dict[PairKey, np.ndarray] = {p: np.zeros((2, 2, 2)) for p in self.pairs}
        self.trip: np.ndarray | None = np.zeros((2, 2, 2, 2)) if len(self.judges) == 3 else None

    def update(self, theta: int, verdicts: Mapping[str, int]) -> None:
        """Full update from an all-buy or canonical-order task."""
        for j, v in verdicts.items():
            self.marg[j][theta, v] += 1
        for a, b in self.pairs:
            if a in verdicts and b in verdicts:
                self.pair[(a, b)][theta, verdicts[a], verdicts[b]] += 1
        if self.trip is not None and len(verdicts) == len(self.judges):
            vs = tuple(verdicts[j] for j in self.judges)
            self.trip[(theta, *vs)] += 1

    def update_po(self, theta: int, order: Sequence[str], verdicts: Mapping[str, int]) -> None:
        """Usage-matched update for purchase-order betting: each purchase updates
        ONLY the table used to bet on it, so a table's missingness depends only on
        its own conditioning variables (ignorable)."""
        for i, j in enumerate(order):
            if i == 0:
                self.marg[j][theta, verdicts[j]] += 1
            elif i == 1:
                k = order[0]
                key: PairKey = (j, k) if j < k else (k, j)
                self.pair[key][theta, verdicts[key[0]], verdicts[key[1]]] += 1
            elif i == 2 and self.trip is not None:
                vs = tuple(verdicts[jj] for jj in self.judges)
                self.trip[(theta, *vs)] += 1
            else:
                raise NotImplementedError("purchase-order update beyond 3 judges")

    def p1(self, j: str, cond: Mapping[str, int], theta: int) -> float:
        """P_hat(v_j = 1 | conditioning verdicts, theta)."""
        s = self.s
        if len(cond) == 0:
            c = self.marg[j][theta]
            return float((c[1] + s) / (c.sum() + 2 * s))
        if len(cond) == 1:
            ((k, vk),) = cond.items()
            key: PairKey = (j, k) if j < k else (k, j)
            t = self.pair[key][theta]
            sub = t[:, vk] if key[0] == j else t[vk, :]
            return float((sub[1] + s) / (sub.sum() + 2 * s))
        if len(cond) == 2 and self.trip is not None:
            idx: list[object] = [slice(None)] * 3
            for k, vk in cond.items():
                idx[self.idx[k]] = vk
            sub = self.trip[theta][tuple(idx)]
            return float((sub[1] + s) / (sub.sum() + 2 * s))
        raise NotImplementedError("conditioning on >2 judges is not supported")

    def lr_factor(self, j: str, cond: Mapping[str, int], v: int) -> float:
        """Plug-in likelihood ratio for observing v_j = v given conditioning set."""
        a = self.p1(j, cond, 1)
        b = self.p1(j, cond, 0)
        return (a if v == 1 else 1 - a) / (b if v == 1 else 1 - b)

    def agree(self, j1: str, j2: str) -> float:
        """Learned P_hat(v_j1 = v_j2) under a 0.5 theta prior, from the pair table."""
        key: PairKey = (j1, j2) if j1 < j2 else (j2, j1)
        t = self.pair[key]
        s = self.s
        out = 0.0
        for th in (0, 1):
            tot = t[th].sum() + 4 * s
            agree = t[th, 0, 0] + t[th, 1, 1] + 2 * s
            out += 0.5 * agree / tot
        return float(out)

    def min_cell_count(self) -> int:
        """Smallest raw count over marginal and pairwise cells (triple excluded;
        see min_marginal_count for the exploration trigger)."""
        m = min(int(t.min()) for t in self.marg.values())
        if self.pairs:
            m = min(m, min(int(t.min()) for t in self.pair.values()))
        return m

    def min_marginal_count(self) -> int:
        """Smallest raw count over marginal cells only. The exploration
        schedule keys on this (D-003 revised): pairwise cells can be
        unattainable under near-deterministic cloning (a gamma=0.99 clone makes
        disagreement cells arbitrarily rare), which would pin exploration hot
        forever; thin pair/triple cells are guarded by the tau floor instead."""
        return min(int(t.min()) for t in self.marg.values())
