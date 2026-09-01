"""Aggregate preregistered benchmark metrics without repeat inflation."""

from __future__ import annotations

import pytest

from attest.benchmark.metrics import aggregate, wilson_interval
from attest.benchmark.schema import (
    BenchmarkCase,
    ChangedLocation,
    PatchDescriptor,
    Placement,
    Prediction,
    RunRecord,
    TestDescriptor,
    TruthDefect,
)

_PATCH = PatchDescriptor(
    relative_path="patches/app.patch",
    sha256="af4749a1580b936481c1c087bc72d5031e256c38e266d0ee8d4f2707d3aa0e58",
    normalization="bytes",
)
_TEST = TestDescriptor(
    relative_path="tests/test_app.py",
    sha256="52ece453f7dd506d2a37a0f2e36732132f489cd662a1b92fad16545a56a3c3bd",
    normalization="normalized_text",
)


def _case(case_id: str, pair_id: str, role: str) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        pair_id=pair_id,
        source_id="source-000000000001",
        role=role,
        provenance_kind="historical_fix",
        source_license="Apache-2.0",
        buggy_commit="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        fixed_commit="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        patch=_PATCH,
        tests=_TEST,
        changed_locations=(ChangedLocation("src/app.py", 10, 12),),
        split="test",
    )


def _pair(index: int) -> tuple[BenchmarkCase, BenchmarkCase]:
    pair_id = f"pair-{index:012x}"
    return (
        _case(f"case-{(index * 2):012x}", pair_id, "historical_bug_replay"),
        _case(f"case-{(index * 2 + 1):012x}", pair_id, "developer_fix_control"),
    )


def _prediction(
    finding_id: str,
    case_id: str,
    line: int,
    *,
    placement: Placement = Placement.INLINE,
    action: str = "drawer",
    repro_status: str = "buggy_fail_fixed_pass",
) -> Prediction:
    return Prediction(
        finding_id=finding_id,
        case_id=case_id,
        file="src/app.py",
        line=line,
        placement=placement,
        action=action,
        repro_status=repro_status,
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


def test_aggregate_scores_paired_roles_and_finding_outcomes_and_delivery() -> None:
    """Inferring positives from truth allows malformed controls to alter PR metrics."""
    replay_1, control_1 = _pair(1)
    replay_2, control_2 = _pair(2)
    cases = (replay_1, control_1, replay_2, control_2)
    truth = (
        TruthDefect("truth_001", replay_1.case_id, "src/app.py", 10, 10),
        TruthDefect("truth_002", replay_2.case_id, "src/app.py", 10, 10),
    )
    runs = (
        _run("run_001", replay_1.case_id, (_prediction("finding_001", replay_1.case_id, 10),), 3.0),
        _run(
            "run_002",
            control_1.case_id,
            (_prediction("finding_002", control_1.case_id, 10, placement=Placement.OVERFLOW),),
            2.0,
        ),
        _run("run_003", replay_2.case_id, (_prediction("finding_003", replay_2.case_id, 30),), 5.0),
        _run("run_004", control_2.case_id, (), None),
    )

    report = aggregate(cases, truth, runs)

    assert (
        report.true_positives,
        report.false_positives,
        report.false_negatives,
        report.true_negatives,
    ) == (1, 1, 1, 1)
    assert (report.finding_true_positives, report.finding_false_positives) == (1, 2)
    assert report.clean_false_positive_rate == 0.5
    assert report.specificity == 0.5
    assert report.all_positive_detection == 0.5
    assert report.finding_precision == pytest.approx(1 / 3)
    assert report.conditional_recall == 0.5
    assert report.abstention_rate is None
    assert report.silent_run_rate == 0.25
    assert report.delivery_rate == 0.75
    assert report.deadline_censored == 1
    assert (report.delivery_p50_s, report.delivery_p95_s) == (3.0, 5.0)


def test_aggregate_excludes_a_case_whose_oracle_could_not_decide() -> None:
    """An inconclusive oracle leaves no usable ground truth for that case.

    Counting it costs the product twice for one undecided oracle: the surfaced
    finding becomes a finding false positive and the case becomes a false
    negative, so the same missing evidence is charged in both directions.
    """
    replay_1, control_1 = _pair(1)
    replay_2, control_2 = _pair(2)
    cases = (replay_1, control_1, replay_2, control_2)
    truth = (
        TruthDefect("truth_001", replay_1.case_id, "src/app.py", 10, 10),
        TruthDefect("truth_002", replay_2.case_id, "src/app.py", 10, 10),
    )
    runs = (
        _run("run_001", replay_1.case_id, (_prediction("finding_001", replay_1.case_id, 10),), 3.0),
        _run("run_002", control_1.case_id, (), 2.0),
        _run(
            "run_003",
            replay_2.case_id,
            (
                _prediction(
                    "finding_003", replay_2.case_id, 10, repro_status="deferred"
                ),
            ),
            4.0,
        ),
        _run("run_004", control_2.case_id, (), 5.0),
    )

    report = aggregate(cases, truth, runs)

    assert [
        (exclusion.case_id, exclusion.reason) for exclusion in report.excluded_cases
    ] == [(replay_2.case_id, "oracle_inconclusive")]
    assert (
        report.true_positives,
        report.false_positives,
        report.false_negatives,
        report.true_negatives,
    ) == (1, 0, 0, 2)
    assert (report.finding_true_positives, report.finding_false_positives) == (1, 0)
    assert report.decided_cases == 3
    assert report.all_positive_detection == 1.0
    assert report.all_positive_detection_interval == wilson_interval(1, 1)
    assert report.delivery_rate == 1.0


def test_aggregate_requires_truth_for_replay_and_rejects_truth_for_control() -> None:
    """Role/truth disagreement would make positive and clean denominators ambiguous."""
    replay, control = _pair(1)
    runs = (
        _run("run_001", replay.case_id, (), 1.0),
        _run("run_002", control.case_id, (), 1.0),
    )

    with pytest.raises(ValueError, match="positive"):
        aggregate((replay, control), (), runs)
    with pytest.raises(ValueError, match="control"):
        aggregate(
            (replay, control),
            (
                TruthDefect("truth_001", replay.case_id, "src/app.py", 10, 10),
                TruthDefect("truth_002", control.case_id, "src/app.py", 10, 10),
            ),
            runs,
        )


def test_aggregate_counts_overflow_duplicate_as_an_additional_finding_false_positive() -> None:
    """Allowing duplicate overflow surfaces to match one truth inflates precision."""
    replay, control = _pair(1)
    report = aggregate(
        (replay, control),
        (TruthDefect("truth_001", replay.case_id, "src/app.py", 10, 10),),
        (
            _run(
                "run_001",
                replay.case_id,
                (
                    _prediction("finding_001", replay.case_id, 10),
                    _prediction("finding_002", replay.case_id, 10, placement=Placement.OVERFLOW),
                ),
                4.0,
            ),
            _run("run_002", control.case_id, (), 4.0),
        ),
    )

    assert (report.finding_true_positives, report.finding_false_positives) == (1, 1)
    assert report.duplicate_surfaces == 1


def test_aggregate_requires_exactly_one_repeat_zero_record_for_each_case() -> None:
    """Missing or duplicate repeat zero runs must not silently shrink a denominator."""
    replay, control = _pair(1)
    truth = (TruthDefect("truth_001", replay.case_id, "src/app.py", 10, 10),)

    with pytest.raises(ValueError, match="missing repeat 0"):
        aggregate((replay, control), truth, (_run("run_001", replay.case_id, (), 1.0),))
    with pytest.raises(ValueError, match="duplicate preregistered"):
        aggregate(
            (replay, control),
            truth,
            (
                _run("run_001", replay.case_id, (), 1.0),
                _run("run_002", replay.case_id, (), 1.0),
                _run("run_003", control.case_id, (), 1.0),
            ),
        )


def test_aggregate_censors_late_repeat_zero_delivery_and_uses_nearest_rank() -> None:
    """A late repeat-zero delivery must be censored rather than counted in latency percentiles."""
    replay_1, control_1 = _pair(1)
    replay_2, control_2 = _pair(2)
    replay_3, control_3 = _pair(3)
    cases = (replay_1, control_1, replay_2, control_2, replay_3, control_3)
    truth = (
        TruthDefect("truth_001", replay_1.case_id, "src/app.py", 10, 10),
        TruthDefect("truth_002", replay_2.case_id, "src/app.py", 10, 10),
        TruthDefect("truth_003", replay_3.case_id, "src/app.py", 10, 10),
    )
    runs = (
        _run("run_001", replay_1.case_id, (), 1.0),
        _run("run_002", control_1.case_id, (), 2.0),
        _run("run_003", replay_2.case_id, (), 3.0),
        _run("run_004", control_2.case_id, (), 4.0),
        _run("run_005", replay_3.case_id, (), 5.0),
        _run("run_006", control_3.case_id, (), 11.0),
        _run("run_007", replay_1.case_id, (), 100.0, repeat=1),
    )

    report = aggregate(cases, truth, runs)

    assert report.delivery_rate == pytest.approx(5 / 6)
    assert report.deadline_censored == 1
    assert (report.delivery_p50_s, report.delivery_p95_s) == (3.0, 5.0)
