import math
from types import SimpleNamespace
from typing import Any

import pytest

from attest.review.budget import CHARS_PER_TOKEN, Budget
from attest.review.config import ReviewConfig, load_pricing
from attest.review.diffs import DiffInfo, parse_diff
from attest.review.proposer import (
    PROPOSER_MAX_OUTPUT_TOKENS,
    ApiProvider,
    MockProvider,
    ProviderResult,
    build_prompt,
    propose,
    response_fragment,
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
    assert run.sample_observations[0].stop_reason == "not_recorded"
    assert run.sample_observations[0].output_tokens == 10
    assert 'raw="{not json"' in run.sample_errors[0]


def test_response_fragment_is_bounded_and_redacts_known_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "credential-value-that-must-not-be-recorded"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)

    fragment = response_fragment(secret + "x" * 600)

    assert secret not in fragment
    assert "[REDACTED]" in fragment
    assert "[truncated]" in fragment


def test_api_provider_records_stop_reason_and_actual_output_tokens() -> None:
    provider = ApiProvider("test-model")
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"findings": []}')],
        usage=SimpleNamespace(input_tokens=11, output_tokens=17),
        stop_reason="max_tokens",
    )
    provider.client = SimpleNamespace(
        messages=SimpleNamespace(create=lambda **_kwargs: response)
    )

    result = provider.sample("system", "prompt", {}, 20)

    assert result.stop_reason == "max_tokens"
    assert result.output_tokens == 17


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


# The conservative default-budget boundary after reserving 2,400 output tokens
# for all five calls is about 38,150 diff characters (proposer.py). Keep the
# fixture below that bound while exercising a much larger input than the live
# truncation case that motivated the increase.
LARGE_DIFF_CHARS = 37_000


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


def test_default_budget_reserves_documented_large_diff() -> None:
    cfg = ReviewConfig()  # factory defaults: $0.25, K=5, default-model pricing
    budget = Budget(limit_usd=cfg.budget_usd, model=cfg.model)
    run = propose(ascii_diff(LARGE_DIFF_CHARS), cfg, budget, WorstCaseProvider())
    assert run.sample_errors == []
    assert len(budget.calls) == cfg.k_samples


def test_maximal_settled_response_stays_within_budget() -> None:
    cfg = ReviewConfig()
    budget = Budget(limit_usd=cfg.budget_usd, model=cfg.model)
    propose(ascii_diff(LARGE_DIFF_CHARS), cfg, budget, WorstCaseProvider())
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
