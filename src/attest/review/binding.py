"""Name binding: a written call, resolved to the one definition it can mean.

Four parts of this product ask the same question in four different ways --
*which definition does this name refer to?* -- and every one of them answered it
by comparing bare strings. The impact level indexed call sites by the name they
were written with, so `import math; math.sqrt(9)` was a call site of the
project's own `sqrt`, and an aliased `from mathlib import sqrt as root` was a
call site of nothing. The propagation level called two definitions of one name
ambiguous even when the file it was reading imported neither. The gate level
counted a `grep`-found call as a witness of reachability. This module is the one
answer, and it does exactly one thing:

    resolve(reference) -> Target(path, qualname) | None

**What it supports**, and nothing beyond it:

- a module-level ``def`` of the referring file itself;
- ``from m import f`` and ``from m import f as g``;
- ``import m``, ``import m as n``, ``import a.b.c`` -- then ``m.f`` / ``n.f`` /
  ``a.b.c.f``, with exactly one trailing segment;
- absolute and relative imports. A module is matched to a repository file by
  **dotted suffix**: ``a.b`` matches any file whose path ends in ``a/b.py`` or
  ``a/b/__init__.py`` at a component boundary, because ``src/`` and ``lib/`` are
  layout and not packages. Two files matching one suffix are ambiguous -> None;
- ``self.f`` and ``cls.f``, resolved to a method of the **innermost enclosing
  class of the same file**.

**What it refuses**, each of them a deliberate abstention rather than a gap to be
filled later: inheritance (a method the base class defines is not in this file's
text), decorators (the decorated name may be a wrapper of a different shape),
a re-export a package ``__init__`` does not itself define, a call through a
variable, a dynamic attribute, and every name of a file that contains
``from m import *`` -- a star import can supply any bare name, so after one no
bare name in that file can be resolved. A name bound twice in one file (an
import and a ``def``, two ``def``s, a module-level assignment) resolves to
nothing, and so does a name an enclosing function binds locally: a parameter
called ``math`` is not the module ``math``.

Free: `ast` and the file text, no model, no execution, no network. The only cost
is one parse per file, cached for the life of the index.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field

BINDING_POLICY_VERSION = "attest.binding.v1"

MAX_SOURCE_BYTES = 1_000_000


@dataclass(frozen=True)
class Target:
    """The one definition a reference can mean: a file and a qualname in it."""

    path: str
    qualname: str

    @property
    def name(self) -> str:
        return self.qualname.rsplit(".", 1)[-1]


@dataclass(frozen=True)
class Reference:
    """One written name, where it was written, and in what scope.

    ``dotted`` is the expression exactly as the source spells it -- ``sqrt``,
    ``math.sqrt``, ``self.save``, ``a.b.c.f`` -- and ``scope`` is the qualname of
    the enclosing ``def``/``class`` chain, ``None`` at module level.
    """

    path: str
    dotted: str
    scope: str | None = None


@dataclass(frozen=True)
class _FileFacts:
    """Everything one file says about what its own names mean."""

    #: qualname -> how many definitions of it this file holds (>1 is ambiguous)
    defs: Mapping[str, int] = field(default_factory=dict)
    #: qualnames that are ``class`` statements
    classes: frozenset[str] = frozenset()
    #: local name -> (module, relative level, name in that module)
    functions: Mapping[str, tuple[str | None, int, str]] = field(default_factory=dict)
    #: local dotted prefix -> (module, relative level)
    modules: Mapping[str, tuple[str | None, int]] = field(default_factory=dict)
    #: function qualname -> names bound inside it (parameters, assignments, ...)
    locals: Mapping[str, frozenset[str]] = field(default_factory=dict)
    #: this file contains ``from m import *``: no bare name of it can be resolved
    star_import: bool = False
    #: names this file binds more than once, or in more than one way
    shadowed: frozenset[str] = frozenset()


_UNPARSABLE = _FileFacts()


def dotted_name(node: ast.expr) -> str | None:
    """``a.b.c`` for the expression as written, or None when it is not a plain
    name or attribute chain -- a call, a subscript, a literal, anything dynamic."""
    parts: list[str] = []
    current: ast.expr = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    parts.append(current.id)
    return ".".join(reversed(parts))


class _FactVisitor(ast.NodeVisitor):
    """One pass over one module: definitions, imports and local bindings."""

    def __init__(self) -> None:
        self.stack: list[str] = []
        self.defs: dict[str, int] = {}
        self.classes: set[str] = set()
        self.functions: dict[str, tuple[str | None, int, str]] = {}
        self.modules: dict[str, tuple[str | None, int]] = {}
        self.locals: dict[str, set[str]] = {}
        self.star_import = False
        self.bound_at_module: dict[str, int] = {}

    # -- helpers
    @property
    def _scope(self) -> str | None:
        return ".".join(self.stack) if self.stack else None

    def _qualname(self, name: str) -> str:
        return ".".join([*self.stack, name])

    def _bind_local(self, name: str) -> None:
        scope = self._scope
        if scope is None:
            self.bound_at_module[name] = self.bound_at_module.get(name, 0) + 1
            return
        self.locals.setdefault(scope, set()).add(name)

    # -- definitions
    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualname = self._qualname(node.name)
        self.defs[qualname] = self.defs.get(qualname, 0) + 1
        self._bind_local(node.name)
        self.stack.append(node.name)
        args = node.args
        for arg in [
            *args.posonlyargs,
            *args.args,
            *args.kwonlyargs,
            *([args.vararg] if args.vararg else []),
            *([args.kwarg] if args.kwarg else []),
        ]:
            self._bind_local(arg.arg)
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast API
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast API
        qualname = self._qualname(node.name)
        self.defs[qualname] = self.defs.get(qualname, 0) + 1
        self.classes.add(qualname)
        self._bind_local(node.name)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    # -- imports
    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802 - ast API
        for alias in node.names:
            local = alias.asname or alias.name  # `import a.b` binds `a.b` usably
            self.modules[local] = (alias.name, 0)
            self._bind_local(local.split(".", 1)[0])
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802 - ast API
        level = node.level
        module = node.module
        for alias in node.names:
            if alias.name == "*":
                self.star_import = True
                continue
            local = alias.asname or alias.name
            self.functions[local] = (module, level, alias.name)
            # `from . import mod` and `from .pkg import mod` may name a module;
            # a bare reference reads the function binding, a dotted one this.
            submodule = alias.name if module is None else f"{module}.{alias.name}"
            self.modules[local] = (submodule, level)
            self._bind_local(local)
        self.generic_visit(node)

    # -- other bindings, which shadow
    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802 - ast API
        for target in node.targets:
            self._bind_targets(target)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:  # noqa: N802 - ast API
        self._bind_targets(node.target)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802 - ast API
        self._bind_targets(node.target)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:  # noqa: N802 - ast API
        self._bind_targets(node.target)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:  # noqa: N802 - ast API
        self._bind_targets(node.target)
        self.generic_visit(node)

    def visit_withitem(self, node: ast.withitem) -> None:  # noqa: N802 - ast API
        if node.optional_vars is not None:
            self._bind_targets(node.optional_vars)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:  # noqa: N802
        if node.name:
            self._bind_local(node.name)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:  # noqa: N802 - ast API
        self._bind_targets(node.target)
        self.generic_visit(node)

    def _bind_targets(self, node: ast.expr) -> None:
        if isinstance(node, ast.Name):
            self._bind_local(node.id)
        elif isinstance(node, ast.Tuple | ast.List):
            for element in node.elts:
                self._bind_targets(element)
        elif isinstance(node, ast.Starred):
            self._bind_targets(node.value)


def _facts(source: str) -> _FileFacts:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return _UNPARSABLE
    visitor = _FactVisitor()
    visitor.visit(tree)
    # A module-level name bound more than once means one of two things this
    # module refuses to choose between: a redefinition, or an import a `def`
    # overrides. Either way the name no longer identifies one definition.
    shadowed = {name for name, count in visitor.bound_at_module.items() if count > 1}
    return _FileFacts(
        defs=dict(visitor.defs),
        classes=frozenset(visitor.classes),
        functions=dict(visitor.functions),
        modules=dict(visitor.modules),
        locals={scope: frozenset(names) for scope, names in visitor.locals.items()},
        star_import=visitor.star_import,
        shadowed=frozenset(shadowed),
    )


class BindingIndex:
    """The repository's answer to "which definition does this name mean?".

    Built from a path list and a loader so that a caller with the working tree
    in memory and a caller reading blobs out of `git` share one implementation;
    every file is parsed at most once.
    """

    def __init__(self, paths: Iterable[str], load: Callable[[str], str | None]) -> None:
        self._paths = tuple(sorted({path for path in paths if path.endswith(".py")}))
        self._load = load
        self._facts: dict[str, _FileFacts] = {}
        self._modules: dict[tuple[str, int, str], str | None] = {}
        self._suffixes: dict[str, list[str]] | None = None

    @classmethod
    def from_sources(cls, sources: Mapping[str, str]) -> BindingIndex:
        return cls(sources.keys(), lambda path: sources.get(path))

    # -- file facts
    def facts(self, path: str) -> _FileFacts:
        held = self._facts.get(path)
        if held is not None:
            return held
        source = self._load(path)
        if source is None or len(source.encode("utf-8", "ignore")) > MAX_SOURCE_BYTES:
            self._facts[path] = _UNPARSABLE
        else:
            self._facts[path] = _facts(source)
        return self._facts[path]

    def defines(self, target: Target) -> bool:
        """Does ``target``'s file hold exactly one definition of its qualname?"""
        return self.facts(target.path).defs.get(target.qualname, 0) == 1

    # -- module resolution
    def _suffix_index(self) -> dict[str, list[str]]:
        if self._suffixes is None:
            index: dict[str, list[str]] = {}
            for path in self._paths:
                parts = path.split("/")
                for start in range(len(parts)):
                    index.setdefault("/".join(parts[start:]), []).append(path)
            self._suffixes = index
        return self._suffixes

    def module_path(self, module: str | None, level: int, *, from_path: str) -> str | None:
        """The one repository file a module name can mean, or None.

        Absolute names match by dotted **suffix**, because a repository lays its
        packages out under `src/` or `lib/` and those directories are not part of
        any importable name. Two files matching one suffix are ambiguous.
        """
        key = (module or "", level, from_path if level else "")
        if key in self._modules:
            return self._modules[key]
        resolved = self._module_path(module, level, from_path)
        self._modules[key] = resolved
        return resolved

    def _module_path(self, module: str | None, level: int, from_path: str) -> str | None:
        if level == 0:
            if not module:
                return None
            stem = module.replace(".", "/")
            index = self._suffix_index()
            matched = {
                path
                for suffix in (f"{stem}.py", f"{stem}/__init__.py")
                for path in index.get(suffix, ())
            }
            return matched.pop() if len(matched) == 1 else None
        # relative: walk up from the referring file's own directory
        parts = from_path.split("/")[:-1]
        if level - 1 > len(parts):
            return None
        base = parts[: len(parts) - (level - 1)]
        stem = "/".join([*base, *(module.split(".") if module else [])])
        known = set(self._paths)
        candidates = [f"{stem}.py", f"{stem}/__init__.py"] if stem else ["__init__.py"]
        if not module:
            candidates = [f"{'/'.join([*base, '__init__.py'])}" if base else "__init__.py"]
        present = [path for path in candidates if path in known]
        return present[0] if len(present) == 1 else None

    # -- the one question
    def resolve(self, reference: Reference) -> Target | None:
        """The definition ``reference`` can only mean, or None for every doubt."""
        dotted = reference.dotted
        if not dotted:
            return None
        parts = dotted.split(".")
        facts = self.facts(reference.path)
        if facts is _UNPARSABLE:
            return None
        head = parts[0]
        if head in {"self", "cls"}:
            return self._resolve_receiver(reference, facts, parts)
        if self._locally_bound(facts, reference.scope, head):
            return None
        if head in facts.shadowed:
            return None
        if len(parts) == 1:
            if facts.star_import:
                return None  # a star import can supply any bare name
            return self._resolve_bare(reference, facts, head)
        return self._resolve_dotted(reference, facts, parts)

    def _resolve_receiver(
        self, reference: Reference, facts: _FileFacts, parts: list[str]
    ) -> Target | None:
        """``self.f`` / ``cls.f``: a method of the innermost enclosing class.

        Only of **this file**: a method the base class defines is not in this
        file's text, and this module does not follow inheritance."""
        if len(parts) != 2 or reference.scope is None:
            return None
        scope = reference.scope.split(".")
        for stop in range(len(scope), 0, -1):
            candidate = ".".join(scope[:stop])
            if candidate in facts.classes:
                qualname = f"{candidate}.{parts[1]}"
                if facts.defs.get(qualname, 0) == 1:
                    return Target(reference.path, qualname)
                return None
        return None

    def _resolve_bare(
        self, reference: Reference, facts: _FileFacts, name: str
    ) -> Target | None:
        imported = facts.functions.get(name)
        if imported is not None:
            module, level, original = imported
            path = self.module_path(module, level, from_path=reference.path)
            if path is None:
                return None
            return self._module_level(path, original)
        if facts.defs.get(name, 0) == 1:
            return Target(reference.path, name)
        return None

    def _resolve_dotted(
        self, reference: Reference, facts: _FileFacts, parts: list[str]
    ) -> Target | None:
        # everything but the last segment must be a bound module name, and the
        # last segment is the name in it. `import a` then `a.b.c()` therefore
        # resolves to nothing: `a.b` is an attribute this module cannot read,
        # and only `import a.b` (which binds `a.b`) makes `a.b.c` a call.
        prefix = ".".join(parts[:-1])
        bound = facts.modules.get(prefix)
        if bound is None:
            return None
        module, level = bound
        path = self.module_path(module, level, from_path=reference.path)
        if path is None:
            return None
        return self._module_level(path, parts[-1])

    def _module_level(self, path: str, name: str) -> Target | None:
        """The one module-level definition of ``name`` in ``path``, or None.

        A package ``__init__`` that re-exports a name without defining it
        resolves to nothing: the re-export is an import and this module does not
        chain through one."""
        return Target(path, name) if self.facts(path).defs.get(name, 0) == 1 else None

    def _locally_bound(
        self, facts: _FileFacts, scope: str | None, name: str
    ) -> bool:
        """Does some enclosing function of ``scope`` bind ``name`` itself?

        A parameter named ``math`` is not the module ``math``, and a nested
        ``def helper`` is not the module-level ``helper``."""
        if scope is None:
            return False
        parts = scope.split(".")
        return any(
            name in facts.locals.get(".".join(parts[:stop]), frozenset())
            for stop in range(len(parts), 0, -1)
        )


__all__ = [
    "BINDING_POLICY_VERSION",
    "BindingIndex",
    "Reference",
    "Target",
    "dotted_name",
]
