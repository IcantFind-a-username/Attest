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
