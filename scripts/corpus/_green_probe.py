"""A throwaway probe for the green channel (owner instruction 4c, 2026-09-05).

This file exists only to make one pull request carry a structural finding, so
that the green channel posts one real comment and the display can be read. It is
deleted with the pull request that carries it. It claims nothing and nothing
imports it.
"""

from __future__ import annotations

import json
from pathlib import Path


class ProbeStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read_all(self, run_id: str | None = None) -> list[dict]:
        if not self.path.is_file():
            return []
        entries: list[dict] = []
        for row in self.path.read_text(encoding="utf-8").splitlines():
            try:
                parsed = json.loads(row)
                entry = dict(parsed)
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
            if run_id is None or entry.get("run_id") == run_id:
                entries.append(entry)
        return entries
