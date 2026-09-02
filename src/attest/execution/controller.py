"""The privileged side of the execution protocol (X-01).

The controller mints one nonce per run, materialises the declared inputs by
digest into a fresh per-run directory, records the request, hands the job to an
adapter, and then judges the result on its own reading of the artifacts: every
listed artifact is re-read from the outputs directory under the protocol
bound (regular files only, never symlinks) and ``verify_result`` recomputes the
digests. A result that does not answer the issued nonce, a duplicate result, a
result for a job that was never issued or that a restart made ambiguous, an
executor crash and an oversized artifact are all rejected. Accepted results are
persisted atomically (artifacts first, ``result.json`` last).
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

from attest.execution.protocol import (
    ProtocolError,
    canonical_bytes,
    decode_request,
    decode_result,
    encode_request,
    encode_result,
    sha256_hex,
    verify_result,
)
from attest.execution.types import (
    EXECUTION_PROTOCOL_VERSION,
    MAX_ARTIFACT_BYTES,
    NONCE_HEX_CHARS,
    DeclaredInput,
    ExecutionRequest,
    ExecutionResultEnvelope,
    ResourceLimits,
)


class JobState(str, Enum):  # noqa: UP042 - persisted values must stay plain strings
    ISSUED = "issued"
    DISPATCHED = "dispatched"
    COMPLETED = "completed"
    REJECTED = "rejected"
    AMBIGUOUS = "ambiguous"


class ExecutorAdapter(Protocol):
    """One execution backend. It receives host paths for the three mounts and
    must write every artifact it reports into ``outputs``."""

    @property
    def profile(self) -> str: ...

    def backend_digest(self) -> str: ...

    def interpreter_identity(self, host_interpreter: str) -> tuple[str, str]:
        """(interpreter as the job will invoke it, its version text)."""
        ...

    def execute(
        self, request: ExecutionRequest, *, tree: Path, inputs: Path, outputs: Path
    ) -> ExecutionResultEnvelope: ...


@dataclass(frozen=True)
class DispatchOutcome:
    accepted: bool
    reasons: tuple[str, ...]
    envelope: ExecutionResultEnvelope | None
    artifacts: Mapping[str, bytes]  # controller-verified bytes, by artifact name
    run_dir: Path | None

    @property
    def reason(self) -> str:
        return "; ".join(self.reasons)


def write_atomic(path: Path, data: bytes) -> None:
    """Write via a sibling temporary file and rename, so a crash leaves either
    the old file or the complete new one."""
    temporary = path.with_name(path.name + ".tmp")
    with open(temporary, "wb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def read_bounded(path: Path, limit: int) -> bytes | None:
    """The bytes of a regular, non-symlink file of at most ``limit`` bytes; None
    when it is missing, not a regular file, or larger."""
    try:
        info = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        return None
    try:
        with open(path, "rb") as handle:
            # read exactly what lstat announced plus one byte: a file that grew
            # in between is not the file that was measured, so it fails closed
            data = handle.read(info.st_size + 1)
    except OSError:
        return None
    return None if len(data) > info.st_size else data


def _fresh_nonce() -> str:
    return secrets.token_hex(NONCE_HEX_CHARS // 2)


class Controller:
    def __init__(self, root: Path, *, nonce_source: Callable[[], str] | None = None):
        self.root = root
        self._nonce_source = nonce_source or _fresh_nonce
        self._states: dict[str, JobState] = {}
        self._requests: dict[str, ExecutionRequest] = {}

    @classmethod
    def resume(cls, root: Path) -> Controller:
        """After a restart, every job that was issued or dispatched but never
        completed is ambiguous: it can neither be completed nor counted."""
        controller = cls(root)
        for state_path in sorted(root.glob("*/state.json")):
            try:
                raw = json.loads(state_path.read_bytes())
            except (OSError, ValueError):
                continue
            nonce = raw.get("nonce") if isinstance(raw, dict) else None
            state = raw.get("state") if isinstance(raw, dict) else None
            if not isinstance(nonce, str) or state not in {item.value for item in JobState}:
                continue
            job = JobState(state)
            if job in (JobState.ISSUED, JobState.DISPATCHED):
                job = JobState.AMBIGUOUS
            controller._states[nonce] = job
        return controller

    def state(self, nonce: str) -> JobState | None:
        return self._states.get(nonce)

    def issue(
        self,
        *,
        task_id: str,
        run_id: str,
        candidate_id: str,
        revision_sha: str,
        profile: str,
        interpreter: str,
        argv_template: tuple[str, ...] | list[str],
        environment: Mapping[str, str],
        inputs: Mapping[str, bytes],
        limits: ResourceLimits,
        expected_artifacts: tuple[str, ...] | list[str],
    ) -> ExecutionRequest:
        """Mint a request. It must survive the strict decoder, so an unsafe name,
        a credential-looking variable or an oversized input never reaches an
        executor."""
        nonce = self._nonce_source()
        if nonce in self._states:
            raise ProtocolError("nonce reuse")
        request = ExecutionRequest(
            protocol_version=EXECUTION_PROTOCOL_VERSION,
            task_id=task_id,
            nonce=nonce,
            run_id=run_id,
            candidate_id=candidate_id,
            revision_sha=revision_sha,
            profile=profile,
            interpreter=interpreter,
            argv_template=tuple(argv_template),
            environment=tuple(sorted(environment.items())),
            inputs=tuple(
                DeclaredInput(name=name, digest=sha256_hex(data), size=len(data))
                for name, data in sorted(inputs.items())
            ),
            limits=limits,
            expected_artifacts=tuple(expected_artifacts),
        )
        decode_request(encode_request(request))
        self._states[nonce] = JobState.ISSUED
        self._requests[nonce] = request
        return request

    def _set_state(self, run_dir: Path, nonce: str, state: JobState) -> None:
        self._states[nonce] = state
        payload = canonical_bytes({"nonce": nonce, "state": state.value})
        write_atomic(run_dir / "state.json", payload)

    def dispatch(
        self,
        request: ExecutionRequest,
        adapter: ExecutorAdapter,
        *,
        tree: Path,
        inputs: Mapping[str, bytes],
    ) -> DispatchOutcome:
        nonce = request.nonce
        state = self._states.get(nonce)
        if state is None:
            return DispatchOutcome(
                False,
                ("result before dispatch: this controller never issued the request",),
                None,
                {},
                None,
            )
        if state is not JobState.ISSUED:
            self._states[nonce] = JobState.REJECTED if state is JobState.ISSUED else state
            return DispatchOutcome(
                False, (f"stale request: already {state.value}",), None, {}, None
            )
        if self._requests.get(nonce) != request:
            self._states[nonce] = JobState.REJECTED
            return DispatchOutcome(
                False, ("request differs from the one issued under this nonce",), None, {}, None
            )
        if adapter.profile != request.profile:
            self._states[nonce] = JobState.REJECTED
            return DispatchOutcome(
                False,
                (f"adapter profile {adapter.profile} differs from {request.profile}",),
                None,
                {},
                None,
            )
        run_dir = self.root / request.run_id
        inputs_dir = run_dir / "inputs"
        outputs_dir = run_dir / "outputs"
        artifacts_dir = run_dir / "artifacts"
        try:
            if not tree.is_dir():
                raise OSError(f"tree {tree} is not a directory")
            for directory in (inputs_dir, outputs_dir, artifacts_dir):
                shutil.rmtree(directory, ignore_errors=True)
            run_dir.mkdir(parents=True, exist_ok=True)
            inputs_dir.mkdir()
            outputs_dir.mkdir()
            for declared in request.inputs:
                data = inputs.get(declared.name)
                if (
                    data is None
                    or len(data) != declared.size
                    or sha256_hex(data) != declared.digest
                ):
                    self._states[nonce] = JobState.REJECTED
                    return DispatchOutcome(
                        False,
                        (f"input {declared.name} does not match its declaration",),
                        None,
                        {},
                        run_dir,
                    )
                (inputs_dir / declared.name).write_bytes(data)
            write_atomic(run_dir / "request.json", encode_request(request))
            self._set_state(run_dir, nonce, JobState.DISPATCHED)
        except OSError as exc:
            self._states[nonce] = JobState.REJECTED
            return DispatchOutcome(
                False, (f"could not materialise the job: {exc}",), None, {}, run_dir
            )
        try:
            envelope = adapter.execute(request, tree=tree, inputs=inputs_dir, outputs=outputs_dir)
        except Exception as exc:  # noqa: BLE001 - an executor crash is a rejected run
            self._set_state(run_dir, nonce, JobState.REJECTED)
            return DispatchOutcome(
                False, (f"executor crash: {type(exc).__name__}: {exc}",), None, {}, run_dir
            )
        problems: list[str] = []
        artifact_bytes: dict[str, bytes] = {}
        try:
            envelope = decode_result(encode_result(envelope))
        except ProtocolError as exc:
            problems.append(f"malformed result: {exc}")
        else:
            for artifact in envelope.artifacts:
                if artifact.name not in request.expected_artifacts:
                    continue  # verify_result names it
                data = read_bounded(outputs_dir / artifact.name, MAX_ARTIFACT_BYTES)
                if data is None:
                    problems.append(
                        f"artifact {artifact.name} is missing, not a regular file, "
                        "or exceeds the bound"
                    )
                else:
                    artifact_bytes[artifact.name] = data
            problems.extend(verify_result(request, envelope, artifact_bytes))
        if problems:
            self._set_state(run_dir, nonce, JobState.REJECTED)
            return DispatchOutcome(False, tuple(problems), envelope, {}, run_dir)
        try:
            artifacts_dir.mkdir()
            for name, data in artifact_bytes.items():
                write_atomic(artifacts_dir / name, data)
            write_atomic(run_dir / "result.json", encode_result(envelope))
            self._set_state(run_dir, nonce, JobState.COMPLETED)
        except OSError as exc:
            self._states[nonce] = JobState.REJECTED
            return DispatchOutcome(
                False, (f"could not persist the result: {exc}",), envelope, {}, run_dir
            )
        return DispatchOutcome(True, (), envelope, artifact_bytes, run_dir)
