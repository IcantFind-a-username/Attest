"""The proposer: K parallel samples from a single model, schema-constrained.

A single model sampled K times is a CORRELATED panel — downstream, votes are
discounted accordingly (channels.py). The provider seam exists so tests replay
canned samples; the real provider resolves credentials through the SDK's
standard environment chain (BYOK).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event, Lock
from typing import Any, Protocol

from attest.review.budget import Budget, BudgetExceeded
from attest.review.config import ReviewConfig
from attest.review.dedup import cluster_findings
from attest.review.diffs import DiffInfo
from attest.review.ledger import redact_known_secrets
from attest.review.planner import ReviewPlan
from attest.review.recovery import (
    MODEL_REPAIR_ATTEMPTS,
    AttemptCache,
    CachedAttempt,
    attempt_digest,
    salvage_findings,
)
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
# Visible-schema headroom alone put the original bound at 1,600. The first
# stop-reason-instrumented live observation then saw 4/20 proposal calls stop
# at that bound, all on one 2,348-input-token diff, while a valid response from
# the same case used 1,539 output tokens. The provider's adaptive reasoning
# also consumes this allowance even when the reasoning text is not returned.
# Add 50% measured headroom: 1,600 x 1.5 = 2,400. This remains a hard cap;
# truncation destroys the JSON and voids the whole sample.
#
# Product constraint (default model per pricing.toml: $2/MTok in, $10/MTok
# out; default $0.25 budget; K=5). The K up-front reservations cost
#   5 x (input_chars/3 x $2e-6 + 2,400 x $1e-5)
#     = input_chars x $3.33e-6 + $0.12
# so input_chars may reach (0.25 - 0.12) / 3.33e-6 = 39,000 chars — a diff
# boundary of ~38,150 chars after prompt overhead. That explicit conservative
# boundary is the cost of reserving the provider-enforced allowance up front.
#
# 2026-09-02 (owner, after the dev-slice re-run): on the eight regression PRs 9 of
# the 13 empty proposal samples had stopped at the 2,400 bound with the allowance
# consumed by reasoning, so the bound is raised to 3,200. It is a runtime output
# parameter, not a statistical constant; the reservation arithmetic above now
# reads 5 x (input_chars/3 x $2e-6 + 3,200 x $1e-5) = input_chars x $3.33e-6 +
# $0.16, a default-budget diff boundary of about 26,000 chars.
PROPOSER_MAX_OUTPUT_TOKENS = 3200
MAX_RESPONSE_FRAGMENT_CHARS = 500

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
    text: str | None  # None when the response carried no text block at all
    input_tokens: int  # the uncached remainder of the prompt
    output_tokens: int
    stop_reason: str | None = None
    content_types: tuple[str, ...] = ("text",)  # block types the response carried, in order
    cache_creation_input_tokens: int = 0  # prompt tokens written to the cache (1.25x)
    cache_read_input_tokens: int = 0  # prompt tokens served from the cache (0.1x)


FirstTokenCallback = Callable[[], None]


def call_provider(
    provider: Provider,
    system: str,
    prompt: str,
    schema: dict[str, Any],
    max_tokens: int,
    *,
    timeout_s: float | None = None,
    shared_prefix: str = "",
    on_first_token: FirstTokenCallback | None = None,
    shared_system: str = "",
) -> ProviderResult:
    """One provider call. A provider that understands prompt caching gets the
    shared prefix (the cacheable head of the user prompt), the first-token
    callback and the shared system block (owner instruction 4: one cached
    block ahead of the role instruction, identical across roles); every other
    provider gets the plain call with the shared block folded into the
    system text."""
    if getattr(provider, "supports_cache_control", False):
        return provider.sample(  # type: ignore[call-arg]
            system,
            prompt,
            schema,
            max_tokens,
            timeout_s=timeout_s,
            shared_prefix=shared_prefix,
            on_first_token=on_first_token,
            shared_system=shared_system,
        )
    folded = f"{shared_system}\n\n{system}" if shared_system else system
    if timeout_s is None:
        return provider.sample(folded, prompt, schema, max_tokens)
    return provider.sample(folded, prompt, schema, max_tokens, timeout_s=timeout_s)


def no_text_reason(result: ProviderResult) -> str:
    """The honest failure label for a response without a text block: the stop
    reason and the block types, never a fabricated ``{}``."""
    blocks = ",".join(result.content_types) or "none"
    stop = result.stop_reason or "not_recorded"
    return f"generation_no_text (stop_reason={stop}, blocks={blocks})"


def call_parameters(model: str) -> dict[str, Any]:
    """What besides the prompt decides a sample: the model and how it is asked
    to think. Part of the attempt cache identity."""
    return {"model": model, "cache": "ephemeral", **thinking_arguments(model)}


def thinking_arguments(model: str) -> dict[str, Any]:
    """Structured generation buys text, not reasoning: on models that accept
    it, thinking is disabled so the whole output bound is available to the JSON
    document; on models whose thinking is always on, the request omits the
    parameter and asks for the lowest effort instead."""
    if model.startswith(("claude-fable", "claude-mythos")):
        return {"output_config": {"effort": "low"}}
    return {"thinking": {"type": "disabled"}}


@dataclass(frozen=True)
class SampleObservation:
    sample: int
    stop_reason: str
    output_tokens: int | None
    # intact | empty | no_text | salvaged:<n> | repaired | unrecoverable | error;
    # "empty" is the model's own empty findings list (a true abstention),
    # "no_text" is a response without a text block (not an abstention)
    recovery: str = "intact"
    replayed: bool = False  # served from the immutable attempt cache, nothing bought
    input_tokens: int | None = None  # uncached prompt tokens
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


def response_fragment(text: str) -> str:
    """Return a bounded, one-line JSON fragment with known credentials redacted."""

    redacted = str(redact_known_secrets(text))
    suffix = "...[truncated]" if len(redacted) > MAX_RESPONSE_FRAGMENT_CHARS else ""
    return json.dumps(
        redacted[:MAX_RESPONSE_FRAGMENT_CHARS] + suffix,
        ensure_ascii=False,
    )


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
    """Messages API provider; model id comes from configuration.

    Prompt caching (owner instruction 3, 2026-09-03): the system prompt and
    the shared prefix of the user prompt carry ``cache_control`` breakpoints;
    the variable remainder follows them. When a first-token callback is given
    the request streams and the callback fires on the first content delta,
    so a fan-out can start its siblings once the cache entry exists.
    """

    supports_cache_control = True

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
        shared_prefix: str = "",
        on_first_token: FirstTokenCallback | None = None,
        shared_system: str = "",
    ) -> ProviderResult:
        cache_control = {"type": "ephemeral"}
        content: list[dict[str, Any]]
        if shared_prefix and prompt.startswith(shared_prefix):
            variable = prompt[len(shared_prefix) :]
            content = [{"type": "text", "text": shared_prefix, "cache_control": cache_control}]
            if variable:
                content.append({"type": "text", "text": variable})
        else:
            content = [{"type": "text", "text": prompt, "cache_control": cache_control}]
        system_blocks: list[dict[str, Any]] = []
        if shared_system:
            # the shared block comes first so every role's request shares the
            # same cached prefix; the role instruction is its own breakpoint
            system_blocks.append(
                {"type": "text", "text": shared_system, "cache_control": cache_control}
            )
        system_blocks.append({"type": "text", "text": system, "cache_control": cache_control})
        arguments: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_blocks,
            "messages": [{"role": "user", "content": content}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
            "timeout": self.timeout if timeout_s is None else timeout_s,
        }
        for key, value in thinking_arguments(self.model).items():
            if key == "output_config":
                arguments["output_config"].update(value)
            else:
                arguments[key] = value
        messages = self._client().messages
        if on_first_token is None or getattr(messages, "stream", None) is None:
            response = messages.create(**arguments)
            if on_first_token is not None:
                on_first_token()
        else:
            fired = False
            with messages.stream(**arguments) as stream:
                for event in stream:
                    if not fired and getattr(event, "type", "") == "content_block_delta":
                        fired = True
                        on_first_token()
                response = stream.get_final_message()
            if not fired:
                on_first_token()
        # a response without a text block is reported as exactly that: the
        # stop reason and the block types travel with the result, and no
        # placeholder document is ever invented for it
        text = next((b.text for b in response.content if b.type == "text"), None)
        usage = response.usage
        return ProviderResult(
            text=text,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            stop_reason=response.stop_reason,
            content_types=tuple(str(b.type) for b in response.content),
            cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
            cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
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
    sample_observations: list[SampleObservation]
    per_sample: list[list[Finding]] = field(default_factory=list)
    omitted_units: list[str] = field(default_factory=list)  # typed, never silent


CONTEXT_PREAMBLE = (
    "Repository context: read-only excerpts from outside the diff. A defect that "
    "manifests at a caller or test outside the diff is still reportable: anchor it at "
    "the changed definition inside the hunks and name the caller in failure_scenario."
)


def build_prompt(diff: DiffInfo, context: str = "") -> str:
    prompt = (
        "Review this diff. Anchors must use new-file line numbers inside the hunks.\n\n"
        "```diff\n" + diff.text + "\n```"
    )
    if context:
        prompt += "\n\n" + CONTEXT_PREAMBLE + "\n\n" + context
    return prompt


def propose_plan(
    plan: ReviewPlan,
    config: ReviewConfig,
    budget: Budget,
    provider: Provider,
    *,
    cache_root: Path | None = None,
    shared_system: str = "",
) -> ProposalRun:
    """Propose per planned unit in deterministic order, then cluster task-wide.

    Units are attempted in plan order; the first unit that the budget cannot
    cover stops the run and every remaining unit is recorded as omitted, so a
    large change is reviewed partially and *visibly*, never truncated in
    silence. A first unit that does not fit raises BudgetExceeded as before.
    """
    per_sample: list[list[Finding]] = []
    rejected: list[str] = []
    errors: list[str] = []
    observations: list[SampleObservation] = []
    successful = 0
    omitted: list[str] = []
    for index, unit in enumerate(plan.units):
        try:
            run = propose(
                unit.diff(),
                config,
                budget,
                provider,
                context=unit.prompt_context(),
                sample_offset=index * config.k_samples,
                cache_root=cache_root,
                shared_system=shared_system,
            )
        except BudgetExceeded as exc:
            if index == 0:
                raise
            omitted.append(f"unit {unit.unit_id} ({', '.join(unit.files)}): budget: {exc.reason}")
            omitted.extend(
                f"unit {later.unit_id} ({', '.join(later.files)}): not attempted after budget stop"
                for later in plan.units[index + 1 :]
            )
            break
        per_sample.extend(run.per_sample)
        rejected.extend(run.rejected)
        errors.extend(run.sample_errors)
        observations.extend(run.sample_observations)
        successful += run.successful_samples
    return ProposalRun(
        candidates=cluster_findings(per_sample),
        rejected=rejected,
        sample_errors=errors,
        successful_samples=successful,
        sample_observations=observations,
        per_sample=per_sample,
        omitted_units=omitted,
    )


def propose(
    diff: DiffInfo,
    config: ReviewConfig,
    budget: Budget,
    provider: Provider,
    *,
    context: str = "",
    sample_offset: int = 0,
    cache_root: Path | None = None,
    shared_system: str = "",
) -> ProposalRun:
    """K parallel samples -> recover/validate four-piece schema -> cluster candidates.

    Recovery is precommitted (R-02): a truncated sample keeps its complete
    findings, an unusable sample gets exactly MODEL_REPAIR_ATTEMPTS more
    samples of the same prompt, and every attempt is cached by an immutable
    digest so a repeated run replays instead of buying.
    """
    prompt = build_prompt(diff, context)
    k = config.k_samples
    cache = AttemptCache(cache_root)
    reservations: list[float] = []
    try:
        for i in range(k):
            reservations.append(
                budget.reserve(
                    f"sample-{sample_offset + i}",
                    len(SYSTEM_PROMPT) + len(prompt),
                    PROPOSER_MAX_OUTPUT_TOKENS,
                )
            )
    except BudgetExceeded:
        for reservation in reservations:
            budget.cancel(reservation)
        raise

    def attempt(
        slot: int, attempt_index: int, on_first_token: FirstTokenCallback | None = None
    ) -> tuple[ProviderResult, bool] | Exception:
        """One attempt of the prompt; (result, replayed) or the provider error."""
        digest = attempt_digest(
            SYSTEM_PROMPT,
            prompt,
            PROPOSAL_SCHEMA,
            PROPOSER_MAX_OUTPUT_TOKENS,
            sample_offset + slot,
            attempt_index,
            {
                **call_parameters(config.model),
                "shared_system_sha256": hashlib.sha256(shared_system.encode("utf-8")).hexdigest(),
            },
        )
        cached = cache.get(digest)
        if cached is not None:
            return (
                ProviderResult(
                    cached.text,
                    cached.input_tokens,
                    cached.output_tokens,
                    cached.stop_reason,
                    cached.content_types,
                    cached.cache_creation_input_tokens,
                    cached.cache_read_input_tokens,
                ),
                True,
            )
        try:
            # the whole proposal prompt is shared by every sample of the unit,
            # so it is the cacheable prefix
            result = call_provider(
                provider,
                SYSTEM_PROMPT,
                prompt,
                PROPOSAL_SCHEMA,
                PROPOSER_MAX_OUTPUT_TOKENS,
                shared_prefix=prompt,
                on_first_token=on_first_token,
                shared_system=shared_system,
            )
        except Exception as exc:  # noqa: BLE001 - error becomes a sample failure
            return exc
        cache.put(
            digest,
            CachedAttempt(
                result.text,
                result.input_tokens,
                result.output_tokens,
                result.stop_reason,
                result.content_types,
                result.cache_creation_input_tokens,
                result.cache_read_input_tokens,
            ),
        )
        return result, False

    # fan-out timing (owner instruction 3): the first sample goes alone and the
    # other K-1 are dispatched once its first token has arrived, so they read
    # the cache entry the first one wrote instead of each writing their own
    first_token = Event()
    with ThreadPoolExecutor(max_workers=k) as pool:
        futures = [pool.submit(attempt, 0, 0, first_token.set)]
        while not first_token.is_set() and not futures[0].done():
            first_token.wait(0.05)
        futures.extend(pool.submit(attempt, i, 0) for i in range(1, k))
        results = [future.result() for future in futures]

    per_sample: list[list[Finding]] = []
    rejected: list[str] = []
    errors: list[str] = []
    successful_samples = 0
    observations: list[SampleObservation] = []
    for i, outcome in enumerate(results):
        label = sample_offset + i
        if isinstance(outcome, Exception):
            budget.cancel(reservations[i])
            errors.append(f"sample {label}: {type(outcome).__name__}: {outcome}")
            observations.append(
                SampleObservation(label, f"error:{type(outcome).__name__}", None, "error")
            )
            per_sample.append([])
            continue
        res, replayed = outcome
        if replayed:
            budget.cancel(reservations[i])
        else:
            budget.settle(
                f"sample-{label}",
                reservations[i],
                res.input_tokens,
                res.output_tokens,
                cache_creation_input_tokens=res.cache_creation_input_tokens,
                cache_read_input_tokens=res.cache_read_input_tokens,
            )
        if res.text is None:
            # not an abstention: the model produced no document to read
            observations.append(
                SampleObservation(
                    label,
                    res.stop_reason or "not_recorded",
                    res.output_tokens,
                    "no_text",
                    replayed,
                    res.input_tokens,
                    res.cache_creation_input_tokens,
                    res.cache_read_input_tokens,
                )
            )
            errors.append(f"sample {label}: {no_text_reason(res)}")
            per_sample.append([])
            continue
        salvage = salvage_findings(res.text)
        recovery = salvage.status
        raw_findings = salvage.findings
        if salvage.status == "unrecoverable":
            # precommitted repair: the same prompt again, at most
            # MODEL_REPAIR_ATTEMPTS times, reserved before each dispatch
            for repair_index in range(1, MODEL_REPAIR_ATTEMPTS + 1):
                try:
                    reserved = budget.reserve(
                        f"sample-{label}-repair-{repair_index}",
                        len(SYSTEM_PROMPT) + len(prompt),
                        PROPOSER_MAX_OUTPUT_TOKENS,
                    )
                except BudgetExceeded as exc:
                    recovery = f"unrecoverable; repair unaffordable: {exc.reason}"
                    break
                repaired = attempt(i, repair_index)
                if isinstance(repaired, Exception):
                    budget.cancel(reserved)
                    recovery = f"unrecoverable; repair error: {type(repaired).__name__}"
                    continue
                repaired_result, repaired_replayed = repaired
                if repaired_replayed:
                    budget.cancel(reserved)
                else:
                    budget.settle(
                        f"sample-{label}-repair-{repair_index}",
                        reserved,
                        repaired_result.input_tokens,
                        repaired_result.output_tokens,
                        cache_creation_input_tokens=repaired_result.cache_creation_input_tokens,
                        cache_read_input_tokens=repaired_result.cache_read_input_tokens,
                    )
                if repaired_result.text is None:
                    recovery = f"unrecoverable; repair {no_text_reason(repaired_result)}"
                    continue
                again = salvage_findings(repaired_result.text)
                if again.status != "unrecoverable":
                    raw_findings = again.findings
                    recovery = "repaired"
                    res = repaired_result
                    break
        observations.append(
            SampleObservation(
                label,
                res.stop_reason or "not_recorded",
                res.output_tokens,
                recovery,
                replayed,
                res.input_tokens,
                res.cache_creation_input_tokens,
                res.cache_read_input_tokens,
            )
        )
        if recovery.startswith("unrecoverable"):
            errors.append(
                f"sample {label}: unparseable JSON ({recovery}); "
                f"raw={response_fragment(res.text or '')}"
            )
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
            errors.append(
                f"sample {i}: all findings malformed; raw={response_fragment(res.text or '')}"
            )
        per_sample.append(valid)

    return ProposalRun(
        candidates=cluster_findings(per_sample),
        rejected=rejected,
        sample_errors=errors,
        successful_samples=successful_samples,
        sample_observations=observations,
        per_sample=per_sample,
    )
