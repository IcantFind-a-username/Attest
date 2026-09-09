"""D-125: the publication family is the change unit, and the partition is
order-invariant and deterministic.

**D-199 (2026-09-13) stopped applying that bar.** D-125's own behavioural
properties are pinned here under the schema version that owns them,
``attest.publication-policy.v3`` -- which is exactly the replay rule D-199
added, exercised on the tests that first established the behaviour. The v4
behaviour has its own three tests at the end of the file.

The one required RED (owner decision 2 of 2026-09-04). Three properties, one
test each, plus the behaviour the decision exists to produce: a finding that the
PR-wide bar suppressed publishes when its own file holds few eligible
candidates, and one competing inside a crowded file still does not.
"""

from __future__ import annotations

import hashlib
import random

import pytest

from attest.certification.selection import (
    PUBLICATION_POLICY_SCHEMA_VERSION,
    REASON_BELOW_THRESHOLD,
    REASON_BEYOND_CAP,
    FamilyPolicy,
    ScoredFinding,
    finding_unit,
    score_bar_applies,
    select_for_publication,
)
from attest.certification.types import (
    _ACCEPTED_RECEIPT_TOKEN,
    AcceptedReceipt,
    CertificationReceipt,
    CertifiedFinding,
    FindingAnchor,
)
from attest.certification.units import CHANGE_UNIT_POLICY_VERSION, change_unit, unit_counts

V3 = "attest.publication-policy.v3"  # the last version that applied the score bar


def _finding(
    receipt: CertificationReceipt, candidate_id: str, path: str, line: int
) -> CertifiedFinding:
    """One certified finding with its own reproduction, so the publication
    clusterer keeps distinct anchors distinct."""
    digest = hashlib.sha256(candidate_id.encode("utf-8")).hexdigest()
    accepted = AcceptedReceipt._from_validated(
        CertificationReceipt(
            **{**receipt.__dict__, "candidate_id": candidate_id, "test_digest": digest}
        ),
        _ACCEPTED_RECEIPT_TOKEN,
    )
    return CertifiedFinding.from_accepted_receipt(accepted, (FindingAnchor(path=path, line=line),))


def test_the_unit_partition_is_order_invariant_and_deterministic() -> None:
    """Every permutation of the eligible anchors yields the same units, the same
    counts, and therefore the same threshold for every unit."""
    anchors = [
        "src/pkg/a.py",
        "src/pkg/a.py",
        "src/pkg/a.py",
        "src/pkg/b.py",
        "docs/readme.md",
        "src\\pkg\\b.py",  # a Windows-style anchor for a file already counted
    ]
    expected = {"src/pkg/a.py": 3, "src/pkg/b.py": 2, "docs/readme.md": 1}
    assert dict(unit_counts(anchors)) == expected

    rng = random.Random(20260904)
    for _ in range(50):
        shuffled = anchors[:]
        rng.shuffle(shuffled)
        assert dict(unit_counts(shuffled)) == expected

    # deterministic: the same anchor always names the same unit, and the unit is
    # a function of that anchor alone -- nothing about the rest of the batch
    assert change_unit("src/pkg/a.py") == change_unit("src\\pkg\\a.py") == "src/pkg/a.py"
    assert CHANGE_UNIT_POLICY_VERSION == "attest.change-unit.file.v1"


def test_the_unit_partition_is_total_and_counts_each_candidate_once(
    receipt: CertificationReceipt,
) -> None:
    """Units partition the eligible set: every candidate lands in exactly one,
    and the unit sizes sum to the PR-wide eligible count."""
    paths = ["a.py", "a.py", "b.py", "c/d.py", "b.py", "b.py"]
    counts = unit_counts(paths)
    assert sum(counts.values()) == len(paths)
    for index, path in enumerate(paths):
        finding = _finding(receipt, f"cand-{index}", path, 1)
        assert finding_unit(finding) in counts


def test_a_finding_is_judged_by_its_own_unit_not_the_pull_request(
    receipt: CertificationReceipt,
) -> None:
    """The behaviour the decision buys. Ten eligible candidates in the PR, but
    the certified finding is alone in its file: at alpha 0.1 the PR-wide bar is
    100 and the unit bar is 10, so an e-value of 12 publishes where it did not.
    A second finding competing inside a file with eight eligible candidates has
    a bar of 80 and stays suppressed."""
    alone = _finding(receipt, "alone", "src/rare.py", 10)
    crowded = _finding(receipt, "crowded", "src/busy.py", 400)
    policy = FamilyPolicy(
        alpha=0.1,
        eligible_count=10,
        hard_cap=3,
        eligible_units={"src/rare.py": 1, "src/busy.py": 8, "src/other.py": 1},
        schema_version=V3,
    )
    assert policy.pr_family_threshold == pytest.approx(100.0)
    assert policy.threshold_for("src/rare.py") == pytest.approx(10.0)
    assert policy.threshold_for("src/busy.py") == pytest.approx(80.0)

    selection = select_for_publication(
        [ScoredFinding(alone, 12.0), ScoredFinding(crowded, 12.0)],
        policy,
        [1.0] * 10,
    )
    published = [f.accepted_receipt.receipt.candidate_id for f in selection.published]
    assert published == ["alone"]
    suppressed = {
        item.finding.accepted_receipt.receipt.candidate_id: item.reason
        for item in selection.suppressed
    }
    assert suppressed == {"crowded": REASON_BELOW_THRESHOLD}
    # both bars are on the record: the one applied, and the PR-wide one it replaced
    assert selection.unit_thresholds == {"src/busy.py": 80.0, "src/rare.py": 10.0}
    assert selection.family_threshold == pytest.approx(100.0)


def test_selection_is_unchanged_by_the_order_the_findings_arrive_in(
    receipt: CertificationReceipt,
) -> None:
    """Order-invariance end to end, not only in the counter."""
    findings = [
        ScoredFinding(_finding(receipt, "a", "src/one.py", 10), 30.0),
        ScoredFinding(_finding(receipt, "b", "src/two.py", 20), 25.0),
        ScoredFinding(_finding(receipt, "c", "src/two.py", 200), 5.0),
        ScoredFinding(_finding(receipt, "d", "src/three.py", 30), 40.0),
    ]
    policy = FamilyPolicy(
        alpha=0.1,
        eligible_count=9,
        hard_cap=3,
        eligible_units={"src/one.py": 2, "src/two.py": 5, "src/three.py": 2},
        schema_version=V3,
    )
    rng = random.Random(4)
    baseline = None
    for _ in range(24):
        shuffled = findings[:]
        rng.shuffle(shuffled)
        selection = select_for_publication(shuffled, policy, [1.0] * 9)
        shape = (
            tuple(f.accepted_receipt.receipt.candidate_id for f in selection.published),
            tuple(
                (item.finding.accepted_receipt.receipt.candidate_id, item.reason)
                for item in selection.suppressed
            ),
            tuple(sorted(selection.unit_thresholds.items())),
        )
        baseline = shape if baseline is None else baseline
        assert shape == baseline
    assert baseline is not None and baseline[0] == ("d", "a")


def test_a_reproduced_receipt_publishes_whatever_its_score(
    receipt: CertificationReceipt,
) -> None:
    """The one required RED for D-199. The score bar is no longer applied: a
    certified finding -- accepted receipt, reproduction reproduced -- publishes
    subject only to same-defect clustering and the hard cap. The bar it would
    have faced is still computed and reported, because the record has to keep
    saying what the old rule would have done.

    The population is the shape the census found suppressed most often: one
    crowded file whose bar (80) is far above the ceiling a certified finding can
    ever reach (S_CAP x V_CAP = 60, D-197).
    """
    findings = [
        ScoredFinding(_finding(receipt, "low", "src/busy.py", 10), 40.0),
        ScoredFinding(_finding(receipt, "high", "src/busy.py", 400), 60.0),
    ]
    policy = FamilyPolicy(
        alpha=0.1, eligible_count=8, hard_cap=3, eligible_units={"src/busy.py": 8}
    )
    assert policy.threshold_for("src/busy.py") == pytest.approx(80.0)

    selection = select_for_publication(findings, policy, [1.0] * 8)

    published = [f.accepted_receipt.receipt.candidate_id for f in selection.published]
    assert published == ["high", "low"]  # both, ordered by score
    assert selection.suppressed == ()
    assert REASON_BELOW_THRESHOLD not in {item.reason for item in selection.suppressed}
    # the bar is reported, not applied
    assert selection.unit_thresholds == {"src/busy.py": 80.0}
    assert selection.family_threshold == pytest.approx(80.0)
    assert selection.score_bar_applied is False


def test_the_hard_cap_and_the_same_defect_rule_are_the_only_remaining_suppressions(
    receipt: CertificationReceipt,
) -> None:
    """D-199 removes one gate and no others. Four distinct defects at scores the
    old bar would have refused: three publish in score order and the fourth is
    `beyond the hard author-visible cap` -- the reason the census found had never
    fired once in 574 recorded rows."""
    findings = [
        ScoredFinding(_finding(receipt, "a", "src/one.py", 10), 40.0),
        ScoredFinding(_finding(receipt, "b", "src/one.py", 20), 60.0),
        ScoredFinding(_finding(receipt, "c", "src/two.py", 30), 52.78),
        ScoredFinding(_finding(receipt, "d", "src/two.py", 40), 40.0),
    ]
    policy = FamilyPolicy(
        alpha=0.1, eligible_count=20, hard_cap=3,
        eligible_units={"src/one.py": 10, "src/two.py": 10},
    )
    selection = select_for_publication(findings, policy, [1.0] * 20)
    assert [f.accepted_receipt.receipt.candidate_id for f in selection.published] == ["b", "c", "a"]
    assert [
        (item.finding.accepted_receipt.receipt.candidate_id, item.reason)
        for item in selection.suppressed
    ] == [("d", REASON_BEYOND_CAP)]


def test_a_row_recorded_under_an_older_version_replays_under_that_version_s_bar(
    receipt: CertificationReceipt,
) -> None:
    """`schema_version` on the policy selects the rule, so a historical
    `publication_policy` row replays under the rule it was written by and
    reproduces its own record. Without this the new rule would rewrite history
    rather than change the product."""
    findings = [ScoredFinding(_finding(receipt, "low", "src/busy.py", 10), 40.0)]
    for version in ("attest.publication-policy.v1", "attest.publication-policy.v3"):
        assert score_bar_applies(version) is True
        old = select_for_publication(
            findings,
            FamilyPolicy(
                alpha=0.1, eligible_count=8, hard_cap=3,
                eligible_units={"src/busy.py": 8}, schema_version=version,
            ),
            [1.0] * 8,
        )
        assert old.published == ()
        assert [item.reason for item in old.suppressed] == [REASON_BELOW_THRESHOLD]
        assert old.score_bar_applied is True
    assert score_bar_applies(PUBLICATION_POLICY_SCHEMA_VERSION) is False
    assert PUBLICATION_POLICY_SCHEMA_VERSION == "attest.publication-policy.v4"
