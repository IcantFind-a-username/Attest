"""The proposer: K parallel samples from a single model, schema-constrained.

A single model sampled K times is a CORRELATED panel — downstream, votes are
discounted accordingly (channels.py). The provider seam exists so tests replay
canned samples; the real provider resolves credentials through the SDK's
standard environment chain (BYOK).
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Protocol

from attest.review.budget import Budget
from attest.review.config import ReviewConfig
from attest.review.dedup import merge_findings
from attest.review.diffs import DiffInfo
from attest.review.schema import PROPOSAL_SCHEMA, Finding, validate_finding

MAX_OUTPUT_TOKENS = 2000

SYSTEM_PROMPT = """You are a code reviewer that reports ONLY high-severity defects: crashes, \
data loss or corruption, security vulnerabilities, and logic errors with real consequences. \
No style comments, no maybes, no full coverage. If nothing rises to that bar, return an \
empty findings list — silence is the correct answer far more often than not.

For each finding, all four pieces are mandatory:
- claim: at most 2 sentences stating the defect
- anchor: file path (as it appears in the diff, after the +++ b/ prefix) and a NEW-file \
line number that falls inside one of the diff hunks
- failure_scenario: the concrete input or state under which it breaks
- falsification_plan: how a skeptic would check whether your claim is wrong

Report at most 5 findings, best first."""


@dataclass
class ProviderResult:
    text: str
    input_tokens: int
    output_tokens: int


class Provider(Protocol):
    def sample(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int
    ) -> ProviderResult: ...


class ApiProvider:
    """Messages API provider; model id comes from configuration."""

    def __init__(self, model: str, timeout: float = 120.0):
        import anthropic

        self.model = model
        self.client = anthropic.Anthropic(timeout=timeout)

    def sample(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int
    ) -> ProviderResult:
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
        )
        text = next((b.text for b in response.content if b.type == "text"), "{}")
        return ProviderResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


class MockProvider:
    """Replays canned JSON payloads; for tests and offline dry runs."""

    def __init__(self, payloads: list[str]):
        self.payloads = list(payloads)
        self.calls = 0

    def sample(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int
    ) -> ProviderResult:
        text = self.payloads[self.calls % len(self.payloads)]
        self.calls += 1
        return ProviderResult(text=text, input_tokens=len(prompt) // 4, output_tokens=200)


@dataclass
class ProposalRun:
    candidates: list[Finding]
    rejected: list[str]  # human-readable rejection reasons (void findings)
    sample_errors: list[str]


def build_prompt(diff: DiffInfo) -> str:
    return (
        "Review this diff. Anchors must use new-file line numbers inside the hunks.\n\n"
        "```diff\n" + diff.text + "\n```"
    )


def propose(
    diff: DiffInfo, config: ReviewConfig, budget: Budget, provider: Provider
) -> ProposalRun:
    """K parallel samples -> validate four-piece schema -> merge into candidates."""
    prompt = build_prompt(diff)
    k = config.k_samples
    reservations = [
        budget.reserve(f"sample-{i}", len(SYSTEM_PROMPT) + len(prompt), MAX_OUTPUT_TOKENS)
        for i in range(k)
    ]

    def one(i: int) -> ProviderResult | Exception:
        try:
            return provider.sample(SYSTEM_PROMPT, prompt, PROPOSAL_SCHEMA, MAX_OUTPUT_TOKENS)
        except Exception as exc:  # noqa: BLE001 - error becomes a sample failure
            return exc

    with ThreadPoolExecutor(max_workers=k) as pool:
        results = list(pool.map(one, range(k)))

    per_sample: list[list[Finding]] = []
    rejected: list[str] = []
    errors: list[str] = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            budget.cancel(reservations[i])
            errors.append(f"sample {i}: {type(res).__name__}: {res}")
            per_sample.append([])
            continue
        budget.settle(f"sample-{i}", reservations[i], res.input_tokens, res.output_tokens)
        try:
            payload = json.loads(res.text)
            raw_findings = payload.get("findings", [])
        except (json.JSONDecodeError, AttributeError):
            errors.append(f"sample {i}: unparseable JSON")
            per_sample.append([])
            continue
        valid: list[Finding] = []
        for raw in raw_findings if isinstance(raw_findings, list) else []:
            finding, reason = validate_finding(raw, diff)
            if finding is None:
                rejected.append(f"sample {i}: {reason}")
            else:
                valid.append(finding)
        per_sample.append(valid)

    return ProposalRun(
        candidates=merge_findings(per_sample), rejected=rejected, sample_errors=errors
    )
