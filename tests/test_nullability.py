"""Yellow (b), the null/Optional class: the checker decides, not the model (D-151).

The level is a division of labour -- the model names a parameter, a line and a
caller; a deterministic checker decides whether the three premises hold; the
kernel writes the sentence from the premises that were verified. These tests fix
the division: a hypothesis whose premises all hold produces exactly one note, and
a hypothesis with a false premise produces **nothing**, whichever premise it is.

Every one of them fails on any implementation that trusts what the model said.
"""

from __future__ import annotations

from attest.github.presentation import nullability_line
from attest.review.nullability import (
    PREMISE_CALLER,
    PREMISE_OPTIONAL,
    PREMISE_UNGUARDED,
    Hypothesis,
    check,
    note_for,
)
from attest.review.output_contract import LEVEL_MARKERS
from attest.review.output_contract import check as contract_check

# `render` takes an Optional parameter, dereferences it, and `lookup` -- whose
# return annotation admits None -- supplies it. All three premises hold.
WIDGET = """
def render(widget: "Widget | None", scale: int = 1) -> str:
    label = widget.label
    return label * scale
"""

CALLER = """
from pkg.widget import render


def lookup(key: str) -> "Widget | None":
    return REGISTRY.get(key)


def show(key: str) -> str:
    found = lookup(key)
    return render(found)
"""

TREE = {"pkg/widget.py": WIDGET, "pkg/view.py": CALLER}

HYPOTHESIS = Hypothesis(
    path="pkg/widget.py",
    qualname="render",
    parameter="widget",
    access_line=3,
    caller_path="pkg/view.py",
    caller_line=11,
    argument_source="lookup",
)


def _verdicts(sources: dict[str, str], hypothesis: Hypothesis = HYPOTHESIS) -> dict[str, bool]:
    return {verdict.premise: verdict.holds for verdict in check(sources, hypothesis)}


def test_all_three_premises_hold_and_the_level_says_one_line() -> None:
    """The whole conjunction: the parameter admits None, the line dereferences it
    unguarded, and a caller passes a value from a function that returns None."""
    assert _verdicts(TREE) == {
        PREMISE_OPTIONAL: True,
        PREMISE_UNGUARDED: True,
        PREMISE_CALLER: True,
    }

    note = note_for(TREE, HYPOTHESIS)
    assert note is not None

    line = nullability_line(note)
    assert contract_check(line).admitted is True
    assert line.startswith(LEVEL_MARKERS["yellow"])
    assert "pkg/widget.py:3" in line and "pkg/view.py:11" in line
    assert "no None guard" in line


def test_a_guard_makes_premise_ii_false_and_the_level_says_nothing() -> None:
    """The owner's second RED: an early return on `is None` is a guard, so the
    dereference below it is not unguarded and the hypothesis is void."""
    guarded = """
def render(widget: "Widget | None", scale: int = 1) -> str:
    if widget is None:
        return ""
    label = widget.label
    return label * scale
"""
    sources = {**TREE, "pkg/widget.py": guarded}
    hypothesis = Hypothesis(**{**HYPOTHESIS.__dict__, "access_line": 5})

    verdicts = _verdicts(sources, hypothesis)
    assert verdicts[PREMISE_OPTIONAL] is True
    assert verdicts[PREMISE_UNGUARDED] is False
    assert note_for(sources, hypothesis) is None


def test_a_source_whose_return_annotation_excludes_none_makes_premise_iii_false() -> None:
    """The owner's third RED: the caller's argument comes from a function that
    cannot return None, so nothing can reach the dereference as None."""
    caller = CALLER.replace(
        'def lookup(key: str) -> "Widget | None":', 'def lookup(key: str) -> "Widget":'
    )
    sources = {**TREE, "pkg/view.py": caller}

    verdicts = _verdicts(sources)
    assert verdicts[PREMISE_OPTIONAL] is True
    assert verdicts[PREMISE_UNGUARDED] is True
    assert verdicts[PREMISE_CALLER] is False
    assert note_for(sources, HYPOTHESIS) is None


def test_a_parameter_that_does_not_admit_none_makes_premise_i_false() -> None:
    """A non-Optional annotation with no `None` default: premise (i) fails and the
    other two are never allowed to carry the claim on their own."""
    sources = {**TREE, "pkg/widget.py": WIDGET.replace('"Widget | None"', '"Widget"')}

    assert _verdicts(sources)[PREMISE_OPTIONAL] is False
    assert note_for(sources, HYPOTHESIS) is None


def test_a_hypothesis_naming_a_line_that_does_not_dereference_is_void() -> None:
    """The model may name any line at all; the checker reads the line."""
    hypothesis = Hypothesis(**{**HYPOTHESIS.__dict__, "access_line": 4})

    assert _verdicts(TREE, hypothesis)[PREMISE_UNGUARDED] is False
    assert note_for(TREE, hypothesis) is None


def test_a_hypothesis_naming_the_wrong_argument_source_is_void() -> None:
    """The checker verifies *which* function the argument came from, so a model
    that names a plausible-sounding one it did not read is refused."""
    hypothesis = Hypothesis(**{**HYPOTHESIS.__dict__, "argument_source": "fetch"})

    assert _verdicts(TREE, hypothesis)[PREMISE_CALLER] is False
    assert note_for(TREE, hypothesis) is None
