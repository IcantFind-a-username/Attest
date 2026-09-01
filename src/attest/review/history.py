"""Sparse, unpriced observations from the anchored line's git history."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from attest.review.schema import Finding

HISTORY_SIGNAL_SCHEMA_VERSION = "attest.history-signal.v1"
HISTORY_LOOKBACK_COMMITS = 50
_REPAIR_SUBJECT = re.compile(r"\b(?:revert|hotfix)\b", re.IGNORECASE)


@dataclass(frozen=True)
class HistorySignal:
    triggered: bool
    commit_sha: str | None
    commit_message: str | None


def _git_output(repo: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def inspect_history_signal(repo: Path, finding: Finding) -> HistorySignal:
    """Observe whether a recent revert/hotfix owns the current anchor line.

    The observation fails open and is never a wealth purchase. "Recent" is
    the fixed, recorded window of the latest 50 commits reachable from HEAD.
    """

    blame = _git_output(
        repo,
        "blame",
        "--line-porcelain",
        f"-L{finding.line},{finding.line}",
        "HEAD",
        "--",
        finding.file,
    )
    if not blame:
        return HistorySignal(False, None, None)
    commit_sha = blame.split(maxsplit=1)[0].lstrip("^")
    recent = _git_output(repo, "rev-list", f"--max-count={HISTORY_LOOKBACK_COMMITS}", "HEAD")
    if not recent or commit_sha not in recent.splitlines():
        return HistorySignal(False, commit_sha, None)
    message = _git_output(repo, "show", "-s", "--format=%B", commit_sha)
    return HistorySignal(
        bool(message and _REPAIR_SUBJECT.search(message)),
        commit_sha,
        message or None,
    )
