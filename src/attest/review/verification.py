"""The verification stage shared by CI and the local review (fix 5, 2026-09-03).

Differential reproduction for every regression-eligible candidate the S/T
ranking did not discard, one certification attempt per result, the PR-level
family policy (C-05) and the hard author-visible cap: one code path, so
``attest review`` and ``attest ci`` publish exactly the same receipts. S and T
rank; they never speak (INV-CERT-001).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from attest.certification.selection import (
    PUBLICATION_METHOD,
    PUBLICATION_POLICY_SCHEMA_VERSION,
    FamilyPolicy,
    ScoredFinding,
    Suppressed,
    select_for_publication,
)
from attest.certification.types import CertifiedFinding
from attest.execution.backends import select_backend
from attest.execution.controller import ExecutorAdapter
from attest.review.candidates import CandidateStore
from attest.review.certify import (
    EXECUTOR_PROFILE,
    attempt_certification,
    certification_policy,
    certification_task,
)
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutionOutcome, ExecutorLimits, verify_candidate
from attest.review.finding_evidence import FindingEvidence, evidence_from_bundle
from attest.review.gate import GateResult
from attest.review.ledger import Ledger
from attest.review.planner import package_block
from attest.review.proposer import Provider
from attest.review.run import ReviewRun

# differential repeats per side; the certification policy demands exactly this many
CERTIFICATION_REPEATS = 3


def candidate_id(finding: CertifiedFinding) -> str:
    return finding.accepted_receipt.receipt.candidate_id


@dataclass
class VerificationStage:
    results_by_id: dict[str, GateResult]
    certified_by_id: dict[str, CertifiedFinding]
    published: list[CertifiedFinding]
    suppressed: list[Suppressed]
    eligible_ids: list[str]
    verification_defers: list[str]
    family_threshold: float
    hard_cap: int
    attempted: int = 0  # candidates that entered differential reproduction
    reasons: dict[str, str] = field(default_factory=dict)  # finding id -> DEFER reason
    evidence: dict[str, FindingEvidence] = field(default_factory=dict)  # item 7


def run_verification_stage(
    repo: Path,
    *,
    task_id: str,
    repository_id: str,
    base_sha: str,
    head_sha: str,
    review: ReviewRun,
    review_policy_digest: str,
    config: ReviewConfig,
    provider: Provider,
    limits: ExecutorLimits | None = None,
    verification_timeout_s: float = 600.0,
    clock: Callable[[], float] = time.monotonic,
    adapter: ExecutorAdapter | None = None,
    production: bool = True,
) -> VerificationStage:
    ledger = Ledger(repo)
    verification_started = clock()
    deadline = verification_started + verification_timeout_s
    default_limits = limits or ExecutorLimits()
    results_by_id: dict[str, GateResult] = {
        result.finding.finding_id: result for result in review.results
    }
    candidates = [
        candidate
        for candidate in CandidateStore(repo).load(task_id)
        if candidate.action != "discard"
    ]
    # D-111: reproductions are bought in ranking order, so a shared deadline or
    # an exhausted budget stops at the *weakest* candidate rather than at
    # whichever the store happened to hold last. The key is the one C-05
    # already uses for publication: score first, candidate id to break ties.
    candidates.sort(key=lambda item: (-item.wealth, item.finding.finding_id))
    eligible_candidates = [c for c in candidates if c.eligibility == "regression"]
    backend_reason = "caller-supplied adapter"
    if adapter is None and eligible_candidates:
        # X-02: one backend per task; the image is built from the head tree
        # before any head code runs, and a failed bootstrap is its own reason
        backend = select_backend(
            repo, production=production, remaining_s=max(0.0, deadline - clock())
        )
        adapter = backend.adapter
        backend_reason = backend.reason
        profile = backend.profile
    else:
        profile = adapter.profile if adapter is not None else EXECUTOR_PROFILE
    ledger.append(
        {
            "kind": "executor_backend",
            "task_id": task_id,
            "profile": profile,
            "available": adapter is not None or not eligible_candidates,
            "reason": backend_reason,
        }
    )
    policy = certification_policy(CERTIFICATION_REPEATS, profile)
    certification = certification_task(
        task_id=task_id,
        repository_id=repository_id,
        merge_base_sha=base_sha,
        head_sha=head_sha,
        diff_digest=review.diff_digest,
        policy_source_sha=base_sha,
        policy=policy,
        review_policy_digest=review_policy_digest,
    )
    certified_by_id: dict[str, CertifiedFinding] = {}
    verification_defers: list[str] = []
    reasons: dict[str, str] = {}
    evidence: dict[str, FindingEvidence] = {}
    attempted = 0
    for index, candidate in enumerate(candidates):
        if candidate.eligibility != "regression":
            # typed abstention before any paid generation; not a verification
            # DEFER and never part of the eligible denominator
            ledger.append(
                {
                    "kind": "certification",
                    "task_id": task_id,
                    "finding_id": candidate.finding.finding_id,
                    "outcome": "not_attempted",
                    "reason": (
                        f"ineligible: {candidate.eligibility}: {candidate.eligibility_reason}"
                    ),
                    "executor_profile": EXECUTOR_PROFILE,
                }
            )
            continue
        if adapter is None:
            reason = f"isolation backend unavailable: {backend_reason}"
            ledger.record_verification(
                task_id=candidate.task_id,
                finding_id=candidate.finding.finding_id,
                outcome=ExecutionOutcome.DEFERRED.value,
                reason=reason,
                elapsed_s=0.0,
                network_blocked=False,
                evidence="",
            )
            verification_defers.append(reason)
            reasons[candidate.finding.finding_id] = reason
            continue
        remaining_s = max(0.0, deadline - clock())
        if remaining_s <= 0:
            reason = f"shared verification deadline exceeded after {verification_timeout_s:g}s"
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
                reasons[unprocessed.finding.finding_id] = reason
            break
        attempted += 1
        shared_system = ""
        if config.context_strategy == "package-cache":
            shared_system = package_block(repo, candidate.finding.file)
        verification = verify_candidate(
            repo,
            candidate,
            results_by_id[candidate.finding.finding_id],
            provider,
            review.budget,
            default_limits,
            base_sha=base_sha,
            head_sha=head_sha,
            repeats=CERTIFICATION_REPEATS,
            deadline=deadline,
            clock=clock,
            adapter=adapter,
            shared_system=shared_system,
        )
        results_by_id[candidate.finding.finding_id] = verification.gate_result
        if verification.execution.outcome is ExecutionOutcome.DEFERRED:
            verification_defers.append(verification.execution.reason)
            reasons[candidate.finding.finding_id] = verification.execution.reason
        elif verification.execution.outcome is ExecutionOutcome.NOT_REPRODUCED:
            reasons[candidate.finding.finding_id] = verification.execution.reason
        attempt = attempt_certification(
            certification,
            policy,
            candidate,
            verification,
            limits=default_limits,
            bundle_root=repo,
        )
        ledger.append(attempt.to_ledger_row(task_id))
        if attempt.finding is not None:
            certified_by_id[candidate.finding.finding_id] = attempt.finding
            if attempt.bundle is not None:
                block = evidence_from_bundle(attempt.bundle.path, repo=repo)
                if block is not None:
                    evidence[candidate.finding.finding_id] = block

    # C-05 (INV-FAMILY-001): same-defect certified findings count once, a
    # finding publishes only at e-value >= m/alpha for the m eligible candidates
    # in this PR, and at most the hard cap is author-visible anywhere
    eligible_ids = [
        candidate.finding.finding_id
        for candidate in candidates
        if candidate.eligibility == "regression"
    ]
    family = FamilyPolicy(
        alpha=review.alpha,
        eligible_count=len(eligible_ids),
        hard_cap=min(3, config.max_findings),
    )
    selection = select_for_publication(
        [
            ScoredFinding(finding, results_by_id[candidate_id(finding)].wealth)
            for finding in certified_by_id.values()
        ],
        family,
        [results_by_id[finding_id].wealth for finding_id in eligible_ids],
    )
    ledger.append(
        {
            "kind": "publication_policy",
            "schema_version": PUBLICATION_POLICY_SCHEMA_VERSION,
            "task_id": task_id,
            "method": PUBLICATION_METHOD,
            "alpha": review.alpha,
            "eligible_count": family.eligible_count,
            "family_threshold": round(selection.family_threshold, 6),
            "hard_cap": family.hard_cap,
            "mean_e_value": (
                None if selection.mean_e_value is None else round(selection.mean_e_value, 6)
            ),
            "clusters": [list(cluster) for cluster in selection.clusters],
            "published": [candidate_id(finding) for finding in selection.published],
            "suppressed": [
                {"finding_id": candidate_id(item.finding), "reason": item.reason}
                for item in selection.suppressed
            ],
        }
    )
    return VerificationStage(
        results_by_id=results_by_id,
        certified_by_id=certified_by_id,
        published=list(selection.published),
        suppressed=list(selection.suppressed),
        eligible_ids=eligible_ids,
        verification_defers=verification_defers,
        family_threshold=selection.family_threshold,
        hard_cap=family.hard_cap,
        attempted=attempted,
        reasons=reasons,
        evidence=evidence,
    )
