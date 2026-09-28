"""The mutation-recall driver's `--only` (D-236 re-measurement): named cases in the
frozen order, every other pending case recorded as not selected."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from mutation_recall import _only_units  # noqa: E402
from prospective_shadow import _plan_units  # noqa: E402


def _sample(*ids: str) -> list[dict[str, object]]:
    return [{"unit_id": unit_id} for unit_id in ids]


def test_only_parses_the_comma_list_and_keeps_the_frozen_order() -> None:
    assert _only_units(" b--forward, a--forward ,,") == ("b--forward", "a--forward")
    assert _only_units("") == ()
    sample = _sample("a--forward", "b--forward", "c--forward")

    pending, not_selected = _plan_units(sample, set(), only=_only_units("c--forward,a--forward"))

    assert [row["unit_id"] for row in pending] == ["a--forward", "c--forward"]  # frozen order
    assert not_selected == ["b--forward"]


def test_only_refuses_a_case_the_sample_does_not_hold() -> None:
    with pytest.raises(SystemExit):
        _plan_units(_sample("a--forward"), set(), only=("nope--forward",))


# --- a certified case is one whose receipt sits on the mutation (D-250) ----------

from mutation_recall import classify  # noqa: E402


def _certified_rows(finding: str, path: str, changed: tuple[int, ...]) -> list[dict[str, object]]:
    return [
        {
            "kind": "verification",
            "finding_id": finding,
            "outcome": "reproduced",
            "evidence_class": "regression_reproduced",
            "reason": "head FAIL 3/3, base PASS 3/3",
            "intent": {"path": path, "changed_lines": list(changed)},
        },
        {"kind": "certification", "finding_id": finding, "outcome": "accepted",
         "reason": "accepted"},
    ]


def test_a_receipt_on_the_mutation_hunk_is_a_hit() -> None:
    rows = _certified_rows("f1", "src/pkg/target.py", (50, 51, 52, 53, 54, 55))
    klass, why = classify(rows, "", site=("src/pkg/target.py", 53))
    assert klass == "certified"
    assert why == "accepted"


def test_a_receipt_anchored_off_the_mutation_site_is_not_a_hit() -> None:
    """The classifier counted a case as certified when *any* accepted receipt
    existed in it, wherever that receipt sat. A receipt on another file, or on
    another hunk of the same file, is a certification of something else."""
    rows = _certified_rows("f1", "src/pkg/other.py", (10, 11, 12))
    klass, why = classify(rows, "", site=("src/pkg/target.py", 53))
    assert klass == "certified elsewhere"
    assert "src/pkg/other.py:10-12" in why and "src/pkg/target.py:53" in why

    same_file = _certified_rows("f2", "src/pkg/target.py", (200, 201, 202))
    klass, _why = classify(same_file, "", site=("src/pkg/target.py", 53))
    assert klass == "certified elsewhere"


def test_without_a_site_the_old_reading_stands() -> None:
    rows = _certified_rows("f1", "src/pkg/other.py", (10, 11, 12))
    assert classify(rows, "")[0] == "certified"
