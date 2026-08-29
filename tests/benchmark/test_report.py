"""Reports are deterministic and state what they cannot claim."""

from __future__ import annotations

import json
from pathlib import Path

from attest.benchmark.report import (
    LIVE_MODE,
    REPLAY_MODE,
    ReportExclusion,
    build_report,
    render_markdown,
    write_report,
)
from attest.benchmark.schema import (
    BenchmarkCase,
    BenchmarkManifest,
    ChangedLocation,
    PatchDescriptor,
    Placement,
    Prediction,
    RunRecord,
    TestDescriptor,
    TruthDefect,
)

REPLAY_CASE = "case-aaaaaaaaaaaa"
CONTROL_CASE = "case-bbbbbbbbbbbb"
UNRUN_CASE = "case-cccccccccccc"
UNRUN_CONTROL = "case-dddddddddddd"
MANIFEST_SHA = "e" * 64


def _case(case_id: str, pair_id: str, role: str) -> BenchmarkCase:
    return BenchmarkCase(
        case_id=case_id,
        pair_id=pair_id,
        source_id="source-111111111111",
        role=role,
        provenance_kind="historical_fix",
        source_license="MIT",
        buggy_commit="a" * 40,
        fixed_commit="b" * 40,
        patch=PatchDescriptor("artifacts/fix.patch", "c" * 64, "unified_diff"),
        tests=TestDescriptor("artifacts/test.argv", "d" * 64, "normalized_text"),
        changed_locations=(ChangedLocation("app.py", 1, 2),),
        split="test",
    )


def _manifest() -> BenchmarkManifest:
    return BenchmarkManifest(
        schema_version="1",
        protocol_version="1",
        corpus_commit="f" * 40,
        cases=(
            _case(REPLAY_CASE, "pair-111111111111", "historical_bug_replay"),
            _case(CONTROL_CASE, "pair-111111111111", "developer_fix_control"),
            _case(UNRUN_CASE, "pair-222222222222", "historical_bug_replay"),
            _case(UNRUN_CONTROL, "pair-222222222222", "developer_fix_control"),
        ),
        truth_defects=(
            TruthDefect("defect-1", REPLAY_CASE, "app.py", 1, 2),
            TruthDefect("defect-2", UNRUN_CASE, "app.py", 1, 2),
        ),
    )


def _prediction(
    finding_id: str,
    line: int,
    *,
    repro_status: str,
    evidence_class: str,
    case_id: str = REPLAY_CASE,
) -> Prediction:
    return Prediction(
        finding_id=finding_id,
        case_id=case_id,
        file="app.py",
        line=line,
        placement=Placement.INLINE,
        action="surface",
        repro_status=repro_status,
        evidence_class=evidence_class,
    )


def _runs() -> tuple[RunRecord, ...]:
    return (
        RunRecord(
            run_id="run-1",
            case_id=REPLAY_CASE,
            repeat=0,
            predictions=(
                _prediction(
                    "f-hit",
                    2,
                    repro_status="buggy_fail_fixed_pass",
                    evidence_class="regression_reproduced",
                ),
                _prediction(
                    "f-new",
                    40,
                    repro_status="new_code_candidate",
                    evidence_class="new_code_candidate",
                ),
            ),
            delivery_at_s=12.0,
            deadline_s=60.0,
        ),
        RunRecord(
            run_id="run-2",
            case_id=CONTROL_CASE,
            repeat=0,
            predictions=(),
            delivery_at_s=9.0,
            deadline_s=60.0,
        ),
        RunRecord(
            run_id="run-1-repeat",
            case_id=REPLAY_CASE,
            repeat=1,
            predictions=(),
            delivery_at_s=11.0,
            deadline_s=60.0,
        ),
    )


def _report(mode: str = REPLAY_MODE):
    return build_report(
        _manifest(),
        _runs(),
        mode=mode,
        manifest_sha256=MANIFEST_SHA,
        exclusions=(
            ReportExclusion(UNRUN_CASE, "prepared_environment_required"),
            ReportExclusion(UNRUN_CONTROL, "prepared_environment_required"),
        ),
        differential_repeats=3,
    )


def test_report_scores_only_evaluated_cases_and_never_hides_exclusions() -> None:
    """An unevaluated case is an exclusion, never a silent negative."""
    report = _report()

    assert report.evaluated_cases == 2
    assert [exclusion.case_id for exclusion in report.excluded_cases] == [
        UNRUN_CASE,
        UNRUN_CONTROL,
    ]
    assert report.metrics is not None
    assert report.metrics.true_positives == 1
    assert report.metrics.false_negatives == 0
    assert report.metrics.true_negatives == 1
    assert report.metrics.finding_true_positives == 1
    assert report.metrics.finding_false_positives == 1


def test_headline_rates_carry_wilson_intervals() -> None:
    report = _report()

    assert report.metrics is not None
    assert report.metrics.all_positive_detection_interval is not None
    assert report.metrics.finding_precision_interval is not None
    assert report.metrics.clean_false_positive_rate_interval is not None
    payload = report.to_json_dict()
    assert payload["metrics"]["finding_precision_interval"] == [
        round(value, 6) for value in report.metrics.finding_precision_interval
    ]


def test_evidence_classes_are_broken_out_and_the_unpriced_class_is_named() -> None:
    """A new-code candidate is unpriced signal, not a failure; the report says so."""
    report = _report()

    assert report.evidence_class_counts == {
        "new_code_candidate": 1,
        "regression_reproduced": 1,
    }
    limitations = " ".join(report.limitations)
    assert "new_code_candidate" in limitations
    assert "unpriced" in limitations
    markdown = render_markdown(report)
    assert "new_code_candidate" in markdown
    assert "| regression_reproduced | 1 |" in markdown


def test_replay_and_live_modes_are_described_differently() -> None:
    replay = " ".join(_report(REPLAY_MODE).limitations)
    live = " ".join(_report(LIVE_MODE).limitations)

    assert "replay regression" in replay
    assert "live" not in replay.split("replay regression")[0]
    assert "live observation" in live
    assert "replay regression" not in live


def test_report_states_provenance_repeats_and_exclusions() -> None:
    report = _report()
    markdown = render_markdown(report)

    assert MANIFEST_SHA in markdown
    assert "f" * 40 in markdown
    assert "prepared_environment_required" in markdown
    assert "repeat zero" in " ".join(report.limitations)
    assert report.repeats == 2
    assert report.differential_repeats == 3
    assert "differential repeats per side: 3" in markdown


def test_report_without_runs_reports_no_metrics_rather_than_zeros() -> None:
    report = build_report(
        _manifest(),
        (),
        mode=REPLAY_MODE,
        manifest_sha256=MANIFEST_SHA,
        exclusions=(
            ReportExclusion(case.case_id, "prepared_environment_required")
            for case in _manifest().cases
        ),
    )

    assert report.metrics is None
    assert report.evaluated_cases == 0
    assert report.to_json_dict()["metrics"] is None
    assert "no case was evaluated" in render_markdown(report)


def test_report_json_and_markdown_are_deterministic(tmp_path: Path) -> None:
    first, second = _report(), _report()

    assert first.digest == second.digest
    assert json.dumps(first.to_json_dict(), sort_keys=True) == json.dumps(
        second.to_json_dict(), sort_keys=True
    )
    assert render_markdown(first) == render_markdown(second)

    json_path, markdown_path = write_report(first, tmp_path / "out")
    first_bytes = (json_path.read_bytes(), markdown_path.read_bytes())
    json_path, markdown_path = write_report(second, tmp_path / "out")

    assert (json_path.read_bytes(), markdown_path.read_bytes()) == first_bytes
    assert json.loads(json_path.read_text(encoding="utf-8"))["digest"] == first.digest
