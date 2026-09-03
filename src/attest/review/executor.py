"""Generate and execute focused Python reproduction tests."""

from __future__ import annotations

import ast
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from attest.certification.binding import (
    BINDING_POLICY_VERSION,
    BindingObservation,
    binding_verdict,
)
from attest.certification.intent import IntentObservation, intent_verdict
from attest.execution.controller import Controller, ExecutorAdapter
from attest.execution.local_adapter import LocalDevelopmentAdapter
from attest.execution.types import ResourceLimits
from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.diffs import parse_diff
from attest.review.gate import GateResult, apply_verification
from attest.review.intent import RaiseOrigin, observe_intent, parse_raise_record
from attest.review.ledger import Ledger
from attest.review.planner import generation_context
from attest.review.proposer import Provider, call_provider, no_text_reason, response_fragment

MAX_CONTEXT_LINES = 200
REPRO_MAX_OUTPUT_TOKENS = 3_000
MAX_REPRO_ATTEMPTS = 2
# D-114: extra generations bought when the reproduction does not collect on
# head. One: a second scaffolding failure is a signal, not a budget to spend.
COLLECTION_REGENERATIONS = 1
CLEANUP_TIMEOUT_S = 1.0
GIT_TIMEOUT_S = 60.0
MAX_REASON_CHARS = 300
MAX_RUN_OUTPUT_FRAGMENT_CHARS = 2_000
CAP_SYS_ADMIN = 21
CAP_SYS_RESOURCE = 24
# where the reproduction is executed from inside the tree under test; it is
# disposable, because the tree is a throwaway worktree removed after the run
RUN_DIR_NAME = ".attest-repro"

REPRO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"test_body": {"type": "string"}},
    "required": ["test_body"],
    "additionalProperties": False,
}

GENERATOR_SYSTEM = """Write one focused pytest reproduction for the supplied finding. Return only
the test body required by the schema, never an empty object.

The reviewed change is a pull request. Two versions of the anchored code are shown: the current
(head) version, which contains the claimed defect, and the merge-base version it replaced. The
test must FAIL on the current version because of the claimed defect and PASS on the merge-base
version: assert the merge-base behaviour concretely, not merely the absence of a crash. Exactly
one module-level test function; import the project the way its existing tests do; no network,
subprocesses, threads, or mocks of the code under test. If the defect only shows through
pytest's own runner, use the project's test fixtures as the shown tests do.

The file must stand alone. It runs by itself, outside the project's test directory: import
every name it uses, and import only the standard library and the project's own packages --
never a test module, a conftest, or anything under a tests package. Helpers you were shown
from an existing test module are there to be copied into the file, not imported. When the
assertion is about log records, set the level first (``caplog.set_level(logging.INFO)``, or
whatever level the code logs at), or the records will be absent for the wrong reason."""

SITECUSTOMIZE = """import _thread
import os
import socket
import sys
import threading
import traceback
from pathlib import Path

_PROCESS_EVENTS = {
    "os.fork",
    "os.forkpty",
    "os.posix_spawn",
    "os.spawn",
    "os.system",
    "pty.spawn",
    "subprocess.Popen",
}
_PROCESS_REPLACEMENT_EVENTS = {"os.exec"}
_PROCESS_SYMBOLS = {
    "clone",
    "clone3",
    "fork",
    "posix_spawn",
    "posix_spawnp",
    "popen",
    "system",
    "vfork",
}
_PROCESS_REPLACEMENT_SYMBOLS = {
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execveat",
    "execvp",
    "execvpe",
    "fexecve",
    "syscall",
}
_NETWORK_EVENTS = {"socket.connect"}
# owner fix 3 (2026-09-03): the tree under test is the only import root for its
# own packages -- ahead of site-packages (an editable install of the same
# name) and of anything the interpreter's environment prepends
_tree_paths = [
    entry for entry in os.environ.get("ATTEST_TREE_PATHS", "").split(os.pathsep) if entry
]
for _index, _entry in enumerate(_tree_paths):
    while _entry in sys.path:
        sys.path.remove(_entry)
    sys.path.insert(_index, _entry)
# the writable outputs mount is the only place the guard reports to; a missing
# mount fails closed, because no marker can then be written
_outputs = Path(os.environ["ATTEST_OUTPUTS"])
_network_marker = _outputs / "network-blocked"
_process_guard_marker = _outputs / "process-guarded"
_process_containment_marker = _outputs / "process-contained"
_process_attempt_marker = _outputs / "process-attempted"
_process_replacement_marker = _outputs / "process-replacement-attempted"
_thread_attempt_marker = _outputs / "thread-attempted"
_network_attempt_marker = _outputs / "network-attempted"
_write_attempt_marker = _outputs / "write-attempted"
_PROCESS_GUARD_PROBE = "attest.process_guard_probe"
# X-02: the writable set is the outputs mount, the scratch/tmp areas and the
# reproduction's own directory; a write anywhere else is an escape attempt
# and marks the run, whatever the OS then does with it
_writable_prefixes = tuple(
    os.path.realpath(entry)
    for entry in [
        str(_outputs),
        "/dev",  # device files (os.devnull) are not an escape
        *os.environ.get("ATTEST_WRITABLE", "").split(os.pathsep),
    ]
    if entry
)
_WRITE_MODES = set("wax+")


def _record_write_attempt(path, mode):
    if _write_attempt_marker.exists():
        return
    try:
        _write_attempt_marker.write_text(f"path={path!r}\\nmode={mode!r}\\n", encoding="utf-8")
    except OSError:
        pass


def _guard_writes(event, args):
    if event != "open" or len(args) < 2:
        return
    path, mode = args[0], args[1]
    if isinstance(path, int) or not isinstance(mode, str) or not (set(mode) & _WRITE_MODES):
        return
    try:
        real = os.path.realpath(os.fspath(path))
    except (TypeError, OSError):
        return
    if any(real == prefix or real.startswith(prefix + os.sep) for prefix in _writable_prefixes):
        return
    _record_write_attempt(real, mode)

def _record_process_attempt(event, args):
    if _process_attempt_marker.exists():
        return
    target = None
    if args:
        target = args[-1] if event in {"ctypes.dlsym", "ctypes.dlsym/handle"} else args[0]
    frames = traceback.extract_stack(limit=16)[:-2]
    stack = "\\n".join(
        f"{frame.filename}:{frame.lineno}:{frame.name}" for frame in frames
    )
    _process_attempt_marker.write_text(
        f"event={event}\\ntarget={target!r}\\nstack:\\n{stack}\\n",
        encoding="utf-8",
    )

if os.name == "posix":
    import resource
    if resource.getrlimit(resource.RLIMIT_NPROC) != (0, 0):
        raise RuntimeError("kernel process containment is inactive")
    _process_containment_marker.write_text("active", encoding="utf-8")

def _guard_operations(event, args):
    if event == _PROCESS_GUARD_PROBE:
        _process_guard_marker.write_text("active", encoding="utf-8")
        return
    if event in _NETWORK_EVENTS:
        if not _network_attempt_marker.exists():
            _network_attempt_marker.write_text("attempted", encoding="utf-8")
        raise PermissionError("network disabled by evidence executor")
    process_event = event in _PROCESS_EVENTS
    native_symbol = (
        event in {"ctypes.dlsym", "ctypes.dlsym/handle"}
        and args
        and args[-1] in _PROCESS_SYMBOLS
    )
    replacement_event = event in _PROCESS_REPLACEMENT_EVENTS
    replacement_symbol = (
        event in {"ctypes.dlsym", "ctypes.dlsym/handle"}
        and args
        and args[-1] in _PROCESS_REPLACEMENT_SYMBOLS
    )
    if replacement_event or replacement_symbol:
        _process_replacement_marker.write_text("attempted", encoding="utf-8")
        raise PermissionError("process replacement disabled by evidence executor")
    if not process_event and not native_symbol:
        return
    _record_process_attempt(event, args)
    if os.name != "posix":
        raise PermissionError("process creation disabled by evidence executor")

sys.addaudithook(_guard_operations)
sys.addaudithook(_guard_writes)
sys.audit(_PROCESS_GUARD_PROBE)

if os.name == "posix":
    def _reject_thread(*args, **kwargs):
        _thread_attempt_marker.write_text("attempted", encoding="utf-8")
        raise PermissionError("thread creation disabled by evidence executor")
    for _module, _names in (
        (_thread, ("start_new_thread", "start_joinable_thread")),
        (threading, ("_start_new_thread", "_start_joinable_thread")),
    ):
        for _name in _names:
            if hasattr(_module, _name):
                setattr(_module, _name, _reject_thread)

def _reject_connection(*args, **kwargs):
    if not _network_attempt_marker.exists():
        _network_attempt_marker.write_text("attempted", encoding="utf-8")
    raise PermissionError("network disabled by evidence executor")

socket.socket.connect = _reject_connection
socket.socket.connect_ex = _reject_connection
socket.create_connection = _reject_connection
_network_marker.write_text("active", encoding="utf-8")
"""


class ExecutionOutcome(str, Enum):  # noqa: UP042 - public API requires this exact base shape
    REPRODUCED = "reproduced"
    NOT_REPRODUCED = "not_reproduced"
    DEFERRED = "deferred"


class EvidenceClass(str, Enum):  # noqa: UP042 - public API requires this exact base shape
    """What the head/base pair actually showed. Only REGRESSION_REPRODUCED is
    priced today; NEW_CODE_CANDIDATE is recorded signal awaiting an owner
    decision on its LR (D-020), so it purchases nothing."""

    REGRESSION_REPRODUCED = "regression_reproduced"
    NEW_CODE_CANDIDATE = "new_code_candidate"
    UNFAITHFUL = "unfaithful"
    NOT_REPRODUCED = "not_reproduced"
    INDETERMINATE = "indeterminate"
    UNBOUND = "unbound"  # head failed, base passed, but no changed line ran (V-02)
    # D-102: head rejects an input the base accepted -- the failure was raised
    # from a raise/assert on a changed line; publishable only with a base-tree witness
    BEHAVIOR_CHANGE = "behavior_change"


class FailureSignature(str, Enum):  # noqa: UP042 - public API requires this exact base shape
    SYMBOL_ABSENT = "symbol_absent"
    ASSERTION = "assertion"
    OTHER = "other"


@dataclass(frozen=True)
class ExecutorLimits:
    wall_timeout_s: float = 60.0
    cpu_timeout_s: int = 30
    memory_mb: int = 1024
    output_bytes: int = 16_384


@dataclass(frozen=True)
class ReproSpec:
    test_body: str


@dataclass(frozen=True)
class ExecutionResult:
    outcome: ExecutionOutcome
    reason: str
    exit_code: int | None
    stdout: str
    stderr: str
    elapsed_s: float
    network_blocked: bool
    # JUnit-derived collection identity of a completed run; a deferred run
    # carries the zero defaults, which no certification receipt can accept.
    collected_count: int = 0
    skipped_count: int = 0
    xfailed_count: int = 0
    test_node: str = ""
    # exact execution identity (V-01): what ran, where, with what
    command_template: tuple[str, ...] = ()  # argv with tree/site paths as placeholders
    interpreter: str = ""
    interpreter_version: str = ""
    environment_digest: str = ""  # canonical digest of the guard-relevant environment
    test_file_digest: str = ""  # SHA-256 of the exact test bytes written for the run
    junit_xml: str = ""
    executed_lines: tuple[int, ...] = ()  # lines of the anchored file the run executed
    executor_profile: str = ""  # X-01: the adapter profile that ran it
    executor_digest: str = ""  # X-01: that adapter's backend digest
    # owner fix 3: modules that shadowed the anchored file (name, file), if any
    import_origins: tuple[tuple[str, str], ...] = ()
    fresh_state: bool = True  # V-03: the writable outputs directory was created empty
    # D-102: exceptions first seen in a frame of the anchored file, in order;
    # ``raise_origins_truncated`` says the tracer hit its record bound
    raise_origins: tuple[RaiseOrigin, ...] = ()
    raise_origins_truncated: bool = False
    failure_message: str = ""  # the JUnit failure message ("Type: text"), failed runs only


@dataclass(frozen=True)
class DifferentialExecution:
    head_runs: tuple[ExecutionResult, ...]
    base_runs: tuple[ExecutionResult, ...]
    outcome: ExecutionOutcome
    reason: str
    base_sha: str
    head_sha: str
    repeats: int
    elapsed_s: float
    network_blocked: bool  # every executed run confirmed the network guard
    evidence_class: EvidenceClass = EvidenceClass.INDETERMINATE
    collection_run: ExecutionResult | None = None  # the collect-only run (V-01)
    binding: BindingObservation | None = None  # changed-line binding (V-02)
    intent: IntentObservation | None = None  # regression or new rejection (D-102)


@dataclass(frozen=True)
class VerificationRun:
    execution: DifferentialExecution
    gate_result: GateResult
    spec: ReproSpec | None = None  # the generated test that was executed, if any


def _failure_point_markers(*exceptions: str) -> tuple[re.Pattern[str], ...]:
    """Only lines pytest emits *at* the point of failure: the reported exception
    detail ("E   AttributeError: ..."), the traceback location line, a raw
    interpreter traceback, or a collection-error header. Echoed source lines
    ("> with pytest.raises(NameError):") deliberately do not count."""
    alternation = "|".join(exceptions)
    return tuple(
        re.compile(pattern, re.MULTILINE)
        for pattern in (
            rf"^E\s+(?:{alternation})\b",
            rf"^.*:\d+: (?:{alternation})\s*$",
            rf"^(?:{alternation}):",
            rf"^(?:{alternation}) while importing test module",
        )
    )


# Exceptions that can mean nothing except *a name could not be resolved*: an
# import that found no module, or an unbound name.
_UNRESOLVED_NAME_MARKERS = _failure_point_markers("ModuleNotFoundError", "ImportError", "NameError")
# AttributeError is ambiguous. It is raised both when a definition is missing
# from a namespace (the D-029 rename: `module 'calc' has no attribute
# '_validate'`) and when the code under test produced a value of the wrong
# shape (`'NoneType' object has no attribute 'strip'`), which is the code
# misbehaving. The message says which, so it is read rather than the name.
#
# KeyError is deliberately absent from both lists. A mapping lookup is always a
# question about DATA -- the interpreter never reports an unresolved name as a
# KeyError -- so treating it as a missing symbol classified genuine defects
# ("head stopped supplying the default and now raises KeyError") as
# fabrications, and since certification requires the head code to misbehave,
# that silently blocked true findings from buying any evidence.
_AMBIGUOUS_NAME_MARKERS = _failure_point_markers("AttributeError")
_ATTRIBUTE_ERROR_DETAIL = re.compile(r"^(?:E\s+)?AttributeError: (?P<detail>.+)$", re.MULTILINE)
_INSTANCE_ATTRIBUTE_DETAIL = re.compile(r"^'(?P<type>[\w.]+)' object has no attribute")
# Namespaces the interpreter owns. No reviewed diff can add or remove an
# attribute on them, so a missing attribute here can only mean a value of the
# wrong type arrived -- never a symbol that used to exist.
_BUILTIN_VALUE_TYPES = frozenset(
    {
        "NoneType",
        "bool",
        "bytearray",
        "bytes",
        "complex",
        "dict",
        "float",
        "frozenset",
        "int",
        "list",
        "range",
        "set",
        "str",
        "tuple",
    }
)
_ASSERTION_MARKERS = tuple(
    re.compile(pattern, re.MULTILINE)
    for pattern in (
        r"^E\s+(?:assert\b|AssertionError\b)",
        r"^.*:\d+: AssertionError\s*$",
        r"^AssertionError\b",
    )
)


def _attribute_error_names_a_missing_definition(detail: str) -> bool:
    """Whether one AttributeError message is about a NAME the reviewed revision
    does not have, rather than about the shape of a value. Unrecognised messages
    stay conservative and count as a missing definition: erring that way defers,
    while erring the other way could certify a rename refactor."""
    if detail.startswith(("module ", "type object ")):
        return True
    instance = _INSTANCE_ATTRIBUTE_DETAIL.match(detail)
    if instance is not None:
        return instance.group("type") not in _BUILTIN_VALUE_TYPES
    return True


def classify_failure_signature(result: ExecutionResult) -> FailureSignature:
    """Why a run failed: a name the reproduction used could not be resolved, a
    real assertion fired, or neither. Deliberately conservative -- when both
    signatures appear the assertion wins, so a bogus test cannot hide behind an
    incidental resolution failure raised somewhere in the same output."""
    text = f"{result.stdout}\n{result.stderr}"
    if any(marker.search(text) for marker in _ASSERTION_MARKERS):
        return FailureSignature.ASSERTION
    if any(marker.search(text) for marker in _UNRESOLVED_NAME_MARKERS):
        return FailureSignature.SYMBOL_ABSENT
    if any(marker.search(text) for marker in _AMBIGUOUS_NAME_MARKERS):
        details = [
            match.group("detail").strip() for match in _ATTRIBUTE_ERROR_DETAIL.finditer(text)
        ]
        # no message at all (a bare location line): stay conservative
        if not details or any(
            _attribute_error_names_a_missing_definition(detail) for detail in details
        ):
            return FailureSignature.SYMBOL_ABSENT
    return FailureSignature.OTHER


def _no_run_reports_the_symbol_absent(runs: list[ExecutionResult]) -> bool:
    """True when not one of these runs failed because the symbol under test was
    missing. Used on the head side, where every run is already a genuine test
    failure, to separate *the code misbehaved* from *the symbol was never
    there*."""
    return all(
        classify_failure_signature(run) is not FailureSignature.SYMBOL_ABSENT for run in runs
    )


def _anchor_context(repo: Path, candidate: StoredCandidate) -> str:
    repo_root = repo.resolve()
    path = (repo_root / candidate.finding.file).resolve()
    try:
        path.relative_to(repo_root)
    except ValueError:
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    anchor_index = max(0, candidate.finding.line - 1)
    start = max(0, anchor_index - MAX_CONTEXT_LINES // 2)
    start = min(start, max(0, len(lines) - MAX_CONTEXT_LINES))
    return "\n".join(lines[start : start + MAX_CONTEXT_LINES])


def _generation_prompt(repo: Path, candidate: StoredCandidate, base_ref: str | None = None) -> str:
    finding = candidate.finding
    context = ""
    if base_ref is not None:
        context = generation_context(repo, base_ref, finding.file, finding.line)
    return (
        f"Claim: {finding.claim}\n"
        f"Failure scenario: {finding.failure_scenario}\n"
        f"Falsification plan: {finding.falsification_plan}\n"
        f"Anchor: {finding.file}:{finding.line}\n\n"
        + (f"{context}\n\n" if context else "")
        + "Anchor window (head):\n"
        f"{_anchor_context(repo, candidate)}"
    )


def imported_test_modules(source: str) -> tuple[str, ...]:
    """Test modules the generated reproduction imports, sorted.

    D-114: the reproduction runs from its own directory, outside the project's
    test tree, so an import of a test module, a conftest or a tests package
    cannot resolve there -- the file must carry its helpers itself. A source
    that does not parse yields no names; the collection gate answers for it.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return ()
    dotted: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            dotted.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            dotted.append(node.module)
    return tuple(sorted({name for name in dotted if _names_a_test_module(name)}))


def _names_a_test_module(dotted: str) -> bool:
    return any(
        part == "conftest" or part == "tests" or part.startswith("test_") or part.endswith("_test")
        for part in dotted.split(".")
    )


class GenerationNoText(ValueError):
    """The model answered without a text block: nothing to parse, and never a
    schema mismatch (owner fix 1, 2026-09-03)."""


def _parse_repro(text: str) -> ReproSpec:
    stripped = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fenced is not None:
        stripped = fenced.group(1)
    try:
        payload = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"generator output is not valid JSON; raw={response_fragment(text)}"
        ) from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"test_body"}
        or not isinstance(payload["test_body"], str)
    ):
        raise ValueError(
            "generator output does not match the reproduction schema; "
            f"raw={response_fragment(text)}"
        )
    return ReproSpec(test_body=payload["test_body"])


# The V-02 line tracer costs one Python call per frame while installed, so it
# is a pytest plugin that installs itself for the reproduction window only --
# setup, call and teardown of the one collected item -- and never for pytest's
# bootstrap, collection or the imports they trigger. Loaded with ``-p``; the
# guard sitecustomize stays tracer-free.
_LINES_PLUGIN = """import json
import os
import sys
import threading
from pathlib import Path

import pytest

_trace_target = os.path.realpath(os.environ["ATTEST_TRACE_TARGET"])
_lines_marker = Path(os.environ["ATTEST_OUTPUTS"]) / "executed-lines"
_origin_marker = Path(os.environ["ATTEST_OUTPUTS"]) / "import-origin"
_raise_marker = Path(os.environ["ATTEST_OUTPUTS"]) / "raise-origin"
_executed_lines = set()
_matches = {}
_raise_origins = []  # recorded exception origins, in order
_origin_index = {}  # id(exception) -> index into _raise_origins
_seen_exceptions = {}  # id(exception) -> the object (kept alive so ids stay unique)
_signatures = set()  # exact-duplicate suppression
_pending = {}  # id(frame) -> id(exception) currently propagating through that frame
_caught = set()  # ids of exceptions handled inside a frame of the anchored file
_truncated = False
MAX_RAISE_ORIGINS = 256
MAX_SEEN_EXCEPTIONS = 4096
MAX_MESSAGE_CHARS = 1000
MAX_VALUE_CHARS = 300
MAX_VALUES = 12


def _clean(text):
    # lone surrogates (os.fsdecode of undecodable bytes) must not break the
    # artifact write: replace them, never raise inside the hook
    return text.encode("utf-8", "replace").decode("utf-8")


def _string_values(frame):
    values = []
    try:
        items = list(frame.f_locals.items())
    except Exception:
        return values
    for _name, value in items:
        if isinstance(value, str):
            values.append(_clean(value[:MAX_VALUE_CHARS]))
            if len(values) >= MAX_VALUES:
                break
    return values


def _record_exception(frame, arg):
    # The first exception event for one exception object is the innermost
    # frame of the anchored file it passed through (only anchored frames are
    # traced). Every later event for the same object marks propagation into
    # another anchored frame. A frame that runs a line after the event has
    # handled the exception; a frame that returns right after it let it out.
    global _truncated
    if not isinstance(arg, tuple) or len(arg) != 3:
        return
    exc_type, exc_value, _tb = arg
    key = id(exc_value)
    _pending[id(frame)] = key
    if key in _seen_exceptions:
        return
    if len(_seen_exceptions) >= MAX_SEEN_EXCEPTIONS:
        _truncated = True
        return
    _seen_exceptions[key] = exc_value
    try:
        message = _clean(str(exc_value)[:MAX_MESSAGE_CHARS])
    except Exception:
        message = ""
    record = {
        "line": frame.f_lineno,
        "function": frame.f_code.co_name,
        "exception_type": getattr(exc_type, "__name__", str(exc_type)),
        "message": message,
        "values": _string_values(frame),
        "exception_id": key,
    }
    signature = (record["line"], record["exception_type"], message, tuple(record["values"]))
    if signature in _signatures:
        return
    if len(_raise_origins) >= MAX_RAISE_ORIGINS:
        _truncated = True
        return
    _signatures.add(signature)
    _origin_index[key] = len(_raise_origins)
    _raise_origins.append(record)


def _write_raise_origins():
    origins = []
    for record in _raise_origins:
        row = dict(record)
        key = row.pop("exception_id")
        row["escaped"] = key not in _caught
        origins.append(row)
    payload = {"origins": origins, "truncated": _truncated}
    try:
        text = json.dumps(payload, ensure_ascii=True)
    except Exception as exc:
        text = json.dumps({"origins": [], "truncated": True, "error": type(exc).__name__})
    _raise_marker.write_text(text, encoding="utf-8")


def _expected_module_names():
    # the dotted names under which the anchored file is importable from the
    # tree's import roots (ATTEST_TREE_PATHS); a module of another name that
    # merely shares the file's basename (stdlib ``logging`` beside
    # ``_pytest/logging.py``) is not a shadow
    names = set()
    for root in os.environ.get("ATTEST_TREE_PATHS", "").split(os.pathsep):
        if not root:
            continue
        root = os.path.realpath(root)
        if not _trace_target.startswith(root + os.sep):
            continue
        relative = _trace_target[len(root) + 1 :]
        if relative.endswith(os.sep + "__init__.py"):
            relative = relative[: -len(os.sep + "__init__.py")]
        elif relative.endswith(".py"):
            relative = relative[:-3]
        names.add(relative.replace(os.sep, "."))
    return names


def _record_import_origin():
    # every loaded module whose dotted name is one the anchored file answers
    # to, but whose file is a different one: the anchored module was shadowed.
    # Without a known import root the basename rule is the fallback.
    lines = []
    expected = _expected_module_names()
    for name, module in list(sys.modules.items()):
        file = getattr(module, "__file__", None)
        if not isinstance(file, str) or not file:
            continue
        if expected:
            if name not in expected:
                continue
        else:
            as_path = name.replace(".", os.sep)
            tails = (os.sep + as_path + ".py", os.sep + as_path + os.sep + "__init__.py")
            if not any(_trace_target.endswith(tail) for tail in tails):
                continue
        real = os.path.realpath(file)
        if real != _trace_target:
            lines.append(name + "\\t" + real)
    _origin_marker.write_text("\\n".join(lines), encoding="utf-8")


def _attest_tracer(frame, event, arg):
    filename = frame.f_code.co_filename
    match = _matches.get(filename)
    if match is None:
        match = filename == _trace_target or os.path.realpath(filename) == _trace_target
        _matches[filename] = match
    if not match:
        return None
    if event == "line":
        _executed_lines.add(frame.f_lineno)
        handled = _pending.pop(id(frame), None)
        if handled is not None:
            _caught.add(handled)
    elif event == "exception":
        _record_exception(frame, arg)
    elif event == "return":
        _pending.pop(id(frame), None)
    return _attest_tracer


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_protocol(item, nextitem):
    sys.settrace(_attest_tracer)
    threading.settrace(_attest_tracer)
    try:
        yield
    finally:
        sys.settrace(None)
        threading.settrace(None)
        _lines_marker.write_text(
            ",".join(str(n) for n in sorted(_executed_lines)), encoding="utf-8"
        )
        try:
            _write_raise_origins()
        except Exception:
            pass
        _record_import_origin()
"""
LINES_PLUGIN_NAME = "attest_repro_lines"


def generate_repro(
    repo: Path,
    candidate: StoredCandidate,
    provider: Provider,
    budget: Budget,
    *,
    timeout_s: float | None = None,
    base_ref: str | None = None,
    shared_system: str = "",
) -> ReproSpec:
    prompt = _generation_prompt(repo, candidate, base_ref)
    labels = [
        f"verify-{candidate.finding.finding_id}-attempt-{attempt}"
        for attempt in range(1, MAX_REPRO_ATTEMPTS + 1)
    ]
    reservations: list[float] = []
    try:
        for label in labels:
            reservations.append(
                budget.reserve(
                    label,
                    len(GENERATOR_SYSTEM) + len(prompt),
                    REPRO_MAX_OUTPUT_TOKENS,
                )
            )
    except Exception:
        for reservation in reservations:
            budget.cancel(reservation)
        raise

    last_schema_error: ValueError | None = None
    for index, (label, reservation) in enumerate(zip(labels, reservations, strict=True)):
        try:
            # the prompt is the shared prefix: the precommitted second attempt
            # reads the cache entry the first one wrote
            result = call_provider(
                provider,
                GENERATOR_SYSTEM,
                prompt,
                REPRO_SCHEMA,
                REPRO_MAX_OUTPUT_TOKENS,
                timeout_s=timeout_s,
                shared_prefix=prompt,
                shared_system=shared_system,
            )
        except Exception:
            for unused in reservations[index:]:
                budget.cancel(unused)
            raise
        budget.settle(
            label,
            reservation,
            result.input_tokens,
            result.output_tokens,
            cache_creation_input_tokens=result.cache_creation_input_tokens,
            cache_read_input_tokens=result.cache_read_input_tokens,
        )
        if result.text is None:
            # the honest reason travels as-is: stop reason and block types,
            # never a fabricated document reported as a schema mismatch
            last_schema_error = GenerationNoText(no_text_reason(result))
            continue
        try:
            spec = _parse_repro(result.text)
        except ValueError as exc:
            last_schema_error = exc
            continue
        imported = imported_test_modules(spec.test_body)
        if imported:
            # never written, never executed: a reproduction that borrows from
            # the project's test tree proves nothing about the diff
            last_schema_error = ValueError(
                "generated reproduction imports test module(s) "
                f"{', '.join(imported)}; it must be self-contained"
            )
            continue
        for unused in reservations[index + 1 :]:
            budget.cancel(unused)
        return spec

    if last_schema_error is None:  # pragma: no cover - fixed positive attempt count
        raise RuntimeError("reproduction generation made no attempts")
    raise last_schema_error


def _truncate_output(output: bytes | str | None, limit: int) -> str:
    if output is None or limit <= 0:
        return ""
    encoded = output.encode("utf-8", errors="replace") if isinstance(output, str) else output
    return encoded[-limit:].decode("utf-8", errors="ignore")


def _append_guard_evidence(stderr: str, marker: bytes | None, limit: int) -> str:
    evidence = (
        marker.decode("utf-8", errors="replace")
        if marker
        else "process audit details were unavailable"
    )
    return _truncate_output(f"{stderr}\n[process audit]\n{evidence}", limit)


@dataclass(frozen=True)
class _JUnitSummary:
    failures: int
    errors: int
    collected: int
    skipped: int
    xfailed: int
    test_node: str
    failure_message: str = ""  # first <failure>/<error> message attribute, entity-decoded


def _junit_summary(data: bytes) -> _JUnitSummary:
    root = ET.fromstring(data)
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise ValueError("JUnit has no test suites")
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    cases = [case for suite in suites for case in suite.iter("testcase")]
    xfailed = sum(
        1
        for case in cases
        for skipped in case.iter("skipped")
        if skipped.attrib.get("type") == "pytest.xfail"
    )
    skipped = sum(int(suite.attrib.get("skipped", "0")) for suite in suites) - xfailed
    test_node = ""
    if len(cases) == 1:
        # the generated module is always test_repro.py; pytest's classname joins
        # path components with dots, so anchor on the module name rather than
        # re-splitting a run directory whose name itself contains a dot
        classname = cases[0].attrib.get("classname", "")
        name = cases[0].attrib.get("name", "")
        parts = classname.split(".")
        if "test_repro" in parts and name:
            module_index = len(parts) - 1 - parts[::-1].index("test_repro")
            test_node = "::".join(["test_repro.py", *parts[module_index + 1 :], name])
    failure_message = ""
    for case in cases:
        for tag in ("failure", "error"):
            for node in case.iter(tag):
                failure_message = " ".join(str(node.attrib.get("message", "")).split())[:2000]
                break
            if failure_message:
                break
        if failure_message:
            break
    return _JUnitSummary(
        failures=failures,
        errors=errors,
        collected=len(cases),
        skipped=skipped,
        xfailed=xfailed,
        test_node=test_node,
        failure_message=failure_message,
    )


def _executed_lines(marker: bytes | None) -> tuple[int, ...]:
    if not marker:
        return ()
    text = marker.decode("utf-8", errors="replace")
    return tuple(int(part) for part in text.split(",") if part.strip().isdigit())


def _changed_lines(repo: Path, base_sha: str, head_sha: str, path: str) -> tuple[int, ...]:
    """New-file lines inside the anchored file's hunks between base and head."""
    proc = subprocess.run(
        ["git", "-C", str(repo), "diff", "--no-color", base_sha, head_sha, "--", path],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if proc.returncode != 0:
        return ()
    ranges = parse_diff(proc.stdout).hunks.get(path, [])
    return tuple(sorted({line for start, end in ranges for line in range(start, end + 1)}))


def _junit_counts(data: bytes) -> tuple[int, int]:
    summary = _junit_summary(data)
    return summary.failures, summary.errors


def _deferred(
    reason: str,
    started: float,
    *,
    exit_code: int | None = None,
    stdout: str = "",
    stderr: str = "",
    network_blocked: bool = False,
) -> ExecutionResult:
    return ExecutionResult(
        outcome=ExecutionOutcome.DEFERRED,
        reason=reason,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        elapsed_s=time.monotonic() - started,
        network_blocked=network_blocked,
    )


def _safe_path_component(value: str) -> bool:
    return bool(value) and value not in {".", ".."} and "/" not in value and "\\" not in value


def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


MAX_JUNIT_CHARS = 64_000


def _environment_digest(environment: dict[str, str]) -> str:
    """Canonical digest of the whole explicit job environment (mounts are
    placeholders, so every run of a candidate on the same host agrees)."""
    return hashlib.sha256(
        json.dumps(environment, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


_COLLECT_COUNT_RE = re.compile(r"^(?P<path>\S+\.py): (?P<count>\d+)$")


def _single_test_function(source: str) -> str | None:
    """The one module-level test function in a generated file, else None."""
    try:
        tree = ast.parse(source)
    except (ValueError, SyntaxError, RecursionError):
        return None
    names = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test")
    ]
    return names[0] if len(names) == 1 else None


def _collected_nodes(stdout: str, source: str) -> tuple[int, str]:
    """(collected count, node id) from a collect-only run.

    pytest prints one node id per line under ``-q``; a project whose own
    configuration adds a second ``-q`` prints ``path: count`` instead. In that
    style the node name comes from the generated source, which by construction
    holds exactly one test function.
    """
    nodes = [
        line.strip()
        for line in stdout.splitlines()
        if "::" in line and not line.startswith(("=", " ", "<"))
    ]
    if nodes:
        node = nodes[0].split("/")[-1] if len(nodes) == 1 else ""
        return len(nodes), node
    matches = (_COLLECT_COUNT_RE.match(line) for line in stdout.splitlines())
    total = sum(int(m.group("count")) for m in matches if m)
    name = _single_test_function(source)
    return total, f"test_repro.py::{name}" if total == 1 and name else ""


@functools.lru_cache(maxsize=8)
def _interpreter_version(interpreter: str) -> str:
    """One probe per interpreter path per process; the receipt binds its text."""
    if interpreter == sys.executable:
        return sys.version
    try:
        probe = subprocess.run(
            [interpreter, "-c", "import sys; print(sys.version)"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return probe.stdout.strip() if probe.returncode == 0 else ""


_PROJECT_MARKERS = ("pyproject.toml", "setup.py", "setup.cfg")
_PROJECT_SKIP_DIRS = {
    ".git",
    ".attest",
    ".attest-repro",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".tox",
    ".nox",
}
MAX_PROJECT_ROOT_DEPTH = 4
MAX_PROJECT_ROOTS = 32


def project_roots(tree: Path) -> list[str]:
    """Placeholder-relative import roots of a tree: the tree and its ``src``,
    then every directory (bounded depth) holding a project marker and its
    ``src`` when present, so ``services/*/src`` layouts import from the tree
    under test rather than from an installed copy (owner fix 3)."""
    roots = ["{tree}", "{tree}/src"]
    found: list[str] = []
    for current, directories, files in os.walk(tree):
        rel = Path(current).relative_to(tree)
        depth = len(rel.parts)
        directories[:] = sorted(
            name
            for name in directories
            if name not in _PROJECT_SKIP_DIRS and not name.startswith(".")
        )
        if depth >= MAX_PROJECT_ROOT_DEPTH:
            directories[:] = []
        if depth == 0:
            continue
        if any(marker in files for marker in _PROJECT_MARKERS):
            found.append(rel.as_posix())
            if len(found) >= MAX_PROJECT_ROOTS:
                break
    for relative in found:
        roots.append(f"{{tree}}/{relative}")
        if (tree / relative / "src").is_dir():
            roots.append(f"{{tree}}/{relative}/src")
    # the projects' own test directories come last, the way pytest's prepend
    # import mode exposes them to the project's tests: a reproduction may then
    # import the helpers of the test module it imitates by module name
    for relative in ("", *found):
        tests_dir = tree / relative / "tests" if relative else tree / "tests"
        if tests_dir.is_dir():
            roots.append(f"{{tree}}/{relative}/tests" if relative else "{tree}/tests")
    return roots


def _reproduction_environment(
    *, in_tree: bool, traced: bool, anchored_file: str, roots: list[str] | None = None
) -> dict[str, str]:
    """The explicit, secret-free job environment. Nothing is inherited from the
    controller: the request names every variable, and the mounts are the
    placeholders the adapter resolves. Tree entries come first so the revision
    under test shadows any installed copy; the guard sitecustomize is resolved
    from the inputs mount via the remainder of the path scan (a tree-level
    shadow fails closed on markers). PYTHONPATH is necessary but not sufficient
    for import steering: pytest prepends the directories it collects from, so
    execute_repro also runs the reproduction from inside the tree with rootdir
    and confcutdir pinned there."""
    tree_entries = list(roots or ["{tree}", "{tree}/src"]) if in_tree else []
    entries = [*tree_entries, "{inputs}"]
    environment = {
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONSAFEPATH": "1",
        # no __pycache__ inside the revision under test: it would dirty the
        # worktree, and a cached test_repro of the same size written in the
        # same mtime second would otherwise be replayed instead of the
        # reproduction actually generated
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": os.pathsep.join(entries),
        "ATTEST_OUTPUTS": "{outputs}",
    }
    if tree_entries:
        environment["ATTEST_TREE_PATHS"] = os.pathsep.join(tree_entries)
    # the reproduction may write inside its own run directory and the host's
    # temporary directory (pytest's own tmp_path lives there); everything else
    # is an escape attempt the guard marks
    environment["ATTEST_WRITABLE"] = os.pathsep.join(["{tree}/" + RUN_DIR_NAME, "{scratch}"])
    if traced:
        environment["ATTEST_TRACE_TARGET"] = "{tree}/" + anchored_file
    return environment


def _linux_capabilities_override_process_limit() -> bool | None:
    try:
        status = Path("/proc/self/status").read_text(encoding="utf-8")
    except OSError:
        return None
    values: dict[str, int] = {}
    for line in status.splitlines():
        name, separator, value = line.partition(":")
        if separator and name in {"CapEff", "CapPrm"}:
            try:
                values[name] = int(value.strip(), 16)
            except ValueError:
                return None
    if set(values) != {"CapEff", "CapPrm"}:
        return None
    override_mask = (1 << CAP_SYS_ADMIN) | (1 << CAP_SYS_RESOURCE)
    return any(capabilities & override_mask for capabilities in values.values())


def _process_containment_unavailable_reason() -> str | None:
    if os.name != "posix":
        return None
    try:
        import resource
    except ImportError:
        return "process containment unavailable: resource limits are not supported"

    if not hasattr(resource, "RLIMIT_NPROC"):
        return "process containment unavailable: RLIMIT_NPROC is not supported"
    if os.getuid() == 0:
        return "process containment unavailable for privileged POSIX user"
    if sys.platform.startswith("linux"):
        privileged = _linux_capabilities_override_process_limit()
        if privileged is None:
            return "process containment unavailable: Linux capabilities could not be verified"
        if privileged:
            return "process containment unavailable: Linux capabilities override RLIMIT_NPROC"
    return None


MARKER_NAMES = (
    "network-blocked",
    "process-guarded",
    "process-contained",
    "process-attempted",
    "process-replacement-attempted",
    "thread-attempted",
    "network-attempted",
    "write-attempted",
)
EXPECTED_ARTIFACTS = (
    *MARKER_NAMES,
    "executed-lines",
    "import-origin",
    "raise-origin",
    "junit.xml",
    "stdout.txt",
    "stderr.txt",
)


def _import_origins(marker: bytes | None) -> tuple[tuple[str, str], ...]:
    if not marker:
        return ()
    origins = []
    for line in marker.decode("utf-8", errors="replace").splitlines():
        name, separator, file = line.partition("\t")
        if separator and name and file:
            origins.append((name, file))
    return tuple(origins)


_DEFAULT_ADAPTER: LocalDevelopmentAdapter | None = None


def _default_adapter() -> LocalDevelopmentAdapter:
    """One host adapter per process, so the interpreter version is probed once."""
    global _DEFAULT_ADAPTER
    if _DEFAULT_ADAPTER is None:
        _DEFAULT_ADAPTER = LocalDevelopmentAdapter()
    return _DEFAULT_ADAPTER


def execute_repro(
    repo: Path,
    candidate: StoredCandidate,
    spec: ReproSpec,
    limits: ExecutorLimits,
    *,
    tree: Path | None = None,
    run_label: str = "",
    node: str | None = None,
    collect_only: bool = False,
    revision_sha: str = "",
    controller: Controller | None = None,
    adapter: ExecutorAdapter | None = None,
) -> ExecutionResult:
    """One guarded pytest run through the controller/executor protocol (X-01).
    ``node`` selects the exact test function; with ``collect_only`` the run only
    collects and reports the node ids it found. The controller issues a nonced,
    content-addressed request, the adapter runs it, and everything below is
    read from artifacts the controller verified against that request."""
    started = time.monotonic()
    repo_root = repo.resolve()
    suffix = Path(candidate.finding.file).suffix.lower()
    if suffix != ".py":
        return _deferred(f"unsupported anchor language: {suffix or '<none>'}", started)
    if not isinstance(spec.test_body, str):
        return _deferred("malformed generator output: test_body must be a string", started)
    if not _safe_path_component(candidate.task_id):
        return _deferred("unsafe task identity", started)
    if run_label and not _safe_path_component(run_label):
        return _deferred("unsafe run label", started)
    containment_reason = _process_containment_unavailable_reason()
    if containment_reason is not None:
        return _deferred(containment_reason, started)
    interpreter = os.environ.get("ATTEST_PROJECT_PYTHON", sys.executable)
    if not Path(interpreter).is_file() or not os.access(interpreter, os.X_OK):
        return _deferred("reviewed-project Python interpreter is unavailable", started)

    work_dir = repo_root / ".attest" / "repro" / candidate.task_id / candidate.finding.finding_id
    if run_label:
        work_dir = work_dir / run_label
    generated_path = work_dir / "test_repro.py"
    # The reproduction is executed from inside the tree (see
    # _reproduction_environment): the revision under test becomes the only
    # import root while its own conftest.py is still honoured. Everything that
    # has to outlive the tree (the generated source, the request, the verified
    # artifacts) lives under work_dir.
    run_path = generated_path if tree is None else tree / RUN_DIR_NAME / "test_repro.py"
    traced = tree is not None and not collect_only
    active_adapter: ExecutorAdapter = adapter or _default_adapter()
    active_controller = controller or Controller(work_dir.parent if run_label else work_dir)
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        source = spec.test_body.rstrip("\n") + "\n"
        generated_path.write_text(source, encoding="utf-8")
        if run_path != generated_path:
            # not parents=True: a missing tree must fail here rather than be
            # conjured into existence and then run as an empty revision
            run_path.parent.mkdir(exist_ok=True)
            run_path.write_text(source, encoding="utf-8")
        inputs: dict[str, bytes] = {
            "sitecustomize.py": SITECUSTOMIZE.encode("utf-8"),
            "test_repro.py": source.encode("utf-8"),
        }
        if traced:
            inputs[f"{LINES_PLUGIN_NAME}.py"] = _LINES_PLUGIN.encode("utf-8")
        selector = str(generated_path) if tree is None else f"{{tree}}/{RUN_DIR_NAME}/test_repro.py"
        if node is not None:
            selector = f"{selector}::{node}"
        argv = [interpreter, "-m", "pytest", "-q", selector]
        if collect_only:
            argv.append("--collect-only")
        if tree is not None:
            argv += [
                # rootdir also anchors conftest discovery, so both are pinned to
                # the tree: no conftest above it may be loaded, and loading one
                # is what would otherwise prepend the other revision's directory
                "--rootdir",
                "{tree}",
                "--confcutdir",
                "{tree}",
                # never write a .pytest_cache into the revision under test
                "-p",
                "no:cacheprovider",
            ]
        if traced:
            argv += ["-p", LINES_PLUGIN_NAME]
        if not collect_only:
            argv += ["--junitxml", "{outputs}/junit.xml"]
        environment = _reproduction_environment(
            in_tree=tree is not None,
            traced=traced,
            anchored_file=candidate.finding.file,
            roots=None if tree is None else project_roots(tree),
        )
        job_interpreter, interpreter_version = active_adapter.interpreter_identity(interpreter)
        identity: dict[str, Any] = {
            "executed_lines": (),  # filled after the run from the verified marker
            "command_template": tuple([job_interpreter, *argv[1:]]),
            "interpreter": job_interpreter,
            "interpreter_version": interpreter_version,
            "environment_digest": _environment_digest(environment),
            "test_file_digest": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "executor_profile": active_adapter.profile,
            "executor_digest": active_adapter.backend_digest(),
            "import_origins": (),
            "fresh_state": True,
            "raise_origins": (),
            "raise_origins_truncated": False,
        }
        request = active_controller.issue(
            task_id=candidate.task_id,
            run_id=run_label or "run",
            candidate_id=candidate.finding.finding_id,
            revision_sha=revision_sha,
            profile=active_adapter.profile,
            interpreter=interpreter,
            argv_template=argv,
            environment=environment,
            inputs=inputs,
            limits=ResourceLimits(
                wall_timeout_s=limits.wall_timeout_s,
                cpu_timeout_s=limits.cpu_timeout_s,
                memory_mb=limits.memory_mb,
                output_bytes=limits.output_bytes,
            ),
            expected_artifacts=EXPECTED_ARTIFACTS,
        )
        dispatched = active_controller.dispatch(
            request, active_adapter, tree=repo_root if tree is None else tree, inputs=inputs
        )
    except Exception as exc:  # noqa: BLE001 - infrastructure failures are ternary DEFER
        return _deferred(f"executor failure: {type(exc).__name__}: {exc}", started)

    if not dispatched.accepted or dispatched.envelope is None:
        return _deferred(f"executor result rejected: {dispatched.reason}", started)
    envelope = dispatched.envelope
    artifacts = dispatched.artifacts
    identity["fresh_state"] = dispatched.fresh_state
    stdout = _truncate_output(artifacts.get("stdout.txt"), limits.output_bytes)
    stderr = _truncate_output(artifacts.get("stderr.txt"), limits.output_bytes)
    network_blocked = "network-blocked" in artifacts
    if envelope.timed_out:
        return _deferred(
            f"reproduction timed out after {limits.wall_timeout_s:g}s",
            started,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if envelope.error:
        return _deferred(
            f"executor failure: {envelope.error}",
            started,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if envelope.exit_code is None:
        return _deferred("executor failure: process was not started", started)
    exit_code = envelope.exit_code
    process_guarded = "process-guarded" in artifacts
    process_contained = os.name != "posix" or "process-contained" in artifacts
    if not process_guarded:
        return _deferred(
            "process guard did not initialize",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if not process_contained:
        return _deferred(
            "kernel process containment did not initialize",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if "process-replacement-attempted" in artifacts:
        return _deferred(
            "reproduction attempted to replace the pytest process",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if "process-attempted" in artifacts:
        return _deferred(
            "reproduction attempted to create a child process",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=_append_guard_evidence(
                stderr, artifacts.get("process-attempted"), limits.output_bytes
            ),
            network_blocked=network_blocked,
        )
    if "thread-attempted" in artifacts:
        return _deferred(
            "reproduction attempted to create a thread",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if "network-attempted" in artifacts:
        return _deferred(
            "reproduction attempted a network connection",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if "write-attempted" in artifacts:
        return _deferred(
            "reproduction attempted to write outside its work directory",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=_append_guard_evidence(
                stderr, artifacts.get("write-attempted"), limits.output_bytes
            ),
            network_blocked=network_blocked,
        )
    if not network_blocked:
        return _deferred(
            "network guard did not initialize",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
        )
    if collect_only:
        if exit_code != 0:
            return _deferred(
                "pytest collection/import/syntax or infrastructure failure during "
                f"collection (exit code {exit_code})",
                started,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                network_blocked=network_blocked,
            )
        collected, node_id = _collected_nodes(stdout, source)
        return ExecutionResult(
            outcome=ExecutionOutcome.NOT_REPRODUCED,
            reason=f"collected {collected} node(s)",
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            elapsed_s=time.monotonic() - started,
            network_blocked=network_blocked,
            collected_count=collected,
            test_node=node_id,
            **identity,
        )
    identity["executed_lines"] = _executed_lines(artifacts.get("executed-lines"))
    identity["import_origins"] = _import_origins(artifacts.get("import-origin"))
    raise_record = parse_raise_record(artifacts.get("raise-origin"))
    identity["raise_origins"] = raise_record.origins
    identity["raise_origins_truncated"] = raise_record.truncated
    junit_bytes = artifacts.get("junit.xml")
    try:
        if junit_bytes is None:
            raise ValueError("no JUnit artifact")
        junit = _junit_summary(junit_bytes)
        failures, errors = junit.failures, junit.errors
        # decode only the bounded prefix: the artifact may be megabytes of
        # captured output and the receipt keeps at most MAX_JUNIT_CHARS
        junit_text = junit_bytes[: MAX_JUNIT_CHARS * 4].decode("utf-8", errors="replace")[
            :MAX_JUNIT_CHARS
        ]
    except (ET.ParseError, TypeError, ValueError) as exc:
        return _deferred(
            f"missing or malformed JUnit evidence: {type(exc).__name__}: {exc}",
            started,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )

    if exit_code == 0:
        return ExecutionResult(
            outcome=ExecutionOutcome.NOT_REPRODUCED,
            reason="pytest passed",
            exit_code=0,
            stdout=stdout,
            stderr=stderr,
            elapsed_s=time.monotonic() - started,
            network_blocked=network_blocked,
            collected_count=junit.collected,
            skipped_count=junit.skipped,
            xfailed_count=junit.xfailed,
            test_node=junit.test_node,
            junit_xml=junit_text,
            **identity,
        )
    if exit_code == 1 and failures > 0 and errors == 0:
        return ExecutionResult(
            outcome=ExecutionOutcome.REPRODUCED,
            reason=f"pytest reported {failures} failure(s) and 0 error(s)",
            exit_code=1,
            stdout=stdout,
            stderr=stderr,
            elapsed_s=time.monotonic() - started,
            network_blocked=network_blocked,
            collected_count=junit.collected,
            skipped_count=junit.skipped,
            xfailed_count=junit.xfailed,
            test_node=junit.test_node,
            junit_xml=junit_text,
            failure_message=junit.failure_message,
            **identity,
        )
    return _deferred(
        "pytest collection/import/syntax or infrastructure failure "
        f"(exit code {exit_code}, {failures} failure(s), {errors} error(s))",
        started,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        network_blocked=network_blocked,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=GIT_TIMEOUT_S,
    )


def _resolve_commit(repo: Path, ref: str) -> str | None:
    try:
        resolved = _git(repo, "rev-parse", "--verify", f"{ref}^{{commit}}")
    except (OSError, subprocess.SubprocessError):
        return None
    return resolved.stdout.strip() if resolved.returncode == 0 else None


def _working_tree_clean(repo: Path) -> bool:
    try:
        status = _git(repo, "status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.SubprocessError):
        return False
    return status.returncode == 0 and not status.stdout.strip()


def _bounded_reason(reason: str) -> str:
    if len(reason) <= MAX_REASON_CHARS:
        return reason
    return reason[: MAX_REASON_CHARS - 3] + "..."


DEADLINE_REASON = "shared verification deadline exceeded during differential execution"
NEW_CODE_REASON = (
    "new-code candidate: reproduction fails on head and the symbol is absent on base; not priced"
)
STALE_REFERENCE_REASON = (
    "unfaithful generated test: it references a symbol absent from head, "
    "so its head failure is a stale reference rather than a defect"
)


def execute_differential(
    repo: Path,
    candidate: StoredCandidate,
    spec: ReproSpec,
    limits: ExecutorLimits,
    *,
    base_sha: str,
    head_sha: str,
    repeats: int = 3,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    adapter: ExecutorAdapter | None = None,
    regenerate: Callable[[], ReproSpec] | None = None,
) -> DifferentialExecution:
    """Run the same reproduction repeatedly against detached head/base
    worktrees. Only a deterministic head failure that shows the code
    misbehaving -- never merely reporting the symbol absent -- paired with a
    deterministic base pass counts as REPRODUCED; every other pattern is
    DEFERRED (flaky or
    unfaithful evidence must never purchase V). Every result also carries an
    evidence class, which describes what was seen without pricing it: a
    new-code candidate is recorded and still DEFERRED."""
    started = time.monotonic()
    repo_root = repo.resolve()
    head_runs: list[ExecutionResult] = []
    base_runs: list[ExecutionResult] = []

    collection_runs: list[ExecutionResult] = []
    bindings: list[BindingObservation] = []
    intents: list[IntentObservation] = []

    def finish(
        outcome: ExecutionOutcome,
        reason: str,
        evidence_class: EvidenceClass = EvidenceClass.INDETERMINATE,
    ) -> DifferentialExecution:
        runs = (*head_runs, *base_runs)
        return DifferentialExecution(
            head_runs=tuple(head_runs),
            base_runs=tuple(base_runs),
            outcome=outcome,
            reason=reason,
            base_sha=base_sha,
            head_sha=head_sha,
            repeats=repeats,
            elapsed_s=time.monotonic() - started,
            network_blocked=bool(runs) and all(run.network_blocked for run in runs),
            evidence_class=evidence_class,
            collection_run=collection_runs[-1] if collection_runs else None,
            binding=bindings[0] if bindings else None,
            intent=intents[0] if intents else None,
        )

    def deferred(
        reason: str, evidence_class: EvidenceClass = EvidenceClass.INDETERMINATE
    ) -> DifferentialExecution:
        return finish(ExecutionOutcome.DEFERRED, _bounded_reason(reason), evidence_class)

    node: str | None = None
    candidate_root = (
        repo_root / ".attest" / "repro" / candidate.task_id / candidate.finding.finding_id
    )
    # one controller for the whole differential: every run gets its own nonce
    # and a result can only ever answer the request it was issued for
    controller = Controller(candidate_root)
    revisions = {
        "head": _resolve_commit(repo_root, head_sha) or "",
        "base": _resolve_commit(repo_root, base_sha) or "",
    }

    def run_once(
        side: str, index: int, tree: Path, *, collect_only: bool = False
    ) -> ExecutionResult | None:
        """One containment-guarded run against `tree`; None when the shared
        deadline is exhausted."""
        effective = limits
        if deadline is not None:
            remaining = deadline - clock()
            if remaining <= 0:
                return None
            effective = replace(limits, wall_timeout_s=min(limits.wall_timeout_s, remaining))
        if collect_only:
            label = "collect" if index == 0 else f"collect-{index}"
        else:
            label = f"{side}-{index}"
        return execute_repro(
            repo_root,
            candidate,
            spec,
            effective,
            tree=tree,
            run_label=label,
            node=node,
            collect_only=collect_only,
            revision_sha=revisions.get(side, revisions["head"]),
            controller=controller,
            adapter=adapter,
        )

    if repeats < 1:
        return deferred("differential execution requires at least one run")
    if not _safe_path_component(candidate.task_id):
        return deferred("unsafe task identity")
    if deadline is not None and deadline - clock() <= 0:
        return deferred(DEADLINE_REASON)
    trees_dir = (
        repo_root / ".attest" / "repro" / candidate.task_id / candidate.finding.finding_id / "trees"
    )
    created: list[Path] = []
    try:
        trees_dir.mkdir(parents=True, exist_ok=True)
        for side, sha in (("head", head_sha), ("base", base_sha)):
            try:
                added = _git(repo_root, "worktree", "add", "--detach", str(trees_dir / side), sha)
            except (OSError, subprocess.SubprocessError) as exc:
                return deferred(f"could not create {side} worktree: {type(exc).__name__}")
            if added.returncode != 0:
                return deferred(f"could not create {side} worktree: {added.stderr.strip()}")
            created.append(trees_dir / side)

        # V-01: collect first, under the same guards, and demand exactly one
        # node; every behavioural run then selects that node explicitly.
        # D-114: a file that does not collect is a scaffolding failure, not
        # evidence about the diff, so the generator is asked again before any
        # behavioural run is bought.
        rounds = 1 if regenerate is None else 1 + COLLECTION_REGENERATIONS
        collected: ExecutionResult | None = None
        failures: list[str] = []
        for round_index in range(rounds):
            if round_index:
                try:
                    spec = regenerate()  # type: ignore[misc]
                except Exception as exc:  # noqa: BLE001 - budget/deadline/provider
                    return deferred(
                        f"{failures[-1]}; regeneration failed: {type(exc).__name__}: {exc}"
                    )
            collection = run_once("collect", round_index, trees_dir / "head", collect_only=True)
            if collection is None:
                return deferred(DEADLINE_REASON)
            collection_runs.append(collection)
            if collection.outcome is ExecutionOutcome.DEFERRED:
                failures.append(f"collection deferred: {collection.reason}")
                continue
            if collection.collected_count != 1 or not collection.test_node:
                failures.append(
                    f"collection produced {collection.collected_count} test node(s); "
                    "exactly one is required"
                )
                continue
            collected = collection
            break
        if collected is None or not collected.test_node:
            suffix = "" if len(failures) < 2 else f" (after {len(failures)} generations)"
            return deferred(f"{failures[-1]}{suffix}")
        node = collected.test_node.split("::", 1)[1]
        for index in range(1, repeats + 1):
            run = run_once("head", index, trees_dir / "head")
            if run is None:
                return deferred(DEADLINE_REASON)
            head_runs.append(run)
            if run.outcome is ExecutionOutcome.DEFERRED:
                return deferred(f"head run {index}/{repeats} deferred: {run.reason}")
        # owner fix 3: a head run that imported the anchored module from
        # outside the tree proves nothing about the tree; it is recorded as
        # shadowed, never as "passed on head"
        for run in head_runs:
            for name, origin in run.import_origins:
                return deferred(
                    f"binding: the anchored module {name} was imported from outside the "
                    f"head tree ({origin})",
                    EvidenceClass.UNBOUND,
                )
        head_failures = sum(1 for run in head_runs if run.outcome is ExecutionOutcome.REPRODUCED)
        if head_failures == 0:
            return finish(
                ExecutionOutcome.NOT_REPRODUCED,
                f"pytest passed on head in {repeats}/{repeats} runs; base not executed",
                EvidenceClass.NOT_REPRODUCED,
            )
        if head_failures < repeats:
            return deferred(f"flaky reproduction on head ({head_failures}/{repeats} runs failed)")
        # Head runs only reach this point as genuine test failures (exit 1,
        # failures > 0, errors == 0), so the head signature distinguishes *the
        # code misbehaved* -- an assertion OR a real crash such as
        # ZeroDivisionError, TypeError or IndexError -- from *the symbol was
        # never there*. Demanding an assertion misclassified the common case,
        # because most real bug reproductions crash rather than assert. The
        # fabrication guard is unchanged and still load-bearing: a reproduction
        # naming a symbol that exists nowhere fails on HEAD with SYMBOL_ABSENT,
        # so it can never be classified as new code. This condition gates BOTH
        # base outcomes below -- the unpriced new-code class and certification
        # alike -- because both must first establish that the code misbehaved.
        head_symbol_is_present = _no_run_reports_the_symbol_absent(head_runs)

        for index in range(1, repeats + 1):
            run = run_once("base", index, trees_dir / "base")
            if run is None:
                return deferred(DEADLINE_REASON)
            base_runs.append(run)
            if run.outcome is ExecutionOutcome.NOT_REPRODUCED:
                continue
            if (
                head_symbol_is_present
                and classify_failure_signature(run) is FailureSignature.SYMBOL_ABSENT
            ):
                # the reviewed diff added the symbol: real signal, but pricing it
                # needs an LR that only the owner may introduce (D-020)
                return deferred(NEW_CODE_REASON, EvidenceClass.NEW_CODE_CANDIDATE)
            if run.outcome is ExecutionOutcome.DEFERRED:
                return deferred(f"base run {index}/{repeats} deferred: {run.reason}")
            return deferred(
                "unfaithful generated test: fails on base as well", EvidenceClass.UNFAITHFUL
            )
        # Every base run passed. That alone is NOT enough to certify: the same
        # head-side condition the new-code class already demands must hold here
        # too, and for the same reason. Read the four quadrants together --
        #   head absent + base absent  -> unfaithful (fails on both trees)
        #   head present + base absent -> the new-code case, recorded unpriced
        #   head present + base pass   -> the regression this channel prices
        #   head absent  + base pass   -> a stale/moved/renamed reference: the
        #       reproduction names something the reviewed revision no longer
        #       has, so the head failure says nothing about behaviour. Without
        #       this branch a pure rename refactor certifies and buys V.
        # -- and one invariant covers all four: the head runs must show the code
        # MISBEHAVING before anything is bought.
        if not head_symbol_is_present:
            return deferred(STALE_REFERENCE_REASON, EvidenceClass.UNFAITHFUL)
        # V-02: the failing head runs must have executed the changed code
        changed = _changed_lines(repo_root, base_sha, head_sha, candidate.finding.file)
        executed_on_every_head_run = set(changed)
        for run in head_runs:
            executed_on_every_head_run &= set(run.executed_lines)
        binding = BindingObservation(
            policy_version=BINDING_POLICY_VERSION,
            path=candidate.finding.file,
            changed_lines=changed,
            executed_changed_lines=tuple(sorted(executed_on_every_head_run)),
            head_runs_observed=len(head_runs),
        )
        bindings.append(binding)
        verdict = binding_verdict(binding)
        if verdict is not None:
            return deferred(f"binding: {verdict}", EvidenceClass.UNBOUND)
        # D-102: a failure raised by a raise/assert on a changed line of the
        # anchored file is a new rejection, not a regression. It publishes as a
        # behavior change only when the rejected input -- a literal of the
        # generated test that reached the raising frame -- occurs verbatim in
        # the base tree's tests, fixtures or documentation; otherwise it goes
        # to the drawer with the label "behavior change confirmed, intent unknown".
        try:
            head_source = (trees_dir / "head" / candidate.finding.file).read_text(
                encoding="utf-8", errors="replace"
            )
        except OSError:
            head_source = ""
        observed = observe_intent(
            path=candidate.finding.file,
            changed_lines=changed,
            head_source=head_source,
            test_source=spec.test_body,
            head_origins=[run.raise_origins for run in head_runs],
            head_failures=[run.failure_message for run in head_runs],
            truncated=any(run.raise_origins_truncated for run in head_runs),
            base_tree=trees_dir / "base",
        )
        if isinstance(observed, str):
            return deferred(f"intent: {observed}")
        intents.append(observed)
        differential = f"head FAIL {repeats}/{repeats}, base PASS {repeats}/{repeats}"
        if observed.new_rejection:
            intent_reason = intent_verdict(observed)
            if intent_reason is not None:
                return deferred(f"intent: {intent_reason}", EvidenceClass.BEHAVIOR_CHANGE)
            literal, witness = observed.witnesses[0]
            return finish(
                ExecutionOutcome.REPRODUCED,
                f"{differential}; behavior change: head raises {observed.exception_type} "
                f"from a changed line ({observed.path}:{observed.origin_line}) on "
                f"{literal!r}, an input present in the base tree at {witness}",
                EvidenceClass.BEHAVIOR_CHANGE,
            )
        return finish(
            ExecutionOutcome.REPRODUCED, differential, EvidenceClass.REGRESSION_REPRODUCED
        )
    finally:
        for tree in created:
            with suppress(OSError, subprocess.SubprocessError):
                _git(repo_root, "worktree", "remove", "--force", str(tree))
        shutil.rmtree(trees_dir, ignore_errors=True)
        with suppress(OSError, subprocess.SubprocessError):
            _git(repo_root, "worktree", "prune")


def _execution_evidence(result: ExecutionResult) -> str:
    parts = []
    if result.stdout:
        parts.append(f"stdout:\n{result.stdout}")
    if result.stderr:
        parts.append(f"stderr:\n{result.stderr}")
    return "\n".join(parts)


def _differential_evidence(execution: DifferentialExecution) -> str:
    sections = []
    for side, runs in (("head", execution.head_runs), ("base", execution.base_runs)):
        for index, run in enumerate(runs, start=1):
            evidence = _execution_evidence(run)
            if evidence:
                sections.append(f"{side} run {index}:\n{evidence}")
    return "\n".join(sections)


def _bounded_run_output(value: str) -> str:
    if len(value) <= MAX_RUN_OUTPUT_FRAGMENT_CHARS:
        return value
    marker = "[...truncated...]\n"
    return marker + value[-(MAX_RUN_OUTPUT_FRAGMENT_CHARS - len(marker)) :]


def _differential_run_evidence(
    execution: DifferentialExecution,
) -> list[dict[str, object]]:
    evidence: list[dict[str, object]] = []
    collection = () if execution.collection_run is None else (execution.collection_run,)
    for side, runs in (
        ("collect", collection),
        ("head", execution.head_runs),
        ("base", execution.base_runs),
    ):
        for repeat, run in enumerate(runs, start=1):
            evidence.append(
                {
                    "side": side,
                    "repeat": repeat,
                    "outcome": run.outcome.value,
                    "reason": run.reason,
                    "exit_code": run.exit_code,
                    "elapsed_s": round(run.elapsed_s, 6),
                    "network_blocked": run.network_blocked,
                    "stdout": _bounded_run_output(run.stdout),
                    "stderr": _bounded_run_output(run.stderr),
                }
            )
    return evidence


def verify_candidate(
    repo: Path,
    candidate: StoredCandidate,
    gate_result: GateResult,
    provider: Provider,
    budget: Budget,
    limits: ExecutorLimits,
    *,
    base_sha: str,
    head_sha: str,
    repeats: int = 3,
    deadline: float | None = None,
    clock: Callable[[], float] = time.monotonic,
    adapter: ExecutorAdapter | None = None,
    shared_system: str = "",
) -> VerificationRun:
    started = time.monotonic()
    resolved_base = _resolve_commit(repo, base_sha)
    resolved_head = _resolve_commit(repo, head_sha)
    spec: ReproSpec | None = None

    def deferred_execution(reason: str) -> DifferentialExecution:
        return DifferentialExecution(
            head_runs=(),
            base_runs=(),
            outcome=ExecutionOutcome.DEFERRED,
            reason=reason,
            base_sha=resolved_base or base_sha,
            head_sha=resolved_head or head_sha,
            repeats=repeats,
            elapsed_s=time.monotonic() - started,
            network_blocked=False,
        )

    # differential evidence is only meaningful against immutable, reviewed
    # revisions: validate before spending any generation budget
    violation: str | None = None
    if resolved_base is None or resolved_head is None:
        violation = "unresolvable base/head revision"
    elif _resolve_commit(repo, "HEAD") != resolved_head:
        violation = "workspace HEAD does not match the reviewed head"
    elif not _working_tree_clean(repo):
        violation = "working tree is dirty; differential evidence requires immutable revisions"

    if violation is not None:
        execution = deferred_execution(violation)
    else:
        def generate() -> ReproSpec:
            remaining = None if deadline is None else max(0.0, deadline - clock())
            if remaining is not None and remaining <= 0:
                raise TimeoutError("shared verification deadline exceeded before generation")
            return generate_repro(
                repo,
                candidate,
                provider,
                budget,
                timeout_s=remaining,
                base_ref=resolved_base,
                shared_system=shared_system,
            )

        try:
            spec = generate()
        except Exception as exc:  # noqa: BLE001 - generation failures are ternary DEFER
            execution = deferred_execution(f"generation failed: {type(exc).__name__}: {exc}")
        else:
            execution = execute_differential(
                repo,
                candidate,
                spec,
                limits,
                base_sha=resolved_base or base_sha,
                head_sha=resolved_head or head_sha,
                repeats=repeats,
                deadline=deadline,
                clock=clock,
                adapter=adapter,
                regenerate=generate,
            )

    Ledger(repo).record_verification(
        task_id=candidate.task_id,
        finding_id=candidate.finding.finding_id,
        outcome=execution.outcome.value,
        reason=execution.reason,
        elapsed_s=execution.elapsed_s,
        network_blocked=execution.network_blocked,
        evidence=_differential_evidence(execution),
        mode="differential",
        base_sha=execution.base_sha,
        head_sha=execution.head_sha,
        head_runs=[run.outcome.value for run in execution.head_runs],
        base_runs=[run.outcome.value for run in execution.base_runs],
        repeats=execution.repeats,
        evidence_class=execution.evidence_class.value,
        run_evidence=_differential_run_evidence(execution),
        intent=None if execution.intent is None else asdict(execution.intent),
    )
    if execution.outcome is ExecutionOutcome.DEFERRED:
        return VerificationRun(execution=execution, gate_result=gate_result, spec=spec)
    verified = apply_verification(
        gate_result,
        candidate.alpha,
        reproduced=execution.outcome is ExecutionOutcome.REPRODUCED,
    )
    return VerificationRun(execution=execution, gate_result=verified, spec=spec)
