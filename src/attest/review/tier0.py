"""Tier-0 static corroboration: cheap deterministic signals near the anchor.

Runs available linters over changed files and collects diagnostics whose line
overlaps a finding's anchor (+/- slack). Signals are corroboration only — they
feed the T channel's capped LR; absence of tooling just means no signal.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

ANCHOR_SLACK = 2


@dataclass
class Tier0Signal:
    tool: str
    file: str
    line: int
    message: str


def run_ruff(repo: Path, files: list[str]) -> list[Tier0Signal]:
    exe = shutil.which("ruff")
    py_files = [f for f in files if f.endswith(".py") and (repo / f).is_file()]
    if not exe or not py_files:
        return []
    proc = subprocess.run(
        [exe, "check", "--output-format", "json", "--exit-zero", *py_files],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=repo,
    )
    try:
        diags = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    out = []
    for d in diags:
        try:
            out.append(
                Tier0Signal(
                    tool="ruff",
                    file=str(Path(d["filename"]).as_posix()),
                    line=int(d["location"]["row"]),
                    message=f"{d.get('code', '?')}: {d.get('message', '')}",
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def collect_signals(repo: Path, files: list[str], commands: list[str]) -> list[Tier0Signal]:
    signals: list[Tier0Signal] = []
    if "ruff" in commands:
        signals.extend(run_ruff(repo, files))
    return signals


def signals_near(signals: list[Tier0Signal], file: str, line: int) -> list[Tier0Signal]:
    norm = file.replace("\\", "/")
    return [
        s
        for s in signals
        if s.file.replace("\\", "/").endswith(norm) and abs(s.line - line) <= ANCHOR_SLACK
    ]
