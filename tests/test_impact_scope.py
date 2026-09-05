"""Yellow (a), the impact scope (D-143): what a change reaches, computed.

The two the owner named are
`test_a_changed_signature_with_an_untested_caller_produces_one_note` and
`test_a_body_change_whose_callers_are_all_tested_is_silent`; both fail on the
previous implementation, which had no impact level at all. The rest hold the
abstentions, which are the reason this level may speak without a model.
"""

from __future__ import annotations

from pathlib import Path

from attest.github.presentation import impact_comments, impact_line
from attest.review.impact import (
    MAX_NOTES,
    build_call_graph,
    changed_functions,
    notes_for_change,
    read_tree,
)
from attest.review.output_contract import LEVEL_MARKERS
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
    assert note.reason == "the signature changed"
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


def test_a_body_change_still_speaks_when_a_caller_is_named_by_no_test() -> None:
    notes, _ = _notes(HEAD_PRICING_BODY, {4, 5, 6})

    assert len(notes) == 1
    assert notes[0].changed.interface_changed is False
    assert notes[0].reason == "a caller is named by no test"


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
    assert len(notes) == 1  # the signature changed, so it still speaks
    assert notes[0].untested == ()  # but the constructor is not "named by no test"
    assert "0 of them named by no test" in impact_line(notes[0])
