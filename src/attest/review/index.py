"""The tree index: where every definition lives, what every module imports,
and which definition each call site reaches (D-245).

The planner used to find a changed symbol's callers by grepping for its name,
which has two known holes. A short or common name -- ``get``, ``parse``,
``run`` -- was not searched at all, because a name-only match on it is mostly
noise; and the shared package block handed to the generator was cut at a byte
bound in *alphabetical* order, so on a large package the file that imports the
changed module could be the one omitted. Both are questions the ``ast`` answers
exactly: a call resolves through the import that bound its name, and a file's
distance from the anchored module is a walk over the import graph.

Everything here is computed from the checked-out tree with the standard
library, once per tree, and cached on disk under ``.attest/index/`` keyed by
the paths, sizes and modification times of the Python files it read. No model
is called and nothing is bought. The index describes the tree; it never
decides anything.

Resolution is deliberately shallow and honest about it. A call is **exact**
when the name it uses is bound by an import of an in-tree module or defined in
the same module (``self.method()`` inside a class counts, through the enclosing
class); it is an **attribute** match when the receiver is a variable whose type
the index does not know, and then the caller's file importing the defining
module is the evidence that ranks it. A bare name match on a generic name is
never reported as a caller.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import warnings
from collections import Counter, deque
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

INDEX_SCHEMA_VERSION = "attest.tree-index.v1"
INDEX_DIR = ".attest/index"

MAX_INDEXED_FILES = 4_000
MAX_INDEXED_FILE_BYTES = 400_000
MAX_LITERALS_PER_CALL = 6
MAX_LITERAL_CHARS = 40
_SKIP_DIRS = frozenset(
    {".git", ".attest", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
)

# how a call site reached a definition; smaller ranks first
EXACT = "exact"
ATTRIBUTE = "attribute"
_RANK = {EXACT: 0, ATTRIBUTE: 1}


@dataclass(frozen=True)
class Definition:
    module: str
    qualname: str  # "func" or "Class.method"
    path: str
    start: int
    end: int
    kind: str  # "function" | "class"

    @property
    def name(self) -> str:
        return self.qualname.rsplit(".", 1)[-1]


@dataclass(frozen=True)
class CallSite:
    path: str
    line: int
    name: str  # the attribute or name the call used
    callee: str  # "module:qualname" when resolved, else ""
    resolution: str  # EXACT | ATTRIBUTE
    literals: tuple[str, ...]  # literal arguments as written, bounded


@dataclass(frozen=True)
class TreeIndex:
    key: str
    modules: dict[str, str]  # path -> module name
    definitions: tuple[Definition, ...]
    imports: dict[str, tuple[str, ...]]  # path -> in-tree modules it imports
    calls: tuple[CallSite, ...]
    _by_module: dict[str, list[Definition]] = field(default_factory=dict, repr=False)
    _paths: dict[str, str] = field(default_factory=dict, repr=False)

    # ------------------------------------------------------------ lookups

    def module_of(self, path: str) -> str:
        return self.modules.get(path, "")

    def path_of(self, module: str) -> str:
        if not self._paths:
            self._paths.update({module: path for path, module in self.modules.items()})
        return self._paths.get(module, "")

    def definitions_named(self, module: str, name: str) -> list[Definition]:
        """Every definition in ``module`` whose last component is ``name``: the
        function, and any method of that name on any class."""
        if not self._by_module:
            for definition in self.definitions:
                self._by_module.setdefault(definition.module, []).append(definition)
        return [d for d in self._by_module.get(module, []) if d.name == name]

    def callers_of(self, module: str, name: str) -> list[CallSite]:
        """Call sites reaching a definition named ``name`` in ``module``, exact
        ones first, then attribute calls from files that import ``module``.

        The attribute rule is the honest bound of a static index: a call on a
        receiver whose type it cannot know is a caller *if* the file could have
        got the object from the changed module. A same-named call in a file
        that never imports it is not reported."""
        targets = {f"{module}:{d.qualname}" for d in self.definitions_named(module, name)}
        if not targets:
            return []
        exact = [c for c in self.calls if c.resolution == EXACT and c.callee in targets]
        importers = {path for path, imported in self.imports.items() if module in imported}
        attribute = [
            c
            for c in self.calls
            if c.resolution == ATTRIBUTE and c.name == name and c.path in importers
        ]
        return sorted(exact, key=_site_order) + sorted(attribute, key=_site_order)

    def importers_of(self, module: str) -> list[str]:
        return sorted(path for path, imported in self.imports.items() if module in imported)

    def import_distance(self, path: str) -> dict[str, int]:
        """Breadth-first distance of every file from ``path`` over the import
        graph read in both directions: a file the anchored module imports and a
        file that imports it are both one step away."""
        neighbours: dict[str, set[str]] = {}
        for source, imported in self.imports.items():
            for module in imported:
                target = self.path_of(module)
                if not target:
                    continue
                neighbours.setdefault(source, set()).add(target)
                neighbours.setdefault(target, set()).add(source)
        distance = {path: 0}
        queue = deque([path])
        while queue:
            current = queue.popleft()
            for nxt in sorted(neighbours.get(current, ())):
                if nxt not in distance:
                    distance[nxt] = distance[current] + 1
                    queue.append(nxt)
        return distance

    def literal_arguments(self, module: str, name: str, *, limit: int = 12) -> list[str]:
        """The literal arguments the tree passes to ``name`` of ``module``, most
        frequent first, ties by text: the values the tree already treats as
        inputs, which is where a probe looks for a boundary."""
        counts: Counter[str] = Counter()
        for site in self.callers_of(module, name):
            counts.update(site.literals)
        ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return [text for text, _count in ranked[:limit]]


def _site_order(site: CallSite) -> tuple[int, str, int]:
    return (_RANK[site.resolution], site.path, site.line)


# ------------------------------------------------------------------ building


def python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in _SKIP_DIRS and not d.startswith("."))
        for name in sorted(filenames):
            if name.endswith(".py"):
                files.append(Path(dirpath) / name)
                if len(files) >= MAX_INDEXED_FILES:
                    return files
    return files


def tree_key(root: Path, files: Sequence[Path] | None = None) -> str:
    """What the cache is keyed by: every indexed file's path, size and mtime."""
    digest = hashlib.sha256(INDEX_SCHEMA_VERSION.encode())
    for path in files if files is not None else python_files(root):
        try:
            stat = path.stat()
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        digest.update(f"{rel}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()


def module_name(root: Path, path: Path) -> str:
    """The dotted name ``path`` imports as: the walk up through ``__init__.py``
    files finds the package root; a ``src`` or ``lib`` directory directly above
    it is layout, not a package (the rule the binding layer applies)."""
    rel = path.relative_to(root)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    directory = path.parent
    depth = 0
    while (directory / "__init__.py").is_file() and directory != root:
        depth += 1
        directory = directory.parent
    kept = parts[len(parts) - depth - (0 if rel.name == "__init__.py" else 1) :]
    if not kept:
        kept = parts[-1:]
    return ".".join(kept)


def _parse(source: str) -> ast.Module | None:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            return ast.parse(source)
    except (ValueError, SyntaxError, RecursionError):
        return None


def _literal(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant):
        return repr(node.value)[:MAX_LITERAL_CHARS]
    if (
        isinstance(node, ast.UnaryOp)
        and isinstance(node.op, ast.USub)
        and isinstance(node.operand, ast.Constant)
        and isinstance(node.operand.value, (int, float))
    ):
        return f"-{node.operand.value!r}"[:MAX_LITERAL_CHARS]
    if isinstance(node, (ast.List, ast.Tuple, ast.Set, ast.Dict)) and not getattr(
        node, "elts", getattr(node, "keys", None)
    ):
        return {ast.List: "[]", ast.Tuple: "()", ast.Set: "set()", ast.Dict: "{}"}[type(node)]
    return None


def _literals(call: ast.Call) -> tuple[str, ...]:
    found: list[str] = []
    for arg in call.args:
        text = _literal(arg)
        if text is not None:
            found.append(text)
    for keyword in call.keywords:
        if keyword.arg is None:
            continue
        text = _literal(keyword.value)
        if text is not None:
            found.append(f"{keyword.arg}={text}")
    return tuple(found[:MAX_LITERALS_PER_CALL])


def _resolve_relative(module: str, is_package: bool, level: int, name: str | None) -> str:
    parts = module.split(".") if module else []
    base = parts if is_package else parts[:-1]
    if level > 1:
        base = base[: len(base) - (level - 1)]
    return ".".join([*base, *([name] if name else [])])


class _FileIndexer(ast.NodeVisitor):
    """One file: its definitions, the modules it imports, and its calls,
    each call resolved through the names the file's imports bound."""

    def __init__(self, rel: str, module: str, is_package: bool, tree_modules: set[str]) -> None:
        self.rel = rel
        self.module = module
        self.is_package = is_package
        self.tree_modules = tree_modules
        self.definitions: list[Definition] = []
        self.imports: list[str] = []
        self.calls: list[CallSite] = []
        # a bound name -> "module" (the object is a module) or "module:qualname"
        self.bindings: dict[str, str] = {}
        self.local_names: set[str] = set()
        self._class_stack: list[str] = []

    # -- imports

    def _note_module(self, module: str) -> None:
        if module in self.tree_modules and module not in self.imports:
            self.imports.append(module)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._note_module(alias.name)
            # `import a.b` binds `a`; `import a.b as x` binds `x` to `a.b`
            bound = alias.asname or alias.name.split(".", 1)[0]
            self.bindings[bound] = alias.name if alias.asname else alias.name.split(".", 1)[0]

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        origin = (
            _resolve_relative(self.module, self.is_package, node.level, node.module)
            if node.level
            else (node.module or "")
        )
        self._note_module(origin)
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname or alias.name
            submodule = f"{origin}.{alias.name}" if origin else alias.name
            if submodule in self.tree_modules:
                self._note_module(submodule)
                self.bindings[bound] = submodule
            else:
                self.bindings[bound] = f"{origin}:{alias.name}"

    # -- definitions

    def _define(self, node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> None:
        qualname = ".".join([*self._class_stack, node.name])
        if len(self._class_stack) <= 1:  # top level, or a method of a top-level class
            self.definitions.append(
                Definition(
                    module=self.module,
                    qualname=qualname,
                    path=self.rel,
                    start=node.lineno,
                    end=node.end_lineno or node.lineno,
                    kind="class" if isinstance(node, ast.ClassDef) else "function",
                )
            )
        if not self._class_stack:
            self.local_names.add(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._define(node)
        self._class_stack.append(node.name)
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._define(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._define(node)
        self.generic_visit(node)

    # -- calls

    def visit_Call(self, node: ast.Call) -> None:
        site = self._site(node)
        if site is not None:
            self.calls.append(site)
        self.generic_visit(node)

    def _site(self, node: ast.Call) -> CallSite | None:
        func = node.func
        literals = _literals(node)
        if isinstance(func, ast.Name):
            bound = self.bindings.get(func.id)
            if bound and ":" in bound:
                return CallSite(self.rel, node.lineno, func.id, bound, EXACT, literals)
            if bound is None and func.id in self.local_names:
                callee = f"{self.module}:{func.id}"
                return CallSite(self.rel, node.lineno, func.id, callee, EXACT, literals)
            return None
        if not isinstance(func, ast.Attribute):
            return None
        name = func.attr
        receiver = func.value
        if isinstance(receiver, ast.Name):
            bound = self.bindings.get(receiver.id)
            if bound and ":" not in bound and bound in self.tree_modules:
                return CallSite(self.rel, node.lineno, name, f"{bound}:{name}", EXACT, literals)
            if bound and ":" in bound:
                return CallSite(self.rel, node.lineno, name, f"{bound}.{name}", EXACT, literals)
            if receiver.id == "self" and self._class_stack:
                callee = f"{self.module}:{self._class_stack[-1]}.{name}"
                return CallSite(self.rel, node.lineno, name, callee, EXACT, literals)
            if bound is None and receiver.id in self.local_names:
                callee = f"{self.module}:{receiver.id}.{name}"
                return CallSite(self.rel, node.lineno, name, callee, EXACT, literals)
        if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name):
            # `Reader().parse(x)`: the receiver is a fresh instance of a bound class
            bound = self.bindings.get(receiver.func.id)
            if bound and ":" in bound:
                return CallSite(self.rel, node.lineno, name, f"{bound}.{name}", EXACT, literals)
            if bound is None and receiver.func.id in self.local_names:
                callee = f"{self.module}:{receiver.func.id}.{name}"
                return CallSite(self.rel, node.lineno, name, callee, EXACT, literals)
        return CallSite(self.rel, node.lineno, name, "", ATTRIBUTE, literals)


def build_index(root: Path) -> TreeIndex:
    """Index the Python files under ``root``; never raises on a file it cannot
    read or parse -- that file simply contributes nothing."""
    root = root.resolve()
    files = python_files(root)
    key = tree_key(root, files)
    modules: dict[str, str] = {}
    sources: list[tuple[str, Path, str]] = []
    for path in files:
        try:
            if path.is_symlink() or path.stat().st_size > MAX_INDEXED_FILE_BYTES:
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        modules[rel] = module_name(root, path)
        sources.append((rel, path, source))
    tree_modules = set(modules.values())
    definitions: list[Definition] = []
    imports: dict[str, tuple[str, ...]] = {}
    calls: list[CallSite] = []
    for rel, path, source in sources:
        tree = _parse(source)
        if tree is None:
            continue
        indexer = _FileIndexer(rel, modules[rel], path.name == "__init__.py", tree_modules)
        indexer.visit(tree)
        definitions.extend(indexer.definitions)
        if indexer.imports:
            imports[rel] = tuple(indexer.imports)
        calls.extend(indexer.calls)
    return TreeIndex(
        key=key,
        modules=modules,
        definitions=tuple(definitions),
        imports=imports,
        calls=tuple(calls),
    )


# ------------------------------------------------------------------- caching

_MEMO: dict[tuple[str, str], TreeIndex] = {}


def _cache_path(root: Path, key: str) -> Path:
    return root / INDEX_DIR / f"{key}.json"


def _to_json(index: TreeIndex) -> dict[str, object]:
    return {
        "schema_version": INDEX_SCHEMA_VERSION,
        "key": index.key,
        "modules": index.modules,
        "definitions": [
            [d.module, d.qualname, d.path, d.start, d.end, d.kind] for d in index.definitions
        ],
        "imports": {path: list(names) for path, names in index.imports.items()},
        "calls": [
            [c.path, c.line, c.name, c.callee, c.resolution, list(c.literals)]
            for c in index.calls
        ],
    }


def _from_json(payload: dict[str, Any], key: str) -> TreeIndex | None:
    if payload.get("schema_version") != INDEX_SCHEMA_VERSION or payload.get("key") != key:
        return None
    try:
        modules = {str(path): str(module) for path, module in payload["modules"].items()}
        definitions = tuple(
            Definition(str(m), str(q), str(p), int(s), int(e), str(k))
            for m, q, p, s, e, k in payload["definitions"]
        )
        imports = {
            str(path): tuple(str(n) for n in names) for path, names in payload["imports"].items()
        }
        calls = tuple(
            CallSite(str(p), int(ln), str(n), str(c), str(r), tuple(str(x) for x in lits))
            for p, ln, n, c, r, lits in payload["calls"]
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return None
    return TreeIndex(
        key=key, modules=modules, definitions=definitions, imports=imports, calls=calls
    )


def tree_index(root: Path) -> TreeIndex:
    """The index of ``root``, from memory or ``.attest/index/`` when the tree
    it was built from is unchanged, else built and written.

    A cache that cannot be written is not an error: the index is still
    returned, it is only not remembered."""
    root = root.resolve()
    key = tree_key(root)
    memo = _MEMO.get((str(root), key))
    if memo is not None:
        return memo
    cached = _cache_path(root, key)
    if cached.is_file():
        try:
            loaded = _from_json(json.loads(cached.read_text(encoding="utf-8")), key)
        except (OSError, ValueError):
            loaded = None
        if loaded is not None:
            _MEMO[(str(root), key)] = loaded
            return loaded
    built = build_index(root)
    try:
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(_to_json(built), sort_keys=True), encoding="utf-8")
    except OSError:
        pass
    _MEMO[(str(root), key)] = built
    return built


def rendered_literals(values: Iterable[str]) -> str:
    return ", ".join(f"`{value}`" for value in values)
