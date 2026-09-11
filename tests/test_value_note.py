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


def test_a_value_over_the_verbatim_cap_is_rendered_as_a_digest_not_cut(note_line_cap) -> None:
    """Three of the 16 lines the 2026-09-11 run produced were refused for length
    because a `repr` is whatever the project's object prints. D-142 forbids
    truncating a line into shape; a value over the cap is rendered as
    `<type len=N sha256 hhhhhhhh>` -- a different rendering of the same
    measurement, never a cut `repr`."""
    long_list = "[" + ", ".join(f"({n}.0, [{n}.0, {n + 1}.0])" for n in range(40)) + "]"
    assert len(long_list) > 200
    note = _note(base_detail=long_list, head_detail="[]")
    assert note is not None

    line = render(note)

    assert check(line).admitted, check(line).reason
    assert long_list not in line
    assert f"<list len={len(long_list)} sha256 " in line
    assert "and head returns [] (" in line
    # the digest is of the recorded repr, so an operator can match it to the ledger
    import hashlib

    assert hashlib.sha256(long_list.encode("utf-8")).hexdigest()[:8] in line
    # no `repr` is ever cut: what is not written whole is written as a digest
    assert "..." not in line
    assert note_line_cap(line)


def test_a_line_that_still_overflows_digests_the_longest_part_first(note_line_cap) -> None:
    """`pydata__xarray-6744`: two 130-character values under the cap each, and
    the assembled line is 513. Parts are digested longest-first until the line
    fits, and the expression is a part too (`pytest-dev__pytest-10051` carries
    a 230-character expression)."""
    base = "[" + ", ".join(f"('{n}', [{n}.0, {n + 1}.0])" for n in range(6)) + "]"
    head = "[" + ", ".join(f"('{n}', [{n}.0, {n + 1}.0])" for n in range(5)) + "]"
    assert len(head) < len(base) <= 200
    note = _note(base_detail=base, head_detail=head, expression="x" * 60 + "(roll)")
    assert note is not None

    line = render(note)

    assert check(line).admitted, check(line).reason
    assert note_line_cap(line)
    assert head in line  # the shortest part survives verbatim
    assert "<list len=" in line
    assert "sha256" in line


def test_a_banned_word_inside_a_measured_literal_does_not_refuse_the_line() -> None:
    """`sphinx-doc__sphinx-10466`: the recorded value contains the word `hello`
    -- a fixture string of that project's own gettext test -- and the
    contract's preamble rule refused a line no model wrote a word of. The rule
    still applies to the sentence; it does not apply inside the two measured
    literals."""
    from attest.review.value_note import admitted

    note = _note(
        base_detail="[('hello', [('a.rst', 1)], 4)]",
        head_detail="[('hello', [('b.rst', 10), ('a.rst', 1)], 4)]",
    )
    assert note is not None
    line = render(note)

    assert not check(line).admitted  # the bare contract still says preamble
    verdict = admitted(note)
    assert verdict.admitted, verdict.reason
    # and the sentence itself is still adjudicated: a banned word outside the
    # literals refuses the line
    prose = _note(expression="maybe(x)")
    assert prose is not None
    assert not admitted(prose).admitted


def test_notes_are_one_per_path_and_expression() -> None:
    """The `click` pair of the census: the same call recorded twice is one
    fact. Two notes on the same `(path, expression)` keep the first."""
    from attest.review.value_note import distinct

    first = _note()
    again = _note(head_detail="Decimal('1.20')")
    other = _note(expression="money.rate('USD')")
    assert first and again and other

    kept = distinct([first, again, other])

    assert kept == [first, other]


def test_a_note_anchored_inside_tests_is_not_shown() -> None:
    """`itsdangerous` in the census anchors in `tests/test_serializer.py`: the
    note would point an author at their own test. Such a note is written to
    the ledger and not shown."""
    from attest.review.value_note import anchored_in_tests

    inside = _note(intent=_intent(path="tests/test_money.py"))
    assert inside is not None and anchored_in_tests(inside)
    for path in ("pkg/money.py", "src/pkg/money.py", "pkg/testing.py"):
        outside = _note(intent=_intent(path=path))
        assert outside is not None and not anchored_in_tests(outside)


def test_every_line_of_the_2026_09_11_run_is_admitted_under_the_visible_rule(
    note_line_cap,
) -> None:
    """The 16 notes the paid held-out run wrote (run 34530619773), replayed
    through the rendering an author would see. At recording 12 of 16 were
    admitted -- three over the length cap, one on a banned word inside a
    measured literal. Under this rule all 16 are."""
    import json
    from pathlib import Path

    from attest.review.value_note import ValueNote, admitted, anchored_in_tests, distinct

    evidence = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "docs/acceptance/evidence/2026-09-11-value-notes-sixteen.json"
        ).read_text(encoding="utf-8")
    )
    rows = evidence["notes"]
    assert len(rows) == 16
    fields = {f for f in ValueNote.__dataclass_fields__}

    def rebuilt(row: dict) -> ValueNote:
        payload = {k: v for k, v in row.items() if k in fields}
        payload["specified_by"] = tuple(tuple(x) for x in payload["specified_by"])
        payload["pinned_values"] = tuple(payload["pinned_values"])
        return ValueNote(**payload)

    notes = [rebuilt(row) for row in rows]
    verdicts = [admitted(note) for note in notes]
    refused = [(n.path, v.reason) for n, v in zip(notes, verdicts, strict=True) if not v]
    assert refused == []
    assert all(note_line_cap(render(note)) for note in notes)
    # what the author-visible rule then keeps: none in tests/, and one fewer
    # after the (path, expression) rule -- `kahane_simplify(t)` twice
    assert [n for n in notes if anchored_in_tests(n)] == []
    assert len(distinct(notes)) == 15


def test_ci_reads_no_note_while_the_switch_is_off() -> None:
    """`value_notes_visible` is False by default; a ledger full of notes yields
    nothing an author sees. Only the switch opens the surface, and the switch is
    a base-owned policy key."""
    from attest.review.ci import value_notes_for_task
    from attest.review.config import _KNOWN_POLICY_KEYS, ReviewConfig

    assert ReviewConfig().value_notes_visible is False
    assert "value_notes_visible" in _KNOWN_POLICY_KEYS
    from dataclasses import asdict

    note = _note()
    assert note is not None
    row = {
        "kind": "value_observation_note",
        "task_id": "t1",
        "finding_id": "cafe1234ab",
        "note_id": note.note_id(),
        **asdict(note),
    }
    assert value_notes_for_task([row], "t1", ReviewConfig()) == []
    shown = value_notes_for_task([row], "t1", ReviewConfig(value_notes_visible=True))
    assert shown == [note]
    # another task's row is not this task's note
    assert value_notes_for_task([row], "t2", ReviewConfig(value_notes_visible=True)) == []


def test_the_note_s_coordinate_is_the_anchored_source_line_not_the_test_s() -> None:
    """Found in the self-review of the drawer window: `failing_assertion_line`
    is *the line of the generated test the head runs failed on* (D-132), and
    D-218 paired it with the source path -- so 13 of the 16 lines of the paid
    run pointed at `xarray/core/rolling.py:11`, a test-file line number on a
    source file. The coordinate is the candidate's anchor, a changed line of
    the anchored file; the assertion line stays in the ledger row."""
    note = _note(intent=_intent(failing_assertion_line=11), anchor_line=347)
    assert note is not None
    assert note.line == 347
    assert render(note).startswith("[yellow] pkg/money.py:347 — ")


def test_the_inline_value_comment_asks_for_a_reply_only_when_told_to() -> None:
    """D-227: `value_comments(..., ask_for_reply=True)` ends the action clause
    with the one sentence that asks for `intended` or `unintended`, and the
    comment still passes the whole-comment adjudicator; without the flag the
    clause is unchanged."""
    from attest.github.presentation import REPLY_PROMPT, value_comments
    from attest.review.output_contract import check_comment

    note = _note()
    plain = value_comments([note])
    asked = value_comments([note], ask_for_reply=True)
    assert len(plain) == 1 and len(asked) == 1
    plain_body, asked_body = str(plain[0]["body"]), str(asked[0]["body"])
    assert REPLY_PROMPT.strip() not in plain_body
    assert asked_body.rstrip().endswith("Reply `intended` or `unintended` to record it.")
    assert check_comment(asked_body).admitted
    # one action clause, still: the sentence is appended to it, not a second one
    assert asked_body.count("Action:") == 1
