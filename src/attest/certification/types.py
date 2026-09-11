"""Frozen values owned by the certification boundary."""

from __future__ import annotations

from dataclasses import dataclass

CERTIFICATION_TASK_SCHEMA_VERSION = "attest.certification-task.v1"
CERTIFICATION_POLICY_SCHEMA_VERSION = "attest.certification-policy.v1"
CERTIFICATION_RECEIPT_SCHEMA_VERSION = "attest.certification-receipt.v4"
# Owner authorisation 2 of 2026-09-12: the receipt **body** -- the field set the
# provenance digest is computed over -- is versioned apart from the schema. v1
# is the set every bundle sealed before 2026-09-12 was digested over; v2 adds
# `body_version` itself and `contained_attempts` (D-217). A receipt is digested
# under the body version it records, so a v1 bundle keeps the digest it was
# sealed with (INV-VERSION-001) and a v2 receipt's digest covers what it
# discloses.
RECEIPT_BODY_V1 = "attest.receipt-body.v1"
RECEIPT_BODY_V2 = "attest.receipt-body.v2"
RECEIPT_BODY_VERSION = RECEIPT_BODY_V2
KNOWN_RECEIPT_BODY_VERSIONS = frozenset({RECEIPT_BODY_V1, RECEIPT_BODY_V2})


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
    binding_policy_version: str = ""  # V-02; "" means no binding is required (legacy)
    intent_policy_version: str = ""  # D-102; "" means no intent observation is required


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
    binding_policy_version: str = ""  # V-02
    binding_digest: str = ""  # digest of the recorded BindingObservation
    intent_policy_version: str = ""  # D-102
    intent_digest: str = ""  # digest of the recorded IntentObservation
    # Which field set the provenance digest covers. The default is the current
    # version; a bundle written before the field exists is read back as v1 by
    # the verifier, never by this default.
    body_version: str = RECEIPT_BODY_VERSION
    # D-217, disclosed in the receipt under body v2: every process or thread
    # creation the kernel refused across the certified runs. Empty under the
    # product's setting where such an attempt voids the run, and always empty
    # under body v1, whose digest could not cover it.
    contained_attempts: tuple[str, ...] = ()


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
