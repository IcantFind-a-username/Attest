"""D-174: what the per-unit Bonferroni family actually bounds at pull-request level.

D-125 made the family the change unit, and said the pull-request bound was
``hard_cap * alpha`` -- three claims are visible, so at most three units can be
wrong. That reasoning is wrong in the only direction that matters. Bonferroni
over ``m_u`` controls the family-wise error **inside a unit**; across units the
tests are separate families and the union bound over the units that were
*searched* is ``min(1, U * alpha)``. The hard cap truncates the **display**, not
the search: a unit that produced a false claim which the cap then hid was still
a unit whose null was rejected, and the cap cannot un-reject it.

This test measures the rate with the real selector rather than arguing about it.
"""

from __future__ import annotations

import hashlib
import random

from attest.certification.selection import (
    FamilyPolicy,
    ScoredFinding,
    select_for_publication,
)
from attest.certification.types import (
    _ACCEPTED_RECEIPT_TOKEN,
    AcceptedReceipt,
    CertificationReceipt,
    CertifiedFinding,
    FindingAnchor,
)

UNITS = 10
ALPHA = 0.1
E_UNDER_NULL = 10.0  # exactly the per-unit bar at m_u = 1
HIT_PROBABILITY = 0.1  # a valid e-value under the null clears m/alpha at most alpha
TRIALS = 4000


def _finding(receipt: CertificationReceipt, candidate_id: str, path: str) -> CertifiedFinding:
    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()
    accepted = AcceptedReceipt._from_validated(
        CertificationReceipt(
            **{**receipt.__dict__, "candidate_id": candidate_id, "test_digest": digest}
        ),
        _ACCEPTED_RECEIPT_TOKEN,
    )
    return CertifiedFinding.from_accepted_receipt(accepted, (FindingAnchor(path=path, line=1),))


def test_the_pull_request_error_rate_is_the_union_over_units_not_the_cap(
    receipt: CertificationReceipt,
) -> None:
    """Ten units, one eligible candidate each, alpha 0.1. Each unit's e-value is
    a valid e-value under the null -- 10 with probability 0.1, 0 otherwise -- so
    each unit publishes with probability exactly alpha, and the pull request
    publishes something with probability ``1 - 0.9**10 = 0.651``.

    That is above ``hard_cap * alpha = 0.3`` and below ``min(1, U * alpha) = 1``.
    The rate is what it is; what changes is which sentence the product prints
    about it."""
    paths = [f"src/unit{i}.py" for i in range(UNITS)]
    findings = [_finding(receipt, f"cand-{i}", path) for i, path in enumerate(paths)]
    policy = FamilyPolicy(
        alpha=ALPHA,
        eligible_count=UNITS,
        hard_cap=3,
        eligible_units=dict.fromkeys(paths, 1),
    )
    rng = random.Random(20260908)
    wrong = 0
    for _ in range(TRIALS):
        scored = [
            ScoredFinding(
                finding, E_UNDER_NULL if rng.random() < HIT_PROBABILITY else 0.0
            )
            for finding in findings
        ]
        if select_for_publication(scored, policy, [item.e_value for item in scored]).published:
            wrong += 1
    rate = wrong / TRIALS

    assert 0.60 < rate < 0.70  # the analytic 0.651, within Monte-Carlo noise
    assert rate > policy.hard_cap * ALPHA  # the bound D-125 claimed
    assert rate <= min(1.0, UNITS * ALPHA)  # the bound that actually holds


def test_the_selection_reports_the_bound_it_actually_offers(
    receipt: CertificationReceipt,
) -> None:
    """The three numbers a reader needs to size the claim, on the record."""
    paths = [f"src/unit{i}.py" for i in range(UNITS)]
    findings = [_finding(receipt, f"cand-{i}", path) for i, path in enumerate(paths)]
    policy = FamilyPolicy(
        alpha=ALPHA,
        eligible_count=UNITS,
        hard_cap=3,
        eligible_units=dict.fromkeys(paths, 1),
    )
    selection = select_for_publication(
        [ScoredFinding(finding, 12.0) for finding in findings],
        policy,
        [12.0] * UNITS,
    )

    assert selection.units_searched == UNITS
    assert selection.pr_error_bound == min(1.0, UNITS * ALPHA)
    assert selection.e_value_validity == "assumed-calibrated"
    # the cap truncates the display and not the search
    assert len(selection.published) == 3
    assert selection.units_searched > len(selection.published)


def test_a_smaller_pull_request_gets_a_smaller_bound(
    receipt: CertificationReceipt,
) -> None:
    """`min(1, U * alpha)` is not a constant: two units at alpha 0.1 is 0.2."""
    findings = [_finding(receipt, f"c{i}", f"src/u{i}.py") for i in range(2)]
    policy = FamilyPolicy(
        alpha=ALPHA,
        eligible_count=2,
        hard_cap=3,
        eligible_units={"src/u0.py": 1, "src/u1.py": 1},
    )
    selection = select_for_publication(
        [ScoredFinding(finding, 12.0) for finding in findings], policy, [12.0, 12.0]
    )

    assert selection.units_searched == 2
    assert selection.pr_error_bound == 0.2
