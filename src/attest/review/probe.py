"""Reproduction by probe and record/replay: the model proposes, base decides (D-146).

D-140 measured the wall on forward pairs: **20 of 31 answered candidates** ended
as `unfaithful generated test: fails on base as well`, and the classification
([report](../../../docs/acceptance/2026-09-06-forward-pair-generation-failures.md))
found **0 environment failures** and **18 tests that asserted a behaviour the base
revision does not have either**. The model was being asked a question it cannot
answer from a forward diff: *what did the code do before?* On a reversed pair the
diff is the repair and states the answer; on a forward pair nothing does.

So this module stops asking. The division of labour becomes:

    the model chooses **what to call**   -- imports, setup, one expression
    the base revision says **what it does** -- recorded by executing the probe
    the kernel writes **the assertion**   -- from the recording, never from prose

A generated test is then a *replay*: the same expression, with the merge base's
own observed outcome asserted back. **`fails on base as well` is structurally
impossible on this path** -- the expectation is literally what base produced --
and if the differential reports it anyway that is a bug in this module, not
evidence about the diff, which is why `execute_differential` gives it its own
reason string in probe mode.

Two guards make the recording admissible, and both are structural:

- **the probe must execute the anchored file on base.** A probe that never
  reaches the code under review has recorded something else: a signature only
  head has (`TypeError: missing 2 required positional arguments`), an import
  that does not resolve, or -- the case D-140 case 20 actually produced -- its
  own pasted copy of the function. Refused, not recorded.
- **the recording must be stable.** The probe runs three times on base and the
  observations must be identical. A clock, an iteration order: either would make
  the replay fail on base for a reason that has nothing to do with the diff.
  Refused, not recorded. An object's ` at 0x…` address is not part of the
  recording (D-236): the probe body drops it and the replay compares the same
  address-free `repr`, so a returned closure or context manager records stably.

An observation is deliberately coarse -- `("value", repr(x))` or
`("exception", type(x).__name__)`. It is not a semantic model of the code; it is
the most that can be asserted about an arbitrary object without importing the
project's own vocabulary into the test file, and the replay compares the pair as
a whole so a value that becomes an exception, or the reverse, is a difference.

A third kind, `("warning", type(x).__name__)`, is recorded and never replayed
(D-235). Under a `filterwarnings = error` configuration -- the tree's own, or
one a probe's setup installed -- `warnings.warn` raises, and until 2026-09-13
the recorder wrote that down as an exception: `pallets/werkzeug#3266` certified
three red receipts whose "rejection" was a `DeprecationWarning` the probe's
`warnings.simplefilter("error")` had escalated. A warning is not a behaviour of
the code under review, so a recording that is one is refused, a head run that
raises one is not a difference, and the kernel never reads one as a rejection
(:func:`attest.certification.intent.warning_rejection`).

**Probe hygiene (D-235).** The setup builds arguments and nothing else. A setup
that reaches for the interpreter -- `warnings`, `sys.modules`, the recursion
limit, `os.environ` -- or that replaces part of the tree before the call --
`unittest.mock`, `monkeypatch`, an assignment to an attribute of an imported
name -- records the replacement, not the code. :func:`hygiene_refusal` refuses
those shapes statically, before anything is paid for, and the reason travels to
the next probe the search buys (D-216).
"""

from __future__ import annotations

import ast
import base64
import json
import re
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

from attest.review.output_contract import strip_addresses

PROBE_POLICY_VERSION = "attest.probe.record-replay.v1"

# The one line a probe run reports its observation on. It is printed *and*
# raised: a passing pytest test shows neither its stdout nor its message, so the
# probe fails on purpose -- a recording run is not a verdict and has no other
# way to return a payload through the executor protocol.
MARKER = "ATTEST-PROBE-OBSERVATION"
_MARKER_RE = re.compile(re.escape(MARKER) + r"\s+([A-Za-z0-9+/=]+)")

PROBE_MAX_OUTPUT_TOKENS = 1_500
PROBE_TEST_NAME = "test_attest_probe"
WARNING_KIND = "warning"  # D-235: a Warning subclass raised under a filter
# D-236: the one pattern the probe and the replay both strip from a `repr`. It is
# the same rule the renderer applies (`output_contract.strip_addresses`), spelled
# out here because the generated files must not import this package.
ADDRESS_PATTERN = r" at 0x[0-9a-f]+"
OBSERVATION_KINDS = frozenset({"value", "exception", WARNING_KIND})
REPLAY_TEST_NAME = "test_attest_replay"

PROBE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "imports": {"type": "string"},
        "setup": {"type": "string"},
        "expression": {"type": "string"},
    },
    "required": ["imports", "setup", "expression"],
    "additionalProperties": False,
}

PROBE_SYSTEM = """You are choosing ONE call into the code under review. You are NOT writing a
test and you are NOT stating what the code should do: something else will execute your call
against the previous revision and record what it actually did.

Return exactly three fields.

  imports     module-level import statements, one per line, and nothing else. Import the
              project the way its own code does. Never import a test module, a conftest, or
              anything under a tests package: your call runs outside the test tree.
  setup       statements that build the arguments. Standard library and the project only; no
              network, no subprocesses, no threads, no mocks of the code under review, no
              assertions, no printing. May be empty.
  expression  ONE Python expression that calls the changed code with those arguments. It must
              reach the anchored file -- a call that never enters it records nothing and is
              discarded.

Choose the input most likely to be handled DIFFERENTLY by the two revisions: the edge the change
is about. An expression that raises is fine and is often the point; the exception type is part
of what gets recorded. Do not guard it with try/except -- that hides exactly what is being
recorded."""


@dataclass(frozen=True)
class ProbeSpec:
    """What the model chose to call. No expectation of any kind."""

    imports: str
    setup: str
    expression: str


@dataclass(frozen=True)
class Observation:
    """What the base revision did when the probe called it.

    ``kind`` is ``"value"``, ``"exception"`` or ``"warning"``; ``detail`` is
    ``repr(value)`` or the exception's type name. Coarse on purpose -- see the
    module docstring. A ``"warning"`` is a `Warning` subclass raised as an
    exception under a warnings filter (D-235); it is recorded so the reason can
    name it and is never replayed."""

    kind: str
    detail: str

    def as_literal(self) -> str:
        """The observation as a Python literal the replay compares against."""
        return repr({"kind": self.kind, "detail": self.detail})

    def sentence(self) -> str:
        """One clause naming what base did, for a reason string or a receipt.
        An object's address (` at 0x…`) is the process's, not the value's, and
        is dropped from the prose (D-235 c)."""
        if self.kind == WARNING_KIND:
            return f"the merge base raised {self.detail}, a warning escalated to an exception"
        if self.kind == "exception":
            return f"the merge base raised {self.detail}"
        return f"the merge base returned {strip_addresses(self.detail)}"


class ProbeRefused(ValueError):
    """The model's probe is not admissible, with the reason a person can act on."""


def parse_probe(text: str) -> ProbeSpec:
    """The model's answer, structurally validated before anything executes it.

    Validation here is about *shape*, not safety: the sandbox is the safety
    boundary and is unchanged. A probe whose expression is two statements, or
    whose imports carry a function definition, is a probe that will record
    something other than one call, so it is refused before it is paid for."""
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced is not None:
        stripped = fenced.group(1)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ProbeRefused("probe output is not valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {"imports", "setup", "expression"}:
        raise ProbeRefused("probe output does not match the probe schema")
    if any(not isinstance(payload[field], str) for field in payload):
        raise ProbeRefused("probe output does not match the probe schema")
    spec = ProbeSpec(
        imports=payload["imports"].strip("\n"),
        setup=payload["setup"].strip("\n"),
        expression=" ".join(payload["expression"].split()),
    )
    if not spec.expression:
        raise ProbeRefused("probe has no expression")
    try:
        ast.parse(spec.expression, mode="eval")
    except SyntaxError as exc:
        raise ProbeRefused("probe expression is not a single Python expression") from exc
    try:
        imports = ast.parse(spec.imports or "pass")
    except SyntaxError as exc:
        raise ProbeRefused("probe imports do not parse") from exc
    if any(not isinstance(node, ast.Import | ast.ImportFrom | ast.Pass) for node in imports.body):
        raise ProbeRefused("probe imports contain something that is not an import")
    try:
        ast.parse(spec.setup or "pass")
    except SyntaxError as exc:
        raise ProbeRefused("probe setup does not parse") from exc
    refusal = hygiene_refusal(spec)
    if refusal is not None:
        raise ProbeRefused(refusal)
    return spec


# --- D-235: probe hygiene ----------------------------------------------------
#
# Owner authorisation of 2026-09-13. Each rule is a fact about the setup's text,
# read from its AST, and each refusal names the rule and quotes the statement so
# the next probe (D-216) knows what not to do. Names are resolved through the
# import bindings of the imports block and of the setup itself: `import sys as
# s` makes `s.modules` the same fact as `sys.modules`, and `from os import
# environ` makes `environ[...] = ...` a write to `os.environ`. A name the setup
# itself binds -- `mock = object()` -- is a local and reaches no rule.

_SNIPPET_CHARS = 80
_MOCK_MODULES = frozenset({"unittest.mock", "mock"})
_ENVIRON_WRITERS = frozenset(
    {"update", "setdefault", "pop", "popitem", "clear", "__setitem__", "__delitem__"}
)
_ENV_FUNCTIONS = frozenset({"os.putenv", "os.unsetenv"})


def hygiene_refusal(spec: ProbeSpec) -> str | None:
    """Why this probe's setup may not run, or ``None`` when it may (D-235).

    Refused, each with its own sentence: the `warnings` module reached by any
    route; `sys.modules` read or written; `unittest.mock`, the `mock`
    distribution or pytest's `monkeypatch`; an assignment, augmented or
    annotated assignment, deletion or `setattr`/`delattr` whose target root is a
    name an import bound; `sys.setrecursionlimit`; a write to `os.environ`
    (subscript assignment or deletion, a mutating method, `os.putenv`,
    `os.unsetenv`). A read of `os.environ`, a local object's attribute and a
    local named like a refused module are not refused. Shape errors are
    `parse_probe`'s and return ``None`` here."""
    try:
        imports = ast.parse(spec.imports or "pass")
        setup = ast.parse(spec.setup or "pass")
    except SyntaxError:
        return None
    bound = _import_bindings((*imports.body, *setup.body))
    local = _local_bindings(setup) - set(bound)

    def canonical(node: ast.AST) -> str | None:
        parts: list[str] = []
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if not isinstance(node, ast.Name):
            return None
        if node.id in local:
            return None
        root = bound.get(node.id, node.id)
        return ".".join([root, *reversed(parts)])

    def snippet(node: ast.AST, source: str = spec.setup) -> str:
        text = ast.get_source_segment(source, node) or ""
        text = " ".join(text.split())
        return text if len(text) <= _SNIPPET_CHARS else text[: _SNIPPET_CHARS - 1] + "…"

    def root_name(node: ast.AST) -> str | None:
        while isinstance(node, ast.Attribute | ast.Subscript):
            node = node.value
        return node.id if isinstance(node, ast.Name) else None

    for node in ast.walk(setup):
        # writes first: the target decides the sentence
        targets: list[ast.AST] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        elif isinstance(node, ast.Delete):
            targets = list(node.targets)
        for target in targets:
            if isinstance(target, ast.Subscript) and canonical(target.value) == "os.environ":
                return (
                    f"probe setup writes os.environ ({snippet(node)}); the code under review "
                    "must read the environment the executor gives it (D-235)"
                )
            if isinstance(target, ast.Attribute):
                root = root_name(target)
                if root is not None and root in bound and root not in local:
                    return (
                        f"probe setup assigns an attribute of the imported name {root} "
                        f"({snippet(node)}); replacing part of the tree before the call records "
                        "the replacement, not the code (D-235)"
                    )
        if isinstance(node, ast.Call):
            callee = canonical(node.func)
            if callee in ("setattr", "delattr") and node.args:
                root = root_name(node.args[0])
                if root is not None and root in bound and root not in local:
                    return (
                        f"probe setup assigns an attribute of the imported name {root} "
                        f"({snippet(node)}); replacing part of the tree before the call records "
                        "the replacement, not the code (D-235)"
                    )
            if callee in _ENV_FUNCTIONS or (
                isinstance(node.func, ast.Attribute)
                and node.func.attr in _ENVIRON_WRITERS
                and canonical(node.func.value) == "os.environ"
            ):
                return (
                    f"probe setup writes os.environ ({snippet(node)}); the code under review "
                    "must read the environment the executor gives it (D-235)"
                )
        if isinstance(node, ast.Name | ast.Attribute):
            name = canonical(node)
            if name is None:
                continue
            if name == "warnings" or name.startswith("warnings."):
                return (
                    f"probe setup uses the warnings module ({snippet(node)}); a recording made "
                    "under a changed warnings filter measures the filter, not the code, and a "
                    "warning is never a rejection (D-235)"
                )
            if name == "sys.modules" or name.startswith("sys.modules."):
                return (
                    f"probe setup touches sys.modules ({snippet(node)}); the recording must "
                    "see the tree's own import state (D-235)"
                )
            if name == "sys.setrecursionlimit":
                return (
                    f"probe setup changes the recursion limit with sys.setrecursionlimit "
                    f"({snippet(node)}); interpreter state is not an argument (D-235)"
                )
            if (
                name in _MOCK_MODULES
                or any(name.startswith(f"{module}.") for module in _MOCK_MODULES)
                or name == "monkeypatch"
                or name.startswith("monkeypatch.")
            ):
                what = "monkeypatch" if name.split(".", 1)[0] == "monkeypatch" else "mock"
                return (
                    f"probe setup mocks with {what} ({snippet(node)}); the code under review "
                    "must run against its real dependencies (D-235)"
                )
    # the import statements last, so a refusal quotes the use rather than the
    # import where there is one; an import nobody uses is still refused, because
    # the module is refused however it is reached
    for source, statements in ((spec.imports, imports.body), (spec.setup, setup.body)):
        for node in statements:
            modules: list[str] = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
                modules = [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
            for module in modules:
                if module == "warnings" or module.startswith("warnings."):
                    quoted = snippet(node, source) or module
                    return (
                        f"probe setup uses the warnings module ({quoted}); a recording made "
                        "under a changed warnings filter measures the filter, not the code, and "
                        "a warning is never a rejection (D-235)"
                    )
                if module in _MOCK_MODULES or any(
                    module.startswith(f"{name}.") for name in _MOCK_MODULES
                ):
                    return (
                        f"probe setup mocks ({snippet(node, source) or module}); the code under "
                        "review must run against its real dependencies (D-235)"
                    )
    return None


def _import_bindings(statements: Iterable[ast.AST]) -> dict[str, str]:
    """Every name an import statement binds, mapped to what it names:
    ``import os.path as p`` -> ``p: os.path``; ``from os import environ`` ->
    ``environ: os.environ``; ``import a.b`` binds ``a``."""
    bound: dict[str, str] = {}
    for node in statements:
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    bound[alias.asname] = alias.name
                else:
                    top = alias.name.split(".", 1)[0]
                    bound[top] = top
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            for alias in node.names:
                bound[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    return bound


def _local_bindings(tree: ast.AST) -> set[str]:
    """Names the setup binds by anything other than an import: an assignment,
    a def or class, a loop or `with` target, a walrus, an except clause, a
    parameter of a def or lambda it declares."""
    names: set[str] = set()

    def bind(target: ast.AST) -> None:
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, ast.Tuple | ast.List):
            for element in target.elts:
                bind(element)
        elif isinstance(target, ast.Starred):
            bind(target.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                bind(target)
        elif isinstance(
            node, ast.AnnAssign | ast.AugAssign | ast.For | ast.AsyncFor | ast.NamedExpr
        ):
            bind(node.target)
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                if item.optional_vars is not None:
                    bind(item.optional_vars)
        elif isinstance(node, ast.ExceptHandler) and node.name:
            names.add(node.name)
        elif isinstance(node, ast.comprehension):
            bind(node.target)
        elif isinstance(node, ast.arg):
            # a parameter of a def or lambda the setup declares: `self` in a
            # helper class's method is the probe's own object, not the tree's
            names.add(node.arg)
    return names


def reaches_the_tree(spec: ProbeSpec, tree_roots: Collection[str]) -> bool:
    """Does this probe touch anything the repository itself defines? (D-206)

    A probe must execute the anchored file, and it can only do that through
    something of the tree. The recorder already refuses one that does not -- but
    only after three container runs on base, and the 2026-09-12 held-out
    measurement spent **17 of 56** verification attempts on probes that never
    collected. This is the same refusal, decided before anything runs.

    **The whole probe is what reaches, not its import block.** An import is one
    route; loading a module by path is another, and the release drills use it:
    `import runpy` then `runpy.run_path('app.py')`. Reading imports alone called
    that unreachable, which broke `gates` on `main` at `516b924` and would have
    silenced the same shape on any real repository. So a probe reaches when an
    import names a tree root **or** any string it carries names a tree module or
    a Python file of the tree.

    Deliberately one-sided, and it fails open. A probe importing `numpy` **and**
    the project is fine: whether the image provides `numpy` is the image's
    answer, and refusing on a dependency this cannot enumerate would silence
    probes that work. Only a probe naming **nothing** of the tree anywhere is
    refused, because that one cannot reach the code under review by any route.
    A relative import names no root and cannot resolve outside the test tree; it
    does not count on its own.
    """
    try:
        tree = ast.parse(spec.imports or "pass")
    except SyntaxError:
        return True  # not this function's refusal; `parse_probe` owns the shape
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".", 1)[0] in tree_roots for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue
            if node.module.split(".", 1)[0] in tree_roots:
                return True
    # the other route: the probe names a module of the tree in a string it
    # carries -- `runpy.run_path("app.py")`, an `importlib` spec from a path, a
    # file opened by name. Read from the text rather than from the imports.
    for name in _quoted_names(f"{spec.setup}\n{spec.expression}"):
        stem = name.rsplit("/", 1)[-1]
        if stem.endswith(".py") and stem[:-3] in tree_roots:
            return True
        if stem in tree_roots:
            return True
    return False


def _quoted_names(source: str) -> set[str]:
    """Every string literal in a fragment, or every quoted run when it will not
    parse -- the fragment is the model's and need not be a complete statement."""
    found: set[str] = set()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set(re.findall(r"""['"]([^'"\n]{1,200})['"]""", source))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


def probe_test_body(spec: ProbeSpec) -> str:
    """The recording file: call the expression, report what happened, fail.

    It fails on purpose. `pytest` shows neither the stdout nor the message of a
    passing test, and the executor protocol carries no artifact of this module's
    own; a deliberate `AssertionError` puts the payload in both the captured
    output and the JUnit failure, and a recording run is never read as a verdict
    because only this module ever reads it."""
    return _render(
        name=PROBE_TEST_NAME,
        spec=spec,
        preamble=("import base64", "import json", "import re", ""),
        body=[
            "    try:",
            f"        _attest_value = {spec.expression}",
            "    except BaseException as _attest_error:  # noqa: BLE001 - the type is the record",
            "        _attest_observed = {",
            "            'kind': 'warning' if isinstance(_attest_error, Warning) else 'exception',",
            "            'detail': type(_attest_error).__name__,",
            "        }",
            "    else:",
            "        _attest_observed = {",
            "            'kind': 'value',",
            f"            'detail': re.sub({ADDRESS_PATTERN!r}, '', repr(_attest_value)),",
            "        }",
            "    _attest_payload = base64.b64encode(",
            "        json.dumps(_attest_observed, sort_keys=True).encode('utf-8')",
            "    ).decode('ascii')",
            f"    print('{MARKER} ' + _attest_payload)",
            f"    raise AssertionError('{MARKER} ' + _attest_payload)",
        ],
    )


RECORDED_COMMENT = (
    "    # recorded by executing the expression above on the merge base;\n"
    "    # no model wrote this expectation"
)


def replay_test_body(spec: ProbeSpec, observation: Observation) -> str:
    """The differential test: the same call, asserting what base actually did.

    This is the file that reaches the evidence bundle and that a reader verifies
    offline. Every expectation in it was measured, and the comment above the
    assertion says so -- a reviewer reading the bundle can see that no model
    wrote the value the assertion compares against.

    **The assertion is written the way a person would write it**, and that is
    not cosmetic. Every rule downstream reads the failing assertion: the
    changed-line binding, D-102's new-rejection origin, and D-132/D-134's
    value class, which asks whether *the base tree states the value this
    assertion pins*. An assertion that pinned ``"6"`` -- the string -- would be
    invisible to a base test that states ``6``, and the whole value class would
    drawer for a reason that is an artefact of this file's shape rather than a
    fact about the change. So a recorded value that is a literal is compared as
    that literal:

        _attest_value = mod.total(items)
        assert _attest_value == 6

    and nothing wraps the call, so a head revision that *raises* where base
    returned produces the crash at its real origin, which is what D-102 reads.
    A value whose ``repr`` is not a literal (a class instance, a `datetime`)
    falls back to comparing the ``repr``, and a recorded exception compares the
    type name; both pin a string, and the unchanged value-class rule decides
    what that is worth.
    """
    if observation.kind == WARNING_KIND:
        # D-235: never reached through `execute_differential`, which refuses the
        # recording; a caller that gets here has bypassed that rule
        raise ValueError(
            f"a warning observation ({observation.detail}) is not a behaviour of the code "
            "under review and cannot be replayed (D-235)"
        )
    if observation.kind == "value":
        try:
            ast.literal_eval(observation.detail)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            # D-236: the recording dropped the object's address, so the replay
            # compares the same address-free repr -- a fresh object on either
            # revision has a fresh address and the same value
            body = [
                f"    _attest_value = {spec.expression}",
                RECORDED_COMMENT,
                f"    assert re.sub({ADDRESS_PATTERN!r}, '', repr(_attest_value)) == "
                f"{observation.detail!r}",
            ]
        else:
            body = [
                f"    _attest_value = {spec.expression}",
                RECORDED_COMMENT,
                f"    assert _attest_value == {observation.detail}",
            ]
    else:
        body = [
            "    try:",
            f"        _attest_value = {spec.expression}",
            "    except BaseException as _attest_error:  # noqa: BLE001 - the type is the record",
            "        _attest_raised = type(_attest_error).__name__",
            "    else:",
            "        _attest_raised = None",
            RECORDED_COMMENT,
            f"    assert _attest_raised == {observation.detail!r}",
        ]
    return _render(name=REPLAY_TEST_NAME, spec=spec, body=body, preamble=("import re", ""))


def _render(
    *,
    name: str,
    spec: ProbeSpec,
    body: list[str],
    preamble: tuple[str, ...] = (),
) -> str:
    setup = [f"    {line}" if line.strip() else "" for line in spec.setup.splitlines()]
    lines = [
        *preamble,
        *spec.imports.splitlines(),
        "",
        "",
        f"def {name}():",
        *setup,
        *body,
        "",
    ]
    return "\n".join(line.rstrip() for line in lines)


def parse_observation(*texts: str) -> Observation | None:
    """The observation a probe run reported, from any of the streams it reached.

    The marker is looked for in every stream the executor brings back, because
    which one carries it depends on how `pytest` chose to report the failure,
    and a recording that exists must not be lost to that choice."""
    for text in texts:
        for match in _MARKER_RE.finditer(text or ""):
            try:
                payload = json.loads(base64.b64decode(match.group(1)).decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("kind") in OBSERVATION_KINDS
                and isinstance(payload.get("detail"), str)
            ):
                return Observation(kind=payload["kind"], detail=payload["detail"])
    return None


_SKIPPED = frozenset(
    {".git", ".attest", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
)



def tree_roots(root: Path) -> frozenset[str]:
    """Top-level module names **this repository defines**, for the probe check.

    Packages (a directory with ``__init__.py``) and modules at the repository
    root, and the same one level down -- ``src/`` and ``lib/`` are layout, not
    packages, which is the rule the binding layer already applies to paths.
    The standard library and installed distributions are deliberately absent:
    the question this answers is *does the probe import the project*, not
    *does every import resolve*.
    """
    names: set[str] = set()
    try:
        top = sorted(root.iterdir())
    except OSError:
        return frozenset()
    for base in (root, *(child for child in top if child.is_dir())):
        if base is not root and (base.name.startswith(".") or base.name in _SKIPPED):
            continue
        try:
            entries = sorted(base.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.name.startswith(".") or entry.name in _SKIPPED:
                continue
            if entry.is_dir() and (entry / "__init__.py").is_file():
                names.add(entry.name)
            elif entry.is_file() and entry.suffix == ".py":
                names.add(entry.stem)
    return frozenset(names)
