"""Git diff acquisition and hunk-range parsing for anchor validation."""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
_FILE_RE = re.compile(r"^\+\+\+ b/(.+)$")


@dataclass
class DiffInfo:
    text: str
    # file path -> list of (start, end) inclusive new-file line ranges per hunk
    hunks: dict[str, list[tuple[int, int]]] = field(default_factory=dict)

    def anchor_in_hunk(self, path: str, line: int) -> bool:
        norm = path.replace("\\", "/").lstrip("./")
        for fpath, ranges in self.hunks.items():
            if fpath == norm and any(a <= line <= b for a, b in ranges):
                return True
        return False

    @property
    def files(self) -> list[str]:
        return sorted(self.hunks)


def parse_diff(text: str) -> DiffInfo:
    hunks: dict[str, list[tuple[int, int]]] = {}
    current: str | None = None
    for line in text.splitlines():
        m = _FILE_RE.match(line)
        if m:
            current = m.group(1).strip()
            hunks.setdefault(current, [])
            continue
        m = _HUNK_RE.match(line)
        if m and current is not None:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count > 0:
                hunks[current].append((start, start + count - 1))
    return DiffInfo(text=text, hunks={k: v for k, v in hunks.items() if v})


def git_diff(repo: Path, base: str | None = None) -> DiffInfo:
    """Working-tree diff against base (default: HEAD)."""
    args = ["git", "-C", str(repo), "diff", "--no-color"]
    if base:
        args.append(base)
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"git diff failed: {proc.stderr.strip()}")
    return parse_diff(proc.stdout)
