from __future__ import annotations

import subprocess
from pathlib import Path

from attest.review.history import inspect_history_signal
from attest.review.schema import Finding


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _finding() -> Finding:
    return Finding(
        claim="The value is wrong.",
        file="app.py",
        line=1,
        failure_scenario="Calling value returns the wrong integer.",
        falsification_plan="Call value and compare its result.",
    )


def _repo(tmp_path: Path, subject: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "app.py").write_text("value = 1\n", encoding="utf-8")
    _git(repo, "add", "app.py")
    _git(repo, "commit", "-qm", subject)
    return repo


def test_recent_hotfix_owning_anchor_triggers(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "hotfix: restore value")

    signal = inspect_history_signal(repo, _finding())

    assert signal.triggered is True
    assert signal.commit_sha == _git(repo, "rev-parse", "HEAD")
    assert signal.commit_message == "hotfix: restore value"


def test_ordinary_commit_and_unavailable_anchor_do_not_trigger(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "refactor value")

    ordinary = inspect_history_signal(repo, _finding())
    missing = inspect_history_signal(
        repo,
        Finding(
            claim="Missing.",
            file="missing.py",
            line=1,
            failure_scenario="The file is absent.",
            falsification_plan="Check the path.",
        ),
    )

    assert ordinary.triggered is False
    assert ordinary.commit_message == "refactor value"
    assert missing.triggered is False
    assert missing.commit_sha is None
