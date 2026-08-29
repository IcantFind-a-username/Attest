"""The default engine: purchase-order betting on a non-adaptive calibration slice.

Variant semantics (spec-fixed):

- ``po_calib`` (default): bets decompose in PURCHASE order (each conditional bet
  conditions on exactly the verdicts already bought), and the tables are learned
  ONLY from all-buy exploration tasks. The calibration slice is missingness-free
  by construction (purchases there don't depend on verdicts), which removes both
  the selection bias of canonical-order betting (RESULTS §6) and the main source
  of the winner's curse (adaptive buys never feed the tables that price them).
  All-buy tasks use full-table updates: the slice is unbiased for every table
  simultaneously, so usage-matched updates would just throw away samples.
- ``po_adaptive`` (experimental flag): purchase-order betting with usage-matched
  updates from every task — statistically pure but slower to converge.
- ``canonical`` (legacy): the seed prototype's canonical-order variant, kept for
  comparison only.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from attest.core.allocation import choose_next, expected_info
from attest.core.betting import decide, task_lr_canonical, task_lr_purchase_order
from attest.core.exploration import ExplorationSchedule
from attest.core.monitor import WinnersCurseMonitor
from attest.core.stream import Stream
from attest.core.tables import Tables

VARIANTS = ("po_calib", "po_adaptive", "canonical")


@dataclass
class EngineConfig:
    judges: tuple[str, ...] = ("A", "B", "C")
    prices: Mapping[str, float] = field(default_factory=lambda: {"A": 1.00, "B": 0.50, "C": 0.15})
    alpha: float = 0.1
    tau: float = 0.05
    smoothing: float = 1.0
    variant: str = "po_calib"
    price_aware: bool = True
    eps_hot: float = 0.10
    eps_cold: float = 0.02
    cell_target: int = 30
    seed: int = 0

    def __post_init__(self) -> None:
        if self.variant not in VARIANTS:
            raise ValueError(f"unknown variant {self.variant!r}")
        if not 0 < self.alpha < 1:
            raise ValueError("alpha must be in (0, 1)")
        missing = set(self.judges) - set(self.prices)
        if missing:
            raise ValueError(f"no price for judges {sorted(missing)}")


@dataclass
class TaskResult:
    decision: int | None  # 1 surface, 0 silent discard, None drawer
    wealth: float
    order: list[str]
    verdicts: dict[str, int]
    spend: dict[str, float]
    explored: bool
    estimated_log_e: float
    realized_log_e: float


class Engine:
    """Streaming engine: review_task() decides purchases and the verdict gate;
    learn() feeds revealed truth back into the tables per the active variant."""

    def __init__(self, config: EngineConfig | None = None):
        self.config = config or EngineConfig()
        c = self.config
        self.tables = Tables(c.judges, c.smoothing)
        self.schedule = ExplorationSchedule(c.eps_hot, c.eps_cold, c.cell_target)
        self.monitor = WinnersCurseMonitor()
        self._rng = np.random.default_rng(c.seed)
        self._po = c.variant in ("po_calib", "po_adaptive")

    def _lr(self, order: list[str], verdicts: dict[str, int]) -> float:
        if self._po:
            return task_lr_purchase_order(self.tables, order, verdicts)
        return task_lr_canonical(self.tables, verdicts)

    def review_task(self, get_verdict: Callable[[str], int]) -> TaskResult:
        c = self.config
        explored = self.schedule.should_explore(self._rng, self.tables)
        order: list[str] = []
        verdicts: dict[str, int] = {}
        spend: dict[str, float] = {}
        est_total = 0.0

        if explored:
            all_order = list(c.judges)
            if self._po:
                self._rng.shuffle(all_order)
            wealth = 1.0
            for j in all_order:
                p1post = wealth / (1.0 + wealth)
                est = expected_info(self.tables, j, verdicts, p1post)
                v = int(get_verdict(j))
                realized = float(np.log(self.tables.lr_factor(j, verdicts, v)))
                order.append(j)
                verdicts[j] = v
                spend[j] = spend.get(j, 0.0) + c.prices[j]
                est_total += est
                self.monitor.record(j, est, realized, c.prices[j])
                wealth = self._lr(order, verdicts)
        else:
            wealth = 1.0
            while True:
                if decide(wealth, c.alpha) is not None:
                    break
                cand = [j for j in c.judges if j not in verdicts]
                if not cand:
                    break
                best, bestval = choose_next(
                    self.tables, cand, verdicts, wealth, c.prices, c.price_aware, c.tau
                )
                if best is None:
                    break
                p1post = wealth / (1.0 + wealth)
                est = expected_info(self.tables, best, verdicts, p1post)
                v = int(get_verdict(best))
                realized = float(np.log(self.tables.lr_factor(best, verdicts, v)))
                order.append(best)
                verdicts[best] = v
                spend[best] = spend.get(best, 0.0) + c.prices[best]
                est_total += est
                self.monitor.record(best, est, realized, c.prices[best])
                wealth = self._lr(order, verdicts)

        return TaskResult(
            decision=decide(wealth, c.alpha),
            wealth=wealth,
            order=order,
            verdicts=verdicts,
            spend=spend,
            explored=explored,
            estimated_log_e=est_total,
            realized_log_e=float(np.log(wealth)) if wealth > 0 else float("-inf"),
        )

    def learn(self, theta: int, result: TaskResult) -> None:
        """Feed revealed truth back. po_calib learns ONLY from the all-buy
        exploration slice (full update: the slice is missingness-free); the
        other variants learn from every task."""
        c = self.config
        if c.variant == "po_calib":
            if result.explored:
                self.tables.update(theta, result.verdicts)
        elif c.variant == "po_adaptive":
            self.tables.update_po(theta, result.order, result.verdicts)
        else:
            self.tables.update(theta, result.verdicts)

    def run_stream(self, stream: Stream) -> list[tuple[int, TaskResult]]:
        """Simulation driver: verdicts come from the stream, truth is revealed
        after each task. The stream's own explore mask is ignored — the engine's
        schedule decides exploration."""
        out: list[tuple[int, TaskResult]] = []
        for t in range(len(stream.theta)):
            res = self.review_task(lambda j: int(stream.verdicts[j][t]))  # noqa: B023
            theta = int(stream.theta[t])
            self.learn(theta, res)
            out.append((theta, res))
        return out


def summarize(results: list[tuple[int, TaskResult]]) -> dict[str, Any]:
    """Aggregate metrics for a run_stream() output."""
    n = len(results)
    certed = [(th, r.decision) for th, r in results if r.decision is not None]
    ncert = len(certed)
    nwrong = sum(1 for th, d in certed if d != th)
    spend = sum(sum(r.spend.values()) for _, r in results)
    explored = sum(1 for _, r in results if r.explored)
    return dict(
        n=n,
        cert_rate=ncert / n if n else 0.0,
        false_cert_rate=nwrong / n if n else 0.0,
        cert_acc=(ncert - nwrong) / ncert if ncert else float("nan"),
        defer_rate=1 - ncert / n if n else 1.0,
        avg_cost=spend / n if n else 0.0,
        explore_rate=explored / n if n else 0.0,
    )
