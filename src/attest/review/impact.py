"""Yellow (a): the impact scope of a change, computed and not guessed (D-143).

Mainline §1.1 gives yellow one job: *state a hypothesis as premises, verify each
premise with a deterministic checker, and say only the premises that were
verified*. This module is the first yellow level and it is the smallest possible
one — every premise it states is a count over an abstract syntax tree:

    for each function or method the diff changed
      -> its call sites, walked up the reverse call graph to an entry point or a test
      -> for each caller: is it reached by any test in this repository?
      -> did the changed function's signature or return annotation change?

**No model, no execution, no network, no cost.** Reading files and `ast` is the
whole of it, which is why this level can run on every pull request.

What it refuses to say is as important as what it says. A call graph built from
names alone is an over-approximation, so this module **abstains on every
ambiguity** rather than narrowing a claim it cannot support:

- a changed function whose name is defined more than once in the repository is
  dropped: `save` in two classes is two functions and a name cannot tell them
  apart;
- a call site reached through a registry, a dispatch table, `getattr`, or any
  dynamic form is invisible here, so "no test reaches it" is stated as **no
  test *names* it**, which is what was actually measured;
- a repository that exceeds the file, byte or node caps yields nothing at all.

It speaks only when there is something an author can act on: a changed
signature, or a caller no test names. A change to a function body whose every
caller is under test is exactly the case where this level stays quiet.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

IMPACT_POLICY_VERSION = "attest.impact.caller-scope.v0"
CATEGORY = "impact"

MAX_FILES = 5_000
MAX_FILE_BYTES = 1_000_000
MAX_CALLERS_REPORTED = 8  # per changed function, in the evidence; the line names one
MAX_DEPTH = 4  # hops from a caller back to a test before "no test names it"
MAX_NOTES = 2  # author-visible notes per pull request (the same cap green has)

SKIPPED_DIRS = frozenset(
    {
        ".git",
        ".attest",
        ".attest-repro",
        ".claude",
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
        "site-packages",
    }
)


@dataclass(frozen=True)
class FunctionDef:
    """One `def` of one file, reduced to what impact analysis compares."""

    path: str
    name: str
    qualname: str
    line: int
    end_line: int
    parameters: tuple[str, ...]
    required: int  # positional-or-keyword parameters with no default
    returns: str | None  # the return annotation, unparsed to text

    @property
    def is_test(self) -> bool:
        return is_test_path(self.path) or self.name.startswith("test_")


@dataclass(frozen=True)
class CallSite:
    """One call, by the name it was written with, and where it was written."""

    path: str
    line: int
    callee: str
    inside: str | None  # qualname of the enclosing function, None at module level

    @property
    def is_test(self) -> bool:
        return is_test_path(self.path)


@dataclass(frozen=True)
class ChangedFunction:
    """A function the diff touched, and how its interface moved."""

    definition: FunctionDef
    signature_changed: bool
    returns_changed: bool
    added_required_parameter: bool

    @property
    def interface_changed(self) -> bool:
        return self.signature_changed or self.returns_changed


@dataclass(frozen=True)
class Caller:
    """One call site of a changed function, with the one fact yellow checks."""

    site: CallSite
    named_by_test: bool
    hops_to_test: int | None  # None when no test reaches it within MAX_DEPTH


@dataclass(frozen=True)
class ImpactNote:
    """One yellow (a) finding: what changed, who calls it, who is untested."""

    changed: ChangedFunction
    callers: tuple[Caller, ...]
    untested: tuple[Caller, ...]
    reason: str  # why this note speaks; "" when it does not


@dataclass
class CallGraph:
    """Definitions and call sites of one tree, indexed by bare name."""

    definitions: dict[str, list[FunctionDef]] = field(default_factory=dict)
    sites: dict[str, list[CallSite]] = field(default_factory=dict)
    # every mention of a name -- calls, attribute reads, bare references. Used
    # only to answer "does a test name this?", never to claim a call.
    mentions: dict[str, list[CallSite]] = field(default_factory=dict)
    by_qualname: dict[str, FunctionDef] = field(default_factory=dict)
    # qualname -> the bare names it calls
    calls_from: dict[str, set[str]] = field(default_factory=dict)

    def unique(self, name: str) -> FunctionDef | None:
        """The one definition of this name, or None when the name is ambiguous.

        Ambiguity is an abstention, not a guess: two `save` methods in two
        classes are two functions and this level cannot tell a caller of one
        from a caller of the other."""
        found = self.definitions.get(name, ())
        return found[0] if len(found) == 1 else None


def is_test_path(relative: str) -> bool:
    name = PurePosixPath(relative).name
    parts = PurePosixPath(relative).parts
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or name == "conftest.py"
        or any(part in {"tests", "test", "testing"} for part in parts)
    )


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[tuple[str, ...], int]:
    args = node.args
    positional = [*args.posonlyargs, *args.args]
    names = [a.arg for a in positional]
    names.extend(a.arg for a in ([args.vararg] if args.vararg else []))
    names.extend(a.arg for a in args.kwonlyargs)
    names.extend(a.arg for a in ([args.kwarg] if args.kwarg else []))
    required = len(positional) - len(args.defaults)
    required += sum(1 for default in args.kw_defaults if default is None)
    return tuple(names), required


class _Visitor(ast.NodeVisitor):
    """One pass per file: definitions with their signatures, and call sites with
    the enclosing function they were written in."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.stack: list[str] = []
        self.definitions: list[FunctionDef] = []
        self.sites: list[CallSite] = []
        # every *mention* of a name, call or not. A property a test reads as an
        # attribute (`timeout.read_timeout`) is named by that test and is not a
        # call; the question "does a test name this?" must see it, or the level
        # says "named by no test" about something a test plainly names.
        self.mentions: list[CallSite] = []

    # -- definitions
    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self.stack.append(node.name)
        qualname = ".".join(self.stack)
        names, required = _signature(node)
        self.definitions.append(
            FunctionDef(
                path=self.path,
                name=node.name,
                qualname=qualname,
                line=node.lineno,
                end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
                parameters=names,
                required=required,
                returns=ast.unparse(node.returns) if node.returns is not None else None,
            )
        )
        self.generic_visit(node)
        self.stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802 - ast API
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self._function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:  # noqa: N802 - ast API
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    # -- call sites
    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802 - ast API
        callee = _callee_name(node.func)
        if callee is not None:
            self.sites.append(self._here(node.lineno, callee))
        self.generic_visit(node)

    # -- mentions
    def visit_Name(self, node: ast.Name) -> None:  # noqa: N802 - ast API
        self.mentions.append(self._here(node.lineno, node.id))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802 - ast API
        self.mentions.append(self._here(node.lineno, node.attr))
        self.generic_visit(node)

    def _here(self, line: int, name: str) -> CallSite:
        return CallSite(
            path=self.path,
            line=line,
            callee=name,
            inside=".".join(self.stack) if self.stack else None,
        )


def _callee_name(func: ast.expr) -> str | None:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def build_call_graph(sources: Mapping[str, str]) -> CallGraph:
    """Index a whole tree. Unparsable files are skipped, never guessed at."""
    graph = CallGraph()
    definitions: dict[str, list[FunctionDef]] = defaultdict(list)
    sites: dict[str, list[CallSite]] = defaultdict(list)
    mentions: dict[str, list[CallSite]] = defaultdict(list)
    for path in sorted(sources):
        source = sources[path]
        if len(source.encode("utf-8", "ignore")) > MAX_FILE_BYTES:
            continue
        try:
            tree = ast.parse(source)
        except (SyntaxError, ValueError, RecursionError):
            continue
        visitor = _Visitor(path)
        visitor.visit(tree)
        for definition in visitor.definitions:
            definitions[definition.name].append(definition)
            graph.by_qualname[f"{definition.path}::{definition.qualname}"] = definition
        for site in visitor.sites:
            sites[site.callee].append(site)
            if site.inside is not None:
                key = f"{site.path}::{site.inside}"
                graph.calls_from.setdefault(key, set()).add(site.callee)
        for mention in visitor.mentions:
            mentions[mention.callee].append(mention)
    graph.definitions = dict(definitions)
    graph.sites = dict(sites)
    graph.mentions = dict(mentions)
    return graph


def read_tree(root: Path) -> dict[str, str]:
    """Every Python file of a tree, by repository-relative POSIX path."""
    sources: dict[str, str] = {}
    for path in sorted(root.rglob("*.py")):
        if len(sources) >= MAX_FILES:
            break
        relative = path.relative_to(root)
        if any(part in SKIPPED_DIRS for part in relative.parts):
            continue
        try:
            sources[relative.as_posix()] = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return sources


def changed_functions(
    *,
    path: str,
    head_source: str,
    base_source: str | None,
    changed_lines: Iterable[int],
) -> tuple[ChangedFunction, ...]:
    """The functions of one file the diff touched, and how their interface moved.

    A function is changed when a changed line falls inside it. Its interface is
    compared against the same qualname in the base revision; a function with no
    base counterpart is **new code**, which is the gate level's business and not
    this one's, so it is dropped here."""
    touched = set(changed_lines)
    try:
        head_tree = ast.parse(head_source)
    except (SyntaxError, ValueError, RecursionError):
        return ()
    head_visitor = _Visitor(path)
    head_visitor.visit(head_tree)
    base_by_qualname: dict[str, FunctionDef] = {}
    if base_source is not None:
        try:
            base_tree = ast.parse(base_source)
        except (SyntaxError, ValueError, RecursionError):
            base_source = None
        else:
            base_visitor = _Visitor(path)
            base_visitor.visit(base_tree)
            base_by_qualname = {d.qualname: d for d in base_visitor.definitions}

    out: list[ChangedFunction] = []
    for definition in head_visitor.definitions:
        span = range(definition.line, definition.end_line + 1)
        if not touched.intersection(span):
            continue
        before = base_by_qualname.get(definition.qualname)
        if before is None:
            continue  # new code: not this level's claim
        signature_changed = before.parameters != definition.parameters
        returns_changed = before.returns != definition.returns
        out.append(
            ChangedFunction(
                definition=definition,
                signature_changed=signature_changed,
                returns_changed=returns_changed,
                added_required_parameter=definition.required > before.required,
            )
        )
    # a nested function and its parent both match the touched lines; the
    # innermost is the one the diff is about, so deeper qualnames come first
    out.sort(key=lambda c: (-c.definition.qualname.count("."), c.definition.line))
    return tuple(out)


def _named_by_test(graph: CallGraph, site: CallSite) -> tuple[bool, int | None]:
    """Does any test in this repository name this call site's enclosing function,
    directly or within `MAX_DEPTH` hops? Returns `(named, hops)`.

    This is reverse reachability over names, and the docstring's honesty matters
    more than the number: a caller reached only through a registry looks
    untested here, and the published sentence says *named by no test*, never
    *not covered*."""
    if site.is_test:
        return True, 0
    if site.inside is None:
        return False, None
    seen = {site.inside}
    frontier: deque[tuple[str, int]] = deque([(site.inside, 0)])
    while frontier:
        qualname, depth = frontier.popleft()
        if depth >= MAX_DEPTH:
            continue
        bare = qualname.rsplit(".", 1)[-1]
        for caller in graph.mentions.get(bare, ()):
            if caller.is_test:
                return True, depth + 1
            if caller.inside is not None and caller.inside not in seen:
                seen.add(caller.inside)
                frontier.append((caller.inside, depth + 1))
    return False, None


def callers_of(graph: CallGraph, changed: ChangedFunction) -> tuple[Caller, ...]:
    """Every call site that names this function, outside its own definition."""
    definition = changed.definition
    out: list[Caller] = []
    for site in graph.sites.get(definition.name, ()):
        if site.path == definition.path and definition.line <= site.line <= definition.end_line:
            continue  # recursion, or a call inside the function itself
        named, hops = _named_by_test(graph, site)
        out.append(Caller(site=site, named_by_test=named, hops_to_test=hops))
    out.sort(key=lambda c: (c.named_by_test, c.site.path, c.site.line))
    return tuple(out)


def note_for(graph: CallGraph, changed: ChangedFunction) -> ImpactNote | None:
    """One note, or None when this level has nothing an author can act on.

    Three abstentions, each of them deliberate: an ambiguous name, no caller at
    all, and a body change whose every caller is named by a test."""
    definition = changed.definition
    if graph.unique(definition.name) is None:
        return None  # the name is defined more than once: no claim is possible
    callers = callers_of(graph, changed)
    if not callers:
        return None
    untested = tuple(c for c in callers if not c.named_by_test)
    if changed.interface_changed:
        what = "signature" if changed.signature_changed else "return annotation"
        reason = f"the {what} changed"
    elif untested:
        reason = "a caller is named by no test"
    else:
        return None
    return ImpactNote(changed=changed, callers=callers, untested=untested, reason=reason)


def notes_for_change(
    graph: CallGraph,
    changed: Sequence[ChangedFunction],
    *,
    limit: int = MAX_NOTES,
) -> tuple[ImpactNote, ...]:
    """The notes one pull request may show, most consequential first.

    Order: a changed signature with untested callers, then a changed signature,
    then untested callers; ties by how many callers are untested, then by
    coordinate, so the order is total and does not depend on file order."""
    produced = [note for definition in changed if (note := note_for(graph, definition))]
    produced.sort(
        key=lambda n: (
            not (n.changed.interface_changed and n.untested),
            not n.changed.interface_changed,
            -len(n.untested),
            n.changed.definition.path,
            n.changed.definition.line,
        )
    )
    return tuple(produced[:limit])
