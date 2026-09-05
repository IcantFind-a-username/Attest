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

It speaks only when there is something an author can act on, and since D-145
that is a **conjunction**: the signature or return annotation moved **and** some
call site is named by no test. Either half on its own is refused — an interface
change whose callers are all named by tests will be reported by those tests, and
an untested caller under an unchanged interface is a coverage remark this level
has no standing to make. A change to a function body is silent whatever its
callers look like.

The cost of that rule is measured and stated rather than hidden: on the 79 units
of the 2026-09-06 scan the conjunction fires on **none of them**, so this level
is author-visible and expected to be silent on ordinary traffic.
"""

from __future__ import annotations

import ast
from collections import defaultdict, deque
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

IMPACT_POLICY_VERSION = "attest.impact.caller-scope.v1"
CATEGORY = "impact"

MAX_FILES = 5_000
MAX_FILE_BYTES = 1_000_000
MAX_DEPTH = 4  # hops from a caller back to a test before "no test names it"
# and this bound produces speech rather than silence: a test five calls away
# leaves the caller reported as unnamed. Raising it can only quieten the level.
MAX_NOTES = 2  # author-visible notes per pull request (the same cap green has)

# D-150: the three conditions, measured and switched on one at a time. Every one
# of them is a conjunction whose second half is a *checkable consequence*, never
# a bare interface fact -- D-145 established that an interface change on its own
# says nothing an author can act on, and the 2026-09-06 scan's six disjunctive
# notes are why (all six named functions whose every caller a test already
# names).
CONDITION_SIGNATURE = "a1_signature_untested_caller"
CONDITION_RAISE_OR_RETURNS = "a2_raise_or_returns_untested_caller"
CONDITION_ARITY = "a3_added_parameter_arity_break"
CONDITIONS = (CONDITION_SIGNATURE, CONDITION_RAISE_OR_RETURNS, CONDITION_ARITY)
# The conditions this level is allowed to publish. A condition whose measured
# trigger rate on the null controls exceeds the owner's 3% ceiling stays out of
# this tuple and is measured without ever being author-visible.
ENABLED_CONDITIONS: tuple[str, ...] = CONDITIONS

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
    # the exception type names this function raises directly, as written. A
    # bare `raise` re-raises and names nothing, so it is recorded as `""`.
    raises: frozenset[str] = frozenset()

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
    # What the call passes, for the one question a static arity check may ask.
    # `unknown_arity` is set by `*args`, `**kwargs` or any keyword argument:
    # each of them can supply a parameter this level cannot see, so the check
    # abstains rather than guessing.
    positional: int = 0
    unknown_arity: bool = True
    attribute_call: bool = False  # written as `x.f(...)`, so `self` is implicit

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
    # D-150 condition (a2): the head function raises an exception type the base
    # function did not. A caller that never had to handle it now does.
    added_raise: bool = False
    # the first line *inside* this function that the diff actually changed. The
    # `def` line is the function's identity and is what the published sentence
    # names; this is where an inline comment may be placed, because GitHub
    # refuses a review comment on a line the diff does not carry (D-147).
    anchor_line: int = 0

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
    # D-150: which of the three conditions fired. The line an author reads is
    # built from this, and the ledger records it, so a level whose conditions
    # are measured separately can be switched off separately.
    condition: str = CONDITION_SIGNATURE
    # a3 only: the call sites that pass fewer positional arguments than the
    # function now requires. Empty for every other condition.
    arity_breaks: tuple[CallSite, ...] = ()


@dataclass
class CallGraph:
    """Definitions and call sites of one tree, indexed by bare name."""

    definitions: dict[str, list[FunctionDef]] = field(default_factory=dict)
    sites: dict[str, list[CallSite]] = field(default_factory=dict)
    # every mention of a name -- calls, attribute reads, bare references. Used
    # only to answer "does a test name this?", never to claim a call.
    mentions: dict[str, list[CallSite]] = field(default_factory=dict)

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


def _raised_types(node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    """The exception type names this function raises **in its own body**.

    A nested `def` is its own function and its raises belong to it, so the walk
    stops at one. A bare `raise` re-raises whatever is being handled and names
    no new type, so it contributes `""` -- which compares equal across
    revisions and therefore never counts as a raise the base did not have."""
    found: set[str] = set()
    stack: list[ast.AST] = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if isinstance(current, ast.Raise):
            found.add(_raised_name(current))
        stack.extend(ast.iter_child_nodes(current))
    return frozenset(found)


def _raised_name(node: ast.Raise) -> str:
    exception = node.exc
    if exception is None:
        return ""
    if isinstance(exception, ast.Call):
        exception = exception.func
    name = _callee_name(exception) if isinstance(exception, ast.Attribute | ast.Name) else None
    return name or ""


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
        raises = _raised_types(node)
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
                raises=raises,
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
            site = self._here(node.lineno, callee)
            positional = sum(1 for a in node.args if not isinstance(a, ast.Starred))
            unknown = any(isinstance(a, ast.Starred) for a in node.args) or bool(node.keywords)
            self.sites.append(
                CallSite(
                    path=site.path,
                    line=site.line,
                    callee=site.callee,
                    inside=site.inside,
                    positional=positional,
                    unknown_arity=unknown,
                    attribute_call=isinstance(node.func, ast.Attribute),
                )
            )
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
        for site in visitor.sites:
            sites[site.callee].append(site)
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
        inside = touched.intersection(span)
        if not inside:
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
                added_raise=bool(definition.raises - before.raises),
                anchor_line=min(inside),
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
        bare = _addressable_name(qualname)
        for caller in graph.mentions.get(bare, ()):
            if caller.is_test:
                return True, depth + 1
            if caller.inside is not None and caller.inside not in seen:
                seen.add(caller.inside)
                frontier.append((caller.inside, depth + 1))
    return False, None


def _addressable_name(qualname: str) -> str:
    """The name a test would have to write to reach this function.

    A constructor is the case that matters: nothing outside the class writes
    `__init__`, so asking whether a test names `__init__` answers "no" for every
    constructor in every repository, and the published sentence would call a
    class that ten tests instantiate "named by no test". For a dunder the
    addressable name is the **class**; for everything else it is the function's
    own name."""
    parts = qualname.split(".")
    if parts[-1].startswith("__") and parts[-1].endswith("__") and len(parts) > 1:
        return parts[-2]
    return parts[-1]


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


def arity_breaks_of(changed: ChangedFunction, callers: Sequence[Caller]) -> tuple[CallSite, ...]:
    """Call sites that now pass fewer positional arguments than the function takes.

    This is the only claim yellow makes that does **not** rest on a coverage
    proxy, because it is decidable from the two trees: the head definition says
    how many positional parameters have no default, and the call site says how
    many it writes. Every uncertainty abstains --

    - a call with `*args`, `**kwargs` or any keyword argument may supply the
      missing parameter, so `unknown_arity` sites are dropped;
    - a method reached as `x.f(...)` binds `self` implicitly, so one parameter
      is discounted for an attribute call on a nested qualname;
    - a call inside a test is still a break, and is still reported: an arity
      mismatch is not a coverage remark.
    """
    definition = changed.definition
    is_method = "." in definition.qualname
    out: list[CallSite] = []
    for caller in callers:
        site = caller.site
        if site.unknown_arity:
            continue
        implicit = 1 if (is_method and site.attribute_call) else 0
        if site.positional + implicit < definition.required:
            out.append(site)
    return tuple(out)


def note_for(
    graph: CallGraph,
    changed: ChangedFunction,
    *,
    conditions: Sequence[str] = ENABLED_CONDITIONS,
) -> ImpactNote | None:
    """One note, or None when this level has nothing an author can act on.

    Three conditions, each measured on its own before it was allowed to speak
    (D-150), and each of them a conjunction:

    - **a1** the *signature* moved **and** some caller is named by no test.
      D-145's rule, retained unchanged.
    - **a2** the function *raises a type the base did not*, or its *return
      annotation* moved, **and** some caller is named by no test. A caller that
      never had to handle `KeyError` now does, and no test names it.
    - **a3** the function *gained a required parameter* **and** some call site
      statically passes fewer positional arguments than it now takes. This one
      carries no coverage half, because arity is decidable: the call is wrong
      whether or not a test names it.

    Four abstentions survive from D-145, each of them deliberate: an ambiguous
    name, no caller at all, an interface change every test names, and an
    untested caller under an unchanged interface.
    """
    definition = changed.definition
    if graph.unique(definition.name) is None:
        return None  # the name is defined more than once: no claim is possible
    callers = callers_of(graph, changed)
    if not callers:
        return None
    untested = tuple(c for c in callers if not c.named_by_test)

    if CONDITION_ARITY in conditions and changed.added_required_parameter:
        breaks = arity_breaks_of(changed, callers)
        if breaks:
            return ImpactNote(
                changed=changed,
                callers=callers,
                untested=untested,
                reason="a required parameter was added and a call site passes too few",
                condition=CONDITION_ARITY,
                arity_breaks=breaks,
            )
    if not untested:
        return None
    if CONDITION_SIGNATURE in conditions and changed.signature_changed:
        return ImpactNote(
            changed=changed,
            callers=callers,
            untested=untested,
            reason="the signature changed and a caller is named by no test",
            condition=CONDITION_SIGNATURE,
        )
    if CONDITION_RAISE_OR_RETURNS in conditions and (
        changed.added_raise or changed.returns_changed
    ):
        what = (
            "a new exception type is raised"
            if changed.added_raise
            else "the return annotation changed"
        )
        return ImpactNote(
            changed=changed,
            callers=callers,
            untested=untested,
            reason=f"{what} and a caller is named by no test",
            condition=CONDITION_RAISE_OR_RETURNS,
        )
    return None


def notes_for_change(
    graph: CallGraph,
    changed: Sequence[ChangedFunction],
    *,
    limit: int = MAX_NOTES,
    conditions: Sequence[str] = ENABLED_CONDITIONS,
) -> tuple[ImpactNote, ...]:
    """The notes one pull request may show, most consequential first.

    Every note that reaches here already carries both halves of its condition's
    conjunction, so the order is by condition -- a decidable arity break before
    a coverage-proxy claim, a changed signature before a raise or a return
    annotation -- then by how many callers are untested, then by coordinate, so
    the order is total and does not depend on file order."""
    produced = [
        note
        for definition in changed
        if (note := note_for(graph, definition, conditions=conditions))
    ]
    # A decidable break outranks a coverage-proxy claim, and a moved signature
    # outranks a moved raise or return annotation.
    rank = {CONDITION_ARITY: 0, CONDITION_SIGNATURE: 1, CONDITION_RAISE_OR_RETURNS: 2}
    produced.sort(
        key=lambda n: (
            rank.get(n.condition, 3),
            -len(n.untested),
            n.changed.definition.path,
            n.changed.definition.line,
        )
    )
    return tuple(produced[:limit])
