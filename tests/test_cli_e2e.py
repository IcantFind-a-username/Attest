"""End-to-end CLI test on a real temp git repo with a mock provider."""

import json
import subprocess
from pathlib import Path

import pytest

from attest.cli.main import main

CLEAN = """def total(items):
    return sum(items)
"""

BUGGY = """def total(items):
    return sum(items)


def average(items):
    result = sum(items) / len(items)
    return result
"""


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "app.py").write_text(CLEAN, encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "base")
    (tmp_path / "app.py").write_text(BUGGY, encoding="utf-8")
    return tmp_path


def _payload(*findings: dict) -> str:
    return json.dumps({"findings": list(findings)})


FINDING_A = {
    "claim": "average() divides by zero when items is empty.",
    "anchor": {"file": "app.py", "line": 6},
    "failure_scenario": "average([]) raises ZeroDivisionError",
    "falsification_plan": "call average([]) and observe the exception",
}
FINDING_A2 = {
    "claim": "Division by zero in average() when items is an empty list.",
    "anchor": {"file": "app.py", "line": 6},
    "failure_scenario": "average([]) -> ZeroDivisionError",
    "falsification_plan": "run average([])",
}


@pytest.fixture
def mocks(tmp_path: Path) -> list[str]:
    p1 = tmp_path / "m1.json"
    p2 = tmp_path / "m2.json"
    p3 = tmp_path / "m3.json"
    p1.write_text(_payload(FINDING_A), encoding="utf-8")
    p2.write_text(_payload(FINDING_A2), encoding="utf-8")
    p3.write_text(_payload(), encoding="utf-8")
    return [str(p1), str(p2), str(p3)]


def test_review_verify_feedback_stats(repo: Path, mocks: list[str], capsys) -> None:
    # --- review: 2 of 3 samples assert the finding -> drawer (S=2.64 < 10)
    rc = main(["--repo", str(repo), "review", "--k", "3", "--mock", *mocks])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no findings cleared the evidence bar" in out
    assert "drawer (1 candidate(s)" in out
    assert "reachable only" in out  # feasibility transparency note
    assert "divides by zero" in out or "Division by zero" in out

    ledger_path = repo / ".attest" / "ledger.jsonl"
    assert ledger_path.is_file()
    entries = [json.loads(x) for x in ledger_path.read_text().splitlines() if x.strip()]
    reviews = [e for e in entries if e["kind"] == "review"]
    assert len(reviews) == 1
    assert reviews[0]["action"] == "drawer"
    assert reviews[0]["channels_bought"] == ["S"]
    finding_id = reviews[0]["finding_id"]
    # CandidateStore must skip malformed legacy/corrupt rows so a valid stored
    # candidate remains verifiable.
    candidates_path = repo / ".attest" / "candidates.jsonl"
    candidates_path.write_text(
        '{"task_id": "incomplete"}\n' + candidates_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    # --- verify: reproduction pushes wealth past the gate
    rc = main(
        [
            "--repo",
            str(repo),
            "verify",
            finding_id,
            "--reproduced",
            "--evidence",
            "python -c average([]) -> ZeroDivisionError",
        ]
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "=> surface" in out

    # --- feedback + stats
    rc = main(["--repo", str(repo), "feedback", finding_id, "--good"])
    capsys.readouterr()
    assert rc == 0
    rc = main(["--repo", str(repo), "stats"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "runs: 1" in out
    assert "surfaced: 1" in out  # the verified surface


def test_review_budget_defer(repo: Path, mocks: list[str], capsys) -> None:
    rc = main(["--repo", str(repo), "review", "--k", "3", "--budget", "0.000001", "--mock", *mocks])
    out = capsys.readouterr().out
    assert rc == 0
    assert "DEFER: budget:" in out
    entries = [
        json.loads(x)
        for x in (repo / ".attest" / "ledger.jsonl").read_text().splitlines()
        if x.strip()
    ]
    assert any(e["kind"] == "defer" for e in entries)


def test_review_no_diff(repo: Path, mocks: list[str], capsys) -> None:
    subprocess.run(["git", "-C", str(repo), "checkout", "--", "app.py"], check=True)
    rc = main(["--repo", str(repo), "review", "--mock", mocks[0]])
    out = capsys.readouterr().out
    assert rc == 0
    assert "no diff" in out


def test_mock_without_files_rejected(repo: Path) -> None:
    # regression: `--mock` with zero files must NEVER fall through to the
    # real paid API — argparse rejects it outright
    with pytest.raises(SystemExit):
        main(["--repo", str(repo), "review", "--mock"])


def test_invalid_cli_override_rejected(repo: Path, mocks: list[str], capsys) -> None:
    # regression: CLI overrides must go through config validation
    rc = main(["--repo", str(repo), "review", "--alpha", "5.0", "--mock", *mocks])
    assert rc == 2
    assert "alpha" in capsys.readouterr().err


def test_verify_unknown_id(repo: Path, capsys) -> None:
    rc = main(["--repo", str(repo), "verify", "0000000000", "--reproduced"])
    assert rc == 2


def test_unreachable_gate_refused(repo: Path, mocks: list[str], capsys) -> None:
    rc = main(["--repo", str(repo), "review", "--alpha", "0.001", "--k", "3", "--mock", *mocks])
    assert rc == 2
    err = capsys.readouterr().err
    assert "unreachable" in err
