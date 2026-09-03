"""D-102: a new rejection publishes only with a base-tree witness; otherwise the drawer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace

import pytest

from attest.certification.intent import (
    EVIDENCE_CLASS_BEHAVIOR_CHANGE,
    EVIDENCE_CLASS_REGRESSION,
    INTENT_POLICY_V1,
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
from attest.review.evidence import intent_reasons

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


# --- the audit chain: a receipt verifies under the policy version it records ---


def v1_observation(**overrides: object) -> IntentObservation:
    """A receipt written under `attest.intent.new-rejection.v1`, before D-120: a
    regression, with none of the constant fields v2 added."""
    values: dict[str, object] = {
        "policy_version": INTENT_POLICY_V1,
        "path": "services/analysis_core/us_stock_helper_core/scoring.py",
        "changed_lines": (5, 6, 7),
        "origin_line": 0,
        "origin_statement": "",
        "exception_type": "",
        "new_rejection": False,
        "rejected_inputs": (),
        "witnesses": (),
        "head_runs_observed": 3,
    }
    values.update(overrides)
    return IntentObservation(**values)  # type: ignore[arg-type]


def test_a_v1_receipt_still_verifies_under_the_v1_rules() -> None:
    """The audit-chain promise: bumping the policy version may not silently
    invalidate every receipt already issued."""
    observation = v1_observation()

    assert intent_verdict(observation) is None
    assert evidence_class_for(observation) == EVIDENCE_CLASS_REGRESSION


def test_a_v1_digest_is_computed_over_the_fields_v1_defined() -> None:
    """v2 added two fields to the dataclass. A v1 observation's digest must not
    move because of them, or every v1 bundle fails its digest check."""
    observation = v1_observation()

    assert observation.digest() == hashlib.sha256(
        json.dumps(
            {
                "policy_version": INTENT_POLICY_V1,
                "path": "services/analysis_core/us_stock_helper_core/scoring.py",
                "changed_lines": [5, 6, 7],
                "origin_line": 0,
                "origin_statement": "",
                "exception_type": "",
                "new_rejection": False,
                "rejected_inputs": [],
                "witnesses": [],
                "head_runs_observed": 3,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def test_the_v2_constant_rule_is_not_applied_to_a_v1_receipt() -> None:
    """D-120 did not exist under v1; a v1 observation cannot be re-judged by it,
    however its fields are filled in."""
    observation = v1_observation(constant_substitution=True, asserted_constants=('"v1"',))

    assert evidence_class_for(observation) == EVIDENCE_CLASS_REGRESSION
    assert intent_verdict(observation) is None


def test_an_unknown_intent_policy_still_fails_closed() -> None:
    observation = v1_observation(policy_version="attest.intent.v99")

    assert intent_verdict(observation) == "unknown intent policy"


def test_the_verifier_reads_a_v1_intent_record_and_judges_it_under_v1() -> None:
    """`verify_bundle`'s intent step, on the record a v1 bundle actually holds:
    ten keys, none of them D-120's."""
    observation = v1_observation()
    record = {
        "policy_version": observation.policy_version,
        "path": observation.path,
        "changed_lines": list(observation.changed_lines),
        "origin_line": observation.origin_line,
        "origin_statement": observation.origin_statement,
        "exception_type": observation.exception_type,
        "new_rejection": observation.new_rejection,
        "rejected_inputs": list(observation.rejected_inputs),
        "witnesses": [],
        "head_runs_observed": observation.head_runs_observed,
    }

    assert (
        intent_reasons(
            record,
            receipt_policy_version=INTENT_POLICY_V1,
            receipt_intent_digest=observation.digest(),
            receipt_evidence_class=EVIDENCE_CLASS_REGRESSION,
        )
        == ()
    )


def test_the_verifier_rejects_a_v1_record_carrying_a_field_v1_never_had() -> None:
    """The digest is computed over v1's fields, so a v2-only key smuggled into a
    v1 record would not be bound by it. It is refused instead."""
    observation = v1_observation()
    record = {
        "policy_version": observation.policy_version,
        "path": observation.path,
        "changed_lines": list(observation.changed_lines),
        "origin_line": observation.origin_line,
        "origin_statement": observation.origin_statement,
        "exception_type": observation.exception_type,
        "new_rejection": observation.new_rejection,
        "rejected_inputs": list(observation.rejected_inputs),
        "witnesses": [],
        "head_runs_observed": observation.head_runs_observed,
        "constant_substitution": True,
    }

    reasons = intent_reasons(
        record,
        receipt_policy_version=INTENT_POLICY_V1,
        receipt_intent_digest=observation.digest(),
        receipt_evidence_class=EVIDENCE_CLASS_REGRESSION,
    )

    assert reasons == ("intent observation malformed",)


def test_a_retired_policy_cannot_authorise_a_new_publication(
    task: CertificationTask,
    policy: CertificationPolicy,
    subject: CertificationSubject,
    receipt: CertificationReceipt,
) -> None:
    """Keeping v1 verifiable is a promise about receipts already issued. A task
    running under today's policy still refuses a receipt that names the old one."""
    today = replace(policy, intent_policy_version=INTENT_POLICY_VERSION)
    retired = replace(
        receipt,
        intent_policy_version=INTENT_POLICY_V1,
        intent_digest=v1_observation().digest(),
    )

    verdict = validate_receipt(task, today, subject, retired)

    assert not isinstance(verdict, AcceptedReceipt)
    assert RejectionCode.INTENT_POLICY_MISMATCH in verdict.codes
