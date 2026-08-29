"""Generate and execute focused Python reproduction tests."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, BinaryIO

from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.gate import GateResult, apply_verification
from attest.review.ledger import Ledger
from attest.review.proposer import Provider

MAX_CONTEXT_LINES = 200
MAX_REPRO_TOKENS = 2_000
CLEANUP_TIMEOUT_S = 1.0
GIT_TIMEOUT_S = 60.0
MAX_REASON_CHARS = 300
CAP_SYS_ADMIN = 21
CAP_SYS_RESOURCE = 24
_CREDENTIAL_NAME_PARTS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")

REPRO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"test_body": {"type": "string"}},
    "required": ["test_body"],
    "additionalProperties": False,
}

GENERATOR_SYSTEM = """Write one focused pytest reproduction for the supplied finding. Return only
the test body required by the schema. The test must distinguish the claimed defect from correct
behavior and must not use the network."""

SITECUSTOMIZE = """import _thread
import os
import socket
import sys
import threading
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

def _reject_connection(*args, **kwargs):
    raise PermissionError("network disabled by evidence executor")
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


@dataclass(frozen=True)
class VerificationRun:
    execution: DifferentialExecution
    gate_result: GateResult


_SYMBOL_ABSENT_EXCEPTIONS = (
    "ModuleNotFoundError",
    "ImportError",
    "AttributeError",
    "NameError",
    "KeyError",
)
_ABSENT_ALTERNATION = "|".join(_SYMBOL_ABSENT_EXCEPTIONS)
# Only lines pytest emits *at* the point of failure: the reported exception detail
# ("E   AttributeError: ..."), the traceback location line, a raw interpreter
# traceback, or a collection-error header. Echoed source lines
# ("> with pytest.raises(KeyError):") deliberately do not count.
_SYMBOL_ABSENT_MARKERS = tuple(
    re.compile(pattern, re.MULTILINE)
    for pattern in (
        rf"^E\s+(?:{_ABSENT_ALTERNATION})\b",
        rf"^.*:\d+: (?:{_ABSENT_ALTERNATION})\s*$",
        rf"^(?:{_ABSENT_ALTERNATION}):",
        rf"^(?:{_ABSENT_ALTERNATION}) while importing test module",
    )
)
_ASSERTION_MARKERS = tuple(
    re.compile(pattern, re.MULTILINE)
    for pattern in (
        r"^E\s+(?:assert\b|AssertionError\b)",
        r"^.*:\d+: AssertionError\s*$",
        r"^AssertionError\b",
    )
)


def classify_failure_signature(result: ExecutionResult) -> FailureSignature:
    """Why a run failed: the symbol under test is absent, a real assertion
    fired, or neither. Deliberately conservative -- when both signatures appear
    the assertion wins, so a bogus test cannot hide behind an incidental
    KeyError raised somewhere in the same output."""
    text = f"{result.stdout}\n{result.stderr}"
    if any(marker.search(text) for marker in _ASSERTION_MARKERS):
        return FailureSignature.ASSERTION
    if any(marker.search(text) for marker in _SYMBOL_ABSENT_MARKERS):
        return FailureSignature.SYMBOL_ABSENT
    return FailureSignature.OTHER


def _side_signature(runs: list[ExecutionResult]) -> FailureSignature:
    """The signature shared by every failing run on one side; OTHER when the
    runs disagree or when nothing failed."""
    signatures = {
        classify_failure_signature(run)
        for run in runs
        if run.outcome is ExecutionOutcome.REPRODUCED
    }
    return signatures.pop() if len(signatures) == 1 else FailureSignature.OTHER


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


def _generation_prompt(repo: Path, candidate: StoredCandidate) -> str:
    finding = candidate.finding
    return (
        f"Claim: {finding.claim}\n"
        f"Failure scenario: {finding.failure_scenario}\n"
        f"Falsification plan: {finding.falsification_plan}\n"
        f"Anchor: {finding.file}:{finding.line}\n\n"
        "Source context:\n"
        f"{_anchor_context(repo, candidate)}"
    )


def _parse_repro(text: str) -> ReproSpec:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("generator output is not valid JSON") from exc
    if (
        not isinstance(payload, dict)
        or set(payload) != {"test_body"}
        or not isinstance(payload["test_body"], str)
    ):
        raise ValueError("generator output does not match the reproduction schema")
    return ReproSpec(test_body=payload["test_body"])


def _sitecustomize(
    network_marker: Path,
    process_guard_marker: Path,
    process_containment_marker: Path,
    process_attempt_marker: Path,
    process_replacement_marker: Path,
    thread_attempt_marker: Path,
) -> str:
    return (
        SITECUSTOMIZE
        + f"""
_network_marker = Path({str(network_marker)!r})
_process_guard_marker = Path({str(process_guard_marker)!r})
_process_containment_marker = Path({str(process_containment_marker)!r})
_process_attempt_marker = Path({str(process_attempt_marker)!r})
_process_replacement_marker = Path({str(process_replacement_marker)!r})
_thread_attempt_marker = Path({str(thread_attempt_marker)!r})
_PROCESS_GUARD_PROBE = "attest.process_guard_probe"

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
        raise PermissionError("network disabled by evidence executor")
    process_event = event in _PROCESS_EVENTS
    native_symbol = (
        event in {{"ctypes.dlsym", "ctypes.dlsym/handle"}}
        and args
        and args[-1] in _PROCESS_SYMBOLS
    )
    replacement_event = event in _PROCESS_REPLACEMENT_EVENTS
    replacement_symbol = (
        event in {{"ctypes.dlsym", "ctypes.dlsym/handle"}}
        and args
        and args[-1] in _PROCESS_REPLACEMENT_SYMBOLS
    )
    if replacement_event or replacement_symbol:
        _process_replacement_marker.write_text("attempted", encoding="utf-8")
        raise PermissionError("process replacement disabled by evidence executor")
    if not process_event and not native_symbol:
        return
    _process_attempt_marker.write_text("attempted", encoding="utf-8")
    if os.name != "posix":
        raise PermissionError("process creation disabled by evidence executor")

sys.addaudithook(_guard_operations)
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

socket.socket.connect = _reject_connection
socket.socket.connect_ex = _reject_connection
socket.create_connection = _reject_connection
_network_marker.write_text("active", encoding="utf-8")
"""
    )


def generate_repro(
    repo: Path,
    candidate: StoredCandidate,
    provider: Provider,
    budget: Budget,
    *,
    timeout_s: float | None = None,
) -> ReproSpec:
    prompt = _generation_prompt(repo, candidate)
    label = f"verify-{candidate.finding.finding_id}"
    reservation = budget.reserve(label, len(GENERATOR_SYSTEM) + len(prompt), MAX_REPRO_TOKENS)
    try:
        result = provider.sample(
            GENERATOR_SYSTEM,
            prompt,
            REPRO_SCHEMA,
            MAX_REPRO_TOKENS,
            timeout_s=timeout_s,
        )
    except Exception:
        budget.cancel(reservation)
        raise
    budget.settle(label, reservation, result.input_tokens, result.output_tokens)
    return _parse_repro(result.text)


def _truncate_output(output: bytes | str | None, limit: int) -> str:
    if output is None or limit <= 0:
        return ""
    encoded = output.encode("utf-8", errors="replace") if isinstance(output, str) else output
    return encoded[-limit:].decode("utf-8", errors="ignore")


class _TailBuffer:
    def __init__(self, limit: int):
        self.limit = max(0, limit)
        self.data = bytearray()

    def append(self, chunk: bytes) -> None:
        if self.limit == 0:
            return
        if len(chunk) >= self.limit:
            self.data = bytearray(chunk[-self.limit :])
            return
        excess = len(self.data) + len(chunk) - self.limit
        if excess > 0:
            del self.data[:excess]
        self.data.extend(chunk)


def _drain_stream(stream: BinaryIO, tail: _TailBuffer) -> None:
    try:
        with stream:
            while chunk := stream.read(65_536):
                tail.append(chunk)
    except (OSError, ValueError):
        return


def _resource_limiter(limits: ExecutorLimits) -> Callable[[], None] | None:
    if os.name != "posix":
        return None

    def apply_limits() -> None:
        import resource

        cpu_seconds = max(1, limits.cpu_timeout_s)
        memory_bytes = max(1, limits.memory_mb) * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        except (OSError, ValueError):
            # Darwin rejects finite address-space limits for the interpreter;
            # Linux runners enforce this branch normally.
            if sys.platform != "darwin":
                raise

    return apply_limits


def _junit_counts(path: Path) -> tuple[int, int]:
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.iter("testsuite"))
    if not suites:
        raise ValueError("JUnit has no test suites")
    failures = sum(int(suite.attrib.get("failures", "0")) for suite in suites)
    errors = sum(int(suite.attrib.get("errors", "0")) for suite in suites)
    return failures, errors


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


def _reproduction_environment(site_dir: Path, tree: Path | None = None) -> dict[str, str]:
    env = {
        name: value
        for name, value in os.environ.items()
        if not any(part in name.upper() for part in _CREDENTIAL_NAME_PARTS)
    }
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTHONSAFEPATH"] = "1"
    # tree entries come first so the revision under test shadows any installed
    # copy; the guard sitecustomize is still resolved from site_dir via the
    # remainder of the path scan (a tree-level shadow fails closed on markers)
    entries = [] if tree is None else [str(tree), str(tree / "src")]
    entries.append(str(site_dir))
    old_pythonpath = env.get("PYTHONPATH")
    if old_pythonpath:
        entries.append(old_pythonpath)
    env["PYTHONPATH"] = os.pathsep.join(entries)
    return env


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


def _terminate_owned_process(
    process: subprocess.Popen[bytes],
    deadline: float,
) -> None:
    if os.name == "nt":
        killer = subprocess.Popen(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            killer.wait(timeout=_remaining(deadline))
        except subprocess.TimeoutExpired:
            killer.kill()
    if process.poll() is None:
        process.kill()


def _cleanup_raw_process(process: subprocess.Popen[bytes], deadline: float) -> None:
    with suppress(Exception):
        _terminate_owned_process(process, deadline)
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=_remaining(deadline))
    for stream in (process.stdout, process.stderr):
        if stream is not None and not stream.closed:
            with suppress(OSError):
                stream.close()


class _OwnedProcess:
    def __init__(self, process: subprocess.Popen[bytes], output_bytes: int):
        self.process = process
        self.stdout_tail = _TailBuffer(output_bytes)
        self.stderr_tail = _TailBuffer(output_bytes)
        self.drainers: list[threading.Thread] = []

    def start(self) -> None:
        if self.process.stdout is None or self.process.stderr is None:
            raise RuntimeError("executor pipes were not created")
        for stream, tail in (
            (self.process.stdout, self.stdout_tail),
            (self.process.stderr, self.stderr_tail),
        ):
            drainer = threading.Thread(target=_drain_stream, args=(stream, tail), daemon=True)
            drainer.start()
            self.drainers.append(drainer)

    def wait(self, deadline: float) -> None:
        self.process.wait(timeout=_remaining(deadline))
        for drainer in self.drainers:
            drainer.join(timeout=_remaining(deadline))
        if any(drainer.is_alive() for drainer in self.drainers):
            raise subprocess.TimeoutExpired(self.process.args, timeout=0)

    def cleanup(self, deadline: float) -> None:
        with suppress(Exception):
            _terminate_owned_process(self.process, deadline)
        with suppress(subprocess.TimeoutExpired):
            self.process.wait(timeout=_remaining(deadline))
        for drainer in self.drainers:
            drainer.join(timeout=_remaining(deadline))
        for stream in (self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                with suppress(OSError):
                    stream.close()
        for drainer in self.drainers:
            if drainer.is_alive():
                drainer.join(timeout=_remaining(deadline))

    @property
    def stdout(self) -> bytes:
        return bytes(self.stdout_tail.data)

    @property
    def stderr(self) -> bytes:
        return bytes(self.stderr_tail.data)


def execute_repro(
    repo: Path,
    candidate: StoredCandidate,
    spec: ReproSpec,
    limits: ExecutorLimits,
    *,
    tree: Path | None = None,
    run_label: str = "",
) -> ExecutionResult:
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

    work_dir = (
        repo_root
        / ".attest"
        / "repro"
        / candidate.task_id
        / candidate.finding.finding_id
    )
    if run_label:
        work_dir = work_dir / run_label
    generated_path = work_dir / "test_repro.py"
    junit_path = work_dir / "junit.xml"
    site_dir = work_dir / "python_startup"
    network_marker = site_dir / "network-blocked"
    process_guard_marker = site_dir / "process-guarded"
    process_containment_marker = site_dir / "process-contained"
    process_attempt_marker = site_dir / "process-attempted"
    process_replacement_marker = site_dir / "process-replacement-attempted"
    thread_attempt_marker = site_dir / "thread-attempted"
    raw_process: subprocess.Popen[bytes] | None = None
    owner: _OwnedProcess | None = None
    failure: Exception | None = None
    timed_out = False
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        site_dir.mkdir(exist_ok=True)
        generated_path.write_text(spec.test_body.rstrip("\n") + "\n", encoding="utf-8")
        (site_dir / "sitecustomize.py").write_text(
            _sitecustomize(
                network_marker,
                process_guard_marker,
                process_containment_marker,
                process_attempt_marker,
                process_replacement_marker,
                thread_attempt_marker,
            ),
            encoding="utf-8",
        )
        junit_path.unlink(missing_ok=True)
        for marker in (
            network_marker,
            process_guard_marker,
            process_containment_marker,
            process_attempt_marker,
            process_replacement_marker,
            thread_attempt_marker,
        ):
            marker.unlink(missing_ok=True)

        env = _reproduction_environment(site_dir, tree)
        raw_process = subprocess.Popen(
            [
                interpreter,
                "-m",
                "pytest",
                "-q",
                str(generated_path),
                "--junitxml",
                str(junit_path),
            ],
            cwd=repo_root if tree is None else tree,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
            preexec_fn=_resource_limiter(limits),
            start_new_session=os.name == "posix",
            creationflags=(
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0
            ),
        )
        owner = _OwnedProcess(raw_process, limits.output_bytes)
        owner.start()
        owner.wait(started + limits.wall_timeout_s)
    except subprocess.TimeoutExpired as exc:
        failure = exc
        timed_out = True
    except Exception as exc:  # noqa: BLE001 - infrastructure failures are ternary DEFER
        failure = exc
    finally:
        if failure is not None:
            cleanup_deadline = time.monotonic() + CLEANUP_TIMEOUT_S
            if owner is not None:
                owner.cleanup(cleanup_deadline)
            elif raw_process is not None:
                _cleanup_raw_process(raw_process, cleanup_deadline)

    stdout_bytes = owner.stdout if owner is not None else b""
    stderr_bytes = owner.stderr if owner is not None else b""
    if timed_out:
        return _deferred(
            f"reproduction timed out after {limits.wall_timeout_s:g}s",
            started,
            stdout=_truncate_output(stdout_bytes, limits.output_bytes),
            stderr=_truncate_output(stderr_bytes, limits.output_bytes),
            network_blocked=network_marker.is_file(),
        )
    if failure is not None:
        return _deferred(
            f"executor failure: {type(failure).__name__}: {failure}",
            started,
            stdout=_truncate_output(stdout_bytes, limits.output_bytes),
            stderr=_truncate_output(stderr_bytes, limits.output_bytes),
            network_blocked=network_marker.is_file(),
        )

    if owner is None:
        return _deferred("executor failure: process was not started", started)
    process = owner.process
    stdout = _truncate_output(stdout_bytes, limits.output_bytes)
    stderr = _truncate_output(stderr_bytes, limits.output_bytes)
    network_blocked = network_marker.is_file()
    process_guarded = process_guard_marker.is_file()
    process_contained = os.name != "posix" or process_containment_marker.is_file()
    if not process_guarded:
        return _deferred(
            "process guard did not initialize",
            started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if not process_contained:
        return _deferred(
            "kernel process containment did not initialize",
            started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if process_replacement_marker.is_file():
        return _deferred(
            "reproduction attempted to replace the pytest process",
            started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if process_attempt_marker.is_file():
        return _deferred(
            "reproduction attempted to create a child process",
            started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if thread_attempt_marker.is_file():
        return _deferred(
            "reproduction attempted to create a thread",
            started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )
    if not network_blocked:
        return _deferred(
            "network guard did not initialize",
            started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    try:
        failures, errors = _junit_counts(junit_path)
    except (OSError, ET.ParseError, TypeError, ValueError) as exc:
        return _deferred(
            f"missing or malformed JUnit evidence: {type(exc).__name__}: {exc}",
            started,
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            network_blocked=network_blocked,
        )

    if process.returncode == 0:
        return ExecutionResult(
            outcome=ExecutionOutcome.NOT_REPRODUCED,
            reason="pytest passed",
            exit_code=0,
            stdout=stdout,
            stderr=stderr,
            elapsed_s=time.monotonic() - started,
            network_blocked=network_blocked,
        )
    if process.returncode == 1 and failures > 0 and errors == 0:
        return ExecutionResult(
            outcome=ExecutionOutcome.REPRODUCED,
            reason=f"pytest reported {failures} failure(s) and 0 error(s)",
            exit_code=1,
            stdout=stdout,
            stderr=stderr,
            elapsed_s=time.monotonic() - started,
            network_blocked=network_blocked,
        )
    return _deferred(
        "pytest collection/import/syntax or infrastructure failure "
        f"(exit code {process.returncode}, {failures} failure(s), {errors} error(s))",
        started,
        exit_code=process.returncode,
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
) -> DifferentialExecution:
    """Run the same reproduction repeatedly against detached head/base
    worktrees. Only a deterministic head failure paired with a deterministic
    base pass counts as REPRODUCED; every other pattern is DEFERRED (flaky or
    unfaithful evidence must never purchase V). Every result also carries an
    evidence class, which describes what was seen without pricing it: a
    new-code candidate is recorded and still DEFERRED."""
    started = time.monotonic()
    repo_root = repo.resolve()
    head_runs: list[ExecutionResult] = []
    base_runs: list[ExecutionResult] = []

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
        )

    def deferred(
        reason: str, evidence_class: EvidenceClass = EvidenceClass.INDETERMINATE
    ) -> DifferentialExecution:
        return finish(ExecutionOutcome.DEFERRED, _bounded_reason(reason), evidence_class)

    def run_once(side: str, index: int, tree: Path) -> ExecutionResult | None:
        """One containment-guarded run against `tree`; None when the shared
        deadline is exhausted."""
        effective = limits
        if deadline is not None:
            remaining = deadline - clock()
            if remaining <= 0:
                return None
            effective = replace(limits, wall_timeout_s=min(limits.wall_timeout_s, remaining))
        return execute_repro(
            repo_root,
            candidate,
            spec,
            effective,
            tree=tree,
            run_label=f"{side}-{index}",
        )

    if repeats < 1:
        return deferred("differential execution requires at least one run")
    if not _safe_path_component(candidate.task_id):
        return deferred("unsafe task identity")
    if deadline is not None and deadline - clock() <= 0:
        return deferred(DEADLINE_REASON)
    trees_dir = (
        repo_root
        / ".attest"
        / "repro"
        / candidate.task_id
        / candidate.finding.finding_id
        / "trees"
    )
    created: list[Path] = []
    try:
        trees_dir.mkdir(parents=True, exist_ok=True)
        for side, sha in (("head", head_sha), ("base", base_sha)):
            try:
                added = _git(
                    repo_root, "worktree", "add", "--detach", str(trees_dir / side), sha
                )
            except (OSError, subprocess.SubprocessError) as exc:
                return deferred(f"could not create {side} worktree: {type(exc).__name__}")
            if added.returncode != 0:
                return deferred(f"could not create {side} worktree: {added.stderr.strip()}")
            created.append(trees_dir / side)

        for index in range(1, repeats + 1):
            run = run_once("head", index, trees_dir / "head")
            if run is None:
                return deferred(DEADLINE_REASON)
            head_runs.append(run)
            if run.outcome is ExecutionOutcome.DEFERRED:
                return deferred(f"head run {index}/{repeats} deferred: {run.reason}")
        head_failures = sum(
            1 for run in head_runs if run.outcome is ExecutionOutcome.REPRODUCED
        )
        if head_failures == 0:
            return finish(
                ExecutionOutcome.NOT_REPRODUCED,
                f"pytest passed on head in {repeats}/{repeats} runs; base not executed",
                EvidenceClass.NOT_REPRODUCED,
            )
        if head_failures < repeats:
            return deferred(
                f"flaky reproduction on head ({head_failures}/{repeats} runs failed)"
            )
        # a fabricated finding fails on head because its symbol exists nowhere,
        # so only an assertion-class head can ever reach NEW_CODE_CANDIDATE
        head_is_assertion = _side_signature(head_runs) is FailureSignature.ASSERTION

        for index in range(1, repeats + 1):
            run = run_once("base", index, trees_dir / "base")
            if run is None:
                return deferred(DEADLINE_REASON)
            base_runs.append(run)
            if run.outcome is ExecutionOutcome.NOT_REPRODUCED:
                continue
            if (
                head_is_assertion
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
        return finish(
            ExecutionOutcome.REPRODUCED,
            f"head FAIL {repeats}/{repeats}, base PASS {repeats}/{repeats}",
            EvidenceClass.REGRESSION_REPRODUCED,
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
) -> VerificationRun:
    started = time.monotonic()
    resolved_base = _resolve_commit(repo, base_sha)
    resolved_head = _resolve_commit(repo, head_sha)

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
        remaining_before_generation = None if deadline is None else max(0.0, deadline - clock())
        try:
            if remaining_before_generation is not None and remaining_before_generation <= 0:
                raise TimeoutError("shared verification deadline exceeded before generation")
            spec = generate_repro(
                repo,
                candidate,
                provider,
                budget,
                timeout_s=remaining_before_generation,
            )
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
    )
    if execution.outcome is ExecutionOutcome.DEFERRED:
        return VerificationRun(execution=execution, gate_result=gate_result)
    verified = apply_verification(
        gate_result,
        candidate.alpha,
        reproduced=execution.outcome is ExecutionOutcome.REPRODUCED,
    )
    return VerificationRun(execution=execution, gate_result=verified)
