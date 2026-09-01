"""Frozen values owned by the certification boundary."""

from __future__ import annotations

from dataclasses import dataclass

CERTIFICATION_TASK_SCHEMA_VERSION = "attest.certification-task.v1"
CERTIFICATION_POLICY_SCHEMA_VERSION = "attest.certification-policy.v1"
CERTIFICATION_RECEIPT_SCHEMA_VERSION = "attest.certification-receipt.v2"


@dataclass(frozen=True)
class CertificationTask:
    schema_version: str
    task_id: str
    repository_id: str
    merge_base_sha: str
    head_sha: str
    diff_digest: str
    policy_source_sha: str
    policy_digest: str


@dataclass(frozen=True)
class CertificationPolicy:
    schema_version: str
    receipt_schema_version: str
    required_head_runs: int
    required_base_runs: int
    allowed_executor_profiles: tuple[str, ...]
    allowed_evidence_classes: tuple[str, ...]


@dataclass(frozen=True)
class CertificationSubject:
    candidate_id: str
    normalized_claim: str
    claim_digest: str
    test_digest: str
    test_node: str
    environment_digest: str
    interpreter_digest: str
    executor_profile: str
    executor_digest: str

    def __post_init__(self) -> None:
        if type(self.normalized_claim) is str:
            object.__setattr__(
                self, "normalized_claim", " ".join(self.normalized_claim.split())
            )


@dataclass(frozen=True)
class ExecutionRun:
    run_id: str
    revision_sha: str
    outcome: str
    artifact_digest: str
    collected_count: int
    skipped_count: int
    xfailed_count: int
    failure_signature: str | None


@dataclass(frozen=True)
class CertificationReceipt:
    schema_version: str
    policy_version: str
    task_id: str
    repository_id: str
    merge_base_sha: str
    head_sha: str
    diff_digest: str
    candidate_id: str
    normalized_claim: str
    claim_digest: str
    test_digest: str
    test_node: str
    policy_source_sha: str
    policy_digest: str
    environment_digest: str
    interpreter_digest: str
    executor_profile: str
    executor_digest: str
    head_runs: tuple[ExecutionRun, ...]
    base_runs: tuple[ExecutionRun, ...]
    result_class: str
    evidence_class: str
    provenance_digest: str


_ACCEPTED_RECEIPT_TOKEN = object()


@dataclass(frozen=True, init=False)
class AcceptedReceipt:
    """A receipt value that only the pure validator can construct."""

    receipt: CertificationReceipt

    @classmethod
    def _from_validated(
        cls, receipt: CertificationReceipt, token: object
    ) -> AcceptedReceipt:
        if token is not _ACCEPTED_RECEIPT_TOKEN:
            raise TypeError("AcceptedReceipt requires validator authority")
        accepted = object.__new__(cls)
        object.__setattr__(accepted, "receipt", receipt)
        return accepted


@dataclass(frozen=True)
class FindingAnchor:
    path: str
    line: int


@dataclass(frozen=True, init=False)
class CertifiedFinding:
    """Author-visible finding material rooted in one accepted receipt."""

    accepted_receipt: AcceptedReceipt
    claim: str
    anchors: tuple[FindingAnchor, ...]

    @classmethod
    def from_accepted_receipt(
        cls,
        accepted_receipt: AcceptedReceipt,
        anchors: tuple[FindingAnchor, ...],
    ) -> CertifiedFinding:
        if not anchors or any(
            not anchor.path or anchor.line < 1 for anchor in anchors
        ):
            raise ValueError("a certified finding requires valid anchors")
        finding = object.__new__(cls)
        object.__setattr__(finding, "accepted_receipt", accepted_receipt)
        object.__setattr__(finding, "claim", accepted_receipt.receipt.normalized_claim)
        object.__setattr__(finding, "anchors", anchors)
        return finding
