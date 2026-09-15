"""Conservative refusals for implicit test context, without executing repository code.

This screens local setup mechanisms, not the transitive effects of imported code or
ambient pytest plugins. Passing this screen alone is never an admission certificate.
"""

from __future__ import annotations

import ast
from pathlib import Path

_HOOKS = frozenset({
    "setup", "teardown", "setup_module", "teardown_module", "setup_function",
    "teardown_function", "setup_class", "teardown_class", "setup_method", "teardown_method",
    "setUp", "tearDown", "setUpClass", "tearDownClass", "pytest_plugins",
})


def _inert(node: ast.AST) -> bool:
    return all(isinstance(n, (
        ast.Constant, ast.Name, ast.Load, ast.Store, ast.Tuple, ast.List, ast.Set, ast.Dict,
        ast.UnaryOp, ast.UAdd, ast.USub,
    )) for n in ast.walk(node))


def _plain_parametrize(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call) or ast.unparse(node.func) != "pytest.mark.parametrize":
        return False
    if len(node.args) != 2:
        return False
    # Rows are evaluated at import, even when the tested call never uses their
    # parameters. A constructor or callback there can replace the tested callable.
    if any(isinstance(n, ast.Call) for arg in node.args for n in ast.walk(arg)):
        return False
    try:
        names, rows = (ast.literal_eval(arg) for arg in node.args)
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return False
    if not isinstance(names, str | list | tuple) or not isinstance(rows, list | tuple) or not rows:
        return False
    # ids can be a callback; indirect may invoke fixtures. Even a decorator argument
    # discarded by the row reader executes before collection, so it cannot be ignored.
    for keyword in node.keywords:
        try:
            value = ast.literal_eval(keyword.value)
        except (ValueError, TypeError, SyntaxError, RecursionError):
            return False
        if keyword.arg == "ids":
            if value is not None and not (
                isinstance(value, list | tuple)
                and all(v is None or isinstance(v, str | int | float | bool) for v in value)
            ):
                return False
        elif keyword.arg == "indirect":
            if value is not False:
                return False
        elif keyword.arg == "scope":
            if not isinstance(value, str):
                return False
        else:
            return False
    return True


def _body_refusal(body: list[ast.stmt], *, pytest_imported: bool = False) -> tuple[int, str] | None:
    for statement in body:
        names: list[str] = []
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names = [statement.name]
        elif isinstance(statement, ast.Import | ast.ImportFrom):
            names = [a.asname or a.name for a in statement.names]
        elif isinstance(statement, ast.Assign):
            names = [n.id for t in statement.targets for n in ast.walk(t)
                     if isinstance(n, ast.Name)]
        if "pytest" in names:
            if not isinstance(statement, ast.Import) or any(
                a.name != "pytest" for a in statement.names if (a.asname or a.name) == "pytest"
            ):
                return statement.lineno, "the pytest decorator binding is unexamined or rebound"
            pytest_imported = True
        if any(n in _HOOKS or n.startswith("pytest_") for n in names):
            return statement.lineno, "setup hook or plugin declaration"
        if isinstance(statement, ast.Import | ast.ImportFrom):
            continue  # imported modules' execution is explicitly outside this screen
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            if any(not (
                statement.name.startswith("test") and pytest_imported and _plain_parametrize(d)
            ) for d in statement.decorator_list):
                return statement.lineno, "decorator may install an implicit fixture or wrapper"
            # Test marks/parametrize are checked by the existing program-point reader.
            evaluated = [*statement.args.defaults,
                         *(v for v in statement.args.kw_defaults if v is not None)]
            evaluated.extend(a.annotation for a in (
                *statement.args.posonlyargs, *statement.args.args, *statement.args.kwonlyargs,
                *(a for a in (statement.args.vararg, statement.args.kwarg) if a is not None),
            ) if a.annotation is not None)
            if statement.returns is not None:
                evaluated.append(statement.returns)
            if any(not _inert(v) for v in evaluated):
                return statement.lineno, "function default or annotation executes unexamined code"
            continue
        if isinstance(statement, ast.ClassDef):
            if statement.bases or statement.keywords or statement.decorator_list:
                return statement.lineno, "class construction or inherited setup is unexamined"
            refusal = _body_refusal(statement.body, pytest_imported=pytest_imported)
            if refusal:
                return refusal
            continue
        if isinstance(statement, ast.Pass):
            continue
        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant):
            continue
        if isinstance(statement, ast.Assign) and all(
            isinstance(t, ast.Name) for t in statement.targets
        ) and _inert(statement.value):
            continue
        return statement.lineno, "module or class body executes unexamined code"
    return None


def context_refusal(root: Path, relative: Path, module: ast.Module) -> str:
    """Screen the test module and ancestor conftests inside this immutable tree.

    Even an apparently unrelated conftest can register hooks or import fixtures. Only an
    empty/docstring/pass conftest is supported. Missing/unreadable evidence is not clearance.
    The observer calls this independently on both trees; no generator flags are consumed.
    """
    for parent in (relative.parent, *relative.parent.parents):
        conftest = root / parent / "conftest.py"
        label = (parent / "conftest.py").as_posix()
        try:
            if conftest.is_symlink():
                return f"test context {label}: symlinked setup is unexamined"
            if not conftest.exists():
                continue
            if conftest.stat().st_size > 64_000:
                return f"test context {label}: setup exceeds the reading limit"
            tree = ast.parse(conftest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError):
            return f"test context {label}: setup cannot be read"
        for statement in tree.body:
            if isinstance(statement, ast.Pass) or (
                isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
                and isinstance(statement.value.value, str)
            ):
                continue
            return f"test context {label}:{statement.lineno}: conftest execution is unexamined"
    refusal = _body_refusal(module.body)
    if refusal:
        line, reason = refusal
        return f"test context {relative.as_posix()}:{line}: {reason}"
    return ""
