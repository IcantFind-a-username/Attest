from __future__ import annotations

import pytest

from attest.certification.types import (
    CERTIFICATION_POLICY_SCHEMA_VERSION,
    CERTIFICATION_RECEIPT_SCHEMA_VERSION,
    CERTIFICATION_TASK_SCHEMA_VERSION,
    CertificationPolicy,
    CertificationReceipt,
    CertificationSubject,
    CertificationTask,
    ExecutionRun,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
HEAD_SHA = "1" * 40
BASE_SHA = "2" * 40
POLICY_SHA = "3" * 40


@pytest.fixture
def task() -> CertificationTask:
    return CertificationTask(
        schema_version=CERTIFICATION_TASK_SCHEMA_VERSION,
        task_id="task-1",
        repository_id="owner/repository",
        merge_base_sha=BASE_SHA,
        head_sha=HEAD_SHA,
        diff_digest=DIGEST_A,
        policy_source_sha=POLICY_SHA,
        policy_digest=DIGEST_B,
    )


@pytest.fixture
def policy() -> CertificationPolicy:
    return CertificationPolicy(
        schema_version=CERTIFICATION_POLICY_SCHEMA_VERSION,
        receipt_schema_version=CERTIFICATION_RECEIPT_SCHEMA_VERSION,
        required_head_runs=2,
        required_base_runs=2,
        allowed_executor_profiles=("container-v1",),
        allowed_evidence_classes=("regression_reproduced",),
    )


@pytest.fixture
def subject() -> CertificationSubject:
    return CertificationSubject(
        candidate_id="candidate-1",
        normalized_claim="negative values bypass validation",
        claim_digest=DIGEST_C,
        test_digest="d" * 64,
        test_node="test_repro.py::test_negative_value",
        environment_digest="e" * 64,
        interpreter_digest="f" * 64,
        executor_profile="container-v1",
        executor_digest="0" * 64,
    )


@pytest.fixture
def receipt(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
) -> CertificationReceipt:
    head_runs = tuple(
        ExecutionRun(
            run_id=f"head-{index}",
            revision_sha=task.head_sha,
            outcome="failed",
            artifact_digest=str(index + 4) * 64,
            collected_count=1,
            skipped_count=0,
            xfailed_count=0,
            failure_signature="9" * 64,
        )
        for index in range(policy.required_head_runs)
    )
    base_runs = tuple(
        ExecutionRun(
            run_id=f"base-{index}",
            revision_sha=task.merge_base_sha,
            outcome="passed",
            artifact_digest=str(index + 6) * 64,
            collected_count=1,
            skipped_count=0,
            xfailed_count=0,
            failure_signature=None,
        )
        for index in range(policy.required_base_runs)
    )
    return CertificationReceipt(
        schema_version=CERTIFICATION_RECEIPT_SCHEMA_VERSION,
        policy_version=policy.schema_version,
        task_id=task.task_id,
        repository_id=task.repository_id,
        merge_base_sha=task.merge_base_sha,
        head_sha=task.head_sha,
        diff_digest=task.diff_digest,
        candidate_id=subject.candidate_id,
        normalized_claim=subject.normalized_claim,
        claim_digest=subject.claim_digest,
        test_digest=subject.test_digest,
        test_node=subject.test_node,
        policy_source_sha=task.policy_source_sha,
        policy_digest=task.policy_digest,
        environment_digest=subject.environment_digest,
        interpreter_digest=subject.interpreter_digest,
        executor_profile=subject.executor_profile,
        executor_digest=subject.executor_digest,
        head_runs=head_runs,
        base_runs=base_runs,
        result_class="head_fail_base_pass",
        evidence_class="regression_reproduced",
        provenance_digest="8" * 64,
    )
