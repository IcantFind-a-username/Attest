"""D-171: `attest stats --since` and the period report it prints.

Stable-period preparation (owner instruction 7 of 2026-09-07): the running
totals of a whole ledger are the right default and the wrong thing to hand
someone on a Monday. `--since` slices the ledger *before* anything is counted,
so every number in the report is about the window.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from attest.review.window import parse_since, row_time, since


def _row(ts: str, kind: str = "review_run", **extra: object) -> dict[str, object]:
    return {"ts": ts, "kind": kind, "task_id": ts, **extra}


NOW = datetime(2026, 9, 8, 12, 0, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("spec", "expected"),
    (
        ("7d", NOW - timedelta(days=7)),
        ("24h", NOW - timedelta(hours=24)),
        ("90m", NOW - timedelta(minutes=90)),
        ("2w", NOW - timedelta(weeks=2)),
        ("2026-09-01", datetime(2026, 9, 1, tzinfo=UTC)),
        (
            "2026-09-01T09:00:00+0800",
            datetime(2026, 9, 1, 9, 0, tzinfo=timezone(timedelta(hours=8))),
        ),
    ),
)
def test_every_spelling_a_person_writes_is_read(spec: str, expected: datetime) -> None:
    parsed = parse_since(spec, now=NOW)
    assert abs((parsed - expected).total_seconds()) < 1


@pytest.mark.parametrize("spec", ("last tuesday", "", "7", "d7", "7x", "2026-13-01", "  "))
def test_a_spec_that_cannot_be_read_is_refused_with_the_spellings_that_can(spec: str) -> None:
    """A report over the wrong window is worse than a report that did not run."""
    with pytest.raises(ValueError) as raised:
        parse_since(spec, now=NOW)
    assert "7d" in str(raised.value) and "2026-09-01" in str(raised.value)


def test_the_window_keeps_what_is_at_or_after_the_boundary() -> None:
    rows = [
        _row("2026-09-01T00:00:00+0000"),
        _row("2026-09-07T00:00:00+0000"),
        _row("2026-09-08T11:59:59+0000"),
    ]
    kept, unreadable = since(rows, datetime(2026, 9, 7, tzinfo=UTC))
    assert [row["ts"] for row in kept] == [
        "2026-09-07T00:00:00+0000",
        "2026-09-08T11:59:59+0000",
    ]
    assert unreadable == 0


def test_a_row_whose_timestamp_cannot_be_read_is_shown_not_dropped() -> None:
    """The opposite default from `daily_spend`, and for the opposite reason: a
    cap is safe when it charges an unreadable row, a report is honest when it
    shows one."""
    rows = [_row("not a timestamp"), _row(""), _row("2026-09-08T00:00:00+0000")]
    rows.append({"kind": "review_run"})  # no `ts` at all
    kept, unreadable = since(rows, datetime(2026, 9, 7, tzinfo=UTC))
    assert len(kept) == 4
    assert unreadable == 3
    assert row_time("not a timestamp") is None
    assert row_time("2026-09-08T00:00:00+0000") is not None


def test_the_report_is_about_the_window_and_says_so(tmp_path: Path) -> None:
    from attest.cli.main import main

    repo = tmp_path / "repo"
    (repo / ".attest").mkdir(parents=True)
    ledger = repo / ".attest" / "ledger.jsonl"
    ledger.write_text(
        "\n".join(
            json.dumps(row)
            for row in (
                _row("2026-08-01T00:00:00+0000", spend_usd=9.0, elapsed_s=10.0),
                _row("2026-09-08T00:00:00+0000", spend_usd=0.25, elapsed_s=4.0),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    assert main(["--repo", str(repo), "stats", "--since", "2026-09-01"]) == 0


def test_an_unreadable_since_exits_two_without_a_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from attest.cli.main import main

    repo = tmp_path / "repo"
    (repo / ".attest").mkdir(parents=True)
    (repo / ".attest" / "ledger.jsonl").write_text("", encoding="utf-8")
    assert main(["--repo", str(repo), "stats", "--since", "whenever"]) == 2
    captured = capsys.readouterr()
    assert "cannot read --since" in captured.err
    assert captured.out == ""
