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
    records = [entry for entry in entries if entry["kind"] in {"review", "review_run"}]
    assert [entry["kind"] for entry in records] == ["review", "review_run"]
    assert {entry["task_id"] for entry in records} == {run.task_id}
    assert records[1]["elapsed_s"] == 1.25


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
