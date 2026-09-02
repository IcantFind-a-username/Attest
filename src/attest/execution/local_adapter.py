"""``local_development_best_effort``: the in-process host adapter (X-01).

It runs the requested interpreter as a child of the controller process with
the language-level guards the request's inputs carry, POSIX resource limits
and a wall clock. It is a development convenience for the operator's own
machine and is never a production profile: nothing below the language runtime
separates the reviewed code from the host.
"""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO

from attest.execution.protocol import request_digest, sha256_hex
from attest.execution.types import (
    EXECUTION_PROTOCOL_VERSION,
    LOCAL_DEVELOPMENT_PROFILE,
    Artifact,
    ExecutionRequest,
    ExecutionResultEnvelope,
    ResourceLimits,
)

CLEANUP_TIMEOUT_S = 1.0
# host variables a development interpreter needs to start at all; never a
# credential (the protocol rejects those names before a request exists)
HOST_PASSTHROUGH = (
    "PATH",
    "HOME",
    "TMPDIR",
    "TEMP",
    "TMP",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "SYSTEMROOT",
    "PATHEXT",
    "COMSPEC",
)


def substitute(value: str, mounts: dict[str, str]) -> str:
    for placeholder, path in mounts.items():
        value = value.replace(placeholder, path)
    return value


def _remaining(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


class _TailBuffer:
    def __init__(self, limit: int):
        self.limit = max(1, limit)
        self.chunks: list[bytes] = []
        self.size = 0

    def append(self, chunk: bytes) -> None:
        self.chunks.append(chunk)
        self.size += len(chunk)
        while self.size > self.limit and len(self.chunks) > 1:
            self.size -= len(self.chunks.pop(0))
        if self.size > self.limit:
            self.chunks[0] = self.chunks[0][-self.limit :]
            self.size = len(self.chunks[0])

    def value(self) -> bytes:
        return b"".join(self.chunks)[-self.limit :]


def _drain_stream(stream: BinaryIO, tail: _TailBuffer) -> None:
    try:
        with stream:
            while chunk := stream.read(65_536):
                tail.append(chunk)
    except (OSError, ValueError):
        return


def _resource_limiter(limits: ResourceLimits) -> Callable[[], None] | None:
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


def _terminate_owned_process(process: subprocess.Popen[bytes], deadline: float) -> None:
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
        return self.stdout_tail.value()

    @property
    def stderr(self) -> bytes:
        return self.stderr_tail.value()


def list_artifacts(outputs: Path, expected: tuple[str, ...]) -> tuple[Artifact, ...]:
    """Regular files among the expected names, with their digests."""
    found: list[Artifact] = []
    for name in expected:
        path = outputs / name
        try:
            info = os.lstat(path)
        except OSError:
            continue
        if not stat.S_ISREG(info.st_mode):
            continue
        data = path.read_bytes()
        found.append(Artifact(name=name, digest=sha256_hex(data), size=len(data)))
    return tuple(found)


class LocalDevelopmentAdapter:
    profile = LOCAL_DEVELOPMENT_PROFILE

    def backend_digest(self) -> str:
        return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def execute(
        self, request: ExecutionRequest, *, tree: Path, inputs: Path, outputs: Path
    ) -> ExecutionResultEnvelope:
        started = time.monotonic()
        mounts = {"{tree}": str(tree), "{inputs}": str(inputs), "{outputs}": str(outputs)}
        argv = [substitute(entry, mounts) for entry in request.argv_template]
        env = {name: os.environ[name] for name in HOST_PASSTHROUGH if name in os.environ}
        env.update({name: substitute(value, mounts) for name, value in request.environment})
        limits = request.limits
        raw_process: subprocess.Popen[bytes] | None = None
        owner: _OwnedProcess | None = None
        failure: Exception | None = None
        timed_out = False
        try:
            raw_process = subprocess.Popen(
                argv,
                cwd=tree,
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
        except Exception as exc:  # noqa: BLE001 - infrastructure failures are reported, not raised
            failure = exc
        finally:
            if failure is not None:
                cleanup_deadline = time.monotonic() + CLEANUP_TIMEOUT_S
                if owner is not None:
                    owner.cleanup(cleanup_deadline)
                elif raw_process is not None:
                    _cleanup_raw_process(raw_process, cleanup_deadline)
        stdout = owner.stdout if owner is not None else b""
        stderr = owner.stderr if owner is not None else b""
        with suppress(OSError):
            (outputs / "stdout.txt").write_bytes(stdout)
            (outputs / "stderr.txt").write_bytes(stderr)
        error = ""
        if failure is not None and not timed_out:
            error = f"{type(failure).__name__}: {failure}"
        exit_code = None
        if raw_process is not None and failure is None:
            exit_code = raw_process.returncode
        return ExecutionResultEnvelope(
            protocol_version=EXECUTION_PROTOCOL_VERSION,
            nonce=request.nonce,
            request_digest=request_digest(request),
            run_id=request.run_id,
            profile=self.profile,
            backend_digest=self.backend_digest(),
            exit_code=exit_code,
            timed_out=timed_out,
            elapsed_s=time.monotonic() - started,
            artifacts=list_artifacts(outputs, request.expected_artifacts),
            error=error,
        )
