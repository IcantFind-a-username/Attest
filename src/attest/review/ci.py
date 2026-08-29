"""Two-stage GitHub CI review orchestration."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from attest.github.client import STATUS_MARKER, GitHubApiError, GitHubClient
from attest.github.context import PullRequestContext
from attest.github.presentation import (
    inline_comments,
    render_complete,
    render_deferred,
    render_running,
)
from attest.review.candidates import CandidateStore
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutionOutcome, ExecutorLimits, verify_candidate
from attest.review.gate import GateResult, apply_gate
from attest.review.ledger import Ledger
from attest.review.proposer import Provider
from attest.review.run import ReviewExecutionError, ReviewSetupError, make_task_id, run_review


@dataclass
class CiRun:
    task_id: str | None
    candidate_count: int
    surfaced_count: int
    deferred_reason: str | None
    spend_usd: float
    elapsed_s: float


def _record_comment(
    ledger: Ledger,
    task_id: str | None,
    phase: str,
    *,
    outcome: str = "posted",
    reason: str | None = None,
) -> None:
    entry: dict[str, object] = {
        "kind": "github_comment",
        "task_id": task_id,
        "phase": phase,
        "outcome": outcome,
    }
    if reason is not None:
        entry["reason"] = reason
    ledger.append(entry)


def _github_reason(exc: GitHubApiError) -> str:
    return f"GitHub comment: {exc}"


def _ci_run(
    *,
    task_id: str | None,
    candidate_count: int,
    surfaced_count: int,
    deferred_reason: str | None,
    spend_usd: float,
    started: float,
    clock: Callable[[], float],
) -> CiRun:
    return CiRun(
        task_id=task_id,
        candidate_count=candidate_count,
        surfaced_count=surfaced_count,
        deferred_reason=deferred_reason,
        spend_usd=spend_usd,
        elapsed_s=clock() - started,
    )


def _post_deferred(
    *,
    context: PullRequestContext,
    client: GitHubClient,
    ledger: Ledger,
    task_id: str | None,
    reason: str,
    surfaced: list[GateResult] | None = None,
    spend_usd: float = 0.0,
    elapsed_s: float = 0.0,
) -> str:
    body = render_deferred(f"DEFER: {reason}")
    if surfaced:
        body = render_complete(surfaced, spend_usd, elapsed_s).replace(
            "Review complete.", body, 1
        )
    try:
        client.upsert_issue_comment(
            context.repository,
            context.number,
            STATUS_MARKER,
            body,
        )
    except GitHubApiError as exc:
        github_reason = _github_reason(exc)
        _record_comment(ledger, task_id, "defer", outcome="failed", reason=github_reason)
        return f"{reason}; {github_reason}"
    _record_comment(ledger, task_id, "defer")
    return reason


def run_ci(
    repo: Path,
    context: PullRequestContext,
    client: GitHubClient,
    config: ReviewConfig,
    provider: Provider,
    *,
    verification_timeout_s: float = 600.0,
    limits: ExecutorLimits | None = None,
    clock: Callable[[], float] = time.monotonic,
) -> CiRun:
    """Run a review whose candidate details remain private until verified."""
    started = clock()
    ledger = Ledger(repo)
    task_id = make_task_id(
        f"{context.repository}:{context.number}:{context.head_sha}:{started}"
    )
    if context.is_fork:
        reason = "fork pull requests are skipped before model or head-code execution"
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            reason=reason,
        )
        return _ci_run(
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=0.0,
            started=started,
            clock=clock,
        )

    try:
        client.upsert_issue_comment(
            context.repository,
            context.number,
            STATUS_MARKER,
            render_running(),
        )
    except GitHubApiError as exc:
        reason = _github_reason(exc)
        _record_comment(ledger, task_id, "running", outcome="failed", reason=reason)
        return _ci_run(
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=0.0,
            started=started,
            clock=clock,
        )

    _record_comment(ledger, task_id, "running")
    try:
        review = run_review(
            repo,
            context.base_sha,
            config,
            provider,
            clock=clock,
            task_id=task_id,
        )
    except ReviewSetupError as exc:
        reason = f"review setup failed: {type(exc).__name__}"
        ledger.append({"kind": "defer", "task_id": task_id, "reason": reason})
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            reason=reason,
        )
        return _ci_run(
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=0.0,
            started=started,
            clock=clock,
        )
    except ReviewExecutionError as exc:
        reason = str(exc)
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=exc.task_id,
            reason=reason,
        )
        return _ci_run(
            task_id=exc.task_id,
            candidate_count=exc.candidate_count,
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=exc.budget.spent_usd,
            started=started,
            clock=clock,
        )
    try:
        client.upsert_issue_comment(
            context.repository,
            context.number,
            STATUS_MARKER,
            render_running(len(review.results)),
        )
    except GitHubApiError as exc:
        reason = _github_reason(exc)
        _record_comment(
            ledger,
            task_id,
            "candidate_count",
            outcome="failed",
            reason=reason,
        )
        return _ci_run(
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )
    _record_comment(ledger, task_id, "candidate_count")

    if review.deferred_reason is not None:
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            reason=review.deferred_reason,
        )
        return _ci_run(
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=0,
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )

    verification_started = clock()
    deadline = verification_started + verification_timeout_s
    default_limits = limits or ExecutorLimits()
    results_by_id: dict[str, GateResult] = {
        result.finding.finding_id: result for result in review.results
    }
    candidates = CandidateStore(repo).load(task_id) if task_id is not None else []
    verification_defers: list[str] = []
    for index, candidate in enumerate(candidates):
        remaining_s = max(0.0, deadline - clock())
        if remaining_s <= 0:
            reason = (
                "shared verification deadline exceeded "
                f"after {verification_timeout_s:g}s"
            )
            for unprocessed in candidates[index:]:
                ledger.record_verification(
                    task_id=unprocessed.task_id,
                    finding_id=unprocessed.finding.finding_id,
                    outcome=ExecutionOutcome.DEFERRED.value,
                    reason=reason,
                    elapsed_s=0.0,
                    network_blocked=False,
                    evidence="",
                )
                verification_defers.append(reason)
            break
        verification = verify_candidate(
            repo,
            candidate,
            results_by_id[candidate.finding.finding_id],
            provider,
            review.budget,
            default_limits,
            deadline=deadline,
            clock=clock,
        )
        results_by_id[candidate.finding.finding_id] = verification.gate_result
        if verification.execution.outcome is ExecutionOutcome.DEFERRED:
            verification_defers.append(verification.execution.reason)

    updated_results = list(results_by_id.values())
    outcome = apply_gate(updated_results, config.max_findings)
    surfaced = [*outcome.formal, *outcome.drawer_overflow]
    ledger.record_ci_final(
        task_id=task_id,
        decisions=[
            {
                "finding_id": result.finding.finding_id,
                "action": result.action,
                "wealth_final": round(result.wealth, 4),
                "placement": (
                    "inline"
                    if result in outcome.formal
                    else "overflow"
                    if result in outcome.drawer_overflow
                    else result.action
                ),
            }
            for result in updated_results
        ],
        spend_usd=review.budget.spent_usd,
        elapsed_s=clock() - started,
    )
    if surfaced:
        try:
            client.create_review(
                context.repository,
                context.number,
                context.head_sha,
                inline_comments(surfaced),
            )
        except GitHubApiError as exc:
            reason = _github_reason(exc)
            _record_comment(ledger, task_id, "review", outcome="failed", reason=reason)
            reason = _post_deferred(
                context=context,
                client=client,
                ledger=ledger,
                task_id=task_id,
                reason=reason,
                surfaced=surfaced,
                spend_usd=review.budget.spent_usd,
                elapsed_s=clock() - started,
            )
            return _ci_run(
                task_id=task_id,
                candidate_count=len(review.results),
                surfaced_count=len(surfaced),
                deferred_reason=reason,
                spend_usd=review.budget.spent_usd,
                started=started,
                clock=clock,
            )
        _record_comment(ledger, task_id, "review")

    if verification_defers:
        reason = f"verification deferred: {verification_defers[0]}"
        if len(verification_defers) > 1:
            reason += f" ({len(verification_defers)} candidates)"
        reason = _post_deferred(
            context=context,
            client=client,
            ledger=ledger,
            task_id=task_id,
            reason=reason,
            surfaced=surfaced,
            spend_usd=review.budget.spent_usd,
            elapsed_s=clock() - started,
        )
        return _ci_run(
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=len(surfaced),
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )

    elapsed_s = clock() - started
    try:
        client.upsert_issue_comment(
            context.repository,
            context.number,
            STATUS_MARKER,
            render_complete(surfaced, review.budget.spent_usd, elapsed_s),
        )
    except GitHubApiError as exc:
        reason = _github_reason(exc)
        _record_comment(ledger, task_id, "complete", outcome="failed", reason=reason)
        return _ci_run(
            task_id=task_id,
            candidate_count=len(review.results),
            surfaced_count=len(surfaced),
            deferred_reason=reason,
            spend_usd=review.budget.spent_usd,
            started=started,
            clock=clock,
        )
    _record_comment(ledger, task_id, "complete")
    return CiRun(
        task_id=task_id,
        candidate_count=len(review.results),
        surfaced_count=len(surfaced),
        deferred_reason=None,
        spend_usd=review.budget.spent_usd,
        elapsed_s=elapsed_s,
    )
