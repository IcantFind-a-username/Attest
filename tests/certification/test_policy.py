from __future__ import annotations

from dataclasses import replace

import pytest

from attest.certification.policy import PolicyRejectionCode, validate_policy
from attest.certification.types import CertificationPolicy


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"schema_version": "future"}, PolicyRejectionCode.UNKNOWN_VERSION),
        (
            {"receipt_schema_version": "future"},
            PolicyRejectionCode.UNKNOWN_RECEIPT_VERSION,
        ),
        ({"required_head_runs": 0}, PolicyRejectionCode.INVALID_RUN_COUNT),
        ({"required_base_runs": 0}, PolicyRejectionCode.INVALID_RUN_COUNT),
        ({"allowed_executor_profiles": ()}, PolicyRejectionCode.INVALID_EXECUTOR_PROFILE),
        (
            {"allowed_executor_profiles": ("",)},
            PolicyRejectionCode.INVALID_EXECUTOR_PROFILE,
        ),
        (
            {"allowed_executor_profiles": ("container-v1", "container-v1")},
            PolicyRejectionCode.INVALID_EXECUTOR_PROFILE,
        ),
        (
            {"allowed_evidence_classes": ("future",)},
            PolicyRejectionCode.UNKNOWN_EVIDENCE_CLASS,
        ),
        (
            {
                "allowed_evidence_classes": (
                    "regression_reproduced",
                    "regression_reproduced",
                )
            },
            PolicyRejectionCode.UNKNOWN_EVIDENCE_CLASS,
        ),
    ],
)
def test_policy_rejects_invalid_or_unknown_values(
    policy: CertificationPolicy,
    changes: dict[str, object],
    expected: PolicyRejectionCode,
) -> None:
    rejection = validate_policy(replace(policy, **changes))

    assert rejection is not None
    assert expected in rejection.codes


def test_policy_accepts_current_version(policy: CertificationPolicy) -> None:
    assert validate_policy(policy) is None
