"""Yellow (b), second class: an exception that now reaches a caller that never
handled it (D-164).

The first yellow (b) class asks about `None`. It measured **0 of 79** because
the corpus it read carries no type annotations at all, and no prompt change
addresses that. This class asks a question the same code *can* answer, because
it reads statements rather than declarations:

    the changed function now calls something that raises, and on the way out to
    a caller nobody catches it.

Three premises, each decidable from the two trees, and **all three or nothing**:

  (i)   the changed function calls a callee at head that the **base** version of
        the same function did not call -- a call the change introduced;
  (ii)  that callee raises an exception type: `raise X` in its own body, or a
        docstring that declares `Raises: X` / `:raises X:`. A bare `raise`
        names nothing and does not count;
  (iii) from the changed function out to some **non-test** caller, nothing
        catches it: not a `try` around the new call, not the changed function
        itself, not the caller's call to it.

Every direction of doubt voids the hypothesis and none of them costs precision:
a callee whose written name does not resolve to one definition voids (v2 --
`attest.review.binding`, which is stricter than the old "defined twice
anywhere" rule in one direction and far weaker in the other); a bare `except:`
or an `except Exception` catches everything and voids; a handler whose relation
to the raised type Python cannot decide voids; a caller this level cannot
resolve voids; a file that does not parse voids.

The whole check is `ast` and `git`. A model is called **once, after the three
premises already hold**, to write the sentence a person reads -- and if it
fails, hedges, or names no coordinate, the deterministic sentence is published
instead. Nothing the model writes decides anything.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from attest.review.binding import Reference, dotted_name
from attest.review.impact import (
    CATCH_ALL,
    MAX_DEPTH,
    CallGraph,
    ChangedFunction,
    FunctionDef,
    exception_caught,
    handler_names,
    is_test_path,
)

# v2 (2026-09-08): two changes, both of them about *which* facts the three
# premises are read from. Premise (i)'s callee and premise (iii)'s callers are
# now resolved by `attest.review.binding` rather than matched by the name they
# were written with -- so a second definition of one name in an unrelated file
# is no longer ambiguity, and a `math.sqrt` is no longer a call of this
# repository's `sqrt`. And a `raise` the same function's own `try` catches no
# longer counts as raised: `exception_caught` reads the built-in hierarchy, so
# `except LookupError` covers a `KeyError` and two names Python does not know
# abstain rather than assert.
PROPAGATION_POLICY_VERSION = "attest.propagation.unhandled-exception.v2"

# Owner decision 2 of 2026-09-07: this class stays, and stays a **shadow**.
#
# It is the better of yellow (b)'s two negatives -- *rare*, not *unverifiable*:
# on the 79 units of the 2026-09-06 scan it fired on 0 forward pairs and 0
# controls, with 0% control noise against the owner's 3% ceiling, and of 198
# changed functions 135 added no call at all while 43 called a name defined more
# than once. Those refusals are informative, and it costs $0.00 to keep taking
# them. (That 43 was measured under v1, when a second definition *anywhere in
# the tree* was ambiguity; under v2 most of those are resolvable and the scan
# has not been re-run.) What it has not earned is an author's attention: a level that has never
# said anything is not yet a level a reader should be asked to read.
#
# So it runs on every review, writes `propagation_note` rows to the ledger, and
# reaches no author-visible surface -- no inline comment, no line in the summary
# body. This is the arrangement D-137 gave the gate level. Publishing it is this
# one flag.
PROPAGATION_SHADOW = True
# yellow's cap is shared between (a) and (b) (D-151); this is the bound on how
# many this class may contribute before that cap is applied.
MAX_NOTES = 2

# what a docstring says it raises. Both the Google/NumPy `Raises:` section and
# Sphinx's `:raises X:` field, because a project uses one or the other and
# reading only one would make the level depend on documentation fashion.
_SPHINX_RAISES = re.compile(r"^\s*:raises?\s+([A-Za-z_][\w.]*)\s*:", re.M)
_SECTION_RAISES = re.compile(r"^[ \t]*Raises:?\s*$", re.M)
_SECTION_ENTRY = re.compile(r"^[ \t]+([A-Za-z_][\w.]*)\s*(?:\(.*?\))?\s*:", re.M)

# The wording prompt. Deliberately silent about the contract's rules: the
# adjudicator's job is to hold against a model that was not told, and a prompt
# that begs the answer measures nothing (D-133).
WORDING_SYSTEM = (
    "You are reviewing a colleague's pull request. A static analysis has already "
    "established that a newly added call can raise an exception which no caller "
    "handles. State that for the author in one plain sentence."
)
WORDING_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {"sentence": {"type": "string"}},
    "required": ["sentence"],
    "additionalProperties": False,
}
WORDING_MAX_TOKENS = 200


@dataclass(frozen=True)
class PropagationNote:
    """One yellow (b) exception-propagation finding, with all three premises."""

    policy_version: str
    path: str  # where the new call is
    line: int
    changed_qualname: str
    callee: str
    exception: str
    evidence: str  # "raise" | "docstring"
    caller_path: str
    caller_line: int
    caller_qualname: str

    @property
    def note_id(self) -> str:
        """The delivery journal identifies every author-visible comment, and
        this one carries no receipt, so it is identified by the coordinate of
        the call it is about and the type it names."""
        return f"{self.path}:{self.line}:{self.exception}"

    @property
    def sentence(self) -> str:
        """The deterministic sentence, which is what is published when the
        model's is refused -- and is never worse than a hedge."""
        source = (
            f"`{self.callee}` raises `{self.exception}`"
            if self.evidence == "raise"
            else f"`{self.callee}` documents that it raises `{self.exception}`"
        )
        return (
            f"the call to `{self.callee}` added here can raise `{self.exception}` "
            f"({source}), and `{self.caller_qualname}` does not handle it"
        )


def _docstring_raises(node: ast.FunctionDef | ast.AsyncFunctionDef) -> frozenset[str]:
    """The exception types a function's own docstring says it raises."""
    text = ast.get_docstring(node) or ""
    if not text:
        return frozenset()
    found = set(_SPHINX_RAISES.findall(text))
    section = _SECTION_RAISES.search(text)
    if section:
        tail = text[section.end() :]
        # the section ends at the next unindented line
        for line in tail.splitlines():
            if line.strip() and not line[:1].isspace():
                break
            entry = _SECTION_ENTRY.match(line)
            if entry:
                found.add(entry.group(1))
    return frozenset(name for name in found if name)


def _function_nodes(source: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function of one file by qualname, so a caller can be re-read."""
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return {}
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def walk(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                qualname = f"{prefix}.{child.name}" if prefix else child.name
                found[qualname] = child
                walk(child, qualname)
            elif isinstance(child, ast.ClassDef):
                walk(child, f"{prefix}.{child.name}" if prefix else child.name)

    walk(tree, "")
    return found


def _handled_types(node: ast.AST) -> frozenset[str]:
    """Every exception name caught by a `try` anywhere inside ``node``.

    Deliberately coarse in the safe direction: a handler *anywhere* inside the
    function is read as covering the whole function, so a note is voided by a
    `try` it might not actually be under. Missing a real propagation is a lost
    note; claiming one that is caught is a wrong sentence.
    """
    caught: set[str] = set()
    stack: list[ast.AST] = [node]
    while stack:
        current = stack.pop()
        if isinstance(current, ast.ExceptHandler):
            caught.update(handler_names(current))
        stack.extend(ast.iter_child_nodes(current))
    return frozenset(caught)


def _called_names(node: ast.AST) -> set[str]:
    """Every call expression written inside ``node``, nested defs excluded.

    The expression **as written** -- `read`, `self.read`, `mod.read` -- because
    that is what the binding layer resolves. Premise (i) compares two revisions
    of the same function, so both sides are read the same way and a call that
    only changed its spelling is still a call the change introduced."""
    names: set[str] = set()
    stack: list[ast.AST] = list(ast.iter_child_nodes(node))
    while stack:
        current = stack.pop()
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if isinstance(current, ast.Call):
            written = dotted_name(current.func)
            if written is not None:
                names.add(written)
        stack.extend(ast.iter_child_nodes(current))
    return names


def _raises_of(definition: FunctionDef, node: ast.FunctionDef | ast.AsyncFunctionDef | None) -> (
    tuple[str, str] | None
):
    """(exception type, how it was learned) for one callee, or None.

    A named `raise` in the body is preferred over a docstring, because the body
    is the code and the docstring is a claim about it. A bare `raise` names
    nothing and is not a hypothesis.
    """
    body_raises = sorted(name for name in definition.raises if name)
    if body_raises:
        return body_raises[0], "raise"
    if node is not None:
        documented = sorted(_docstring_raises(node))
        if documented:
            return documented[0], "docstring"
    return None


# Why a hypothesis did not survive. Recorded rather than discarded: a level
# that never speaks is only interpretable if its refusals are counted, and
# "0 of 79" means nothing until you know which premise did the work.
VOID_NO_BASE = "no base revision of this function"
VOID_NO_ADDED_CALL = "the change added no call"
VOID_HANDLED_HERE = "the changed function catches everything"
VOID_UNBOUND_CALLEE = "the callee does not resolve to one definition"
VOID_CALLEE_RAISES_NOTHING = "the callee names no exception"
VOID_HANDLED_BY_CALLEE_TYPE = "the changed function catches this type"
VOID_NO_UNGUARDED_CALLER = "no non-test caller is unguarded"


def notes_for_change(
    graph: CallGraph,
    changed: Sequence[ChangedFunction],
    *,
    head_sources: Mapping[str, str],
    base_sources: Mapping[str, str],
    limit: int = MAX_NOTES,
    trace: list[str] | None = None,
) -> tuple[PropagationNote, ...]:
    """Every note whose three premises hold, most consequential first.

    ``trace`` collects one string per changed function that produced nothing,
    naming the premise that voided it."""
    head_nodes: dict[str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]] = {}

    def nodes_of(path: str) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
        if path not in head_nodes:
            head_nodes[path] = _function_nodes(head_sources.get(path, ""))
        return head_nodes[path]

    produced: list[PropagationNote] = []
    for definition in changed:
        note = note_for(
            graph,
            definition,
            head_sources=head_sources,
            base_sources=base_sources,
            nodes_of=nodes_of,
            trace=trace,
        )
        if note is not None:
            produced.append(note)
    produced.sort(key=lambda note: (note.path, note.line, note.exception))
    return tuple(produced[:limit])


def note_for(  # noqa: PLR0911 - every return is one premise failing, named
    graph: CallGraph,
    changed: ChangedFunction,
    *,
    head_sources: Mapping[str, str],
    base_sources: Mapping[str, str],
    nodes_of: Callable[[str], dict[str, ast.FunctionDef | ast.AsyncFunctionDef]],
    trace: list[str] | None = None,
) -> PropagationNote | None:
    """The one note this changed function earns, or None.

    Every `return None` below is a premise that did not hold, and that is the
    whole design: a hypothesis with two of three is a guess.
    """
    def void(reason: str) -> None:
        if trace is not None:
            trace.append(reason)

    subject = changed.definition
    if subject.is_test:
        return None
    head_node = nodes_of(subject.path).get(subject.qualname)
    base_node = _function_nodes(base_sources.get(subject.path, "")).get(subject.qualname)
    if head_node is None or base_node is None:
        void(VOID_NO_BASE)
        return None  # premise (i) needs both revisions of the same function

    # (i) a call this change introduced
    added = _called_names(head_node) - _called_names(base_node)
    if not added:
        void(VOID_NO_ADDED_CALL)
        return None

    # the changed function's own handlers, read once
    handled_here = _handled_types(head_node)
    if handled_here & CATCH_ALL:
        void(VOID_HANDLED_HERE)
        return None

    furthest = VOID_UNBOUND_CALLEE
    for callee_name in sorted(added):
        callee = _resolved_callee(graph, subject, callee_name)
        if callee is None or callee.is_test:
            furthest = VOID_UNBOUND_CALLEE
            continue  # unresolved or a test helper: not a hypothesis
        callee_node = nodes_of(callee.path).get(callee.qualname)
        raised = _raises_of(callee, callee_node)
        if raised is None:
            furthest = VOID_CALLEE_RAISES_NOTHING
            continue
        exception, evidence = raised
        # `is not False` and not `is True`: an undecidable handler voids the
        # hypothesis rather than asserting the exception is unhandled.
        if exception_caught(handled_here, exception) is not False:
            furthest = VOID_HANDLED_BY_CALLEE_TYPE
            continue
        furthest = VOID_NO_UNGUARDED_CALLER

        # (iii) a non-test caller of the changed function that does not catch it
        for site in graph.bound_sites(subject):
            if site.is_test or site.inside is None or site.inside == subject.qualname:
                continue
            caller_node = nodes_of(site.path).get(site.inside)
            if caller_node is None:
                continue
            caught = _handled_types(caller_node)
            if exception_caught(caught, exception) is not False:
                continue
            call_line = next(
                (
                    node.lineno
                    for node in ast.walk(head_node)
                    if isinstance(node, ast.Call) and dotted_name(node.func) == callee_name
                ),
                subject.line,
            )
            return PropagationNote(
                policy_version=PROPAGATION_POLICY_VERSION,
                path=subject.path,
                line=call_line,
                changed_qualname=subject.qualname,
                callee=callee_name,
                exception=exception,
                evidence=evidence,
                caller_path=site.path,
                caller_line=site.line,
                caller_qualname=site.inside,
            )
    void(furthest)
    return None


def _resolved_callee(
    graph: CallGraph, subject: FunctionDef, written: str
) -> FunctionDef | None:
    """The one definition a call written inside ``subject`` can mean, or None."""
    if graph.binding is None:
        return None
    target = graph.binding.resolve(
        Reference(path=subject.path, dotted=written, scope=subject.qualname)
    )
    return graph.definition_at(target)


__all__ = [
    "MAX_DEPTH",
    "MAX_NOTES",
    "PROPAGATION_POLICY_VERSION",
    "WORDING_MAX_TOKENS",
    "WORDING_SCHEMA",
    "WORDING_SYSTEM",
    "PropagationNote",
    "is_test_path",
    "note_for",
    "notes_for_change",
]
