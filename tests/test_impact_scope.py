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


def _notes(head_pricing: str, changed_lines: set[int], **kwargs: bool):
    sources = _tree(head_pricing, **kwargs)
    graph = build_call_graph(sources)
    changed = changed_functions(
        path="pricing.py",
        head_source=head_pricing,
        base_source=BASE_PRICING,
        changed_lines=changed_lines,
    )
    return notes_for_change(graph, changed), graph


# --- the two the level is defined by ----------------------------------------


def test_a_changed_signature_with_an_untested_caller_produces_one_note() -> None:
    notes, _ = _notes(HEAD_PRICING_SIGNATURE, {2})

    assert len(notes) == 1
    note = notes[0]
    assert note.changed.signature_changed is True
    assert note.changed.added_required_parameter is True
    assert note.reason == "the signature changed and a caller is named by no test"
    assert {caller.site.path for caller in note.callers} == {"checkout.py", "reporting.py"}
    assert [caller.site.path for caller in note.untested] == ["reporting.py"]

    line = impact_line(note)
    assert contract_check(line).admitted is True
    assert line.startswith(LEVEL_MARKERS["yellow"])
    assert "pricing.py:2" in line and "reporting.py:6" in line
    assert "changed signature" in line and "1 of them named by no test" in line


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
    """D-145's second half. Under D-143 a changed signature spoke on its own;
    a suite that names every caller will report the breakage itself."""

    notes, _ = _notes(HEAD_PRICING_SIGNATURE, {2}, with_untested_caller=False)

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

    silent, _ = _notes(HEAD_PRICING_SIGNATURE, {2}, with_untested_caller=False)
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
