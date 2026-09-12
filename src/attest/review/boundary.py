"""The conditions a change removed or altered in the definitions it touched (D-240 a).

`boundary` mutations certified 1 of 13 on the forty (2026-09-13): the change is
`x >= 13` becoming `x > 13`, and the probe search -- told the changed lines, the
definitions, the diff and what the tests assert -- still rarely tried the one
input that sits on the boundary. `none_guard` and `guard_raise` mutations
delete an `if` that returned early or raised. All three are a fact of the two
sources: a condition present in the merge base's definition and absent from
the head's, or the same operands under a different operator or constant.

Read from the ASTs, rendered in the words a probe needs, no model anywhere.
Only the definitions the change touched are read; a condition that moved
elsewhere in the file is not this change's.
"""

from __future__ import annotations

import ast
from collections.abc import Collection

MAX_CONDITIONS = 4
_COMPARE_OPS = {
    ast.Lt: "<",
    ast.LtE: "<=",
    ast.Gt: ">",
    ast.GtE: ">=",
    ast.Eq: "==",
    ast.NotEq: "!=",
    ast.Is: "is",
    ast.IsNot: "is not",
    ast.In: "in",
    ast.NotIn: "not in",
}


def _definitions(tree: ast.Module) -> dict[str, ast.AST]:
    """Qualified name -> def/class node, for every definition in ``tree``."""
    found: dict[str, ast.AST] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
                name = f"{prefix}{child.name}"
                found[name] = child
                walk(child, f"{name}.")
            else:
                walk(child, prefix)

    walk(tree, "")
    return found


def _touched(tree: ast.Module, changed: Collection[int]) -> list[str]:
    lines = set(changed)
    names: list[str] = []
    for name, node in _definitions(tree).items():
        last = getattr(node, "end_lineno", None) or node.lineno  # type: ignore[attr-defined]
        if any(node.lineno <= line <= last for line in lines):  # type: ignore[attr-defined]
            names.append(name)
    # innermost definitions carry the condition; drop a class that only
    # contains a touched method
    return [n for n in names if not any(o != n and o.startswith(f"{n}.") for o in names)]


def _conditions(node: ast.AST) -> dict[str, ast.AST]:
    """Rendered condition -> the statement it guards (or the expression itself)."""
    out: dict[str, ast.AST] = {}
    for inner in ast.walk(node):
        if isinstance(inner, ast.If | ast.While | ast.IfExp | ast.Assert):
            out.setdefault(ast.unparse(inner.test), inner)
        elif isinstance(inner, ast.comprehension):
            for test in inner.ifs:
                out.setdefault(ast.unparse(test), inner)
        elif isinstance(inner, ast.Compare):
            out.setdefault(ast.unparse(inner), inner)
    return out


def _operands(text: str) -> str | None:
    """The comparison's operands with the operator and constants blanked, so that
    `x >= 13` and `x > 13` pair up as the same comparison, altered."""
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    if not isinstance(node, ast.Compare) or len(node.ops) != 1:
        return None
    left, right = node.left, node.comparators[0]
    if isinstance(right, ast.Constant):
        return f"{ast.unparse(left)} ? <const>"
    if isinstance(left, ast.Constant):
        return f"<const> ? {ast.unparse(right)}"
    return f"{ast.unparse(left)} ? {ast.unparse(right)}"


def _boundary(text: str) -> str | None:
    try:
        node = ast.parse(text, mode="eval").body
    except SyntaxError:
        return None
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        for operand in (node.left, node.comparators[0]):
            if isinstance(operand, ast.Constant) and not isinstance(operand.value, bool):
                return repr(operand.value)
    return None


def _did(statement: ast.AST) -> str:
    """What the guarded statement did, for a removed guard."""
    if not isinstance(statement, ast.If):
        return ""
    for inner in statement.body:
        if isinstance(inner, ast.Raise):
            exc = inner.exc
            if isinstance(exc, ast.Call):
                exc = exc.func
            name = ast.unparse(exc).rsplit(".", 1)[-1] if exc is not None else "an exception"
            return f" (it raised {name})"
        if isinstance(inner, ast.Return):
            return " (it returned early)"
        if isinstance(inner, ast.Continue | ast.Break):
            return " (it left the loop)"
    return ""


def changed_conditions(
    base_source: str, head_source: str, changed_lines: Collection[int]
) -> tuple[str, ...]:
    """The conditions this change removed or altered, one sentence each, at most
    ``MAX_CONDITIONS``; empty when either source does not parse or nothing moved."""
    try:
        base_tree = ast.parse(base_source)
        head_tree = ast.parse(head_source)
    except (SyntaxError, ValueError):
        return ()
    base_defs = _definitions(base_tree)
    head_defs = _definitions(head_tree)
    out: list[str] = []
    for name in _touched(head_tree, changed_lines):
        head_node = head_defs.get(name)
        base_node = base_defs.get(name)
        if head_node is None or base_node is None:
            continue
        before = _conditions(base_node)
        after = _conditions(head_node)
        removed = [c for c in before if c not in after]
        added = [c for c in after if c not in before]
        short = name.rsplit(".", 1)[-1]
        paired: set[str] = set()
        for old in removed:
            shape = _operands(old)
            match = next(
                (new for new in added if new not in paired and _operands(new) == shape), None
            )
            if shape is not None and match is not None:
                paired.add(match)
                boundary = _boundary(match) or _boundary(old)
                tail = f" (the boundary is {boundary})" if boundary is not None else ""
                out.append(f"in `{short}`: the comparison `{old}` became `{match}`{tail}")
            else:
                out.append(f"in `{short}`: the guard `{old}` was removed{_did(before[old])}")
            if len(out) >= MAX_CONDITIONS:
                return tuple(out)
        for new in added:
            if new in paired:
                continue
            out.append(f"in `{short}`: the condition `{new}` was added")
            if len(out) >= MAX_CONDITIONS:
                return tuple(out)
    return tuple(out)
