from typing import Any

import pytest

from attest.review.budget import Budget
from attest.review.config import ReviewConfig
from attest.review.diffs import parse_diff
from attest.review.proposer import MockProvider, ProviderResult, build_prompt, propose

DIFF = parse_diff(
    """\
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
    budget = Budget(limit_usd=0.25, model="claude-sonnet-5")
    run = propose(DIFF, cfg, budget, ExplodingProvider())
    assert run.candidates == []
    assert len(run.sample_errors) == 3
    assert "TimeoutError" in run.sample_errors[0]
    assert budget.reserved_usd == pytest.approx(0.0)
    assert budget.spent_usd == pytest.approx(0.0)


def test_unparseable_json_is_a_sample_error_but_spend_settles() -> None:
    cfg = ReviewConfig(k_samples=2)
    budget = Budget(limit_usd=0.25, model="claude-sonnet-5")
    run = propose(DIFF, cfg, budget, GarbageProvider())
    assert run.candidates == []
    assert len(run.sample_errors) == 2
    assert "unparseable" in run.sample_errors[0]
    assert budget.spent_usd > 0  # the calls happened; the spend is real


def test_non_list_findings_tolerated() -> None:
    cfg = ReviewConfig(k_samples=1)
    budget = Budget(limit_usd=0.25, model="claude-sonnet-5")
    run = propose(DIFF, cfg, budget, MockProvider(['{"findings": "nope"}']))
    assert run.candidates == []
    assert run.sample_errors == []


def test_build_prompt_contains_diff() -> None:
    assert "risky = 1 / n" in build_prompt(DIFF)
