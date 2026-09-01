"""Graded, unpriced change-heat observations for an anchored line.

F is an observation channel, never a purchase. It multiplies no wealth, orders
nothing, vetoes nothing, and reaches no publication path (D-064).

The first definition asked one boolean question — is the anchor line owned by a
recent revert or hotfix? — and fired on nothing in 26 candidates. A rare event
answered once is not a fair test of whether the line's history carries signal,
so the observation is now graded: four raw values per candidate, recorded
without a threshold, so a later analysis can look at the distribution rather
than at a trigger rate.

"Recent" is measured from the reviewed revision's own commit date, not from the
wall clock. A corpus pair from 2019 must be asked about its own 12 months.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from attest.review.schema import Finding

HISTORY_SIGNAL_SCHEMA_VERSION = "attest.history-signal.v2"
HISTORY_LOOKBACK_DAYS = 365
# Repair vocabulary, recorded with every row so the share is auditable rather
# than asserted. Deliberately broader than v1's revert|hotfix, which is a rare
# event rather than a graded one.
REPAIR_SUBJECT_PATTERN = (
    r"\b(?:revert|reverts|reverted|hotfix|fix|fixes|fixed|fixing|bug|bugfix"
    r"|regression|regressions|broken|crash|repair)\b"
)
_REPAIR_SUBJECT = re.compile(REPAIR_SUBJECT_PATTERN, re.IGNORECASE)
# Unit separator: argv cannot carry a NUL, and no commit subject contains this.
_RECORD_SEPARATOR = "\x1f"


@dataclass(frozen=True)
class HistorySignal:
    """Four raw values describing how much the anchor line has been churned.

    Every field is recorded as observed. Nothing here is compared with a
    threshold, and no field is combined into a score.
    """

    available: bool
    commits: int
    repair_commits: int
    repair_share: float | None
    distinct_authors: int
    days_since_last_change: int | None
    reference_date: str | None
    lookback_days: int
    latest_commit_sha: str | None
    latest_commit_message: str | None

    @classmethod
    def unavailable(cls) -> HistorySignal:
        """The fail-open value: git could not answer, and nothing is inferred."""
        return cls(
            available=False,
            commits=0,
            repair_commits=0,
            repair_share=None,
            distinct_authors=0,
            days_since_last_change=None,
            reference_date=None,
            lookback_days=HISTORY_LOOKBACK_DAYS,
            latest_commit_sha=None,
            latest_commit_message=None,
        )

    def to_json_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "commits": self.commits,
            "repair_commits": self.repair_commits,
            "repair_share": self.repair_share,
            "distinct_authors": self.distinct_authors,
            "days_since_last_change": self.days_since_last_change,
            "reference_date": self.reference_date,
            "lookback_days": self.lookback_days,
            "latest_commit_sha": self.latest_commit_sha,
            "latest_commit_message": self.latest_commit_message,
        }


def _git_output(repo: Path, *args: str, timeout_s: float = 15.0) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_s,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return completed.stdout.strip() if completed.returncode == 0 else None


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def inspect_history_signal(
    repo: Path, finding: Finding, *, lookback_days: int = HISTORY_LOOKBACK_DAYS
) -> HistorySignal:
    """Observe how often and by whom the anchor line changed, and how recently.

    The observation fails open and is never a wealth purchase. The window ends
    at the reviewed revision's own commit date, so a historical revision is
    asked about its own recent past rather than about today's.
    """

    head_date_raw = _git_output(repo, "show", "-s", "--format=%aI", "HEAD")
    reference = None if head_date_raw is None else _parse_date(head_date_raw)
    if reference is None:
        return HistorySignal.unavailable()
    since = (reference - timedelta(days=lookback_days)).isoformat()
    log = _git_output(
        repo,
        "log",
        f"--since={since}",
        f"-L{finding.line},{finding.line}:{finding.file}",
        f"--format=%H{_RECORD_SEPARATOR}%an{_RECORD_SEPARATOR}%aI{_RECORD_SEPARATOR}%s",
        "-s",
    )
    if log is None:
        return HistorySignal.unavailable()

    commits: list[tuple[str, str, datetime | None, str]] = []
    for line in log.splitlines():
        parts = line.split(_RECORD_SEPARATOR)
        if len(parts) != 4:
            continue
        sha, author, when, subject = parts
        commits.append((sha, author, _parse_date(when), subject))

    repair_commits = sum(1 for _, _, _, subject in commits if _REPAIR_SUBJECT.search(subject))
    dates = [when for _, _, when, _ in commits if when is not None]
    latest = max(dates, default=None)
    return HistorySignal(
        available=True,
        commits=len(commits),
        repair_commits=repair_commits,
        repair_share=(repair_commits / len(commits) if commits else None),
        distinct_authors=len({author for _, author, _, _ in commits}),
        days_since_last_change=(
            None if latest is None else max(0, (reference - latest).days)
        ),
        reference_date=reference.isoformat(),
        lookback_days=lookback_days,
        latest_commit_sha=commits[0][0] if commits else None,
        latest_commit_message=commits[0][3] if commits else None,
    )
