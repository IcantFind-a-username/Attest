import math
from typing import Any

import pytest

from attest.review.budget import CHARS_PER_TOKEN, Budget
from attest.review.config import ReviewConfig, load_pricing
from attest.review.diffs import DiffInfo, parse_diff
from attest.review.proposer import (
    PROPOSER_MAX_OUTPUT_TOKENS,
    MockProvider,
    ProviderResult,
    build_prompt,
    propose,
)

DEFAULT_MODEL = str(load_pricing()["default_model"])

DIFF = parse_diff(
    """\
diff --git a/app.py b/app.py
--- a/app.py
+++ b/app.py
@@ -5,3 +5,4 @@
 context
+risky = 1 / n
 context
 context
"""
)


class ExplodingProvider:
    def sample(self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int):
        raise TimeoutError("provider timed out")


class GarbageProvider:
    def sample(self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int):
        return ProviderResult(text="{not json", input_tokens=10, output_tokens=10)


def test_provider_errors_cancel_reservations() -> None:
    cfg = ReviewConfig(k_samples=3)
    budget = Budget(limit_usd=0.25, model=DEFAULT_MODEL)
    run = propose(DIFF, cfg, budget, ExplodingProvider())
    assert run.candidates == []
    assert len(run.sample_errors) == 3
    assert "TimeoutError" in run.sample_errors[0]
    assert budget.reserved_usd == pytest.approx(0.0)
    assert budget.spent_usd == pytest.approx(0.0)
    assert run.successful_samples == 0


def test_unparseable_json_is_a_sample_error_but_spend_settles() -> None:
    cfg = ReviewConfig(k_samples=2)
    budget = Budget(limit_usd=0.25, model=DEFAULT_MODEL)
    run = propose(DIFF, cfg, budget, GarbageProvider())
    assert run.candidates == []
    assert len(run.sample_errors) == 2
    assert "unparseable" in run.sample_errors[0]
    assert budget.spent_usd > 0  # the calls happened; the spend is real
    assert run.successful_samples == 0


def test_non_list_findings_tolerated() -> None:
    cfg = ReviewConfig(k_samples=1)
    budget = Budget(limit_usd=0.25, model=DEFAULT_MODEL)
    run = propose(DIFF, cfg, budget, MockProvider(['{"findings": "nope"}']))
    assert run.candidates == []
    assert run.sample_errors
    assert run.successful_samples == 0


def test_valid_empty_sample_is_successful() -> None:
    run = propose(
        DIFF,
        ReviewConfig(k_samples=1),
        Budget(limit_usd=0.25, model=DEFAULT_MODEL),
        MockProvider(['{"findings": []}']),
    )

    assert run.candidates == []
    assert run.successful_samples == 1


def test_build_prompt_contains_diff() -> None:
    assert "risky = 1 / n" in build_prompt(DIFF)


# The representative case from the PROPOSER_MAX_OUTPUT_TOKENS derivation
# (proposer.py): 44,158 ASCII diff chars was the DEFER boundary under the old
# 2,000-token bound (5 reservations hit exactly $0.25); the preregistered
# bound must clear it with headroom and push the boundary to ~50,150 chars.
OLD_BOUNDARY_DIFF_CHARS = 44_158


class WorstCaseProvider:
    """Records max_tokens and settles every sample at the preregistered worst
    case: estimate-sized input, a full PROPOSER_MAX_OUTPUT_TOKENS of output."""

    def __init__(self) -> None:
        self.max_tokens_seen: list[int] = []

    def sample(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int
    ) -> ProviderResult:
        self.max_tokens_seen.append(max_tokens)
        return ProviderResult(
            text='{"findings": []}',
            input_tokens=math.ceil((len(system) + len(prompt)) / CHARS_PER_TOKEN),
            output_tokens=PROPOSER_MAX_OUTPUT_TOKENS,
        )


def ascii_diff(total_chars: int) -> DiffInfo:
    """Single-hunk ASCII diff padded to exactly total_chars characters."""
    header = (
        "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
        "@@ -1,1 +1,2 @@\n context\n"
    )
    text = header + "+" + "x" * (total_chars - len(header) - 2) + "\n"
    assert len(text) == total_chars
    return parse_diff(text)


def test_default_budget_reserves_old_boundary_diff() -> None:
    cfg = ReviewConfig()  # factory defaults: $0.25, K=5, default-model pricing
    budget = Budget(limit_usd=cfg.budget_usd, model=cfg.model)
    # must not raise BudgetExceeded at the old DEFER boundary
    run = propose(ascii_diff(OLD_BOUNDARY_DIFF_CHARS), cfg, budget, WorstCaseProvider())
    assert run.sample_errors == []
    assert len(budget.calls) == cfg.k_samples
    # well past the old boundary, inside the new ~50,150-char one
    budget2 = Budget(limit_usd=cfg.budget_usd, model=cfg.model)
    propose(ascii_diff(48_000), cfg, budget2, WorstCaseProvider())


def test_maximal_settled_response_stays_within_budget() -> None:
    cfg = ReviewConfig()
    budget = Budget(limit_usd=cfg.budget_usd, model=cfg.model)
    propose(ascii_diff(OLD_BOUNDARY_DIFF_CHARS), cfg, budget, WorstCaseProvider())
    assert budget.reserved_usd == pytest.approx(0.0)
    assert all(c["output_tokens"] == PROPOSER_MAX_OUTPUT_TOKENS for c in budget.calls)
    assert budget.spent_usd <= cfg.budget_usd


def test_provider_receives_preregistered_output_bound() -> None:
    """Reserved bound == enforced bound: the same constant feeds both the
    budget reservation and the provider's max_tokens hard cap."""
    cfg = ReviewConfig(k_samples=3)
    budget = Budget(limit_usd=cfg.budget_usd, model=cfg.model)
    provider = WorstCaseProvider()
    propose(DIFF, cfg, budget, provider)
    assert provider.max_tokens_seen == [PROPOSER_MAX_OUTPUT_TOKENS] * 3
