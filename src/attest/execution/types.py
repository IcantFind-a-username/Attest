"""Frozen values of the execution protocol (X-01). Pure: no I/O, no subprocess."""

from __future__ import annotations

from dataclasses import dataclass

EXECUTION_PROTOCOL_VERSION = "attest.execution-protocol.v1"
LOCAL_DEVELOPMENT_PROFILE = "local_development_best_effort"
NONCE_HEX_CHARS = 32
MAX_ARTIFACT_BYTES = 4 * 1024 * 1024  # hard per-artifact bound the controller enforces
MAX_ARTIFACTS = 16
MAX_INPUTS = 16
MAX_ARGV = 64
MAX_ENVIRONMENT = 32
MAX_TEXT_CHARS = 4_096


@dataclass(frozen=True)
class DeclaredInput:
    """One file the controller materialises for the executor, by content."""

    name: str  # one path component inside the inputs mount
    digest: str  # SHA-256 of the bytes
    size: int


@dataclass(frozen=True)
class ResourceLimits:
    wall_timeout_s: float
    cpu_timeout_s: int
    memory_mb: int
    output_bytes: int


@dataclass(frozen=True)
class ExecutionRequest:
    """What the executor is asked to run. Carries no credential and no host path:
    argv and environment values name the mounts by placeholder (``{tree}``,
    ``{inputs}``, ``{outputs}``) and the adapter resolves them."""

    protocol_version: str
    task_id: str
    nonce: str  # controller-minted, one per run
    run_id: str
    candidate_id: str
    revision_sha: str  # the tree the run executes against; "" when untracked
    profile: str  # executor profile the request is for
    interpreter: str  # interpreter path (local) or image reference (container)
    argv_template: tuple[str, ...]
    environment: tuple[tuple[str, str], ...]  # explicit, sorted by name; nothing inherited
    inputs: tuple[DeclaredInput, ...]
    limits: ResourceLimits
    expected_artifacts: tuple[str, ...]  # the only names the controller will read back


@dataclass(frozen=True)
class Artifact:
    name: str
    digest: str
    size: int


@dataclass(frozen=True)
class ExecutionResultEnvelope:
    """What the executor reports. The controller re-reads every artifact under
    the protocol bound and recomputes every digest before accepting it."""

    protocol_version: str
    nonce: str
    request_digest: str
    run_id: str
    profile: str
    backend_digest: str  # adapter module digest (local) or image digest (container)
    exit_code: int | None
    timed_out: bool
    elapsed_s: float
    artifacts: tuple[Artifact, ...]
    error: str  # non-empty when the executor could not run the job at all
