"""Yellow (a), the impact scope (D-143), narrowed and published (D-145).

The two the owner named for D-143 are
`test_a_changed_signature_with_an_untested_caller_produces_one_note` and
`test_a_body_change_whose_callers_are_all_tested_is_silent`. D-145 adds the
conjunction -- the interface moved **and** a caller is named by no test -- so
`test_an_interface_change_whose_callers_are_all_tested_is_silent` and
`test_an_untested_caller_without_an_interface_change_is_silent` fail on the
D-143 implementation, which spoke on either half alone. The rest hold the
abstentions, which are the reason this level may speak without a model.
"""

from __future__ import annotations

from pathlib import Path

from attest.github.presentation import (
    IMPACT_HEADING,
    impact_comments,
    impact_line,
    render_complete,
)
from attest.review.impact import (
    CONDITION_ARITY,
    CONDITION_RAISE_OR_RETURNS,
    CONDITION_SIGNATURE,
    ENABLED_CONDITIONS,
    MAX_NOTES,
    build_call_graph,
    changed_functions,
    notes_for_change,
    read_tree,
)
from attest.review.output_contract import LEVEL_MARKERS, silence_line
from attest.review.output_contract import check as contract_check

# One library function, one tested caller, one untested caller, one test.
BASE_PRICING = '''
def quote(items):
    """Price a basket."""
    return sum(item.price for item in items)
'''

HEAD_PRICING_SIGNATURE = '''
def quote(items, currency):
    """Price a basket."""
    return sum(item.price for item in items)
'''

HEAD_PRICING_BODY = '''
def quote(items):
    """Price a basket."""
    total = 0
    for item in items:
        total += item.price
    return total
'''

CHECKOUT = """
from pricing import quote


def checkout(basket):
    return quote(basket)
"""

REPORTING = """
from pricing import quote


def nightly_report(basket):
    return quote(basket)
"""

TEST_CHECKOUT = """
from checkout import checkout


def test_checkout_totals():
    assert checkout([]) == 0
"""


def _tree(head_pricing: str, *, with_untested_caller: bool = True) -> dict[str, str]:
    sources = {
        "pricing.py": head_pricing,
        "checkout.py": CHECKOUT,
        "tests/test_checkout.py": TEST_CHECKOUT,
    }
    if with_untested_caller:
        sources["reporting.py"] = REPORTING
    return sources


def _notes(
    head_pricing: str,
    changed_lines: set[int],
    *,
    conditions: tuple[str, ...] = ENABLED_CONDITIONS,
    **kwargs: bool,
):
    sources = _tree(head_pricing, **kwargs)
    graph = build_call_graph(sources)
    changed = changed_functions(
        path="pricing.py",
        head_source=head_pricing,
        base_source=BASE_PRICING,
        changed_lines=changed_lines,
    )
    return notes_for_change(graph, changed, conditions=conditions), graph


# --- the two the level is defined by ----------------------------------------


def test_a_changed_signature_with_an_untested_caller_produces_one_note() -> None:
    """D-150 re-ranked this fixture and the re-ranking is the point: `quote`
    gained a required parameter and **both** call sites still pass one, so the
    decidable claim (a3) outranks the coverage-proxy claim (a1) it used to
    make. The a1 half is still true and still asserted here."""
    notes, _ = _notes(HEAD_PRICING_SIGNATURE, {2})

    assert len(notes) == 1
    note = notes[0]
    assert note.condition == CONDITION_ARITY
    assert note.changed.signature_changed is True
    assert note.changed.added_required_parameter is True
    assert {caller.site.path for caller in note.callers} == {"checkout.py", "reporting.py"}
    assert [caller.site.path for caller in note.untested] == ["reporting.py"]

    line = impact_line(note)
    assert contract_check(line).admitted is True
    assert line.startswith(LEVEL_MARKERS["yellow"])
    assert "pricing.py:2" in line
    assert "gained a required parameter" in line


def test_a_body_change_whose_callers_are_all_tested_is_silent() -> None:
    notes, _ = _notes(HEAD_PRICING_BODY, {4, 5, 6}, with_untested_caller=False)

    assert notes == ()


# --- the abstentions ---------------------------------------------------------


def test_an_untested_caller_without_an_interface_change_is_silent() -> None:
    """D-145's first half. Under D-143 this spoke; a coverage remark under an
    unchanged interface is not a claim this level has standing to make."""

    notes, _ = _notes(HEAD_PRICING_BODY, {4, 5, 6})

    assert notes == ()


def test_an_interface_change_whose_callers_are_all_tested_is_silent() -> None:
    """D-145's second half, still true of a1 and a2. Under D-143 a changed
    signature spoke on its own; a suite that names every caller will report the
    breakage itself.

    a3 is excluded here on purpose: it does not rest on coverage at all, so a
    tested caller does not silence it, and this fixture's call really is broken.
    That is `test_a3_...` below."""

    notes, _ = _notes(
        HEAD_PRICING_SIGNATURE,
        {2},
        with_untested_caller=False,
        conditions=(CONDITION_SIGNATURE, CONDITION_RAISE_OR_RETURNS),
    )

    assert notes == ()


def test_an_ambiguous_name_produces_no_claim() -> None:
    """Two `quote` definitions: a call site cannot be attributed to either."""

    sources = _tree(HEAD_PRICING_SIGNATURE)
    sources["legacy/pricing.py"] = BASE_PRICING
    graph = build_call_graph(sources)
    changed = changed_functions(
        path="pricing.py",
        head_source=HEAD_PRICING_SIGNATURE,
        base_source=BASE_PRICING,
        changed_lines={2},
    )
    assert changed  # the function did change
    assert notes_for_change(graph, changed) == ()


def test_a_function_with_no_caller_produces_no_claim() -> None:
    head = HEAD_PRICING_SIGNATURE
    graph = build_call_graph({"pricing.py": head})
    changed = changed_functions(
        path="pricing.py", head_source=head, base_source=BASE_PRICING, changed_lines={2}
    )
    assert notes_for_change(graph, changed) == ()


def test_new_code_is_not_this_levels_claim() -> None:
    """A function with no counterpart in the base is the gate level's business."""

    head = BASE_PRICING + "\n\ndef discount(items):\n    return 0\n"
    changed = changed_functions(
        path="pricing.py",
        head_source=head,
        base_source=BASE_PRICING,
        changed_lines={6, 7},
    )
    assert [c.definition.name for c in changed] == []


def test_a_test_that_names_the_caller_at_one_hop_counts_as_named() -> None:
    notes, _ = _notes(HEAD_PRICING_SIGNATURE, {2})
    tested = [c for c in notes[0].callers if c.named_by_test]
    assert [c.site.path for c in tested] == ["checkout.py"]
    assert tested[0].hops_to_test == 1


def test_a_return_annotation_change_is_an_interface_change() -> None:
    base = "def quote(items):\n    return 0\n"
    head = "def quote(items) -> int:\n    return 0\n"
    sources = {"pricing.py": head, "reporting.py": REPORTING}
    graph = build_call_graph(sources)
    changed = changed_functions(
        path="pricing.py", head_source=head, base_source=base, changed_lines={1}
    )
    notes = notes_for_change(graph, changed)
    assert len(notes) == 1
    assert notes[0].changed.returns_changed is True
    assert "return annotation" in impact_line(notes[0])


def test_at_most_two_notes_reach_one_pull_request() -> None:
    base = "".join(f"def f{i}(a):\n    return a\n\n" for i in range(5))
    head = "".join(f"def f{i}(a, b):\n    return a\n\n" for i in range(5))
    callers = "".join(f"def call{i}():\n    return f{i}(1, 2)\n\n" for i in range(5))
    graph = build_call_graph({"lib.py": head, "app.py": callers})
    changed = changed_functions(
        path="lib.py",
        head_source=head,
        base_source=base,
        changed_lines=set(range(1, 20)),
    )
    assert len(changed) == 5
    notes = notes_for_change(graph, changed)
    assert len(notes) == MAX_NOTES == 2
    comments = impact_comments(list(notes))
    assert len(comments) == 2
    body = str(comments[0]["body"])
    assert "named by no test" in body
    assert "never *not covered*" in body  # the honesty clause is in the comment
    assert contract_check(body.splitlines()[1]).admitted is True


def test_reading_a_tree_skips_the_directories_that_are_not_source(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "b.py").write_text("def g():\n    return 1\n", encoding="utf-8")
    sources = read_tree(tmp_path)
    assert set(sources) == {"pkg/a.py"}


def test_a_call_inside_a_constructor_is_named_by_a_test_that_names_the_class() -> None:
    """Nothing outside a class writes `__init__`, so asking whether a test names
    it answers "no" for every constructor ever written. The addressable name of
    a dunder is its class."""

    head = "def quote(items, currency):\n    return 0\n"
    base = "def quote(items):\n    return 0\n"
    library = {
        "pricing.py": head,
        "basket.py": "from pricing import quote\n\n\nclass Basket:\n"
        "    def __init__(self, items):\n        self.total = quote(items, 'usd')\n",
        "tests/test_basket.py": "from basket import Basket\n\n\n"
        "def test_basket_totals():\n    assert Basket([]).total == 0\n",
    }
    graph = build_call_graph(library)
    changed = changed_functions(
        path="pricing.py", head_source=head, base_source=base, changed_lines={1}
    )
    notes = notes_for_change(graph, changed)
    # the constructor is the only call site and it is *not* untested, so under
    # D-145's conjunction the level has nothing to say -- which is the point:
    # before the dunder fix this same tree produced a note about a class ten
    # tests instantiate
    assert notes == ()

    library["reporting.py"] = (
        "from pricing import quote\n\n\ndef nightly():\n    return quote([], 'usd')\n"
    )
    notes = notes_for_change(build_call_graph(library), changed)
    assert len(notes) == 1
    assert [c.site.path for c in notes[0].untested] == ["reporting.py"]
    assert "1 of them named by no test" in impact_line(notes[0])


# --- D-145: the level is author-visible, and its silence is silence -----------


def test_a_published_yellow_comment_is_one_contract_line() -> None:
    """The owner's RED for D-145: what reaches a pull request is one line in the
    D-142 shape -- marker, coordinate, one sentence of fact, evidence."""

    notes, _ = _notes(HEAD_PRICING_SIGNATURE, {2})
    comments = impact_comments(list(notes))

    assert len(comments) == 1
    comment = comments[0]
    assert comment["path"] == "pricing.py"
    assert comment["line"] == 2
    body = str(comment["body"]).splitlines()
    assert body[0] == "<!-- attest:impact:pricing.py:2 -->"
    claim = body[1]
    assert claim.startswith(LEVEL_MARKERS["yellow"])
    assert contract_check(claim).admitted is True
    assert len([line for line in body if LEVEL_MARKERS["yellow"] in line]) == 1


def test_a_silent_impact_level_produces_no_yellow_line() -> None:
    """The owner's second RED: when the level says nothing, nothing about it
    reaches the author -- not a heading, not an empty section, not a marker."""

    # A body change whose every caller a test names: silent under all three
    # conditions, which is what a silence test needs. (The signature fixture is
    # no longer silent -- D-150's a3 sees that its callers pass too few
    # arguments -- and a silence test must not depend on which condition is on.)
    silent, _ = _notes(HEAD_PRICING_BODY, {4, 5, 6}, with_untested_caller=False)
    assert silent == ()
    assert impact_comments(list(silent)) == []

    body = render_complete([], 0.0125, 3.2, units=(4, 9), impact=list(silent))
    assert LEVEL_MARKERS["yellow"] not in body
    assert body == silence_line(units_read=4, units_planned=9, spend_usd=0.0125, elapsed_s=3.2)


def test_the_summary_carries_the_yellow_line_when_the_level_speaks() -> None:
    notes, _ = _notes(HEAD_PRICING_SIGNATURE, {2})

    body = render_complete([], 0.0125, 3.2, units=(4, 9), impact=list(notes))

    lines = body.splitlines()
    assert lines[0] == "Review complete."
    assert IMPACT_HEADING in lines
    yellow = [line for line in lines if LEVEL_MARKERS["yellow"] in line]
    assert len(yellow) == 1
    assert contract_check(yellow[0].removeprefix("- ")).admitted is True
    # yellow never borrows red's words
    assert "Verified" not in body


def test_the_impact_channel_refuses_anything_that_is_not_an_impact_note() -> None:
    class Impostor:
        pass

    for bad in ([Impostor()], [object()]):
        try:
            impact_comments(bad)  # type: ignore[arg-type]
        except TypeError:
            continue
        raise AssertionError("the impact channel accepted a foreign value")


# --- D-147: an inline comment is placed on a line the diff changed -----------


def test_a_yellow_comment_is_anchored_on_a_line_the_diff_changed() -> None:
    """The `def` line is the function's identity and is what the sentence names;
    it is usually only *context* in the hunk, and GitHub refuses a review comment
    on a line the diff does not carry -- refusing the whole review with it."""

    notes, _ = _notes(HEAD_PRICING_SIGNATURE, {2})

    note = notes[0]
    assert note.changed.definition.line == 2
    assert note.changed.anchor_line == 2  # here the def line *is* the changed one

    # a change one line further in: the sentence still names the def, the
    # comment moves to the line that changed
    body = "def quote(items):\n    total = 0\n    return total\n"
    changed = changed_functions(
        path="pricing.py",
        head_source=body,
        base_source="def quote(items):\n    return 0\n",
        changed_lines={2},
    )
    assert changed[0].definition.line == 1
    assert changed[0].anchor_line == 2


def test_a_comment_whose_anchor_the_diff_does_not_carry_is_not_posted() -> None:
    notes, _ = _notes(HEAD_PRICING_SIGNATURE, {2})

    assert impact_comments(list(notes), {"pricing.py": {2}}) != []
    # the same note, against a diff that does not carry line 2
    assert impact_comments(list(notes), {"pricing.py": {99}}) == []
    assert impact_comments(list(notes), {"other.py": {2}}) == []
    # no diff supplied: nothing is filtered, because a filter with no data is a
    # silent drop
    assert impact_comments(list(notes), None) != []


# --- D-150: the three conditions, one test each -----------------------------
#
# Every one of these fails on the D-145 implementation, which had a single
# condition (`signature or return annotation` and an untested caller) and no
# notion of a raise or of call arity.


def _one_note(head: str, base: str, *, path: str = "pkg/mod.py", extra: dict | None = None):
    """The single note a two-file tree produces for every changed line of `path`."""
    sources = {path: head, **(extra or {})}
    graph = build_call_graph(sources)
    changed = changed_functions(
        path=path,
        head_source=head,
        base_source=base,
        changed_lines=range(1, head.count("\n") + 2),
    )
    notes = notes_for_change(graph, changed, limit=10)
    return notes


def test_a1_a_moved_signature_with_an_untested_caller_still_speaks() -> None:
    """D-145's condition, retained verbatim: it is the one with a measured
    history and the widening may not disturb it."""
    head = "def widget(a, b):\n    return a\n\n\ndef caller():\n    return widget(1, 2)\n"
    base = "def widget(a):\n    return a\n\n\ndef caller():\n    return widget(1)\n"

    notes = _one_note(head, base)

    assert [n.condition for n in notes] == [CONDITION_SIGNATURE]
    assert "changed signature" in impact_line(notes[0])


def test_a2_a_new_exception_type_with_an_untested_caller_speaks() -> None:
    """The signature is byte-identical and the return annotation never moves;
    only the raised type is new. D-145 was silent here."""
    head = (
        "def widget(a):\n"
        "    if a:\n"
        "        raise KeyError(a)\n"
        "    return a\n"
        "\n\n"
        "def caller():\n"
        "    return widget(1)\n"
    )
    base = "def widget(a):\n    return a\n\n\ndef caller():\n    return widget(1)\n"

    notes = _one_note(head, base)

    assert [n.condition for n in notes] == [CONDITION_RAISE_OR_RETURNS]
    assert "raises an exception type the base did not" in impact_line(notes[0])


def test_a2_is_silent_when_the_raise_was_already_there() -> None:
    """A raise the base already had is not a new obligation for any caller."""
    head = "def widget(a):\n    raise KeyError(a)\n\n\ndef caller():\n    return widget(1)\n"
    base = "def widget(a):\n    raise KeyError(a)  # unchanged\n\n\ndef caller():\n    return widget(1)\n"

    assert _one_note(head, base) == ()


def test_a3_an_added_parameter_that_breaks_a_call_speaks_even_when_a_test_names_it() -> None:
    """a3 rests on no coverage proxy: the call is wrong whether or not a test
    names the caller, so a caller a test names is still reported."""
    head = "def widget(a, b):\n    return a + b\n"
    base = "def widget(a):\n    return a\n"
    caller = "from pkg.mod import widget\n\n\ndef test_widget():\n    assert widget(1)\n"

    notes = _one_note(head, base, extra={"tests/test_mod.py": caller})

    assert [n.condition for n in notes] == [CONDITION_ARITY]
    line = impact_line(notes[0])
    assert "gained a required parameter" in line
    assert "tests/test_mod.py:5" in line


def test_a3_abstains_when_the_call_could_be_supplying_the_parameter() -> None:
    """`*args`, `**kwargs` and any keyword argument can carry the new parameter,
    so the arity check cannot decide and says nothing."""
    head = "def widget(a, b):\n    return a\n"
    base = "def widget(a):\n    return a\n"
    caller = "from pkg.mod import widget\n\n\ndef test_widget(args):\n    assert widget(*args)\n"

    notes = _one_note(head, base, extra={"tests/test_mod.py": caller})

    assert [n.condition for n in notes] == []
