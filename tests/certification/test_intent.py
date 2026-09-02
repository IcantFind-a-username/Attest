"""D-102: a new rejection publishes only with a base-tree witness; otherwise the drawer."""

from __future__ import annotations

from dataclasses import replace

import pytest

from attest.certification.intent import (
    EVIDENCE_CLASS_BEHAVIOR_CHANGE,
    EVIDENCE_CLASS_REGRESSION,
    INTENT_POLICY_VERSION,
    INTENT_UNKNOWN_LABEL,
    INTENT_UNKNOWN_LABEL_ZH,
    IntentObservation,
    evidence_class_for,
    intent_verdict,
)
from attest.certification.policy import validate_policy
from attest.certification.types import (
    AcceptedReceipt,
    CertificationPolicy,
    CertificationReceipt,
    CertificationSubject,
    CertificationTask,
)
from attest.certification.validate import RejectionCode, validate_receipt

PATH = "services/analysis_core/us_stock_helper_core/patterns_shapes.py"
FABRICATED = ("买入价曾经历史新高", "本次形态与", "相关，仅作历史信息呈现")


def natural_null_observation(**overrides: object) -> IntentObservation:
    """The E-01 publication on `3a32c92` as the discriminator sees it: the head
    failure is a ``raise`` on a changed line and the generated test fabricated
    its "legitimate" phrase."""
    values: dict[str, object] = {
        "policy_version": INTENT_POLICY_VERSION,
        "path": PATH,
        "changed_lines": tuple(range(331, 356)),
        "origin_line": 347,
        "origin_statement": "raise",
        "exception_type": "ValueError",
        "new_rejection": True,
        "rejected_inputs": FABRICATED,
        "witnesses": (),
        "head_runs_observed": 3,
    }
    values.update(overrides)
    return IntentObservation(**values)  # type: ignore[arg-type]


def test_the_natural_null_publication_goes_to_the_drawer_with_the_label() -> None:
    observation = natural_null_observation()

    verdict = intent_verdict(observation)

    assert evidence_class_for(observation) == EVIDENCE_CLASS_BEHAVIOR_CHANGE
    assert verdict is not None
    assert verdict.startswith(INTENT_UNKNOWN_LABEL)
    assert INTENT_UNKNOWN_LABEL_ZH in verdict
    assert "raise statement on a changed line" in verdict
    # the verdict is author-visible: it names neither the line nor the input
    assert PATH not in verdict and "347" not in verdict
    assert "买入价曾经历史新高" not in verdict


def test_a_rejection_of_an_input_the_base_tree_attests_may_publish() -> None:
    witnessed = natural_null_observation(
        witnesses=tuple(
            (literal, "services/analysis_core/tests/test_patterns_shapes.py")
            for literal in FABRICATED
        )
    )

    assert intent_verdict(witnessed) is None
    assert evidence_class_for(witnessed) == EVIDENCE_CLASS_BEHAVIOR_CHANGE


def test_every_rejected_input_needs_a_witness() -> None:
    partial = natural_null_observation(
        witnesses=(("本次形态与", "services/analysis_core/tests/test_patterns_shapes.py"),)
    )

    verdict = intent_verdict(partial)

    assert verdict is not None and "not in the base tree" in verdict


def test_an_unidentified_rejected_input_goes_to_the_drawer() -> None:
    verdict = intent_verdict(natural_null_observation(rejected_inputs=()))

    assert verdict is not None
    assert "no rejected input could be identified" in verdict
    assert INTENT_UNKNOWN_LABEL_ZH in verdict


def test_a_regression_keeps_its_class_and_publishes() -> None:
    regression = natural_null_observation(
        origin_line=0,
        origin_statement="",
        exception_type="",
        new_rejection=False,
        rejected_inputs=(),
    )

    assert intent_verdict(regression) is None
    assert evidence_class_for(regression) == EVIDENCE_CLASS_REGRESSION


def test_a_crash_on_a_changed_line_is_not_a_rejection() -> None:
    crash = natural_null_observation(
        origin_statement="other", exception_type="AttributeError", new_rejection=False
    )

    assert intent_verdict(crash) is None
    assert evidence_class_for(crash) == EVIDENCE_CLASS_REGRESSION


@pytest.mark.parametrize(
    "overrides",
    [
        {"origin_statement": "other"},
        {"origin_line": 10},
        {"policy_version": "attest.intent.future"},
        {"head_runs_observed": 0},
    ],
)
def test_an_inconsistent_new_rejection_never_publishes(overrides: dict[str, object]) -> None:
    witnessed = natural_null_observation(
        witnesses=tuple((literal, "tests/test_x.py") for literal in FABRICATED), **overrides
    )

    assert intent_verdict(witnessed) is not None


def test_the_digest_binds_every_field() -> None:
    base = natural_null_observation()
    assert base.digest() == natural_null_observation().digest()
    assert base.digest() != replace(base, witnesses=(("本次形态与", "tests/t.py"),)).digest()
    assert base.digest() != replace(base, origin_line=348).digest()


def test_policy_knows_the_behavior_change_class(policy: CertificationPolicy) -> None:
    assert validate_policy(replace(policy, allowed_evidence_classes=("behavior_change",))) is None


def test_a_behavior_change_receipt_needs_the_intent_policy_and_digest(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
) -> None:
    allowing = replace(
        policy, allowed_evidence_classes=("regression_reproduced", "behavior_change")
    )
    unbound = replace(receipt, evidence_class="behavior_change")
    verdict = validate_receipt(task, allowing, subject, unbound)
    assert not isinstance(verdict, AcceptedReceipt)
    assert RejectionCode.INTENT_POLICY_MISMATCH in verdict.codes

    intent_policy = replace(allowing, intent_policy_version=INTENT_POLICY_VERSION)
    missing_digest = replace(unbound, intent_policy_version=INTENT_POLICY_VERSION)
    verdict = validate_receipt(task, intent_policy, subject, missing_digest)
    assert not isinstance(verdict, AcceptedReceipt)
    assert RejectionCode.INTENT_DIGEST_INVALID in verdict.codes

    bound = replace(missing_digest, intent_digest=natural_null_observation().digest())
    assert isinstance(validate_receipt(task, intent_policy, subject, bound), AcceptedReceipt)
    # and a regression receipt under an intent policy is bound the same way
    regression = replace(bound, evidence_class="regression_reproduced")
    assert isinstance(validate_receipt(task, intent_policy, subject, regression), AcceptedReceipt)
    stale = replace(regression, intent_policy_version="")
    assert not isinstance(validate_receipt(task, intent_policy, subject, stale), AcceptedReceipt)
