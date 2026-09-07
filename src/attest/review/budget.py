"""Hard per-review budget: preflight estimate, pre-debit, explicit DEFER.

Every model call is estimated BEFORE it happens; if the projected total would
exceed the budget, the call is not made and the review defers with the reason.
Actual usage replaces the estimate once known.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast

from attest.review.config import load_pricing

# Discovery may spend at most this share of a review's budget, so breadth
# cannot starve every reproduction (owner decision 3 of 2026-09-03d). On
# `d7be758` the proposal stage produced 12 candidates from a 210-line change and
# left nine of eleven reproductions with no budget to generate a test at all.
#
# 0.6 -> 0.3, and it now binds the *whole* proposal stage rather than every unit
# after the first (owner decision 1 of 2026-09-07, D-168). The 2026-09-07 budget
# re-run is the measurement: four times the budget bought 3.2x the candidates and
# moved not one verdict, and 167 of the 331 candidates were drawered
# `no-reproduction-bought` -- discovered, then never ranked high enough to buy a
# reproduction. Raising the budget raises discovery, and discovery re-starves the
# budget; capping discovery is what makes a larger budget buy reproductions.
#
# The first unit no longer has D-111's exemption. A review that cannot read one
# change unit inside 30% of its budget now defers with a budget reason, which is
# a contract line a reader can act on -- where the exemption let discovery take
# the whole budget and leave verification nothing, silently.
PROPOSAL_SHARE = 0.3

# rough chars-per-token for preflight estimates (conservative: low divisor
# overestimates tokens and cost)
CHARS_PER_TOKEN = 3.0


@dataclass
class BudgetExceeded(Exception):
    reason: str
    # D-187: what the truncation actually cost, for the caller that has to say
    # so in one line. `shortfall_usd` is how much more the call needed than the
    # ceiling in force; `budget_usd_needed` is the `budget-usd` at which the
    # same call would have fitted, and both are None when the raise did not
    # come from a ceiling comparison (a caller that constructs the exception
    # itself, or an older ledger being replayed).
    shortfall_usd: float | None = None
    budget_usd_needed: float | None = None


@dataclass
class Budget:
    limit_usd: float
    model: str
    spent_usd: float = 0.0
    reserved_usd: float = 0.0
    calls: list[dict[str, Any]] = field(default_factory=list)
    stage_label: str = ""  # the stage whose share is in force, "" for none
    stage_ceiling_usd: float | None = None
    # model id -> its price table; one review may buy from more than one model
    # (D-115: proposals on the default, reproductions on the generation model)
    _prices: dict[str, dict[str, float]] = field(default_factory=dict)
    # D-157: reproductions may run two candidates at once. The lock is not part
    # of the budget's value -- never compared, never printed, never serialised.
    _lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if (
            isinstance(self.limit_usd, bool)
            or not isinstance(self.limit_usd, (int, float))
            or not math.isfinite(self.limit_usd)
            or self.limit_usd <= 0
        ):
            raise ValueError("budget limit must be a finite positive number")
        self.prices(self.model)

    def prices(self, model: str | None = None) -> dict[str, float]:
        """The price table for ``model``; the budget's own model by default.

        An unpriced model raises here rather than being charged at another
        model's rate: a cost the ledger cannot justify is not a cost.
        """
        name = model or self.model
        cached = self._prices.get(name)
        if cached is not None:
            return cached
        pricing = load_pricing()
        try:
            m = pricing["models"][name]
        except KeyError:
            raise ValueError(f"no pricing for model {name!r}") from None
        table = {
            "in": float(m["input_per_mtok"]) / 1e6,
            "out": float(m["output_per_mtok"]) / 1e6,
        }
        table["cache_write"] = table["in"] * float(pricing.get("cache_write_multiplier", 1.25))
        table["cache_read"] = table["in"] * float(pricing.get("cache_read_multiplier", 0.10))
        self._prices[name] = table
        return table

    def estimate_cost(
        self, input_chars: int, max_output_tokens: int, model: str | None = None
    ) -> float:
        prices = self.prices(model)
        in_tokens = input_chars / CHARS_PER_TOKEN
        return in_tokens * prices["in"] + max_output_tokens * prices["out"]

    @contextmanager
    def stage(self, label: str, share: float) -> Iterator[None]:
        """Inside the block, reservations may not exceed ``share`` of the limit.

        One stage at a time: the block restores whatever was in force before it.
        """
        previous = (self.stage_label, self.stage_ceiling_usd)
        self.stage_label = label
        self.stage_ceiling_usd = self.limit_usd * share
        try:
            yield
        finally:
            self.stage_label, self.stage_ceiling_usd = previous

    def reserve(
        self,
        label: str,
        input_chars: int,
        max_output_tokens: int,
        model: str | None = None,
    ) -> float:
        """Pre-debit a planned call; raises BudgetExceeded instead of calling."""
        est = self.estimate_cost(input_chars, max_output_tokens, model)
        # D-157: reproductions may run two candidates at once, and
        # `self.reserved_usd += est` is a read-modify-write. Two threads
        # interleaving it lose a reservation, and a lost reservation is spend
        # above the cap -- the one number this project never lets slip. The
        # lock makes the check-and-debit one step; single-threaded behaviour is
        # unchanged.
        with self._lock:
            projected = self.spent_usd + self.reserved_usd + est
            ceiling = self.stage_ceiling_usd
            if ceiling is not None and projected > ceiling:
                share = ceiling / self.limit_usd if self.limit_usd else 0.0
                raise BudgetExceeded(
                    f"call '{label}' estimated ${est:.4f}; projected total "
                    f"${projected:.4f} exceeds the {self.stage_label} share "
                    f"${ceiling:.4f} of budget ${self.limit_usd:.2f}",
                    shortfall_usd=projected - ceiling,
                    # the stage ceiling is a share of the whole budget, so the
                    # budget that would have covered this call is the projected
                    # total divided by that share
                    budget_usd_needed=(projected / share) if share else None,
                )
            if projected > self.limit_usd:
                raise BudgetExceeded(
                    f"call '{label}' estimated ${est:.4f}; projected total "
                    f"${projected:.4f} exceeds budget ${self.limit_usd:.2f}",
                    shortfall_usd=projected - self.limit_usd,
                    budget_usd_needed=projected,
                )
            self.reserved_usd += est
        return est

    def settle(
        self,
        label: str,
        reserved: float,
        input_tokens: int,
        output_tokens: int,
        *,
        cache_creation_input_tokens: int = 0,
        cache_read_input_tokens: int = 0,
        model: str | None = None,
    ) -> float:
        """Replace a reservation with actual usage-based cost. ``input_tokens``
        is the uncached remainder; cache writes and reads are priced apart."""
        prices = self.prices(model)
        actual = (
            input_tokens * prices["in"]
            + cache_creation_input_tokens * prices["cache_write"]
            + cache_read_input_tokens * prices["cache_read"]
            + output_tokens * prices["out"]
        )
        with self._lock:
            self.reserved_usd = max(0.0, self.reserved_usd - reserved)
            self.spent_usd += actual
            self.calls.append(
                {
                    "label": label,
                    "model": model or self.model,
                    "input_tokens": input_tokens,
                    "cache_creation_input_tokens": cache_creation_input_tokens,
                    "cache_read_input_tokens": cache_read_input_tokens,
                    "output_tokens": output_tokens,
                    "cost_usd": actual,
                }
            )
        return actual

    def cancel(self, reserved: float) -> None:
        with self._lock:
            self.reserved_usd = max(0.0, self.reserved_usd - reserved)

    def exhausted(self) -> bool:
        """Is there nothing left to reserve? (the dispatch guard, D-157)"""
        with self._lock:
            return self.spent_usd + self.reserved_usd >= self.limit_usd


# D-161: the second ceiling. `limit_usd` bounds one review; this bounds a
# repository's spend over a rolling day, so a busy afternoon of pull requests
# cannot cost an unbounded amount however small each one is.
DAILY_WINDOW_S = 86_400.0
_SPEND_KINDS = frozenset({"review_run", "ci_final"})


def _row_epoch(value: object) -> float | None:
    """The epoch seconds of a ledger row's `ts`, or None when it cannot be read."""
    if type(value) is not str or not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z").timestamp()
    except ValueError:
        return None


def daily_spend(
    entries: Sequence[Mapping[str, Any]], *, now: float, window_s: float = DAILY_WINDOW_S
) -> tuple[float, int]:
    """(total spend, rows counted) over the last ``window_s`` of this ledger.

    A row whose timestamp cannot be read is **counted** rather than skipped:
    the ceiling is a safety limit, and the safe direction for an unreadable row
    is to charge it. A row with no spend field contributes nothing either way.
    """
    total = 0.0
    counted = 0
    for row in entries:
        if row.get("kind") not in _SPEND_KINDS:
            continue
        stamp = _row_epoch(row.get("ts"))
        if stamp is not None and stamp < now - window_s:
            continue
        spend = row.get("spend_usd")
        if type(spend) not in {int, float} or isinstance(spend, bool):
            continue
        value = float(cast(float, spend))
        if not math.isfinite(value) or value < 0:
            continue
        total += value
        counted += 1
    return total, counted

