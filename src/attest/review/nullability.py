"""Yellow (b), the first class: a null hypothesis with premises that are checked.

Mainline §1.1 gives yellow one job -- *state a hypothesis as premises, verify
each premise with a deterministic checker, and say only the premises that were
verified*. Yellow (a) (`impact.py`) does that with no model at all, which is why
it is silent on every unit it has ever been measured over. This module is the
first yellow level where a **model proposes** and an **algorithm decides**, and
the division of labour is the whole design:

    the model chooses    *which parameter, which line, which caller*
    the checker decides  *whether the three premises actually hold*
    the kernel writes    *the sentence, from the verified premises*

The model may write anything at all; nothing it writes reaches an author. What
reaches an author is one sentence built from three facts the checker read out of
the tree itself. A hypothesis whose premises do not all hold is **void** -- not
softened, not hedged, not published with a caveat -- and its refusal is recorded
in the ledger so the void rate is measurable rather than assumed.

## The three premises, and why only these three

A premise is admissible here only if a deterministic checker can decide it from
the head tree. That rules out every interesting question about *intent* and
leaves exactly three facts, which together are a nullability hazard:

    (i)   the parameter **can** be None -- its annotation is `Optional[...]` /
          `... | None`, or its default is `None`;
    (ii)  the code **dereferences it anyway** -- some line inside the function
          reads an attribute of it, subscripts it, or calls it, and no `None`
          guard stands between the function's entry and that line;
    (iii) some caller **can actually supply None** -- the argument it passes for
          that parameter comes from a function whose own return annotation
          admits None.

(i) alone is a type annotation. (ii) alone is an ordinary dereference. (iii)
alone is a nullable value nobody misuses. Only the conjunction says something,
and each third of it is a fact this module reads rather than a judgement it
makes.

## What it refuses to say

Every uncertainty abstains, which is the same rule yellow (a) follows:

- a parameter whose annotation cannot be parsed is not Optional *as far as this
  module knows*, and premise (i) fails;
- a guard this module does not recognise makes premise (ii) fail, so an
  unrecognised guard produces **silence**, never a false claim;
- an argument this module cannot trace to a definition fails premise (iii), and
  a source function with no return annotation fails it too -- an unannotated
  function is not evidence of anything;
- a function name defined more than once in the tree is ambiguous and every
  premise about it fails.

The asymmetry is deliberate: every direction of doubt costs recall and none of
them costs precision.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

NULLABILITY_POLICY_VERSION = "attest.nullability.premised-hypothesis.v2"
CATEGORY = "nullability"

# The model is asked for candidates, not for conclusions, and the prompt says so.
# It is deliberately silent about what the checker will accept: a prompt that
# describes the checker's rules measures the prompt, not the level.
HYPOTHESIS_SYSTEM = (
    "You are reading one function that a pull request changed. Name the places "
    "where a parameter that can be None is used without being checked for None "
    "first, and name a caller that could pass None. Answer only about the "
    "function you are shown. If nothing fits, return an empty list."
)
HYPOTHESIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "hypotheses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "function": {"type": "string"},
                    "parameter": {"type": "string"},
                    "access_line": {"type": "integer"},
                    "caller_path": {"type": "string"},
                    "caller_line": {"type": "integer"},
                    "argument_source": {"type": "string"},
                },
                "required": [
                    "file",
                    "function",
                    "parameter",
                    "access_line",
                    "caller_path",
                    "caller_line",
                    "argument_source",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["hypotheses"],
    "additionalProperties": False,
}
HYPOTHESIS_MAX_TOKENS = 900
MAX_HYPOTHESES = 6  # per review; the checker voids most of them and says so
MAX_NOTES = 2  # author-visible notes per pull request, **shared with yellow (a)**
# What one prompt may show. A model shown fifty functions answers about the ones
# it can hold, not the ones that matter, and the price of the call grows with
# the prompt; a long function is dropped rather than truncated, because a
# truncated body makes the line numbers the model must return meaningless.
NULLABILITY_MAX_UNITS_PER_CALL = 5
NULLABILITY_MAX_FUNCTION_LINES = 120

PREMISE_OPTIONAL = "i_parameter_admits_none"
PREMISE_UNGUARDED = "ii_unguarded_dereference"
PREMISE_CALLER = "iii_caller_supplies_none"
PREMISES = (PREMISE_OPTIONAL, PREMISE_UNGUARDED, PREMISE_CALLER)


@dataclass(frozen=True)
class Hypothesis:
    """One model proposal, in the only shape the checker can read."""

    path: str
    qualname: str
    parameter: str
    access_line: int
    caller_path: str
    caller_line: int
    argument_source: str


@dataclass(frozen=True)
class PremiseVerdict:
    """One premise, decided. `detail` is what the checker read, not why it chose."""

    premise: str
    holds: bool
    detail: str


@dataclass(frozen=True)
class NullabilityNote:
    """A hypothesis all of whose premises hold, with the readings that hold them."""

    hypothesis: Hypothesis
    verdicts: tuple[PremiseVerdict, ...]
    annotation: str  # the parameter's annotation or default, as premise (i) read it
    access_kind: str  # "attribute", "subscript" or "call"
    source_returns: str  # the source function's return annotation


# --------------------------------------------------------------------------
# tree reading


def _parse(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return None


def _functions(tree: ast.Module) -> dict[str, ast.FunctionDef | ast.AsyncFunctionDef]:
    """Every function of one module, by qualname."""
    found: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}

    def walk(node: ast.AST, prefix: list[str]) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                qualname = ".".join([*prefix, child.name])
                found[qualname] = child
                walk(child, [*prefix, child.name])
            elif isinstance(child, ast.ClassDef):
                walk(child, [*prefix, child.name])

    walk(tree, [])
    return found


def _annotation_admits_none(annotation: ast.expr | None) -> str | None:
    """The annotation text when it admits None, else None.

    Textual and deliberately so: `str | None`, `Optional[str]`, `t.Optional[X]`
    and `Union[X, None]` all unparse to text containing `None` or `Optional`, and
    a form this module cannot recognise is treated as not admitting None."""
    if annotation is None:
        return None
    text = ast.unparse(annotation)
    return text if ("None" in text or "Optional" in text) else None


# --------------------------------------------------------------------------
# premise (i): the parameter admits None


def _tested_against_none(
    function: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str
) -> bool:
    """Does this function itself compare ``parameter`` against ``None``? (D-165)

    An author who writes ``if x is None`` has said, in code, that `x` can be
    None -- and said it without a type annotation, which is what the first
    measurement of this level ran out of. A test anywhere in the function
    counts: what premise (ii) then asks is whether one stands *above the
    dereference*, and those are different questions. `x is None`,
    `x is not None`, `x == None` and `not x` are read; anything else is not.
    """
    for node in ast.walk(function):
        if isinstance(node, ast.Compare):
            if not _names(node.left, parameter):
                continue
            for operator, comparator in zip(node.ops, node.comparators, strict=False):
                if isinstance(operator, ast.Is | ast.IsNot | ast.Eq | ast.NotEq) and (
                    isinstance(comparator, ast.Constant) and comparator.value is None
                ):
                    return True
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            if _names(node.operand, parameter):
                return True
    return False


def _names(expression: ast.expr, parameter: str) -> bool:
    return isinstance(expression, ast.Name) and expression.id == parameter


def check_optional(
    function: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str
) -> tuple[PremiseVerdict, str]:
    args = function.args
    positional = [*args.posonlyargs, *args.args]
    for index, arg in enumerate(positional):
        if arg.arg != parameter:
            continue
        annotated = _annotation_admits_none(arg.annotation)
        if annotated is not None:
            return (
                PremiseVerdict(PREMISE_OPTIONAL, True, f"annotated `{annotated}`"),
                annotated,
            )
        offset = index - (len(positional) - len(args.defaults))
        if offset >= 0 and offset < len(args.defaults):
            default_node = args.defaults[offset]
            if isinstance(default_node, ast.Constant) and default_node.value is None:
                return (
                    PremiseVerdict(PREMISE_OPTIONAL, True, "defaults to `None`"),
                    "default None",
                )
        if _tested_against_none(function, parameter):
            return (
                PremiseVerdict(
                    PREMISE_OPTIONAL, True, "the function itself tests it against `None`"
                ),
                "tested against None",
            )
        return (
            PremiseVerdict(
                PREMISE_OPTIONAL,
                False,
                "no annotation admits None, the default is not None, and the function "
                "never tests it against None",
            ),
            "",
        )
    for arg, default in zip(args.kwonlyargs, args.kw_defaults, strict=False):
        if arg.arg != parameter:
            continue
        annotated = _annotation_admits_none(arg.annotation)
        if annotated is not None:
            return (
                PremiseVerdict(PREMISE_OPTIONAL, True, f"annotated `{annotated}`"),
                annotated,
            )
        if isinstance(default, ast.Constant) and default.value is None:
            return (
                PremiseVerdict(PREMISE_OPTIONAL, True, "defaults to `None`"),
                "default None",
            )
        if _tested_against_none(function, parameter):
            return (
                PremiseVerdict(
                    PREMISE_OPTIONAL, True, "the function itself tests it against `None`"
                ),
                "tested against None",
            )
        return (
            PremiseVerdict(
                PREMISE_OPTIONAL,
                False,
                "no annotation admits None, the default is not None, and the function "
                "never tests it against None",
            ),
            "",
        )
    return PremiseVerdict(PREMISE_OPTIONAL, False, f"no parameter named `{parameter}`"), ""


# --------------------------------------------------------------------------
# premise (ii): the dereference, and no guard between entry and it

# Every guard form this module recognises. An unrecognised guard makes the
# premise *fail*, so this list can only cost recall.
_GUARD_CALLS = frozenset({"isinstance", "getattr", "hasattr"})


def _tests_not_none(test: ast.expr, parameter: str) -> bool:
    """Does this test, when true, establish that `parameter` is not None?"""
    if isinstance(test, ast.Name):
        return test.id == parameter  # `if p:`
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name):
        if test.left.id != parameter:
            return False
        for op, comparator in zip(test.ops, test.comparators, strict=False):
            is_none = isinstance(comparator, ast.Constant) and comparator.value is None
            if isinstance(op, ast.IsNot) and is_none:
                return True
        return False
    if isinstance(test, ast.Call) and isinstance(test.func, ast.Name):
        return test.func.id in _GUARD_CALLS and any(
            isinstance(a, ast.Name) and a.id == parameter for a in test.args
        )
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        return any(_tests_not_none(value, parameter) for value in test.values)
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return _tests_is_none(test.operand, parameter)
    return False


def _tests_is_none(test: ast.expr, parameter: str) -> bool:
    """Does this test, when true, establish that `parameter` **is** None?"""
    if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name):
        if test.left.id != parameter:
            return False
        for op, comparator in zip(test.ops, test.comparators, strict=False):
            is_none = isinstance(comparator, ast.Constant) and comparator.value is None
            if isinstance(op, ast.Is) and is_none:
                return True
        return False
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return isinstance(test.operand, ast.Name) and test.operand.id == parameter
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        return any(_tests_is_none(value, parameter) for value in test.values)
    return False


def _exits(body: Sequence[ast.stmt]) -> bool:
    """Does this block leave, so that what follows it is guarded?"""
    return any(
        isinstance(statement, ast.Return | ast.Raise | ast.Continue | ast.Break)
        for statement in body
    )


def _rebinds(statement: ast.stmt, parameter: str) -> bool:
    """Does this statement give the parameter a value of its own?"""
    targets: list[ast.expr] = []
    if isinstance(statement, ast.Assign):
        targets = list(statement.targets)
    elif isinstance(statement, ast.AnnAssign | ast.AugAssign):
        targets = [statement.target]
    return any(isinstance(t, ast.Name) and t.id == parameter for t in targets)


def _access_at(
    function: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str, line: int
) -> str | None:
    """The kind of dereference of `parameter` on `line`, or None when there is none."""
    for node in ast.walk(function):
        if getattr(node, "lineno", None) != line:
            continue
        value: ast.expr | None = None
        kind = ""
        if isinstance(node, ast.Attribute):
            value, kind = node.value, "attribute"
        elif isinstance(node, ast.Subscript):
            value, kind = node.value, "subscript"
        elif isinstance(node, ast.Call):
            value, kind = node.func, "call"
        if isinstance(value, ast.Name) and value.id == parameter:
            return kind
    return None


def check_unguarded(
    function: ast.FunctionDef | ast.AsyncFunctionDef, parameter: str, line: int
) -> tuple[PremiseVerdict, str]:
    """Premise (ii): the line dereferences the parameter and no guard reaches it.

    The walk is a path search rather than a dataflow analysis, and every guard it
    passes through makes the premise fail:

    - an enclosing `if`/`while` whose test establishes not-None, with the line in
      the positive branch (or `is None` with the line in the `else`);
    - an earlier sibling `if p is None: return/raise/continue/break`;
    - an earlier `assert p is not None`;
    - any earlier statement that rebinds the parameter;
    - a `try:` whose handler catches `AttributeError` or `TypeError`;
    - an `if`/ternary expression on the line itself that tests the parameter.
    """
    kind = _access_at(function, parameter, line)
    if kind is None:
        return (
            PremiseVerdict(
                PREMISE_UNGUARDED, False, f"line {line} does not dereference `{parameter}`"
            ),
            "",
        )

    guard: str | None = None

    def scan(body: Sequence[ast.stmt]) -> bool:
        """Walk one block towards the line; True when the line is inside it."""
        nonlocal guard
        for statement in body:
            start = statement.lineno
            end = getattr(statement, "end_lineno", start) or start
            if end < line:
                # a statement entirely before the line: it may guard what follows
                early_return = (
                    isinstance(statement, ast.If)
                    and _tests_is_none(statement.test, parameter)
                    and (
                        _exits(statement.body)
                        or any(_rebinds(inner, parameter) for inner in statement.body)
                    )
                )
                if early_return:
                    guard = f"line {statement.lineno} returns or rebinds when `{parameter}` is None"
                    return False
                if isinstance(statement, ast.Assert) and _tests_not_none(statement.test, parameter):
                    guard = f"line {statement.lineno} asserts `{parameter}` is not None"
                    return False
                if _rebinds(statement, parameter):
                    guard = f"line {statement.lineno} rebinds `{parameter}`"
                    return False
                continue
            if not (start <= line <= end):
                continue
            # the line is inside this statement: descend, checking what it guards
            if isinstance(statement, ast.If | ast.While):
                in_body = any(
                    inner.lineno
                    <= line
                    <= (getattr(inner, "end_lineno", inner.lineno) or inner.lineno)
                    for inner in statement.body
                )
                if in_body and _tests_not_none(statement.test, parameter):
                    guard = f"line {statement.lineno} tests `{parameter}` is not None"
                    return False
                orelse = getattr(statement, "orelse", [])
                in_else = any(
                    inner.lineno
                    <= line
                    <= (getattr(inner, "end_lineno", inner.lineno) or inner.lineno)
                    for inner in orelse
                )
                if in_else and _tests_is_none(statement.test, parameter):
                    guard = (
                        f"line {statement.lineno} puts the else branch behind `{parameter} is None`"
                    )
                    return False
                return scan(statement.body) or scan(list(orelse))
            if isinstance(statement, ast.Try):
                caught = {
                    ast.unparse(handler.type) if handler.type is not None else ""
                    for handler in statement.handlers
                }
                if caught & {
                    "AttributeError",
                    "TypeError",
                    "Exception",
                    "(AttributeError, TypeError)",
                }:
                    guard = f"line {statement.lineno} catches the dereference"
                    return False
                for block in (statement.body, statement.orelse, statement.finalbody):
                    if scan(list(block)):
                        return True
                return guard is None
            for field in ("body", "orelse", "finalbody"):
                nested = getattr(statement, field, None)
                if isinstance(nested, list) and nested and isinstance(nested[0], ast.stmt):
                    if scan(nested):
                        return True
                    if guard is not None:
                        return False
            return True
        return False

    scan(function.body)
    if guard is not None:
        return PremiseVerdict(PREMISE_UNGUARDED, False, guard), ""
    # a ternary on the line itself is a guard the block walk cannot see
    for node in ast.walk(function):
        if not isinstance(node, ast.IfExp):
            continue
        end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
        if node.lineno <= line <= end_line and (
            _tests_not_none(node.test, parameter) or _tests_is_none(node.test, parameter)
        ):
            return (
                PremiseVerdict(
                    PREMISE_UNGUARDED, False, f"line {node.lineno} guards the use inline"
                ),
                "",
            )
    return (
        PremiseVerdict(
            PREMISE_UNGUARDED,
            True,
            f"line {line} takes the {kind} of `{parameter}` with no None guard above it",
        ),
        kind,
    )


# --------------------------------------------------------------------------
# premise (iii): a caller whose argument can be None


def _argument_for(
    call: ast.Call,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    parameter: str,
    *,
    implicit_self: bool,
) -> ast.expr | None:
    """The expression this call passes for `parameter`, or None when it cannot be told."""
    for keyword in call.keywords:
        if keyword.arg == parameter:
            return keyword.value
        if keyword.arg is None:
            return None  # `**kwargs` may carry it; nothing can be told
    positional = [a.arg for a in [*function.args.posonlyargs, *function.args.args]]
    if implicit_self and positional:
        positional = positional[1:]
    if parameter not in positional:
        return None
    index = positional.index(parameter)
    if any(isinstance(a, ast.Starred) for a in call.args):
        return None
    return call.args[index] if index < len(call.args) else None


def _source_name(expression: ast.expr, enclosing: ast.AST | None, line: int) -> str | None:
    """The function whose return value this expression is, if that is decidable."""
    if isinstance(expression, ast.Call):
        func = expression.func
        if isinstance(func, ast.Name):
            return func.id
        if isinstance(func, ast.Attribute):
            return func.attr
        return None
    if isinstance(expression, ast.Name) and enclosing is not None:
        # a local name: the one assignment above the call that binds it
        found: str | None = None
        for node in ast.walk(enclosing):
            if not isinstance(node, ast.Assign | ast.AnnAssign) or node.lineno >= line:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if not any(isinstance(t, ast.Name) and t.id == expression.id for t in targets):
                continue
            value = node.value
            if value is None:
                continue
            found = _source_name(value, None, line)
        return found
    return None


def check_caller(
    sources: Mapping[str, str],
    hypothesis: Hypothesis,
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[PremiseVerdict, str]:
    caller_source = sources.get(hypothesis.caller_path)
    if caller_source is None:
        return PremiseVerdict(PREMISE_CALLER, False, "no such caller file"), ""
    caller_tree = _parse(caller_source)
    if caller_tree is None:
        return PremiseVerdict(PREMISE_CALLER, False, "the caller file does not parse"), ""
    bare = hypothesis.qualname.split(".")[-1]
    call: ast.Call | None = None
    for node in ast.walk(caller_tree):
        if not isinstance(node, ast.Call) or node.lineno != hypothesis.caller_line:
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name == bare:
            call = node
            break
    if call is None:
        return (
            PremiseVerdict(
                PREMISE_CALLER,
                False,
                f"{hypothesis.caller_path}:{hypothesis.caller_line} does not call `{bare}`",
            ),
            "",
        )
    implicit_self = "." in hypothesis.qualname and isinstance(call.func, ast.Attribute)
    argument = _argument_for(call, function, hypothesis.parameter, implicit_self=implicit_self)
    if argument is None:
        return (
            PremiseVerdict(
                PREMISE_CALLER, False, f"the call does not pass `{hypothesis.parameter}` decidably"
            ),
            "",
        )
    enclosing: ast.AST | None = None
    for node in ast.walk(caller_tree):
        if isinstance(
            node, ast.FunctionDef | ast.AsyncFunctionDef
        ) and node.lineno <= call.lineno <= (
            getattr(node, "end_lineno", node.lineno) or node.lineno
        ):
            enclosing = node
    source = _source_name(argument, enclosing, call.lineno)
    if source is None:
        return (
            PremiseVerdict(PREMISE_CALLER, False, "the argument traces to no function call"),
            "",
        )
    if source != hypothesis.argument_source:
        return (
            PremiseVerdict(
                PREMISE_CALLER,
                False,
                f"the argument comes from `{source}`, not `{hypothesis.argument_source}`",
            ),
            "",
        )
    definitions = [
        function_node
        for path in sorted(sources)
        if (tree := _parse(sources[path])) is not None
        for qualname, function_node in _functions(tree).items()
        if qualname.split(".")[-1] == source
    ]
    if len(definitions) != 1:
        return (
            PremiseVerdict(
                PREMISE_CALLER, False, f"`{source}` is defined {len(definitions)} times"
            ),
            "",
        )
    returns = _annotation_admits_none(definitions[0].returns)
    if returns is None:
        # D-165: an unannotated function that writes `return None` -- or falls
        # off the end of a branch -- has said what it returns in code. The
        # annotation was the only reading before, and 11 of 13 hypotheses died
        # here on a corpus that carries no annotations at all.
        if _returns_none(definitions[0]):
            return (
                PremiseVerdict(
                    PREMISE_CALLER,
                    True,
                    f"`{source}` has a `return None` in its body and the call passes it here",
                ),
                "returns None",
            )
        return (
            PremiseVerdict(
                PREMISE_CALLER,
                False,
                f"`{source}` has no return annotation admitting None and no `return None`",
            ),
            "",
        )
    return (
        PremiseVerdict(
            PREMISE_CALLER, True, f"`{source}` returns `{returns}` and the call passes it here"
        ),
        returns,
    )


def _returns_none(function: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Does this function's own body write `return None`, or a bare `return`?

    A nested `def` is its own function, so the walk stops at one. A bare
    `return` returns None as surely as an explicit one; a function with no
    `return` at all also returns None, but that is a function nobody calls for
    a value and reading it that way would make the premise vacuous.
    """
    stack: list[ast.AST] = list(ast.iter_child_nodes(function))
    while stack:
        current = stack.pop()
        if isinstance(current, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        if isinstance(current, ast.Return):
            if current.value is None:
                return True
            if isinstance(current.value, ast.Constant) and current.value.value is None:
                return True
        stack.extend(ast.iter_child_nodes(current))
    return False


# --------------------------------------------------------------------------
# the adjudication


def check(sources: Mapping[str, str], hypothesis: Hypothesis) -> tuple[PremiseVerdict, ...]:
    """The three premises, each decided from the tree. Order is fixed."""
    source = sources.get(hypothesis.path)
    tree = _parse(source) if source is not None else None
    if tree is None:
        void = "the changed file does not parse"
        return tuple(PremiseVerdict(premise, False, void) for premise in PREMISES)
    function = _functions(tree).get(hypothesis.qualname)
    if function is None:
        void = f"no function `{hypothesis.qualname}` in {hypothesis.path}"
        return tuple(PremiseVerdict(premise, False, void) for premise in PREMISES)
    first, _ = check_optional(function, hypothesis.parameter)
    second, _ = check_unguarded(function, hypothesis.parameter, hypothesis.access_line)
    third, _ = check_caller(sources, hypothesis, function)
    return (first, second, third)


def note_for(sources: Mapping[str, str], hypothesis: Hypothesis) -> NullabilityNote | None:
    """One note, or None. **All three premises or nothing** -- there is no partial
    finding, because a hypothesis with two of three premises is a guess."""
    source = sources.get(hypothesis.path)
    tree = _parse(source) if source is not None else None
    if tree is None:
        return None
    function = _functions(tree).get(hypothesis.qualname)
    if function is None:
        return None
    first, annotation = check_optional(function, hypothesis.parameter)
    if not first.holds:
        return None
    second, kind = check_unguarded(function, hypothesis.parameter, hypothesis.access_line)
    if not second.holds:
        return None
    third, returns = check_caller(sources, hypothesis, function)
    if not third.holds:
        return None
    return NullabilityNote(
        hypothesis=hypothesis,
        verdicts=(first, second, third),
        annotation=annotation,
        access_kind=kind,
        source_returns=returns,
    )


# --------------------------------------------------------------------------
# the model's half


def prompt_for(units: Sequence[tuple[str, str, int, str]]) -> str:
    """The one prompt this level ever sends: the changed functions, numbered.

    Every line carries its **file line number**, because the only thing the model
    is asked to produce that a checker cannot recover is a coordinate, and a
    coordinate off by the length of a preamble is a void hypothesis rather than a
    wrong one."""
    blocks: list[str] = []
    for path, qualname, start, source in units:
        numbered = "\n".join(
            f"{start + offset:5d}  {text}" for offset, text in enumerate(source.splitlines())
        )
        blocks.append(f"file: {path}\nfunction: {qualname}\n{numbered}")
    return (
        "The functions this pull request changed, with their real line numbers:\n\n"
        + "\n\n".join(blocks)
        + "\n\nFor each place where a parameter that can be None is used without a "
        "None check, give the file, the function, the parameter, the line of the "
        "use, and one caller (its file, its line, and the function whose return "
        "value that caller passes)."
    )


def hypotheses_from(payload: object, *, limit: int = MAX_HYPOTHESES) -> tuple[Hypothesis, ...]:
    """The model's answer, in the checker's shape. Anything malformed is dropped
    rather than repaired: a hypothesis is cheap and a guess is not."""
    if not isinstance(payload, dict):
        return ()
    raw = payload.get("hypotheses")
    if not isinstance(raw, list):
        return ()
    out: list[Hypothesis] = []
    for item in raw[:limit]:
        if not isinstance(item, dict):
            continue
        try:
            out.append(
                Hypothesis(
                    path=str(item["file"]),
                    qualname=str(item["function"]),
                    parameter=str(item["parameter"]),
                    access_line=int(item["access_line"]),
                    caller_path=str(item["caller_path"]),
                    caller_line=int(item["caller_line"]),
                    argument_source=str(item["argument_source"]),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return tuple(out)


def notes_for_change(
    sources: Mapping[str, str],
    hypotheses: Sequence[Hypothesis],
    *,
    limit: int = MAX_NOTES,
) -> tuple[tuple[NullabilityNote, ...], tuple[tuple[Hypothesis, tuple[PremiseVerdict, ...]], ...]]:
    """The notes, and **every hypothesis that was voided with the premise that
    voided it** -- the second half is the point: a level that only reports what it
    said cannot be measured, and the void rate is what says whether the model is
    proposing anything real."""
    notes: list[NullabilityNote] = []
    voided: list[tuple[Hypothesis, tuple[PremiseVerdict, ...]]] = []
    for hypothesis in hypotheses:
        verdicts = check(sources, hypothesis)
        if all(verdict.holds for verdict in verdicts):
            note = note_for(sources, hypothesis)
            if note is not None:
                notes.append(note)
                continue
        voided.append((hypothesis, verdicts))
    return tuple(notes[:limit]), tuple(voided)
