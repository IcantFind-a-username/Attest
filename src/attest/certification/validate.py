"""Pure, fail-closed validation of regression certification receipts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .policy import validate_policy
from .types import (
    _ACCEPTED_RECEIPT_TOKEN,
    CERTIFICATION_RECEIPT_SCHEMA_VERSION,
    CERTIFICATION_TASK_SCHEMA_VERSION,
    AcceptedReceipt,
    CertificationPolicy,
    CertificationReceipt,
    CertificationSubject,
    CertificationTask,
    ExecutionRun,
)

_SHA_RE = re.compile(r"[0-9a-f]{40}")
_DIGEST_RE = re.compile(r"[0-9a-f]{64}")
_RESULT_CLASS = "head_fail_base_pass"


class RejectionCode(StrEnum):
    UNKNOWN_TASK_VERSION = "unknown_task_version"
    UNKNOWN_RECEIPT_VERSION = "unknown_receipt_version"
    TASK_INVALID = "task_invalid"
    SUBJECT_INVALID = "subject_invalid"
    POLICY_INVALID = "policy_invalid"
    POLICY_VERSION_MISMATCH = "policy_version_mismatch"
    TASK_ID_MISMATCH = "task_id_mismatch"
    REPOSITORY_MISMATCH = "repository_mismatch"
    MERGE_BASE_MISMATCH = "merge_base_mismatch"
    HEAD_SHA_MISMATCH = "head_sha_mismatch"
    DIFF_DIGEST_MISMATCH = "diff_digest_mismatch"
    CANDIDATE_ID_MISMATCH = "candidate_id_mismatch"
    CLAIM_MISMATCH = "claim_mismatch"
    CLAIM_DIGEST_MISMATCH = "claim_digest_mismatch"
    TEST_DIGEST_MISMATCH = "test_digest_mismatch"
    TEST_NODE_MISMATCH = "test_node_mismatch"
    POLICY_SOURCE_MISMATCH = "policy_source_mismatch"
    POLICY_DIGEST_MISMATCH = "policy_digest_mismatch"
    ENVIRONMENT_MISMATCH = "environment_mismatch"
    INTERPRETER_MISMATCH = "interpreter_mismatch"
    EXECUTOR_PROFILE_MISMATCH = "executor_profile_mismatch"
    EXECUTOR_DIGEST_MISMATCH = "executor_digest_mismatch"
    HEAD_RUN_COUNT_MISMATCH = "head_run_count_mismatch"
    BASE_RUN_COUNT_MISMATCH = "base_run_count_mismatch"
    HEAD_RUN_INVALID = "head_run_invalid"
    BASE_RUN_INVALID = "base_run_invalid"
    DUPLICATE_RUN_ID = "duplicate_run_id"
    RESULT_CLASS_INVALID = "result_class_invalid"
    EVIDENCE_CLASS_UNSUPPORTED = "evidence_class_unsupported"
    PROVENANCE_INVALID = "provenance_invalid"


@dataclass(frozen=True)
class ReceiptRejection:
    codes: tuple[RejectionCode, ...]


MAX_CLAIM_CHARS = 2_000


def _is_identifier(value: object) -> bool:
    return type(value) is str and value == value.strip() and 0 < len(value) <= 256


def _is_claim(value: object) -> bool:
    """A normalized claim is prose: single-spaced, printable, bounded, never empty."""
    return (
        type(value) is str
        and value == " ".join(value.split())
        and 0 < len(value) <= MAX_CLAIM_CHARS
        and value.isprintable()
    )


def _is_sha(value: object) -> bool:
    return type(value) is str and _SHA_RE.fullmatch(value) is not None


def _is_digest(value: object) -> bool:
    return type(value) is str and _DIGEST_RE.fullmatch(value) is not None


def _task_is_valid(task: CertificationTask) -> bool:
    return (
        _is_identifier(task.task_id)
        and _is_identifier(task.repository_id)
        and _is_sha(task.merge_base_sha)
        and _is_sha(task.head_sha)
        and _is_digest(task.diff_digest)
        and _is_sha(task.policy_source_sha)
        and _is_digest(task.policy_digest)
    )


def _subject_is_valid(subject: CertificationSubject) -> bool:
    return (
        _is_identifier(subject.candidate_id)
        and _is_claim(subject.normalized_claim)
        and _is_digest(subject.claim_digest)
        and _is_digest(subject.test_digest)
        and _is_identifier(subject.test_node)
        and _is_digest(subject.environment_digest)
        and _is_digest(subject.interpreter_digest)
        and _is_identifier(subject.executor_profile)
        and _is_digest(subject.executor_digest)
    )


def _run_is_valid(
    run: object,
    *,
    revision_sha: str,
    outcome: str,
) -> bool:
    if type(run) is not ExecutionRun:
        return False
    assert isinstance(run, ExecutionRun)
    failure_is_valid = (
        _is_digest(run.failure_signature)
        if outcome == "failed"
        else run.failure_signature is None
    )
    return (
        _is_identifier(run.run_id)
        and run.revision_sha == revision_sha
        and run.outcome == outcome
        and _is_digest(run.artifact_digest)
        and type(run.collected_count) is int
        and run.collected_count == 1
        and type(run.skipped_count) is int
        and run.skipped_count == 0
        and type(run.xfailed_count) is int
        and run.xfailed_count == 0
        and failure_is_valid
    )


def validate_receipt(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
) -> AcceptedReceipt | ReceiptRejection:
    """Validate all current bindings without I/O, exceptions, or ranking inputs."""
    codes: list[RejectionCode] = []

    def reject_if(condition: bool, code: RejectionCode) -> None:
        if condition and code not in codes:
            codes.append(code)

    reject_if(
        task.schema_version != CERTIFICATION_TASK_SCHEMA_VERSION,
        RejectionCode.UNKNOWN_TASK_VERSION,
    )
    reject_if(not _task_is_valid(task), RejectionCode.TASK_INVALID)
    reject_if(not _subject_is_valid(subject), RejectionCode.SUBJECT_INVALID)
    reject_if(validate_policy(policy) is not None, RejectionCode.POLICY_INVALID)
    reject_if(
        receipt.schema_version != CERTIFICATION_RECEIPT_SCHEMA_VERSION,
        RejectionCode.UNKNOWN_RECEIPT_VERSION,
    )
    reject_if(
        receipt.policy_version != policy.schema_version,
        RejectionCode.POLICY_VERSION_MISMATCH,
    )

    bindings = (
        (receipt.task_id != task.task_id, RejectionCode.TASK_ID_MISMATCH),
        (receipt.repository_id != task.repository_id, RejectionCode.REPOSITORY_MISMATCH),
        (receipt.merge_base_sha != task.merge_base_sha, RejectionCode.MERGE_BASE_MISMATCH),
        (receipt.head_sha != task.head_sha, RejectionCode.HEAD_SHA_MISMATCH),
        (receipt.diff_digest != task.diff_digest, RejectionCode.DIFF_DIGEST_MISMATCH),
        (receipt.candidate_id != subject.candidate_id, RejectionCode.CANDIDATE_ID_MISMATCH),
        (receipt.normalized_claim != subject.normalized_claim, RejectionCode.CLAIM_MISMATCH),
        (receipt.claim_digest != subject.claim_digest, RejectionCode.CLAIM_DIGEST_MISMATCH),
        (receipt.test_digest != subject.test_digest, RejectionCode.TEST_DIGEST_MISMATCH),
        (receipt.test_node != subject.test_node, RejectionCode.TEST_NODE_MISMATCH),
        (
            receipt.policy_source_sha != task.policy_source_sha,
            RejectionCode.POLICY_SOURCE_MISMATCH,
        ),
        (receipt.policy_digest != task.policy_digest, RejectionCode.POLICY_DIGEST_MISMATCH),
        (
            receipt.environment_digest != subject.environment_digest,
            RejectionCode.ENVIRONMENT_MISMATCH,
        ),
        (
            receipt.interpreter_digest != subject.interpreter_digest,
            RejectionCode.INTERPRETER_MISMATCH,
        ),
        (
            receipt.executor_profile != subject.executor_profile
            or receipt.executor_profile not in policy.allowed_executor_profiles,
            RejectionCode.EXECUTOR_PROFILE_MISMATCH,
        ),
        (
            receipt.executor_digest != subject.executor_digest,
            RejectionCode.EXECUTOR_DIGEST_MISMATCH,
        ),
    )
    for condition, code in bindings:
        reject_if(condition, code)

    reject_if(
        type(receipt.head_runs) is not tuple
        or len(receipt.head_runs) != policy.required_head_runs,
        RejectionCode.HEAD_RUN_COUNT_MISMATCH,
    )
    reject_if(
        type(receipt.base_runs) is not tuple
        or len(receipt.base_runs) != policy.required_base_runs,
        RejectionCode.BASE_RUN_COUNT_MISMATCH,
    )
    reject_if(
        type(receipt.head_runs) is not tuple
        or not all(
            _run_is_valid(run, revision_sha=task.head_sha, outcome="failed")
            for run in receipt.head_runs
        )
        or len(
            {
                run.failure_signature
                for run in receipt.head_runs
                if type(run) is ExecutionRun
            }
        )
        != 1,
        RejectionCode.HEAD_RUN_INVALID,
    )
    reject_if(
        type(receipt.base_runs) is not tuple
        or not all(
            _run_is_valid(run, revision_sha=task.merge_base_sha, outcome="passed")
            for run in receipt.base_runs
        ),
        RejectionCode.BASE_RUN_INVALID,
    )
    all_runs = (
        (*receipt.head_runs, *receipt.base_runs)
        if type(receipt.head_runs) is tuple and type(receipt.base_runs) is tuple
        else ()
    )
    run_ids = [run.run_id for run in all_runs if type(run) is ExecutionRun]
    reject_if(len(run_ids) != len(set(run_ids)), RejectionCode.DUPLICATE_RUN_ID)
    reject_if(receipt.result_class != _RESULT_CLASS, RejectionCode.RESULT_CLASS_INVALID)
    reject_if(
        receipt.evidence_class not in policy.allowed_evidence_classes,
        RejectionCode.EVIDENCE_CLASS_UNSUPPORTED,
    )
    reject_if(not _is_digest(receipt.provenance_digest), RejectionCode.PROVENANCE_INVALID)
    if codes:
        return ReceiptRejection(tuple(codes))
    return AcceptedReceipt._from_validated(receipt, _ACCEPTED_RECEIPT_TOKEN)
