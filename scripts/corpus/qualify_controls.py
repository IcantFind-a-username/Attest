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
from collections import Counter
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
    truncated: bool = False  # blame stopped at the first disqualifying file

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


# Blaming a path at a tip is the cost of this whole screen, and the answer does
# not depend on which commit is being judged: it is the same file at the same
# revision. Screening a population re-asks it constantly -- the commits that
# touch a repository's hot files are exactly the ones that keep coming up -- so
# the per-commit line counts are memoised per (repository, tip, path).
_BLAME_CACHE: dict[tuple[str, str, str], Counter[str]] = {}


def _blamed_line_counts(repo: Path, path: str, tip: str) -> Counter[str] | None:
    """Commit -> number of lines of ``path`` at ``tip`` blamed to it, or None
    when the path is gone at the tip.

    ``--incremental`` rather than ``--line-porcelain``: the same attribution,
    one header line per contiguous run instead of per line, and none of the file
    content. On a three-thousand-line module with three thousand commits of
    history that is the difference between megabytes of output and kilobytes.
    """
    key = (str(repo), tip, path)
    cached = _BLAME_CACHE.get(key)
    if cached is not None:
        return cached
    listing = git(repo, "ls-tree", "-r", "--name-only", tip, "--", path).strip()
    if not listing:
        return None
    counts: Counter[str] = Counter()
    for line in git(repo, "blame", "--incremental", tip, "--", path).splitlines():
        head = line.split(" ")
        if len(head) == 4 and len(head[0]) == 40 and all(c in "0123456789abcdef" for c in head[0]):
            counts[head[0]] += int(head[3])
    _BLAME_CACHE[key] = counts
    return counts


def _later_commits_touching(repo: Path, sha: str, path: str, tip: str) -> int:
    """How many commits between ``sha`` and ``tip`` touched ``path`` at all.

    Zero is the cheap sufficient condition for "untouched": if nothing later
    changed the file, nothing later changed a line the commit added, and no
    blame is needed. On cold code -- which is what this rule selects -- that is
    the common case, and blame is the entire cost of the screen.
    """
    out = git(repo, "rev-list", "--count", f"{sha}..{tip}", "--", path).strip()
    return int(out or "0")


def surviving_lines(
    repo: Path, sha: str, path: str, tip: str, *, added: int | None = None
) -> tuple[int, str]:
    """How many lines of ``path`` at ``tip`` are still blamed to ``sha``.

    A file that no longer exists at the tip is not a survivor: something removed
    or renamed it, which is exactly what disqualifies the control. With ``added``
    given, a file no later commit touched at all short-circuits: every added line
    necessarily survives, and the expensive blame is skipped.
    """
    if added is not None and _later_commits_touching(repo, sha, path, tip) == 0:
        listing = git(repo, "ls-tree", "-r", "--name-only", tip, "--", path).strip()
        if not listing:
            return 0, "the file does not exist at the branch tip"
        return added, ""
    counts = _blamed_line_counts(repo, path, tip)
    if counts is None:
        return 0, "the file does not exist at the branch tip"
    full = git(repo, "rev-parse", sha).strip()
    return counts[full], ""


def changed_text_files(repo: Path, sha: str) -> list[str]:
    """Files ``sha`` added to or modified, minus the ones it deleted and the
    binaries (a binary has no line a blame could follow)."""
    names = git(repo, "diff", "--name-only", "--diff-filter=AM", f"{sha}^", sha).splitlines()
    numstat = git(repo, "diff", "--numstat", f"{sha}^", sha).splitlines()
    binary = {row.split("\t")[-1] for row in numstat if row.startswith("-\t-\t")}
    return [name for name in names if name and name not in binary]


def qualify(
    repo: Path, sha: str, *, as_of: datetime, tip: str, early_stop: bool = False
) -> Verdict:
    """``early_stop`` stops blaming after the first file that disqualifies the
    commit. The verdict is identical -- one touched file is enough -- but the
    per-file detail is then partial, and the verdict says so in ``truncated``.
    It exists because blame dominates the cost of screening a large population."""
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
        # Two passes, same verdict, very different cost. The cheap pass answers
        # two questions with git plumbing alone: is the file still at the tip
        # (gone means disqualified outright), and did any later commit touch it
        # (none means every added line necessarily survives). Only a file that is
        # both still present and touched afterwards needs a blame, and on an
        # actively maintained repository a deleted changelog disqualifies the
        # commit before a single blame is paid for.
        needs_blame: list[tuple[str, int]] = []
        disqualified = False
        for path in changed_text_files(repo, sha):
            added = added_lines(repo, sha, path)
            if added == 0:
                continue
            if not git(repo, "ls-tree", "-r", "--name-only", tip, "--", path).strip():
                verdict.files.append(
                    FileVerdict(path, added, 0, "the file does not exist at the branch tip")
                )
                disqualified = True
                if early_stop:
                    verdict.truncated = True
                    break
                continue
            if _later_commits_touching(repo, sha, path, tip) == 0:
                verdict.files.append(FileVerdict(path, added, added))
                continue
            needs_blame.append((path, added))
        if not (disqualified and early_stop):
            # smallest first: a cheap blame that disqualifies saves an expensive one
            needs_blame.sort(key=lambda item: item[1])
            for path, added in needs_blame:
                survived, reason = surviving_lines(repo, sha, path, tip)
                file_verdict = FileVerdict(path, added, survived, reason)
                verdict.files.append(file_verdict)
                if early_stop and not file_verdict.untouched:
                    verdict.truncated = True
                    break
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
