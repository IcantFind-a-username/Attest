"""The same review, said to a machine, and the same summary as numbers (D-163).

A pipeline that wants to gate a merge, chart a speech rate or bill a repository
had to parse prose written for a person to get numbers the run already had. A
parser of prose is a bug waiting for a rewording.

`attest review --json` and `attest stats --json` are **projections of what the
text already says**, not second reports: the level lines are the same lines and
the drawer histogram is the same histogram the accounting line prints.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from attest.cli.main import main
from attest.review.ledger import Ledger
from attest.review.machine import (
    REVIEW_JSON_SCHEMA_VERSION,
    STATS_JSON_SCHEMA_VERSION,
    stats_json,
)


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


def _payload(tmp_path: Path) -> Path:
    path = tmp_path / "payload.json"
    path.write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "claim": "average() divides by zero when items is empty.",
                        "anchor": {"file": "app.py", "line": 5},
                        "failure_scenario": "average([]) raises ZeroDivisionError",
                        "falsification_plan": "call average([]) and observe",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    return path


def test_review_json_is_one_object_with_the_levels_and_the_numbers(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = main(
        [
            "--repo",
            str(repo),
            "review",
            "--base",
            "HEAD",
            "--k",
            "1",
            "--json",
            "--mock",
            str(_payload(tmp_path)),
        ]
    )

    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["schema_version"] == REVIEW_JSON_SCHEMA_VERSION
    assert set(payload["levels"]) == {"red", "gate", "yellow", "green"}
    assert payload["candidates"]["total"] >= 1
    assert isinstance(payload["drawer_reasons"], dict)
    assert isinstance(payload["unverified_by_budget"], int)
    assert payload["silent"] is (not any(payload["levels"].values()))
    assert payload["units"]["read"] >= 0
    assert payload["spend_usd"] >= 0.0
    for candidate in payload["silent_candidates"]:
        assert {"finding_id", "file", "line", "reason_class", "spend_usd"} <= set(candidate)


def test_the_json_and_the_report_are_the_same_run(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A projection, not a second report: what the accounting line counts and
    what the object counts must agree."""
    payload_file = _payload(tmp_path)
    argv = ["--repo", str(repo), "review", "--base", "HEAD", "--k", "1", "--mock"]

    main([*argv, str(payload_file)])
    text = capsys.readouterr().out
    main([*argv, str(payload_file), "--json"])
    obj = json.loads(capsys.readouterr().out)

    accounting = [line for line in text.splitlines() if line.startswith("read ")][-1]
    assert f"candidates {obj['candidates']['total']}" in accounting
    assert f"drawer {obj['candidates']['drawer']}" in accounting


def test_explain_names_the_coordinate_the_reason_and_the_cost(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    main(
        [
            "--repo",
            str(repo),
            "review",
            "--base",
            "HEAD",
            "--k",
            "1",
            "--explain",
            "--mock",
            str(_payload(tmp_path)),
        ]
    )

    lines = [
        line
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("  [") and "app.py:" in line
    ]
    assert lines, "no --explain line was printed"
    assert "app.py:5" in lines[0]
    assert "$" in lines[0], "the cost column is missing"
    assert " — " in lines[0], "the reason class is missing"


def test_stats_json_summarises_speech_spend_drawers_and_the_image_cache(repo: Path) -> None:
    ledger = Ledger(repo)
    ledger.append({"kind": "review_run", "task_id": "t1", "spend_usd": 0.25, "elapsed_s": 4.0})
    ledger.append({"kind": "review_run", "task_id": "t2", "spend_usd": 0.75, "elapsed_s": 8.0})
    ledger.append(
        {
            "kind": "structural_note",
            "schema_version": "attest.structural-note.v2",
            "task_id": "t1",
            "policy_version": "p",
            "note_id": "a|b",
            "fingerprint": "f",
            "similarity": 1.0,
            "advice_published": False,
            "refusal": None,
        }
    )
    ledger.append({"kind": "image_cache", "task_id": "t1", "tag": "x", "cached": False})
    ledger.append({"kind": "image_cache", "task_id": "t2", "tag": "x", "cached": True})

    payload = stats_json(repo)

    assert payload["schema_version"] == STATS_JSON_SCHEMA_VERSION
    assert payload["reviews"] == 2
    assert payload["spoke_on"]["green"] == 1
    assert payload["speech_rate"]["green"] == 0.5
    assert payload["speech_rate"]["red"] == 0.0
    assert payload["spend_usd"] == 1.0
    assert payload["spend_per_review_usd"] == 0.5
    assert payload["images"] == {"lookups": 2, "hits": 1, "hit_rate": 0.5}


def test_stats_json_of_an_empty_repository_says_nothing_rather_than_dividing_by_zero(
    repo: Path,
) -> None:
    payload = stats_json(repo)

    assert payload["reviews"] == 0
    assert payload["speech_rate"] == {level: None for level in ("red", "gate", "yellow", "green")}
    assert payload["spend_per_review_usd"] is None
    assert payload["images"]["hit_rate"] is None


def test_the_stats_command_prints_valid_json(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    Ledger(repo).append({"kind": "review_run", "task_id": "t1", "spend_usd": 0.1})

    code = main(["--repo", str(repo), "stats", "--json"])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["reviews"] == 1


def test_a_local_review_records_the_levels_below_red_too(
    repo: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """D-167: the ledger is the record of what this product *said*, and until now
    only `attest ci` wrote the rows for the three levels below red. A repository
    reviewed only locally therefore read as "green never spoke" in
    `attest stats` on runs where green spoke on a third of the commits."""
    body = (
        "def summarise(rows, key):\n"
        "    seen = {}\n"
        "    for row in rows:\n"
        "        value = row.get(key)\n"
        "        if value is None:\n"
        "            continue\n"
        "        seen.setdefault(value, []).append(row)\n"
        "    return [(name, len(items)) for name, items in sorted(seen.items())]\n"
    )
    (repo / "one.py").write_text(body, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "one"], check=True, capture_output=True
    )
    (repo / "two.py").write_text(body.replace("summarise", "tally"), encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "two"], check=True, capture_output=True
    )

    code = main(
        [
            "--repo",
            str(repo),
            "review",
            "--base",
            "HEAD~1",
            "--k",
            "1",
            "--mock",
            str(_payload(tmp_path)),
        ]
    )
    out = capsys.readouterr().out

    assert code == 0
    assert "[green]" in out, "the fixture did not make green speak"
    rows = [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    green_rows = [row for row in rows if row.get("kind") == "structural_note"]
    assert len(green_rows) == out.count("[green]")
    assert green_rows[0]["fingerprint"], "the row must carry D-160's fingerprint"
    assert green_rows[0]["schema_version"] == "attest.structural-note.v2"

    # and the summary now agrees with what the terminal printed
    assert stats_json(repo)["spoke_on"]["green"] == 1
