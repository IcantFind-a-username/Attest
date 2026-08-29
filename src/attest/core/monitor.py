"""Winner's-curse monitor.

Adaptive buying couples small-sample optimism to the buy rule: judges get bought
exactly in conditioning cells whose estimated informativeness is currently
overstated, and those same overstated estimates price the bets (RESULTS §6).
This monitor watches for the signature — realized log-e systematically below the
estimate, and spend-share drift — and raises alarms for the ledger. It never
intervenes (MVP scope).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class _Purchase:
    judge: str
    estimated: float
    realized: float
    spend: float


@dataclass
class WinnersCurseMonitor:
    window: int = 200
    optimism_threshold: float = 0.15  # nats; alarm when mean(realized - est) < -this
    min_samples: int = 30
    drift_threshold: float = 0.15  # absolute spend-share change between half-windows
    _buf: deque[_Purchase] = field(default_factory=deque, repr=False)

    def record(
        self, judge: str, estimated_log_e: float, realized_log_e: float, spend: float
    ) -> None:
        self._buf.append(_Purchase(judge, estimated_log_e, realized_log_e, spend))
        while len(self._buf) > self.window:
            self._buf.popleft()

    def alarms(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        buf = list(self._buf)
        by_judge: dict[str, list[_Purchase]] = {}
        for p in buf:
            by_judge.setdefault(p.judge, []).append(p)

        for judge, ps in sorted(by_judge.items()):
            if len(ps) < self.min_samples:
                continue
            gap = sum(p.realized - p.estimated for p in ps) / len(ps)
            if gap < -self.optimism_threshold:
                out.append(
                    {
                        "kind": "winners_curse_optimism",
                        "judge": judge,
                        "mean_realized_minus_estimated": gap,
                        "n": len(ps),
                    }
                )

        half = len(buf) // 2
        if half >= self.min_samples:
            prior, recent = buf[:half], buf[half:]
            tot_prior = sum(p.spend for p in prior)
            tot_recent = sum(p.spend for p in recent)
            if tot_prior > 0 and tot_recent > 0:
                for judge in sorted(by_judge):
                    share_prior = sum(p.spend for p in prior if p.judge == judge) / tot_prior
                    share_recent = sum(p.spend for p in recent if p.judge == judge) / tot_recent
                    drift = share_recent - share_prior
                    if abs(drift) > self.drift_threshold:
                        out.append(
                            {
                                "kind": "spend_share_drift",
                                "judge": judge,
                                "drift": drift,
                                "share_prior": share_prior,
                                "share_recent": share_recent,
                            }
                        )
        return out
