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


def test_history_signal_grades_the_anchor_line_instead_of_thresholding_it(
    tmp_path: Path,
) -> None:
    """F records four raw values; no field is compared with a threshold.

    D-064: the v1 boolean asked whether a recent revert or hotfix owned the
    line and fired on nothing in 26 candidates. A rare event answered once is
    not a fair test, so the observation is graded and left unpriced.
    """
    repo = _repo(tmp_path, "hotfix: restore value")
    _git(repo, "config", "user.name", "Second")
    (repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    _git(repo, "commit", "-qam", "refactor value")

    signal = inspect_history_signal(repo, _finding())

    assert signal.available is True
    assert signal.commits == 2
    assert signal.repair_commits == 1
    assert signal.repair_share == 0.5
    assert signal.distinct_authors == 2
    assert signal.days_since_last_change == 0
    assert signal.latest_commit_message == "refactor value"
    assert not hasattr(signal, "triggered")


def test_the_window_ends_at_the_reviewed_revision_not_at_the_wall_clock(
    tmp_path: Path,
) -> None:
    """A 2019 revision must be asked about its own twelve months."""
    repo = _repo(tmp_path, "fix: restore value")
    (repo / "app.py").write_text("value = 2\n", encoding="utf-8")
    _git(
        repo,
        "-c",
        "user.name=Test",
        "commit",
        "-qam",
        "later change",
        "--date=2019-01-02T00:00:00+00:00",
    )

    signal = inspect_history_signal(repo, _finding())

    assert signal.available is True
    assert signal.reference_date is not None
    # The window is anchored on HEAD's own author date, so the older commit is
    # inside it even though it is years before today.
    assert signal.commits == 2


def test_an_unreadable_anchor_fails_open_and_infers_nothing(tmp_path: Path) -> None:
    repo = _repo(tmp_path, "refactor value")

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

    assert missing.available is False
    assert missing.commits == 0
    assert missing.repair_share is None
    assert missing.days_since_last_change is None
