"""The cumulative cap a paid driver runs under, with the reservation it was missing.

Every corpus driver holds a `--cap`: the total this run may spend across all its
units, set from the reservation recorded in `DEVSPEND.md`. Until now each of them
gated a unit on **spend so far**::

    if spent >= args.cap:      # skip

which reads the cap as *"stop once it is already broken"*. On 2026-09-07 that cost
real money and is on the record: `us-stock-helper`'s sixth unit began at $3.25
against a $3.50 cap, ran a `--budget 1.00` review, and ended the run at $4.12 --
$0.62 over the item's cumulative cap and $0.32 over the window's reservation. No
unit misbehaved; the rule did. A cap that gates *starting* on money already spent
cannot bound a run whose next unit may cost up to the per-review budget.

This module holds the cap the other way round, the way `attest`'s own `Budget`
holds a review's: a unit may start only when its **maximum** cost still fits.

    spent + reserved + reservation <= cap

The reservation was the per-review `--budget`, because that is exactly what one
unit may cost -- the product's own hard ceiling. Since D-244 it is the 95th
percentile of the most recent forty cases' spend, bounded by that ceiling: the
ceiling refused the last three of forty at $2.53 of a $3.50 cap on 2026-09-13. It is
held while the unit runs and replaced by the actual
spend afterwards. Two consequences, both deliberate:

* a run **stops one unit earlier** than it used to, and the units it did not
  attempt are named rather than silently dropped -- an unattempted unit is a
  smaller `n`, which is reportable, where an overrun is not reversible;
* a unit whose actual spend could not be read is **charged the reservation**.
  The safe direction for an unknown cost is to charge it, the same convention
  `Budget.daily_spend` already uses for a ledger row it cannot parse.

Pure arithmetic: no clock, no I/O, no provider. The drivers own the loop; this
owns the one number that must not slip.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# D-172. The overrun this replaces is on the record in DEVSPEND.md.
# D-244 (owner instruction of 2026-09-14): the reservation is the recent
# history's 95th percentile, not the ceiling -- see `reservation_from_history`.
DRIVER_CAP_POLICY_VERSION = "attest.driver-cap.reserve-p95.v2"
HISTORY_CASES = 40  # the most recent cases whose spend the reservation is read from
MINIMUM_HISTORY = 10  # fewer than this and the ceiling stands
MINIMUM_RESERVATION = 0.01


def reservation_from_history(spends: list[float], *, fallback: float) -> float:
    """What one unit is reserved at: the 95th percentile of the most recent
    ``HISTORY_CASES`` spends, bounded by a cent and by the ceiling (D-244).

    D-172 reserved every unit at its ceiling, the per-review budget, because
    that is what one unit *may* cost. Under a cumulative cap that reservation
    is what admits the next unit, and on 2026-09-13 it refused the last three of
    forty at $2.53 of a $3.50 cap when no case of the forty had cost more than
    $0.18. The ceiling still binds what a unit may spend -- the review's own
    `Budget` holds it -- so the cap can still be overshot by at most one unit's
    distance between its p95 and its ceiling, and the run records which unit.
    With fewer than ``MINIMUM_HISTORY`` cases of history the ceiling stands.
    """
    fallback = _finite(fallback, "fallback")
    recent = [_finite(value, "spend") for value in spends][-HISTORY_CASES:]
    if len(recent) < MINIMUM_HISTORY:
        return fallback
    ordered = sorted(recent)
    # nearest-rank 95th percentile: the smallest value at or above 95% of the sample
    rank = max(1, math.ceil(0.95 * len(ordered)))
    p95 = ordered[rank - 1]
    return max(MINIMUM_RESERVATION, min(fallback, p95))


def recent_spends(rows: list[dict], *, limit: int = HISTORY_CASES) -> list[float]:
    """The ``spend_usd`` of the most recent ``limit`` trial rows by ``recorded_at``."""
    dated = [
        (str(row.get("recorded_at") or ""), float(row.get("spend_usd") or 0.0))
        for row in rows
        if isinstance(row, dict)
    ]
    dated.sort()
    return [spend for _at, spend in dated[-limit:]]


def _finite(value: float, label: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < minimum:
        raise ValueError(f"{label} must be a finite number >= {minimum:g}")
    return number


@dataclass
class DriverCap:
    """The cumulative cap of one paid run, reserving each unit's maximum cost."""

    cap: float
    reservation_usd: float  # what one unit may cost: the per-review `--budget`
    spent: float = 0.0
    reserved: float = 0.0
    started: int = 0
    refused: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.cap = _finite(self.cap, "cap")
        self.reservation_usd = _finite(self.reservation_usd, "reservation_usd")
        self.spent = _finite(self.spent, "spent")

    @property
    def committed(self) -> float:
        return self.spent + self.reserved

    def refusal(self, unit: str = "") -> str | None:
        """Why this unit may not start, or None when its maximum still fits."""
        projected = self.committed + self.reservation_usd
        if projected <= self.cap:
            return None
        name = f"unit {unit}: " if unit else ""
        return (
            f"{name}skipped: cumulative cap: ${self.spent:.4f} spent"
            + (f" + ${self.reserved:.4f} reserved" if self.reserved else "")
            + f", reserving ${self.reservation_usd:.4f} for this unit would project "
            f"${projected:.4f} past the ${self.cap:.2f} cap"
        )

    def start(self, unit: str = "") -> bool:
        """Reserve this unit's maximum. False (and nothing reserved) when it does not fit."""
        reason = self.refusal(unit)
        if reason is not None:
            self.refused.append(reason)
            return False
        self.reserved += self.reservation_usd
        self.started += 1
        return True

    def settle(self, actual: float | None) -> float:
        """Replace the reservation with what the unit actually cost.

        ``None`` -- the driver could not read a spend line -- is charged the full
        reservation rather than nothing: an unreadable cost is not a free one."""
        charge = self.reservation_usd if actual is None else _finite(actual, "actual")
        self.reserved = max(0.0, self.reserved - self.reservation_usd)
        self.spent += charge
        return charge

    def summary(self) -> str:
        return (
            f"cap ${self.cap:.2f}; reservation ${self.reservation_usd:.4f} per unit; "
            f"started {self.started}; refused {len(self.refused)}; "
            f"spent ${self.spent:.6f}"
        )
