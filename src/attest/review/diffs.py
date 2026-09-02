"""Git diff acquisition and hunk-range parsing for anchor validation."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")


def norm_path(path: str) -> str:
    """Forward slashes, leading ./ segments removed (as a PREFIX — lstrip
    would eat leading dots of dotfiles like .github/ or .env)."""
    p = path.replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


@dataclass
class DiffInfo:
    text: str
    # file path -> list of (start, end) inclusive new-file line ranges per hunk
    hunks: dict[str, list[tuple[int, int]]] = field(default_factory=dict)

    def canonical_anchor(self, path: str, line: int) -> str | None:
        """Repository path the anchor names, or None. Proposer models often
        emit git-notation anchors (a/pkg/mod.py for pkg/mod.py). The exact
        path is tried FIRST — repos that genuinely contain a top-level a/ or
        b/ directory keep their literal keys — and only then is a single a/
        or b/ prefix stripped (once, never in a loop). Any `..` segment is
        rejected outright, never stripped-and-retried."""
        norm = norm_path(path)
        if ".." in norm.split("/"):
            return None
        candidates = [norm]
        if norm.startswith(("a/", "b/")):
            candidates.append(norm[2:])
        for candidate in candidates:
            if any(a <= line <= b for a, b in self.hunks.get(candidate, [])):
                return candidate
        return None

    def anchor_in_hunk(self, path: str, line: int) -> bool:
        return self.canonical_anchor(path, line) is not None

    @property
    def files(self) -> list[str]:
        return sorted(self.hunks)


def parse_diff(text: str) -> DiffInfo:
    """Hunk map for anchor validation. File headers are honored only inside a
    `diff --git` header block, never once a hunk has started: diff CONTENT is
    untrusted (an added line reading `++ b/evil.py` renders as `+++ b/evil.py`
    and would otherwise poison the map)."""
    hunks: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    in_header = False
    for line in text.splitlines():
        if line.startswith("diff --git "):
            in_header = True
            current = None
            continue
        m = _FILE_RE.match(line)
        if m and in_header:
            current = m.group(1).strip()
            hunks.setdefault(current, [])
            continue
        m = _HUNK_RE.match(line)
        if m and current is not None:
            in_header = False
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count > 0:
                hunks[current].append((start, start + count - 1))
    return DiffInfo(text=text, hunks={k: v for k, v in hunks.items() if v})


_SHA_RE = re.compile(r"[0-9a-f]{40}")


def resolve_merge_base(repo: Path, base: str, head: str) -> str | None:
    """Full merge-base SHA of ``base`` and ``head``, or None when unresolvable.

    A shallow clone that never fetched the base history returns None; the
    caller must DEFER rather than fall back to two-dot base-tip semantics.
    """
    proc = subprocess.run(
        ["git", "-C", str(repo), "merge-base", base, head],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return None
    sha = proc.stdout.strip()
    return sha if _SHA_RE.fullmatch(sha) else None


def git_diff(repo: Path, base: str | None = None) -> DiffInfo:
    """Working-tree diff against base (default HEAD, so staged changes are
    reviewed too — bare `git diff` would silently skip anything added to the
    index)."""
    args = ["git", "-C", str(repo), "diff", "--no-color", base or "HEAD"]
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()}")
    return parse_diff(proc.stdout)
