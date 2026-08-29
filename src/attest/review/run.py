"""Reusable orchestration for one evidence-first review run."""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from attest.review.budget import Budget, BudgetExceeded
from attest.review.candidates import CandidateStore
from attest.review.channels import gate_feasibility
from attest.review.config import ReviewConfig
from attest.review.diffs import git_diff
from attest.review.gate import GateOutcome, GateResult, apply_gate, evaluate_finding
from attest.review.ledger import Ledger
from attest.review.proposer import Provider, propose
from attest.review.tier0 import collect_signals, signals_near


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


def _empty_outcome() -> GateOutcome:
    return GateOutcome(formal=[], drawer_overflow=[], drawer=[], discarded=[])


def run_review(
    repo: Path,
    base: str | None,
    config: ReviewConfig,
    provider: Provider,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> ReviewRun:
    started = clock()
    diff = git_diff(repo, base)
    budget = Budget(limit_usd=config.budget_usd, model=config.model)
    if not diff.hunks:
        return ReviewRun(
            task_id="",
            alpha=config.alpha,
            budget=budget,
            results=[],
            outcome=_empty_outcome(),
            notes=["no diff to review."],
            deferred_reason=None,
            elapsed_s=clock() - started,
        )

    ledger = Ledger(repo)
    alpha = ledger.current_alpha(config.alpha) if config.auto_tighten_alpha else config.alpha
    alpha, tighten_note = ledger.maybe_tighten_alpha(alpha, config.auto_tighten_alpha)
    notes = [tighten_note] if tighten_note else []
    task_id = (
        time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256(diff.text.encode()).hexdigest()[:8]
    )

    feasibility = gate_feasibility(alpha)
    if not feasibility["reachable_with_verification"]:
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
            elapsed_s=clock() - started,
        )
    if not feasibility["reachable_without_verification"]:
        notes.append(
            f"at alpha={alpha} the gate (wealth >= {1 / alpha:.0f}) is reachable only "
            "with reproduction evidence: drawer candidates surface via 'attest verify'."
        )

    results: list[GateResult] = []
    outcome = _empty_outcome()
    deferred_reason = None
    try:
        proposal = propose(diff, config, budget, provider)
        signals = collect_signals(repo, diff.files, config.tier0_commands)
        results = [
            evaluate_finding(finding, alpha, signals_near(signals, finding.file, finding.line))
            for finding in proposal.candidates
        ]
        outcome = apply_gate(results, config.max_findings)
        CandidateStore(repo).append(task_id, alpha, results)

        n_results = max(1, len(results))
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

    elapsed = clock() - started
    ledger.append(
        {
            "kind": "review_run",
            "task_id": task_id,
            "elapsed_s": round(elapsed, 2),
            "spend_usd": round(budget.spent_usd, 6),
            "model": config.model,
            "alpha": alpha,
            "files": len(diff.files),
        }
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
    )
