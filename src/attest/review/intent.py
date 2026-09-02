"""Observing the intent of a head failure (D-102): the raise origins the tracer
recorded, the statement kind from the head source, the rejected inputs from the
generated test's literals, and their witnesses in the base tree. File reads
only: no execution, no model, no repository command.
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

MAX_ORIGIN_RECORDS = 32
MAX_MESSAGE_CHARS = 2_000
MAX_VALUE_CHARS = 500
MAX_VALUES = 16
MIN_LITERAL_CHARS = 2
MAX_WITNESS_FILES = 5_000
MAX_WITNESS_FILE_BYTES = 1_000_000
MAX_WITNESS_TOTAL_BYTES = 64_000_000
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
WITNESS_SUFFIXES = (".md", ".rst", ".txt")
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


def parse_raise_origins(marker: bytes | None) -> tuple[RaiseOrigin, ...]:
    """The tracer's ``raise-origin`` artifact, fail-soft: malformed rows are dropped."""
    if not marker:
        return ()
    try:
        rows = json.loads(marker.decode("utf-8", errors="replace"))
    except ValueError:
        return ()
    if not isinstance(rows, list):
        return ()
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
            )
        )
    return tuple(origins)


def statement_kinds(source: str) -> dict[int, str]:
    """Line -> ``raise`` | ``assert`` for every line such a statement spans."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return {}
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
    """The string constants of the generated test (f-string parts included):
    the only inputs the test can have fed the code under test verbatim."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ()
    literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            if len(value.strip()) >= MIN_LITERAL_CHARS:
                literals.add(value)
    # a module/function docstring is prose about the test, never an input
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            docstring = ast.get_docstring(node, clean=False)
            if docstring is not None:
                literals.discard(docstring)
    return tuple(sorted(literals))


def identify_rejected_inputs(literals: tuple[str, ...], origin: RaiseOrigin) -> tuple[str, ...]:
    """The test literals that reached the raising frame: present in the
    exception message or in a string-typed local of that frame."""
    haystacks = (origin.message, *origin.values)
    return tuple(literal for literal in literals if any(literal in text for text in haystacks))


def is_witness_file(relative: Path) -> bool:
    """A file of the base tree that can attest an input as legitimate: a test
    module, a fixture or example directory, or documentation."""
    parts = relative.parts[:-1]
    if any(part in WITNESS_DIRS for part in parts):
        return True
    name = relative.name
    if name.endswith(WITNESS_SUFFIXES) or name.upper().startswith("README"):
        return True
    return name == "conftest.py" or (
        name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))
    )


def find_witnesses(base_tree: Path, literals: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    """(literal, relative path) for every literal found verbatim in a witness file
    of ``base_tree``; bounded walk, first witness per literal."""
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
                size = path.stat().st_size
                if size > MAX_WITNESS_FILE_BYTES or path.is_symlink():
                    continue
                bytes_seen += size
                if bytes_seen > MAX_WITNESS_TOTAL_BYTES:
                    return tuple(sorted(found.items()))
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for literal in list(pending):
                if literal in text:
                    found[literal] = relative.as_posix()
                    pending.discard(literal)
    return tuple(sorted(found.items()))


def _rejecting_origin(
    origins: tuple[RaiseOrigin, ...], changed: frozenset[int], kinds: dict[int, str]
) -> RaiseOrigin | None:
    for origin in origins:
        if origin.line in changed and kinds.get(origin.line) in REJECTING_STATEMENTS:
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
) -> IntentObservation | str:
    """The intent observation for one differential, or the reason the head runs
    could not be read consistently (a string; the caller DEFERs)."""
    changed = frozenset(changed_lines)
    kinds = statement_kinds(head_source)
    rejecting = [_rejecting_origin(origins, changed, kinds) for origins in head_origins]
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
