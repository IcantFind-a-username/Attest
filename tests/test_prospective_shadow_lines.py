"""The E-04 driver's line capture (owner instruction 7 of 2026-09-11): every
line a review would put in front of the author, rendered offline by the same
functions `run_ci` uses, from a review object and the ledger rows."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from prospective_shadow import _author_visible_lines  # noqa: E402

from attest.review.config import ReviewConfig  # noqa: E402


def _value_row(task_id: str) -> dict[str, object]:
    return {
        "kind": "value_observation_note",
        "task_id": task_id,
        "finding_id": "cafe1234ab",
        "policy_version": "attest.value-note.v2",
        "path": "pkg/money.py",
        "line": 41,
        "expression": "money.rate('EUR')",
        "base_kind": "value",
        "base_detail": "Decimal('1.05')",
        "head_kind": "value",
        "head_detail": "Decimal('1.10')",
        "head_runs": 3,
        "base_runs": 3,
        "pinned_values": ["Decimal('1.05')"],
        "specified_by": [],
        "drawer_reason": "intent: value change confirmed, intent unknown: nothing pins it",
        "candidate_id": "cafe1234ab",
    }


def _gate_row(task_id: str) -> dict[str, object]:
    return {
        "kind": "gate_shadow",
        "schema_version": "attest.gate-shadow.v2",
        "task_id": task_id,
        "finding_id": "feed5678cd",
        "path": "lib.py",
        "symbol": "widen",
        "reachability": "through_caller",
        "call_site": "cli.py:14",
        "caller": "main",
        "entry": "main([''])",
        "repeats": 3,
        "exception_type": "IndexError",
        "origin_line": 2,
        "runs_agreeing": True,
        "control_passed": True,
        "would_publish": True,
        "reason": "IndexError from the added line lib.py:2, reached from cli.py:14",
    }


def test_the_lines_are_rendered_only_under_the_switches(tmp_path: Path) -> None:
    review = SimpleNamespace(task_id="t1", published=[])
    rows = [_value_row("t1"), _gate_row("t1")]
    off = _author_visible_lines(
        tmp_path, review, rows, ReviewConfig(), base_sha="0" * 40, head_sha="1" * 40
    )
    assert off["red"] == [] and off["value"] == [] and off["gate"] == []
    on = _author_visible_lines(
        tmp_path,
        review,
        rows,
        ReviewConfig(value_notes_visible=True, gate_notes_visible=True),
        base_sha="0" * 40,
        head_sha="1" * 40,
    )
    assert len(on["value"]) == 1
    assert on["value"][0]["line"].startswith("[yellow] pkg/money.py:41 — ")
    assert on["value"][0]["note_id"] and on["value"][0]["drawer_reason"]
    assert len(on["gate"]) == 1
    assert on["gate"][0]["line"].startswith(
        "[yellow] cli.py:14 — new code at lib.py:2 raises IndexError on main(['']) "
    )
    # yellow (a) over a non-repository is silence, never an error
    assert on["impact"] == []


def _sample(*unit_ids: str) -> list[dict[str, object]]:
    return [{"unit_id": unit_id, "repository": unit_id.split("#")[0]} for unit_id in unit_ids]


def test_only_runs_the_named_units_in_the_frozen_order_and_names_the_rest() -> None:
    """Owner instruction of 2026-09-12 (run A): `--only` selects a subset of the
    frozen sample. The frozen order is kept -- the subset is filtered, never
    re-ordered -- and every pending unit the subset did not name is returned so
    the run records it as `skipped: not selected`, which keeps the sample's
    denominator readable: a unit nobody asked for is not a unit the run could
    not buy."""
    from prospective_shadow import _only_units, _plan_units

    samples = _sample("o/a#1", "o/b#2", "o/a#3", "o/c#4", "o/b#5")
    only = _only_units(" o/b#5, o/a#1 ,,")
    assert only == ("o/b#5", "o/a#1")

    pending, not_selected = _plan_units(samples, {"o/c#4"}, only=only)

    assert [row["unit_id"] for row in pending] == ["o/a#1", "o/b#5"]
    assert not_selected == ["o/b#2", "o/a#3"]

    # a unit already in the trials file is neither run nor named again
    again, left = _plan_units(samples, {"o/a#1", "o/c#4"}, only=only)
    assert [row["unit_id"] for row in again] == ["o/b#5"]
    assert left == ["o/b#2", "o/a#3"]

    # `--limit` applies after the selection, and the unselected are still named
    limited, still = _plan_units(samples, set(), only=only, limit=1)
    assert [row["unit_id"] for row in limited] == ["o/a#1"]
    assert still == ["o/b#2", "o/a#3", "o/c#4"]

    # without `--only` nothing is "not selected": the whole pending sample runs
    everything, none = _plan_units(samples, {"o/c#4"})
    assert [row["unit_id"] for row in everything] == ["o/a#1", "o/b#2", "o/a#3", "o/b#5"]
    assert none == []


def test_only_refuses_a_unit_the_sample_does_not_hold() -> None:
    """A typo in `--only` must not become a silent empty run that spends nothing
    and reports nothing: a name outside the frozen sample refuses before any
    unit starts."""
    import pytest
    from prospective_shadow import _plan_units

    with pytest.raises(SystemExit, match="not in the sample"):
        _plan_units(_sample("o/a#1"), set(), only=("o/a#1", "o/zzz#9"))
