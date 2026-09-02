"""R-02: precommitted recovery of truncated or unusable proposal samples."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from attest.review.budget import Budget
from attest.review.config import ReviewConfig
from attest.review.diffs import parse_diff
from attest.review.proposer import ProviderResult, propose

DIFF = parse_diff(
    "diff --git a/app.py b/app.py\n--- a/app.py\n+++ b/app.py\n"
    "@@ -1,4 +1,4 @@\n def average(items):\n-    if not items:\n-        return 0\n"
    "+    total = sum(items)\n+    count = len(items)\n     return sum(items) / len(items)\n"
)


def _finding(line: int, claim: str, scenario: str) -> dict[str, Any]:
    return {
        "claim": claim,
        "anchor": {"file": "app.py", "line": line},
        "failure_scenario": scenario,
        "falsification_plan": f"plan for line {line}",
    }


class ScriptedProvider:
    """Sample 0 truncates mid-array; sample 1 is unusable, its repair is valid."""

    def __init__(self) -> None:
        self.calls = 0
        full = json.dumps(
            {
                "findings": [
                    _finding(2, "Division by zero on empty input.", "average([]) raises"),
                    _finding(3, "Negative counts corrupt the mean.", "len below one skews"),
                ]
            }
        )
        self.truncated = full[:-2] + ', {"claim": "Overflow that was cut'
        self.repaired = json.dumps(
            {"findings": [_finding(4, "Totals overflow past the limit.", "huge sums wrap")]}
        )

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.calls += 1
        if self.calls == 1:
            return ProviderResult(self.truncated, 10, max_tokens, stop_reason="max_tokens")
        if self.calls == 2:
            return ProviderResult("{", 10, max_tokens, stop_reason="max_tokens")
        return ProviderResult(self.repaired, 10, 50, stop_reason="end_turn")


def test_truncated_sample_is_salvaged_and_unusable_sample_gets_one_cached_repair(
    tmp_path: Path,
) -> None:
    config = ReviewConfig(k_samples=2)
    provider = ScriptedProvider()

    run = propose(
        DIFF, config, Budget(limit_usd=1.0, model=config.model), provider, cache_root=tmp_path
    )

    claims = sorted(finding.claim for finding in run.candidates)
    assert claims == [
        "Division by zero on empty input.",
        "Negative counts corrupt the mean.",
        "Totals overflow past the limit.",
    ]
    assert [o.recovery for o in run.sample_observations] == ["salvaged:2", "repaired"]
    assert provider.calls == 3  # two samples, exactly one repair
    assert run.sample_errors == []

    # the same inputs replay every recorded attempt: no new paid call, same result
    again = propose(
        DIFF, config, Budget(limit_usd=1.0, model=config.model), provider, cache_root=tmp_path
    )
    assert provider.calls == 3
    assert sorted(f.claim for f in again.candidates) == claims


def test_attempt_identity_binds_the_model_and_its_call_parameters() -> None:
    """A changed model or thinking setting is a new paid attempt, never a
    replay of a response bought under different parameters (2026-09-03)."""
    from attest.review.proposer import call_parameters
    from attest.review.recovery import attempt_digest

    base = attempt_digest("s", "p", {}, 100, 0, 0, call_parameters("claude-sonnet-5"))
    assert base != attempt_digest("s", "p", {}, 100, 0, 0)
    assert base != attempt_digest("s", "p", {}, 100, 0, 0, call_parameters("claude-opus-5"))
    assert base != attempt_digest(
        "s", "p", {}, 100, 0, 0, {**call_parameters("claude-sonnet-5"), "thinking": "on"}
    )
    assert base == attempt_digest("s", "p", {}, 100, 0, 0, call_parameters("claude-sonnet-5"))
