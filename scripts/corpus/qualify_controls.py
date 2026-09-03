"""Does a commit qualify as a *control* — a commit with positive evidence that
what it changed was not a defect?

The 2026-09-03 real-traffic corpus chose controls by commit subject (`docs:`,
`refactor:`, test-only) and two of them carried real defects. The 2026-09-04
amendment to `G-NULL-001` replaces that with two checks, both positive, both
free of any model call:

1. **age** -- the commit is at least six months older than the measurement date;
2. **untouched** -- no later commit on the default branch touches a line it
   added. Checked forward with ``git blame``: every line the commit added to a
   file must still be present at the branch tip and still blamed to that commit.
   One line re-blamed, deleted, or a whole file gone, and the control is
   dropped.

Any later commit disqualifies, whether or not it looks like a fix: deciding
"was that a fix?" is the subjective judgement the amendment exists to remove,
and the conservative reading only ever drops controls. The cost is a bias
toward cold code, which this script measures rather than hides: it reports the
number of surviving lines beside the number added.

Usage::

    python scripts/corpus/qualify_controls.py <repo> <sha> [<sha> ...]
    python scripts/corpus/qualify_controls.py --json <repo> <sha> ...
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

MONTHS_REQUIRED = 6
DAYS_PER_MONTH = 30.4375  # mean Gregorian month; six of them is the gate's floor
HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(?P<start>\d+)(?:,(?P<count>\d+))? @@")


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()[:300]}")
    return result.stdout


@dataclass
class FileVerdict:
    path: str
    added: int
    surviving: int
    reason: str = ""

    @property
    def untouched(self) -> bool:
        return self.added == 0 or (self.surviving == self.added and not self.reason)


@dataclass
class Verdict:
    sha: str
    subject: str
    committed: str
    age_days: float
    age_ok: bool
    files: list[FileVerdict] = field(default_factory=list)
    error: str = ""

    @property
    def added(self) -> int:
        return sum(f.added for f in self.files)

    @property
    def surviving(self) -> int:
        return sum(f.surviving for f in self.files)

    @property
    def untouched(self) -> bool:
        return bool(self.files) and all(f.untouched for f in self.files)

    @property
    def qualifies(self) -> bool:
        return not self.error and self.age_ok and self.untouched

    @property
    def reason(self) -> str:
        if self.error:
            return self.error
        if not self.age_ok:
            return f"younger than {MONTHS_REQUIRED} months ({self.age_days:.0f} days)"
        if not self.files:
            return "no added line in any text file: nothing to check"
        touched = [f for f in self.files if not f.untouched]
        if touched:
            head = touched[0]
            detail = head.reason or f"{head.surviving} of {head.added} lines survive"
            return f"{len(touched)} file(s) touched since; {head.path}: {detail}"
        return "at least six months old, and no later commit touched a line it added"


def added_lines(repo: Path, sha: str, path: str) -> int:
    """How many lines ``sha`` added to ``path``, in ``sha``'s own tree."""
    diff = git(repo, "diff", "--unified=0", f"{sha}^", sha, "--", path)
    total = 0
    for line in diff.splitlines():
        match = HUNK.match(line)
        if match:
            total += int(match.group("count") or "1")
    return total


def surviving_lines(repo: Path, sha: str, path: str, tip: str) -> tuple[int, str]:
    """How many lines of ``path`` at ``tip`` are still blamed to ``sha``.

    A file that no longer exists at the tip is not a survivor: something removed
    or renamed it, which is exactly what disqualifies the control.
    """
    listing = git(repo, "ls-tree", "-r", "--name-only", tip, "--", path).strip()
    if not listing:
        return 0, "the file does not exist at the branch tip"
    blame = git(repo, "blame", "--line-porcelain", tip, "--", path)
    full = git(repo, "rev-parse", sha).strip()
    return sum(1 for line in blame.splitlines() if line.startswith(full + " ")), ""


def changed_text_files(repo: Path, sha: str) -> list[str]:
    """Files ``sha`` added to or modified, minus the ones it deleted and the
    binaries (a binary has no line a blame could follow)."""
    names = git(repo, "diff", "--name-only", "--diff-filter=AM", f"{sha}^", sha).splitlines()
    numstat = git(repo, "diff", "--numstat", f"{sha}^", sha).splitlines()
    binary = {row.split("\t")[-1] for row in numstat if row.startswith("-\t-\t")}
    return [name for name in names if name and name not in binary]


def qualify(repo: Path, sha: str, *, as_of: datetime, tip: str) -> Verdict:
    try:
        subject = git(repo, "log", "-1", "--format=%s", sha).strip()
        stamp = git(repo, "log", "-1", "--format=%cI", sha).strip()
    except RuntimeError as exc:
        return Verdict(sha, "", "", 0.0, False, error=str(exc))
    committed = datetime.fromisoformat(stamp)
    age_days = (as_of - committed).total_seconds() / 86400
    verdict = Verdict(
        sha=sha,
        subject=subject,
        committed=stamp,
        age_days=age_days,
        age_ok=age_days >= MONTHS_REQUIRED * DAYS_PER_MONTH,
    )
    try:
        if not _reachable(repo, sha, tip):
            verdict.error = f"not reachable from {tip}"
            return verdict
        for path in changed_text_files(repo, sha):
            added = added_lines(repo, sha, path)
            if added == 0:
                continue
            survived, reason = surviving_lines(repo, sha, path, tip)
            verdict.files.append(FileVerdict(path, added, survived, reason))
    except RuntimeError as exc:
        verdict.error = str(exc)
    return verdict


def _reachable(repo: Path, sha: str, tip: str) -> bool:
    result = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", sha, tip],
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def default_tip(repo: Path) -> str:
    for candidate in ("origin/HEAD", "origin/main", "origin/master", "main", "master", "HEAD"):
        probe = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", "--quiet", candidate],
            capture_output=True,
            check=False,
        )
        if probe.returncode == 0:
            return candidate
    return "HEAD"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", type=Path)
    parser.add_argument("shas", nargs="+")
    parser.add_argument("--as-of", default=None, help="measurement date (ISO); default now")
    parser.add_argument("--tip", default=None, help="branch tip to check against")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    as_of = (
        datetime.fromisoformat(args.as_of).replace(tzinfo=UTC) if args.as_of else datetime.now(UTC)
    )
    tip = args.tip or default_tip(args.repo)
    verdicts = [qualify(args.repo, sha, as_of=as_of, tip=tip) for sha in args.shas]

    if args.json:
        print(
            json.dumps(
                [
                    {
                        "sha": v.sha,
                        "subject": v.subject,
                        "committed": v.committed,
                        "age_days": round(v.age_days, 1),
                        "age_ok": v.age_ok,
                        "added": v.added,
                        "surviving": v.surviving,
                        "qualifies": v.qualifies,
                        "reason": v.reason,
                    }
                    for v in verdicts
                ],
                indent=2,
            )
        )
    else:
        for v in verdicts:
            mark = "QUALIFIES" if v.qualifies else "dropped  "
            print(
                f"{mark} {v.sha[:10]}  {v.age_days:6.0f}d  "
                f"{v.surviving}/{v.added} lines  {v.reason}"
            )
        kept = sum(1 for v in verdicts if v.qualifies)
        print(
            f"\n{kept} of {len(verdicts)} qualify as controls "
            f"(>= {MONTHS_REQUIRED} months, no later commit on {tip} touched a line they added)"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
