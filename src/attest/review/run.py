"""Reusable orchestration for one evidence-first review run."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NoReturn

from attest.review.budget import Budget, BudgetExceeded
from attest.review.candidates import CandidateStore
from attest.review.channels import gate_feasibility
from attest.review.config import ReviewConfig
from attest.review.diffs import git_diff
from attest.review.gate import GateOutcome, GateResult, apply_gate, evaluate_finding
from attest.review.history import (
    HISTORY_LOOKBACK_COMMITS,
    HISTORY_SIGNAL_SCHEMA_VERSION,
    inspect_history_signal,
)
from attest.review.ledger import REVIEW_AUTHORITY_RANKING, Ledger
from attest.review.proposer import Provider, propose
from attest.review.tier0 import collect_signals, signals_near, unresolved_identifiers


@dataclass
class ReviewRun:
    task_id: str
    alpha: float
    budget: Budget
    results: list[GateResult]
    outcome: GateOutcome
    notes: list[str]
    deferred_reason: str | None
    elapsed_s: float
    diff_digest: str = ""  # SHA-256 of the reviewed diff text; binds receipts to it


class ReviewSetupError(RuntimeError):
    """Review input could not be prepared before any provider work."""


class ReviewExecutionError(RuntimeError):
    """Review failed after execution began, with accounting state attached."""

    def __init__(
        self,
        *,
        task_id: str,
        phase: str,
        budget: Budget,
        candidate_count: int,
        elapsed_s: float,
    ) -> None:
        super().__init__(f"review execution failed during {phase.replace('_', ' ')}")
        self.task_id = task_id
        self.phase = phase
        self.budget = budget
        self.candidate_count = candidate_count
        self.elapsed_s = elapsed_s


def _empty_outcome() -> GateOutcome:
    return GateOutcome(formal=[], drawer_overflow=[], drawer=[], discarded=[])


def make_task_id(seed: str) -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256(seed.encode()).hexdigest()[:8]


def _review_run_entry(
    *,
    task_id: str,
    elapsed_s: float,
    budget: Budget,
    config: ReviewConfig,
    alpha: float,
    files: int,
    phase: str | None = None,
    provider_samples: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    entry: dict[str, object] = {
        "kind": "review_run",
        "task_id": task_id,
        "elapsed_s": round(elapsed_s, 2),
        "spend_usd": round(budget.spent_usd, 6),
        "model": config.model,
        "alpha": alpha,
        "files": files,
    }
    if phase is not None:
        entry["phase"] = phase
        entry["outcome"] = "deferred"
    if provider_samples is not None:
        entry["provider_samples"] = provider_samples
    return entry


def _raise_execution_error(
    *,
    cause: OSError | RuntimeError,
    ledger: Ledger,
    task_id: str,
    phase: str,
    elapsed_s: float,
    budget: Budget,
    config: ReviewConfig,
    alpha: float,
    files: int,
    candidate_count: int,
    provider_samples: list[dict[str, object]],
) -> NoReturn:
    reason = f"review execution failed during {phase.replace('_', ' ')}"
    with suppress(OSError, RuntimeError):
        ledger.append(
            {
                "kind": "defer",
                "task_id": task_id,
                "reason": reason,
                "phase": phase,
            }
        )
    with suppress(OSError, RuntimeError):
        ledger.append(
            _review_run_entry(
                task_id=task_id,
                elapsed_s=elapsed_s,
                budget=budget,
                config=config,
                alpha=alpha,
                files=files,
                phase=phase,
                provider_samples=provider_samples,
            )
        )
    raise ReviewExecutionError(
        task_id=task_id,
        phase=phase,
        budget=budget,
        candidate_count=candidate_count,
        elapsed_s=elapsed_s,
    ) from cause


def run_review(
    repo: Path,
    base: str | None,
    config: ReviewConfig,
    provider: Provider,
    *,
    clock: Callable[[], float] = time.monotonic,
    task_id: str | None = None,
) -> ReviewRun:
    started = clock()
    try:
        diff = git_diff(repo, base)
    except (OSError, RuntimeError) as exc:
        raise ReviewSetupError("review setup failed") from exc
    budget = Budget(limit_usd=config.budget_usd, model=config.model)
    diff_digest = hashlib.sha256(diff.text.encode("utf-8")).hexdigest()
    if not diff.hunks:
        return ReviewRun(
            task_id=task_id or "",
            alpha=config.alpha,
            budget=budget,
            results=[],
            outcome=_empty_outcome(),
            notes=["no diff to review."],
            deferred_reason=None,
            elapsed_s=clock() - started,
            diff_digest=diff_digest,
        )

    try:
        ledger = Ledger(repo)
        alpha = ledger.current_alpha(config.alpha) if config.auto_tighten_alpha else config.alpha
        alpha, tighten_note = ledger.maybe_tighten_alpha(alpha, config.auto_tighten_alpha)
    except (OSError, RuntimeError) as exc:
        raise ReviewSetupError("review setup failed") from exc
    notes = [tighten_note] if tighten_note else []
    task_id = task_id or make_task_id(diff.text)

    feasibility = gate_feasibility(alpha)
    if not feasibility["reachable_with_verification"]:
        elapsed = clock() - started
        ledger.append({"kind": "defer", "task_id": task_id, "reason": "unreachable gate"})
        ledger.append(
            _review_run_entry(
                task_id=task_id,
                elapsed_s=elapsed,
                budget=budget,
                config=config,
                alpha=alpha,
                files=len(diff.files),
                phase="gate_feasibility",
            )
        )
        return ReviewRun(
            task_id=task_id,
            alpha=alpha,
            budget=budget,
            results=[],
            outcome=_empty_outcome(),
            notes=[
                f"gate 1/alpha = {1 / alpha:.0f} exceeds the factory evidence ceiling "
                "even with verification; refusing to run an unreachable gate."
            ],
            deferred_reason="unreachable gate",
            elapsed_s=elapsed,
            diff_digest=diff_digest,
        )
    if not feasibility["reachable_without_verification"]:
        notes.append(
            f"at alpha={alpha} the gate (wealth >= {1 / alpha:.0f}) is reachable only "
            "with reproduction evidence: drawer candidates surface via 'attest verify'."
        )

    results: list[GateResult] = []
    outcome = _empty_outcome()
    deferred_reason = None
    provider_samples: list[dict[str, object]] = []
    phase = "proposal"
    try:
        proposal = propose(diff, config, budget, provider)
        provider_samples = [asdict(sample) for sample in proposal.sample_observations]
        notes.extend(
            "provider sample "
            f"{sample.sample}: stop_reason={sample.stop_reason}; "
            + (
                f"output_tokens={sample.output_tokens}"
                if sample.output_tokens is not None
                else "output_tokens=unknown"
            )
            for sample in proposal.sample_observations
        )
        if proposal.successful_samples == 0:
            deferred_reason = "all provider samples failed or were malformed"
            ledger.append({"kind": "defer", "task_id": task_id, "reason": deferred_reason})
        # Observation only — this vetoes nothing and changes no wealth. Every
        # candidate below still reaches the gate exactly as it would without
        # this block; the rows exist so the would-be veto rate can be measured
        # before anyone decides whether it should ever become a gate.
        phase = "identifier_resolution"
        for candidate in proposal.candidates:
            unresolved = unresolved_identifiers(repo, candidate)
            if unresolved:
                ledger.append(
                    {
                        "kind": "identifier_check",
                        "task_id": task_id,
                        "finding_id": candidate.finding_id,
                        "unresolved": unresolved,
                    }
                )
        # F is observation-only: a separate versioned row with no purchase,
        # wealth mutation, ordering effect, or publication path.
        phase = "history_observation"
        for candidate in proposal.candidates:
            history = inspect_history_signal(repo, candidate)
            ledger.append(
                {
                    "kind": "history_signal",
                    "schema_version": HISTORY_SIGNAL_SCHEMA_VERSION,
                    "task_id": task_id,
                    "finding_id": candidate.finding_id,
                    "file": candidate.file,
                    "line": candidate.line,
                    "lookback_commits": HISTORY_LOOKBACK_COMMITS,
                    "triggered": history.triggered,
                    "commit_sha": history.commit_sha,
                    "commit_message": history.commit_message,
                    "priced": False,
                }
            )
        phase = "static_analysis"
        signals = (
            []
            if deferred_reason is not None
            else collect_signals(repo, diff.files, config.tier0_commands)
        )
        phase = "candidate_evaluation"
        results = (
            []
            if deferred_reason is not None
            else [
                evaluate_finding(finding, alpha, signals_near(signals, finding.file, finding.line))
                for finding in proposal.candidates
            ]
        )
        outcome = apply_gate(results, config.max_findings)
        phase = "candidate_persistence"
        CandidateStore(repo).append(task_id, alpha, results)

        n_results = max(1, len(results))
        phase = "review_accounting"
        for result in results:
            ledger.record_review(
                task_id=task_id,
                finding_id=result.finding.finding_id,
                channels_bought=[purchase.channel for purchase in result.purchases],
                spend=budget.spent_usd / n_results,
                wealth_final=result.wealth,
                action=(
                    result.action if result not in outcome.drawer_overflow else "overflow_surface"
                ),
                authority=REVIEW_AUTHORITY_RANKING,
            )
        notes.extend(f"sample error: {error}" for error in proposal.sample_errors)
        if proposal.rejected:
            notes.append(
                f"{len(proposal.rejected)} finding(s) voided (schema/anchor): "
                + "; ".join(proposal.rejected[:3])
            )
    except BudgetExceeded as exc:
        deferred_reason = f"budget: {exc.reason}"
        ledger.append({"kind": "defer", "task_id": task_id, "reason": deferred_reason})
    except (OSError, RuntimeError) as exc:
        elapsed = clock() - started
        _raise_execution_error(
            cause=exc,
            ledger=ledger,
            task_id=task_id,
            phase=phase,
            elapsed_s=elapsed,
            budget=budget,
            config=config,
            alpha=alpha,
            files=len(diff.files),
            candidate_count=len(results),
            provider_samples=provider_samples,
        )

    elapsed = clock() - started
    try:
        ledger.append(
            _review_run_entry(
                task_id=task_id,
                elapsed_s=elapsed,
                budget=budget,
                config=config,
                alpha=alpha,
                files=len(diff.files),
                provider_samples=provider_samples,
            )
        )
    except (OSError, RuntimeError) as exc:
        _raise_execution_error(
            cause=exc,
            ledger=ledger,
            task_id=task_id,
            phase="review_run_accounting",
            elapsed_s=elapsed,
            budget=budget,
            config=config,
            alpha=alpha,
            files=len(diff.files),
            candidate_count=len(results),
            provider_samples=provider_samples,
        )
    return ReviewRun(
        task_id=task_id,
        alpha=alpha,
        budget=budget,
        results=results,
        outcome=outcome,
        notes=notes,
        deferred_reason=deferred_reason,
        elapsed_s=elapsed,
        diff_digest=diff_digest,
    )
