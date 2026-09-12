# ruff: noqa: E501 - the fixture is a markdown table and its rows are wide
"""The receipts page reads a verdict typed on a re-rendered line.

A line whose level changed between §1 and §1b (red → value) is adjudicated as
it is shown now, so §1's verdict is deliberately not carried; the §1b row must
be able to carry the three columns itself, or such a line stays pending for
ever.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "acceptance" / "receipts_page.py"

REPORT = """# Lines on real pull requests, a fixture

## 1. Every line, verbatim

| # | run | pull request | level | the line | what stands behind it | useful | true but useless | wrong |
|---|---|---|---|---|---|---|---|---|
| 1 | run X | `o/r#1` | red | [red] a.py:1 — claim — receipt 0123456789ab | receipt 0123456789ab | x | | |
| 2 | run X | `o/r#2` | value | [yellow] b.py:2 — for f(), base 1 head 2 — note abcdefabcdef | note abcdefabcdef | | x | |

## 1b. The same lines under a later rule

| # | run | pull request | level before → after | the line, as it would be shown now | what moved it | useful | true but useless | wrong |
|---|---|---|---|---|---|---|---|---|
| 1 | run X | `o/r#1` | red → value | [yellow] a.py:1 — for g(), base None head raises — note fedcbafedcba | moved | | x | |
| 2 | run X | `o/r#2` | value | [yellow] b.py:2 — for f(), base 1 head 2 — note abcdefabcdef | unchanged |

## 2. One row per pull request

| pull request | cand | elig | att | cert | drawers | red | value | gate | yellow (a) | units read | spend |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `o/r#1` | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 1 of 1 | $0.01 |
| `o/r#2` | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 1 of 1 | $0.01 |
"""


def _load():
    spec = importlib.util.spec_from_file_location("receipts_page", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(module)
    return module


def test_a_verdict_typed_on_the_re_rendered_line_is_read_and_the_old_one_is_not(tmp_path) -> None:
    module = _load()
    path = tmp_path / "2026-01-01-lines-on-real-prs.md"
    path.write_text(REPORT, encoding="utf-8")
    report = module.parse_report(path)
    by_id = {line.evidence_id: line for line in report.lines}
    # red → value: §1 said useful against the red wording; §1b says true-but-useless as shown now
    assert by_id["fedcbafedcba"].verdict() == "true but not actionable"
    # unchanged level: §1's verdict carries by id
    assert by_id["abcdefabcdef"].verdict() == "true but not actionable"
