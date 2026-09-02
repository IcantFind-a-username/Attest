"""Hard per-review budget: preflight estimate, pre-debit, explicit DEFER.

Every model call is estimated BEFORE it happens; if the projected total would
exceed the budget, the call is not made and the review defers with the reason.
Actual usage replaces the estimate once known.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from attest.review.config import load_pricing

# rough chars-per-token for preflight estimates (conservative: low divisor
# overestimates tokens and cost)
CHARS_PER_TOKEN = 3.0


@dataclass
class BudgetExceeded(Exception):
    reason: str


@dataclass
class Budget:
    limit_usd: float
    model: str
    spent_usd: float = 0.0
    reserved_usd: float = 0.0
    calls: list[dict[str, Any]] = field(default_factory=list)
    _prices: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if (
            isinstance(self.limit_usd, bool)
            or not isinstance(self.limit_usd, (int, float))
            or not math.isfinite(self.limit_usd)
            or self.limit_usd <= 0
        ):
            raise ValueError("budget limit must be a finite positive number")
        pricing = load_pricing()
        try:
            m = pricing["models"][self.model]
        except KeyError:
            raise ValueError(f"no pricing for model {self.model!r}") from None
        self._prices = {
            "in": float(m["input_per_mtok"]) / 1e6,
            "out": float(m["output_per_mtok"]) / 1e6,
        }
        self._prices["cache_write"] = self._prices["in"] * float(
            pricing.get("cache_write_multiplier", 1.25)
        )
        self._prices["cache_read"] = self._prices["in"] * float(
            pricing.get("cache_read_multiplier", 0.10)
        )

    def estimate_cost(self, input_chars: int, max_output_tokens: int) -> float:
        in_tokens = input_chars / CHARS_PER_TOKEN
        return in_tokens * self._prices["in"] + max_output_tokens * self._prices["out"]

    def reserve(self, label: str, input_chars: int, max_output_tokens: int) -> float:
        """Pre-debit a planned call; raises BudgetExceeded instead of calling."""
        est = self.estimate_cost(input_chars, max_output_tokens)
        projected = self.spent_usd + self.reserved_usd + est
        if projected > self.limit_usd:
            raise BudgetExceeded(
                f"call '{label}' estimated ${est:.4f}; projected total "
                f"${projected:.4f} exceeds budget ${self.limit_usd:.2f}"
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
    ) -> float:
        """Replace a reservation with actual usage-based cost. ``input_tokens``
        is the uncached remainder; cache writes and reads are priced apart."""
        actual = (
            input_tokens * self._prices["in"]
            + cache_creation_input_tokens * self._prices["cache_write"]
            + cache_read_input_tokens * self._prices["cache_read"]
            + output_tokens * self._prices["out"]
        )
        self.reserved_usd = max(0.0, self.reserved_usd - reserved)
        self.spent_usd += actual
        self.calls.append(
            {
                "label": label,
                "input_tokens": input_tokens,
                "cache_creation_input_tokens": cache_creation_input_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": actual,
            }
        )
        return actual

    def cancel(self, reserved: float) -> None:
        self.reserved_usd = max(0.0, self.reserved_usd - reserved)
