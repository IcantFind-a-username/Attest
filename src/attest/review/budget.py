"""Hard per-review budget: preflight estimate, pre-debit, explicit DEFER.

Every model call is estimated BEFORE it happens; if the projected total would
exceed the budget, the call is not made and the review defers with the reason.
Actual usage replaces the estimate once known.
"""

from __future__ import annotations

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
        pricing = load_pricing()
        try:
            m = pricing["models"][self.model]
        except KeyError:
            raise ValueError(f"no pricing for model {self.model!r}") from None
        self._prices = {
            "in": float(m["input_per_mtok"]) / 1e6,
            "out": float(m["output_per_mtok"]) / 1e6,
        }

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

    def settle(self, label: str, reserved: float, input_tokens: int, output_tokens: int) -> float:
        """Replace a reservation with actual usage-based cost."""
        actual = input_tokens * self._prices["in"] + output_tokens * self._prices["out"]
        self.reserved_usd = max(0.0, self.reserved_usd - reserved)
        self.spent_usd += actual
        self.calls.append(
            {
                "label": label,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": actual,
            }
        )
        return actual

    def cancel(self, reserved: float) -> None:
        self.reserved_usd = max(0.0, self.reserved_usd - reserved)
