"""Conservative refusals for implicit test context, without executing repository code.

This screens local setup mechanisms, not the transitive effects of imported code or
ambient pytest plugins. Passing this screen alone is never an admission certificate.

D-282: a conftest is read rather than refused for existing. Code that runs before the
assertion -- a conftest's module body, its hooks, an autouse fixture's setup, and any
fixture the test asks for -- is refused only when a call or a store it makes resolves to
the module under review or to a module that one imports, or when the rule cannot tell
what it resolves to. A name is followed to the module it is imported from, never into
that module's body: that limit is stated, not closed. Teardown after a fixture's `yield`
runs after the assertion and is not read.
"""

from __future__ import annotations

import ast
import builtins
from dataclasses import dataclass
from pathlib import Path

# a builtin that reaches into a namespace is not a harmless builtin
_NAMESPACE_BUILTINS = frozenset({
    "setattr", "delattr", "globals", "locals", "vars", "exec", "eval", "compile", "__import__",
})
_BUILTINS = frozenset(dir(builtins)) - _NAMESPACE_BUILTINS
# pytest's own patching API, whatever object it is reached through
_PATCH_METHODS = frozenset({
    "setattr", "delattr", "setitem", "delitem", "setenv", "delenv", "syspath_prepend", "chdir",
})

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


def _body_refusal(
    body: list[ast.stmt],
    *,
    pytest_imported: bool = False,
    fixtures: frozenset[str] = frozenset(),
) -> tuple[int, str] | None:
    for statement in body:
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef) and (
            statement.name in fixtures and _fixture_decorators(statement)[0]
        ):
            continue  # D-282: read as a fixture, with its own reason recorded
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
            # D-282: a decorator is screened on the test that states the contract
            # (`TestContext.function_refusal`); another function's does not reach it.
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
            refusal = _body_refusal(
                statement.body, pytest_imported=pytest_imported, fixtures=fixtures,
            )
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


def _imports(body: list[ast.stmt]) -> dict[str, str]:
    """Local name -> the module it is imported from, for the file's own imports."""
    found: dict[str, str] = {}
    for node in body:
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                found[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.Import):
            for alias in node.names:
                found[(alias.asname or alias.name).split(".")[0]] = alias.name
    return found


def _root(node: ast.AST) -> str:
    while isinstance(node, ast.Attribute | ast.Subscript | ast.Call):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else ""


def _reaches(module: str, related: frozenset[str]) -> bool:
    return any(module == name or module.startswith(f"{name}.") for name in related)


def _is_class_of(repository: Path | None, module: str, name: str) -> bool:
    """Is ``name`` a class this module defines? Constructing a value of the module under
    review reads it; it does not replace anything in it (a constructor with side effects
    is the stated limit)."""
    if repository is None:
        return False
    path = _module_file(repository, module)
    if path is None:
        return False
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError, RecursionError):
        return False
    return any(isinstance(n, ast.ClassDef) and n.name == name for n in tree.body)


def _bound_here(nodes: list[ast.AST]) -> set[str]:
    """Names this code binds itself: a loop target, an assignment, a `with` alias. A call
    on one of them is screened where the name is bound, not again at every use."""
    bound: set[str] = set()
    for parent in nodes:
        for node in ast.walk(parent):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            elif isinstance(
                node,
                ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef
                | ast.ExceptHandler | ast.MatchAs | ast.MatchStar,
            ) and node.name:
                bound.add(node.name)
            elif isinstance(node, ast.arg):
                bound.add(node.arg)
    return bound


_MAX_FOLLOW = 2


def _module_file(root: Path, module: str) -> Path | None:
    """The file of a module of this repository, or None when it is not one of ours."""
    relative = module.replace(".", "/")
    for candidate in (f"{relative}.py", f"src/{relative}.py", f"{relative}/__init__.py",
                      f"src/{relative}/__init__.py"):
        path = root / candidate
        try:
            if path.is_file() and not path.is_symlink() and path.stat().st_size <= 256_000:
                return path
        except OSError:
            return None
    return None


def _follow_refusal(
    root: Path, module: str, name: str, related: frozenset[str], depth: int, seen: set[str],
) -> tuple[int, str] | None:
    """What a function of this repository's own module reaches, read one level deeper.

    A call into a module the repository itself ships can install anything; a call into the
    standard library or a third-party package is the stated limit, not read."""
    key = f"{module}.{name}"
    if key in seen or depth > _MAX_FOLLOW:
        return 0, f"{key} is followed deeper than the rule reads"
    seen.add(key)
    path = _module_file(root, module)
    if path is None:
        return None  # not a module of this repository
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError, RecursionError):
        return 0, f"{key} cannot be read"
    target = next(
        (n for n in tree.body
         if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
         and n.name == name),
        None,
    )
    if target is None:
        return None  # a method or an attribute of an object: outside what this rule reads
    found = _reach_refusal(
        list(target.body), _imports(tree.body), related, frozenset(), root, depth + 1, seen,
    )
    if found is None:
        return None
    return found[0], f"{key} {found[1]}"


def _reach_refusal(
    nodes: list[ast.AST],
    imports: dict[str, str],
    related: frozenset[str],
    provided: frozenset[str] = frozenset(),
    repository: Path | None = None,
    depth: int = 0,
    seen: set[str] | None = None,
    here: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] | None = None,
) -> tuple[int, str] | None:
    """What this code, which runs before the assertion, may reach.

    A call or a store whose root name is imported reaches that module; one the rule
    cannot resolve -- a fixture argument, a name defined elsewhere in the file -- is
    refused, because what it reaches cannot be read."""
    provided = provided | _bound_here(nodes)
    seen = set() if seen is None else seen
    here = {} if here is None else here
    for parent in nodes:
        for node in ast.walk(parent):
            if isinstance(node, ast.Call):
                root, shown = _root(node.func), ast.unparse(node.func)
                if isinstance(node.func, ast.Attribute) and node.func.attr in _PATCH_METHODS:
                    return getattr(node, "lineno", 0), (
                        f"{shown} replaces a binding, whatever it is reached through"
                    )
                if root in here and depth <= _MAX_FOLLOW:
                    key = f"<this file>.{root}"
                    if key not in seen:
                        seen.add(key)
                        deeper = _reach_refusal(
                            list(here[root].body), imports, related, provided, repository,
                            depth + 1, seen, here,
                        )
                        if deeper is not None:
                            return getattr(node, "lineno", 0), f"{root} {deeper[1]}"
                # a name of the module under review handed to a call may be replaced in it
                for argument in (*node.args, *(k.value for k in node.keywords)):
                    handed = _root(argument)
                    if handed in imports and _reaches(imports[handed], related):
                        return getattr(node, "lineno", 0), (
                            f"{shown} is handed {ast.unparse(argument)}, which reaches "
                            f"{imports[handed]}, the module under review"
                        )
            elif isinstance(node, ast.Attribute | ast.Subscript) and isinstance(
                node.ctx, ast.Store | ast.Del
            ):
                root, shown = _root(node), ast.unparse(node)
            else:
                continue
            line = getattr(node, "lineno", getattr(parent, "lineno", 0))
            if not root:
                continue  # a call on a literal or on another call's result, screened itself
            if root in imports:
                target = imports[root]
                if _reaches(target, related):
                    if isinstance(node, ast.Call) and _is_class_of(
                        repository, target, shown.split(".")[-1],
                    ):
                        continue
                    return line, f"{shown} reaches {target}, the module under review"
                parts = shown.split(".")
                if isinstance(node, ast.Call) and repository is not None and len(parts) <= 2:
                    inner = _follow_refusal(
                        repository, target, parts[-1], related, depth, seen,
                    )
                    if inner is not None:
                        return line, inner[1]
                continue
            if root in _BUILTINS or root in provided:
                continue
            return line, f"the rule cannot tell what {shown} reaches"
    return None


def _fixture_decorators(statement: ast.stmt) -> tuple[bool, bool]:
    """(is a pytest fixture, is autouse)."""
    if not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
        return False, False
    for decorator in statement.decorator_list:
        call = decorator if isinstance(decorator, ast.Call) else None
        name = ast.unparse(call.func if call else decorator).rsplit(".", 1)[-1]
        if name != "fixture":
            continue
        autouse = any(
            k.arg == "autouse" and not (
                isinstance(k.value, ast.Constant) and k.value.value is False
            )
            for k in (call.keywords if call else ())
        )
        return True, autouse
    return False, False


def _setup_part(statement: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.AST]:
    """The statements that run before the test: everything up to the first `yield`."""
    setup: list[ast.AST] = []
    for inner in statement.body:
        if any(isinstance(n, ast.Yield | ast.YieldFrom) for n in ast.walk(inner)):
            break
        setup.append(inner)
    # the `pytest.fixture` marker itself is the declaration, not code the fixture runs
    setup.extend(
        d for d in statement.decorator_list
        if ast.unparse(d.func if isinstance(d, ast.Call) else d).rsplit(".", 1)[-1] != "fixture"
    )
    return setup


def _row_names(statement: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    names: set[str] = set()
    for decorator in statement.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if ast.unparse(decorator.func).rsplit(".", 1)[-1] != "parametrize" or not decorator.args:
            continue
        try:
            first = ast.literal_eval(decorator.args[0])
        except (ValueError, TypeError, SyntaxError, RecursionError):
            continue
        if isinstance(first, str):
            names.update(n.strip() for n in first.split(",") if n.strip())
        elif isinstance(first, list | tuple):
            names.update(str(n) for n in first)
    return names


@dataclass(frozen=True)
class TestContext:
    """What the rule read about one test file's implicit context."""

    reason: str  # "" when nothing that runs before every test of this file was refused
    fixtures: dict[str, str]  # fixture name -> "" when read, else why it is refused

    def function_refusal(self, statement: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
        """Why this test's own decorators and fixtures leave its assertions unbound."""
        for decorator in statement.decorator_list:
            call = decorator if isinstance(decorator, ast.Call) else None
            text = ast.unparse(call.func if call else decorator)
            name = text.rsplit(".", 1)[-1]
            if not (text.startswith("pytest.mark.") or text.startswith("mark.")):
                return (
                    f"test context: {statement.name} is decorated with {text}, which may "
                    "install an implicit fixture or wrapper"
                )
            if name == "usefixtures":
                return f"test context: {statement.name} uses fixtures it does not name"
            if name == "parametrize" and call is not None:
                # D-282: the rows themselves are read by the reach screen (a constructor of
                # the module under review builds a value; a callback could replace one);
                # what still has to be literal is how pytest is told to use them
                for keyword in call.keywords:
                    try:
                        value = ast.literal_eval(keyword.value)
                    except (ValueError, TypeError, SyntaxError, RecursionError):
                        return (
                            f"test context: {statement.name} parametrizes with "
                            f"{keyword.arg}= the rule cannot read"
                        )
                    if keyword.arg == "indirect" and value is not False:
                        return (
                            f"test context: {statement.name} parametrizes indirectly, "
                            "through fixtures"
                        )
        arguments = statement.args
        params = [a.arg for a in (
            *arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
        )]
        rows = _row_names(statement)
        for name in params:
            if name in rows or name in ("self", "cls"):
                continue
            known = self.fixtures.get(name)
            if known is None:
                return (
                    f"test context: {statement.name} asks for {name!r}, a fixture no conftest "
                    "on the path defines: what it does is not read"
                )
            if known:
                return f"test context: {statement.name} asks for {name!r}: {known}"
        return ""


def _screen_setup_file(
    body: list[ast.stmt],
    label: str,
    related: frozenset[str],
    repository: Path | None = None,
) -> tuple[str, dict[str, str]]:
    """Read one file that runs before the assertion: its module body, hooks and fixtures."""
    imports = _imports(body)
    known = frozenset(_bound_here(list(body)))
    here = {
        n.name: n for n in body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    fixtures: dict[str, str] = {}
    for statement in body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            bound = [(a.asname or a.name).split(".")[0] for a in statement.names]
            if "pytest" in bound and not (
                isinstance(statement, ast.Import)
                and any(a.name == "pytest" for a in statement.names
                        if (a.asname or a.name) == "pytest")
            ):
                return (
                    f"test context {label}:{statement.lineno}: the pytest decorator binding "
                    "is unexamined or rebound"
                ), fixtures
            if any(n in _HOOKS or n.startswith("pytest_") for n in bound):
                return (
                    f"test context {label}:{statement.lineno}: an import binds the setup hook "
                    f"{next(n for n in bound if n in _HOOKS or n.startswith('pytest_'))!r}"
                ), fixtures
            continue
        is_fixture, autouse = _fixture_decorators(statement)
        if is_fixture and isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            for name in (a.arg for a in statement.args.args):
                if name not in fixtures:
                    fixtures[name] = f"{label}: {statement.name} asks for {name!r} itself"
            found = _reach_refusal(
                _setup_part(statement), imports, related, known, repository, here=here,
            )
            reason = "" if found is None else f"{label}:{found[0]}: {found[1]}"
            fixtures[statement.name] = reason
            if autouse and reason:
                return (
                    f"test context {label}:{statement.lineno}: the autouse fixture "
                    f"{statement.name} runs before every test and {reason}"
                ), fixtures
            continue
        names: list[str] = []
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names = [statement.name]
        elif isinstance(statement, ast.Assign):
            names = [n.id for t in statement.targets for n in ast.walk(t)
                     if isinstance(n, ast.Name)]
        if "pytest" in names:
            return (
                f"test context {label}:{statement.lineno}: the pytest decorator binding "
                "is unexamined or rebound"
            ), fixtures
        if "pytest_plugins" in names:
            return f"test context {label}:{statement.lineno}: plugin declaration", fixtures
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef) and (
            statement.name.startswith("pytest_") or statement.name in _HOOKS
        ):
            if "teardown" in statement.name:
                continue  # runs after the assertion
            given = frozenset(a.arg for a in (
                *statement.args.posonlyargs, *statement.args.args, *statement.args.kwonlyargs,
            ))
            found = _reach_refusal(
                [*statement.body, *statement.decorator_list], imports, related,
                given | known, repository, here=here,
            )
            if found is not None:
                return (
                    f"test context {label}:{found[0]}: the hook {statement.name} runs before "
                    f"the test and {found[1]}"
                ), fixtures
            continue
        if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            evaluated: list[ast.AST] = [*statement.decorator_list]
            if isinstance(statement, ast.ClassDef):
                # a base or a metaclass runs code when the class is created
                for base in (*statement.bases, *(k.value for k in statement.keywords)):
                    root_name = _root(base)
                    if root_name and root_name not in imports and root_name not in _BUILTINS:
                        return (
                            f"test context {label}:{statement.lineno}: the rule cannot tell "
                            f"what the base {ast.unparse(base)} of {statement.name} runs"
                        ), fixtures
                evaluated.extend(statement.bases)
                evaluated.extend(k.value for k in statement.keywords)
                for inner in statement.body:
                    if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef) and (
                        inner.name in _HOOKS or inner.name.startswith("pytest_")
                    ):
                        if "teardown" in inner.name.lower():
                            continue
                        given = frozenset(a.arg for a in (
                            *inner.args.posonlyargs, *inner.args.args, *inner.args.kwonlyargs,
                        ))
                        deeper = _reach_refusal(
                            list(inner.body), imports, related, given | known, repository,
                            here=here,
                        )
                        return (
                            f"test context {label}:{inner.lineno}: the setup method "
                            f"{statement.name}.{inner.name} runs before the test"
                            + (f" and {deeper[1]}" if deeper is not None else "")
                        ), fixtures
            else:
                arguments = statement.args
                evaluated.extend(arguments.defaults)
                evaluated.extend(v for v in arguments.kw_defaults if v is not None)
                evaluated.extend(a.annotation for a in (
                    *arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs,
                    *(a for a in (arguments.vararg, arguments.kwarg) if a is not None),
                ) if a.annotation is not None)
                if statement.returns is not None:
                    evaluated.append(statement.returns)
            found = _reach_refusal(evaluated, imports, related, known, repository, here=here)
            if found is not None:
                return f"test context {label}:{found[0]}: {found[1]}", fixtures
            continue
        if isinstance(statement, ast.Pass) or (
            isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant)
        ):
            continue
        if isinstance(statement, ast.If | ast.Try | ast.With | ast.AsyncWith):
            # control flow at module level is where a suite puts its conditional imports;
            # every statement inside it is read by the same rules
            inside: list[ast.stmt] = []
            for field in ("body", "orelse", "finalbody", "handlers", "items"):
                for child in getattr(statement, field, []) or []:
                    if isinstance(child, ast.stmt):
                        inside.append(child)
                    elif isinstance(child, ast.ExceptHandler):
                        inside.extend(child.body)
            guard = _reach_refusal(
                [getattr(statement, "test", None) or ast.Pass()], imports, related, known,
                repository, here=here,
            )
            if guard is not None:
                return f"test context {label}:{guard[0]}: {guard[1]}", fixtures
            reason, found_inside = _screen_setup_file(inside, label, related, repository)
            fixtures.update(found_inside)
            if reason:
                return reason, fixtures
            continue
        found = _reach_refusal([statement], imports, related, known, repository, here=here)
        if found is not None:
            return f"test context {label}:{found[0]}: {found[1]}", fixtures
        if not (isinstance(statement, ast.Assign | ast.AnnAssign | ast.AugAssign)):
            return (
                f"test context {label}:{statement.lineno}: module body executes unexamined code"
            ), fixtures
    return "", fixtures


def _module_fixtures(
    module: ast.Module, label: str, related: frozenset[str],
) -> tuple[str, dict[str, str]]:
    """The test module's own fixtures, read like a conftest's."""
    imports = _imports(module.body)
    fixtures: dict[str, str] = {}
    for statement in module.body:
        is_fixture, autouse = _fixture_decorators(statement)
        if not is_fixture or not isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for name in (a.arg for a in statement.args.args):
            if name not in fixtures:
                fixtures[name] = f"{label}: {statement.name} asks for {name!r} itself"
        found = _reach_refusal(_setup_part(statement), imports, related)
        reason = "" if found is None else f"{label}:{found[0]}: {found[1]}"
        fixtures[statement.name] = reason
        if autouse and reason:
            return (
                f"test context {label}:{statement.lineno}: the autouse fixture "
                f"{statement.name} runs before every test and {reason}"
            ), fixtures
    return "", fixtures


def read_context(
    root: Path,
    relative: Path,
    module: ast.Module,
    *,
    anchored_module: str = "",
    related: frozenset[str] = frozenset(),
) -> TestContext:
    """Read the conftest chain and this file's own fixtures (D-282).

    ``related`` is the module under review and the modules it imports: code that runs
    before the assertion may not reach them. The module body screen of D-257 is kept as
    it was; only the conftest chain and fixture definitions are read rather than refused.
    """
    related = related | ({anchored_module} if anchored_module else frozenset())
    fixtures: dict[str, str] = {}
    label = relative.as_posix()
    for parent in reversed([relative.parent, *relative.parent.parents]):
        conftest = root / parent / "conftest.py"
        shown = (parent / "conftest.py").as_posix()
        try:
            if conftest.is_symlink():
                return TestContext(f"test context {shown}: symlinked setup is unexamined", {})
            if not conftest.exists():
                continue
            if conftest.stat().st_size > 64_000:
                return TestContext(f"test context {shown}: setup exceeds the reading limit", {})
            tree = ast.parse(conftest.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, SyntaxError, ValueError, RecursionError):
            return TestContext(f"test context {shown}: setup cannot be read", {})
        reason, found = _screen_setup_file(tree.body, shown, related, root)
        fixtures.update(found)
        if reason:
            return TestContext(reason, fixtures)
    reason, found = _screen_setup_file(module.body, label, related, root)
    fixtures.update(found)
    return TestContext(reason, fixtures)


def context_refusal(root: Path, relative: Path, module: ast.Module) -> str:
    """The file-level refusal of `read_context`, for callers that read no contract."""
    return read_context(root, relative, module).reason
