"""D-168: what a review's budget is spent on — the order, the cap, and the share.

Owner decision 1 of 2026-09-07, after the budget re-run raised `budget_usd` four
times over on seventeen commits and moved **not one verdict**: 331 candidates
where $0.25 found 105, and 167 of them drawered `no-reproduction-bought` because
the ranking never reached them. Three rules, three REDs:

1. the candidate order is **order-independent and deterministic**;
2. the **N+1st candidate of a change unit does not enter the container**;
3. the **proposal stage cannot spend more than 30%** of one review's budget.
"""

from __future__ import annotations

import random
from pathlib import Path

import pytest

from attest.review.budget import PROPOSAL_SHARE, Budget, BudgetExceeded
from attest.review.candidates import StoredCandidate
from attest.review.config import ReviewConfig, validate_review_config
from attest.review.ranking import (
    RANKED_BELOW_CAP,
    CredibilityIndex,
    cluster_size,
    rank,
    within_cap,
)
from attest.review.report import drawer_reason_class
from attest.review.schema import ClusterMember, Finding

TREE = {
    "src/pkg/core.py": (
        "def widen(value):\n"
        "    return value * 2\n"
        "\n"
        "\n"
        "def narrow(value):\n"
        "    return value // 2\n"
        "\n"
        "\n"
        "def orphan(value):\n"
        "    return value\n"
    ),
    "src/pkg/app.py": "from pkg.core import widen\n\n\ndef run(value):\n    return widen(value)\n",
    "tests/test_core.py": "def test_widen():\n    assert True\n",
}


def _candidate(claim: str, file: str, line: int, members: int) -> StoredCandidate:
    provenance = [
        ClusterMember(sample_id=index, file=file, line=line, claim=claim)
        for index in range(members)
    ]
    finding = Finding(
        claim=claim,
        file=file,
        line=line,
        failure_scenario="scenario",
        falsification_plan="plan",
        votes=members,
        sample_ids=list(range(members)),
        cluster_id=f"cluster-{claim}",
        members=provenance,
    )
    return StoredCandidate(
        task_id="t", finding=finding, wealth=2.0, action="drawer", alpha=0.1
    )


def _anchors(items: list[StoredCandidate]) -> list[tuple[str, int]]:
    return [(item.finding.file, item.finding.line) for item in items]


@pytest.fixture(scope="module")
def index() -> CredibilityIndex:
    return CredibilityIndex(TREE)


# --- 1. the order is order-independent and deterministic ----------------------


def test_the_order_does_not_depend_on_the_order_the_candidates_arrive_in(
    index: CredibilityIndex,
) -> None:
    candidates = [
        _candidate("a", "src/pkg/core.py", 2, members=1),
        _candidate("b", "src/pkg/core.py", 6, members=3),
        _candidate("c", "src/pkg/core.py", 10, members=1),
        _candidate("d", "src/pkg/app.py", 5, members=2),
        _candidate("e", "tests/test_core.py", 2, members=1),
        _candidate("f", "README.md", 1, members=1),
    ]
    expected = [item.finding.finding_id for item in rank(candidates, index)]
    assert len(set(expected)) == len(expected), "the key must be a total order"
    rng = random.Random(20260907)
    for _ in range(64):
        shuffled = candidates[:]
        rng.shuffle(shuffled)
        assert [item.finding.finding_id for item in rank(shuffled, index)] == expected
    # and it is the same answer every time it is asked
    assert [item.finding.finding_id for item in rank(candidates, index)] == expected


def test_cluster_size_ranks_first_and_credibility_breaks_the_tie(
    index: CredibilityIndex,
) -> None:
    big = _candidate("big cluster", "README.md", 1, members=4)
    called = _candidate("called", "src/pkg/core.py", 2, members=1)  # widen: called by app
    uncalled = _candidate("uncalled", "src/pkg/core.py", 10, members=1)  # orphan: never called
    module_level = _candidate("module level", "src/pkg/app.py", 1, members=1)  # an import line
    in_a_test = _candidate("in a test", "tests/test_core.py", 2, members=1)

    ordered = rank([in_a_test, module_level, uncalled, called, big], index)
    assert _anchors(ordered) == [
        ("README.md", 1),  # cluster size 4 outranks everything, whatever its anchor
        ("src/pkg/core.py", 2),  # score 2: in a source definition, and that one is called
        ("src/pkg/core.py", 10),  # score 1: in a source definition, never called
        ("src/pkg/app.py", 1),  # score 0: a source file, but the anchor is module level
        ("tests/test_core.py", 2),  # score 0: a test file is not a source unit
    ]
    assert cluster_size(big) == 4
    assert index.of("src/pkg/core.py", 2).symbol == "widen"
    assert index.of("src/pkg/core.py", 2).score == 2
    assert index.of("src/pkg/core.py", 10).score == 1
    assert index.of("src/pkg/app.py", 1).score == 0
    assert index.of("tests/test_core.py", 2).score == 0
    assert index.of("README.md", 1).score == 0


def test_an_unreadable_tree_ranks_by_cluster_size_and_id_without_failing() -> None:
    """Credibility abstains rather than guessing; the order stays total."""
    empty = CredibilityIndex({})
    candidates = [
        _candidate("b", "src/pkg/core.py", 2, members=1),
        _candidate("a", "src/pkg/core.py", 6, members=1),
        _candidate("c", "src/pkg/core.py", 9, members=2),
    ]
    ordered = rank(candidates, empty)
    assert ordered[0].finding.claim == "c"  # cluster size still ranks
    assert [item.finding.finding_id for item in ordered[1:]] == sorted(
        item.finding.finding_id for item in ordered[1:]
    )
    missing = CredibilityIndex.for_tree(Path("/nonexistent-tree-for-this-red"))
    assert missing.of("x.py", 1).score == 0


# --- 2. the N+1st candidate of a unit does not enter the container ------------


def test_the_candidate_past_the_cap_is_refused_before_any_container(
    index: CredibilityIndex,
) -> None:
    unit = "src/pkg/core.py"
    crowd = [_candidate(f"claim {n}", unit, 2, members=5 - n) for n in range(5)]
    elsewhere = _candidate("elsewhere", "src/pkg/app.py", 5, members=1)
    ordered = rank([elsewhere, *crowd], index)
    purchasable, below = within_cap(ordered, cap=3)

    # three of this unit's five, plus the one candidate of the other unit
    assert len(purchasable) == 4
    assert len(below) == 2
    assert elsewhere.finding.finding_id in purchasable
    bought = [item for item in ordered if item.finding.finding_id in purchasable]
    assert sum(1 for item in bought if item.finding.file == unit) == 3
    # the three bought are the three largest clusters, in that order
    assert [item.finding.claim for item in bought if item.finding.file == unit] == [
        "claim 0",
        "claim 1",
        "claim 2",
    ]

    fourth = next(item for item in ordered if item.finding.finding_id in below)
    reason = below[fourth.finding.finding_id]
    assert reason.startswith(RANKED_BELOW_CAP)
    assert unit in reason and "at most 3" in reason
    # `--explain` and the ledger histogram name it apart from a candidate the
    # ranking never reached at all
    assert drawer_reason_class(reason) == "ranked-below-cap"
    assert drawer_reason_class("") == "no-reproduction-bought"


def test_the_cap_counts_each_change_unit_on_its_own(index: CredibilityIndex) -> None:
    """A review spends across the files it touched, not inside the first one."""
    ordered = rank(
        [_candidate(f"a{n}", "src/pkg/core.py", 2, members=1) for n in range(4)]
        + [_candidate(f"b{n}", "src/pkg/app.py", 5, members=1) for n in range(4)],
        index,
    )
    purchasable, below = within_cap(ordered, cap=3)
    per_unit = {"src/pkg/core.py": 0, "src/pkg/app.py": 0}
    for item in ordered:
        if item.finding.finding_id in purchasable:
            per_unit[item.finding.file] += 1
    assert per_unit == {"src/pkg/core.py": 3, "src/pkg/app.py": 3}
    assert len(below) == 2


def test_the_cap_is_policy_configurable_and_never_zero(index: CredibilityIndex) -> None:
    ordered = rank([_candidate(f"c{n}", "src/pkg/core.py", 2, members=1) for n in range(4)], index)
    assert len(within_cap(ordered, cap=1)[0]) == 1
    assert len(within_cap(ordered, cap=10)[0]) == 4
    assert ReviewConfig().verification_cap_per_unit == 3
    for bad in (0, -1, 2.5, True):
        config = ReviewConfig()
        config.verification_cap_per_unit = bad  # type: ignore[assignment]
        with pytest.raises(ValueError):
            validate_review_config(config)


# --- 3. the proposal stage cannot spend more than 30% of the budget ----------


def test_discovery_cannot_reserve_more_than_thirty_percent_of_one_review() -> None:
    assert PROPOSAL_SHARE == 0.3
    budget = Budget(limit_usd=1.00, model="claude-sonnet-5")
    with budget.stage("discovery", PROPOSAL_SHARE):
        # a call that fits inside the share is bought
        budget.reserve("unit-0", input_chars=30_000, max_output_tokens=1_000)
        assert budget.reserved_usd <= 1.00 * PROPOSAL_SHARE
        with pytest.raises(BudgetExceeded) as raised:
            # one that would take the stage past 30% is refused, not truncated
            budget.reserve("unit-1", input_chars=400_000, max_output_tokens=4_000)
    assert "discovery share" in raised.value.reason
    assert f"${1.00 * PROPOSAL_SHARE:.4f}" in raised.value.reason
    assert budget.reserved_usd <= 1.00 * PROPOSAL_SHARE
    # and outside the stage the rest of the budget is still there for reproductions
    budget.reserve("repro-0", input_chars=400_000, max_output_tokens=4_000)
    assert budget.reserved_usd > 1.00 * PROPOSAL_SHARE
