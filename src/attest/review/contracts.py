"""Contracts: a specification bound to a concrete input, a value source and a call
path (`attest.intent.v6`, experimental, D-252).

D-127's value rule asks whether the base tree *states* the value the failing
assertion pins, and reads that statement off literal constants in ``assert``
comparisons (D-132 (a)), off the exception type a test expects (D-240 (b)), and
off prose. Three shapes a tree uses to state a value are invisible to it:

- an expected side that is an **object** -- ``assert f(x) == Point(1, 2)``;
- a **parametrize row** -- ``@pytest.mark.parametrize("s, expected", [("${a}",
  [Variable(name="a", default=None)])])``;
- an exception a test expects **through a caller** of the touched symbol --
  ``with pytest.raises(UnannotatedAttributeError): attr.s(auto_attribs=True)(C)``
  when the guard that raises it sits in ``_transform_attrs``.

A contract is such a statement read as a whole -- *this symbol, on this input,
yields this* -- and it is **admitted** as a specification of the probe's pinned
value only when three bindings hold, each recorded on its own:

``input_bound``
    the source states the same concrete input the probe called with: every
    argument a literal (or a name bound to one in the test's parametrize row,
    its module constants, or the probe's own setup), compared by value;
``evaluated``
    the expected side is a value this module can derive **mechanically**: a
    literal, a ``NamedTuple`` or ``@dataclass`` constructor of a class the tree
    defines with literal fields, or a list/tuple/dict of those -- never an
    arbitrary call, whose repr nobody can know without running it;
``path_bound``
    the source's call and the probe's call resolve to the same entry: the
    symbol imported from the anchored module, or -- for a caller contract --
    the *same caller*, which the probe must itself have entered through.

``flow_bound`` (D-255, `attest.intent.v6.1`)
    every run reaches the source's call along a path this module read: the call
    belongs to a statement at the test body's own level (or, for a caller
    contract, the first statement of a ``with raises(...)`` block there), and no
    statement before it leaves the test, rebinds a name the call depends on,
    touches a local it depends on -- a state change, an alias, a call it is handed
    to -- changes a module-level name it depends on, or uses a fixture; the test is
    not skipped, expected to fail, patched or a generator. The input is bound *at
    that point*: an assignment after the assertion, or one inside a branch, is not
    the input the assertion checks. What the rule cannot read it refuses, with the
    line. What it does not look at, stated: fixtures (autouse ones, ``conftest``)
    and helper functions a test calls are not followed.

Everything found is recorded, admitted or not, with the reason: a contract the
probe did not bind is exactly the fact the next probe needs. Deterministic end
to end: file reads and ``ast``, no model.
"""

from __future__ import annotations

import ast
import builtins
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from attest.certification.intent import ContractRecord
from attest.review.index import TreeIndex, build_index
from attest.review.intent import (
    MAX_WITNESS_FILE_BYTES,
    MAX_WITNESS_FILES,
    SKIPPED_DIRS,
    is_spec_file,
    symbol_ranges,
)
from attest.review.probe import ProbeSpec, hygiene_refusal, reaches_the_tree, tree_roots

MAX_CONTRACTS = 32  # recorded per observation, admitted ones first
MAX_ROWS = 200  # parametrize rows read per test function
WRAPPERS = frozenset({"list", "tuple", "sorted", "set", "dict", "str", "repr", "len", "next"})
_RAISES = frozenset({"raises", "assertRaises", "assertRaisesRegex", "assertRaisesRegexp"})
_TEST_NAME = re.compile(r"^test")


# ------------------------------------------------------------------ the probe


@dataclass(frozen=True)
class Call:
    """One call, resolved as far as source text allows: the wrapper chain around
    it, the module its callee resolves to, the callee's qualified name inside
    that module, and its arguments as canonical reprs (None when any argument
    is not a literal the reader could bind)."""

    wrappers: tuple[str, ...]
    module: str
    callee: str  # "f" or "Cls.method" or "Cls" (a constructor)
    args: tuple[str, ...] | None
    kwargs: tuple[tuple[str, str], ...] | None
    # D-253: how the object the method is called on was built, as canonical text
    # (`pkg.mod.Grid(width=2)`); "" for a function or a class-level call, None when
    # the construction is not bound. Part of the input: `Grid(width=5).cell(p)` and
    # `Grid(width=2).cell(p)` are different calls even when they return the same value.
    receiver: str | None = ""
    # D-255: why the call's program point was not read ("" when it was). A call
    # whose inputs may have changed on the way to it binds no input at all.
    flow: str = ""

    @property
    def input(self) -> str:
        if self.args is None or self.kwargs is None or self.receiver is None:
            return "<unbound>"
        parts = list(self.args) + [f"{k}={v}" for k, v in self.kwargs]
        text = ", ".join(parts)
        return f"{self.receiver} :: {text}" if self.receiver else text

    def same_input(self, other: Call) -> bool:
        return (
            not self.flow
            and not other.flow
            and self.args is not None
            and other.args is not None
            and self.receiver is not None
            and other.receiver is not None
            and self.args == other.args
            and self.kwargs == other.kwargs
            and self.receiver == other.receiver
        )


@dataclass
class _Scope:
    """What names mean inside one file, and inside one test function of it."""

    from_module: dict[str, tuple[str, str]] = field(default_factory=dict)  # name -> (module, attr)
    module_alias: dict[str, str] = field(default_factory=dict)  # alias -> module
    constants: dict[str, ast.AST] = field(default_factory=dict)  # module-level literal names
    locals: dict[str, ast.AST] = field(default_factory=dict)  # name -> literal node (setup)
    calls: dict[str, ast.Call] = field(default_factory=dict)  # name -> call it was assigned


def _bindings(tree: ast.Module) -> _Scope:
    scope = _Scope()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                scope.from_module[alias.asname or alias.name] = (node.module, alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                scope.module_alias[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                # any value: the binding reader decides whether it is bound (D-253)
                scope.constants[target.id] = node.value
    return scope


def _is_literal(node: ast.AST) -> bool:
    try:
        ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return False
    return True


MAX_BINDING_DEPTH = 8


def _qualified(func: ast.AST, scope: _Scope) -> str:
    """``pkg.mod.Name`` for a callee bound by an import, "" otherwise."""
    if isinstance(func, ast.Name) and func.id in scope.from_module:
        module, attr = scope.from_module[func.id]
        return f"{module}.{attr}"
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id in scope.module_alias:
            return f"{scope.module_alias[func.value.id]}.{func.attr}"
        if func.value.id in scope.from_module:
            module, owner = scope.from_module[func.value.id]
            return f"{module}.{owner}.{func.attr}"
    return ""


def _literal_repr(
    node: ast.AST, scope: _Scope, row: dict[str, ast.AST], depth: int = 0
) -> str | None:
    """The canonical text of a bound argument (D-253), or None.

    Bound means: a literal; a name that resolves -- through the parametrize row,
    the function's own assignments, or the module's -- to something bound, however
    many names deep up to ``MAX_BINDING_DEPTH`` (the probe and the source are read
    by the same rule, so ``output = MUSL_AMD64`` binds on either side); a
    construction of an *imported* callee whose arguments are all bound, written as
    ``pkg.mod.Url('http://example.com')``; or a list or tuple of bound elements."""
    if depth > MAX_BINDING_DEPTH:
        return None
    if isinstance(node, ast.Name):
        bound = (
            row.get(node.id)
            or scope.locals.get(node.id)
            or scope.calls.get(node.id)
            or scope.constants.get(node.id)
        )
        return None if bound is None else _literal_repr(bound, scope, row, depth + 1)
    if isinstance(node, ast.Call):
        qualified = _qualified(node.func, scope)
        if not qualified:
            return None
        parts: list[str] = []
        for arg in node.args:
            shown = _literal_repr(arg, scope, row, depth + 1)
            if shown is None:
                return None
            parts.append(shown)
        for keyword in sorted(node.keywords, key=lambda k: k.arg or ""):
            if keyword.arg is None:
                return None
            shown = _literal_repr(keyword.value, scope, row, depth + 1)
            if shown is None:
                return None
            parts.append(f"{keyword.arg}={shown}")
        return f"{qualified}({', '.join(parts)})"
    try:
        return repr(ast.literal_eval(node))
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        pass
    if isinstance(node, ast.List | ast.Tuple):
        elements = [_literal_repr(e, scope, row, depth + 1) for e in node.elts]
        if any(e is None for e in elements):
            return None
        inner = ", ".join(e for e in elements if e is not None)
        return f"[{inner}]" if isinstance(node, ast.List) else f"({inner},)"
    return None


def _resolve_call(
    node: ast.AST,
    scope: _Scope,
    row: dict[str, ast.AST],
    anchored_module: str,
    seen: frozenset[str] = frozenset(),
) -> Call | None:
    """Unwrap ``list(sorted(f(x)))`` to the innermost call that resolves to a
    module of the tree, keeping the wrapper chain. ``seen`` is the names already
    followed through ``scope.calls``: ``s = s.next()`` names itself, and a
    reader that followed it again would never come back."""
    wrappers: list[str] = []
    current = node
    while isinstance(current, ast.Call):
        func = current.func
        if isinstance(func, ast.Name) and func.id in WRAPPERS and len(current.args) == 1:
            wrappers.append(func.id)
            current = current.args[0]
            continue
        break
    if isinstance(current, ast.Name) and current.id in scope.calls:
        if current.id in seen:
            return None
        seen = seen | {current.id}
        current = scope.calls[current.id]
    if not isinstance(current, ast.Call):
        return None
    func = current.func
    module = ""
    callee = ""
    receiver_text: str | None = ""
    if isinstance(func, ast.Name):
        bound = scope.from_module.get(func.id)
        if bound is not None:
            module, callee = bound
    elif isinstance(func, ast.Attribute):
        receiver = func.value
        if isinstance(receiver, ast.Name):
            if receiver.id in scope.module_alias:
                module, callee = scope.module_alias[receiver.id], func.attr
            elif receiver.id in scope.from_module:
                owner_module, owner = scope.from_module[receiver.id]
                module, callee = owner_module, f"{owner}.{func.attr}"
            elif receiver.id in scope.calls and receiver.id not in seen:
                inner = _resolve_call(
                    scope.calls[receiver.id], scope, row, anchored_module, seen | {receiver.id}
                )
                if inner is not None and inner.callee and "." not in inner.callee:
                    module, callee = inner.module, f"{inner.callee}.{func.attr}"
                    receiver_text = _literal_repr(scope.calls[receiver.id], scope, row)
        elif isinstance(receiver, ast.Call):
            inner = _resolve_call(receiver, scope, row, anchored_module, seen)
            if inner is not None and inner.callee and "." not in inner.callee:
                module, callee = inner.module, f"{inner.callee}.{func.attr}"
                receiver_text = _literal_repr(receiver, scope, row)
    if not module:
        return None
    args: list[str] = []
    kwargs: list[tuple[str, str]] = []
    all_literal = True
    for arg in current.args:
        shown = _literal_repr(arg, scope, row)
        if shown is None:
            all_literal = False
            break
        args.append(shown)
    for keyword in current.keywords:
        shown = _literal_repr(keyword.value, scope, row) if keyword.arg else None
        if shown is None:
            all_literal = False
            break
        kwargs.append((keyword.arg or "", shown))
    return Call(
        wrappers=tuple(wrappers),
        module=module,
        callee=callee,
        args=tuple(args) if all_literal else None,
        kwargs=tuple(sorted(kwargs)) if all_literal else None,
        receiver=receiver_text,
    )


# ------------------------------------------------- the program point (D-255)

_EXIT_CALLS = frozenset({"skip", "fail", "xfail", "exit", "importorskip"})
_REFUSED_MARKS = frozenset({"skip", "skipif", "xfail", "usefixtures"})
# compared lower-cased: pytest's marks, unittest's decorators pytest honours, and patching
_REFUSED_DECORATIONS = frozenset(
    {*_REFUSED_MARKS, "skipunless", "expectedfailure", "patch"}
)
_NESTED_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
_STATEMENT_KINDS = {
    "AsyncFor": "async for", "AsyncWith": "async with", "FunctionDef": "def",
    "AsyncFunctionDef": "async def", "ClassDef": "class", "TryStar": "try",
}


@dataclass(frozen=True)
class ProgramPoint:
    """Where a call runs inside its test function, read on the straight path.

    ``site`` is the statement of the test body's own level the call belongs to;
    ``prefix`` the statements before it at that level, which every run executes
    first; ``bindings`` the plain ``name = value`` assignment among them in force
    for each name there. ``shape`` is "" when the call sits in a shape the rule
    reads, and otherwise why it does not."""

    site: ast.stmt
    prefix: tuple[ast.stmt, ...]
    bindings: dict[str, ast.Assign]
    shape: str


def _kind(statement: ast.stmt) -> str:
    name = type(statement).__name__
    return _STATEMENT_KINDS.get(name, name.lower())


def _shallow(node: ast.AST) -> Iterable[ast.AST]:
    """``ast.walk`` below ``node`` that does not enter a nested def, class or lambda."""
    stack = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        yield current
        if not isinstance(current, _NESTED_SCOPES):
            stack.extend(ast.iter_child_nodes(current))


def _child_statements(node: ast.AST) -> Iterable[ast.stmt]:
    for child in ast.iter_child_nodes(node):
        if isinstance(child, ast.stmt):
            yield child
        elif isinstance(child, ast.excepthandler | ast.match_case):
            yield from _child_statements(child)


def _statement_path(root: ast.stmt, target: ast.AST) -> list[ast.stmt] | None:
    """The statements from ``root`` down to the innermost one holding ``target``."""
    if root is target:
        return [root]
    if not any(node is target for node in ast.walk(root)):
        return None
    for child in _child_statements(root):
        found = _statement_path(child, target)
        if found is not None:
            return [root, *found]
    return [root]


def program_point(
    func: ast.FunctionDef | ast.AsyncFunctionDef, target: ast.AST, *, container: str = ""
) -> ProgramPoint | None:
    """The program point of ``target`` in ``func``; None when it is not in its body.

    A supported shape is a statement of the test body's own level. ``container``
    names the one nesting a caller may also accept: ``"raises"`` -- the first
    statement of a single-context ``with raises(...)`` block, where a caller
    contract's call runs -- or ``"try"`` -- the first statement of a ``try``, where
    the replay test records a raised type."""
    for index, top in enumerate(func.body):
        path = _statement_path(top, target)
        if path is None:
            continue
        prefix = tuple(func.body[:index])
        bindings: dict[str, ast.Assign] = {}
        for statement in prefix:
            if (
                isinstance(statement, ast.Assign)
                and len(statement.targets) == 1
                and isinstance(statement.targets[0], ast.Name)
            ):
                bindings[statement.targets[0].id] = statement
        accepted = (
            container == "raises"
            and isinstance(top, ast.With)
            and _expected_exception(top) is not None
        ) or (container == "try" and isinstance(top, ast.Try))
        depth = 2 if accepted else 1
        shape = ""
        if (
            accepted
            and isinstance(top, ast.With | ast.Try)
            and len(path) >= 2
            and path[1] is not top.body[0]
        ):
            shape = (
                f"line {path[1].lineno} is not the first statement of the block at "
                f"line {top.lineno}: an earlier statement may raise before it"
            )
        elif accepted and isinstance(top, ast.With) and len(top.items) != 1:
            shape = (
                f"the with statement at line {top.lineno} enters more than the "
                "expected-exception context"
            )
        elif len(path) > depth:
            outer = path[depth - 1]
            shape = (
                f"line {path[-1].lineno} sits inside the {_kind(outer)} at line "
                f"{outer.lineno}: the rule reads only statements at the test body's own level"
            )
        return ProgramPoint(site=top, prefix=prefix, bindings=bindings, shape=shape)
    return None


def _point_scope(file_scope: _Scope, point: ProgramPoint | None) -> _Scope:
    """The names a call sees at its program point: the file's, and the plain
    assignments in force there -- never one made after it or inside a branch."""
    scope = _Scope(
        from_module=dict(file_scope.from_module),
        module_alias=dict(file_scope.module_alias),
        constants=dict(file_scope.constants),
    )
    for name, assignment in (point.bindings if point is not None else {}).items():
        if isinstance(assignment.value, ast.Call):
            scope.calls[name] = assignment.value
        else:
            scope.locals[name] = assignment.value
    return scope


def _wide_scope(file_scope: _Scope, func: ast.FunctionDef | ast.AsyncFunctionDef) -> _Scope:
    """Every assignment of the function, the last one winning -- D-254's reading. Used
    only to *recognise* a contract site whose call resolves through a name not in force
    at its program point, so that the site is refused with its reason instead of being
    silently skipped; never to bind an input."""
    scope = _point_scope(file_scope, None)
    for node in sorted(
        (n for n in ast.walk(func) if isinstance(n, ast.Assign) and len(n.targets) == 1),
        key=lambda n: n.lineno,
    ):
        target = node.targets[0]
        if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
            scope.calls[target.id] = node.value
        elif isinstance(target, ast.Name):
            scope.locals[target.id] = node.value
    return scope


_NOT_IN_FORCE = (
    "the call resolves only through an assignment that is not in force at line {line}"
)


def _root_name(node: ast.AST) -> str:
    while isinstance(node, ast.Attribute | ast.Subscript | ast.Call):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else ""


def _exit_call(node: ast.AST) -> str:
    if isinstance(node, ast.Call):
        name = ast.unparse(node.func).rsplit(".", 1)[-1]
        if name in _EXIT_CALLS:
            return ast.unparse(node.func)
    return ""


def _aliases(module: ast.Module | None) -> dict[str, ast.expr]:
    """Module-level ``name = value`` assignments, which a decorator or a parametrize
    table may name instead of spelling the mark out."""
    out: dict[str, ast.expr] = {}
    for node in module.body if module is not None else ():
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out[target.id] = node.value
    return out


def _import_names(module: ast.Module | None) -> dict[str, str]:
    """Module-level import aliases: the local name -> the last segment it imports
    (``from unittest.mock import patch as p`` -> ``p: patch``)."""
    out: dict[str, str] = {}
    for node in module.body if module is not None else ():
        if isinstance(node, ast.Import | ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    out[(alias.asname or alias.name).split(".")[0]] = alias.name.rsplit(".", 1)[-1]
    return out


def _mark_text(
    node: ast.AST,
    aliases: dict[str, ast.expr],
    imports: dict[str, str] | None = None,
    seen: set[str] | None = None,
) -> str:
    """The skip, xfail, usefixtures or patch mark ``node`` applies anywhere inside it --
    a decorator, a ``pytest.param(..., marks=...)`` row, a mark bound to a module name or
    imported under another one -- or "". Each module alias is read at most once."""
    imports = imports or {}
    seen = set() if seen is None else seen
    for inner in ast.walk(node):
        if isinstance(inner, ast.Attribute) and inner.attr.lower() in _REFUSED_DECORATIONS:
            return ast.unparse(inner)
        if isinstance(inner, ast.Name):
            if (
                inner.id.lower() in _REFUSED_DECORATIONS
                or imports.get(inner.id, "").lower() in _REFUSED_DECORATIONS
            ):
                return inner.id
            if inner.id in aliases and inner.id not in seen:
                seen.add(inner.id)
                found = _mark_text(aliases[inner.id], aliases, imports, seen)
                if found:
                    return found
        if (
            isinstance(inner, ast.Call)
            and ast.unparse(inner.func).rsplit(".", 1)[-1] == "parametrize"
            and any(
                k.arg == "indirect"
                and not (isinstance(k.value, ast.Constant) and k.value.value is False)
                for k in inner.keywords
            )
        ):
            return "parametrize(indirect=...)"
    return ""


def _module_bindings(module: ast.Module | None) -> dict[str, list[int]]:
    """Every line each module-level name is bound on, outside function and class bodies."""
    lines: dict[str, list[int]] = {}
    for statement in module.body if module is not None else ():
        nodes = [statement, *_shallow(statement)]
        for node in nodes:
            names: list[str] = []
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
                names = [node.id]
            elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                names = [node.name]
            elif isinstance(node, ast.Import | ast.ImportFrom):
                names = [(a.asname or a.name).split(".")[0] for a in node.names]
            for name in names:
                lines.setdefault(name, []).append(getattr(node, "lineno", 0))
    return lines


def _module_names(module: ast.Module | None) -> tuple[set[str], set[str]]:
    """Every name the module binds, and the ones bound to a value a statement could change."""
    names: set[str] = set()
    mutable: set[str] = set()
    for node in module.body if module is not None else ():
        if isinstance(node, ast.Import | ast.ImportFrom):
            names.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                for inner in ast.walk(target):
                    if isinstance(inner, ast.Name):
                        names.add(inner.id)
                        try:
                            hash(ast.literal_eval(node.value))
                        except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
                            mutable.add(inner.id)
    return names, mutable


def _evaluated_at_definition(statement: ast.AST) -> list[ast.AST]:
    """What a def or class statement runs when it is executed: decorators, defaults,
    annotations and bases -- and a class's body, which a def's is not."""
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
        arguments = statement.args
        every = (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                 *(a for a in (arguments.vararg, arguments.kwarg) if a is not None))
        return [*statement.decorator_list, *arguments.defaults,
                *(d for d in arguments.kw_defaults if d is not None),
                *(a.annotation for a in every if a.annotation is not None),
                *([statement.returns] if statement.returns is not None else [])]
    if isinstance(statement, ast.ClassDef):
        return [*statement.decorator_list, *statement.bases,
                *(k.value for k in statement.keywords), *statement.body]
    return [statement]


def _definition_refusal(statement: ast.stmt, site: int, rebound: set[str]) -> str:
    """D-255: a decorator is a call even when it is a bare name, and creating a class
    runs its bases' ``__init_subclass__`` and its metaclass; neither is read."""
    if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return ""
    if statement.decorator_list:
        return (
            f"line {statement.lineno} decorates {statement.name!r} before the assertion at "
            f"line {site}: a decorator is a call the rule cannot rule out"
        )
    if isinstance(statement, ast.ClassDef) and (
        statement.keywords
        or any(
            not (isinstance(b, ast.Name) and b.id in _BUILTIN_NAMES and b.id not in rebound)
            for b in statement.bases
        )
    ):
        return (
            f"line {statement.lineno} creates the class {statement.name!r} from a base or "
            f"metaclass before the assertion at line {site}: what that runs is not read"
        )
    return ""


@dataclass(frozen=True)
class _ModuleFacts:
    aliases: dict[str, ast.expr]
    imports: dict[str, str]
    names: set[str]
    mutable: set[str]
    lines: dict[str, list[int]]
    imported: set[str]
    star: int  # the line of a star import; 0 when there is none


_FACTS: dict[int, tuple[ast.Module | None, _ModuleFacts]] = {}


def _module_facts(module: ast.Module | None) -> _ModuleFacts:
    """What the rule reads of a test module, once per module object."""
    hit = _FACTS.get(id(module))
    if hit is not None and hit[0] is module:
        return hit[1]
    if len(_FACTS) >= 64:
        _FACTS.clear()
    names, mutable = _module_names(module)
    star = next(
        (
            n.lineno
            for statement in (module.body if module is not None else ())
            for n in (statement, *_shallow(statement))
            if isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
        ),
        0,
    )
    facts = _ModuleFacts(
        aliases=_aliases(module), imports=_import_names(module), names=names, mutable=mutable,
        lines=_module_bindings(module), imported=_imported(module), star=star,
    )
    _FACTS[id(module)] = (module, facts)
    return facts


def _immutable(node: ast.AST, aliases: dict[str, ast.expr], depth: int = 0) -> bool:
    """A literal no call can change: hashable, directly or through module names."""
    if isinstance(node, ast.Name) and node.id in aliases and depth < MAX_BINDING_DEPTH:
        return _immutable(aliases[node.id], aliases, depth + 1)
    try:
        hash(ast.literal_eval(node))
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return False
    return True


def flow_refusal(
    point: ProgramPoint | None,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    call: ast.AST,
    *,
    owners: Sequence[ast.ClassDef] = (),
    module: ast.Module | None = None,
) -> str:
    """Why every run of ``func`` may not reach ``call`` with the inputs bound at its
    program point; "" when the rule read the whole path and found nothing it cannot
    rule out."""
    try:
        return _flow_refusal(point, func, call, owners=owners, module=module)
    except RecursionError:
        return f"{func.name} is nested too deeply for the rule to read"


def _flow_refusal(
    point: ProgramPoint | None,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    call: ast.AST,
    *,
    owners: Sequence[ast.ClassDef],
    module: ast.Module | None,
) -> str:
    if point is None:
        return f"the call is not in the body of {func.name}"
    if point.shape:
        return point.shape
    facts = _module_facts(module)
    aliases = facts.aliases
    carriers: list[tuple[ast.AST, int]] = [(d, d.lineno) for d in func.decorator_list]
    for owner in owners:
        carriers.extend((d, d.lineno) for d in owner.decorator_list)
    for body in (*(o.body for o in owners), module.body if module is not None else []):
        carriers.extend(
            (s.value, s.lineno) for s in body
            if isinstance(s, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in s.targets)
        )
    for carrier, line in carriers:
        text = _mark_text(carrier, aliases, facts.imports)
        if text:
            return (
                f"{func.name} is marked {text} at line {line}: its assertions are not a "
                "standing check of the unpatched code, or its inputs pass through a fixture"
            )
    if any(isinstance(n, ast.Yield | ast.YieldFrom) for n in _shallow(func)):
        return f"{func.name} is a generator: pytest does not run its assertions"
    site = point.site.lineno
    arguments = func.args
    params = {a.arg for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)}
    params.update(a.arg for a in (arguments.vararg, arguments.kwarg) if a is not None)
    row_names = {name for row in _parametrize(func) for name in row}
    fixtures = params - row_names - {"self", "cls"}
    bound_in_function: dict[str, int] = {}
    declared: dict[str, int] = {}
    for node in _shallow(func):
        names: list[str] = []
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            names = [node.id]
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names = [node.name]
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names = [(alias.asname or alias.name).split(".")[0] for alias in node.names]
        elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
            names = [node.name]
        elif isinstance(node, ast.MatchMapping) and node.rest:
            names = [node.rest]
        elif isinstance(node, ast.Global | ast.Nonlocal):
            for name in node.names:
                declared.setdefault(name, node.lineno)
        for name in names:
            bound_in_function.setdefault(name, getattr(node, "lineno", func.lineno))
    module_names, module_mutable = facts.names, facts.mutable
    module_lines = facts.lines
    imported = facts.imported
    defined = {
        s.name for s in point.prefix
        if isinstance(s, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }
    # the names the call depends on, through the bindings in force at its point
    relevant: list[str] = []
    todo = _free_names(call, keep_builtins=True)
    while todo:
        name = todo.pop(0)
        if name in relevant:
            continue
        relevant.append(name)
        binding = point.bindings.get(name)
        if binding is not None:
            todo.extend(_free_names(binding.value, keep_builtins=True))
    local: set[str] = set()
    global_: set[str] = set()
    for name in relevant:
        if name in declared:
            return (
                f"{func.name} declares {name!r} global or nonlocal at line {declared[name]}: "
                "the rule does not follow it"
            )
        if name in fixtures:
            return (
                f"the call depends on {name!r}, a fixture of {func.name}: what a fixture "
                "provides is not read"
            )
        if name in imported and (name in params or name in bound_in_function):
            return (
                f"{name!r} is imported or defined at module level and rebound in {func.name}: "
                "the call does not name the module's binding"
            )
        if name in params:
            local.add(name)
        elif name in bound_in_function:
            if name not in point.bindings and name not in defined:
                return (
                    f"{name!r} is assigned in {func.name} at line {bound_in_function[name]}, "
                    f"not by a plain assignment before line {site} at the test body's own "
                    "level: no input is bound for it there"
                )
            if name in _BUILTIN_NAMES:
                return f"{name!r} shadows a builtin at line {bound_in_function[name]}"
            local.add(name)
        elif name in module_names:
            if name in _BUILTIN_NAMES:
                return f"{name!r} shadows a builtin at module level"
            if len(module_lines.get(name, ())) > 1:
                lines = ", ".join(str(n) for n in module_lines[name])
                return (
                    f"{name!r} is bound more than once at module level (lines {lines}): the "
                    "rule does not decide which binding the call sees"
                )
            global_.add(name)
    # a binding in force reads the names it depends on as they were on its own line
    for name in relevant:
        binding = point.bindings.get(name)
        if binding is None:
            continue
        for used in _free_names(binding.value, keep_builtins=True):
            later = point.bindings.get(used)
            if used in local and later is not None and later.lineno >= binding.lineno:
                return (
                    f"line {later.lineno} rebinds {used!r}, which line {binding.lineno} reads: "
                    f"the value in force at line {site} is not the one that line used"
                )
    if facts.star and any(name not in local and name not in _BUILTIN_NAMES for name in relevant):
        return (
            f"the star import at line {facts.star} may rebind a module-level name the call "
            "depends on"
        )
    # a module-level value is read in the module's scope, never in the test's
    todo = [n for n in global_ if n in aliases]
    seen_module: set[str] = set()
    while todo:
        name = todo.pop()
        if name in seen_module:
            continue
        seen_module.add(name)
        for used in _free_names(aliases[name], keep_builtins=True):
            if used in bound_in_function or used in params:
                return (
                    f"the module-level {name!r} reads {used!r}, which {func.name} binds itself: "
                    "the rule would read the test's value for the module's"
                )
            if used in aliases:
                todo.append(used)
    # a call that is handed a value some statement can change -- in a binding in force, or
    # among the call's own arguments -- may change the input it is read to state
    rows = _parametrize(func)

    def mutable_local(name: str) -> bool:
        if name in row_names:
            return not all(name in row and _immutable(row[name], aliases) for row in rows)
        binding = point.bindings.get(name)
        return binding is None or not _immutable(binding.value, aliases)

    handed_from: list[tuple[int, ast.AST]] = [
        (point.bindings[n].lineno, point.bindings[n].value)
        for n in relevant if n in point.bindings
    ]
    if isinstance(call, ast.Call):
        handed_from.extend(
            (getattr(a, "lineno", site), a) for a in (*call.args, *(k.value for k in call.keywords))
        )
    for at, value in handed_from:
        for inner in ast.walk(value):
            if not isinstance(inner, ast.Call):
                continue
            # what the call is handed: its arguments and, for a method, its receiver --
            # not the name of the function it calls
            handed = [*inner.args, *(k.value for k in inner.keywords)]
            if isinstance(inner.func, ast.Attribute):
                handed.append(inner.func.value)
            touched = [
                n for part in handed for n in _free_names(part, keep_builtins=True)
                if (n in local and mutable_local(n)) or n in global_ & module_mutable
            ]
            if touched:
                return (
                    f"line {at} hands {touched[0]!r} to {ast.unparse(inner.func)} on the way to "
                    f"the assertion at line {site}: a state change the rule cannot rule out"
                )
    selected = {id(point.bindings[n]) for n in relevant if n in point.bindings}
    watched = local | (global_ & module_mutable)
    for statement in point.prefix:
        line = statement.lineno
        if isinstance(statement, ast.Return | ast.Raise):
            verb = "returns" if isinstance(statement, ast.Return) else "raises"
            return f"line {line} {verb} before the assertion at line {site}: no run reaches it"
        if isinstance(statement, ast.Expr) and _exit_call(statement.value):
            return (
                f"line {line} calls {_exit_call(statement.value)} before the assertion at "
                f"line {site}: a run may stop there"
            )
        if isinstance(statement, ast.While):
            return f"the while loop at line {line} may not end before the assertion at line {site}"
        if not isinstance(statement, _NESTED_SCOPES) and any(_child_statements(statement)):
            for inner in _shallow(statement):
                if isinstance(inner, ast.Return | ast.Raise) or _exit_call(inner):
                    return (
                        f"line {getattr(inner, 'lineno', line)} inside the {_kind(statement)} "
                        f"at line {line} may leave the test before the assertion at line {site}"
                    )
        if id(statement) in selected:
            continue  # the binding in force: the probe runs it too, in source order
        ignored: set[str] = set()
        examined: list[ast.AST] = [statement]
        if (
            isinstance(statement, ast.Assign)
            and len(statement.targets) == 1
            and isinstance(statement.targets[0], ast.Name)
            and statement.targets[0].id in point.bindings
        ):
            # an earlier assignment the binding in force replaces; only its value matters
            ignored = {statement.targets[0].id}
            examined = [statement.value]
        # first what the statement touches, then what it may do
        for node in (n for part in examined for n in ast.walk(part)):
            at = getattr(node, "lineno", line)
            if isinstance(node, ast.Name) and node.id not in ignored:
                if node.id in local:
                    return (
                        f"line {at} touches {node.id!r} between the binding in force and the "
                        f"assertion at line {site}: a rebinding, state change, alias or side "
                        "effect the rule cannot rule out"
                    )
                if node.id in watched:
                    return (
                        f"line {at} touches the module-level {node.id!r}, a value a statement "
                        f"can change, before the assertion at line {site}"
                    )
                if node.id in fixtures:
                    return (
                        f"line {at} uses the fixture {node.id!r} before the assertion at line "
                        f"{site}: what a fixture changes is not read"
                    )
            elif isinstance(node, ast.MatchAs | ast.MatchStar) and node.name in local:
                return f"line {at} rebinds {node.name!r} in a match pattern before line {site}"
        for node in (
            n for part in examined for piece in _evaluated_at_definition(part)
            for n in ast.walk(piece)
        ):
            at = getattr(node, "lineno", line)
            if isinstance(node, ast.Attribute | ast.Subscript) and isinstance(
                node.ctx, ast.Store | ast.Del
            ):
                return (
                    f"line {at} changes state through {ast.unparse(node)!r} before the "
                    f"assertion at line {site}: the rule cannot tell it from state the call reads"
                )
            if isinstance(node, ast.Call | ast.Await | ast.Yield | ast.YieldFrom | ast.NamedExpr):
                shown = ast.unparse(node.func) if isinstance(node, ast.Call) else _kind_of(node)
                return (
                    f"line {at} calls {shown} before the assertion at line {site}: a side "
                    "effect the rule cannot rule out"
                )
            if isinstance(node, ast.Attribute | ast.Subscript):
                # a property, `__getattr__` or `__getitem__` is a call by another name
                return (
                    f"line {at} reads {ast.unparse(node)!r} before the assertion at line "
                    f"{site}: an attribute or item read may run code the rule cannot rule out"
                )
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            refusal = _definition_refusal(statement, site, module_names)
            if refusal:
                return refusal
            continue  # nothing it runs changes anything (checked above)
        if not isinstance(statement, ast.Assign | ast.AnnAssign | ast.AugAssign | ast.Expr
                          | ast.Pass | ast.Assert):
            return (
                f"line {line} is a {_kind(statement)} statement before the assertion at line "
                f"{site}: control flow or a binding the rule does not read"
            )
    return ""


def _kind_of(node: ast.AST) -> str:
    return {"Await": "await", "Yield": "yield", "YieldFrom": "yield from",
            "NamedExpr": "an assignment expression"}.get(type(node).__name__, "an expression")


def _imported(module: ast.Module | None) -> set[str]:
    """The module-level names bound by an import, a def or a class."""
    out: set[str] = set()
    for node in module.body if module is not None else ():
        if isinstance(node, ast.Import | ast.ImportFrom):
            out.update((a.asname or a.name).split(".")[0] for a in node.names)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            out.add(node.name)
    return out


def _owners(tree: ast.Module) -> dict[int, tuple[ast.ClassDef, ...]]:
    """The classes each function of the module is defined in, outermost first, by the
    function node's id."""
    out: dict[int, tuple[ast.ClassDef, ...]] = {}

    def visit(node: ast.AST, enclosing: tuple[ast.ClassDef, ...]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, (*enclosing, child))
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                out[id(child)] = enclosing
                visit(child, ())
            else:
                visit(child, enclosing)

    visit(tree, ())
    return out


def probe_call(test_source: str, anchored_module: str) -> Call | None:
    """The call the replay test makes: ``_attest_value = <expression>`` inside
    the test function, with the setup's plain assignments in force before it as
    its names (D-255: a setup the program-point rule cannot read binds no input)."""
    try:
        tree = ast.parse(test_source)
    except (SyntaxError, ValueError):
        return None
    file_scope = _bindings(tree)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        target = next(
            (
                s for s in ast.walk(node)
                if isinstance(s, ast.Assign)
                and len(s.targets) == 1
                and isinstance(s.targets[0], ast.Name)
                and s.targets[0].id == "_attest_value"
            ),
            None,
        )
        if target is None:
            continue
        point = program_point(node, target, container="try")
        call = _resolve_call(target.value, _point_scope(file_scope, point), {}, anchored_module)
        if call is None:
            return None
        flow = flow_refusal(point, node, target.value, module=tree)
        return replace(call, flow=flow) if flow else call
    return None


# ------------------------------------------------------- deriving a value


@dataclass
class _Classes:
    """The tree's ``NamedTuple`` and ``@dataclass`` classes, by plain name, with
    their fields in order and literal defaults -- the only constructors whose
    repr this module derives."""

    fields: dict[str, tuple[tuple[str, ast.AST | None], ...]] = field(default_factory=dict)


def _class_fields(tree: ast.Module) -> dict[str, tuple[tuple[str, ast.AST | None], ...]]:
    found: dict[str, tuple[tuple[str, ast.AST | None], ...]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {ast.unparse(b).rsplit(".", 1)[-1] for b in node.bases}
        decorators = {ast.unparse(d).rsplit(".", 1)[-1].split("(")[0] for d in node.decorator_list}
        if "NamedTuple" not in bases and "dataclass" not in decorators:
            continue
        fields: list[tuple[str, ast.AST | None]] = []
        for statement in node.body:
            if isinstance(statement, ast.AnnAssign) and isinstance(statement.target, ast.Name):
                if "ClassVar" in ast.unparse(statement.annotation):
                    continue
                fields.append((statement.target.id, statement.value))
        found[node.name] = tuple(fields)
    return found


def _derive(
    node: ast.AST,
    classes: _Classes,
    scope: _Scope,
    row: dict[str, ast.AST],
    shadowed: frozenset[str] = frozenset(),
) -> str | None:
    """The repr of ``node`` as the running program would print it, or None when
    this module cannot know it without executing something.

    D-255: a name the test binds itself -- a local, or a parameter no parametrize row
    supplies -- is not the module constant of the same name, and derives nothing."""
    if isinstance(node, ast.Name):
        if node.id not in row and (
            node.id in shadowed or node.id in scope.locals or node.id in scope.calls
        ):
            return None
        bound = row.get(node.id) or scope.constants.get(node.id)
        if bound is None:
            return None
        node = bound
    if _is_literal(node):
        return repr(ast.literal_eval(node))
    if isinstance(node, ast.List | ast.Tuple):
        parts = [_derive(e, classes, scope, row, shadowed) for e in node.elts]
        if any(p is None for p in parts):
            return None
        inner = ", ".join(p for p in parts if p is not None)
        if isinstance(node, ast.Tuple):
            return f"({inner},)" if len(parts) == 1 else f"({inner})"
        return f"[{inner}]"
    if isinstance(node, ast.Dict):
        items = []
        for key, value in zip(node.keys, node.values, strict=True):
            if key is None:
                return None
            k = _derive(key, classes, scope, row, shadowed)
            v = _derive(value, classes, scope, row, shadowed)
            if k is None or v is None:
                return None
            items.append(f"{k}: {v}")
        return "{" + ", ".join(items) + "}"
    if isinstance(node, ast.Call):
        name = ast.unparse(node.func).rsplit(".", 1)[-1]
        fields = classes.fields.get(name)
        if fields is None:
            return None
        values: dict[str, str] = {}
        for (field_name, _default), arg in zip(fields, node.args, strict=False):
            shown = _derive(arg, classes, scope, row, shadowed)
            if shown is None:
                return None
            values[field_name] = shown
        if len(node.args) > len(fields):
            return None
        for keyword in node.keywords:
            if keyword.arg is None or keyword.arg not in dict(fields):
                return None
            shown = _derive(keyword.value, classes, scope, row, shadowed)
            if shown is None:
                return None
            values[keyword.arg] = shown
        rendered = []
        for field_name, default in fields:
            if field_name in values:
                rendered.append(f"{field_name}={values[field_name]}")
            elif default is not None and _is_literal(default):
                rendered.append(f"{field_name}={repr(ast.literal_eval(default))}")
            else:
                return None
        return f"{name}({', '.join(rendered)})"
    return None


# ----------------------------------------------------------- the sources


def _parametrize(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[dict[str, ast.AST]]:
    """Every row of every ``parametrize`` on this test, as name -> value node."""
    rows: list[dict[str, ast.AST]] = [{}]
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        callee = ast.unparse(decorator.func).rsplit(".", 1)[-1]
        if callee != "parametrize" or len(decorator.args) < 2:
            continue
        names_node, table = decorator.args[0], decorator.args[1]
        if isinstance(names_node, ast.Constant) and isinstance(names_node.value, str):
            names = [n.strip() for n in names_node.value.split(",") if n.strip()]
        elif isinstance(names_node, ast.List | ast.Tuple):
            names = [
                e.value for e in names_node.elts
                if isinstance(e, ast.Constant) and isinstance(e.value, str)
            ]
        else:
            continue
        if not isinstance(table, ast.List | ast.Tuple):
            continue
        expanded: list[dict[str, ast.AST]] = []
        for element in table.elts[:MAX_ROWS]:
            values: list[ast.AST]
            if isinstance(element, ast.Call) and ast.unparse(element.func).endswith("param"):
                values = list(element.args)
            elif len(names) == 1:
                values = [element]
            elif isinstance(element, ast.List | ast.Tuple):
                values = list(element.elts)
            else:
                continue
            if len(values) != len(names):
                continue
            for previous in rows:
                expanded.append({**previous, **dict(zip(names, values, strict=True))})
        rows = expanded or rows
    return rows


def _module_name(anchored: str, index: TreeIndex | None) -> str:
    if index is not None:
        found = index.module_of(anchored)
        if found:
            return found
    parts = anchored[:-3].split("/") if anchored.endswith(".py") else anchored.split("/")
    if parts and parts[0] == "src":
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _walk(root: Path) -> Iterable[tuple[Path, Path]]:
    files = 0
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in SKIPPED_DIRS)
        for filename in sorted(filenames):
            if not filename.endswith(".py"):
                continue
            path = Path(current) / filename
            files += 1
            if files > MAX_WITNESS_FILES:
                return
            try:
                if path.is_symlink() or path.stat().st_size > MAX_WITNESS_FILE_BYTES:
                    continue
            except OSError:
                continue
            yield path.relative_to(root), path


def _enclosing_definitions(source: str, line: int) -> list[str]:
    """The def/class names whose body spans ``line``, innermost last."""
    ranges = symbol_ranges(source) or ()
    return [name for name, start, end in sorted(ranges, key=lambda r: r[1]) if start <= line <= end]


def find_contracts(
    *,
    base_tree: Path,
    head_tree: Path | None,
    anchored: str,
    symbols: Sequence[str],
    pinned: Sequence[str],
    test_source: str,
) -> tuple[ContractRecord, ...]:
    """Every contract the base tree holds about ``symbols`` for the values the
    replay pins, each bound to the probe's own call and admitted or refused
    with its reason. Empty when the tree has none, or when the replay's call
    cannot be read.

    D-253: a contract is admitted only while it **stands at head** -- the same
    kind, symbol, input and derived value is found in ``head_tree`` too. Without a
    head tree nothing can be shown to stand, and nothing is admitted."""
    base = _contracts_in(base_tree, anchored, symbols, pinned, test_source)
    if not base:
        return ()
    # D-255: the program point is part of what stands -- a head that keeps the
    # assertion but adds a statement the rule cannot read before it rewrote it
    standing: set[tuple[str, str, str, str, bool]] = set()
    if head_tree is not None:
        standing = {
            (c.kind, c.symbol, c.input, c.derived, c.flow_bound)
            for c in _contracts_in(head_tree, anchored, symbols, pinned, test_source)
        }
    out: list[ContractRecord] = []
    for c in base:
        stands = (c.kind, c.symbol, c.input, c.derived, c.flow_bound) in standing
        if c.admitted and not stands:
            c = replace(
                c, admitted=False, standing_at_head=False,
                reason="the change removes or rewrites this contract at head",
            )
        else:
            c = replace(c, standing_at_head=stands)
        out.append(c)
    out.sort(key=lambda c: (not c.admitted, c.source, c.kind))
    return tuple(out[:MAX_CONTRACTS])


def _contracts_in(
    base_tree: Path,
    anchored: str,
    symbols: Sequence[str],
    pinned: Sequence[str],
    test_source: str,
) -> list[ContractRecord]:
    """The contracts one tree holds, before the standing check."""
    if not symbols or not pinned:
        return []
    root = base_tree.resolve()
    try:
        # built in memory: the tree is a worktree the executor mounts, and a
        # cache file written into it is a file the reproduction did not have
        index: TreeIndex | None = build_index(root)
    except (OSError, ValueError):
        index = None
    anchored_module = _module_name(anchored, index)
    probe = probe_call(test_source, anchored_module)
    if probe is None:
        return []
    wanted = frozenset(symbols)
    pinned_set = frozenset(pinned)
    classes = _Classes()
    spec_files: list[tuple[Path, str]] = []
    for relative, path in _walk(root):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if is_spec_file(relative):
            spec_files.append((relative, text))
        else:
            try:
                classes.fields.update(_class_fields(ast.parse(text)))
            except (SyntaxError, ValueError):
                continue
    callers = _callers(index, anchored_module, wanted, root)
    found: list[ContractRecord] = []
    for relative, text in spec_files:
        try:
            tree = ast.parse(text)
        except (SyntaxError, ValueError):
            continue
        scope = _bindings(tree)
        try:
            owners = _owners(tree)
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if not _TEST_NAME.match(node.name):
                    continue
                where = (tree, owners.get(id(node), ()))
                found.extend(
                    _assertion_contracts(
                        node, relative, scope, classes, probe, anchored_module, wanted,
                        pinned_set, where,
                    )
                )
                found.extend(
                    _caller_contracts(node, relative, scope, probe, callers, pinned_set, where)
                )
                if len(found) >= MAX_CONTRACTS * 4:
                    break
        except RecursionError:
            continue  # D-255: a file nested beyond the interpreter's depth states nothing read
    return found


def _assertion_contracts(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    relative: Path,
    file_scope: _Scope,
    classes: _Classes,
    probe: Call,
    anchored_module: str,
    wanted: frozenset[str],
    pinned: frozenset[str],
    where: tuple[ast.Module, tuple[ast.ClassDef, ...]],
) -> list[ContractRecord]:
    module, owner = where
    rows = _parametrize(node)
    arguments = node.args
    shadowed = frozenset(
        a.arg for a in (*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs)
    )
    out: list[ContractRecord] = []
    for statement in ast.walk(node):
        if not isinstance(statement, ast.Assert) or not isinstance(statement.test, ast.Compare):
            continue
        compare = statement.test
        if len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Eq | ast.Is):
            continue
        # D-255: the names the assertion sees are the ones in force where it runs
        point = program_point(node, statement)
        scope = _point_scope(file_scope, point)
        wide: _Scope | None = None
        flows: dict[int, str] = {}
        for row in rows:
            for call_side, expected_side in (
                (compare.left, compare.comparators[0]),
                (compare.comparators[0], compare.left),
            ):
                call = _resolve_call(call_side, scope, row, anchored_module)
                in_force = call is not None
                if call is None:
                    # recognised through a name not in force here: recorded, input unbound
                    wide = wide or _wide_scope(file_scope, node)
                    call = _resolve_call(call_side, wide, row, anchored_module)
                    if call is not None:
                        call = replace(call, args=None, kwargs=None, receiver=None)
                if call is None or call.module != anchored_module:
                    continue
                if call.callee.rsplit(".", 1)[-1] not in wanted and call.callee not in wanted:
                    continue
                derived = _derive(expected_side, classes, scope, row, shadowed)
                kind = "parametrize_row" if row else "bound_assertion"
                if id(call_side) not in flows:
                    flows[id(call_side)] = flow_refusal(
                        point, node, call_side, owners=owner, module=module
                    ) or ("" if in_force else _NOT_IN_FORCE.format(line=statement.lineno))
                out.append(
                    _record(
                        kind=kind, symbol=call.callee, probe=probe, call=call,
                        flow=flows[id(call_side)],
                        expected=ast.unparse(expected_side)[:120], derived=derived,
                        pinned=pinned, source=f"{relative.as_posix()}:{statement.lineno}",
                        call_path=f"{call.callee} <- {relative.as_posix()}::{node.name}",
                        path_bound=probe.module == call.module and probe.callee == call.callee
                        and probe.wrappers == call.wrappers,
                    )
                )
                break
    return out


def _record(
    *,
    kind: str,
    symbol: str,
    probe: Call,
    call: Call,
    expected: str,
    derived: str | None,
    pinned: frozenset[str],
    source: str,
    call_path: str,
    path_bound: bool,
    flow: str,
) -> ContractRecord:
    input_bound = probe.same_input(call)
    evaluated = derived is not None
    # a literal expected side is pinned as itself (`assert _attest_value == 6`);
    # an object's repr is pinned as the *string* the replay compared it to
    # (`assert re.sub(...) == 'Point(x=1, y=2)'`), so both spellings are tried
    covers = ""
    if derived is not None:
        if derived in pinned:
            covers = derived
        elif repr(derived) in pinned:
            covers = repr(derived)
    flow_bound = not flow
    admitted = flow_bound and input_bound and evaluated and path_bound and bool(covers)
    if admitted:
        reason = "admitted: same input at the assertion's program point, derived value, same entry"
    elif not flow_bound:
        reason = f"the source's program point is not read: {flow}"
    elif not path_bound:
        reason = (
            f"the probe entered through {probe.callee or '<unresolved>'}"
            f"{'(' + ','.join(probe.wrappers) + ')' if probe.wrappers else ''}, "
            f"the source calls {call.callee}"
            f"{'(' + ','.join(call.wrappers) + ')' if call.wrappers else ''}"
        )
    elif not input_bound and probe.flow:
        reason = f"the probe's own setup is not read: {probe.flow}"
    elif not input_bound:
        reason = f"the source's input ({call.input}) is not the probe's ({probe.input})"
    elif not evaluated:
        reason = f"the expected side {expected!r} is not a value this reader can derive"
    else:
        reason = f"the derived value {derived!r} is not one the failing assertion pins"
    return ContractRecord(
        kind=kind, symbol=symbol, input=call.input, expected=expected,
        derived=derived or "", pinned=covers, source=source, call_path=call_path,
        input_bound=input_bound, evaluated=evaluated, path_bound=path_bound,
        admitted=admitted, reason=reason, flow_bound=flow_bound, flow_reason=flow,
    )


# ---------------------------------------------------------- caller contracts


@dataclass(frozen=True)
class _Caller:
    module: str
    callee: str  # the caller's qualified name in its module
    symbol: str  # the touched symbol it calls
    site: str  # path:line of the call


def _callers(
    index: TreeIndex | None, anchored_module: str, wanted: frozenset[str], root: Path
) -> list[_Caller]:
    """The functions of the tree that call a touched symbol, from the index."""
    if index is None or not anchored_module:
        return []
    out: list[_Caller] = []
    for name in sorted(wanted):
        for site in index.callers_of(anchored_module, name):
            try:
                source = (root / site.path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            enclosing = _enclosing_definitions(source, site.line)
            if not enclosing:
                continue
            qualname = ".".join(enclosing[-2:]) if len(enclosing) > 1 else enclosing[-1]
            out.append(
                _Caller(
                    module=index.module_of(site.path), callee=qualname, symbol=name,
                    site=f"{site.path}:{site.line}",
                )
            )
    return out


def _caller_contracts(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    relative: Path,
    file_scope: _Scope,
    probe: Call,
    callers: list[_Caller],
    pinned: frozenset[str],
    where: tuple[ast.Module, tuple[ast.ClassDef, ...]],
) -> list[ContractRecord]:
    if not callers:
        return []
    module, owner = where
    scope = _Scope(
        from_module=dict(file_scope.from_module),
        module_alias=dict(file_scope.module_alias),
        constants=dict(file_scope.constants),
    )
    rows = _parametrize(node)
    out: list[ContractRecord] = []
    for statement in ast.walk(node):
        if not isinstance(statement, ast.With):
            continue
        exception = _expected_exception(statement)
        if exception is None:
            continue
        for inner in statement.body:
            for call_node in ast.walk(inner):
                if not isinstance(call_node, ast.Call):
                    continue
                for row in rows[:1] or [{}]:
                    call = _resolve_call(call_node, scope, row, "")
                    if call is None:
                        continue
                    for caller in callers:
                        if call.module != caller.module:
                            continue
                        if call.callee != caller.callee and call.callee.rsplit(".", 1)[-1] != (
                            caller.callee.rsplit(".", 1)[-1]
                        ):
                            continue
                        flow = flow_refusal(
                            program_point(node, call_node, container="raises"), node,
                            call_node, owners=owner, module=module,
                        )
                        out.append(
                            _record(
                                kind="caller_raises", symbol=caller.symbol, probe=probe,
                                call=call, expected=exception, derived=repr(exception),
                                pinned=pinned, flow=flow,
                                source=f"{relative.as_posix()}:{statement.lineno}",
                                call_path=(
                                    f"{caller.symbol} <- {caller.callee} ({caller.site}) "
                                    f"<- {relative.as_posix()}::{node.name}"
                                ),
                                path_bound=probe.module == caller.module
                                and probe.callee == caller.callee,
                            )
                        )
                        break
    return out


def _expected_exception(statement: ast.AST) -> str | None:
    """``with pytest.raises(X)`` -> "X"; None for any other statement."""
    if not isinstance(statement, ast.With):
        return None
    for item in statement.items:
        call = item.context_expr
        if (
            isinstance(call, ast.Call)
            and ast.unparse(call.func).rsplit(".", 1)[-1] in _RAISES
            and call.args
            and isinstance(call.args[0], ast.Name | ast.Attribute)
        ):
            return ast.unparse(call.args[0]).rsplit(".", 1)[-1]
    return None


# ======================================================================
# D-254: contract probes -- the fixed rule, in the product path
# ======================================================================

# How many contract probes one candidate's search may screen before it asks the
# model. A constant fixed before any measurement ran, not tuned on one: each
# screening costs three recordings on the merge base and one run on head.
MAX_CONTRACT_PROBES = 8
_BUILTIN_NAMES = frozenset(dir(builtins))


class NotConstructible(ValueError):
    """A contract the fixed rule cannot turn into a probe, with the reason."""


@dataclass(frozen=True)
class ContractProbe:
    """One probe read out of a base-tree contract about a touched symbol."""

    spec: ProbeSpec
    kind: str  # "bound_assertion" | "parametrize_row" | "caller_raises"
    site: str  # path:line of the assertion or `with raises` block
    row: int  # parametrize row, 0 when the test has none

    @property
    def origin(self) -> str:
        return f"{self.site}#{self.row}"


@dataclass(frozen=True)
class ContractSearch:
    """What the rule found for one candidate: the probes it built, in the order
    the search screens them, and every contract it could not build and why."""

    symbols: tuple[str, ...]
    probes: tuple[ContractProbe, ...]
    refused: tuple[tuple[str, str], ...]  # (site#row, reason)
    truncated: int  # probes built beyond MAX_CONTRACT_PROBES and not screened


def _is_test_module(module: str) -> bool:
    return any(
        part in ("tests", "test", "testing", "conftest") or part.startswith("test_")
        for part in module.split(".")
    )


def _free_names(node: ast.AST, *, keep_builtins: bool = False) -> list[str]:
    bound: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.comprehension):
            bound.update(t.id for t in ast.walk(inner.target) if isinstance(t, ast.Name))
        elif isinstance(inner, ast.Lambda):
            bound.update(a.arg for a in inner.args.args)
    found: list[str] = []
    for inner in ast.walk(node):
        if (
            isinstance(inner, ast.Name)
            and isinstance(inner.ctx, ast.Load)
            and inner.id not in bound
            and (keep_builtins or inner.id not in _BUILTIN_NAMES)
            and inner.id not in found
        ):
            found.append(inner.id)
    return found


def build_contract_probe(
    *,
    tree_file: ast.Module,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    statement: ast.stmt,
    call: ast.AST,
    row: dict[str, ast.AST],
) -> ProbeSpec:
    """Bind every free name of ``call`` from the test's own source, recursively:
    a parametrize row value, a top-level import of a module that is not a test
    module, an assignment earlier in the test function, or a module-level
    assignment of the test file. Anything else -- a fixture, a name the test
    module defines, an import of a test module -- is `NotConstructible`."""
    imports: dict[str, tuple[str, str]] = {}
    for node in tree_file.body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                text = f"from {node.module} import {alias.name}" + (
                    f" as {alias.asname}" if alias.asname else ""
                )
                imports[alias.asname or alias.name] = (text, node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                text = f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else "")
                imports[(alias.asname or alias.name).split(".")[0]] = (text, alias.name)
    module_assign: dict[str, ast.Assign] = {}
    local_defs: set[str] = set()
    for node in tree_file.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            module_assign[node.targets[0].id] = node
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            local_defs.add(node.name)
    # D-255: the assignments in force at the call's program point, and no other --
    # not one inside a branch before it, not one after it
    point = program_point(
        func, call, container="raises" if isinstance(statement, ast.With) else ""
    )
    body_assign: dict[str, ast.Assign] = dict(point.bindings) if point is not None else {}
    params = {a.arg for a in (*func.args.args, *func.args.kwonlyargs)}
    import_lines: list[str] = []
    setup: list[str] = []
    # D-255: the test body's own assignments run in the order the test runs them
    body_lines: list[tuple[int, str]] = []
    visiting: set[str] = set()
    placed: set[str] = set()

    def bind(name: str) -> None:
        if name in placed:
            return
        if name in visiting:
            raise NotConstructible(f"name {name!r} is defined in terms of itself")
        visiting.add(name)
        if name in row:
            for inner in _free_names(row[name]):
                bind(inner)
            setup.append(f"{name} = {ast.unparse(row[name])}")
        elif name in body_assign:
            for inner in _free_names(body_assign[name].value):
                bind(inner)
            body_lines.append((body_assign[name].lineno, ast.unparse(body_assign[name])))
        elif name in imports:
            text, module = imports[name]
            if _is_test_module(module):
                raise NotConstructible(f"{name!r} is imported from the test module {module}")
            if text not in import_lines:
                import_lines.append(text)
        elif name in module_assign:
            for inner in _free_names(module_assign[name].value):
                bind(inner)
            setup.append(ast.unparse(module_assign[name]))
        elif name in params:
            raise NotConstructible(f"{name!r} is a fixture of {func.name}")
        elif name in local_defs:
            raise NotConstructible(f"{name!r} is defined by the test module itself")
        else:
            raise NotConstructible(f"{name!r} is bound nowhere the rule reads")
        visiting.discard(name)
        placed.add(name)

    for name in _free_names(call):
        bind(name)
    setup.extend(text for _line, text in sorted(body_lines))
    return ProbeSpec(
        imports="\n".join(import_lines), setup="\n".join(setup), expression=ast.unparse(call)
    )


def contract_probes(
    base_tree: Path, anchored: str, symbols: Sequence[str]
) -> ContractSearch:
    """D-254: every contract the base tree's tests state about ``symbols`` -- the
    definitions a candidate's change touched in ``anchored`` -- turned into probes
    by the fixed rule, in (file, line, row) order, at most `MAX_CONTRACT_PROBES`.

    A contract site is an ``assert`` comparing (``==``/``is``) a call that
    resolves, through the test's imports, to a touched symbol of the anchored
    module; or a ``with raises(...)`` block whose body calls a function the tree
    index names as a caller of a touched symbol. The probe is that call, with
    its free names bound by `build_contract_probe`, one per parametrize row, and
    it must pass the probe's own hygiene and import rules. Nothing here reads a
    model, a pinned value or the change's intent: the result depends on the base
    tree and the touched names alone, and the search screens it like any other
    probe."""
    wanted = frozenset(symbols)
    empty = ContractSearch(symbols=tuple(symbols), probes=(), refused=(), truncated=0)
    if not wanted:
        return empty
    root = base_tree.resolve()
    try:
        index: TreeIndex | None = build_index(root)
    except (OSError, ValueError, SyntaxError):
        index = None
    module = _module_name(anchored, index)
    callers = _callers(index, module, wanted, root)
    roots = tree_roots(root)
    built: list[tuple[str, int, int, ContractProbe]] = []
    refused: list[tuple[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for relative, path in _walk(root):
        if not is_spec_file(relative):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            tree_file = ast.parse(text)
        except (OSError, SyntaxError, ValueError):
            continue
        file_scope = _bindings(tree_file)
        try:
            owners = _owners(tree_file)
            for func in ast.walk(tree_file):
                if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if not _TEST_NAME.match(func.name):
                    continue
                rows = _parametrize(func)
                kind_rows = "parametrize_row" if rows != [{}] else "bound_assertion"
                wide: _Scope | None = None
                for statement in ast.walk(func):
                    if not isinstance(statement, ast.stmt):
                        continue
                    point_scope = _point_scope(file_scope, program_point(func, statement))
                    sites: list[tuple[str, ast.AST, bool]] = []
                    # D-255: recognised at the program point first; a site whose call resolves
                    # only through a name not in force there is still a site, refused below
                    for scope, in_force in ((point_scope, True), (None, False)):
                        if sites:
                            break
                        if scope is None:
                            if wide is None:
                                wide = _wide_scope(file_scope, func)
                            scope = wide
                        if isinstance(statement, ast.Assert) and isinstance(
                            statement.test, ast.Compare
                        ):
                            compare = statement.test
                            if len(compare.ops) == 1 and isinstance(
                                compare.ops[0], ast.Eq | ast.Is
                            ):
                                for side in (compare.left, compare.comparators[0]):
                                    resolved = _resolve_call(side, scope, rows[0], module)
                                    if (
                                        resolved is not None
                                        and resolved.module == module
                                        and (
                                            resolved.callee in wanted
                                            or resolved.callee.rsplit(".", 1)[-1] in wanted
                                        )
                                    ):
                                        sites.append((kind_rows, side, in_force))
                                        break
                        elif isinstance(statement, ast.With) and _expected_exception(statement):
                            names = {c.callee.rsplit(".", 1)[-1] for c in callers}
                            modules = {c.module for c in callers}
                            for inner in (n for s in statement.body for n in ast.walk(s)):
                                if not isinstance(inner, ast.Call):
                                    continue
                                resolved = _resolve_call(inner, scope, rows[0], "")
                                if (
                                    resolved is not None
                                    and resolved.module in modules
                                    and resolved.callee.rsplit(".", 1)[-1] in names
                                ):
                                    sites.append(("caller_raises", inner, in_force))
                                    break
                    if not sites:
                        continue
                    kind, call, in_force = sites[0]
                    site = f"{relative.as_posix()}:{statement.lineno}"
                    # D-255: a contract whose program point the rule cannot read is no probe
                    flow = flow_refusal(
                        program_point(
                            func, call, container="raises" if kind == "caller_raises" else ""
                        ),
                        func, call, owners=owners.get(id(func), ()), module=tree_file,
                    ) or ("" if in_force else _NOT_IN_FORCE.format(line=statement.lineno))
                    if flow:
                        refused.extend((f"{site}#{number}", flow) for number in range(len(rows)))
                        continue
                    for number, row in enumerate(rows):
                        try:
                            spec = build_contract_probe(
                                tree_file=tree_file, func=func, statement=statement, call=call,
                                row=row,
                            )
                        except NotConstructible as exc:
                            refused.append((f"{site}#{number}", str(exc)))
                            continue
                        hygiene = hygiene_refusal(spec)
                        if hygiene is not None:
                            refused.append((f"{site}#{number}", f"hygiene: {hygiene}"))
                            continue
                        if not reaches_the_tree(spec, roots):
                            refused.append(
                                (f"{site}#{number}", "the probe imports nothing of the project")
                            )
                            continue
                        key = (spec.imports, spec.setup, spec.expression)
                        if key in seen:
                            continue
                        seen.add(key)
                        built.append(
                            (relative.as_posix(), statement.lineno, number,
                             ContractProbe(spec=spec, kind=kind, site=site, row=number))
                        )
        except RecursionError:
            # D-255: a file nested beyond the interpreter's depth yields nothing more
            continue
    built.sort(key=lambda item: item[:3])
    probes = tuple(item[3] for item in built)
    return ContractSearch(
        symbols=tuple(symbols),
        probes=probes[:MAX_CONTRACT_PROBES],
        refused=tuple(sorted(refused)),
        truncated=max(0, len(probes) - MAX_CONTRACT_PROBES),
    )
