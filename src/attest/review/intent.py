"""Observing the intent of a head failure (D-102, tightened after the D-049 review):
the raise origins the tracer recorded, the statement kind from the head source, the
rejected inputs from the generated test's literals, and their witnesses in the base
tree. D-120 adds one more file read: the base revision of the anchored file, so that an
assertion resting only on constants the change substituted can be recognised as such.
D-127 adds a second walk -- of the base tree for the *specifications* of the values the
failing assertion pins, and of the head tree for whether this change left them standing.
D-132 adds three more reads and no more power: the head runs' JUnit longrepr, to locate the
assertion that actually failed; the anchored file's own def/class ranges, to name the symbols
this change touched; and both revisions of every file the diff touched, to see whether the
author also moved a test, a docstring, a documentation or changelog line, or an inline
comment about one of those symbols. File reads only: no execution, no model, no repository
command.

Fail closed at every step: an unreadable or unparsable anchored file, a truncated
origin record, or head runs that disagree all DEFER instead of classifying; an
unreadable base or head tree yields no specification, which sends a value mismatch to
the drawer rather than publishing it. A longrepr that names no line of the generated test,
or head runs that name different lines, locates no failing assertion and so pins nothing.
"""

from __future__ import annotations

import ast
import io
import json
import os
import re
import tokenize
from dataclasses import dataclass
from pathlib import Path

from attest.certification.intent import (
    GENERIC_VALUE_REPRS,
    INTENT_POLICY_VERSION,
    REJECTING_STATEMENTS,
    IntentObservation,
)

MAX_ORIGIN_RECORDS = 256
MAX_MESSAGE_CHARS = 2_000
MAX_VALUE_CHARS = 500
MAX_VALUES = 16
MIN_LITERAL_CHARS = 2
MAX_CONSTANTS = 4_000  # bound on the constants read from one revision of one file
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
MAX_INTENT_FILES = 500  # changed files read for D-132's intent evidence
MAX_INTENT_EVIDENCE = 16  # sites recorded; the rule needs one
MAX_SYMBOLS = 200
MIN_SYMBOL_CHARS = 3  # a name shorter than this matches prose by accident
# D-132 (c): where a project announces a deliberate change in prose
PROSE_SUFFIXES = (*DOC_SUFFIXES, ".txt")
PROSE_DIRS = frozenset({"changelog", "changes", "news", "docs", "doc"})
PROSE_NAMES = ("CHANGES", "CHANGELOG", "NEWS", "HISTORY", "RELEASE", "README")
# the innermost frame pytest's longrepr attributes the failure to, when it is a
# line of the generated reproduction: "<path>test_repro.py:<line>: <Type>"
_LONGREPR_FRAME = re.compile(r"^(?P<path>\S*test_repro\.py):(?P<line>\d+):", re.MULTILINE)
SPEC_DIRS = frozenset({"tests", "test", "testing"})  # a .py here asserts, wherever named
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


def constant_values(source: str) -> tuple[tuple[str, str], ...] | None:
    """Every literal constant of ``source`` as (type name, repr), or ``None`` when
    the source cannot be parsed. The type is carried so that ``"1"`` and ``1`` are
    never the same constant."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    found: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and node.value is not Ellipsis:
            found.add((type(node.value).__name__, repr(node.value)[:MAX_VALUE_CHARS]))
            if len(found) > MAX_CONSTANTS:
                return None
    return tuple(sorted(found))


def assertion_constant_values(test_source: str) -> tuple[tuple[str, object], ...] | None:
    """The literal constants the ``assert`` statements of ``test_source`` rest on,
    as (type name, value): every constant of an ``assert``'s *condition*, minus the
    ones that only *address* a value -- dictionary keys and subscripts -- which name
    a field rather than pin its content. An assertion's message is prose the
    generator wrote about the failure, not part of what the assertion proves, so it
    is not read. ``None`` when the source cannot be parsed."""
    try:
        tree = ast.parse(test_source)
    except (SyntaxError, ValueError):
        return None
    addressing: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            addressing.update(id(key) for key in node.keys if key is not None)
        elif isinstance(node, ast.Subscript):
            addressing.add(id(node.slice))
    found: dict[tuple[str, str], object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        for inner in ast.walk(node.test):
            if (
                isinstance(inner, ast.Constant)
                and inner.value is not Ellipsis
                and id(inner) not in addressing
                and not (isinstance(inner.value, str) and len(inner.value.strip()) == 0)
            ):
                found[(type(inner.value).__name__, repr(inner.value)[:MAX_VALUE_CHARS])] = (
                    inner.value
                )
                if len(found) > MAX_CONSTANTS:
                    return None
    return tuple((kind, found[(kind, text)]) for kind, text in sorted(found))


def assertion_constants(test_source: str) -> tuple[tuple[str, str], ...] | None:
    """The same constants as (type name, ``repr``); ``None`` when unparsable."""
    values = assertion_constant_values(test_source)
    if values is None:
        return None
    return tuple((kind, repr(value)[:MAX_VALUE_CHARS]) for kind, value in values)


def _operand_constants(node: ast.AST) -> list[object]:
    """The constants of one comparison operand: what the assertion pins.

    A call's arguments are not descended into -- they are the inputs the
    assertion feeds, and only the call's *result* is compared -- nor is a
    subscript's slice or a dictionary's keys, which address a value rather than
    state it. So in ``getattr(w, "__wrapped__") is f`` the operand pins nothing,
    and in ``run_path("calc.py")["value"]() == 1`` it pins ``1``.
    """
    found: list[object] = []
    stack: list[ast.AST] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.Constant):
            found.append(current.value)
        elif isinstance(current, ast.Call):
            continue
        elif isinstance(current, ast.Subscript):
            stack.append(current.value)
        elif isinstance(current, ast.Dict):
            stack.extend(value for value in current.values if value is not None)
        else:
            stack.extend(ast.iter_child_nodes(current))
    return found


def assertion_pinned_values(source: str) -> tuple[tuple[str, object], ...] | None:
    """D-127: the values the ``assert`` statements of ``source`` **pin**, as
    (type name, value) -- the constant operands of their comparisons.

    Narrower than D-120's :func:`assertion_constants`, and for a different
    question. D-120 asks whether the assertion rests *only* on constants the
    change substituted, so every literal in the condition counts, inputs
    included. D-127 asks what old value the assertion states, and an assertion
    states the side it compares against: the inputs it passes and the names it
    looks up are how it reaches the value, not the value. ``None`` when the
    source cannot be parsed.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    found: dict[tuple[str, str], object] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        for inner in ast.walk(node.test):
            if not isinstance(inner, ast.Compare):
                continue
            for operand in (inner.left, *inner.comparators):
                for value in _operand_constants(operand):
                    if value is Ellipsis:
                        continue
                    if isinstance(value, str) and len(value.strip()) == 0:
                        continue
                    found[(type(value).__name__, repr(value)[:MAX_VALUE_CHARS])] = value
                    if len(found) > MAX_CONSTANTS:
                        return None
    return tuple((kind, found[(kind, text)]) for kind, text in sorted(found))


def docstring_texts(source: str) -> tuple[str, ...]:
    """Every module, class and function docstring of ``source``; () when unparsable.
    A docstring is where a Python file *writes down* what it returns."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ()
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                found.append(doc)
    return tuple(found)


def is_spec_file(relative: Path) -> bool:
    """A base-tree file that can *specify* a value: a test module, which asserts
    it, or documentation, which writes it down. Narrower than a witness file --
    a fixture holds inputs, not statements about results."""
    name = relative.name
    if name.endswith(DOC_SUFFIXES) or name.upper().startswith("README"):
        return True
    if not name.endswith(".py"):
        return False
    return (
        name == "conftest.py"
        or name.startswith("test_")
        or name.endswith("_test.py")
        or any(part in SPEC_DIRS for part in relative.parts[:-1])
    )


def specified_by(relative: Path, text: str, pinned: tuple[tuple[str, object], ...]) -> set[str]:
    """The ``repr`` of every pinned value this file specifies.

    A Python file specifies a value by asserting it, or by quoting it in a
    docstring; a documentation file, by quoting it in its prose. Only string
    values can be quoted: a bare number in prose names nothing in particular.
    """
    found: set[str] = set()
    if relative.suffix == ".py":
        asserted = assertion_pinned_values(text)
        if asserted:
            keys = {(kind, repr(value)[:MAX_VALUE_CHARS]) for kind, value in asserted}
            found |= {
                repr(value)[:MAX_VALUE_CHARS]
                for kind, value in pinned
                if (kind, repr(value)[:MAX_VALUE_CHARS]) in keys
            }
        prose: tuple[str, ...] = docstring_texts(text)
    else:
        prose = (text,)
    for _kind, value in pinned:
        if not isinstance(value, str) or len(value.strip()) < MIN_LITERAL_CHARS:
            continue
        if any(form in body for body in prose for form in _quoted_forms(value)):
            found.add(repr(value)[:MAX_VALUE_CHARS])
    return found


def find_specifications(
    *,
    base_tree: Path,
    head_tree: Path | None,
    pinned: tuple[tuple[str, object], ...],
    anchored: str,
) -> tuple[tuple[tuple[str, str], ...], tuple[tuple[str, str], ...]]:
    """D-127: (the base tree's specification of each pinned value, the sites this
    change no longer specifies at head).

    The base walk is bounded exactly as the witness walk is, takes the first site
    per value in a deterministic order, and reads the anchored file itself as well
    -- its docstrings are where a function states what it returns. Without a head
    tree nothing can be shown to stand, so every site found is reported as
    rewritten and the receipt goes to the drawer.
    """
    if not pinned:
        return (), ()
    pending = {repr(value)[:MAX_VALUE_CHARS] for _kind, value in pinned}
    found: dict[str, str] = {}
    files_seen = 0
    bytes_seen = 0
    root = base_tree.resolve()
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIPPED_DIRS)
        for filename in sorted(filenames):
            if not pending:
                break
            path = Path(current) / filename
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if not is_spec_file(relative) and relative.as_posix() != anchored:
                continue
            files_seen += 1
            if files_seen > MAX_WITNESS_FILES:
                pending.clear()
                break
            try:
                if path.is_symlink():
                    continue
                size = path.stat().st_size
                if size > MAX_WITNESS_FILE_BYTES:
                    continue
                bytes_seen += size
                if bytes_seen > MAX_WITNESS_TOTAL_BYTES:
                    pending.clear()
                    break
                body = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for value in specified_by(relative, body, pinned) & pending:
                found[value] = relative.as_posix()
                pending.discard(value)
        if not pending:
            break
    specified = tuple(sorted(found.items()))
    respecified: list[tuple[str, str]] = []
    for value, site in specified:
        still: set[str] = set()
        if head_tree is not None:
            head_path = head_tree / site
            try:
                if not head_path.is_symlink() and head_path.is_file():
                    still = specified_by(
                        Path(site),
                        head_path.read_text(encoding="utf-8", errors="replace"),
                        pinned,
                    )
            except OSError:
                still = set()
        if value not in still:
            respecified.append((value, site))
    return specified, tuple(respecified)


def failing_assertion_line(detail: str) -> int:
    """D-132 (a): the line of the generated reproduction the head run failed on.

    ``detail`` is pytest's longrepr as the JUnit ``<failure>`` body carries it.
    Its frames are printed outermost first, so the **last** frame naming
    ``test_repro.py`` is where the exception was actually raised -- the assertion
    in the simple case, and the stub's own ``raise`` when the test defines one.
    0 when no frame of the reproduction is named, which is a crash inside the
    code under test and not a value mismatch anyway.
    """
    if not detail:
        return 0
    matches = _LONGREPR_FRAME.findall(detail)
    if not matches:
        return 0
    try:
        return int(matches[-1][1])
    except ValueError:  # pragma: no cover - the pattern only matches digits
        return 0


def assertion_pinned_values_at(
    source: str, line: int
) -> tuple[tuple[str, object], ...] | None:
    """D-132 (a): :func:`assertion_pinned_values`, restricted to the ``assert``
    statement that spans ``line``.

    ``None`` when the source cannot be parsed; ``()`` when ``line`` is not inside
    an ``assert`` at all -- a bare ``raise`` in a stub the test defines, a call
    inside ``pytest.raises``, a fixture. That is the fail-closed case and it is
    the common one: what did not fail on an assertion states no old value.
    """
    if line < 1:
        return ()
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        end = node.end_lineno or node.lineno
        if node.lineno <= line <= end:
            return assertion_pinned_values(ast.unparse(node))
    return ()


def symbol_ranges(source: str) -> tuple[tuple[str, int, int], ...] | None:
    """Every def/class of ``source`` as (name, first line, last line); ``None``
    when it cannot be parsed. Plain names, not qualified ones: a changelog entry
    or a docstring names a function the way a reader does."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return None
    found: list[tuple[str, int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            found.append((node.name, node.lineno, node.end_lineno or node.lineno))
            if len(found) > MAX_SYMBOLS:
                return None
    return tuple(sorted(found))


def anchored_symbols(
    *, base_source: str, head_source: str, changed_lines: tuple[int, ...]
) -> tuple[str, ...]:
    """D-132 (c): the def/class names this change touched in the anchored file --
    those whose head body spans a changed line, plus those the change removed
    from the file outright. A deletion has no head node to intersect, and a
    deleted symbol is exactly what the shadow findings are about."""
    head = symbol_ranges(head_source)
    base = symbol_ranges(base_source)
    changed = frozenset(changed_lines)
    names: set[str] = set()
    if head is not None:
        head_names = {name for name, _start, _end in head}
        names |= {
            name
            for name, start, end in head
            if any(start <= line <= end for line in changed)
        }
        if base is not None:
            names |= {name for name, _start, _end in base if name not in head_names}
    return tuple(sorted(names))


def prose_lines(source: str) -> frozenset[str]:
    """Every comment and docstring line of a Python source, whitespace-collapsed.
    This is what a Python file says *about* its code rather than as code."""
    found: set[str] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                text = " ".join(token.string.lstrip("#").split())
                if text:
                    found.add(text)
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    for doc in docstring_texts(source):
        found |= {" ".join(line.split()) for line in doc.splitlines() if line.strip()}
    return frozenset(found)


def located_prose_lines(source: str) -> tuple[tuple[int, str], ...]:
    """The same prose, with the line each piece starts on -- so that a comment
    can be placed inside the body of the symbol under test."""
    found: set[tuple[int, str]] = set()
    try:
        for token in tokenize.generate_tokens(io.StringIO(source).readline):
            if token.type == tokenize.COMMENT:
                text = " ".join(token.string.lstrip("#").split())
                if text:
                    found.add((token.start[0], text))
    except (tokenize.TokenError, IndentationError, SyntaxError, ValueError):
        pass
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return tuple(sorted(found))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        body = getattr(node, "body", None)
        if not body or not isinstance(body[0], ast.Expr):
            continue
        literal = body[0].value
        if not (isinstance(literal, ast.Constant) and isinstance(literal.value, str)):
            continue
        for offset, line in enumerate(literal.value.splitlines()):
            if line.strip():
                found.add((body[0].lineno + offset, " ".join(line.split())))
    return tuple(sorted(found))


def is_prose_file(relative: Path) -> bool:
    """A file whose *whole text* is prose: documentation, a changelog, a release
    note. Where a project announces on purpose what it changed."""
    name = relative.name
    if name.endswith(PROSE_SUFFIXES):
        return True
    if any(part.lower() in PROSE_DIRS for part in relative.parts[:-1]):
        return True
    return name.upper().startswith(PROSE_NAMES)


def _mentions(text: str, symbols: tuple[str, ...]) -> str | None:
    """The first of ``symbols`` this text names as a word, or ``None``. A name
    shorter than :data:`MIN_SYMBOL_CHARS` is not matched: it collides with
    English."""
    for symbol in symbols:
        if len(symbol) < MIN_SYMBOL_CHARS:
            continue
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(symbol)}(?![A-Za-z0-9_])", text):
            return symbol
    return None


def _read(tree: Path | None, relative: str) -> str | None:
    if tree is None:
        return None
    path = tree / relative
    try:
        if path.is_symlink() or not path.is_file():
            return None
        if path.stat().st_size > MAX_WITNESS_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _moved_lines(base: str | None, head: str | None) -> frozenset[str]:
    """The whitespace-collapsed lines this change added or removed."""
    def lines(text: str | None) -> frozenset[str]:
        if text is None:
            return frozenset()
        return frozenset(
            collapsed for raw in text.splitlines() if (collapsed := " ".join(raw.split()))
        )

    before, after = lines(base), lines(head)
    return (before - after) | (after - before)


def find_intent_evidence(
    *,
    base_tree: Path,
    head_tree: Path | None,
    changed_files: tuple[str, ...],
    anchored: str,
    base_source: str,
    head_source: str,
    changed_lines: tuple[int, ...],
    symbols: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """D-132 (c): the places this diff states what it meant, as (symbol, file).

    Two shapes, because "touching the symbol" means two different things:

    * **in the anchored file**, a comment or docstring line the change added or
      removed *inside the body of a touched symbol* -- position is the link, and
      the urllib3 control is exactly this: three lines widening a tolerated-errno
      set with the comment above them rewritten in the same hunk;
    * **in every other changed file**, an added or removed line that **names** a
      touched symbol -- a test the author moved, a changelog entry, a docs
      sentence, a comment. For a Python file that is not a test only its prose is
      compared, so that a refactor of unrelated code is not read as intent.

    At most one site per file, so an enormous diff cannot flood the record.
    """
    if not symbols:
        return ()
    found: dict[str, str] = {}
    head_ranges = symbol_ranges(head_source) or ()
    base_ranges = symbol_ranges(base_source) or ()
    touched = set(symbols)
    head_spans = [(s, e) for name, s, e in head_ranges if name in touched]
    base_spans = [(s, e) for name, s, e in base_ranges if name in touched]
    for relative in sorted(set(changed_files))[:MAX_INTENT_FILES]:
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            continue
        base_text = _read(base_tree, relative)
        head_text = _read(head_tree, relative)
        if relative == anchored:
            # position, not vocabulary: prose the change moved inside a touched body
            before = prose_lines(base_source)
            after = prose_lines(head_source)
            added = [
                (line, text)
                for line, text in located_prose_lines(head_source)
                if text not in before
                and any(start <= line <= end for start, end in head_spans)
            ]
            removed = [
                (line, text)
                for line, text in located_prose_lines(base_source)
                if text not in after
                and any(start <= line <= end for start, end in base_spans)
            ]
            # ...and prose anywhere in the file that *names* one: a module
            # docstring rewritten to explain a function it no longer has sits
            # inside no symbol's body, and is the plainest statement of intent
            # the file can carry.
            if not added and not removed:
                for text in sorted((after - before) | (before - after)):
                    named_here = _mentions(text, symbols)
                    if named_here is not None:
                        found[relative] = named_here
                        break
                continue
            if added or removed:
                line = (added or removed)[0][0]
                # the innermost touched symbol containing it: a comment inside a
                # method is about the method, not about its class
                enclosing = sorted(
                    (
                        (end - start, name)
                        for name, start, end in (head_ranges if added else base_ranges)
                        if name in touched and start <= line <= end
                    )
                )
                found[relative] = enclosing[0][1] if enclosing else symbols[0]
            continue
        if base_text is None and head_text is None:
            continue
        if is_prose_file(path) or is_spec_file(path):
            moved = _moved_lines(base_text, head_text)
        elif path.suffix == ".py":
            base_prose = prose_lines(base_text) if base_text is not None else frozenset()
            head_prose = prose_lines(head_text) if head_text is not None else frozenset()
            moved = (base_prose - head_prose) | (head_prose - base_prose)
        else:
            continue
        for text in sorted(moved):
            named = _mentions(text, symbols)
            if named is not None:
                found[relative] = named
                break
        if len(found) >= MAX_INTENT_EVIDENCE:
            break
    return tuple(sorted((symbol, site) for site, symbol in found.items()))[
        :MAX_INTENT_EVIDENCE
    ]


def observe_constant_substitution(
    *, base_source: str, head_source: str, test_source: str
) -> tuple[bool, tuple[str, ...]]:
    """D-120: (the failing assertion rests only on constants this change
    substituted, those constants).

    A constant is *substituted* when the change removed it from the anchored file
    -- it occurs in the base revision and nowhere in the head revision -- and put
    one of the same type in its place. A constant merely deleted (nothing of its
    type added) is not a substitution: losing a validation message is a
    regression, not a retuning. Fails closed on an unparsable revision by
    reporting no substitution, which leaves the D-102 classification alone.
    """
    base_constants = constant_values(base_source)
    head_constants = constant_values(head_source)
    asserted = assertion_constants(test_source)
    if base_constants is None or head_constants is None or not asserted:
        return False, ()
    removed = set(base_constants) - set(head_constants)
    added_types = {kind for kind, _value in set(head_constants) - set(base_constants)}
    substituted = {
        (kind, value) for kind, value in removed if kind in added_types
    }
    if not substituted or not set(asserted) <= substituted:
        return False, ()
    return True, tuple(sorted(value for _kind, value in asserted))


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
    base_source: str,
    test_source: str,
    head_origins: list[tuple[RaiseOrigin, ...]],
    base_tree: Path,
    head_tree: Path | None = None,
    head_failures: list[str] | None = None,
    head_failure_details: list[str] | None = None,
    changed_files: tuple[str, ...] = (),
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
    test_level = all(
        failure_type(failure).rsplit(".", 1)[-1] in TEST_LEVEL_FAILURES for failure in failures
    )
    substitution, asserted = (
        observe_constant_substitution(
            base_source=base_source, head_source=head_source, test_source=test_source
        )
        if test_level
        else (False, ())
    )
    # D-132 (a): the pinned set is the assertion the head runs actually failed
    # on. Every run must name the same line of the reproduction; runs that
    # disagree, or a longrepr that names none, locate nothing and pin nothing.
    details = list(head_failure_details or [])
    if len(details) < len(head_origins):
        details += [""] * (len(head_origins) - len(details))
    located = {failing_assertion_line(detail) for detail in details[: len(head_origins)]}
    failing_line = located.pop() if len(located) == 1 else 0
    pinned = (
        assertion_pinned_values_at(test_source, failing_line)
        if test_level and failing_line
        else None
    )
    symbols = (
        anchored_symbols(
            base_source=base_source, head_source=head_source, changed_lines=changed_lines
        )
        if test_level
        else ()
    )
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
        # D-127: no rejecting origin and every head run failed on the test's own
        # assertion -- the differential shows a changed *value*, and it publishes
        # only against a base specification this change left standing.
        # D-132 (b): a generic constant is not something a base tree can specify,
        # so it is not searched for and not required.
        distinctive = tuple(
            (kind, value)
            for kind, value in (pinned or ())
            if repr(value)[:MAX_VALUE_CHARS] not in GENERIC_VALUE_REPRS
        )
        specified, respecified = (
            find_specifications(
                base_tree=base_tree, head_tree=head_tree, pinned=distinctive, anchored=path
            )
            if distinctive
            else ((), ())
        )
        # D-132 (c): what the same diff says about the symbols it touched
        evidence = (
            find_intent_evidence(
                base_tree=base_tree,
                head_tree=head_tree,
                changed_files=changed_files or (path,),
                anchored=path,
                base_source=base_source,
                head_source=head_source,
                changed_lines=tuple(changed_lines),
                symbols=symbols,
            )
            if test_level
            else ()
        )
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
            constant_substitution=substitution,
            asserted_constants=asserted,
            value_mismatch=test_level,
            pinned_values=tuple(
                repr(value)[:MAX_VALUE_CHARS] for _kind, value in (pinned or ())
            ),
            value_specified=specified,
            value_respecified=respecified,
            failing_assertion_line=failing_line,
            anchored_symbols=symbols,
            intent_evidence=evidence,
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
        constant_substitution=substitution,
        asserted_constants=asserted,
    )
