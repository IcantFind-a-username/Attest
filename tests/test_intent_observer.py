"""D-102: reading raise origins, statement kinds, test literals and base-tree witnesses."""

from __future__ import annotations

import json
from pathlib import Path

from attest.certification.intent import IntentObservation
from attest.review.intent import (
    RaiseOrigin,
    find_witnesses,
    identify_rejected_inputs,
    is_witness_file,
    observe_intent,
    parse_raise_origins,
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
    "    signal = mod.Signal(f'the {word} plan raises the floor')\n"
    "    assert 'x' not in signal.summary, 'short literals do not count'\n"
)


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

    assert {line: kinds[line] for line in (5, 6, 7)} == {5: "assert", 6: "assert", 7: "assert"}
    assert {line: kinds[line] for line in (10, 11, 12)} == {10: "raise", 11: "raise", 12: "raise"}
    assert 9 not in kinds and 13 not in kinds
    assert statement_kinds("def broken(:\n") == {}


def test_literals_keep_inputs_and_drop_docstrings_and_short_strings() -> None:
    literals = string_literals(TEST_SOURCE)

    assert "buyback" in literals
    assert "the " in literals and " plan raises the floor" in literals  # f-string parts
    assert "short literals do not count" in literals
    assert "x" not in literals
    assert not any("docstring" in literal or "Neither" in literal for literal in literals)
    assert string_literals("def broken(:\n") == ()


def test_rejected_inputs_are_the_literals_that_reached_the_raising_frame() -> None:
    literals = string_literals(TEST_SOURCE)

    identified = identify_rejected_inputs(literals, _origin())

    assert set(identified) == {"buyback", "the ", " plan raises the floor"}
    assert identify_rejected_inputs(literals, _origin(message="", values=())) == ()


def test_parse_raise_origins_is_fail_soft() -> None:
    rows = [
        {
            "line": 10,
            "function": "f",
            "exception_type": "ValueError",
            "message": "m",
            "values": ["v", 3],
        },
        {"line": "ten"},
        "junk",
    ]

    parsed = parse_raise_origins(json.dumps(rows).encode("utf-8"))

    assert parsed == (RaiseOrigin(10, "f", "ValueError", "m", ("v",)),)
    assert parse_raise_origins(None) == ()
    assert parse_raise_origins(b"not json") == ()
    assert parse_raise_origins(b"{}") == ()


def test_witness_files_are_tests_fixtures_examples_and_docs() -> None:
    assert is_witness_file(Path("tests/test_signal.py"))
    assert is_witness_file(Path("pkg/conftest.py"))
    assert is_witness_file(Path("pkg/signal_test.py"))
    assert is_witness_file(Path("fixtures/copy.json"))
    assert is_witness_file(Path("docs/guide.rst"))
    assert is_witness_file(Path("README.md"))
    assert is_witness_file(Path("examples/demo.py"))
    assert not is_witness_file(Path("pkg/signal.py"))
    assert not is_witness_file(Path("pkg/data.json"))


def test_find_witnesses_reads_only_witness_files_of_the_base_tree(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "signal.py").write_text("SOURCE = 'only in source'\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_signal.py").write_text(
        "def test_copy():\n    assert Signal('the buyback plan raises the floor')\n",
        encoding="utf-8",
    )
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "notes.txt").write_text("hidden witness", encoding="utf-8")

    found = find_witnesses(
        tmp_path, ("the buyback plan raises the floor", "only in source", "hidden witness")
    )

    assert found == (("the buyback plan raises the floor", "tests/test_signal.py"),)
    assert find_witnesses(tmp_path, ()) == ()


def test_observe_intent_reads_a_consistent_new_rejection(tmp_path: Path) -> None:
    observed = observe_intent(
        path="mod.py",
        changed_lines=(8, 9, 10, 11, 12),
        head_source=HEAD_SOURCE,
        test_source=TEST_SOURCE,
        head_origins=[(_origin(),), (_origin(),), (_origin(),)],
        base_tree=tmp_path,
    )

    assert isinstance(observed, IntentObservation)
    assert observed.new_rejection
    assert (observed.origin_line, observed.origin_statement) == (10, "raise")
    assert observed.exception_type == "ValueError"
    assert observed.rejected_inputs == (" plan raises the floor", "buyback", "the ")
    assert observed.witnesses == ()
    assert observed.head_runs_observed == 3


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
