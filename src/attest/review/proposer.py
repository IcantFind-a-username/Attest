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
from threading import Lock
from typing import Any, Protocol

from attest.review.budget import Budget, BudgetExceeded
from attest.review.config import ReviewConfig
from attest.review.dedup import merge_findings
from attest.review.diffs import DiffInfo
from attest.review.schema import PROPOSAL_SCHEMA, Finding, validate_finding

# Preregistered per-sample output-token bound for proposal sampling. It feeds
# BOTH the budget reservation and the provider's max_tokens hard cap, so the
# reserved bound is exactly the enforced bound.
#
# Worst case from PROPOSAL_SCHEMA (schema.py), prompt-capped at 5 findings
# (~1.3 tokens per word of prose):
#   claim               <= 2 sentences, ~20 words each     ~55 tokens
#   anchor              deep file path + line + keys       ~25 tokens
#   failure_scenario    ~50 words of concrete input/state  ~65 tokens
#   falsification_plan  ~50 words                          ~65 tokens
#   JSON syntax         keys/quotes/braces per finding     ~30 tokens
#   per finding                                            ~240 tokens
#   5 findings + {"findings": [...]} envelope (~10)      ~1,210 tokens
# Headroom: 1,210 x 1.25 ~= 1,513, rounded UP to 1,600 (~32%) — truncation
# destroys the JSON and voids the whole sample, so the bound must never clip
# a legitimate maximal response. No dogfood ledger rows with recorded output
# tokens existed at derivation time; the bound is schema-derived only.
#
# Product constraint (default model per pricing.toml: $2/MTok in, $10/MTok
# out; default $0.25 budget; K=5). The K up-front reservations cost
#   5 x (input_chars/3 x $2e-6 + 1,600 x $1e-5)
#     = input_chars x $3.33e-6 + $0.08
# so input_chars may reach (0.25 - 0.08) / 3.33e-6 = 51,000 chars — a diff
# boundary of ~50,150 chars after prompt overhead (754 system prompt + 88
# scaffolding). The old 2,000-token bound put that boundary at 44,158 diff
# chars (5 reservations hit exactly $0.25), making --budget act as a diff-size
# cutoff; a 44,158-char diff now reserves at ~$0.23 with headroom to spare.
PROPOSER_MAX_OUTPUT_TOKENS = 1600

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
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult: ...


class ApiProvider:
    """Messages API provider; model id comes from configuration."""

    def __init__(self, model: str, timeout: float = 120.0):
        self.model = model
        self.timeout = timeout
        self.client: Any | None = None
        self._client_lock = Lock()

    def _client(self) -> Any:
        if self.client is None:
            with self._client_lock:
                if self.client is None:
                    import anthropic

                    self.client = anthropic.Anthropic(timeout=self.timeout)
        return self.client

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        response = self._client().messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
            output_config={"format": {"type": "json_schema", "schema": schema}},
            timeout=self.timeout if timeout_s is None else timeout_s,
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
        if not payloads:
            raise ValueError("mock provider needs at least one payload")
        self.payloads = list(payloads)
        self.calls = 0

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        text = self.payloads[self.calls % len(self.payloads)]
        self.calls += 1
        return ProviderResult(text=text, input_tokens=len(prompt) // 4, output_tokens=200)


@dataclass
class ProposalRun:
    candidates: list[Finding]
    rejected: list[str]  # human-readable rejection reasons (void findings)
    sample_errors: list[str]
    successful_samples: int


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
    reservations: list[float] = []
    try:
        for i in range(k):
            reservations.append(
                budget.reserve(
                    f"sample-{i}", len(SYSTEM_PROMPT) + len(prompt), PROPOSER_MAX_OUTPUT_TOKENS
                )
            )
    except BudgetExceeded:
        for reservation in reservations:
            budget.cancel(reservation)
        raise

    def one(i: int) -> ProviderResult | Exception:
        try:
            return provider.sample(
                SYSTEM_PROMPT, prompt, PROPOSAL_SCHEMA, PROPOSER_MAX_OUTPUT_TOKENS
            )
        except Exception as exc:  # noqa: BLE001 - error becomes a sample failure
            return exc

    with ThreadPoolExecutor(max_workers=k) as pool:
        results = list(pool.map(one, range(k)))

    per_sample: list[list[Finding]] = []
    rejected: list[str] = []
    errors: list[str] = []
    successful_samples = 0
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
        if not isinstance(raw_findings, list):
            errors.append(f"sample {i}: malformed findings collection")
            per_sample.append([])
            continue
        valid: list[Finding] = []
        for raw in raw_findings:
            if not isinstance(raw, dict):
                rejected.append(f"sample {i}: malformed finding")
                continue
            finding, reason = validate_finding(raw, diff)
            if finding is None:
                rejected.append(f"sample {i}: {reason}")
            else:
                valid.append(finding)
        if not raw_findings or valid:
            successful_samples += 1
        else:
            errors.append(f"sample {i}: all findings malformed")
        per_sample.append(valid)

    return ProposalRun(
        candidates=merge_findings(per_sample),
        rejected=rejected,
        sample_errors=errors,
        successful_samples=successful_samples,
    )
