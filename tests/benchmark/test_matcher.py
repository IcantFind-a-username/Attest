"""Location-and-evidence matching for surfaced benchmark findings."""

from __future__ import annotations

import pytest

from attest.benchmark.matcher import (
    DEFAULT_LINE_SLACK,
    MatchResult,
    hunk_labelling,
    line_slack_sweep,
    match_findings,
)
from attest.benchmark.schema import (
    BenchmarkCase,
    ChangedLocation,
    PatchDescriptor,
    Placement,
    Prediction,
    TestDescriptor,
    TruthDefect,
)


def _truth(defect_id: str, start_line: int, end_line: int) -> TruthDefect:
    return TruthDefect(
        defect_id=defect_id,
        case_id="case-000000000001",
        file="src/pkg/worker.py",
        start_line=start_line,
        end_line=end_line,
    )


def _prediction(
    finding_id: str,
    line: int,
    *,
    placement: Placement = Placement.INLINE,
    action: str = "DEFER",
    repro_status: str = "buggy_fail_fixed_pass",
    file: str = "src/pkg/worker.py",
) -> Prediction:
    return Prediction(
        finding_id=finding_id,
        case_id="case-000000000001",
        file=file,
        line=line,
        placement=placement,
        action=action,
        repro_status=repro_status,
    )


def test_matcher_normalizes_paths_and_honors_preregistered_line_slack() -> None:
    """Removing path normalization or slack would lose an otherwise valid detection."""
    results = match_findings(
        (_truth("truth_001", 20, 22),),
        (_prediction("finding_001", 24, file="src/pkg/./worker.py"),),
        line_slack=2,
    )

    assert results == (
        MatchResult(finding_id="finding_001", defect_id="truth_001", matched=True),
    )


def test_matcher_maximizes_one_to_one_cardinality_before_anchor_distance() -> None:
    """A greedy closest-first choice would leave the second truth defect unmatched."""
    results = match_findings(
        (_truth("truth_001", 10, 10), _truth("truth_002", 12, 12)),
        (_prediction("finding_001", 11), _prediction("finding_002", 10)),
        line_slack=1,
    )

    assert results == (
        MatchResult(finding_id="finding_001", defect_id="truth_002", matched=True),
        MatchResult(finding_id="finding_002", defect_id="truth_001", matched=True),
    )


def test_matcher_scores_duplicate_and_overflow_surfaces_independently_of_action() -> None:
    """Treating a second surface as a match or consulting action hides false positives."""
    results = match_findings(
        (_truth("truth_001", 10, 10),),
        (
            _prediction("finding_001", 10, action="drawer"),
            _prediction("finding_002", 10, placement=Placement.OVERFLOW, action="discard"),
        ),
    )

    assert results == (
        MatchResult(finding_id="finding_001", defect_id="truth_001", matched=True),
        MatchResult(finding_id="finding_002", defect_id=None, matched=False),
    )


def test_matcher_excludes_drawer_and_discard_and_requires_differential_repro() -> None:
    """Counting hidden or unreproduced candidates as matches inflates evaluation results."""
    results = match_findings(
        (_truth("truth_001", 10, 10),),
        (
            _prediction("finding_001", 10, placement=Placement.DRAWER),
            _prediction("finding_002", 10, placement=Placement.DISCARD),
            _prediction("finding_003", 10, repro_status="buggy_fail_fixed_fail"),
        ),
    )

    assert results == (
        MatchResult(finding_id="finding_003", defect_id=None, matched=False),
    )


def test_matcher_leaves_a_wrong_location_surface_unmatched() -> None:
    """Broadening location compatibility would turn a wrong anchor into a true positive."""
    results = match_findings(
        (_truth("truth_001", 10, 10),),
        (_prediction("finding_001", 30),),
    )

    assert results == (
        MatchResult(finding_id="finding_001", defect_id=None, matched=False),
    )


def test_matcher_uses_literal_ci_final_placements_and_scores_fourth_overflow() -> None:
    """Treating only inline comments as surfaced would hide overflow false positives."""
    candidate = {
        "task_id": "task-000000000001",
        "finding_id": "finding_004",
        "file": "src/pkg/worker.py",
        "line": 10,
        "claim": "A concrete finding.",
        "failure_scenario": "A concrete scenario.",
        "falsification_plan": "A concrete falsification plan.",
        "votes": 1,
        "sample_ids": [0],
        "wealth": 12.0,
        "action": "drawer",
        "alpha": 0.1,
    }
    ci_final = {
        "finding_id": "finding_004",
        "action": "drawer",
        "wealth_final": 12.0,
        "placement": "overflow",
    }
    fourth = Prediction.from_joined_ci_final(
        candidate,
        ci_final,
        case_id="case-000000000001",
        repro_status="buggy_fail_fixed_pass",
    )
    results = match_findings(
        (_truth("truth_001", 10, 10),),
        (
            _prediction("finding_001", 10),
            _prediction("finding_002", 10, placement=Placement.OVERFLOW),
            _prediction("finding_003", 30, placement=Placement.OVERFLOW),
            fourth,
        ),
    )

    assert fourth.placement is Placement.OVERFLOW
    assert fourth.action == "drawer"
    assert results == (
        MatchResult(finding_id="finding_001", defect_id="truth_001", matched=True),
        MatchResult(finding_id="finding_002", defect_id=None, matched=False),
        MatchResult(finding_id="finding_003", defect_id=None, matched=False),
        MatchResult(finding_id="finding_004", defect_id=None, matched=False),
    )


def test_prediction_join_requires_complete_ci_final_decision_and_known_placement() -> None:
    """Filling missing decision fields from candidate data would mis-score final placement."""
    candidate = {
        "task_id": "task-000000000001",
        "finding_id": "finding_004",
        "file": "src/pkg/worker.py",
        "line": 10,
        "claim": "A concrete finding.",
        "failure_scenario": "A concrete scenario.",
        "falsification_plan": "A concrete falsification plan.",
        "votes": 1,
        "sample_ids": [0],
        "wealth": 12.0,
        "action": "drawer",
        "alpha": 0.1,
    }
    with pytest.raises(ValueError, match="action"):
        Prediction.from_joined_ci_final(
            candidate,
            {"finding_id": "finding_004", "placement": "inline"},
            case_id="case-000000000001",
            repro_status="buggy_fail_fixed_pass",
        )
    with pytest.raises(ValueError, match="placement"):
        Prediction.from_joined_ci_final(
            candidate,
            {"finding_id": "finding_004", "action": "drawer", "placement": "surface"},
            case_id="case-000000000001",
            repro_status="buggy_fail_fixed_pass",
        )
    with pytest.raises(ValueError, match="opaque"):
        Prediction.from_joined_ci_final(
            candidate,
            {"finding_id": "finding_004", "action": "drawer", "placement": "inline"},
            case_id="case-replay000001",
            repro_status="buggy_fail_fixed_pass",
        )


def test_matcher_breaks_equal_distance_ties_by_defect_then_finding_id() -> None:
    """Input-order tie resolution would make benchmark assignments non-reproducible."""
    results = match_findings(
        (_truth("defect_a", 10, 10), _truth("defect_b", 10, 10)),
        (_prediction("finding_a", 10), _prediction("finding_b", 10)),
    )

    assert results == (
        MatchResult(finding_id="finding_a", defect_id="defect_a", matched=True),
        MatchResult(finding_id="finding_b", defect_id="defect_b", matched=True),
    )


def _case(*locations: ChangedLocation) -> BenchmarkCase:
    return BenchmarkCase(
        case_id="case-000000000001",
        pair_id="pair-000000000001",
        source_id="source-000000000001",
        role="historical_bug_replay",
        provenance_kind="historical_fix",
        source_license="MIT",
        buggy_commit="a" * 40,
        fixed_commit="b" * 40,
        patch=PatchDescriptor("artifacts/fix.patch", "c" * 64, "unified_diff"),
        tests=TestDescriptor("artifacts/test.argv", "d" * 64, "normalized_text"),
        changed_locations=locations,
        split="test",
    )


def test_default_tolerance_binds_an_anchor_inside_the_statement_it_names() -> None:
    """A defect occupies a region; an exact line was never the right criterion.

    D-062 pre-registered ``line_slack = 3`` as one Python statement's typical
    physical extent, together with the sweep that shows the count does not hinge
    on the exact value.
    """
    truths = (_truth("d1", 2948, 2948),)
    predictions = (_prediction("f1", 2949),)

    assert not match_findings(truths, predictions, line_slack=0)[0].matched
    assert match_findings(truths, predictions, line_slack=DEFAULT_LINE_SLACK)[0].matched
    assert line_slack_sweep(truths, predictions) == {
        "0": 0,
        "1": 1,
        "2": 1,
        "3": 1,
        "4": 1,
        "5": 1,
        "10": 1,
    }


def test_an_unlabelled_fix_hunk_is_named_and_never_matched() -> None:
    """A pure insertion in the fix has no head-side line for the corpus to label.

    The reverted head still carries that defect, so an unmatched finding in such
    a case is flagged. The flag states a limit of the labelling; it never turns
    a miss into a match.
    """
    truths = (_truth("d1", 626, 626),)
    predictions = (_prediction("f1", 610),)
    case = _case(
        ChangedLocation("src/pkg/worker.py", 610, 612, side="new"),
        ChangedLocation("src/pkg/worker.py", 626, 626, side="old"),
        ChangedLocation("src/pkg/worker.py", 629, 629, side="new"),
    )

    assert hunk_labelling(case).unlabelled_hunks == 1
    result = match_findings(
        truths, predictions, line_slack=DEFAULT_LINE_SLACK, cases=(case,)
    )[0]
    assert result.matched is False
    assert result.defect_id is None
    assert result.unlabelled_hunks_present is True

    fully_labelled = _case(
        ChangedLocation("src/pkg/worker.py", 626, 626, side="old"),
        ChangedLocation("src/pkg/worker.py", 629, 629, side="new"),
    )
    assert hunk_labelling(fully_labelled).unlabelled_hunks == 0
    assert (
        match_findings(
            truths, predictions, line_slack=DEFAULT_LINE_SLACK, cases=(fully_labelled,)
        )[0].unlabelled_hunks_present
        is False
    )


def test_a_matched_finding_is_never_flagged_unlabelled() -> None:
    """The flag describes a miss the corpus cannot adjudicate, nothing else."""
    case = _case(
        ChangedLocation("src/pkg/worker.py", 610, 612, side="new"),
        ChangedLocation("src/pkg/worker.py", 626, 626, side="old"),
    )
    result = match_findings(
        (_truth("d1", 626, 626),),
        (_prediction("f1", 627),),
        line_slack=DEFAULT_LINE_SLACK,
        cases=(case,),
    )[0]
    assert result.matched is True
    assert result.unlabelled_hunks_present is False
