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
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
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
from attest.certification.units import unit_counts
from attest.execution.backends import select_backend
from attest.execution.controller import ExecutorAdapter
from attest.review.candidates import CandidateStore, StoredCandidate
from attest.review.certify import (
    EXECUTOR_PROFILE,
    attempt_certification,
    certification_policy,
    certification_task,
)
from attest.review.config import ReviewConfig
from attest.review.executor import (
    ExecutionOutcome,
    ExecutorLimits,
    VerificationRun,
    verify_candidate,
)
from attest.review.finding_evidence import FindingEvidence, evidence_from_bundle
from attest.review.gate import GateResult
from attest.review.ledger import BufferedLedger, Ledger
from attest.review.planner import package_block
from attest.review.proposer import Provider
from attest.review.ranking import (
    VERIFICATION_RANKING_POLICY_VERSION,
    CredibilityIndex,
    cluster_size,
    rank,
    within_cap,
)
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
    # whichever the store happened to hold last.
    #
    # D-168 changes the key. The gate's wealth was flat -- 190 of the 226
    # candidates of the 2026-09-07 attest run sat at exactly 2.0 -- so the
    # effective order was the finding id, which is a hash. The key is now
    # cluster size, then a static credibility score computed from the head tree,
    # then the id: a total order, so no permutation of samples, findings or
    # files can move a candidate.
    # the tree read is the only cost this ranking has, so it is not taken for a
    # review that found nothing to rank
    credibility = (
        CredibilityIndex.for_tree(repo) if candidates else CredibilityIndex({})
    )
    candidates = rank(candidates, credibility)
    eligible_candidates = [c for c in candidates if c.eligibility == "regression"]
    # D-168: and at most `verification_cap_per_unit` of them per change unit may
    # buy a reproduction. What the cap holds back is recorded, never silent.
    cap = max(1, int(config.verification_cap_per_unit))
    purchasable, below_cap = within_cap(eligible_candidates, cap)
    ledger.append(
        {
            "kind": "verification_ranking",
            "schema_version": VERIFICATION_RANKING_POLICY_VERSION,
            "task_id": task_id,
            "cap_per_unit": cap,
            "eligible": len(eligible_candidates),
            "purchasable": len(purchasable),
            "below_cap": len(below_cap),
            "order": [
                {
                    "finding_id": item.finding.finding_id,
                    "unit": item.finding.file,
                    "cluster_size": cluster_size(item),
                    **credibility.of(item.finding.file, item.finding.line).to_row(),
                }
                for item in eligible_candidates
            ],
        }
    )
    # D-137: the gate level executes head-only, and it needs the same isolation
    # red does, so a review with only new-code candidates still selects one
    gate_candidates = (
        [c for c in candidates if c.eligibility == "new_code"] if config.gate_shadow else []
    )
    backend_reason = "caller-supplied adapter"
    if adapter is None and (eligible_candidates or gate_candidates):
        # X-02: one backend per task; the image is built from the head tree
        # before any head code runs, and a failed bootstrap is its own reason
        backend = select_backend(
            repo, production=production, remaining_s=max(0.0, deadline - clock())
        )
        adapter = backend.adapter
        backend_reason = backend.reason
        profile = backend.profile
        if backend.image is not None:
            # D-156: the image tag is keyed by the interpreter and the tree's
            # dependency manifests, so it is reused across commits that changed
            # only source. Whether that reuse happens is recorded, not assumed.
            ledger.append(
                {
                    "kind": "image_cache",
                    "task_id": task_id,
                    "tag": backend.image.tag,
                    "cached": backend.image.cached,
                    "build_elapsed_s": round(backend.image.build_elapsed_s, 2),
                }
            )
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

    def _verify(candidate: StoredCandidate, journal: Ledger) -> VerificationRun:
        shared_system = ""
        if config.context_strategy == "package-cache":
            shared_system = package_block(repo, candidate.finding.file)
        return verify_candidate(
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
            generation_model=config.generation_model,
            probe_generation=config.probe_generation,
            ledger=journal,
        )

    # D-157: reproductions of *different* candidates may overlap; the three
    # runs inside one candidate stay strictly serial, because the repeat count
    # is what makes a reproduction stable and a concurrent repeat is a
    # different experiment. Each concurrent candidate journals into its own
    # buffer, and the buffers are written in ranked order below, so the ledger
    # is byte-identical to the serial one. Only the *tail* of a run differs:
    # with two in flight, a candidate the serial path would never have started
    # may already hold the last of the budget when a higher-ranked one asks.
    dispatch = max(1, int(config.repro_concurrency))
    schedulable = [
        item
        for item in candidates
        if item.eligibility == "regression" and item.finding.finding_id in purchasable
    ]
    pool: ThreadPoolExecutor | None = None
    if dispatch > 1 and adapter is not None and len(schedulable) > 1:
        pool = ThreadPoolExecutor(max_workers=dispatch, thread_name_prefix="attest-repro")
    in_flight: dict[str, tuple[Future[VerificationRun], BufferedLedger]] = {}
    queue = list(schedulable)

    def _dispatch_ahead() -> None:
        """Keep up to ``dispatch`` reproductions in flight, in ranked order."""
        if pool is None:
            return
        while queue and len(in_flight) < dispatch:
            if clock() >= deadline or review.budget.exhausted():
                return
            nxt = queue.pop(0)
            buffer = BufferedLedger(repo)
            in_flight[nxt.finding.finding_id] = (
                pool.submit(_verify, nxt, buffer),
                buffer,
            )

    try:
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
            if candidate.finding.finding_id in below_cap:
                # D-168: held back by the per-unit cap, before any image, any
                # container and any generation call. Recorded as its own outcome
                # rather than folded into `no-reproduction-bought`: the ranking
                # reached it and declined it, which is a decision, not an absence.
                reason = below_cap[candidate.finding.finding_id]
                ledger.append(
                    {
                        "kind": "certification",
                        "task_id": task_id,
                        "finding_id": candidate.finding.finding_id,
                        "outcome": "not_attempted",
                        "reason": reason,
                        "executor_profile": EXECUTOR_PROFILE,
                    }
                )
                reasons[candidate.finding.finding_id] = reason
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
            finding_id = candidate.finding.finding_id
            started_here = in_flight.pop(finding_id, None)
            if started_here is None:
                remaining_s = max(0.0, deadline - clock())
                if remaining_s <= 0:
                    reason = (
                        f"shared verification deadline exceeded after {verification_timeout_s:g}s"
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
                        reasons[unprocessed.finding.finding_id] = reason
                    break
                _dispatch_ahead()
                started_here = in_flight.pop(finding_id, None)
            attempted += 1
            if started_here is None:
                verification = _verify(candidate, ledger)
            else:
                future, buffer = started_here
                verification = future.result()
                # ranked order, not completion order: the bytes match the
                # serial run's exactly
                buffer.flush(ledger)
                _dispatch_ahead()
            results_by_id[finding_id] = verification.gate_result
            if verification.execution.outcome is ExecutionOutcome.DEFERRED:
                verification_defers.append(verification.execution.reason)
                reasons[finding_id] = verification.execution.reason
            elif verification.execution.outcome is ExecutionOutcome.NOT_REPRODUCED:
                reasons[finding_id] = verification.execution.reason
            attempt = attempt_certification(
                certification,
                policy,
                candidate,
                verification,
                limits=default_limits,
                bundle_root=repo,
            )
            ledger.append(attempt.to_ledger_row(task_id))
            if (
                attempt.outcome == "rejected"
                and attempt.rejection_codes
                and attempt.rejection_codes[0].startswith("bundle_")
            ):
                # D-124: the receipt validated but its bundle did not; that is an
                # abstention, not a finding, and the author sees the reason
                verification_defers.append(attempt.reason)
                reasons[finding_id] = attempt.reason
            if attempt.finding is not None:
                certified_by_id[finding_id] = attempt.finding
                if attempt.bundle is not None:
                    block = evidence_from_bundle(attempt.bundle.path, repo=repo)
                    if block is not None:
                        evidence[finding_id] = block
    finally:
        if pool is not None:
            # a candidate the loop never reached still holds a container; its
            # buffered rows are dropped on purpose -- the ledger records what
            # the review acted on, and it acted on nothing this thread produced
            for future, _buffer in in_flight.values():
                future.cancel()
            pool.shutdown(wait=True)

    # D-137, the gate level, in shadow and off by default. It runs **after**
    # every certification decision has been taken and touches none of them: its
    # candidates are the `new_code` ones, which the loop above skipped without
    # buying anything, and its output goes to the ledger and to
    # `.attest/shadow/gate/` and nowhere else. Any exception anywhere in it
    # leaves the review exactly as it was.
    if config.gate_shadow:
        from attest.review.gate_level import run_gate_shadow_stage

        with suppress(Exception):
            run_gate_shadow_stage(
                repo,
                task_id=task_id,
                base_sha=base_sha,
                head_sha=head_sha,
                candidates=candidates,
                provider=provider,
                budget=review.budget,
                limits=default_limits,
                adapter=adapter,
                deadline=deadline,
                clock=clock,
                generation_model=config.generation_model,
                ledger=ledger,
            )

    # C-05 (INV-FAMILY-001): same-defect certified findings count once, a
    # finding publishes only at e-value >= m/alpha for the m eligible candidates
    # in this PR, and at most the hard cap is author-visible anywhere
    eligible = [candidate for candidate in candidates if candidate.eligibility == "regression"]
    eligible_ids = [candidate.finding.finding_id for candidate in eligible]
    # D-125: the family is the change unit the candidate is anchored in, so the
    # bar a finding clears is set by its own file's eligible count, not the PR's
    units = unit_counts(candidate.finding.file for candidate in eligible)
    family = FamilyPolicy(
        alpha=review.alpha,
        eligible_count=len(eligible_ids),
        hard_cap=min(3, config.max_findings),
        eligible_units=units,
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
            # D-125: `family_threshold` remains the PR-wide bar, reported and no
            # longer applied; `unit_thresholds` is what each cluster was judged by
            "family_threshold": round(selection.family_threshold, 6),
            "unit_policy_version": family.unit_policy_version,
            "eligible_units": dict(sorted(units.items())),
            "unit_thresholds": {
                unit: round(value, 6) for unit, value in sorted(selection.unit_thresholds.items())
            },
            "hard_cap": family.hard_cap,
            # D-174: what the PR-level guarantee actually is. `hard_cap` bounds
            # the display; `units_searched` is the number of families that were
            # searched and `pr_error_bound = min(1, U*alpha)` the union over them,
            # conditional on `e_value_validity`.
            "units_searched": selection.units_searched,
            "pr_error_bound": round(selection.pr_error_bound, 6),
            "e_value_validity": selection.e_value_validity,
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
