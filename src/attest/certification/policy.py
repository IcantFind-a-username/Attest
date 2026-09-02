"""Pure validation for base-owned certification policy values."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .types import (
    CERTIFICATION_POLICY_SCHEMA_VERSION,
    CERTIFICATION_RECEIPT_SCHEMA_VERSION,
    CertificationPolicy,
)

# D-102: a behavior-change receipt proves head rejects an input the base accepted
KNOWN_EVIDENCE_CLASSES = frozenset({"regression_reproduced", "behavior_change"})


class PolicyRejectionCode(StrEnum):
    UNKNOWN_VERSION = "unknown_policy_version"
    UNKNOWN_RECEIPT_VERSION = "unknown_receipt_version"
    INVALID_RUN_COUNT = "invalid_run_count"
    INVALID_EXECUTOR_PROFILE = "invalid_executor_profile"
    UNKNOWN_EVIDENCE_CLASS = "unknown_evidence_class"


@dataclass(frozen=True)
class PolicyRejection:
    codes: tuple[PolicyRejectionCode, ...]


def validate_policy(policy: CertificationPolicy) -> PolicyRejection | None:
    """Return all deterministic policy-version/value failures, or ``None``."""
    codes: list[PolicyRejectionCode] = []
    if policy.schema_version != CERTIFICATION_POLICY_SCHEMA_VERSION:
        codes.append(PolicyRejectionCode.UNKNOWN_VERSION)
    if policy.receipt_schema_version != CERTIFICATION_RECEIPT_SCHEMA_VERSION:
        codes.append(PolicyRejectionCode.UNKNOWN_RECEIPT_VERSION)
    if (
        type(policy.required_head_runs) is not int
        or policy.required_head_runs < 1
        or type(policy.required_base_runs) is not int
        or policy.required_base_runs < 1
    ):
        codes.append(PolicyRejectionCode.INVALID_RUN_COUNT)
    profiles = policy.allowed_executor_profiles
    if (
        type(profiles) is not tuple
        or not profiles
        or any(type(profile) is not str or not profile.strip() for profile in profiles)
        or len(set(profiles)) != len(profiles)
    ):
        codes.append(PolicyRejectionCode.INVALID_EXECUTOR_PROFILE)
    classes = policy.allowed_evidence_classes
    if (
        type(classes) is not tuple
        or not classes
        or any(value not in KNOWN_EVIDENCE_CLASSES for value in classes)
        or len(set(classes)) != len(classes)
    ):
        codes.append(PolicyRejectionCode.UNKNOWN_EVIDENCE_CLASS)
    return PolicyRejection(tuple(codes)) if codes else None
