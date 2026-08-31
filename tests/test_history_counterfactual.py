from __future__ import annotations

from dataclasses import replace

from scripts.history_counterfactual import _counterfactual_row

from attest.benchmark.schema import BenchmarkCase, PatchDescriptor, TestDescriptor
from attest.review.gate import GateResult
from attest.review.schema import Finding


def test_counterfactual_only_reports_triggered_threshold_crossing() -> None:
    finding = Finding(
        claim="The parser drops a value.",
        file="parser.py",
        line=7,
        failure_scenario="Parsing x returns an empty value.",
        falsification_plan="Parse x and inspect the result.",
    )
    case = BenchmarkCase(
        case_id="case-0123456789ab",
        pair_id="pair-0123456789ab",
        source_id="source-0123456789ab",
        role="historical_bug_replay",
        provenance_kind="historical_fix",
        source_license="MIT",
        buggy_commit="1" * 40,
        fixed_commit="2" * 40,
        patch=PatchDescriptor("p", "3" * 64, "unified_diff"),
        tests=TestDescriptor("t", "4" * 64, "normalized_text"),
        changed_locations=(),
        split="test",
    )
    result = GateResult(finding=finding, wealth=6.0)
    history = {"triggered": True, "commit_sha": "5" * 40, "commit_message": "hotfix"}

    assert _counterfactual_row(case, result, history, 1.5) is None
    crossed = _counterfactual_row(case, result, history, 2.0)
    assert crossed is not None
    assert crossed["claim"] == finding.claim
    assert crossed["anchor"] == {"file": "parser.py", "line": 7}
    assert crossed["failure_scenario"] == finding.failure_scenario
    assert crossed["wealth"] == {
        "S": 1.0,
        "T": 1.0,
        "F": 2.0,
        "before": 6.0,
        "after": 12.0,
        "threshold": 10.0,
    }
    assert _counterfactual_row(
        case,
        replace(result, wealth=9.0),
        {**history, "triggered": False},
        3.0,
    ) is None
