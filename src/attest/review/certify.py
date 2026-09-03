"""Adapter from review-side execution evidence to certification receipt attempts.

The certification kernel (``attest.certification``) is pure and imports nothing
from the review package. This module is the only bridge: it turns one
differential verification into kernel values, asks ``validate_receipt``, and
returns whatever the validator decided. Nothing here can create an
``AcceptedReceipt`` or ``CertifiedFinding`` by any other route, so a candidate
without a validator-accepted receipt has no author-visible material at all.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path

from attest.certification.binding import BINDING_POLICY_VERSION
from attest.certification.intent import INTENT_POLICY_VERSION
from attest.certification.types import (
    CERTIFICATION_POLICY_SCHEMA_VERSION,
    CERTIFICATION_RECEIPT_SCHEMA_VERSION,
    CERTIFICATION_TASK_SCHEMA_VERSION,
    AcceptedReceipt,
    CertificationPolicy,
    CertificationReceipt,
    CertificationSubject,
    CertificationTask,
    CertifiedFinding,
    FindingAnchor,
)
from attest.certification.validate import validate_receipt
from attest.execution.local_adapter import LocalDevelopmentAdapter
from attest.execution.provenance import load_or_create_key
from attest.execution.types import LOCAL_DEVELOPMENT_PROFILE
from attest.review.candidates import StoredCandidate
from attest.review.evidence import (
    WrittenBundle,
    execution_run_from_record,
    provenance_digest,
    run_record,
    write_bundle,
)
from attest.review.executor import (
    EvidenceClass,
    ExecutionOutcome,
    ExecutorLimits,
    VerificationRun,
)

# The current declared trust class for reproduction runs: language-level
# process/network guards (AGENTS.md §4). X-02 introduces the OS boundary
# profile; until then this is the only profile a base-owned policy may allow.
# X-01: the only adapter today is the in-process development one; it is named
# for what it is and a production policy must never list it
EXECUTOR_PROFILE = LOCAL_DEVELOPMENT_PROFILE
RESULT_CLASS_HEAD_FAIL_BASE_PASS = "head_fail_base_pass"


def canonical_digest(value: object) -> str:
    """SHA-256 of the canonical JSON encoding of ``value``."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def certification_policy(repeats: int, profile: str = EXECUTOR_PROFILE) -> CertificationPolicy:
    """The policy the current product enforces: N/N differential repeats on
    exactly one executor profile (X-02: production lists the container)."""
    return CertificationPolicy(
        schema_version=CERTIFICATION_POLICY_SCHEMA_VERSION,
        receipt_schema_version=CERTIFICATION_RECEIPT_SCHEMA_VERSION,
        required_head_runs=repeats,
        required_base_runs=repeats,
        allowed_executor_profiles=(profile,),
        allowed_evidence_classes=(
            EvidenceClass.REGRESSION_REPRODUCED.value,
            EvidenceClass.BEHAVIOR_CHANGE.value,
        ),
        binding_policy_version=BINDING_POLICY_VERSION,
        intent_policy_version=INTENT_POLICY_VERSION,
    )


def policy_digest(policy: CertificationPolicy) -> str:
    return canonical_digest(asdict(policy))


def certification_task(
    *,
    task_id: str,
    repository_id: str,
    merge_base_sha: str,
    head_sha: str,
    diff_digest: str,
    policy_source_sha: str,
    policy: CertificationPolicy,
    review_policy_digest: str,
) -> CertificationTask:
    """Bind the task to both the certification policy and the resolved review policy."""
    return CertificationTask(
        schema_version=CERTIFICATION_TASK_SCHEMA_VERSION,
        task_id=task_id,
        repository_id=repository_id,
        merge_base_sha=merge_base_sha,
        head_sha=head_sha,
        diff_digest=diff_digest,
        policy_source_sha=policy_source_sha,
        policy_digest=canonical_digest(
            {"certification": policy_digest(policy), "review": review_policy_digest}
        ),
    )


def executor_digest() -> str:
    """Backend digest of the development adapter (the receipt's executor identity
    is otherwise taken from the runs themselves)."""
    return LocalDevelopmentAdapter().backend_digest()


def _single(values: set[str]) -> str:
    """The one value every run agreed on, or "" (which no receipt can accept)."""
    return next(iter(values)) if len(values) == 1 else ""


@dataclass(frozen=True)
class CertificationAttempt:
    """What one candidate's verification produced at the certification boundary."""

    candidate_id: str
    outcome: str  # "accepted" | "rejected" | "not_attempted"
    reason: str
    receipt_digest: str | None
    rejection_codes: tuple[str, ...]
    finding: CertifiedFinding | None
    bundle: WrittenBundle | None = None
    executor_profile: str = EXECUTOR_PROFILE  # X-02: the profile the runs recorded
    evidence_class: str = ""  # D-102: the accepted receipt's class, for accounting

    def to_ledger_row(self, task_id: str) -> dict[str, object]:
        row: dict[str, object] = {
            "kind": "certification",
            "task_id": task_id,
            "finding_id": self.candidate_id,
            "outcome": self.outcome,
            "reason": self.reason,
            "executor_profile": self.executor_profile,
        }
        if self.receipt_digest is not None:
            row["receipt_digest"] = self.receipt_digest
        if self.evidence_class:
            row["evidence_class"] = self.evidence_class
        if self.rejection_codes:
            row["rejection_codes"] = list(self.rejection_codes)
        if self.bundle is not None:
            row["bundle_path"] = str(self.bundle.path)
            row["bundle_digest"] = self.bundle.manifest_digest
        return row


def attempt_certification(
    task: CertificationTask,
    policy: CertificationPolicy,
    candidate: StoredCandidate,
    verification: VerificationRun,
    *,
    limits: ExecutorLimits,
    bundle_root: Path | None = None,
) -> CertificationAttempt:
    """Build and validate one receipt; every non-regression outcome is a no-op."""
    execution = verification.execution
    candidate_id = candidate.finding.finding_id
    if (
        execution.outcome is not ExecutionOutcome.REPRODUCED
        or execution.evidence_class
        not in (EvidenceClass.REGRESSION_REPRODUCED, EvidenceClass.BEHAVIOR_CHANGE)
        or verification.spec is None
    ):
        return CertificationAttempt(
            candidate_id=candidate_id,
            outcome="not_attempted",
            reason=(
                f"execution outcome {execution.outcome.value} "
                f"({execution.evidence_class.value}) buys no receipt"
            ),
            receipt_digest=None,
            rejection_codes=(),
            finding=None,
            # the runs' own profile, not the dataclass default: this row buys
            # nothing, but it is read as the record of where the code ran
            executor_profile=_single(
                {run.executor_profile for run in (*execution.head_runs, *execution.base_runs)}
            ),
        )

    all_runs = (*execution.head_runs, *execution.base_runs)
    normalized_claim = " ".join(candidate.finding.claim.split())
    # every identity field is what the runs themselves recorded; disagreement
    # between runs collapses to "" and the validator rejects the subject
    subject = CertificationSubject(
        candidate_id=candidate_id,
        normalized_claim=normalized_claim,
        claim_digest=text_digest(normalized_claim),
        test_digest=_single({run.test_file_digest for run in all_runs}),
        test_node=_single({run.test_node for run in all_runs}),
        environment_digest=_single({run.environment_digest for run in all_runs}),
        interpreter_digest=_single(
            {text_digest(f"{run.interpreter}\n{run.interpreter_version}") for run in all_runs}
        ),
        executor_profile=_single({run.executor_profile for run in all_runs}),
        executor_digest=_single({run.executor_digest for run in all_runs}),
    )
    sided = [
        *(
            ("head", index, run, execution.head_sha)
            for index, run in enumerate(execution.head_runs, 1)
        ),
        *(
            ("base", index, run, execution.base_sha)
            for index, run in enumerate(execution.base_runs, 1)
        ),
    ]
    records = [
        (side, index, run, revision, run_record(side, index, run, revision_sha=revision))
        for side, index, run, revision in sided
    ]
    head_runs = tuple(
        execution_run_from_record(record) for side, _i, _r, _v, record in records if side == "head"
    )
    base_runs = tuple(
        execution_run_from_record(record) for side, _i, _r, _v, record in records if side == "base"
    )
    unsigned = {
        "schema_version": CERTIFICATION_RECEIPT_SCHEMA_VERSION,
        "policy_version": policy.schema_version,
        "task_id": task.task_id,
        "repository_id": task.repository_id,
        "merge_base_sha": task.merge_base_sha,
        "head_sha": task.head_sha,
        "diff_digest": task.diff_digest,
        "candidate_id": subject.candidate_id,
        "normalized_claim": subject.normalized_claim,
        "claim_digest": subject.claim_digest,
        "test_digest": subject.test_digest,
        "test_node": subject.test_node,
        "policy_source_sha": task.policy_source_sha,
        "policy_digest": task.policy_digest,
        "environment_digest": subject.environment_digest,
        "interpreter_digest": subject.interpreter_digest,
        "executor_profile": subject.executor_profile,
        "executor_digest": subject.executor_digest,
        "head_runs": [asdict(run) for run in head_runs],
        "base_runs": [asdict(run) for run in base_runs],
        "result_class": RESULT_CLASS_HEAD_FAIL_BASE_PASS,
        "evidence_class": execution.evidence_class.value,
        "binding_policy_version": (
            "" if execution.binding is None else execution.binding.policy_version
        ),
        "binding_digest": "" if execution.binding is None else execution.binding.digest(),
        "intent_policy_version": (
            "" if execution.intent is None else execution.intent.policy_version
        ),
        "intent_digest": "" if execution.intent is None else execution.intent.digest(),
    }
    draft = CertificationReceipt(
        **{**unsigned, "head_runs": head_runs, "base_runs": base_runs},
        provenance_digest="0" * 64,
    )
    provenance = provenance_digest(draft)
    receipt = CertificationReceipt(
        **{**unsigned, "head_runs": head_runs, "base_runs": base_runs},
        provenance_digest=provenance,
    )
    verdict = validate_receipt(task, policy, subject, receipt)
    if not isinstance(verdict, AcceptedReceipt):
        return CertificationAttempt(
            candidate_id=candidate_id,
            outcome="rejected",
            reason="receipt rejected by the certification validator",
            receipt_digest=provenance,
            rejection_codes=tuple(code.value for code in verdict.codes),
            finding=None,
            executor_profile=subject.executor_profile,
        )
    finding = CertifiedFinding.from_accepted_receipt(
        verdict,
        (FindingAnchor(path=candidate.finding.file, line=candidate.finding.line),),
    )
    bundle = None
    if bundle_root is not None:
        test_bytes = (verification.spec.test_body.rstrip("\n") + "\n").encode("utf-8")
        bundle = write_bundle(
            bundle_root,
            task=task,
            policy=policy,
            subject=subject,
            receipt=receipt,
            test_bytes=test_bytes,
            runs=[(side, index, run, revision) for side, index, run, revision in sided],
            binding=execution.binding,
            intent=execution.intent,
            key=load_or_create_key(bundle_root),
        )
    return CertificationAttempt(
        candidate_id=candidate_id,
        outcome="accepted",
        reason=execution.reason,
        receipt_digest=provenance,
        rejection_codes=(),
        finding=finding,
        bundle=bundle,
        executor_profile=subject.executor_profile,
        evidence_class=execution.evidence_class.value,
    )
