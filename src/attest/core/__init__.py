"""Core betting engine: conditional tables, e-value betting, allocation, stopping.

Semantics (fixed by design, see DECISIONS.md and docs upstream):
certification is purely the odds threshold — wealth >= 1/alpha certifies the finding
as true, wealth <= alpha certifies it as false, anything else defers. There is no
quorum or majority rule anywhere.
"""

from attest.core.allocation import choose_next, expected_info, kl
from attest.core.betting import decide, task_lr_canonical, task_lr_purchase_order
from attest.core.engine import Engine, EngineConfig, TaskResult
from attest.core.exploration import ExplorationSchedule
from attest.core.monitor import WinnersCurseMonitor
from attest.core.stream import Stream, make_stream
from attest.core.tables import Tables

__all__ = [
    "Engine",
    "EngineConfig",
    "ExplorationSchedule",
    "Stream",
    "Tables",
    "TaskResult",
    "WinnersCurseMonitor",
    "choose_next",
    "decide",
    "expected_info",
    "kl",
    "make_stream",
    "task_lr_canonical",
    "task_lr_purchase_order",
]
