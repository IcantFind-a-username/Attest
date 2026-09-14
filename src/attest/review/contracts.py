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

Everything found is recorded, admitted or not, with the reason: a contract the
probe did not bind is exactly the fact the next probe needs. Deterministic end
to end: file reads and ``ast``, no model.
"""

from __future__ import annotations

import ast
import os
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from attest.certification.intent import ContractRecord
from attest.review.index import TreeIndex, tree_index
from attest.review.intent import (
    MAX_WITNESS_FILE_BYTES,
    MAX_WITNESS_FILES,
    SKIPPED_DIRS,
    is_spec_file,
    symbol_ranges,
)

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

    @property
    def input(self) -> str:
        if self.args is None or self.kwargs is None:
            return "<unbound>"
        parts = list(self.args) + [f"{k}={v}" for k, v in self.kwargs]
        return ", ".join(parts)

    def same_input(self, other: Call) -> bool:
        return (
            self.args is not None
            and other.args is not None
            and self.args == other.args
            and self.kwargs == other.kwargs
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
            if isinstance(target, ast.Name) and _is_literal(node.value):
                scope.constants[target.id] = node.value
    return scope


def _is_literal(node: ast.AST) -> bool:
    try:
        ast.literal_eval(node)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return False
    return True


def _literal_repr(node: ast.AST, scope: _Scope, row: dict[str, ast.AST]) -> str | None:
    """The canonical repr of a literal argument, following one level of names."""
    if isinstance(node, ast.Name):
        node = row.get(node.id) or scope.locals.get(node.id) or scope.constants.get(node.id) or node
        if isinstance(node, ast.Name):
            return None
    try:
        return repr(ast.literal_eval(node))
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return None


def _resolve_call(
    node: ast.AST, scope: _Scope, row: dict[str, ast.AST], anchored_module: str
) -> Call | None:
    """Unwrap ``list(sorted(f(x)))`` to the innermost call that resolves to a
    module of the tree, keeping the wrapper chain."""
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
        current = scope.calls[current.id]
    if not isinstance(current, ast.Call):
        return None
    func = current.func
    module = ""
    callee = ""
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
            elif receiver.id in scope.calls:
                inner = _resolve_call(scope.calls[receiver.id], scope, row, anchored_module)
                if inner is not None and inner.callee and "." not in inner.callee:
                    module, callee = inner.module, f"{inner.callee}.{func.attr}"
        elif isinstance(receiver, ast.Call):
            inner = _resolve_call(receiver, scope, row, anchored_module)
            if inner is not None and inner.callee and "." not in inner.callee:
                module, callee = inner.module, f"{inner.callee}.{func.attr}"
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
    )


def probe_call(test_source: str, anchored_module: str) -> Call | None:
    """The call the replay test makes: ``_attest_value = <expression>`` inside
    the test function, with the setup's literal assignments as its names."""
    try:
        tree = ast.parse(test_source)
    except (SyntaxError, ValueError):
        return None
    scope = _bindings(tree)
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        expression: ast.AST | None = None
        for statement in ast.walk(node):
            if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
                target = statement.targets[0]
                if isinstance(target, ast.Name) and target.id == "_attest_value":
                    expression = statement.value
                elif isinstance(target, ast.Name) and _is_literal(statement.value):
                    scope.locals[target.id] = statement.value
                elif isinstance(target, ast.Name) and isinstance(statement.value, ast.Call):
                    scope.calls[target.id] = statement.value
        if expression is not None:
            return _resolve_call(expression, scope, {}, anchored_module)
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


def _derive(node: ast.AST, classes: _Classes, scope: _Scope, row: dict[str, ast.AST]) -> str | None:
    """The repr of ``node`` as the running program would print it, or None when
    this module cannot know it without executing something."""
    if isinstance(node, ast.Name):
        bound = row.get(node.id) or scope.constants.get(node.id)
        if bound is None:
            return None
        node = bound
    if _is_literal(node):
        return repr(ast.literal_eval(node))
    if isinstance(node, ast.List | ast.Tuple):
        parts = [_derive(e, classes, scope, row) for e in node.elts]
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
            k, v = _derive(key, classes, scope, row), _derive(value, classes, scope, row)
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
            shown = _derive(arg, classes, scope, row)
            if shown is None:
                return None
            values[field_name] = shown
        if len(node.args) > len(fields):
            return None
        for keyword in node.keywords:
            if keyword.arg is None or keyword.arg not in dict(fields):
                return None
            shown = _derive(keyword.value, classes, scope, row)
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
    anchored: str,
    symbols: Sequence[str],
    pinned: Sequence[str],
    test_source: str,
) -> tuple[ContractRecord, ...]:
    """Every contract the base tree holds about ``symbols`` for the values the
    replay pins, each bound to the probe's own call and admitted or refused
    with its reason. Empty when the tree has none, or when the replay's call
    cannot be read."""
    if not symbols or not pinned:
        return ()
    root = base_tree.resolve()
    try:
        index: TreeIndex | None = tree_index(root)
    except (OSError, ValueError):
        index = None
    anchored_module = _module_name(anchored, index)
    probe = probe_call(test_source, anchored_module)
    if probe is None:
        return ()
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
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            if not _TEST_NAME.match(node.name):
                continue
            found.extend(
                _assertion_contracts(
                    node, relative, scope, classes, probe, anchored_module, wanted, pinned_set
                )
            )
            found.extend(
                _caller_contracts(node, relative, scope, probe, callers, pinned_set)
            )
            if len(found) >= MAX_CONTRACTS * 4:
                break
    found.sort(key=lambda c: (not c.admitted, c.source, c.kind))
    return tuple(found[:MAX_CONTRACTS])


def _assertion_contracts(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    relative: Path,
    file_scope: _Scope,
    classes: _Classes,
    probe: Call,
    anchored_module: str,
    wanted: frozenset[str],
    pinned: frozenset[str],
) -> list[ContractRecord]:
    scope = _Scope(
        from_module=dict(file_scope.from_module),
        module_alias=dict(file_scope.module_alias),
        constants=dict(file_scope.constants),
    )
    for statement in ast.walk(node):
        if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
            target = statement.targets[0]
            if isinstance(target, ast.Name) and isinstance(statement.value, ast.Call):
                scope.calls[target.id] = statement.value
    rows = _parametrize(node)
    out: list[ContractRecord] = []
    for statement in ast.walk(node):
        if not isinstance(statement, ast.Assert) or not isinstance(statement.test, ast.Compare):
            continue
        compare = statement.test
        if len(compare.ops) != 1 or not isinstance(compare.ops[0], ast.Eq | ast.Is):
            continue
        for row in rows:
            for call_side, expected_side in (
                (compare.left, compare.comparators[0]),
                (compare.comparators[0], compare.left),
            ):
                call = _resolve_call(call_side, scope, row, anchored_module)
                if call is None or call.module != anchored_module:
                    continue
                if call.callee.rsplit(".", 1)[-1] not in wanted and call.callee not in wanted:
                    continue
                derived = _derive(expected_side, classes, scope, row)
                kind = "parametrize_row" if row else "bound_assertion"
                out.append(
                    _record(
                        kind=kind, symbol=call.callee, probe=probe, call=call,
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
    admitted = input_bound and evaluated and path_bound and bool(covers)
    if admitted:
        reason = "admitted: same input, derived value, same entry"
    elif not path_bound:
        reason = (
            f"the probe entered through {probe.callee or '<unresolved>'}"
            f"{'(' + ','.join(probe.wrappers) + ')' if probe.wrappers else ''}, "
            f"the source calls {call.callee}"
            f"{'(' + ','.join(call.wrappers) + ')' if call.wrappers else ''}"
        )
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
        admitted=admitted, reason=reason,
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
) -> list[ContractRecord]:
    if not callers:
        return []
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
                        out.append(
                            _record(
                                kind="caller_raises", symbol=caller.symbol, probe=probe,
                                call=call, expected=exception, derived=repr(exception),
                                pinned=pinned,
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
