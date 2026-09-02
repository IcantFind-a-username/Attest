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
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

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
    ExecutionRun,
    FindingAnchor,
)
from attest.certification.validate import validate_receipt
from attest.review import executor as executor_module
from attest.review.candidates import StoredCandidate
from attest.review.executor import (
    SITECUSTOMIZE,
    EvidenceClass,
    ExecutionOutcome,
    ExecutionResult,
    ExecutorLimits,
    VerificationRun,
    classify_failure_signature,
)

# The current declared trust class for reproduction runs: language-level
# process/network guards (AGENTS.md §4). X-02 introduces the OS boundary
# profile; until then this is the only profile a base-owned policy may allow.
EXECUTOR_PROFILE = "language-guard-v1"
RESULT_CLASS_HEAD_FAIL_BASE_PASS = "head_fail_base_pass"


def canonical_digest(value: object) -> str:
    """SHA-256 of the canonical JSON encoding of ``value``."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def certification_policy(repeats: int) -> CertificationPolicy:
    """The policy the current product enforces: N/N differential repeats."""
    return CertificationPolicy(
        schema_version=CERTIFICATION_POLICY_SCHEMA_VERSION,
        receipt_schema_version=CERTIFICATION_RECEIPT_SCHEMA_VERSION,
        required_head_runs=repeats,
        required_base_runs=repeats,
        allowed_executor_profiles=(EXECUTOR_PROFILE,),
        allowed_evidence_classes=(EvidenceClass.REGRESSION_REPRODUCED.value,),
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
) -> CertificationTask:
    return CertificationTask(
        schema_version=CERTIFICATION_TASK_SCHEMA_VERSION,
        task_id=task_id,
        repository_id=repository_id,
        merge_base_sha=merge_base_sha,
        head_sha=head_sha,
        diff_digest=diff_digest,
        policy_source_sha=policy_source_sha,
        policy_digest=policy_digest(policy),
    )


def executor_digest() -> str:
    """Digest of the executor module that produced the runs."""
    return hashlib.sha256(Path(executor_module.__file__).read_bytes()).hexdigest()


def interpreter_digest() -> str:
    interpreter = os.environ.get("ATTEST_PROJECT_PYTHON", sys.executable)
    return text_digest(interpreter)


def environment_digest(limits: ExecutorLimits) -> str:
    return canonical_digest(
        {
            "executor_limits": asdict(limits),
            "guard_digest": text_digest(SITECUSTOMIZE),
            "pytest_plugin_autoload": False,
            "python_safe_path": True,
        }
    )


@dataclass(frozen=True)
class CertificationAttempt:
    """What one candidate's verification produced at the certification boundary."""

    candidate_id: str
    outcome: str  # "accepted" | "rejected" | "not_attempted"
    reason: str
    receipt_digest: str | None
    rejection_codes: tuple[str, ...]
    finding: CertifiedFinding | None

    def to_ledger_row(self, task_id: str) -> dict[str, object]:
        row: dict[str, object] = {
            "kind": "certification",
            "task_id": task_id,
            "finding_id": self.candidate_id,
            "outcome": self.outcome,
            "reason": self.reason,
            "executor_profile": EXECUTOR_PROFILE,
        }
        if self.receipt_digest is not None:
            row["receipt_digest"] = self.receipt_digest
        if self.rejection_codes:
            row["rejection_codes"] = list(self.rejection_codes)
        return row


def _execution_run(
    side: str, index: int, run: ExecutionResult, *, revision_sha: str
) -> ExecutionRun:
    failed = run.outcome is ExecutionOutcome.REPRODUCED
    return ExecutionRun(
        run_id=f"{side}-{index}",
        revision_sha=revision_sha,
        outcome="failed" if failed else "passed",
        artifact_digest=canonical_digest(
            {
                "exit_code": run.exit_code,
                "outcome": run.outcome.value,
                "reason": run.reason,
                "stderr": run.stderr,
                "stdout": run.stdout,
            }
        ),
        collected_count=run.collected_count,
        skipped_count=run.skipped_count,
        xfailed_count=run.xfailed_count,
        failure_signature=(
            text_digest(classify_failure_signature(run).value) if failed else None
        ),
    )


def attempt_certification(
    task: CertificationTask,
    policy: CertificationPolicy,
    candidate: StoredCandidate,
    verification: VerificationRun,
    *,
    limits: ExecutorLimits,
) -> CertificationAttempt:
    """Build and validate one receipt; every non-regression outcome is a no-op."""
    execution = verification.execution
    candidate_id = candidate.finding.finding_id
    if (
        execution.outcome is not ExecutionOutcome.REPRODUCED
        or execution.evidence_class is not EvidenceClass.REGRESSION_REPRODUCED
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
        )

    nodes = {run.test_node for run in (*execution.head_runs, *execution.base_runs)}
    normalized_claim = " ".join(candidate.finding.claim.split())
    subject = CertificationSubject(
        candidate_id=candidate_id,
        normalized_claim=normalized_claim,
        claim_digest=text_digest(normalized_claim),
        test_digest=text_digest(verification.spec.test_body),
        test_node=next(iter(nodes)) if len(nodes) == 1 else "",
        environment_digest=environment_digest(limits),
        interpreter_digest=interpreter_digest(),
        executor_profile=EXECUTOR_PROFILE,
        executor_digest=executor_digest(),
    )
    head_runs = tuple(
        _execution_run("head", index, run, revision_sha=execution.head_sha)
        for index, run in enumerate(execution.head_runs, start=1)
    )
    base_runs = tuple(
        _execution_run("base", index, run, revision_sha=execution.base_sha)
        for index, run in enumerate(execution.base_runs, start=1)
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
    }
    provenance = canonical_digest(unsigned)
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
        )
    finding = CertifiedFinding.from_accepted_receipt(
        verdict,
        (FindingAnchor(path=candidate.finding.file, line=candidate.finding.line),),
    )
    return CertificationAttempt(
        candidate_id=candidate_id,
        outcome="accepted",
        reason=execution.reason,
        receipt_digest=provenance,
        rejection_codes=(),
        finding=finding,
    )
