"""Observing the intent of a head failure (D-102, tightened after the D-049 review):
the raise origins the tracer recorded, the statement kind from the head source, the
rejected inputs from the generated test's literals, and their witnesses in the base
tree. File reads only: no execution, no model, no repository command.

Fail closed at every step: an unreadable or unparsable anchored file, a truncated
origin record, or head runs that disagree all DEFER instead of classifying.
"""

from __future__ import annotations

import ast
import json
import os
from dataclasses import dataclass
from pathlib import Path

from attest.certification.intent import (
    INTENT_POLICY_VERSION,
    REJECTING_STATEMENTS,
    IntentObservation,
)

MAX_ORIGIN_RECORDS = 256
MAX_MESSAGE_CHARS = 2_000
MAX_VALUE_CHARS = 500
MAX_VALUES = 16
MIN_LITERAL_CHARS = 2
MAX_WITNESS_FILES = 5_000
MAX_WITNESS_FILE_BYTES = 1_000_000
MAX_WITNESS_TOTAL_BYTES = 64_000_000
# a failure the test itself raised: the escaped rejection may still be its cause
TEST_LEVEL_FAILURES = frozenset({"AssertionError", "Failed", ""})
WITNESS_DIRS = frozenset(
    {
        "tests",
        "test",
        "testing",
        "fixtures",
        "fixture",
        "testdata",
        "test_data",
        "examples",
        "example",
        "docs",
        "doc",
    }
)
DOC_SUFFIXES = (".md", ".rst")  # documentation anywhere in the tree
DATA_SUFFIXES = (".txt", ".json", ".yaml", ".yml", ".toml", ".csv")  # only inside witness dirs
SKIPPED_DIRS = frozenset(
    {
        ".git",
        ".attest",
        ".attest-repro",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "dist",
        "build",
        ".eggs",
    }
)


@dataclass(frozen=True)
class RaiseOrigin:
    """One exception first seen in a frame of the anchored file during a head run."""

    line: int
    function: str
    exception_type: str
    message: str  # bounded str(exception)
    values: tuple[str, ...]  # bounded string-typed locals of that frame
    escaped: bool = True  # False when a frame of the anchored file handled it


@dataclass(frozen=True)
class RaiseRecord:
    origins: tuple[RaiseOrigin, ...]
    truncated: bool  # the tracer hit its record bound; the record is incomplete


def parse_raise_record(marker: bytes | None) -> RaiseRecord:
    """The tracer's ``raise-origin`` artifact, fail-soft on malformed rows and
    fail-closed on an unreadable artifact (``truncated`` = incomplete)."""
    if not marker:
        return RaiseRecord((), False)
    try:
        payload = json.loads(marker.decode("utf-8", errors="replace"))
    except ValueError:
        return RaiseRecord((), True)
    if isinstance(payload, list):  # the first record format: a bare list
        rows: list[object] = payload
        truncated = False
    elif isinstance(payload, dict):
        raw_rows = payload.get("origins")
        rows = raw_rows if isinstance(raw_rows, list) else []
        truncated = bool(payload.get("truncated")) or "error" in payload
    else:
        return RaiseRecord((), True)
    origins: list[RaiseOrigin] = []
    for row in rows[:MAX_ORIGIN_RECORDS]:
        if not isinstance(row, dict):
            continue
        line = row.get("line")
        if type(line) is not int or line < 1:
            continue
        values = row.get("values")
        origins.append(
            RaiseOrigin(
                line=line,
                function=str(row.get("function") or ""),
                exception_type=str(row.get("exception_type") or ""),
                message=str(row.get("message") or "")[:MAX_MESSAGE_CHARS],
                values=tuple(
                    str(value)[:MAX_VALUE_CHARS]
                    for value in (values if isinstance(values, list) else [])[:MAX_VALUES]
                    if isinstance(value, str)
                ),
                escaped=bool(row.get("escaped", True)),
            )
        )
    return RaiseRecord(tuple(origins), truncated or len(rows) > MAX_ORIGIN_RECORDS)


def parse_raise_origins(marker: bytes | None) -> tuple[RaiseOrigin, ...]:
    return parse_raise_record(marker).origins


def statement_kinds(source: str) -> dict[int, str] | None:
    """Line -> ``raise`` | ``assert`` for every line such a statement spans;
    ``None`` when the source cannot be parsed (the caller must not classify)."""
    if not source.strip():
        return None
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    kinds: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            kind = "raise"
        elif isinstance(node, ast.Assert):
            kind = "assert"
        else:
            continue
        end = node.end_lineno or node.lineno
        for line in range(node.lineno, end + 1):
            kinds[line] = kind
    return kinds


def string_literals(source: str) -> tuple[str, ...]:
    """The string constants of the generated test that can have been fed to the
    code under test: not docstrings, not dictionary keys, not subscripts."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ()
    excluded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            excluded.update(id(key) for key in node.keys if key is not None)
        elif isinstance(node, ast.Subscript):
            excluded.add(id(node.slice))
        elif isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                excluded.add(id(body[0].value))
    literals: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in excluded
            and len(node.value.strip()) >= MIN_LITERAL_CHARS
        ):
            literals.add(node.value)
    return tuple(sorted(literals))


def _quoted_forms(literal: str) -> tuple[str, ...]:
    return (repr(literal), '"' + literal + '"', "'" + literal + "'", "`" + literal + "`")


def identify_rejected_inputs(literals: tuple[str, ...], origin: RaiseOrigin) -> tuple[str, ...]:
    """The test literals that reached the raising frame: equal to a string-typed
    local of that frame, or quoted verbatim in the exception message. Substring
    presence is not enough (a dictionary key inside a message is not an input)."""
    values = set(origin.values)
    return tuple(
        literal
        for literal in literals
        if literal in values or any(form in origin.message for form in _quoted_forms(literal))
    )


def is_witness_file(relative: Path) -> bool:
    """A file of the base tree that can attest an input as legitimate: a test
    module anywhere, documentation anywhere, data files only inside a test,
    fixture, example or documentation directory."""
    name = relative.name
    in_witness_dir = any(part in WITNESS_DIRS for part in relative.parts[:-1])
    if name.endswith(DOC_SUFFIXES) or name.upper().startswith("README"):
        return True
    if name == "conftest.py" or (
        name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))
    ):
        return True
    return in_witness_dir and (name.endswith(".py") or name.endswith(DATA_SUFFIXES))


def find_witnesses(base_tree: Path, literals: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """(literal, relative path) for every literal that occurs *quoted* in a witness
    file of ``base_tree`` -- as a string literal, or in backticks -- so that it is
    used there as an input, not merely mentioned; bounded walk, first witness each."""
    pending = set(literals)
    found: dict[str, str] = {}
    files_seen = 0
    bytes_seen = 0
    root = base_tree.resolve()
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIPPED_DIRS)
        for filename in sorted(filenames):
            if not pending:
                return tuple(sorted(found.items()))
            path = Path(current) / filename
            relative = path.relative_to(root)
            if not is_witness_file(relative):
                continue
            files_seen += 1
            if files_seen > MAX_WITNESS_FILES:
                return tuple(sorted(found.items()))
            try:
                if path.is_symlink():
                    continue
                size = path.stat().st_size
                if size > MAX_WITNESS_FILE_BYTES:
                    continue
                bytes_seen += size
                if bytes_seen > MAX_WITNESS_TOTAL_BYTES:
                    return tuple(sorted(found.items()))
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for literal in list(pending):
                if any(form in text for form in _quoted_forms(literal)):
                    found[literal] = relative.as_posix()
                    pending.discard(literal)
    return tuple(sorted(found.items()))


def failure_type(failure_message: str) -> str:
    """The exception type a JUnit failure message names ("Type: text"), or ""."""
    head = failure_message.split(":", 1)[0].strip() if failure_message else ""
    return head if head.isidentifier() or head.replace(".", "").isidentifier() else ""


def _rejecting_origin(
    origins: tuple[RaiseOrigin, ...],
    changed: frozenset[int],
    kinds: dict[int, str],
    failure: str,
) -> RaiseOrigin | None:
    """The first origin that is a raise/assert on a changed line, escaped the
    anchored code, and is consistent with the failure the test reported: either
    the same exception type, or a test-level failure (assertion, pytest.fail)
    that the escaped rejection can have caused."""
    reported = failure_type(failure).rsplit(".", 1)[-1]
    for origin in origins:
        if origin.line not in changed or kinds.get(origin.line) not in REJECTING_STATEMENTS:
            continue
        if not origin.escaped:
            continue
        if reported in TEST_LEVEL_FAILURES or reported == origin.exception_type:
            return origin
    return None


def observe_intent(
    *,
    path: str,
    changed_lines: tuple[int, ...],
    head_source: str,
    test_source: str,
    head_origins: list[tuple[RaiseOrigin, ...]],
    base_tree: Path,
    head_failures: list[str] | None = None,
    truncated: bool = False,
) -> IntentObservation | str:
    """The intent observation for one differential, or the reason it cannot be
    made (a string; the caller DEFERs and buys nothing)."""
    if truncated:
        return (
            "the raise-origin record is incomplete (the tracer hit its record bound); "
            "the failure origin cannot be classified"
        )
    changed = frozenset(changed_lines)
    failures = list(head_failures or [""] * len(head_origins))
    if len(failures) < len(head_origins):
        failures += [""] * (len(head_origins) - len(failures))
    kinds = statement_kinds(head_source)
    any_on_changed = any(
        origin.line in changed for origins in head_origins for origin in origins
    )
    if kinds is None and any_on_changed:
        return (
            f"the anchored file {path} could not be parsed on the host; a failure origin "
            "on a changed line cannot be classified"
        )
    kinds = kinds or {}
    rejecting = [
        _rejecting_origin(origins, changed, kinds, failure)
        for origins, failure in zip(head_origins, failures, strict=True)
    ]
    present = [origin for origin in rejecting if origin is not None]
    if present and len(present) != len(rejecting):
        return "head runs disagree on whether the failure was raised from a changed line"
    if not present:
        first = head_origins[0][0] if head_origins and head_origins[0] else None
        return IntentObservation(
            policy_version=INTENT_POLICY_VERSION,
            path=path,
            changed_lines=tuple(changed_lines),
            origin_line=first.line if first is not None else 0,
            origin_statement=(kinds.get(first.line, "other") if first is not None else ""),
            exception_type=first.exception_type if first is not None else "",
            new_rejection=False,
            rejected_inputs=(),
            witnesses=(),
            head_runs_observed=len(head_origins),
        )
    signatures = {(origin.line, origin.exception_type) for origin in present}
    if len(signatures) != 1:
        return "head runs disagree on the line or exception of the failure origin"
    origin = present[0]
    literals = string_literals(test_source)
    identified: set[str] | None = None
    for run_origin in present:
        found = set(identify_rejected_inputs(literals, run_origin))
        identified = found if identified is None else identified & found
    rejected = tuple(sorted(identified or ()))
    return IntentObservation(
        policy_version=INTENT_POLICY_VERSION,
        path=path,
        changed_lines=tuple(changed_lines),
        origin_line=origin.line,
        origin_statement=kinds.get(origin.line, "other"),
        exception_type=origin.exception_type,
        new_rejection=True,
        rejected_inputs=rejected,
        witnesses=find_witnesses(base_tree, rejected) if rejected else (),
        head_runs_observed=len(head_origins),
    )
