"""``linux-container-v1``: the production Linux isolation backend (X-02).

Mainline §5 decision B, answered by the owner on 2026-09-02: an OCI container
run as a non-root user with ``--network none``, a read-only root filesystem,
tmpfs scratch, an empty environment (only what the request names, via
``env -i``), every capability dropped, ``no-new-privileges``, a pid limit and
``RLIMIT_NPROC = 0`` so the language guard's kernel-containment check holds.
The tree under test is mounted read-only, the controller's inputs mount is
read-only, and the outputs mount is the only host directory the job can
write. The image is chosen by the executor-side interpreter rule (the
project's declared Python classifiers) and its digest is part of the
backend digest that every run record and receipt carries.

The adapter never sees a credential: the request environment is explicit and
credential-free by protocol, and the container's environment is exactly the
substituted request environment plus PATH and HOME inside the image.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from attest.execution.local_adapter import list_artifacts, substitute
from attest.execution.protocol import request_digest
from attest.execution.types import (
    EXECUTION_PROTOCOL_VERSION,
    ExecutionRequest,
    ExecutionResultEnvelope,
)

CONTAINER_PROFILE = "linux-container-v1"
TREE_MOUNT = "/attest/tree"
INPUTS_MOUNT = "/attest/inputs"
OUTPUTS_MOUNT = "/attest/outputs"
SCRATCH_MOUNT = "/attest/scratch"
CONTAINER_UID = 65534
CONTAINER_PATH = "/usr/local/bin:/usr/bin:/bin"
DEFAULT_PIDS_LIMIT = 16
DEFAULT_TMPFS_MB = 256
KILL_GRACE_S = 2.0
NPROC_LAUNCHER = (
    "import os, resource, sys; "
    "resource.setrlimit(resource.RLIMIT_NPROC, (0, 0)); "
    "os.execvp(sys.argv[1], sys.argv[1:])"
)


@dataclass(frozen=True)
class ContainerImage:
    reference: str  # e.g. attest-repro:<case>-py3.11, or python:3.11-slim
    digest: str  # the image id/digest docker reports, or "" when unresolved


class ContainerUnavailable(RuntimeError):
    """The backend cannot run at all (no docker, no daemon, no image)."""


def docker_executable() -> str | None:
    return shutil.which("docker")


def image_digest(reference: str, *, docker: str | None = None) -> str:
    """The content digest docker holds for ``reference`` ('' when unknown)."""
    binary = docker or docker_executable()
    if binary is None:
        return ""
    probe = subprocess.run(
        [binary, "image", "inspect", "--format", "{{.Id}}", reference],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        return ""
    return probe.stdout.strip()


class ContainerAdapter:
    """Run one request inside a fresh container of ``image``."""

    profile = CONTAINER_PROFILE

    def __init__(
        self,
        image: ContainerImage,
        *,
        docker: str | None = None,
        pids_limit: int = DEFAULT_PIDS_LIMIT,
        tmpfs_mb: int = DEFAULT_TMPFS_MB,
    ) -> None:
        self.image = image
        self.docker = docker or docker_executable()
        self.pids_limit = pids_limit
        self.tmpfs_mb = tmpfs_mb

    def interpreter_identity(self, host_interpreter: str) -> tuple[str, str]:
        """The image's python, whatever the host offered: the job invokes
        ``python3`` from the image and the identity names the image."""
        if not hasattr(self, "_version"):
            self._version = ""
            if self.docker is not None:
                probe = subprocess.run(
                    [
                        self.docker,
                        "run",
                        "--rm",
                        "--network",
                        "none",
                        "--entrypoint",
                        "python3",
                        self.image.reference,
                        "-c",
                        "import sys; print(sys.version)",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if probe.returncode == 0:
                    self._version = probe.stdout.strip()
        return f"python3@{self.image.reference}", self._version

    def backend_digest(self) -> str:
        """The adapter module bytes and the image digest, bound together."""
        material = json.dumps(
            {
                "adapter": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "image": self.image.reference,
                "image_digest": self.image.digest,
                "profile": self.profile,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def command(
        self, request: ExecutionRequest, *, tree: Path, inputs: Path, outputs: Path
    ) -> list[str]:
        """The exact ``docker run`` argv for one request (pure; testable)."""
        if self.docker is None:
            raise ContainerUnavailable("docker is not installed on this host")
        mounts = {
            "{tree}": TREE_MOUNT,
            "{inputs}": INPUTS_MOUNT,
            "{outputs}": OUTPUTS_MOUNT,
            "{scratch}": f"{SCRATCH_MOUNT}:/tmp",
        }
        limits = request.limits
        argv = [
            self.docker,
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--user",
            f"{CONTAINER_UID}:{CONTAINER_UID}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            str(self.pids_limit),
            "--ulimit",
            f"cpu={max(1, limits.cpu_timeout_s)}:{max(1, limits.cpu_timeout_s)}",
            "--memory",
            f"{max(64, limits.memory_mb)}m",
            "--tmpfs",
            f"{SCRATCH_MOUNT}:rw,nosuid,size={self.tmpfs_mb}m",
            "--tmpfs",
            f"/tmp:rw,nosuid,size={self.tmpfs_mb}m",
            "--mount",
            f"type=bind,src={tree},dst={TREE_MOUNT},readonly",
            "--mount",
            f"type=bind,src={inputs},dst={INPUTS_MOUNT},readonly",
            "--mount",
            f"type=bind,src={outputs},dst={OUTPUTS_MOUNT}",
            "--workdir",
            TREE_MOUNT,
            "--entrypoint",
            "/usr/bin/env",
            self.image.reference,
            "-i",
            f"PATH={CONTAINER_PATH}",
            f"HOME={SCRATCH_MOUNT}",
            f"TMPDIR={SCRATCH_MOUNT}",
        ]
        for name, value in request.environment:
            argv.append(f"{name}={substitute(value, mounts)}")
        job = [substitute(entry, mounts) for entry in request.argv_template]
        if job and job[0] == request.interpreter:
            job[0] = "python3"  # the image's interpreter, never a host path
        # RLIMIT_NPROC = 0 is set by a launcher inside the container after the
        # runtime's own setuid/exec (setting it through the runtime races the
        # per-uid process count of the whole VM and fails exec with EAGAIN);
        # fork then fails in the job, and the pid cgroup limit is the backstop
        argv.extend(["python3", "-c", NPROC_LAUNCHER])
        argv.extend(job)
        return argv

    def execute(
        self, request: ExecutionRequest, *, tree: Path, inputs: Path, outputs: Path
    ) -> ExecutionResultEnvelope:
        started = time.monotonic()
        argv = self.command(request, tree=tree, inputs=inputs, outputs=outputs)
        # the outputs mount must be writable by the container's unprivileged
        # user; on Docker Desktop bind mounts map to the host user, on a Linux
        # host the directory is made world-writable for the run
        with_mode = outputs.stat().st_mode
        os.chmod(outputs, 0o777)
        timed_out = False
        error = ""
        exit_code: int | None = None
        stdout = b""
        stderr = b""
        try:
            completed = subprocess.run(
                argv,
                capture_output=True,
                timeout=request.limits.wall_timeout_s,
                env={
                    "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
                    "HOME": os.environ.get("HOME", "/"),
                },
            )
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            stdout = exc.stdout or b""
            stderr = exc.stderr or b""
        except OSError as exc:
            error = f"{type(exc).__name__}: {exc}"
        else:
            exit_code = completed.returncode
            stdout = completed.stdout
            stderr = completed.stderr
            if exit_code == 125 or exit_code == 126 or exit_code == 127:
                # docker itself could not start the container: an infrastructure
                # failure, never a test outcome
                error = (
                    f"container did not start (docker exit {exit_code}): "
                    + stderr.decode("utf-8", errors="replace")[-400:]
                )
        finally:
            os.chmod(outputs, with_mode | 0o700)
        limit = request.limits.output_bytes
        (outputs / "stdout.txt").write_bytes(stdout[-limit:])
        (outputs / "stderr.txt").write_bytes(stderr[-limit:])
        return ExecutionResultEnvelope(
            protocol_version=EXECUTION_PROTOCOL_VERSION,
            nonce=request.nonce,
            request_digest=request_digest(request),
            run_id=request.run_id,
            profile=self.profile,
            backend_digest=self.backend_digest(),
            exit_code=None if error else exit_code,
            timed_out=timed_out,
            elapsed_s=time.monotonic() - started,
            artifacts=list_artifacts(outputs, request.expected_artifacts),
            error=error,
        )
