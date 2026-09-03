"""Semantic diff planning and bounded context retrieval for the proposer (R-01).

The proposer used to see the raw diff and nothing else, so a defect that
manifests outside the hunks — a caller whose callee's signature changed, a
definition that spans beyond the 200-line window, a test that already pins
the old behaviour — was invisible. The planner splits the merge-base diff
into stable units, retrieves bounded read-only excerpts from the repository
(definitions, callers, old-side sources, test references), records every
omission, and never truncates silently. Retrieval reads only the reviewed
repository; nothing here calls a model or spends budget.
"""

from __future__ import annotations

import ast
import hashlib
import os
import re
import subprocess
import warnings
from dataclasses import dataclass
from pathlib import Path

from attest.review.diffs import DiffInfo, parse_diff

PLAN_SCHEMA_VERSION = "attest.review-plan.v1"

MAX_UNIT_CHARS = 30_000  # diff + context handed to one proposer unit
MAX_CONTEXT_CHARS = 10_000  # context appendix per unit
MAX_DEFINITION_LINES = 80
MAX_CALLERS_PER_SYMBOL = 4
CALLER_CONTEXT_LINES = 3
MAX_TEST_REFERENCES = 8
MAX_SCANNED_FILES = 4_000
MAX_SCANNED_FILE_BYTES = 400_000
_SKIP_DIRS = {".git", ".attest", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}

_DEF_RE = re.compile(r"^[-+]\s*(?:async\s+)?(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+?) b/(.+)$")
_HUNK_HEADER_RE = re.compile(r"^@@ [^@]* @@")
_HUNK_RANGES_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_IMPORT_RE = re.compile(r"^(?:import\s|from\s+\S+\s+import\s)")
MAX_IMPORT_LINES = 40
# names too generic to locate callers or tests by text: retrieving them would
# only fill the context budget with unrelated matches (the omission is recorded)
_GENERIC_NAMES = frozenset(
    {
        "add",
        "append",
        "apply",
        "build",
        "call",
        "check",
        "clean",
        "close",
        "create",
        "delete",
        "execute",
        "format",
        "get",
        "handle",
        "init",
        "load",
        "main",
        "open",
        "parse",
        "post",
        "process",
        "put",
        "read",
        "remove",
        "render",
        "reset",
        "run",
        "save",
        "set",
        "setup",
        "start",
        "stop",
        "teardown",
        "update",
        "validate",
        "write",
    }
)
_MIN_SEARCHABLE_NAME = 4


def _searchable(name: str) -> bool:
    return len(name) >= _MIN_SEARCHABLE_NAME and name not in _GENERIC_NAMES


@dataclass(frozen=True)
class ContextSnippet:
    kind: str  # "imports" | "definition" | "caller" | "old_side" | "test"
    symbol: str
    path: str
    start: int
    end: int
    text: str

    def render(self) -> str:
        if self.kind == "test":
            return f"- {self.path}::{self.text} (references `{self.symbol}`)"
        title = {
            "imports": "module imports at head",
            "definition": f"definition of `{self.symbol}` at head",
            "caller": f"caller of `{self.symbol}` outside the diff",
            "old_side": f"definition of `{self.symbol}` at the merge-base (old side)",
        }[self.kind]
        return f"### {title}: {self.path}:{self.start}-{self.end}\n```python\n{self.text}\n```"


@dataclass(frozen=True)
class PlanUnit:
    unit_id: str
    files: tuple[str, ...]
    diff_text: str
    context: tuple[ContextSnippet, ...]
    omissions: tuple[str, ...]

    def diff(self) -> DiffInfo:
        return parse_diff(self.diff_text)

    def prompt_context(self) -> str:
        if not self.context:
            return ""
        sections = [snippet.render() for snippet in self.context if snippet.kind != "test"]
        tests = [snippet.render() for snippet in self.context if snippet.kind == "test"]
        if tests:
            sections.append("### existing tests referencing changed symbols\n" + "\n".join(tests))
        return "\n\n".join(sections)


@dataclass(frozen=True)
class ReviewPlan:
    schema_version: str
    base_ref: str
    units: tuple[PlanUnit, ...]
    digest: str

    def to_ledger_row(self, task_id: str) -> dict[str, object]:
        return {
            "kind": "review_plan",
            "schema_version": self.schema_version,
            "task_id": task_id,
            "plan_digest": self.digest,
            "units": [
                {
                    "unit_id": unit.unit_id,
                    "files": list(unit.files),
                    "diff_chars": len(unit.diff_text),
                    "context_chars": len(unit.prompt_context()),
                    "context": {
                        kind: sum(1 for s in unit.context if s.kind == kind)
                        for kind in ("imports", "definition", "caller", "old_side", "test")
                    },
                    "omissions": list(unit.omissions),
                }
                for unit in self.units
            ],
        }


# ----------------------------------------------------------------- diff split


def split_diff_by_file(text: str) -> dict[str, str]:
    """Per-file diff blocks keyed by the new-side path, in diff order."""
    blocks: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        header = _DIFF_GIT_RE.match(line)
        if header:
            if current is not None:
                blocks[current] = "\n".join(lines) + "\n"
            current = header.group(2).strip()
            lines = [line]
            continue
        if current is not None:
            lines.append(line)
    if current is not None:
        blocks[current] = "\n".join(lines) + "\n"
    return blocks


@dataclass(frozen=True)
class ChangedSymbol:
    name: str
    path: str
    kind: str  # "added" | "removed" | "changed"


def hunk_ranges(block: str) -> list[tuple[int, int, int, int]]:
    """(old_start, old_end, new_start, new_end) per hunk, inclusive, 1-based."""
    ranges = []
    for line in block.splitlines():
        m = _HUNK_RANGES_RE.match(line)
        if not m:
            continue
        old_start = int(m.group(1))
        old_count = int(m.group(2)) if m.group(2) is not None else 1
        new_start = int(m.group(3))
        new_count = int(m.group(4)) if m.group(4) is not None else 1
        ranges.append(
            (
                old_start,
                old_start + max(old_count, 1) - 1,
                new_start,
                new_start + max(new_count, 1) - 1,
            )
        )
    return ranges


def _enclosing_definitions(source: str | None, spans: list[tuple[int, int]]) -> set[str]:
    """Names of the innermost function (else class) definitions touching ``spans``."""
    if not source:
        return set()
    tree = _parse(source)
    if tree is None:
        return set()
    names: set[str] = set()
    for start, end in spans:
        best: tuple[int, str] | None = None  # (span length, name): innermost wins
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            node_end = node.end_lineno or node.lineno
            if node_end < start or node.lineno > end:
                continue
            length = node_end - node.lineno
            if best is None or length < best[0]:
                best = (length, node.name)
        if best is not None:
            names.add(best[1])
    return names


def changed_symbols(
    path: str, block: str, head_source: str | None, base_source: str | None
) -> list[ChangedSymbol]:
    """Definitions changed by the diff: def/class lines on either side, plus the
    definitions enclosing each hunk's old and new line ranges."""
    removed: set[str] = set()
    added: set[str] = set()
    for line in block.splitlines():
        m = _DEF_RE.match(line)
        if not m:
            continue
        (removed if line.startswith("-") else added).add(m.group(1))
    ranges = hunk_ranges(block)
    head_names = _enclosing_definitions(head_source, [(r[2], r[3]) for r in ranges])
    base_names = _enclosing_definitions(base_source, [(r[0], r[1]) for r in ranges])
    symbols = []
    for name in sorted(removed | added | head_names | base_names):
        in_base = name in removed or name in base_names
        in_head = name in added or name in head_names
        if name in removed and name not in added and name not in head_names:
            in_head = False
        kind = "changed" if in_base and in_head else ("removed" if in_base else "added")
        symbols.append(ChangedSymbol(name=name, path=path, kind=kind))
    return symbols


# ----------------------------------------------------------------- retrieval


def _python_files(repo: Path) -> list[Path]:
    """Python files under ``repo`` with skipped directories pruned during the walk."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS)
        for name in sorted(filenames):
            if name.endswith(".py"):
                files.append(Path(dirpath) / name)
                if len(files) >= MAX_SCANNED_FILES:
                    return files
    return files


_TestFunction = tuple[str, str, ast.FunctionDef | ast.AsyncFunctionDef, str]


class _Corpus:
    """The repository's Python sources, read once per plan."""

    def __init__(self, repo: Path) -> None:
        self.repo = repo
        self._sources: list[tuple[str, str]] | None = None

    def sources(self) -> list[tuple[str, str]]:
        if self._sources is None:
            loaded: list[tuple[str, str]] = []
            for path in _python_files(self.repo):
                source = _read(path)
                if source is not None:
                    loaded.append((path.relative_to(self.repo).as_posix(), source))
            self._sources = loaded
        return self._sources

    def test_functions(self) -> list[_TestFunction]:
        """(path, source, node, body) for every test function, parsed once."""
        if not hasattr(self, "_tests"):
            found: list[_TestFunction] = []
            for rel, source in self.sources():
                if "test" not in rel.lower():
                    continue
                tree = _parse(source)
                if tree is None:
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                        node.name.startswith("test")
                    ):
                        body = ast.get_source_segment(source, node) or ""
                        found.append((rel, source, node, body))
            self._tests = found
        return self._tests


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > MAX_SCANNED_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def show_file_at(repo: Path, ref: str, path: str) -> str | None:
    listed = subprocess.run(
        ["git", "-C", str(repo), "ls-tree", ref, "--", path], capture_output=True, text=True
    )
    if listed.returncode != 0 or not listed.stdout.strip():
        return None
    shown = subprocess.run(["git", "-C", str(repo), "show", f"{ref}:{path}"], capture_output=True)
    if shown.returncode != 0:
        return None
    return shown.stdout.decode("utf-8", errors="replace")


def _parse(source: str) -> ast.Module | None:
    """Parse without letting a corpus file's escape-sequence warnings leak out."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.parse(source)
    except (ValueError, SyntaxError, RecursionError):
        return None


def _definition_source(source: str, name: str) -> tuple[int, int, str] | None:
    tree = _parse(source)
    if tree is None:
        return None
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and node.name == name
        ):
            start = node.lineno
            end = min(node.end_lineno or node.lineno, start + MAX_DEFINITION_LINES - 1)
            text = "\n".join(source.splitlines()[start - 1 : end])
            return start, end, text
    return None


def _callers(
    corpus: _Corpus, symbol: ChangedSymbol, diff: DiffInfo
) -> tuple[list[ContextSnippet], int]:
    """Call sites of ``symbol`` outside the diff hunks, bounded; returns (kept, dropped)."""
    pattern = re.compile(rf"(?<![\w.]){re.escape(symbol.name)}\s*\(")
    method = re.compile(rf"\.{re.escape(symbol.name)}\s*\(")
    hits: list[ContextSnippet] = []
    for rel, source in corpus.sources():
        if "test" in rel.lower():
            continue  # tests are retrieved separately as references
        lines = source.splitlines()
        for index, line in enumerate(lines, start=1):
            if not (pattern.search(line) or method.search(line)):
                continue
            if _DEF_RE.match("+" + line.strip()):
                continue  # the definition itself
            if rel == symbol.path and diff.anchor_in_hunk(rel, index):
                continue  # already visible in the diff
            start = max(1, index - CALLER_CONTEXT_LINES)
            end = min(len(lines), index + CALLER_CONTEXT_LINES)
            hits.append(
                ContextSnippet(
                    kind="caller",
                    symbol=symbol.name,
                    path=rel,
                    start=start,
                    end=end,
                    text="\n".join(lines[start - 1 : end]),
                )
            )
    hits.sort(key=lambda s: (s.path, s.start))
    return hits[:MAX_CALLERS_PER_SYMBOL], max(0, len(hits) - MAX_CALLERS_PER_SYMBOL)


def _test_references(corpus: _Corpus, names: list[str]) -> tuple[list[ContextSnippet], int]:
    refs: list[ContextSnippet] = []
    patterns = [(name, re.compile(rf"\b{re.escape(name)}\b")) for name in names]
    for rel, _source, node, body in corpus.test_functions():
        for name, pattern in patterns:
            if pattern.search(body):
                refs.append(
                    ContextSnippet(
                        kind="test",
                        symbol=name,
                        path=rel,
                        start=node.lineno,
                        end=node.end_lineno or node.lineno,
                        text=node.name,
                    )
                )
                break
    refs.sort(key=lambda s: (s.path, s.start))
    return refs[:MAX_TEST_REFERENCES], max(0, len(refs) - MAX_TEST_REFERENCES)


def _import_block(source: str) -> tuple[int, int, str] | None:
    lines = source.splitlines()
    kept = [
        (index, line) for index, line in enumerate(lines[:400], start=1) if _IMPORT_RE.match(line)
    ][:MAX_IMPORT_LINES]
    if not kept:
        return None
    return kept[0][0], kept[-1][0], "\n".join(line for _index, line in kept)


def _file_context(
    repo: Path, corpus: _Corpus, base_ref: str, path: str, block: str, diff: DiffInfo
) -> tuple[list[ContextSnippet], list[str]]:
    snippets: list[ContextSnippet] = []
    omissions: list[str] = []
    if not path.endswith(".py"):
        return snippets, omissions
    head_source = _read(repo / path)
    base_source = show_file_at(repo, base_ref, path)
    symbols = changed_symbols(path, block, head_source, base_source)
    if head_source is not None:
        imports = _import_block(head_source)
        if imports is not None:
            start, end, text = imports
            snippets.append(ContextSnippet("imports", path, path, start, end, text))
    for symbol in symbols:
        if symbol.kind in ("changed", "added") and head_source is not None:
            found = _definition_source(head_source, symbol.name)
            if found is not None:
                start, end, text = found
                snippets.append(ContextSnippet("definition", symbol.name, path, start, end, text))
        if symbol.kind in ("changed", "removed"):
            found = _definition_source(base_source, symbol.name) if base_source else None
            if found is not None:
                start, end, text = found
                snippets.append(ContextSnippet("old_side", symbol.name, path, start, end, text))
            if not _searchable(symbol.name):
                omissions.append(f"callers of generic name {symbol.name} not searched")
                continue
            callers, dropped = _callers(corpus, symbol, diff)
            snippets.extend(callers)
            if dropped:
                omissions.append(f"{dropped} further caller(s) of {symbol.name} omitted")
    searchable = [s.name for s in symbols if _searchable(s.name)]
    if searchable:
        tests, dropped = _test_references(corpus, searchable)
        snippets.extend(tests)
        if dropped:
            omissions.append(f"{dropped} further test reference(s) omitted")
    return snippets, omissions


# ----------------------------------------------------------------- planning


def _unit_id(files: tuple[str, ...], blocks: dict[str, str]) -> str:
    headers = []
    for path in files:
        headers.append(path)
        headers.extend(line for line in blocks[path].splitlines() if _HUNK_HEADER_RE.match(line))
    return hashlib.sha256("\n".join(headers).encode("utf-8")).hexdigest()[:16]


def _bound_context(
    snippets: list[ContextSnippet], omissions: list[str]
) -> tuple[tuple[ContextSnippet, ...], tuple[str, ...]]:
    kept: list[ContextSnippet] = []
    used = 0
    dropped = 0
    # callers first: they are the cross-file evidence the diff cannot show
    priority = {"imports": 0, "old_side": 1, "caller": 2, "definition": 3, "test": 4}
    for snippet in sorted(snippets, key=lambda s: (priority[s.kind], s.path, s.start)):
        rendered = len(snippet.render()) + 2
        if used + rendered > MAX_CONTEXT_CHARS:
            dropped += 1
            continue
        kept.append(snippet)
        used += rendered
    if dropped:
        omissions = [
            *omissions,
            f"{dropped} context excerpt(s) beyond {MAX_CONTEXT_CHARS} chars omitted",
        ]
    return tuple(kept), tuple(omissions)


def _changed_line_count(block: str) -> int:
    """Added plus removed lines in one file's diff block, headers excluded."""
    return sum(
        1
        for line in block.splitlines()
        if line[:1] in {"+", "-"} and not line.startswith(("+++", "---"))
    )


def _unit_order(path: str, block: str) -> tuple[int, int, str]:
    """Source files first, then everything else; largest change first inside
    each rank, with the path breaking ties.

    D-105/E-04: a per-unit budget funds the units it reaches in plan order, so a
    large commit whose paths sort documentation ahead of code used to spend the
    whole budget on anchors that eligibility rejects for not being Python. Only
    a Python file can carry an anchored, reproducible finding, so it is read
    first. D-117: within a rank, alphabetical order carries no information about
    where a defect might be and left the two files carrying a real regression
    unread; the size of a change is the one cheap signal the plan has, so the
    largest is read first. Both keys are properties of the diff alone, so the
    plan stays stable under reordering.
    """
    return (0 if path.endswith(".py") else 1, -_changed_line_count(block), path)


def plan_review(repo: Path, diff: DiffInfo, base_ref: str) -> ReviewPlan:
    """Stable units over the merge-base diff, each with bounded retrieved context."""
    blocks = split_diff_by_file(diff.text)
    corpus = _Corpus(repo)
    per_file: list[tuple[str, list[ContextSnippet], list[str]]] = []
    for path in sorted(blocks, key=lambda name: _unit_order(name, blocks[name])):
        if path not in diff.hunks:
            continue  # no anchorable new-file lines (binary, mode-only)
        snippets, omissions = _file_context(repo, corpus, base_ref, path, blocks[path], diff)
        per_file.append((path, snippets, omissions))

    units: list[PlanUnit] = []
    pending: list[tuple[str, list[ContextSnippet], list[str]]] = []

    def flush() -> None:
        if not pending:
            return
        files = tuple(path for path, _s, _o in pending)
        snippets = [s for _p, group, _o in pending for s in group]
        omissions = [o for _p, _s, group in pending for o in group]
        context, bounded = _bound_context(snippets, omissions)
        diff_text = "".join(blocks[path] for path in files)
        units.append(
            PlanUnit(
                unit_id=_unit_id(files, blocks),
                files=files,
                diff_text=diff_text,
                context=context,
                omissions=bounded,
            )
        )
        pending.clear()

    size = 0
    for path, snippets, omissions in per_file:
        block_size = len(blocks[path]) + sum(len(s.render()) for s in snippets)
        if pending and size + block_size > MAX_UNIT_CHARS:
            flush()
            size = 0
        pending.append((path, snippets, omissions))
        size += block_size
        if len(blocks[path]) > MAX_UNIT_CHARS:
            pending[-1][2].append(f"oversize file diff: {len(blocks[path])} chars")
            flush()
            size = 0
    flush()
    digest = hashlib.sha256(
        "\n".join(
            f"{u.unit_id}:{hashlib.sha256(u.prompt_context().encode()).hexdigest()}" for u in units
        ).encode()
    ).hexdigest()
    return ReviewPlan(
        schema_version=PLAN_SCHEMA_VERSION, base_ref=base_ref, units=tuple(units), digest=digest
    )


MAX_GENERATION_CONTEXT_CHARS = 20_000
MAX_PACKAGE_BLOCK_CHARS = 120_000  # the cacheable shared block (owner instruction 4)
MAX_PACKAGE_FILE_CHARS = 40_000


def _package_dir(repo: Path, path: str) -> Path:
    """The top-most package directory enclosing the anchored file (walk up
    while ``__init__.py`` exists), else the file's own directory."""
    current = (repo / path).parent
    while (current / "__init__.py").is_file() and current.parent != current:
        parent = current.parent
        if not (parent / "__init__.py").is_file():
            break
        current = parent
    return current


def _tests_dir_for(repo: Path, package_dir: Path) -> Path | None:
    """The nearest ``tests`` directory at or above the package (its project)."""
    current = package_dir
    for _ in range(6):
        candidate = current / "tests"
        if candidate.is_dir() and candidate != package_dir:
            return candidate
        if current == repo or current.parent == current:
            break
        current = current.parent
    return None


def package_block(repo: Path, path: str) -> str:
    """One shared, cacheable block: the anchored module's package sources and
    its project's tests directory, bounded, in a deterministic order."""
    package_dir = _package_dir(repo, path)
    sections: list[str] = []
    used = 0

    def add(file: Path) -> bool:
        nonlocal used
        source = _read(file)
        if source is None:
            return True
        if len(source) > MAX_PACKAGE_FILE_CHARS:
            source = source[:MAX_PACKAGE_FILE_CHARS] + "\n# [file truncated]\n"
        rel = file.relative_to(repo).as_posix()
        text = f"### {rel}\n```python\n{source}\n```"
        if used + len(text) > MAX_PACKAGE_BLOCK_CHARS:
            sections.append(f"### [omitted: {rel} and later files, block bound reached]")
            return False
        sections.append(text)
        used += len(text)
        return True

    anchored = repo / path
    ordered = [anchored] if anchored.is_file() else []

    def skipped(file: Path) -> bool:
        return any(part in _SKIP_DIRS for part in file.relative_to(repo).parts)

    ordered.extend(
        file for file in sorted(package_dir.rglob("*.py")) if file != anchored and not skipped(file)
    )
    tests_dir = _tests_dir_for(repo, package_dir)
    if tests_dir is not None:
        ordered.extend(file for file in sorted(tests_dir.rglob("*.py")) if not skipped(file))
    for file in ordered:
        if not add(file):
            break
    if not sections:
        return ""
    return (
        "Shared repository context (the anchored module's package and its tests; "
        "read-only):\n\n" + "\n\n".join(sections)
    )


MAX_SIGNATURE_LINES = 60  # signatures of the anchored module shown to the generator
MAX_HELPERS = 12  # helpers, helper classes and fixtures from the nearest test module
MAX_HELPER_LINES = 25  # per helper or fixture
MAX_REPRESENTATIVE_TESTS = 2  # tests that use the most-used helpers, shown whole (bounded)
MAX_REPRESENTATIVE_TEST_LINES = 40


def _signature_text(lines: list[str], node: ast.AST) -> str:
    """The def/class header as written, joined onto one line."""
    start = getattr(node, "lineno", 1) - 1
    body = getattr(node, "body", None)
    end = body[0].lineno - 1 if body else start + 1
    text = " ".join(line.strip() for line in lines[start:end])
    return text.rstrip(":")


def _signatures(source: str) -> list[str]:
    """Function and constructor signatures of a module: every top-level def,
    every class header with its ``__init__`` (or annotated fields, the
    dataclass constructor) and public methods."""
    tree = _parse(source)
    if tree is None:
        return []
    lines = source.splitlines()
    out: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(_signature_text(lines, node))
        elif isinstance(node, ast.ClassDef):
            out.append(_signature_text(lines, node) + ":")
            for item in node.body:
                if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    out.append("    " + (ast.get_source_segment(source, item) or "").strip())
                elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    item.name == "__init__" or not item.name.startswith("_")
                ):
                    out.append("    " + _signature_text(lines, item))
    return out[:MAX_SIGNATURE_LINES]


def _nearest_test_module(
    corpus: _Corpus, path: str, referenced: list[str]
) -> tuple[str, str] | None:
    """The existing test module the generator should imitate: the first one
    that names the symbol, else the closest test file by path (``test_<stem>``
    wins ties)."""
    tests = [(rel, source) for rel, source in corpus.sources() if "test" in rel.lower()]
    if not tests:
        return None
    by_path = dict(tests)
    stem = Path(path).stem
    parts = Path(path).parts
    # the module named after the anchored file is where its construction
    # helpers live; a test that merely names the symbol comes second
    named = [rel for rel, _source in tests if Path(rel).name == f"test_{stem}.py"]
    if named:
        closest = max(
            named,
            key=lambda rel: sum(
                1 for left, right in zip(parts, Path(rel).parts, strict=False) if left == right
            ),
        )
        return closest, by_path[closest]
    for rel in referenced:
        if rel in by_path:
            return rel, by_path[rel]

    def score(rel: str) -> tuple[int, int, str]:
        shared = 0
        for left, right in zip(parts, Path(rel).parts, strict=False):
            if left != right:
                break
            shared += 1
        named = 1 if Path(rel).name == f"test_{stem}.py" else 0
        return (named, shared, rel)

    best = max(tests, key=lambda item: score(item[0]))
    return best


def _test_module_helpers(source: str) -> list[str]:
    """Fixtures, helper functions and helper classes of one test module -- top
    level, plus non-test methods of test classes -- ranked by how often the
    module's own tests use them (the most-used helpers construct the objects
    under test), each bounded, at most MAX_HELPERS."""
    tree = _parse(source)
    if tree is None:
        return []
    candidates: list[tuple[int, str, ast.AST]] = []
    test_bodies: list[str] = []

    def consider(node: ast.AST) -> None:
        if isinstance(node, ast.ClassDef):
            if node.name.startswith("Test") or node.name.endswith("Tests"):
                for item in node.body:
                    consider(item)
            else:
                candidates.append((node.lineno, node.name, node))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("test"):
                test_bodies.append(ast.get_source_segment(source, node) or "")
            else:
                candidates.append((node.lineno, node.name, node))

    for node in tree.body:
        consider(node)
    corpus_text = "\n".join(test_bodies)
    ranked = sorted(
        candidates,
        key=lambda item: (
            -len(re.findall(rf"\b{re.escape(item[1])}\b", corpus_text)),
            item[0],
        ),
    )
    found: list[tuple[int, str]] = []
    for line, _name, helper in ranked[:MAX_HELPERS]:
        segment = ast.get_source_segment(source, helper, padded=True) or ""
        decorators = [
            ast.get_source_segment(source, decorator) or ""
            for decorator in getattr(helper, "decorator_list", [])
        ]
        header = "".join(f"@{decorator}\n" for decorator in decorators)
        body_lines = segment.splitlines()
        if len(body_lines) > MAX_HELPER_LINES:
            body_lines = [*body_lines[:MAX_HELPER_LINES], "    ..."]
        found.append((line, header + "\n".join(body_lines)))
    found.sort()
    helpers = [text for _line, text in found]
    # two representative tests that use the most-used helpers: they show the
    # scale and shape of the inputs the project's own tests build
    top = [name for _line, name, _node in ranked[:3]]
    representatives: list[tuple[int, int, str]] = []
    for test_node in ast.walk(tree):
        if not isinstance(test_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not test_node.name.startswith("test"):
            continue
        body = ast.get_source_segment(source, test_node, padded=True) or ""
        uses = sum(1 for name in top if re.search(rf"\b{re.escape(name)}\b", body))
        if uses:
            representatives.append((-uses, test_node.lineno, body))
    representatives.sort()
    for _uses, _line, body in representatives[:MAX_REPRESENTATIVE_TESTS]:
        lines = body.splitlines()
        if len(lines) > MAX_REPRESENTATIVE_TEST_LINES:
            lines = [*lines[:MAX_REPRESENTATIVE_TEST_LINES], "    ..."]
        helpers.append("\n".join(lines))
    return helpers


def generation_context(repo: Path, base_ref: str, path: str, line: int) -> str:
    """Bounded read-only context for reproducing one anchored finding.

    The current (head) definition enclosing the anchor, the same definition at
    the merge-base, the head file's imports, and existing test functions that
    name the symbol. Rendered for the reproduction generator; the anchor window
    itself is supplied by the caller.
    """
    head_source = _read(repo / path)
    if head_source is None:
        return ""
    names = _enclosing_definitions(head_source, [(line, line)])
    sections: list[str] = []
    imports = _import_block(head_source)
    if imports is not None:
        sections.append(f"Module imports ({path}):\n```python\n{imports[2]}\n```")
    base_source = show_file_at(repo, base_ref, path)
    corpus = _Corpus(repo)
    for name in sorted(names):
        found = _definition_source(head_source, name)
        if found is not None:
            sections.append(
                f"Current (head) definition of `{name}` ({path}:{found[0]}-{found[1]}), "
                f"which contains the claimed defect:\n```python\n{found[2]}\n```"
            )
        found_base = _definition_source(base_source, name) if base_source else None
        if found_base is not None:
            sections.append(
                f"Merge-base definition of `{name}` ({path}:{found_base[0]}-{found_base[1]}), "
                f"the behaviour the test must assert:\n```python\n{found_base[2]}\n```"
            )
        elif base_source is None:
            sections.append(f"`{path}` does not exist at the merge-base.")
        else:
            sections.append(f"`{name}` does not exist at the merge-base.")
    signatures = _signatures(head_source)
    if signatures:
        sections.append(
            f"Signatures in {path} (call things exactly like this):\n```python\n"
            + "\n".join(signatures)
            + "\n```"
        )
    searchable = [name for name in sorted(names) if _searchable(name)]
    referenced: list[str] = []
    tests: list[ContextSnippet] = []
    if searchable:
        tests, _dropped = _test_references(corpus, searchable)
        referenced = [t.path for t in tests]
    nearest = _nearest_test_module(corpus, path, referenced)
    if nearest is not None:
        test_path, test_source = nearest
        test_imports = _import_block(test_source)
        helpers = _test_module_helpers(test_source)
        parts = []
        if test_imports is not None:
            parts.append(f"# imports\n{test_imports[2]}")
        parts.extend(helpers)
        if parts:
            sections.append(
                f"Nearest existing test module ({test_path}): its imports, fixtures and "
                "helpers, to construct objects the way the project's tests do:\n```python\n"
                + "\n\n".join(parts)
                + "\n```"
            )
    if tests:
        sections.append(
            "Existing tests naming the symbol (import the project the way they do):\n"
            + "\n".join(f"- {t.path}::{t.text}" for t in tests)
        )
    text = "\n\n".join(sections)
    if len(text) > MAX_GENERATION_CONTEXT_CHARS:
        text = text[:MAX_GENERATION_CONTEXT_CHARS] + "\n[context truncated]"
    return text
