"""The value-class observation as one yellow line, in shadow (D-218).

The intent clause's drawer is the right verdict for *"this is a defect"* and
nothing here moves it. What these pin is that the fact the drawer throws away —
the merge base returned A, head returns B, three runs each side, and nothing in
the tree pinned either — is written down, is renderable as one contract line,
and **reaches no author**.
"""

from __future__ import annotations

from attest.certification.intent import IntentObservation
from attest.review.output_contract import check
from attest.review.value_note import (
    VALUE_NOTE_POLICY_VERSION,
    drawered_for_unknown_intent,
    note_from,
    render,
)

VALUE_DRAWER = (
    "intent: value change confirmed, intent unknown: the base tree does not specify the "
    "value this assertion pins about the symbol this change touched -- no base test asserts "
    "it and no docstring or documentation writes it down (返回值变化已证实，意图未知)"
)
REJECTION_DRAWER = (
    "intent: behavior change confirmed, intent unknown: head raises ValueError from a raise "
    "statement on a changed line; the rejected input is not in the base tree's tests, "
    "fixtures or documentation (行为变化已证实，意图未知)"
)
STATED_IN_DIFF = (
    "intent: intent stated in the change itself: the same change also updates a test, a "
    "docstring, documentation, a changelog entry or an inline comment about the symbol "
    "under test (改动自身已陈述意图)"
)


def _intent(**overrides: object) -> IntentObservation:
    fields: dict[str, object] = {
        "policy_version": "attest.intent.v4.2",
        "path": "pkg/money.py",
        "changed_lines": (41, 42),
        "origin_line": 0,
        "origin_statement": "assert",
        "exception_type": "",
        "new_rejection": False,
        "rejected_inputs": (),
        "witnesses": (),
        "head_runs_observed": 3,
        "value_mismatch": True,
        "pinned_values": ("Decimal('1.05')",),
        "value_specified": (),
        "failing_assertion_line": 41,
    }
    fields.update(overrides)
    return IntentObservation(**fields)  # type: ignore[arg-type]


def _note(**overrides: object):  # noqa: ANN202 - the module's own dataclass
    kwargs: dict[str, object] = {
        "intent": _intent(),
        "expression": "money.rate('EUR')",
        "base_kind": "value",
        "base_detail": "Decimal('1.05')",
        "head_kind": "value",
        "head_detail": "Decimal('1.10')",
        "head_runs": 3,
        "base_runs": 3,
        "reason": VALUE_DRAWER,
        "candidate_id": "cafe1234ab",
        "anchor_line": 41,
    }
    kwargs.update(overrides)
    return note_from(**kwargs)  # type: ignore[arg-type]


def test_both_unknown_intent_drawers_produce_a_note_and_nothing_else_does() -> None:
    assert drawered_for_unknown_intent(VALUE_DRAWER)
    assert drawered_for_unknown_intent(REJECTION_DRAWER)
    # the author already said what they meant; a note would be telling them so
    assert not drawered_for_unknown_intent(STATED_IN_DIFF)
    assert not drawered_for_unknown_intent("head FAIL 3/3, base PASS 3/3")
    assert _note(reason=STATED_IN_DIFF) is None


def test_the_line_is_one_admissible_contract_line() -> None:
    """D-142 adjudicates every author-visible line, and a shadow line that
    could never pass it is not a proposal anybody can act on."""
    note = _note()
    assert note is not None

    line = render(note)

    verdict = check(line)
    assert verdict.admitted, verdict.reason
    assert line.startswith("[yellow] pkg/money.py:41 — ")
    assert "for money.rate('EUR'), the merge base returned Decimal('1.05') and head " in line
    assert "returns Decimal('1.10') (3/3 and 3/3 runs each side)" in line
    assert "no base test, docstring or changelog pins either" in line
    assert line.endswith(f"note {note.note_id()}")


def test_a_note_says_when_the_tree_did_pin_the_value_and_the_change_moved_it() -> None:
    """The drawer has several reasons and the line must not assert the wrong
    one. `no base test pins either` is a claim about the tree, and it is false
    when D-132's respecification clause is what drawered the receipt."""
    note = _note(
        intent=_intent(value_specified=(("Decimal('1.05')", "tests/test_money.py:12"),)),
    )
    assert note is not None

    line = render(note)

    assert check(line).admitted
    assert "the base tree pins it at tests/test_money.py:12, and this change moved it" in line
    assert "no base test" not in line


def test_a_recorded_exception_reads_as_one() -> None:
    note = _note(base_kind="exception", base_detail="KeyError", head_kind="value",
                 head_detail="None")
    assert note is not None

    assert "the merge base raised KeyError and head returns None" in render(note)


def test_a_note_without_the_head_observation_is_not_written() -> None:
    """Half the evidence is not a yellow claim. The whole argument of this level
    is that every number in the line was measured, so a note that cannot say
    what head produced is refused rather than hedged."""
    assert _note(head_kind="", head_detail="") is None


def test_the_note_id_is_stable_and_moves_with_the_content() -> None:
    first, second = _note(), _note()
    assert first is not None and second is not None
    assert first.note_id() == second.note_id()

    moved = _note(head_detail="Decimal('1.20')")
    assert moved is not None
    assert moved.note_id() != first.note_id()
    assert first.policy_version == VALUE_NOTE_POLICY_VERSION


def test_nothing_in_the_publication_path_imports_this_module() -> None:
    """Shadow means shadow. `ci.py` is the only thing that writes to a pull
    request, and the check is the import graph rather than a promise."""
    import ast
    from pathlib import Path

    ci = Path(__file__).resolve().parents[1] / "src" / "attest" / "review" / "ci.py"
    tree = ast.parse(ci.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert "attest.review.value_note" not in imported
    assert "value_note" not in ci.read_text(encoding="utf-8")
