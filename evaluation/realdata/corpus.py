"""Build a labeled corpus of real diffs from real repository history.

Ground truth comes from history itself, not from judgement calls:

* A **positive** case is the reverse of a real single-file bug-fix commit —
  the diff that puts the bug back. Its new side is the parent (buggy) blob, so
  the `+` lines are exactly the lines the fix had to change: the true anchor
  set. This is the "reintroduce a fixed crash" scenario, taken from real
  history instead of hand-planted.
* A **negative** case is a real docs/typo/formatting/refactor commit applied
  forwards. Nothing in it should clear an evidence bar.

Nothing here imports the model path; the corpus is pure git.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

FIX_RE = re.compile(
    r"\b(fix(e[sd])?|bug|crash|regression|traceback|exception|broken|"
    r"incorrect|wrong|fail(s|ed|ure)?)\b",
    re.IGNORECASE,
)
CLEAN_RE = re.compile(
    r"\b(docs?|typos?|comments?|readme|changelog|refactor|rename|format(ting)?|"
    r"style|cleanup|lint|whitespace|spelling)\b",
    re.IGNORECASE,
)
# a "fix" message that is really a docs/test-only change is not a defect fix
NOT_A_FIX_RE = re.compile(r"\b(typos?|spelling|changelog|docs?)\b", re.IGNORECASE)

MAX_CHANGED_LINES = 40


@dataclass
class Case:
    """One real diff plus what history says is true about it."""

    repo: str
    label: str  # "positive" (bug reintroduced) | "negative" (clean change)
    fix_sha: str
    parent_sha: str
    new_rev: str  # revision the diff's NEW side corresponds to
    subject: str
    path: str
    diff_text: str
    # new-file line numbers that the fix commit had to touch; for a positive
    # case these are the buggy lines a correct finding should anchor to
    true_lines: list[int] = field(default_factory=list)
    # true_lines is empty when the fix was a pure insertion: the bug is an
    # OMISSION, and no line of the buggy file carries it
    omission: bool = False


def _git(repo: Path, *args: str, timeout: int = 120) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def _plus_lines(diff_text: str) -> list[int]:
    """New-file line numbers of added lines, tracked through the hunk headers."""
    out: list[int] = []
    lineno = 0
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    in_hunk = False
    for line in diff_text.splitlines():
        m = hunk_re.match(line)
        if m:
            lineno = int(m.group(1))
            in_hunk = True
            continue
        if not in_hunk:
            continue
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            out.append(lineno)
            lineno += 1
        elif line.startswith("-") or line.startswith("\\"):
            continue
        else:  # context line (leading space, or an empty trailing line)
            lineno += 1
    return out


def _changed_line_count(diff_text: str) -> int:
    return sum(
        1
        for line in diff_text.splitlines()
        if (line.startswith(("+", "-")) and not line.startswith(("+++", "---")))
    )


def _candidates(repo: Path, limit: int) -> list[tuple[str, str, list[str]]]:
    """(sha, subject, files) for non-merge commits touching exactly one .py file."""
    raw = _git(
        repo,
        "log",
        "--no-merges",
        f"-n{limit}",
        "--pretty=format:\x01%H\x02%s",
        "--name-only",
    )
    out: list[tuple[str, str, list[str]]] = []
    for block in raw.split("\x01"):
        if not block.strip():
            continue
        head, _, rest = block.partition("\n")
        sha, _, subject = head.partition("\x02")
        files = [f for f in rest.splitlines() if f.strip()]
        out.append((sha.strip(), subject.strip(), files))
    return out


def build_cases(repo: Path, scan: int = 4000, per_class: int = 40) -> list[Case]:
    name = repo.name
    positives: list[Case] = []
    negatives: list[Case] = []
    for sha, subject, files in _candidates(repo, scan):
        if len(positives) >= per_class and len(negatives) >= per_class:
            break
        py = [f for f in files if f.endswith(".py")]
        if len(files) != 1 or len(py) != 1:
            continue
        path = py[0]
        if "test" in path.lower():  # a fix to a test file is not a product defect
            continue
        is_fix = bool(FIX_RE.search(subject)) and not NOT_A_FIX_RE.search(subject)
        is_clean = bool(CLEAN_RE.search(subject)) and not FIX_RE.search(subject)
        if not (is_fix or is_clean):
            continue
        if is_fix and len(positives) >= per_class:
            continue
        if is_clean and len(negatives) >= per_class:
            continue
        parents = _git(repo, "rev-list", "--parents", "-n1", sha).split()
        if len(parents) != 2:
            continue
        parent = parents[1]
        # positive: diff FROM the fix TO its parent = the bug going back in
        a, b = (sha, parent) if is_fix else (parent, sha)
        try:
            diff_text = _git(repo, "diff", "--no-color", a, b, "--", path)
        except (RuntimeError, subprocess.TimeoutExpired):
            continue
        if not diff_text.strip() or _changed_line_count(diff_text) > MAX_CHANGED_LINES:
            continue
        plus = _plus_lines(diff_text)
        case = Case(
            repo=name,
            label="positive" if is_fix else "negative",
            fix_sha=sha,
            parent_sha=parent,
            new_rev=b,
            subject=subject[:120],
            path=path,
            diff_text=diff_text,
            true_lines=plus,
            omission=is_fix and not plus,
        )
        (positives if is_fix else negatives).append(case)
    return positives + negatives
