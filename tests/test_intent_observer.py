"""D-102: reading raise origins, statement kinds, test literals and base-tree witnesses."""

from __future__ import annotations

import json
from pathlib import Path

from attest.certification.intent import IntentObservation
from attest.review.intent import (
    RaiseOrigin,
    RaiseRecord,
    failure_type,
    find_witnesses,
    identify_rejected_inputs,
    is_witness_file,
    observe_intent,
    parse_raise_origins,
    parse_raise_record,
    statement_kinds,
    string_literals,
)

HEAD_SOURCE = (
    "BANNED = ('buy',)\n"
    "\n"
    "class Signal:\n"
    "    def __init__(self, summary):\n"
    "        assert isinstance(summary, str), (\n"
    "            'summary must be text'\n"
    "        )\n"
    "        for verb in BANNED:\n"
    "            if verb in summary:\n"
    "                raise ValueError(\n"
    "                    f'summary must never contain {verb!r}: {summary!r}'\n"
    "                )\n"
    "        self.summary = summary\n"
)

TEST_SOURCE = (
    '"""A docstring is prose, never an input."""\n'
    "import mod\n"
    "\n"
    "def test_repro():\n"
    '    """Neither is this one."""\n'
    "    word = 'buyback'\n"
    "    phrase = 'the buyback plan raises the floor'\n"
    "    options = {'tag': 'value'}\n"
    "    signal = mod.Signal(phrase, options['tag'])\n"
    "    assert f'the {word} plan' in signal.summary, 'short literals do not count'\n"
    "    assert 'x' not in signal.summary\n"
)
FAILURE = "ValueError: summary must never contain 'buy': 'the buyback plan raises the floor'"


def _origin(line: int = 10, **overrides: object) -> RaiseOrigin:
    values: dict[str, object] = {
        "line": line,
        "function": "__init__",
        "exception_type": "ValueError",
        "message": "summary must never contain 'buy': 'the buyback plan raises the floor'",
        "values": ("the buyback plan raises the floor", "buy"),
    }
    values.update(overrides)
    return RaiseOrigin(**values)  # type: ignore[arg-type]


def test_statement_kinds_cover_every_line_a_raise_or_assert_spans() -> None:
    kinds = statement_kinds(HEAD_SOURCE)

    assert kinds is not None
    assert {line: kinds[line] for line in (5, 6, 7)} == {5: "assert", 6: "assert", 7: "assert"}
    assert {line: kinds[line] for line in (10, 11, 12)} == {10: "raise", 11: "raise", 12: "raise"}
    assert 9 not in kinds and 13 not in kinds
    # unparsable or empty source is "unknown", never "no raise anywhere"
    assert statement_kinds("def broken(:\n") is None
    assert statement_kinds("") is None
    assert statement_kinds("x = 1\n") == {}


def test_literals_keep_inputs_and_drop_docstrings_keys_and_short_strings() -> None:
    literals = string_literals(TEST_SOURCE)

    assert "buyback" in literals and "the buyback plan raises the floor" in literals
    assert "the " in literals and " plan" in literals  # f-string parts
    assert "short literals do not count" in literals
    assert "value" in literals
    assert "tag" not in literals  # a dictionary key / subscript is a name, not an input
    assert "x" not in literals
    assert not any("docstring" in literal or "Neither" in literal for literal in literals)
    assert string_literals("def broken(:\n") == ()


def test_rejected_inputs_are_literals_equal_to_a_local_or_quoted_in_the_message() -> None:
    literals = string_literals(TEST_SOURCE)

    identified = identify_rejected_inputs(literals, _origin())

    # the phrase equals a local and is quoted in the message; "buyback" is only a
    # substring of both, and substrings are not inputs (review finding F3)
    assert identified == ("the buyback plan raises the floor",)
    assert identify_rejected_inputs(literals, _origin(message="", values=())) == ()
    quoted_only = _origin(message="rejected 'buyback' here", values=())
    assert identify_rejected_inputs(literals, quoted_only) == ("buyback",)
    unquoted = _origin(message="the buyback plan is not allowed", values=())
    assert identify_rejected_inputs(literals, unquoted) == ()


def test_parse_raise_record_is_fail_soft_on_rows_and_fail_closed_on_the_artifact() -> None:
    rows = [
        {
            "line": 10,
            "function": "f",
            "exception_type": "ValueError",
            "message": "m",
            "values": ["v", 3],
            "escaped": False,
        },
        {"line": "ten"},
        "junk",
    ]

    record = parse_raise_record(json.dumps({"origins": rows, "truncated": False}).encode())
    assert record == RaiseRecord((RaiseOrigin(10, "f", "ValueError", "m", ("v",), False),), False)
    # the first artifact format, a bare list, still reads (escaped defaults to True)
    legacy = [{key: value for key, value in rows[0].items() if key != "escaped"}]
    assert parse_raise_origins(json.dumps(legacy).encode("utf-8")) == (
        RaiseOrigin(10, "f", "ValueError", "m", ("v",), True),
    )
    assert parse_raise_record(None) == RaiseRecord((), False)
    assert parse_raise_record(b"{}") == RaiseRecord((), False)
    # an incomplete or unreadable record is flagged, so the caller DEFERs
    assert parse_raise_record(json.dumps({"origins": [], "truncated": True}).encode()).truncated
    assert parse_raise_record(json.dumps({"origins": [], "error": "X"}).encode()).truncated
    assert parse_raise_record(b"not json").truncated
    assert parse_raise_record(b"42").truncated


def test_witness_files_are_tests_fixtures_examples_and_docs() -> None:
    assert is_witness_file(Path("tests/test_signal.py"))
    assert is_witness_file(Path("pkg/conftest.py"))
    assert is_witness_file(Path("pkg/signal_test.py"))
    assert is_witness_file(Path("fixtures/copy.json"))
    assert is_witness_file(Path("tests/data/copy.txt"))
    assert is_witness_file(Path("docs/guide.rst"))
    assert is_witness_file(Path("README.md"))
    assert is_witness_file(Path("examples/demo.py"))
    assert not is_witness_file(Path("pkg/signal.py"))
    assert not is_witness_file(Path("pkg/data.json"))
    # review finding F3: a dependency list is not a witness
    assert not is_witness_file(Path("requirements.txt"))
    assert not is_witness_file(Path("requirements/dev.txt"))
    assert not is_witness_file(Path("poetry.lock"))


def test_find_witnesses_reads_only_witness_files_of_the_base_tree(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "signal.py").write_text("SOURCE = 'only in source'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_signal.py").write_text(
        "def test_copy():\n    assert Signal('the buyback plan raises the floor')\n",
        encoding="utf-8",
    )
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "notes.txt").write_text("'hidden witness'", encoding="utf-8")
    (tmp_path / "requirements.txt").write_text("requests\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text(
        "Mentioning the buyback plan raises the floor in prose is not an example, "
        "but `tag-42` in backticks is.\n",
        encoding="utf-8",
    )

    found = find_witnesses(
        tmp_path,
        (
            "the buyback plan raises the floor",
            "only in source",
            "hidden witness",
            "requests",
            "tag-42",
        ),
    )

    # quoted in a test: witnessed; prose mention, dependency list, .git: not
    assert found == (
        ("tag-42", "docs/guide.md"),
        ("the buyback plan raises the floor", "tests/test_signal.py"),
    )
    assert find_witnesses(tmp_path, ()) == ()


def test_observe_intent_reads_a_consistent_new_rejection(tmp_path: Path) -> None:
    observed = observe_intent(
        path="mod.py",
        changed_lines=(8, 9, 10, 11, 12),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(),), (_origin(),), (_origin(),)],
        head_failures=[FAILURE] * 3,
        base_tree=tmp_path,
    )

    assert isinstance(observed, IntentObservation)
    assert observed.new_rejection
    assert (observed.origin_line, observed.origin_statement) == (10, "raise")
    assert observed.exception_type == "ValueError"
    assert observed.rejected_inputs == ("the buyback plan raises the floor",)
    assert observed.witnesses == ()
    assert observed.head_runs_observed == 3
    # a test-level failure (assertion, pytest.fail) after the escaped raise still
    # names the raise as the rejection
    wrapped = observe_intent(
        path="mod.py",
        changed_lines=(8, 9, 10, 11, 12),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(),)] * 3,
        head_failures=["AssertionError: assert not raised"] * 3,
        base_tree=tmp_path,
    )
    assert isinstance(wrapped, IntentObservation) and wrapped.new_rejection


def test_observe_intent_refuses_to_classify_what_it_cannot_read(tmp_path: Path) -> None:
    """Review findings F1 and F2: an incomplete origin record or an unparsable
    anchored file must DEFER, never fall through to 'regression'."""
    truncated = observe_intent(
        path="mod.py",
        changed_lines=(10,),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(),)] * 3,
        base_tree=tmp_path,
        truncated=True,
    )
    assert isinstance(truncated, str) and "incomplete" in truncated

    unparsable = observe_intent(
        path="mod.py",
        changed_lines=(10,),
        head_source="def broken(:\n",
        test_source=TEST_SOURCE,
        head_origins=[(_origin(),)] * 3,
        base_tree=tmp_path,
    )
    assert isinstance(unparsable, str) and "could not be parsed" in unparsable

    # unparsable but no origin on a changed line: nothing to classify, a regression
    plain = observe_intent(
        path="mod.py",
        changed_lines=(13,),
        head_source="",
        test_source=TEST_SOURCE,
        head_origins=[(), (), ()],
        base_tree=tmp_path,
    )
    assert isinstance(plain, IntentObservation) and not plain.new_rejection


def test_a_caught_or_unrelated_raise_on_a_changed_line_is_not_the_rejection(
    tmp_path: Path,
) -> None:
    """Review finding F4: a raise the anchored code handled itself, or one whose
    exception the test did not fail with, does not decide the class."""
    caught = observe_intent(
        path="mod.py",
        changed_lines=(8, 9, 10, 11, 12),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(escaped=False),)] * 3,
        head_failures=["AssertionError: assert 1 == 0"] * 3,
        base_tree=tmp_path,
    )
    assert isinstance(caught, IntentObservation) and not caught.new_rejection

    unrelated = observe_intent(
        path="mod.py",
        changed_lines=(8, 9, 10, 11, 12),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(),)] * 3,
        head_failures=["TypeError: unsupported operand"] * 3,
        base_tree=tmp_path,
    )
    assert isinstance(unrelated, IntentObservation) and not unrelated.new_rejection
    assert failure_type("ValueError: bad") == "ValueError"
    assert failure_type("requests.exceptions.InvalidURL: x") == "requests.exceptions.InvalidURL"
    assert failure_type("assert 1 == 0") == ""
    assert failure_type("") == ""


def test_observe_intent_records_a_regression_and_a_crash_without_a_rejection(
    tmp_path: Path,
) -> None:
    regression = observe_intent(
        path="mod.py",
        changed_lines=(13,),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(), (), ()],
        base_tree=tmp_path,
    )
    assert isinstance(regression, IntentObservation)
    assert not regression.new_rejection
    assert (regression.origin_line, regression.origin_statement) == (0, "")

    crash = observe_intent(
        path="mod.py",
        changed_lines=(13,),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(line=13, exception_type="AttributeError"),)] * 3,
        base_tree=tmp_path,
    )
    assert isinstance(crash, IntentObservation)
    assert not crash.new_rejection
    assert (crash.origin_line, crash.origin_statement) == (13, "other")
    # a raise on an unchanged line is not a new rejection either
    unchanged = observe_intent(
        path="mod.py",
        changed_lines=(13,),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(line=10),)] * 3,
        base_tree=tmp_path,
    )
    assert isinstance(unchanged, IntentObservation)
    assert not unchanged.new_rejection


def test_observe_intent_refuses_head_runs_that_disagree(tmp_path: Path) -> None:
    disagree = observe_intent(
        path="mod.py",
        changed_lines=(8, 9, 10, 11, 12),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(),), (), (_origin(),)],
        base_tree=tmp_path,
    )
    assert isinstance(disagree, str) and "disagree" in disagree

    other_line = observe_intent(
        path="mod.py",
        changed_lines=(5, 6, 7, 8, 9, 10, 11, 12),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(),), (_origin(line=5, exception_type="AssertionError"),)],
        base_tree=tmp_path,
    )
    assert isinstance(other_line, str) and "disagree" in other_line
