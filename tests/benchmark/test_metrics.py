"""Aggregate preregistered benchmark metrics without repeat inflation."""

from __future__ import annotations

import pytest

from attest.benchmark.metrics import aggregate, wilson_interval
from attest.benchmark.schema import (
    BenchmarkCase,
    ChangedLocation,
    Prediction,
    RunRecord,
    TruthDefect,
)


def _case(case_id: str) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        pair_id="pair_001",
        source_id="source_001",
        role="buggy",
        provenance_kind="upstream",
        source_license="Apache-2.0",
        buggy_commit="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        fixed_commit="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        patch_hash="529431251f17f34724808f96b9dbe574b21e4f7024d7ac194b52bdc4a8b04bbd",
        test_hash="0196e5c8601c41054c1cf094880415c863acd293bbe908a56a96a1d9fc32593f",
        changed_locations=(ChangedLocation("src/app.py", 10, 12),),
        split="test",
    )


def _prediction(
    finding_id: str,
    case_id: str,
    line: int,
    *,
    action: str = "SURFACE",
) -> Prediction:
    return Prediction(
        finding_id=finding_id,
        case_id=case_id,
        file="src/app.py",
        line=line,
        placement="surface",
        action=action,
        repro_status="buggy_fail_fixed_pass",
    )


def _run(
    run_id: str,
    case_id: str,
    predictions: tuple[Prediction, ...],
    delivery_at_s: float | None,
    *,
    repeat: int = 0,
) -> RunRecord:
    return RunRecord(
        run_id=run_id,
        case_id=case_id,
        repeat=repeat,
        predictions=predictions,
        delivery_at_s=delivery_at_s,
        deadline_s=10.0,
    )


@pytest.mark.parametrize(
    ("successes", "total", "expected"),
    [
        (40, 40, (0.912378, 1.0)),
        (38, 40, (0.834961, 0.986179)),
        (20, 40, (0.351995, 0.648005)),
        (0, 40, (0.0, 0.087622)),
    ],
)
def test_wilson_interval_matches_preregistered_95_percent_values(
    successes: int, total: int, expected: tuple[float, float]
) -> None:
    """Changing the interval calculation would alter the preregistered uncertainty bounds."""
    interval = wilson_interval(successes, total)

    assert interval is not None
    assert round(interval[0], 6) == expected[0]
    assert round(interval[1], 6) == expected[1]


def test_wilson_interval_returns_null_for_no_observations() -> None:
    """Inventing an interval for zero evaluated cases would imply nonexistent evidence."""
    assert wilson_interval(0, 0) is None


def test_aggregate_scores_pr_and_finding_outcomes_and_delivery() -> None:
    """Collapsing wrong-location or deferred clean surfaces would hide benchmark errors."""
    cases = (_case("case_001"), _case("case_002"), _case("case_003"), _case("case_004"))
    truth = (
        TruthDefect("truth_001", "case_001", "src/app.py", 10, 10),
        TruthDefect("truth_002", "case_002", "src/app.py", 10, 10),
    )
    runs = (
        _run("run_001", "case_001", (_prediction("finding_001", "case_001", 10),), 3.0),
        _run("run_002", "case_002", (_prediction("finding_002", "case_002", 30),), 5.0),
        _run(
            "run_003",
            "case_003",
            (_prediction("finding_003", "case_003", 10, action="DEFER"),),
            2.0,
        ),
        _run("run_004", "case_004", (), None),
    )

    report = aggregate(cases, truth, runs)

    assert (
        report.true_positives,
        report.false_positives,
        report.false_negatives,
        report.true_negatives,
    ) == (
        1,
        1,
        1,
        1,
    )
    assert (report.finding_true_positives, report.finding_false_positives) == (1, 2)
    assert report.clean_false_positive_rate == 0.5
    assert report.specificity == 0.5
    assert report.all_positive_detection == 0.5
    assert report.finding_precision == pytest.approx(1 / 3)
    assert report.conditional_recall == 0.5
    assert report.abstention_rate == 0.25
    assert report.delivery_rate == 0.75
    assert report.deadline_censored == 1
    assert (report.delivery_p50_s, report.delivery_p95_s) == (3.0, 5.0)


def test_aggregate_counts_duplicate_surface_as_an_additional_finding_false_positive() -> None:
    """Allowing both duplicate surfaces to match one truth inflates finding precision."""
    report = aggregate(
        (_case("case_001"),),
        (TruthDefect("truth_001", "case_001", "src/app.py", 10, 10),),
        (
            _run(
                "run_001",
                "case_001",
                (
                    _prediction("finding_001", "case_001", 10),
                    _prediction("finding_002", "case_001", 10),
                ),
                4.0,
            ),
        ),
    )

    assert (report.finding_true_positives, report.finding_false_positives) == (1, 1)
    assert report.duplicate_surfaces == 1


def test_aggregate_censors_late_delivery_and_excludes_repeats_from_headlines() -> None:
    """Counting late or repeated runs in headline denominators fabricates certainty."""
    report = aggregate(
        (_case("case_001"),),
        (TruthDefect("truth_001", "case_001", "src/app.py", 10, 10),),
        (
            _run("run_001", "case_001", (_prediction("finding_001", "case_001", 10),), 8.0),
            _run(
                "run_002",
                "case_001",
                (_prediction("finding_002", "case_001", 30),),
                15.0,
                repeat=1,
            ),
        ),
    )

    assert (
        report.true_positives,
        report.false_negatives,
        report.finding_false_positives,
    ) == (1, 0, 0)
    assert report.all_positive_detection_interval is not None
    assert tuple(round(value, 6) for value in report.all_positive_detection_interval) == (
        0.206549,
        1.0,
    )
    assert report.delivery_rate == 1.0
    assert report.deadline_censored == 0
