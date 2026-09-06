"""The corpus drivers' cumulative cap reserves a unit's maximum before it starts.

The RED is the run that forced it. On 2026-09-07 the `us-stock-helper` half of
the budget re-run held a $3.50 cumulative cap and a `--budget 1.00` per review.
Its sixth unit began at $3.25 spent -- under the cap, so the old rule
(``if spent >= args.cap: skip``) started it -- and the run ended at $4.12: $0.62
above the item's cap and $0.32 above the window's reservation. Nothing
misbehaved; a cap that gates *starting* on money already spent simply cannot
bound a run whose next unit may cost up to the per-review budget.

The module under test is `scripts/corpus/driver_budget.py`, which every paid
driver now routes its cap through. It is driver code rather than product code,
so it is loaded here by path.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "scripts" / "corpus" / "driver_budget.py"

# the recorded run, unit by unit, from `docs/acceptance/2026-09-07-budget-rerun.md`
CAP = 3.50
BUDGET = 1.00
RECORDED = (0.5127, 0.5861, 0.6641, 0.8857, 0.6054, 0.8623)  # six units, $4.1163


def _module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("driver_budget", MODULE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `@dataclass` resolves its annotations through `sys.modules`, so the module
    # has to be registered before it is executed
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def driver_budget() -> ModuleType:
    return _module()


def test_the_recorded_overrun_cannot_happen_under_the_reservation(
    driver_budget: ModuleType,
) -> None:
    """The 2026-09-07 run, replayed: it stops two units early instead of $0.62 over."""
    # what the old rule did: every unit starts while the money already spent is
    # under the cap, and the run ends above it
    spent = 0.0
    old_rule_started = 0
    for actual in RECORDED:
        if spent >= CAP:
            continue
        old_rule_started += 1
        spent += actual
    assert (old_rule_started, round(spent, 4)) == (6, 4.1163)
    assert spent > CAP  # $0.62 over the item's cap; this is the defect

    # what the rule under test does: a unit starts only when its *maximum* fits
    cap = driver_budget.DriverCap(cap=CAP, reservation_usd=BUDGET)
    for index, actual in enumerate(RECORDED):
        if cap.start(f"unit-{index}"):
            cap.settle(actual)
    assert cap.started == 4  # $2.6486 spent; 2.6486 + 1.00 > 3.50 stops the fifth
    assert round(cap.spent, 4) == 2.6486
    assert cap.spent <= CAP
    assert cap.reserved == 0.0
    # the two units that did not run are named rather than silently dropped
    assert len(cap.refused) == 2
    assert "unit-4" in cap.refused[0] and "cumulative cap" in cap.refused[0]


def test_the_run_never_ends_above_the_cap_however_the_units_fall(
    driver_budget: ModuleType,
) -> None:
    """Every unit that starts is charged; the total is bounded by the cap."""
    cap = driver_budget.DriverCap(cap=CAP, reservation_usd=BUDGET)
    started = 0
    for actual in (0.9, 0.05, 1.0, 0.4, 0.2, 0.7, 0.99, 0.8, 0.6):
        if not cap.start():
            continue
        started += 1
        cap.settle(actual)
    assert started == 5  # each start needs $1.00 of headroom under the $3.50 cap
    assert cap.spent <= CAP
    assert cap.reserved == 0.0
    assert cap.refused, "the units that did not fit are named, not silently dropped"


def test_a_unit_whose_cost_could_not_be_read_is_charged_its_reservation(
    driver_budget: ModuleType,
) -> None:
    """An unreadable spend line is charged, never treated as free."""
    cap = driver_budget.DriverCap(cap=CAP, reservation_usd=BUDGET)
    assert cap.start() is True
    assert cap.settle(None) == BUDGET
    assert cap.spent == BUDGET
    # and a released reservation is available to the next unit
    assert cap.reserved == 0.0
    assert cap.refusal() is None


def test_a_resumed_run_carries_its_earlier_spend_into_the_reservation(
    driver_budget: ModuleType,
) -> None:
    """Resume reads the cumulative figure out of the log; the cap must honour it."""
    cap = driver_budget.DriverCap(cap=CAP, reservation_usd=BUDGET, spent=3.254)
    assert cap.start("resumed") is False
    cap = driver_budget.DriverCap(cap=CAP, reservation_usd=BUDGET, spent=2.4)
    assert cap.start("resumed") is True


@pytest.mark.parametrize(
    "kwargs",
    (
        {"cap": -1.0, "reservation_usd": 1.0},
        {"cap": float("inf"), "reservation_usd": 1.0},
        {"cap": 1.0, "reservation_usd": float("nan")},
        {"cap": True, "reservation_usd": 1.0},
        {"cap": 1.0, "reservation_usd": 1.0, "spent": -0.1},
    ),
)
def test_a_cap_that_cannot_bound_anything_is_refused_at_construction(
    driver_budget: ModuleType, kwargs: dict[str, object]
) -> None:
    with pytest.raises(ValueError):
        driver_budget.DriverCap(**kwargs)
