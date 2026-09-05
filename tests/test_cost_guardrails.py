"""Two ceilings, and a silence that says which one stopped it (D-161).

`budget_usd` bounds one review. It does not bound a repository: an afternoon of
pull requests costs an unbounded amount however small each one is. So there is
a second ceiling over a rolling 24 hours of one repository's ledger, and over
it a review buys nothing and says so.

And a silence that was bought out is a different claim from a silence where
every candidate was judged. The line now says which: *the budget ceiling was
reached; N candidate(s) were not verified*.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from attest.review.budget import DAILY_WINDOW_S, daily_spend
from attest.review.config import ReviewConfig
from attest.review.ledger import Ledger
from attest.review.output_contract import budget_unverified, silence_line
from attest.review.proposer import MockProvider
from attest.review.run import run_review

NOW = time.time()


def _stamp(offset_s: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(NOW + offset_s))


def _rows(*spends_and_ages: tuple[float, float]) -> list[dict[str, object]]:
    return [
        {"ts": _stamp(-age), "kind": "review_run", "task_id": "t", "spend_usd": spend}
        for spend, age in spends_and_ages
    ]


def test_daily_spend_counts_only_the_last_day() -> None:
    rows = _rows((0.40, 60.0), (0.35, 3_600.0), (9.00, DAILY_WINDOW_S + 600.0))

    total, counted = daily_spend(rows, now=NOW)

    assert round(total, 4) == 0.75
    assert counted == 2


def test_an_unreadable_timestamp_is_charged_rather_than_skipped() -> None:
    """A ceiling is a safety limit; the safe direction for a row it cannot read
    is to charge it, never to let it through."""
    rows = [{"ts": "not-a-timestamp", "kind": "review_run", "spend_usd": 5.0}]

    total, counted = daily_spend(rows, now=NOW)

    assert total == 5.0 and counted == 1


def test_rows_that_are_not_spend_contribute_nothing() -> None:
    rows = [
        {"ts": _stamp(-10), "kind": "review", "spend": 3.0},
        {"ts": _stamp(-10), "kind": "review_run", "spend_usd": "0.5"},
        {"ts": _stamp(-10), "kind": "review_run", "spend_usd": float("inf")},
        {"ts": _stamp(-10), "kind": "review_run", "spend_usd": -1.0},
    ]

    assert daily_spend(rows, now=NOW) == (0.0, 0)


def _repo(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)

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


def test_a_repository_over_its_daily_ceiling_buys_nothing_and_says_so(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "over")
    ledger = Ledger(repo)
    for _ in range(3):
        ledger.append({"kind": "review_run", "task_id": "earlier", "spend_usd": 0.9})

    run = run_review(
        repo,
        None,
        ReviewConfig(
            probe_generation=False, k_samples=1, tier0_commands=[], daily_budget_usd=2.0
        ),
        MockProvider(["never asked"]),
    )

    assert run.results == []
    assert run.budget.spent_usd == 0.0
    assert run.deferred_reason is not None
    assert "daily budget ceiling reached" in run.deferred_reason
    assert "0 candidates were verified" in run.deferred_reason


def test_under_the_daily_ceiling_the_review_runs(tmp_path: Path) -> None:
    repo = _repo(tmp_path / "under")
    Ledger(repo).append({"kind": "review_run", "task_id": "earlier", "spend_usd": 0.5})

    run = run_review(
        repo,
        None,
        ReviewConfig(
            probe_generation=False, k_samples=1, tier0_commands=[], daily_budget_usd=5.0
        ),
        MockProvider(['{"findings": []}']),
    )

    assert run.deferred_reason is None or "daily budget" not in run.deferred_reason


def test_the_silence_line_says_how_many_the_ceiling_stopped() -> None:
    stopped = silence_line(units_read=1, units_planned=1, spend_usd=0.25, elapsed_s=9.0, unverified=7)
    judged = silence_line(units_read=1, units_planned=1, spend_usd=0.25, elapsed_s=9.0)

    assert "the budget ceiling was reached; 7 candidate(s) were not verified" in stopped
    assert "nothing met an adjudicator's bar" in judged
    assert "ceiling" not in judged


def test_the_unverified_count_reads_the_drawer_reasons() -> None:
    reasons = {
        "a": "budget-exhausted: generation failed: BudgetExceeded: call 'probe-1'",
        "b": "verification deferred: intent: value change confirmed",
        "c": "预算不足，未买到复现",
    }

    assert budget_unverified(reasons) == 2
    assert budget_unverified({}) == 0
    assert budget_unverified(None) == 0


@pytest.mark.parametrize("value", (-1.0, float("nan"), True))
def test_the_daily_ceiling_is_validated(value: object) -> None:
    with pytest.raises(ValueError, match="daily_budget_usd"):
        ReviewConfig(daily_budget_usd=value)  # type: ignore[arg-type]
