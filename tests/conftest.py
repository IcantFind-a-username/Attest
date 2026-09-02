"""Fixtures for isolated test-owned benchmark authority roots."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

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
from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.config import load_pricing
from attest.review.executor import ExecutorLimits, VerificationRun, verify_candidate
from attest.review.gate import GateResult
from attest.review.proposer import Provider

VerifyWithDefaults = Callable[..., VerificationRun]
CertifiedFactory = Callable[..., CertifiedFinding]


@pytest.fixture
def certified_factory() -> CertifiedFactory:
    """Build a CertifiedFinding the only legal way: through the validator."""

    def build(
        *,
        claim: str = "Null input reaches the serializer.",
        path: str = "src/service.py",
        line: int = 24,
        candidate_id: str | None = None,
    ) -> CertifiedFinding:
        candidate = candidate_id or hashlib.sha256(
            f"{path}:{line}:{claim}".encode()
        ).hexdigest()[:10]
        task = CertificationTask(
            schema_version=CERTIFICATION_TASK_SCHEMA_VERSION,
            task_id="task-1",
            repository_id="owner/repository",
            merge_base_sha="2" * 40,
            head_sha="1" * 40,
            diff_digest="a" * 64,
            policy_source_sha="3" * 40,
            policy_digest="b" * 64,
        )
        policy = CertificationPolicy(
            schema_version=CERTIFICATION_POLICY_SCHEMA_VERSION,
            receipt_schema_version=CERTIFICATION_RECEIPT_SCHEMA_VERSION,
            required_head_runs=3,
            required_base_runs=3,
            allowed_executor_profiles=("language-guard-v1",),
            allowed_evidence_classes=("regression_reproduced",),
        )
        normalized = " ".join(claim.split())
        subject = CertificationSubject(
            candidate_id=candidate,
            normalized_claim=normalized,
            claim_digest=hashlib.sha256(normalized.encode()).hexdigest(),
            test_digest="d" * 64,
            test_node="test_repro.py::test_case",
            environment_digest="e" * 64,
            interpreter_digest="f" * 64,
            executor_profile="language-guard-v1",
            executor_digest="0" * 64,
        )
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
            for index in range(3)
        )
        base_runs = tuple(
            ExecutionRun(
                run_id=f"base-{index}",
                revision_sha=task.merge_base_sha,
                outcome="passed",
                artifact_digest=str(index + 7) * 64,
                collected_count=1,
                skipped_count=0,
                xfailed_count=0,
                failure_signature=None,
            )
            for index in range(3)
        )
        receipt = CertificationReceipt(
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
            provenance_digest=hashlib.sha256(f"receipt:{candidate}".encode()).hexdigest(),
        )
        accepted = validate_receipt(task, policy, subject, receipt)
        assert isinstance(accepted, AcceptedReceipt), accepted
        return CertifiedFinding.from_accepted_receipt(
            accepted, (FindingAnchor(path=path, line=line),)
        )

    return build


@pytest.fixture
def verify_with_defaults() -> VerifyWithDefaults:
    """Verify a candidate with the production defaults used by executor tests."""

    def run(
        repo: Path,
        stored: StoredCandidate,
        gate: GateResult,
        provider: Provider,
        *,
        base_sha: str,
        head_sha: str,
    ) -> VerificationRun:
        pricing = load_pricing()
        return verify_candidate(
            repo,
            stored,
            gate,
            provider,
            Budget(limit_usd=1.0, model=str(pricing["default_model"])),
            ExecutorLimits(),
            base_sha=base_sha,
            head_sha=head_sha,
        )

    return run


@pytest.fixture
def comparison_cli_authority(tmp_path: Path) -> tuple[Path, str]:
    """Create stable owner inputs outside a compare command's output tree."""

    authority_root = tmp_path / "comparison-owner"
    run_identity = hashlib.sha256(str(authority_root).encode("utf-8")).hexdigest()
    return authority_root, run_identity
