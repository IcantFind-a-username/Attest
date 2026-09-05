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
- **the recording must be stable.** The probe runs twice on base and the two
  observations must be identical. A clock, an address in a `repr`, an iteration
  order: any of them would make the replay fail on base for a reason that has
  nothing to do with the diff. Refused, not recorded.

An observation is deliberately coarse -- `("value", repr(x))` or
`("exception", type(x).__name__)`. It is not a semantic model of the code; it is
the most that can be asserted about an arbitrary object without importing the
project's own vocabulary into the test file, and the replay compares the pair as
a whole so a value that becomes an exception, or the reverse, is a difference.
"""

from __future__ import annotations

import ast
import base64
import json
import re
from dataclasses import dataclass

PROBE_POLICY_VERSION = "attest.probe.record-replay.v1"

# The one line a probe run reports its observation on. It is printed *and*
# raised: a passing pytest test shows neither its stdout nor its message, so the
# probe fails on purpose -- a recording run is not a verdict and has no other
# way to return a payload through the executor protocol.
MARKER = "ATTEST-PROBE-OBSERVATION"
_MARKER_RE = re.compile(re.escape(MARKER) + r"\s+([A-Za-z0-9+/=]+)")

PROBE_MAX_OUTPUT_TOKENS = 1_500
PROBE_TEST_NAME = "test_attest_probe"
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

    ``kind`` is ``"value"`` or ``"exception"``; ``detail`` is ``repr(value)`` or
    the exception's type name. Coarse on purpose -- see the module docstring."""

    kind: str
    detail: str

    def as_literal(self) -> str:
        """The observation as a Python literal the replay compares against."""
        return repr({"kind": self.kind, "detail": self.detail})

    def sentence(self) -> str:
        """One clause naming what base did, for a reason string or a receipt."""
        if self.kind == "exception":
            return f"the merge base raised {self.detail}"
        return f"the merge base returned {self.detail}"


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
    return spec


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
        preamble=("import base64", "import json", ""),
        body=[
            "    try:",
            f"        _attest_value = {spec.expression}",
            "    except BaseException as _attest_error:  # noqa: BLE001 - the type is the record",
            "        _attest_observed = {",
            "            'kind': 'exception',",
            "            'detail': type(_attest_error).__name__,",
            "        }",
            "    else:",
            "        _attest_observed = {'kind': 'value', 'detail': repr(_attest_value)}",
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
    if observation.kind == "value":
        try:
            ast.literal_eval(observation.detail)
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            body = [
                f"    _attest_value = {spec.expression}",
                RECORDED_COMMENT,
                f"    assert repr(_attest_value) == {observation.detail!r}",
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
    return _render(name=REPLAY_TEST_NAME, spec=spec, body=body, preamble=())


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
                and payload.get("kind") in {"value", "exception"}
                and isinstance(payload.get("detail"), str)
            ):
                return Observation(kind=payload["kind"], detail=payload["detail"])
    return None
