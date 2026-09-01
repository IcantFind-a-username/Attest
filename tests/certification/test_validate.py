from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from attest.certification.types import (
    AcceptedReceipt,
    CertificationPolicy,
    CertificationReceipt,
    CertificationSubject,
    CertificationTask,
    CertifiedFinding,
    FindingAnchor,
)
from attest.certification.validate import RejectionCode, validate_receipt


def _replace_receipt(
    receipt: CertificationReceipt, field: str, value: object
) -> CertificationReceipt:
    return replace(receipt, **{field: value})


@pytest.mark.parametrize(
    ("field", "value", "expected"),
    [
        ("schema_version", "future", RejectionCode.UNKNOWN_RECEIPT_VERSION),
        ("policy_version", "future", RejectionCode.POLICY_VERSION_MISMATCH),
        ("task_id", "other", RejectionCode.TASK_ID_MISMATCH),
        ("repository_id", "other/repo", RejectionCode.REPOSITORY_MISMATCH),
        ("merge_base_sha", "4" * 40, RejectionCode.MERGE_BASE_MISMATCH),
        ("head_sha", "5" * 40, RejectionCode.HEAD_SHA_MISMATCH),
        ("diff_digest", "6" * 64, RejectionCode.DIFF_DIGEST_MISMATCH),
        ("candidate_id", "", RejectionCode.CANDIDATE_ID_MISMATCH),
        ("normalized_claim", "other claim", RejectionCode.CLAIM_MISMATCH),
        ("claim_digest", "7" * 64, RejectionCode.CLAIM_DIGEST_MISMATCH),
        ("test_digest", "7" * 64, RejectionCode.TEST_DIGEST_MISMATCH),
        ("test_node", "other::node", RejectionCode.TEST_NODE_MISMATCH),
        ("policy_source_sha", "6" * 40, RejectionCode.POLICY_SOURCE_MISMATCH),
        ("policy_digest", "7" * 64, RejectionCode.POLICY_DIGEST_MISMATCH),
        ("environment_digest", "7" * 64, RejectionCode.ENVIRONMENT_MISMATCH),
        ("interpreter_digest", "7" * 64, RejectionCode.INTERPRETER_MISMATCH),
        ("executor_profile", "other", RejectionCode.EXECUTOR_PROFILE_MISMATCH),
        ("executor_digest", "7" * 64, RejectionCode.EXECUTOR_DIGEST_MISMATCH),
        ("result_class", "future", RejectionCode.RESULT_CLASS_INVALID),
        ("evidence_class", "future", RejectionCode.EVIDENCE_CLASS_UNSUPPORTED),
        ("provenance_digest", "", RejectionCode.PROVENANCE_INVALID),
    ],
)
def test_receipt_rejects_each_binding_mutation(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
    field: str,
    value: object,
    expected: RejectionCode,
) -> None:
    result = validate_receipt(task, policy, subject, _replace_receipt(receipt, field, value))

    assert not isinstance(result, AcceptedReceipt)
    assert expected in result.codes


@pytest.mark.parametrize(
    ("task_changes", "expected"),
    [
        ({"schema_version": "future"}, RejectionCode.UNKNOWN_TASK_VERSION),
        ({"task_id": ""}, RejectionCode.TASK_INVALID),
        ({"repository_id": ""}, RejectionCode.TASK_INVALID),
        ({"merge_base_sha": "bad"}, RejectionCode.TASK_INVALID),
        ({"head_sha": "bad"}, RejectionCode.TASK_INVALID),
        ({"diff_digest": "bad"}, RejectionCode.TASK_INVALID),
        ({"policy_source_sha": "bad"}, RejectionCode.TASK_INVALID),
        ({"policy_digest": "bad"}, RejectionCode.TASK_INVALID),
    ],
)
def test_receipt_rejects_invalid_task_context(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
    task_changes: dict[str, object],
    expected: RejectionCode,
) -> None:
    result = validate_receipt(replace(task, **task_changes), policy, subject, receipt)

    assert not isinstance(result, AcceptedReceipt)
    assert expected in result.codes


@pytest.mark.parametrize(
    ("side", "changes", "expected"),
    [
        ("head", {"revision_sha": "7" * 40}, RejectionCode.HEAD_RUN_INVALID),
        ("head", {"outcome": "passed"}, RejectionCode.HEAD_RUN_INVALID),
        ("head", {"collected_count": 2}, RejectionCode.HEAD_RUN_INVALID),
        ("head", {"skipped_count": 1}, RejectionCode.HEAD_RUN_INVALID),
        ("head", {"xfailed_count": 1}, RejectionCode.HEAD_RUN_INVALID),
        ("head", {"failure_signature": None}, RejectionCode.HEAD_RUN_INVALID),
        ("base", {"revision_sha": "7" * 40}, RejectionCode.BASE_RUN_INVALID),
        ("base", {"outcome": "failed"}, RejectionCode.BASE_RUN_INVALID),
        ("base", {"collected_count": 0}, RejectionCode.BASE_RUN_INVALID),
        ("base", {"skipped_count": 1}, RejectionCode.BASE_RUN_INVALID),
        ("base", {"xfailed_count": 1}, RejectionCode.BASE_RUN_INVALID),
        ("base", {"failure_signature": "7" * 64}, RejectionCode.BASE_RUN_INVALID),
    ],
)
def test_receipt_rejects_invalid_run_evidence(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
    side: str,
    changes: dict[str, Any],
    expected: RejectionCode,
) -> None:
    field = f"{side}_runs"
    runs = getattr(receipt, field)
    mutated = (replace(runs[0], **changes), *runs[1:])

    result = validate_receipt(
        task, policy, subject, replace(receipt, **{field: mutated})
    )

    assert not isinstance(result, AcceptedReceipt)
    assert expected in result.codes


def test_receipt_rejects_counts_and_duplicate_run_ids(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
) -> None:
    short = validate_receipt(
        task, policy, subject, replace(receipt, head_runs=receipt.head_runs[:1])
    )
    duplicate = replace(
        receipt,
        base_runs=(replace(receipt.base_runs[0], run_id="head-0"), *receipt.base_runs[1:]),
    )
    repeated = validate_receipt(task, policy, subject, duplicate)

    assert not isinstance(short, AcceptedReceipt)
    assert RejectionCode.HEAD_RUN_COUNT_MISMATCH in short.codes
    assert not isinstance(repeated, AcceptedReceipt)
    assert RejectionCode.DUPLICATE_RUN_ID in repeated.codes


def test_valid_receipt_is_the_only_certified_finding_input(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
) -> None:
    accepted = validate_receipt(task, policy, subject, receipt)

    assert isinstance(accepted, AcceptedReceipt)
    with pytest.raises(TypeError):
        AcceptedReceipt(receipt)  # type: ignore[call-arg]
    finding = CertifiedFinding.from_accepted_receipt(
        accepted, (FindingAnchor(path="src/pkg.py", line=12),)
    )
    assert finding.claim == receipt.normalized_claim
    assert finding.accepted_receipt is accepted
