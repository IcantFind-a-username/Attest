"""Yellow (b), second class: an exception that now reaches an unprotected caller (D-164).

The first yellow (b) class asks about `None` and measured 0 of 79, because the
corpus it reads carries no type annotations at all. This class asks a question
the same code *can* answer, because it reads statements rather than
declarations: the changed function now calls something that raises, and on the
way out to a caller nobody catches it.

Three premises, all three or nothing. These tests pin each of them failing on
its own, and the one case where all three hold.
"""

from __future__ import annotations

from attest.review.impact import build_call_graph, changed_functions
from attest.review.propagation import (
    PROPAGATION_POLICY_VERSION,
    notes_for_change,
)

BASE = '''
def load(path):
    return read(path)


def read(path):
    if not path:
        raise ValueError("empty path")
    return path


def caller():
    return load("x")
'''

HEAD = '''
def load(path):
    validate(path)
    return read(path)


def validate(path):
    if not path:
        raise LookupError("no such path")


def read(path):
    if not path:
        raise ValueError("empty path")
    return path


def caller():
    return load("x")
'''


def _notes(head: str, base: str, changed_lines=(3,), path: str = "app.py"):
    graph = build_call_graph({path: head})
    changed = changed_functions(
        path=path, head_source=head, base_source=base, changed_lines=changed_lines
    )
    return notes_for_change(
        graph, changed, head_sources={path: head}, base_sources={path: base}
    )


def test_all_three_premises_produce_one_note() -> None:
    notes = _notes(HEAD, BASE)

    assert len(notes) == 1
    note = notes[0]
    assert note.policy_version == PROPAGATION_POLICY_VERSION
    assert note.callee == "validate"
    assert note.exception == "LookupError"
    assert note.evidence == "raise"
    assert note.caller_qualname == "caller"
    assert "does not handle it" in note.sentence
    assert note.note_id == f"app.py:{note.line}:LookupError"


def test_a_call_the_base_already_made_is_not_a_new_exception() -> None:
    """Premise (i): the call must be one the change introduced. `read` raises
    `ValueError` and always did; the caller's exposure did not move."""
    base = HEAD.replace("def caller():", "def caller():")  # head == base
    notes = _notes(HEAD, base)

    assert notes == ()


def test_a_callee_that_raises_nothing_named_is_not_a_hypothesis() -> None:
    """Premise (ii): a bare `raise` re-raises and names no type, and a callee
    with neither a named raise nor a documented one is not a hypothesis."""
    head = HEAD.replace(
        'def validate(path):\n    if not path:\n        raise LookupError("no such path")',
        "def validate(path):\n    if not path:\n        raise",
    )
    notes = _notes(head, BASE)

    assert notes == ()


def test_a_handler_anywhere_on_the_way_out_voids_the_note() -> None:
    """Premise (iii), three ways: around the new call, in the changed function,
    and in the caller. Each on its own is enough to void it."""
    guarded_here = HEAD.replace(
        "def load(path):\n    validate(path)\n    return read(path)",
        "def load(path):\n    try:\n        validate(path)\n    except LookupError:\n"
        "        pass\n    return read(path)",
    )
    assert _notes(guarded_here, BASE, changed_lines=(3, 4, 5)) == ()

    catch_all = HEAD.replace(
        "def load(path):\n    validate(path)\n    return read(path)",
        "def load(path):\n    try:\n        validate(path)\n    except Exception:\n"
        "        pass\n    return read(path)",
    )
    assert _notes(catch_all, BASE, changed_lines=(3, 4, 5)) == ()

    guarded_caller = HEAD.replace(
        'def caller():\n    return load("x")',
        'def caller():\n    try:\n        return load("x")\n    except LookupError:\n'
        "        return None",
    )
    assert _notes(guarded_caller, BASE) == ()


def test_only_a_test_caller_is_not_a_caller_this_level_speaks_about() -> None:
    """The claim is that *production* code is now exposed. A test that calls it
    is not exposure, it is coverage."""
    head = HEAD.replace('def caller():\n    return load("x")', "")
    graph = build_call_graph(
        {"app.py": head, "tests/test_app.py": 'def test_load():\n    load("x")\n'}
    )
    changed = changed_functions(
        path="app.py", head_source=head, base_source=BASE, changed_lines=(3,)
    )

    assert (
        notes_for_change(
            graph, changed, head_sources={"app.py": head}, base_sources={"app.py": BASE}
        )
        == ()
    )


def test_a_documented_raises_section_counts_as_evidence() -> None:
    """A project that documents `Raises:` has said what it raises, and reading
    only the body would make the level depend on documentation fashion."""
    head = HEAD.replace(
        'def validate(path):\n    if not path:\n        raise LookupError("no such path")',
        'def validate(path):\n    """Check a path.\n\n    Raises:\n'
        "        PermissionError: when the path is not readable.\n"
        '    """\n    _check(path)',
    )
    notes = _notes(head, BASE)

    assert len(notes) == 1
    assert notes[0].exception == "PermissionError"
    assert notes[0].evidence == "docstring"


def test_a_sphinx_raises_field_counts_too() -> None:
    head = HEAD.replace(
        'def validate(path):\n    if not path:\n        raise LookupError("no such path")',
        'def validate(path):\n    """Check a path.\n\n'
        '    :raises TimeoutError: when the check times out.\n    """\n    _check(path)',
    )
    notes = _notes(head, BASE)

    assert len(notes) == 1 and notes[0].exception == "TimeoutError"


def test_an_ambiguous_callee_name_voids_rather_than_guesses() -> None:
    """Two `validate` definitions are two functions, and this level cannot tell
    a call of one from a call of the other."""
    head = HEAD
    other = 'def validate(x):\n    return x\n'
    graph = build_call_graph({"app.py": head, "other.py": other})
    changed = changed_functions(
        path="app.py", head_source=head, base_source=BASE, changed_lines=(3,)
    )

    assert (
        notes_for_change(
            graph, changed, head_sources={"app.py": head, "other.py": other},
            base_sources={"app.py": BASE},
        )
        == ()
    )


def test_the_class_never_shows_more_than_its_own_cap() -> None:
    assert len(_notes(HEAD, BASE, changed_lines=(3,))) <= 2


def test_the_published_line_is_one_contract_line_with_both_coordinates() -> None:
    """D-142: marker, coordinate, one sentence of fact, and evidence a reader can
    open -- here the caller, because that is the half the author cannot see from
    the changed function alone."""
    from attest.github.presentation import propagation_line
    from attest.review.output_contract import LEVEL_MARKERS
    from attest.review.output_contract import check as contract_check

    note = _notes(HEAD, BASE)[0]
    line = propagation_line(note)

    assert line.startswith(LEVEL_MARKERS["yellow"])
    assert "app.py:" in line
    assert contract_check(line).admitted is True
    assert "\n" not in line


def test_the_two_yellow_classes_share_one_cap() -> None:
    """D-151: a pull request never shows more than two yellow comments however
    many classes spoke."""
    from attest.github.presentation import YELLOW_MAX_COMMENTS, propagation_comments

    note = _notes(HEAD, BASE)[0]
    comments = propagation_comments([note, note, note])

    assert len(comments) <= YELLOW_MAX_COMMENTS
    assert comments[0]["path"] == note.path
    assert "The three premises, as checked" in str(comments[0]["body"])


def test_a_note_whose_line_the_diff_does_not_carry_is_dropped_not_posted() -> None:
    """D-147: GitHub refuses the whole review for one unanchored comment."""
    from attest.github.presentation import propagation_comments

    note = _notes(HEAD, BASE)[0]

    assert propagation_comments([note], {"app.py": {note.line}})
    assert propagation_comments([note], {"app.py": {note.line + 500}}) == []
