"""Generate and execute focused Python reproduction tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.proposer import Provider

MAX_CONTEXT_LINES = 200
MAX_REPRO_TOKENS = 2_000

REPRO_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"test_body": {"type": "string"}},
    "required": ["test_body"],
    "additionalProperties": False,
}

GENERATOR_SYSTEM = """Write one focused pytest reproduction for the supplied finding. Return only
the test body required by the schema. The test must distinguish the claimed defect from correct
behavior and must not use the network."""

SITECUSTOMIZE = """import socket

def _reject_connection(*args, **kwargs):
    raise PermissionError("network disabled by evidence executor")

socket.socket.connect = _reject_connection
socket.socket.connect_ex = _reject_connection
socket.create_connection = _reject_connection
"""


class ExecutionOutcome(str, Enum):  # noqa: UP042 - public API requires this exact base shape
    REPRODUCED = "reproduced"
    NOT_REPRODUCED = "not_reproduced"
    DEFERRED = "deferred"


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


def generate_repro(
    repo: Path,
    candidate: StoredCandidate,
    provider: Provider,
    budget: Budget,
) -> ReproSpec:
    prompt = _generation_prompt(repo, candidate)
    label = f"verify-{candidate.finding.finding_id}"
    reservation = budget.reserve(label, len(GENERATOR_SYSTEM) + len(prompt), MAX_REPRO_TOKENS)
    try:
        result = provider.sample(GENERATOR_SYSTEM, prompt, REPRO_SCHEMA, MAX_REPRO_TOKENS)
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


def _resource_limiter(limits: ExecutorLimits) -> Callable[[], None] | None:
    if os.name != "posix":
        return None

    def apply_limits() -> None:
        import resource

        cpu_seconds = max(1, limits.cpu_timeout_s)
        memory_bytes = max(1, limits.memory_mb) * 1024 * 1024
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


def execute_repro(
    repo: Path,
    candidate: StoredCandidate,
    spec: ReproSpec,
    limits: ExecutorLimits,
) -> ExecutionResult:
    started = time.monotonic()
    suffix = Path(candidate.finding.file).suffix.lower()
    if suffix != ".py":
        return _deferred(f"unsupported anchor language: {suffix or '<none>'}", started)
    if not isinstance(spec.test_body, str):
        return _deferred("malformed generator output: test_body must be a string", started)
    if not _safe_path_component(candidate.task_id):
        return _deferred("unsafe task identity", started)

    work_dir = (
        repo
        / ".attest"
        / "repro"
        / candidate.task_id
        / candidate.finding.finding_id
    )
    generated_path = work_dir / "test_repro.py"
    junit_path = work_dir / "junit.xml"
    site_dir = work_dir / "python_startup"
    try:
        work_dir.mkdir(parents=True, exist_ok=True)
        site_dir.mkdir(exist_ok=True)
        generated_path.write_text(spec.test_body.rstrip("\n") + "\n", encoding="utf-8")
        (site_dir / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
        junit_path.unlink(missing_ok=True)

        env = os.environ.copy()
        env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
        old_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(site_dir) if not old_pythonpath else str(site_dir) + os.pathsep + old_pythonpath
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                str(generated_path),
                "--junitxml",
                str(junit_path),
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            timeout=limits.wall_timeout_s,
            check=False,
            preexec_fn=_resource_limiter(limits),
        )
    except subprocess.TimeoutExpired as exc:
        return _deferred(
            f"reproduction timed out after {limits.wall_timeout_s:g}s",
            started,
            stdout=_truncate_output(exc.stdout, limits.output_bytes),
            stderr=_truncate_output(exc.stderr, limits.output_bytes),
            network_blocked=True,
        )
    except Exception as exc:  # noqa: BLE001 - infrastructure failures are ternary DEFER
        return _deferred(
            f"executor failure: {type(exc).__name__}: {exc}",
            started,
            network_blocked=True,
        )

    stdout = _truncate_output(completed.stdout, limits.output_bytes)
    stderr = _truncate_output(completed.stderr, limits.output_bytes)
    try:
        failures, errors = _junit_counts(junit_path)
    except (OSError, ET.ParseError, TypeError, ValueError) as exc:
        return _deferred(
            f"missing or malformed JUnit evidence: {type(exc).__name__}: {exc}",
            started,
            exit_code=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            network_blocked=True,
        )

    if completed.returncode == 0:
        return ExecutionResult(
            outcome=ExecutionOutcome.NOT_REPRODUCED,
            reason="pytest passed",
            exit_code=0,
            stdout=stdout,
            stderr=stderr,
            elapsed_s=time.monotonic() - started,
            network_blocked=True,
        )
    if completed.returncode == 1 and failures > 0 and errors == 0:
        return ExecutionResult(
            outcome=ExecutionOutcome.REPRODUCED,
            reason=f"pytest reported {failures} failure(s) and 0 error(s)",
            exit_code=1,
            stdout=stdout,
            stderr=stderr,
            elapsed_s=time.monotonic() - started,
            network_blocked=True,
        )
    return _deferred(
        "pytest collection/import/syntax or infrastructure failure "
        f"(exit code {completed.returncode}, {failures} failure(s), {errors} error(s))",
        started,
        exit_code=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        network_blocked=True,
    )
