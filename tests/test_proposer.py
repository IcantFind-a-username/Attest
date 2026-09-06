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
    provider.client = SimpleNamespace(messages=SimpleNamespace(create=lambda **_kwargs: response))

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


# The conservative default-budget boundary after reserving 3,200 output tokens
# for all five calls is about 26,000 diff characters (proposer.py). Keep the
# fixture below that bound while exercising a much larger input than the live
# truncation case that motivated the increase.
LARGE_DIFF_CHARS = 25_000


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
    header = "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n@@ -1,1 +1,2 @@\n context\n"
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


def test_thinking_only_response_is_generation_no_text_not_a_schema_mismatch() -> None:
    """Fix 1 (2026-09-03): a response whose only block is thinking, stopped at
    max_tokens, is reported as generation_no_text with its stop reason and block
    types; the provider never invents a ``{}`` document, and structured
    generation asks the model for text, not reasoning."""
    provider = ApiProvider("claude-sonnet-5")
    captured: dict[str, Any] = {}
    response = SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking="")],
        usage=SimpleNamespace(input_tokens=6201, output_tokens=3000),
        stop_reason="max_tokens",
    )

    def create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return response

    provider.client = SimpleNamespace(messages=SimpleNamespace(create=create))

    result = provider.sample("system", "prompt", {}, 3000)

    assert result.text is None
    assert result.content_types == ("thinking",)
    assert captured["thinking"] == {"type": "disabled"}
    run = propose(
        DIFF,
        ReviewConfig(k_samples=1),
        Budget(limit_usd=0.25, model=DEFAULT_MODEL),
        provider,
    )
    assert run.successful_samples == 0
    assert run.sample_observations[0].recovery == "no_text"
    assert run.sample_observations[0].stop_reason == "max_tokens"
    assert any("generation_no_text" in error for error in run.sample_errors)
    assert not any("schema" in error for error in run.sample_errors)
    assert not any("{}" in error for error in run.sample_errors)


def test_always_on_thinking_models_get_low_effort_instead_of_disabled() -> None:
    provider = ApiProvider("claude-fable-5-1")
    captured: dict[str, Any] = {}
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"findings": []}')],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        stop_reason="end_turn",
    )

    def create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        return response

    provider.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    provider.sample("system", "prompt", {"type": "object"}, 100)
    assert "thinking" not in captured
    assert captured["output_config"]["effort"] == "low"
    assert captured["output_config"]["format"]["type"] == "json_schema"


class NoTextThenEmptyProvider:
    """Sample 0 carries no text block; sample 1 is the model's own empty list."""

    def __init__(self) -> None:
        self.calls = 0

    def sample(self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int):
        self.calls += 1
        if self.calls == 1:
            return ProviderResult(
                text=None,
                input_tokens=10,
                output_tokens=max_tokens,
                stop_reason="max_tokens",
                content_types=("thinking",),
            )
        return ProviderResult(
            text='{"findings": []}', input_tokens=10, output_tokens=5, stop_reason="end_turn"
        )


def test_no_text_and_empty_findings_are_counted_apart() -> None:
    """Fix 2 (2026-09-03): only the model's own empty findings list is an
    abstention; a response without text is a generation failure."""
    run = propose(
        DIFF,
        ReviewConfig(k_samples=2),
        Budget(limit_usd=0.25, model=DEFAULT_MODEL),
        NoTextThenEmptyProvider(),
    )
    recoveries = sorted(observation.recovery for observation in run.sample_observations)
    assert recoveries == ["empty", "no_text"]
    assert run.successful_samples == 1
    assert run.candidates == []


def test_api_provider_marks_cache_breakpoints_and_streams_until_the_first_token() -> None:
    """Owner instruction 3 (2026-09-03): the system prompt and the shared
    prefix of the user prompt carry cache_control; the variable remainder
    follows them; with a first-token callback the request streams and the
    callback fires on the first content delta; cache usage is reported."""
    provider = ApiProvider("claude-sonnet-5")
    captured: dict[str, Any] = {}
    events = [SimpleNamespace(type="message_start"), SimpleNamespace(type="content_block_delta")]
    final = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"findings": []}')],
        usage=SimpleNamespace(
            input_tokens=7,
            output_tokens=3,
            cache_creation_input_tokens=0,
            cache_read_input_tokens=1500,
        ),
        stop_reason="end_turn",
    )

    class Stream:
        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def __iter__(self) -> Any:
            return iter(events)

        def get_final_message(self) -> Any:
            return final

    def stream(**kwargs: Any) -> Stream:
        captured.update(kwargs)
        return Stream()

    provider.client = SimpleNamespace(messages=SimpleNamespace(stream=stream, create=None))
    fired: list[str] = []
    result = provider.sample(
        "system",
        "SHARED-PART variable tail",
        {},
        100,
        shared_prefix="SHARED-PART",
        on_first_token=lambda: fired.append("first"),
    )

    assert fired == ["first"]
    assert captured["system"] == [
        {"type": "text", "text": "system", "cache_control": {"type": "ephemeral"}}
    ]
    assert captured["messages"][0]["content"] == [
        {"type": "text", "text": "SHARED-PART", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": " variable tail"},
    ]
    assert result.cache_read_input_tokens == 1500
    assert result.input_tokens == 7


class StaggeringProvider:
    """Records when each sample starts; the first sample's first token arrives
    after a short delay, so a correct fan-out starts the others after it."""

    supports_cache_control = True

    def __init__(self) -> None:
        self.starts: list[tuple[float, bool]] = []  # (time, had_first_token_callback)
        self.first_token_at: float | None = None
        self._lock = __import__("threading").Lock()

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
        shared_prefix: str = "",
        on_first_token: Any = None,
        shared_system: str = "",
    ) -> ProviderResult:
        import time

        with self._lock:
            self.starts.append((time.monotonic(), on_first_token is not None))
        if on_first_token is not None:
            time.sleep(0.2)
            with self._lock:
                self.first_token_at = time.monotonic()
            on_first_token()
        read = 0 if on_first_token is not None else 1000
        return ProviderResult(
            text='{"findings": []}',
            input_tokens=10,
            output_tokens=5,
            stop_reason="end_turn",
            cache_creation_input_tokens=1000 - read,
            cache_read_input_tokens=read,
        )


def test_second_sample_starts_after_the_first_token_and_pays_cache_read_prices() -> None:
    """The RED for owner instruction 3 at the unit level: sample 0 goes alone,
    samples 1..K-1 start only after its first token, their cache reads are
    priced at the read rate, and the run costs less than four cold samples."""
    provider = StaggeringProvider()
    budget = Budget(limit_usd=0.25, model=DEFAULT_MODEL)
    run = propose(DIFF, ReviewConfig(k_samples=4), budget, provider)

    assert run.successful_samples == 4
    assert provider.first_token_at is not None
    later = [start for start, first in provider.starts if not first]
    assert len(later) == 3 and all(start >= provider.first_token_at for start in later)
    reads = [obs.cache_read_input_tokens for obs in run.sample_observations]
    assert sorted(reads) == [0, 1000, 1000, 1000]
    cold = Budget(limit_usd=0.25, model=DEFAULT_MODEL)
    for i in range(4):
        cold.settle(f"cold-{i}", 0.0, 1010, 5)
    assert budget.spent_usd < cold.spent_usd
    assert budget.calls[1]["cache_read_input_tokens"] == 1000


def test_shared_system_block_leads_every_role_request_identically() -> None:
    """Owner instruction 4: the shared block is the first system block, with
    its own cache breakpoint, byte-identical whichever role instruction
    follows it, so proposals and generations read one cache entry."""
    provider = ApiProvider("claude-sonnet-5")
    captured: list[dict[str, Any]] = []
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"findings": []}')],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1),
        stop_reason="end_turn",
    )

    def create(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return response

    provider.client = SimpleNamespace(messages=SimpleNamespace(create=create))
    block = "Shared repository context: package and tests"
    provider.sample("proposer role", "p", {}, 10, shared_system=block)
    provider.sample("generator role", "g", {}, 10, shared_system=block)

    first = [call["system"][0] for call in captured]
    assert (
        first[0]
        == first[1]
        == {
            "type": "text",
            "text": block,
            "cache_control": {"type": "ephemeral"},
        }
    )
    assert [call["system"][1]["text"] for call in captured] == ["proposer role", "generator role"]


def test_the_discovery_share_bounds_breadth_including_the_first_unit() -> None:
    """D-111: what starved verification on `d7be758` was *breadth* -- twelve
    candidates from four change units -- so the proposal stage is bought inside
    a share of the budget.

    D-168 lowered that share to 30% and removed D-111's exemption for the first
    unit. The exemption existed because a review that cannot afford to read one
    change unit has nothing to say; the 2026-09-07 budget re-run showed its cost,
    which is that discovery may take the whole budget and leave verification
    nothing, silently. The first unit is now bought inside the share like every
    other, and a first unit that does not fit raises `BudgetExceeded` for the
    caller to turn into a stated budget DEFER.

    Two units, a $1.00 budget and K=5: the first fits inside $0.30 and the
    second does not, so the review reads one unit and says so."""
    from types import SimpleNamespace

    from attest.review.budget import PROPOSAL_SHARE, Budget, BudgetExceeded
    from attest.review.config import ReviewConfig
    from attest.review.diffs import DiffInfo
    from attest.review.proposer import ProviderResult, propose_plan

    class Abstaining:
        """Abstains, and bills for it: the share bounds *spend*, so a sample
        that costs nothing can never demonstrate the bound."""

        def __init__(self, output_tokens: int = 3200) -> None:
            self.calls = 0
            self.output_tokens = output_tokens

        def sample(
            self,
            system: str,
            prompt: str,
            schema: dict[str, object],
            max_tokens: int,
            *,
            timeout_s: float | None = None,
        ) -> ProviderResult:
            self.calls += 1
            return ProviderResult(
                text='{"findings": []}', input_tokens=10, output_tokens=self.output_tokens
            )

    def unit(unit_id: str) -> SimpleNamespace:
        return SimpleNamespace(
            unit_id=unit_id,
            files=[f"{unit_id}.py"],
            diff=lambda: DiffInfo(text="@@ -1 +1 @@\n-a\n+b\n"),
            prompt_context=lambda: "",
        )

    config = ReviewConfig(budget_usd=1.00, k_samples=5, tier0_commands=[])
    assert (config.budget_usd, config.k_samples) == (1.00, 5)
    assert PROPOSAL_SHARE == 0.3
    budget = Budget(limit_usd=config.budget_usd, model=config.model)
    provider = Abstaining()

    run = propose_plan(
        SimpleNamespace(units=[unit("first"), unit("second")]),  # type: ignore[arg-type]
        config,
        budget,
        provider,
    )

    # the first unit fits inside the share and spends $0.16 of it; the second
    # unit's reservation would take the stage past $0.30, so it is omitted --
    # visibly, and with the share named in the reason
    assert run.units_read == 1
    assert provider.calls == config.k_samples
    assert len(run.omitted_units) == 1
    assert "second" in run.omitted_units[0]
    assert f"${config.budget_usd * PROPOSAL_SHARE:.4f}" in run.omitted_units[0]
    assert budget.spent_usd <= config.budget_usd * PROPOSAL_SHARE

    # and a first unit that does not fit the share is a BudgetExceeded the
    # caller turns into a stated budget DEFER, not a silent partial read
    tight = ReviewConfig(budget_usd=0.25, k_samples=5, tier0_commands=[])
    with pytest.raises(BudgetExceeded) as refused:
        propose_plan(
            SimpleNamespace(units=[unit("only")]),  # type: ignore[arg-type]
            tight,
            Budget(limit_usd=tight.budget_usd, model=tight.model),
            Abstaining(),
        )
    assert "discovery share" in refused.value.reason

def test_a_provider_error_never_carries_a_credential_into_author_visible_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A revoked-credential outage echoes the key it rejected. That text becomes
    a note, a DEFER reason and a pull-request comment, so it is redacted and
    bounded before it leaves the provider boundary."""
    from attest.review.proposer import redacted_error

    secret = "sk-ant-test-1111111111111111111111111111"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)

    detail = redacted_error(RuntimeError(f"401 authentication_error: invalid x-api-key {secret}"))

    assert secret not in detail
    assert "401 authentication_error" in detail
    assert len(redacted_error(RuntimeError("x" * 5000))) < 600
