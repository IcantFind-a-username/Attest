"""Task-scoped candidate persistence."""

import json
from pathlib import Path

from attest.review.candidates import CandidateStore
from attest.review.gate import GateResult
from attest.review.schema import Finding


def _finding() -> Finding:
    return Finding(
        claim="average() divides by zero when items is empty.",
        file="app.py",
        line=6,
        failure_scenario="average([]) raises ZeroDivisionError",
        falsification_plan="call average([]) and observe the exception",
        votes=2,
        sample_ids=[1, 3],
    )


def _result(finding: Finding, wealth: float = 2.6390158215457884) -> GateResult:
    return GateResult(finding=finding, wealth=wealth, decision=None)


def test_latest_is_scoped_to_task_catches_losing_task_id(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path)
    finding = _finding()
    store.append("review-a", 0.1, [_result(finding, 2.0)])
    store.append("review-b", 0.2, [_result(finding, 3.0)])

    assert store.latest(finding.finding_id, "review-a").task_id == "review-a"  # type: ignore[union-attr]
    latest_b = store.latest(finding.finding_id, "review-b")
    assert latest_b is not None
    assert latest_b.task_id == "review-b"
    assert latest_b.wealth == 3.0


def test_load_round_trips_finding_fields_catches_losing_a_finding_field(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path)
    finding = _finding()
    store.append("review-a", 0.1, [_result(finding)])

    stored = store.load("review-a")

    assert len(stored) == 1
    assert stored[0].finding == finding
    assert stored[0].alpha == 0.1
    assert stored[0].action == "drawer"


def test_load_skips_corrupt_rows_catches_aborting_on_one_corrupt_row(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path)
    finding = _finding()
    store.append("review-a", 0.1, [_result(finding)])
    malformed = {
        "task_id": "bad",
        "finding_id": "bad",
        "file": "app.py",
        "line": 6,
        "claim": None,
        "failure_scenario": "scenario",
        "falsification_plan": "plan",
        "votes": 1,
        "wealth": 1.0,
        "action": "drawer",
        "alpha": 0.1,
    }
    store.path.write_text(
        "not json\n" + json.dumps(malformed) + "\n" + store.path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    stored = store.load()

    assert [candidate.task_id for candidate in stored] == ["review-a"]


def test_load_skips_nonfinite_json_numbers_as_malformed_rows(tmp_path: Path) -> None:
    store = CandidateStore(tmp_path)
    store.path.parent.mkdir()
    store.path.write_text(
        json.dumps(
            {
                "task_id": "bad",
                "finding_id": "bad",
                "file": "app.py",
                "line": 6,
                "claim": "claim",
                "failure_scenario": "scenario",
                "falsification_plan": "plan",
                "votes": 1,
                "wealth": float("nan"),
                "action": "drawer",
                "alpha": 0.1,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    assert store.load() == []
