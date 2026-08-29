"""Location-and-evidence matching for surfaced benchmark findings."""

from __future__ import annotations

from attest.benchmark.matcher import MatchResult, match_findings
from attest.benchmark.schema import Prediction, TruthDefect


def _truth(defect_id: str, start_line: int, end_line: int) -> TruthDefect:
    return TruthDefect(
        defect_id=defect_id,
        case_id="case_001",
        file="src/pkg/worker.py",
        start_line=start_line,
        end_line=end_line,
    )


def _prediction(
    finding_id: str,
    line: int,
    *,
    placement: str = "surface",
    action: str = "DEFER",
    repro_status: str = "buggy_fail_fixed_pass",
    file: str = "src/pkg/worker.py",
) -> Prediction:
    return Prediction(
        finding_id=finding_id,
        case_id="case_001",
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
            _prediction("finding_001", 10, action="SURFACE"),
            _prediction("finding_002", 10, action="DEFER"),
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
            _prediction("finding_001", 10, placement="drawer"),
            _prediction("finding_002", 10, placement="discard"),
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
