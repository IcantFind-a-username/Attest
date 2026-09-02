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
import re
import subprocess
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


@dataclass(frozen=True)
class ContextSnippet:
    kind: str  # "definition" | "caller" | "old_side" | "test"
    symbol: str
    path: str
    start: int
    end: int
    text: str

    def render(self) -> str:
        if self.kind == "test":
            return f"- {self.path}::{self.text} (references `{self.symbol}`)"
        title = {
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
                        for kind in ("definition", "caller", "old_side", "test")
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


def changed_symbols(path: str, block: str) -> list[ChangedSymbol]:
    """Definitions whose def/class line appears on either side of the diff."""
    removed: set[str] = set()
    added: set[str] = set()
    for line in block.splitlines():
        m = _DEF_RE.match(line)
        if not m:
            continue
        (removed if line.startswith("-") else added).add(m.group(1))
    symbols = []
    for name in sorted(removed | added):
        kind = "changed" if name in removed and name in added else (
            "removed" if name in removed else "added"
        )
        symbols.append(ChangedSymbol(name=name, path=path, kind=kind))
    return symbols


# ----------------------------------------------------------------- retrieval


def _python_files(repo: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(repo.rglob("*.py")):
        if any(part in _SKIP_DIRS for part in path.relative_to(repo).parts):
            continue
        files.append(path)
        if len(files) >= MAX_SCANNED_FILES:
            break
    return files


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


def _definition_source(source: str, name: str) -> tuple[int, int, str] | None:
    try:
        tree = ast.parse(source)
    except (ValueError, SyntaxError, RecursionError):
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


def _callers(repo: Path, symbol: ChangedSymbol, diff: DiffInfo) -> tuple[list[ContextSnippet], int]:
    """Call sites of ``symbol`` outside the diff hunks, bounded; returns (kept, dropped)."""
    pattern = re.compile(rf"(?<![\w.]){re.escape(symbol.name)}\s*\(")
    method = re.compile(rf"\.{re.escape(symbol.name)}\s*\(")
    hits: list[ContextSnippet] = []
    for path in _python_files(repo):
        rel = path.relative_to(repo).as_posix()
        source = _read(path)
        if source is None:
            continue
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


def _test_references(repo: Path, names: list[str]) -> tuple[list[ContextSnippet], int]:
    refs: list[ContextSnippet] = []
    for path in _python_files(repo):
        rel = path.relative_to(repo).as_posix()
        if "test" not in rel.lower():
            continue
        source = _read(path)
        if source is None:
            continue
        try:
            tree = ast.parse(source)
        except (ValueError, SyntaxError, RecursionError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test"):
                continue
            body = ast.get_source_segment(source, node) or ""
            for name in names:
                if re.search(rf"\b{re.escape(name)}\b", body):
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


def _file_context(
    repo: Path, base_ref: str, path: str, block: str, diff: DiffInfo
) -> tuple[list[ContextSnippet], list[str]]:
    snippets: list[ContextSnippet] = []
    omissions: list[str] = []
    if not path.endswith(".py"):
        return snippets, omissions
    symbols = changed_symbols(path, block)
    head_source = _read(repo / path)
    base_source: str | None = None
    for symbol in symbols:
        if symbol.kind in ("changed", "added") and head_source is not None:
            found = _definition_source(head_source, symbol.name)
            if found is not None:
                start, end, text = found
                snippets.append(
                    ContextSnippet("definition", symbol.name, path, start, end, text)
                )
        if symbol.kind in ("changed", "removed"):
            if base_source is None:
                base_source = show_file_at(repo, base_ref, path) or ""
            found = _definition_source(base_source, symbol.name) if base_source else None
            if found is not None:
                start, end, text = found
                snippets.append(ContextSnippet("old_side", symbol.name, path, start, end, text))
            callers, dropped = _callers(repo, symbol, diff)
            snippets.extend(callers)
            if dropped:
                omissions.append(f"{dropped} further caller(s) of {symbol.name} omitted")
    if symbols:
        tests, dropped = _test_references(repo, [s.name for s in symbols])
        snippets.extend(tests)
        if dropped:
            omissions.append(f"{dropped} further test reference(s) omitted")
    return snippets, omissions


# ----------------------------------------------------------------- planning


def _unit_id(files: tuple[str, ...], blocks: dict[str, str]) -> str:
    headers = []
    for path in files:
        headers.append(path)
        headers.extend(
            line for line in blocks[path].splitlines() if _HUNK_HEADER_RE.match(line)
        )
    return hashlib.sha256("\n".join(headers).encode("utf-8")).hexdigest()[:16]


def _bound_context(
    snippets: list[ContextSnippet], omissions: list[str]
) -> tuple[tuple[ContextSnippet, ...], tuple[str, ...]]:
    kept: list[ContextSnippet] = []
    used = 0
    dropped = 0
    # callers first: they are the cross-file evidence the diff cannot show
    priority = {"caller": 0, "old_side": 1, "definition": 2, "test": 3}
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


def plan_review(repo: Path, diff: DiffInfo, base_ref: str) -> ReviewPlan:
    """Stable units over the merge-base diff, each with bounded retrieved context."""
    blocks = split_diff_by_file(diff.text)
    per_file: list[tuple[str, list[ContextSnippet], list[str]]] = []
    for path in sorted(blocks):
        if path not in diff.hunks:
            continue  # no anchorable new-file lines (binary, mode-only)
        snippets, omissions = _file_context(repo, base_ref, path, blocks[path], diff)
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
            f"{u.unit_id}:{hashlib.sha256(u.prompt_context().encode()).hexdigest()}"
            for u in units
        ).encode()
    ).hexdigest()
    return ReviewPlan(
        schema_version=PLAN_SCHEMA_VERSION, base_ref=base_ref, units=tuple(units), digest=digest
    )
