"""Forced-exploration schedule.

eps stays at the hot rate until every MARGINAL table cell has cell_target
samples, then drops to the cold rate (D-003 revised: pairwise cells can be
unattainable under near-deterministic cloning, which would pin exploration hot
forever; thin pair/triple cells are guarded by the tau floor). Exploration
tasks buy ALL judges in randomized order and are the only tasks the default
engine learns tables from (the non-adaptive calibration slice).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from attest.core.tables import Tables


@dataclass
class ExplorationSchedule:
    eps_hot: float = 0.10
    eps_cold: float = 0.02
    cell_target: int = 30

    def rate(self, tables: Tables) -> float:
        return self.eps_hot if tables.min_marginal_count() < self.cell_target else self.eps_cold

    def should_explore(self, rng: np.random.Generator, tables: Tables) -> bool:
        return bool(rng.random() < self.rate(tables))
