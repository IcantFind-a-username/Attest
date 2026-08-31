"""Review-run service parity on a real working-tree diff."""

import json
import subprocess
from pathlib import Path

import pytest

from attest.review.candidates import CandidateStore
from attest.review.config import ReviewConfig
from attest.review.proposer import MockProvider
from attest.review.run import run_review


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "app.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "base")
    (tmp_path / "app.py").write_text(
        "def total(items):\n    return sum(items)\n\n\ndef average(items):\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    return tmp_path


def _payload() -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "claim": "average() divides by zero when items is empty.",
                    "anchor": {"file": "app.py", "line": 5},
                    "failure_scenario": "average([]) raises ZeroDivisionError",
                    "falsification_plan": "call average([]) and observe the exception",
                }
            ]
        }
    )


def test_run_review_persists_one_task_scoped_drawer_and_elapsed_time(repo: Path) -> None:
    ticks = iter([10.0, 11.25])
    run = run_review(
        repo,
        None,
        ReviewConfig(k_samples=1, tier0_commands=[]),
        MockProvider([_payload()]),
        clock=lambda: next(ticks),
    )

    assert run.elapsed_s == 1.25
    assert len(run.results) == 1
    assert run.results[0].action == "drawer"
    stored = CandidateStore(repo).load(run.task_id)
    assert [candidate.task_id for candidate in stored] == [run.task_id]
    entries = [
        json.loads(line) for line in (repo / ".attest" / "ledger.jsonl").read_text().splitlines()
    ]
    history = [entry for entry in entries if entry["kind"] == "history_signal"]
    records = [entry for entry in entries if entry["kind"] in {"review", "review_run"}]
    assert len(history) == 1
    assert history[0]["schema_version"] == "attest.history-signal.v1"
    assert history[0]["priced"] is False
    assert history[0]["finding_id"] == run.results[0].finding.finding_id
    assert run.results[0].wealth == 2.0
    assert [purchase.channel for purchase in run.results[0].purchases] == ["S"]
    assert [entry["kind"] for entry in records] == ["review", "review_run"]
    assert records[0]["channels_bought"] == ["S"]
    assert {entry["task_id"] for entry in records} == {run.task_id}
    assert records[1]["elapsed_s"] == 1.25
    assert records[1]["provider_samples"] == [
        {"sample": 0, "stop_reason": "not_recorded", "output_tokens": 200}
    ]
    assert "provider sample 0: stop_reason=not_recorded; output_tokens=200" in run.notes


def test_run_review_defers_before_a_model_call_when_budget_is_exceeded(repo: Path) -> None:
    provider = MockProvider([_payload()])

    run = run_review(
        repo,
        None,
        ReviewConfig(budget_usd=0.000001, k_samples=1, tier0_commands=[]),
        provider,
        clock=lambda: 5.0,
    )

    assert run.deferred_reason is not None
    assert run.deferred_reason.startswith("budget:")
    assert provider.calls == 0
    assert run.results == []
    assert run.outcome.formal == []


def test_run_review_cancels_partial_reservations_on_budget_defer(repo: Path) -> None:
    provider = MockProvider([_payload()])

    run = run_review(
        repo,
        None,
        ReviewConfig(budget_usd=0.03, k_samples=2, tier0_commands=[]),
        provider,
        clock=lambda: 5.0,
    )

    assert run.deferred_reason is not None
    assert provider.calls == 0
    assert run.budget.spent_usd == 0.0
    assert run.budget.reserved_usd == 0.0


@pytest.mark.parametrize("payload", ["{not-json", '{"findings": "malformed"}'])
def test_run_review_defers_when_no_provider_sample_is_valid(repo: Path, payload: str) -> None:
    run = run_review(
        repo,
        None,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        MockProvider([payload]),
    )

    assert run.deferred_reason == "all provider samples failed or were malformed"


def test_run_review_accepts_valid_empty_and_partial_success(repo: Path) -> None:
    empty = run_review(
        repo,
        None,
        ReviewConfig(k_samples=1, tier0_commands=[]),
        MockProvider(['{"findings": []}']),
    )
    partial = run_review(
        repo,
        None,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        MockProvider(["{not-json", _payload()]),
    )

    assert empty.deferred_reason is None
    assert partial.deferred_reason is None
    assert len(partial.results) == 1


def test_unreachable_gate_records_explainable_defer_and_zero_spend_run(repo: Path) -> None:
    run = run_review(
        repo,
        None,
        ReviewConfig(alpha=0.001, k_samples=1, tier0_commands=[]),
        MockProvider([_payload()]),
    )

    rows = [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert run.deferred_reason == "unreachable gate"
    assert [row["kind"] for row in rows] == ["defer", "review_run"]
    assert rows[0]["reason"] == "unreachable gate"
    assert rows[1]["spend_usd"] == 0.0
