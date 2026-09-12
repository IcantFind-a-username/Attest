"""D-240 (a): the conditions a change removed or altered, told to the probe search.

`boundary` mutations certified 1 of 13 on the forty: the change is `<=` becoming
`<` and the probe rarely tried the one input that sits on the boundary. The
facts are in the two sources and cost no model."""

from __future__ import annotations

from attest.review.boundary import changed_conditions

BASE = (
    "def clamp(x):\n"
    "    if x is None:\n"
    "        return 0\n"
    "    if x >= 13:\n"
    "        return 13\n"
    "    return x\n"
    "\n\n"
    "def other(y):\n"
    "    return y < 2\n"
)


def test_an_altered_comparison_names_both_spellings_and_the_boundary() -> None:
    head = BASE.replace("if x >= 13:", "if x > 13:")

    hints = changed_conditions(BASE, head, changed_lines=(4,))

    assert hints == (
        "in `clamp`: the comparison `x >= 13` became `x > 13` (the boundary is 13)",
    )


def test_a_removed_guard_is_named_with_what_it_did() -> None:
    head = BASE.replace("    if x is None:\n        return 0\n", "")

    hints = changed_conditions(BASE, head, changed_lines=(2, 3))

    assert hints == ("in `clamp`: the guard `x is None` was removed (it returned early)",)


def test_a_removed_raising_guard_names_the_exception() -> None:
    base = (
        "def total(items):\n    if not items:\n        raise ValueError('empty')\n"
        "    return sum(items)\n"
    )
    head = "def total(items):\n    return sum(items)\n"

    hints = changed_conditions(base, head, changed_lines=(2, 3))

    assert hints == ("in `total`: the guard `not items` was removed (it raised ValueError)",)


def test_untouched_definitions_and_unparsable_sources_say_nothing() -> None:
    head = BASE.replace("return y < 2", "return y < 3")
    # `other` is changed but the change is outside `changed_lines`
    assert changed_conditions(BASE, head, changed_lines=(4,)) == ()
    assert changed_conditions(BASE, head, changed_lines=(9,)) == (
        "in `other`: the comparison `y < 2` became `y < 3` (the boundary is 3)",
    )
    assert changed_conditions("def f(:", BASE, changed_lines=(1,)) == ()
    assert changed_conditions(BASE, BASE, changed_lines=(4,)) == ()
