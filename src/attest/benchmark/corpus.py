"""Metadata-only BugsInPy import and isolated corpus validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import random
import re
import shlex
import signal
import socket
import subprocess
import tempfile
import threading
import time
import weakref
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from pathlib import Path
from typing import Any, Protocol, TypeGuard

from attest.benchmark.artifacts import (
    MAX_ARTIFACT_MANIFEST_BYTES,
    MAX_VALIDATION_DOCUMENT_BYTES,
    ArtifactError,
    ArtifactRecord,
    ArtifactStore,
    canonical_json_bytes,
    read_artifact_bytes,
    validation_failure_signature,
    validation_junit_counts,
    verify_artifacts,
)
from attest.benchmark.schema import (
    BenchmarkCase,
    BenchmarkManifest,
    RuntimeDescriptor,
    load_manifest,
    normalize_unified_diff_bytes,
    verify_descriptor_bytes,
)

_MAX_CHANGED_LINES = 400
VALIDATION_PROTOCOL_V2 = "attest-validation-v2"
_VALIDATION_RUN_ARTIFACT_NAMES = frozenset(
    {
        "stdout",
        "junit",
        "test",
        "command",
        "interpreter",
        "environment",
        "source",
        "executor",
    }
)
_VALIDATION_VERIFIER_SEAL = object()
_VERIFIED_CAPABILITIES: dict[
    int, tuple[weakref.ReferenceType[object], bytes]
] = {}
_PREFLIGHT_EXCLUSION_REASONS = frozenset(
    {
        "checkout_commit_mismatch",
        "checkout_root_mismatch",
        "descriptor_hash_mismatch",
        "dirty_checkout",
        "integrity_failure",
        "isolation_unverified",
        "patch_mismatch",
        "test_command_mismatch",
    }
)
_EXECUTION_EXCLUSION_REASONS = frozenset(
    {
        "dependency_or_setup_failure",
        "flaky",
        "incomplete_execution",
        "inconsistent_failure_signature",
        "timeout",
    }
)
_INFO_LINE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)="([^"]*)"\s*$')
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_PATH = re.compile(r"^diff --git a/(.+) b/(.+)$")
_COPYRIGHT_LINE = re.compile(
    r"^copyright(?:\s+(?:\(c\)|©))?\s+"
    r"\d{4}(?:\s*[-–]\s*\d{2,4})?(?:\s*,\s*\d{4}(?:\s*[-–]\s*\d{2,4})?)*"
    r"\s*,?\s+[\w][\w .&,()'/-]{0,199}$",
    re.IGNORECASE,
)
_BSD3_HOLDER_NAME = re.compile(
    r"(?<=Neither the name of )[\w][\w &,()'/-]{0,199}"
    r"(?= nor the names of its contributors may be used)"
)
_LICENSE_BODY_STARTS = {
    "MIT": "Permission is hereby granted, free of charge",
    "BSD-2-Clause": "Redistribution and use in source and binary forms",
    "BSD-3-Clause": "Redistribution and use in source and binary forms",
}
_LICENSE_BODY_SHA256 = {
    # SHA-256 of whitespace-normalized standard SPDX template bodies after list-marker
    # normalization. Full-body fingerprints make inserted, reordered, or appended terms
    # fail closed without trying to enumerate every unsupported license family.
    "MIT": "fe2a9817987f862eaced948f0468c7f51d2fedfc48c5c505b246a49a3870e9a5",
    "BSD-2-Clause": "4f61a7bc7704d3ecdd43d1b61e887d81a5e0468581a08a1a3beac62e0156da13",
    "BSD-3-Clause": "667a5ea561e27c5843aedc905ba64e45471dda8240aa1ca7a09e513363cba5ac",
}
_LICENSE_HEADERS = {
    "MIT": frozenset(
        {
            "mit license",
            "the mit license (mit)",
            "released under the mit licence.",
        }
    ),
    "BSD-2-Clause": frozenset({"bsd 2-clause license"}),
    "BSD-3-Clause": frozenset({"bsd 3-clause license"}),
}


@dataclass(frozen=True)
class RunOutcome:
    """Bounded result of one isolated corpus test command."""

    returncode: int
    output: bytes
    timed_out: bool
    junit: bytes = b""
    command: tuple[str, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    execution_prefix: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationReceipt:
    """Manifest-bound allowlist of pairs that passed the differential oracle."""

    schema_version: str
    manifest_sha256: str
    validated_pair_ids: tuple[str, ...]
    validation_results_sha256: str

    @property
    def authority(self) -> str:
        """Legacy receipts prove only consistency of frozen historical files."""
        return "historical_integrity_only"

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "manifest_sha256": self.manifest_sha256,
            "validated_pair_ids": list(self.validated_pair_ids),
            "validation_results_sha256": self.validation_results_sha256,
        }

    def to_canonical_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_json_dict())


@dataclass(frozen=True)
class ValidationRun:
    """One bounded fixed or buggy execution with raw content-addressed evidence."""

    run_id: str
    revision: str
    ordinal: int
    outcome: str
    returncode: int
    timed_out: bool
    failure_signature: str | None
    runner_id: str
    profile_id: str
    artifacts: tuple[tuple[str, ArtifactRecord], ...]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "revision": self.revision,
            "ordinal": self.ordinal,
            "outcome": self.outcome,
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "failure_signature": self.failure_signature,
            "runner_id": self.runner_id,
            "profile_id": self.profile_id,
            "artifacts": {
                name: record.to_json_dict() for name, record in self.artifacts
            },
        }

    def to_canonical_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_json_dict())


@dataclass(frozen=True)
class ValidationAttempt:
    """One precommitted pair-validation attempt, including excluded attempts."""

    attempt_id: str
    pair_id: str
    attempt_index: int
    phase: str
    status: str
    reason: str | None
    runs: tuple[ValidationRun, ...]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "pair_id": self.pair_id,
            "attempt_index": self.attempt_index,
            "phase": self.phase,
            "status": self.status,
            "reason": self.reason,
            "runs": [run.to_json_dict() for run in self.runs],
        }

    def to_canonical_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_json_dict())


@dataclass(frozen=True)
class ValidationResultV2:
    """One included or excluded pair with its complete bounded attempt history."""

    pair_id: str
    status: str
    buggy_sha: str
    fixed_sha: str
    accepted_attempt_id: str | None
    exclusion_reason: str | None
    attempts: tuple[ValidationAttempt, ...]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "pair_id": self.pair_id,
            "status": self.status,
            "buggy_sha": self.buggy_sha,
            "fixed_sha": self.fixed_sha,
            "accepted_attempt_id": self.accepted_attempt_id,
            "exclusion_reason": self.exclusion_reason,
            "attempts": [attempt.to_json_dict() for attempt in self.attempts],
        }

    def to_canonical_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_json_dict())


@dataclass(frozen=True)
class ValidationProvenanceEnvelope:
    """Authenticated local-controller envelope over a v2 receipt body."""

    envelope_version: str
    algorithm: str
    key_id: str
    payload_sha256: str
    authentication_tag: str

    def to_json_dict(self) -> dict[str, object]:
        return {
            "envelope_version": self.envelope_version,
            "algorithm": self.algorithm,
            "key_id": self.key_id,
            "payload_sha256": self.payload_sha256,
            "authentication_tag": self.authentication_tag,
        }


@dataclass(frozen=True)
class ValidationReceiptV2:
    """Current validation receipt bound to results, artifacts, and provenance."""

    schema_version: str
    protocol_version: str
    manifest_sha256: str
    validation_results_sha256: str
    artifact_manifest_sha256: str
    validated_pair_ids: tuple[str, ...]
    provenance_envelope: ValidationProvenanceEnvelope | None

    @property
    def authority(self) -> str:
        return "unverified"

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "protocol_version": self.protocol_version,
            "manifest_sha256": self.manifest_sha256,
            "validation_results_sha256": self.validation_results_sha256,
            "artifact_manifest_sha256": self.artifact_manifest_sha256,
            "validated_pair_ids": list(self.validated_pair_ids),
            "provenance_envelope": (
                None
                if self.provenance_envelope is None
                else self.provenance_envelope.to_json_dict()
            ),
        }

    def to_canonical_json_bytes(self) -> bytes:
        return _canonical_json_bytes(self.to_json_dict())


@dataclass(frozen=True)
class ValidationAuthorityCheck:
    """One independently reported validation-authority decision."""

    accepted: bool
    failure_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ValidationVerification:
    """Separated integrity, provenance, and semantic-policy decisions."""

    integrity: ValidationAuthorityCheck
    provenance: ValidationAuthorityCheck
    semantic_policy: ValidationAuthorityCheck
    _authority: str
    receipt: ValidationReceipt | ValidationReceiptV2 | None = None
    results: tuple[ValidationResultV2, ...] = ()
    _verifier_seal: object | None = dataclass_field(
        default=None, init=False, repr=False, compare=False
    )

    @property
    def authority(self) -> str:
        if (
            self._authority == "current_scoring_authority"
            and not _is_registered_verification(self)
        ):
            return "none"
        return self._authority

    def to_json_dict(self) -> dict[str, object]:
        return {
            "authority": self.authority,
            "integrity": {
                "accepted": self.integrity.accepted,
                "failure_paths": list(self.integrity.failure_paths),
            },
            "authorized_provenance": {
                "accepted": self.provenance.accepted,
                "failure_paths": list(self.provenance.failure_paths),
            },
            "semantic_policy": {
                "accepted": self.semantic_policy.accepted,
                "failure_paths": list(self.semantic_policy.failure_paths),
            },
        }


def _register_verification(
    verification: ValidationVerification,
) -> ValidationVerification:
    identity = id(verification)
    snapshot = _verification_authority_snapshot(verification)
    if snapshot is None:
        return verification

    def forget(reference: weakref.ReferenceType[object]) -> None:
        registered = _VERIFIED_CAPABILITIES.get(identity)
        if registered is not None and registered[0] is reference:
            _VERIFIED_CAPABILITIES.pop(identity, None)

    object.__setattr__(verification, "_verifier_seal", _VALIDATION_VERIFIER_SEAL)
    _VERIFIED_CAPABILITIES[identity] = (weakref.ref(verification, forget), snapshot)
    return verification


def _is_registered_verification(verification: ValidationVerification) -> bool:
    registered = _VERIFIED_CAPABILITIES.get(id(verification))
    snapshot = _verification_authority_snapshot(verification)
    return (
        type(verification) is ValidationVerification
        and verification._verifier_seal is _VALIDATION_VERIFIER_SEAL
        and registered is not None
        and registered[0]() is verification
        and snapshot is not None
        and snapshot == registered[1]
    )


def _verification_authority_snapshot(
    verification: ValidationVerification,
) -> bytes | None:
    """Freeze every authority-bearing field so verifier capabilities are immutable."""
    if (
        type(verification) is not ValidationVerification
        or type(verification.integrity) is not ValidationAuthorityCheck
        or type(verification.provenance) is not ValidationAuthorityCheck
        or type(verification.semantic_policy) is not ValidationAuthorityCheck
        or type(verification.results) is not tuple
        or any(type(result) is not ValidationResultV2 for result in verification.results)
    ):
        return None
    receipt = verification.receipt
    if type(receipt) is ValidationReceipt:
        receipt_kind = "v1"
        receipt_value: object = ValidationReceipt.to_json_dict(receipt)
    elif type(receipt) is ValidationReceiptV2:
        if receipt.provenance_envelope is not None and type(
            receipt.provenance_envelope
        ) is not ValidationProvenanceEnvelope:
            return None
        receipt_kind = "v2"
        receipt_value = ValidationReceiptV2.to_json_dict(receipt)
    elif receipt is None:
        receipt_kind = "none"
        receipt_value = None
    else:
        return None
    if not _validation_result_tree_is_exact(verification.results):
        return None
    document: object = {
        "integrity": {
            "accepted": verification.integrity.accepted,
            "failure_paths": list(verification.integrity.failure_paths),
        },
        "authorized_provenance": {
            "accepted": verification.provenance.accepted,
            "failure_paths": list(verification.provenance.failure_paths),
        },
        "semantic_policy": {
            "accepted": verification.semantic_policy.accepted,
            "failure_paths": list(verification.semantic_policy.failure_paths),
        },
        "authority": verification._authority,
        "receipt_kind": receipt_kind,
        "receipt": receipt_value,
        "results": [
            ValidationResultV2.to_json_dict(result) for result in verification.results
        ],
    }
    if not _is_exact_json_value(document):
        return None
    return _canonical_json_bytes(document)


def _validation_result_tree_is_exact(
    results: tuple[ValidationResultV2, ...],
) -> bool:
    for result in results:
        if type(result.attempts) is not tuple:
            return False
        for attempt in result.attempts:
            if type(attempt) is not ValidationAttempt or type(attempt.runs) is not tuple:
                return False
            for run in attempt.runs:
                if type(run) is not ValidationRun or type(run.artifacts) is not tuple:
                    return False
                for artifact in run.artifacts:
                    if (
                        type(artifact) is not tuple
                        or len(artifact) != 2
                        or type(artifact[1]) is not ArtifactRecord
                    ):
                        return False
    return True


def validation_receipt_binding_bytes(
    receipt: ValidationVerification | ValidationReceipt | ValidationReceiptV2,
) -> bytes:
    """Return canonical authority evidence for a paid-run predeclaration.

    A verifier capability binds its receipt, complete typed results, and the
    three independent authority decisions. The process-local verifier seal is
    deliberately excluded from persisted bytes, while copied or mutated
    current-authority capabilities are rejected before a provider can run.
    """
    if type(receipt) is ValidationReceipt:
        return ValidationReceipt.to_canonical_json_bytes(receipt)
    if type(receipt) is ValidationReceiptV2:
        return ValidationReceiptV2.to_canonical_json_bytes(receipt)
    if type(receipt) is not ValidationVerification:
        raise TypeError("receipt binding requires an exact validation receipt type")
    snapshot = _verification_authority_snapshot(receipt)
    if snapshot is None:
        raise ValueError("validation verification is not canonical receipt evidence")
    if (
        receipt._authority == "current_scoring_authority"
        and not _is_registered_verification(receipt)
    ):
        raise ValueError("current validation authority requires its verifier capability")
    return snapshot


def _is_exact_json_value(value: object) -> bool:
    if value is None or type(value) in {str, int, float, bool}:
        return True
    if type(value) is list:
        return all(_is_exact_json_value(item) for item in value)
    if type(value) is dict:
        return all(
            type(key) is str and _is_exact_json_value(item)
            for key, item in value.items()
        )
    return False


@dataclass(frozen=True)
class IsolationAdapter:
    """Immutable command wrapper claiming one verifiable isolation capability."""

    capability: str
    wrapper_argv: tuple[str, ...]
    wrapper_sha256: str


class IsolationError(ValueError):
    """The execution boundary could not prove network denial."""


class CorpusRunner(Protocol):
    """Execution boundary for generic prepared-corpus validation."""

    def run(
        self, source_id: str, tool: str, args: tuple[str, ...], cwd: Path
    ) -> RunOutcome:
        """Run one test command without a shell."""


class SubprocessCorpusRunner:
    """Run argv-only tests with caller-selected interpreters and bounded resources."""

    def __init__(
        self,
        interpreters: Mapping[str, tuple[str, ...]],
        *,
        allowed_tools: Mapping[tuple[str, str], tuple[str, ...]] | None = None,
        isolation: IsolationAdapter | None = None,
        timeout_s: float = 60,
        max_output_bytes: int = 65_536,
    ) -> None:
        if timeout_s <= 0 or max_output_bytes <= 0:
            raise ValueError("runner limits must be positive")
        self._interpreters = dict(interpreters)
        self._allowed_tools = dict(allowed_tools or {})
        self._isolation = isolation
        self._isolation_verified = False
        self._timeout_s = timeout_s
        self._max_output_bytes = max_output_bytes

    @property
    def isolation_verified(self) -> bool:
        """Return whether this runner passed its owned-boundary socket probe."""
        if not self._isolation_verified:
            return False
        try:
            self._validated_adapter()
        except IsolationError:
            return False
        return True

    def run(
        self, source_id: str, tool: str, args: tuple[str, ...], cwd: Path
    ) -> RunOutcome:
        interpreter = self._interpreters.get(source_id)
        if interpreter is None:
            raise ValueError(f"no interpreter configured for {source_id}")
        self._verify_isolation(interpreter, cwd)
        prefix = (
            interpreter
            if tool == "python"
            else self._allowed_tools.get((source_id, tool))
        )
        if prefix is None:
            raise ValueError(f"tool is not allowed: {tool}")
        _require_explicit_executable(prefix, tool)
        isolation = self._validated_adapter()
        command = (*isolation.wrapper_argv, *prefix, *args)
        if _is_pytest_command(tool, args):
            with tempfile.TemporaryDirectory(prefix="attest-validation-junit-") as directory:
                junit_path = Path(directory) / "junit.xml"
                actual_command = (*command, f"--junitxml={junit_path}")
                outcome = self._execute(
                    actual_command, cwd, self._timeout_s, execution_prefix=prefix
                )
                try:
                    junit = junit_path.read_bytes()
                except OSError:
                    junit = b""
                return RunOutcome(
                    outcome.returncode,
                    outcome.output,
                    outcome.timed_out,
                    junit,
                    actual_command,
                    outcome.environment,
                    outcome.execution_prefix,
                )
        return self._execute(command, cwd, self._timeout_s, execution_prefix=prefix)

    def _verify_isolation(self, interpreter: tuple[str, ...], cwd: Path) -> None:
        if self._isolation_verified:
            self._validated_adapter()
            return
        isolation = self._validated_adapter()
        _require_explicit_executable(interpreter, "python")
        probe = (
            "import socket,sys; s=socket.socket(); "
            "code=s.connect_ex(('127.0.0.1',int(sys.argv[1]))); "
            "raise SystemExit(73 if code == 0 else 0)"
        )
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            command = (
                *isolation.wrapper_argv,
                *interpreter,
                "-c",
                probe,
                str(port),
            )
            outcome = self._execute(
                command,
                cwd,
                min(self._timeout_s, 5.0),
                execution_prefix=interpreter,
            )
        if outcome.timed_out or outcome.returncode != 0:
            raise IsolationError("network isolation socket probe was not denied")
        self._isolation_verified = True

    def _validated_adapter(self) -> IsolationAdapter:
        isolation = self._isolation
        if isolation is None or isolation.capability != "attest.network-deny.v1":
            raise IsolationError("a verified network isolation capability is required")
        try:
            _require_explicit_executable(isolation.wrapper_argv, "isolation wrapper")
        except ValueError as exc:
            raise IsolationError(str(exc)) from exc
        wrapper = Path(isolation.wrapper_argv[0])
        if (
            re.fullmatch(r"[0-9a-f]{64}", isolation.wrapper_sha256) is None
            or hashlib.sha256(wrapper.read_bytes()).hexdigest()
            != isolation.wrapper_sha256
        ):
            raise IsolationError("isolation wrapper digest does not match")
        return isolation

    def _execute(
        self,
        command: tuple[str, ...],
        cwd: Path,
        timeout_s: float,
        *,
        execution_prefix: tuple[str, ...],
    ) -> RunOutcome:
        environment = {
            key: value
            for key, value in os.environ.items()
            if key in {"SYSTEMROOT", "TMPDIR", "TEMP", "TMP", "LANG", "LC_ALL"}
        }
        environment.update(
            {
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTEST_ADDOPTS": "-p no:cacheprovider",
            }
        )
        start_new_session = os.name == "posix"
        creationflags = (
            int(getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0))
            if os.name == "nt"
            else 0
        )
        process: subprocess.Popen[bytes] = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=0,
            start_new_session=start_new_session,
            creationflags=creationflags,
        )
        stdout = process.stdout
        assert stdout is not None
        tail = bytearray()

        def drain() -> None:
            while chunk := stdout.read(65_536):
                tail.extend(chunk)
                excess = len(tail) - self._max_output_bytes
                if excess > 0:
                    del tail[:excess]

        reader = threading.Thread(target=drain, daemon=True)
        reader.start()
        deadline = time.monotonic() + timeout_s
        timed_out = False
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
            reader.join(timeout=max(0.0, deadline - time.monotonic()))
            if reader.is_alive():
                raise subprocess.TimeoutExpired(list(command), timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            _kill_owned_process_tree(process)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:  # pragma: no cover - OS-level failure
                process.kill()
                process.wait()
            reader.join(timeout=1)
        finally:
            stdout.close()
        return RunOutcome(
            process.returncode,
            bytes(tail),
            timed_out,
            command=command,
            environment=tuple(sorted(environment.items())),
            execution_prefix=execution_prefix,
        )


def _require_explicit_executable(prefix: tuple[str, ...], tool: str) -> None:
    if not prefix:
        raise ValueError(f"empty executable mapping for {tool}")
    executable = Path(prefix[0])
    if not executable.is_absolute() or not executable.is_file() or not os.access(
        executable, os.X_OK
    ):
        raise ValueError(f"executable mapping for {tool} must use an absolute executable")


def _is_pytest_command(tool: str, args: tuple[str, ...]) -> bool:
    return tool == "pytest" or (tool == "python" and args[:2] == ("-m", "pytest"))


def _kill_owned_process_tree(process: subprocess.Popen[bytes]) -> None:
    """Kill only the process group/session created for this invocation."""
    if os.name == "posix":
        with suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
    elif os.name == "nt":  # pragma: no cover - exercised on Windows
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    elif process.poll() is None:  # pragma: no cover - exotic platforms
        process.kill()


def validate_corpus(
    manifest: Path,
    root: Path,
    runner: CorpusRunner,
    *,
    artifact_store: ArtifactStore | None = None,
    provenance_key_id: str | None = None,
    provenance_key: bytes | None = None,
) -> dict[str, Any]:
    """Validate prepared pairs and optionally issue an evidence-bearing v2 bundle."""
    manifest_bytes = _read_protocol_file(manifest)
    assert manifest_bytes is not None
    typed = load_manifest(manifest)
    runtimes = {runtime.case_id: runtime for runtime in typed.runtime}
    if set(runtimes) != {case.case_id for case in typed.cases}:
        raise ValueError("runtime rows must exactly cover manifest cases")

    by_pair: dict[str, list[Any]] = {}
    for case in typed.cases:
        by_pair.setdefault(case.pair_id, []).append(case)
    results: list[dict[str, Any]] = []
    results_v2: list[dict[str, object]] = []
    command_success = True
    for pair_id in sorted(by_pair):
        members = by_pair[pair_id]
        replay = next(case for case in members if case.role == "historical_bug_replay")
        control = next(case for case in members if case.role == "developer_fix_control")
        fixed_runs: list[RunOutcome] = []
        buggy_runs: list[RunOutcome] = []
        status = "excluded"
        reason: str | None = None
        signature = ""
        test_bytes = b""
        try:
            _verify_pair_integrity(root, replay, control, runtimes)
            test_bytes = _contained_file(root, replay.tests.relative_path).read_bytes()
            _run_three(
                control,
                runtimes[control.case_id],
                root,
                runner,
                fixed_runs,
            )
            reason = _fixed_failure_reason(fixed_runs)
            if reason is None:
                _run_three(
                    replay,
                    runtimes[replay.case_id],
                    root,
                    runner,
                    buggy_runs,
                )
                reason, signature = _buggy_failure_reason(
                    buggy_runs, artifact_store
                )
            if reason is None:
                status = "validated"
        except IsolationError:
            command_success = False
            reason = "isolation_unverified"
        except _IntegrityError as exc:
            reason = exc.reason
        except (OSError, subprocess.CalledProcessError, ValueError):
            reason = (
                "incomplete_execution"
                if fixed_runs or buggy_runs
                else "integrity_failure"
            )
        if status == "validated":
            results.append(
                {
                    "pair_id": pair_id,
                    "status": status,
                    "failure_signature": signature,
                    "fixed_runs": [_run_json(outcome) for outcome in fixed_runs],
                    "buggy_runs": [_run_json(outcome) for outcome in buggy_runs],
                }
            )
        else:
            assert reason is not None
            results.append({"pair_id": pair_id, "status": status, "reason": reason})
        if artifact_store is not None:
            results_v2.append(
                _validation_result_v2(
                    pair_id,
                    replay.buggy_commit,
                    control.fixed_commit,
                    status,
                    reason,
                    fixed_runs,
                    buggy_runs,
                    runner,
                    control.source_id,
                    replay.source_id,
                    runtimes[control.case_id],
                    runtimes[replay.case_id],
                    test_bytes,
                    artifact_store,
                )
            )
    validated_pair_ids = sorted(
        result["pair_id"] for result in results if result["status"] == "validated"
    )
    validated = len(validated_pair_ids)
    total = len(results)
    corpus_valid = total > 0 and validated == total
    validation_status = (
        "empty"
        if total == 0
        else "valid"
        if corpus_valid
        else "partial"
        if validated
        else "invalid"
    )
    manifest_sha256 = hashlib.sha256(manifest_bytes).hexdigest()
    validation_results: dict[str, object]
    if artifact_store is None:
        validation_results = {
            "schema_version": "1",
            "manifest_sha256": manifest_sha256,
            "results": results,
        }
    else:
        validation_results = {
            "schema_version": "2",
            "protocol_version": VALIDATION_PROTOCOL_V2,
            "manifest_sha256": manifest_sha256,
            "results": results_v2,
        }
    validation_results_bytes = _canonical_json_bytes(validation_results)
    if len(validation_results_bytes) > MAX_VALIDATION_DOCUMENT_BYTES:
        raise ArtifactError(
            "validation results exceed their protocol byte limit",
            failure_path="validation_results.size_bytes",
        )
    isolation_verified = (
        isinstance(runner, SubprocessCorpusRunner) and runner.isolation_verified
    )
    receipt: dict[str, object] | None = None
    if artifact_store is not None:
        artifact_manifest = artifact_store.finalize()
        if (
            provenance_key_id
            and provenance_key
            and (
                not validated_pair_ids
                or (command_success and isolation_verified)
            )
        ):
            receipt = _validation_receipt_v2(
                manifest_sha256,
                validation_results_bytes,
                hashlib.sha256(artifact_manifest.read_bytes()).hexdigest(),
                validated_pair_ids,
                provenance_key_id,
                provenance_key,
            )
    return {
        "manifest": manifest.name,
        "manifest_sha256": manifest_sha256,
        "command_success": command_success,
        "corpus_valid": corpus_valid,
        "validation_status": validation_status,
        "scorable": receipt is not None and bool(validated_pair_ids),
        "validated_pairs": validated,
        "excluded_pairs": total - validated,
        "results": results,
        "validation_results": validation_results,
        "receipt": receipt,
    }


def _validation_result_v2(
    pair_id: str,
    buggy_sha: str,
    fixed_sha: str,
    status: str,
    reason: str | None,
    fixed_runs: list[RunOutcome],
    buggy_runs: list[RunOutcome],
    runner: CorpusRunner,
    fixed_source_id: str,
    buggy_source_id: str,
    fixed_runtime: RuntimeDescriptor,
    buggy_runtime: RuntimeDescriptor,
    test_bytes: bytes,
    store: ArtifactStore,
) -> dict[str, object]:
    attempt_id = "attempt-" + hashlib.sha256(pair_id.encode("utf-8")).hexdigest()[:12]
    runs = [
        _persist_validation_run(
            pair_id,
            "fixed",
            fixed_sha,
            ordinal,
            outcome,
            runner,
            fixed_source_id,
            fixed_runtime,
            test_bytes,
            store,
        )
        for ordinal, outcome in enumerate(fixed_runs, 1)
    ]
    runs.extend(
        _persist_validation_run(
            pair_id,
            "buggy",
            buggy_sha,
            ordinal,
            outcome,
            runner,
            buggy_source_id,
            buggy_runtime,
            test_bytes,
            store,
        )
        for ordinal, outcome in enumerate(buggy_runs, 1)
    )
    return {
        "pair_id": pair_id,
        "status": status,
        "buggy_sha": buggy_sha,
        "fixed_sha": fixed_sha,
        "accepted_attempt_id": attempt_id if status == "validated" else None,
        "exclusion_reason": reason,
        "attempts": [
            {
                "attempt_id": attempt_id,
                "pair_id": pair_id,
                "attempt_index": 1,
                "phase": "execution" if runs else "preflight",
                "status": status,
                "reason": reason,
                "runs": runs,
            }
        ],
    }


def _persist_validation_run(
    pair_id: str,
    revision: str,
    repository_sha: str,
    ordinal: int,
    outcome: RunOutcome,
    runner: CorpusRunner,
    source_id: str,
    runtime: RuntimeDescriptor,
    test_bytes: bytes,
    store: ArtifactStore,
) -> dict[str, object]:
    runner_id, profile_id, interpreter, executor = _runner_evidence(
        runner, source_id, outcome.execution_prefix
    )
    prefix = f"runs/{pair_id}/{revision}-{ordinal}"
    command = outcome.command or (runtime.tool, *runtime.args)
    environment = dict(outcome.environment)
    records = {
        "stdout": store.write(
            f"{prefix}/stdout.txt", "validation_stdout", outcome.output
        ),
        "junit": store.write(
            f"{prefix}/junit.xml", "validation_junit", outcome.junit
        ),
        "test": store.write(
            f"{prefix}/test.txt", "validation_test", test_bytes
        ),
        "command": store.write(
            f"{prefix}/command.json",
            "validation_command",
            {
                "executed_argv": list(command),
                "declared_tool": runtime.tool,
                "declared_args": list(runtime.args),
                "declared_cwd": runtime.cwd,
            },
        ),
        "interpreter": store.write(
            f"{prefix}/interpreter.json", "validation_interpreter", interpreter
        ),
        "environment": store.write(
            f"{prefix}/environment.json",
            "validation_environment",
            {
                "variables": environment,
                "sha256": hashlib.sha256(canonical_json_bytes(environment)).hexdigest(),
            },
        ),
        "source": store.write(
            f"{prefix}/source.json",
            "validation_source",
            {"revision": revision, "repository_sha": repository_sha},
        ),
        "executor": store.write(
            f"{prefix}/executor.json", "validation_executor", executor
        ),
    }
    return {
        "run_id": f"run-{pair_id.removeprefix('pair-')}-{revision}-{ordinal}",
        "revision": revision,
        "ordinal": ordinal,
        "outcome": "fail" if outcome.timed_out or outcome.returncode != 0 else "pass",
        "returncode": outcome.returncode,
        "timed_out": outcome.timed_out,
        "failure_signature": (
            _failure_signature(read_artifact_bytes(store.root, records["stdout"].name))
            if outcome.returncode != 0 and not outcome.timed_out
            else None
        ),
        "runner_id": runner_id,
        "profile_id": profile_id,
        "artifacts": {
            name: record.to_json_dict() for name, record in records.items()
        },
    }


def _runner_evidence(
    runner: CorpusRunner, source_id: str, execution_prefix: tuple[str, ...]
) -> tuple[str, str, dict[str, object], dict[str, object]]:
    runner_id = f"{type(runner).__module__}.{type(runner).__qualname__}"
    if not isinstance(runner, SubprocessCorpusRunner):
        unverified_interpreter: dict[str, object] = {
            "argv": [],
            "executable_sha256": "0" * 64,
        }
        unverified_executor: dict[str, object] = {
            "runner_id": runner_id,
            "profile_id": "unverified",
            "isolation_capability": None,
            "executor_sha256": "0" * 64,
            "wrapper_argv": [],
        }
        return (
            runner_id,
            "unverified",
            unverified_interpreter,
            unverified_executor,
        )
    prefix = execution_prefix or runner._interpreters.get(source_id)
    prefix = prefix or ()
    executable = Path(prefix[0]) if prefix else None
    executable_digest = (
        hashlib.sha256(executable.read_bytes()).hexdigest()
        if executable is not None and executable.is_file()
        else "0" * 64
    )
    isolation = runner._isolation
    profile_id = (
        f"{isolation.capability}:{isolation.wrapper_sha256}"
        if isolation is not None
        else "unverified"
    )
    interpreter: dict[str, object] = {
        "argv": list(prefix),
        "executable_sha256": executable_digest,
    }
    executor: dict[str, object] = {
        "runner_id": runner_id,
        "profile_id": profile_id,
        "isolation_capability": None if isolation is None else isolation.capability,
        "executor_sha256": (
            "0" * 64 if isolation is None else isolation.wrapper_sha256
        ),
        "wrapper_argv": [] if isolation is None else list(isolation.wrapper_argv),
    }
    return runner_id, profile_id, interpreter, executor


def _validation_receipt_v2(
    manifest_sha256: str,
    validation_results_bytes: bytes,
    artifact_manifest_sha256: str,
    validated_pair_ids: list[str],
    key_id: str,
    key: bytes,
) -> dict[str, object]:
    body: dict[str, object] = {
        "schema_version": "2",
        "protocol_version": VALIDATION_PROTOCOL_V2,
        "manifest_sha256": manifest_sha256,
        "validation_results_sha256": hashlib.sha256(
            validation_results_bytes
        ).hexdigest(),
        "artifact_manifest_sha256": artifact_manifest_sha256,
        "validated_pair_ids": validated_pair_ids,
    }
    payload = _canonical_json_bytes(body)
    return {
        **body,
        "provenance_envelope": {
            "envelope_version": "1",
            "algorithm": "hmac-sha256",
            "key_id": key_id,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "authentication_tag": hmac.new(key, payload, hashlib.sha256).hexdigest(),
        },
    }


def _validation_receipt(
    manifest_sha256: str,
    validation_results_bytes: bytes,
    validated_pair_ids: list[str],
) -> dict[str, object]:
    return {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "validated_pair_ids": validated_pair_ids,
        "validation_results_sha256": hashlib.sha256(validation_results_bytes).hexdigest(),
    }


def _canonical_json_bytes(value: object) -> bytes:
    return canonical_json_bytes(value)


def verify_validation_receipt(
    path: Path,
    manifest: Path,
    validation_results: Path,
    artifact_root: Path,
    *,
    authorized_provenance_keys: Mapping[str, bytes],
) -> ValidationVerification:
    """Verify v2 integrity, authorized provenance, and semantics independently.

    This is the offline fail-closed boundary. It reports stable field/artifact
    paths instead of collapsing authentication, hashing, and oracle policy into
    one boolean.
    """
    integrity_failures: list[str] = []
    provenance_failures: list[str] = []
    semantic_failures: list[str] = []
    receipt_bytes, receipt_value = _read_canonical_document(
        path, "receipt", integrity_failures
    )
    results_bytes, results_value = _read_canonical_document(
        validation_results, "validation_results", integrity_failures
    )
    del receipt_bytes
    if not isinstance(receipt_value, dict):
        return _failed_validation_verification(
            integrity_failures or ["receipt"],
            ["receipt.provenance_envelope"],
            ["validation_results"],
        )
    if receipt_value.get("schema_version") != "2":
        path_name = "receipt.schema_version"
        return _failed_validation_verification(
            [path_name], [path_name], [path_name]
        )
    receipt = _parse_validation_receipt_v2(receipt_value, integrity_failures)
    _verify_v2_provenance_value(
        receipt_value,
        authorized_provenance_keys,
        provenance_failures,
    )
    results = _parse_validation_results_v2(
        results_value, semantic_failures, integrity_failures
    )
    manifest_bytes = _read_protocol_file(
        manifest, "manifest", integrity_failures, required=False
    )
    try:
        typed_manifest = load_manifest(manifest) if manifest_bytes is not None else None
    except (OSError, ValueError):
        typed_manifest = None
        integrity_failures.append("manifest")
    if receipt is not None:
        _verify_v2_integrity(
            receipt,
            receipt_value,
            manifest_bytes,
            results_bytes,
            results_value,
            results,
            artifact_root,
            typed_manifest,
            integrity_failures,
        )
        if receipt.protocol_version != VALIDATION_PROTOCOL_V2:
            semantic_failures.append("receipt.protocol_version")
    _verify_v2_semantics(results, artifact_root, typed_manifest, semantic_failures)
    integrity = ValidationAuthorityCheck(
        not integrity_failures, tuple(dict.fromkeys(integrity_failures))
    )
    provenance = ValidationAuthorityCheck(
        not provenance_failures, tuple(dict.fromkeys(provenance_failures))
    )
    semantic_policy = ValidationAuthorityCheck(
        not semantic_failures, tuple(dict.fromkeys(semantic_failures))
    )
    current = integrity.accepted and provenance.accepted and semantic_policy.accepted
    verification = ValidationVerification(
        integrity=integrity,
        provenance=provenance,
        semantic_policy=semantic_policy,
        _authority="current_scoring_authority" if current else "none",
        receipt=receipt,
        results=results,
    )
    return _register_verification(verification)


def load_validation_receipt_v2(
    path: Path,
    manifest: Path,
    validation_results: Path,
    artifact_root: Path,
    *,
    authorized_provenance_keys: Mapping[str, bytes],
) -> ValidationVerification:
    """Load only a fully authorized v2 receipt, raising its first exact failure path."""
    verification = verify_validation_receipt(
        path,
        manifest,
        validation_results,
        artifact_root,
        authorized_provenance_keys=authorized_provenance_keys,
    )
    for name, check in (
        ("integrity", verification.integrity),
        ("authorized_provenance", verification.provenance),
        ("semantic_policy", verification.semantic_policy),
    ):
        if not check.accepted:
            failure_path = check.failure_paths[0] if check.failure_paths else "unknown"
            raise ValueError(f"{name}:{failure_path}")
    return verification


def _failed_validation_verification(
    integrity: list[str], provenance: list[str], semantic_policy: list[str]
) -> ValidationVerification:
    verification = ValidationVerification(
        integrity=ValidationAuthorityCheck(False, tuple(integrity)),
        provenance=ValidationAuthorityCheck(False, tuple(provenance)),
        semantic_policy=ValidationAuthorityCheck(False, tuple(semantic_policy)),
        _authority="none",
    )
    return _register_verification(verification)


def _read_canonical_document(
    path: Path, failure_path: str, failures: list[str]
) -> tuple[bytes, object | None]:
    payload = _read_protocol_file(path, failure_path, failures, required=False)
    if payload is None:
        return b"", None
    try:
        value = json.loads(payload)
    except (json.JSONDecodeError, UnicodeError):
        failures.append(failure_path)
        return b"", None
    if payload != _canonical_json_bytes(value):
        failures.append(f"{failure_path}.canonical_json")
    return payload, value


def _read_protocol_file(
    path: Path,
    failure_path: str | None = None,
    failures: list[str] | None = None,
    *,
    required: bool = True,
) -> bytes | None:
    """Read a protocol document without ever allocating beyond its byte ceiling."""
    try:
        if path.stat().st_size > MAX_VALIDATION_DOCUMENT_BYTES:
            if failures is not None and failure_path is not None:
                failures.append(f"{failure_path}.size_bytes")
                return None
            raise ArtifactError(
                "validation document exceeds its protocol byte limit",
                failure_path=(
                    None if failure_path is None else f"{failure_path}.size_bytes"
                ),
            )
        with path.open("rb") as stream:
            payload = stream.read(MAX_VALIDATION_DOCUMENT_BYTES + 1)
    except OSError:
        if failures is not None and failure_path is not None:
            failures.append(failure_path)
            return None
        if required:
            raise
        return None
    if len(payload) > MAX_VALIDATION_DOCUMENT_BYTES:
        if failures is not None and failure_path is not None:
            failures.append(f"{failure_path}.size_bytes")
            return None
        raise ArtifactError(
            "validation document exceeds its protocol byte limit",
            failure_path=None if failure_path is None else f"{failure_path}.size_bytes",
        )
    return payload


def _parse_validation_receipt_v2(
    value: Mapping[str, object], failures: list[str]
) -> ValidationReceiptV2 | None:
    local_failures: list[str] = []
    expected_body = {
        "schema_version",
        "protocol_version",
        "manifest_sha256",
        "validation_results_sha256",
        "artifact_manifest_sha256",
        "validated_pair_ids",
    }
    if set(value) - {"provenance_envelope"} != expected_body:
        local_failures.append("receipt.fields")
    protocol = value.get("protocol_version")
    manifest_digest = value.get("manifest_sha256")
    results_digest = value.get("validation_results_sha256")
    artifact_digest = value.get("artifact_manifest_sha256")
    pair_ids = value.get("validated_pair_ids")
    for field, candidate in (
        ("manifest_sha256", manifest_digest),
        ("validation_results_sha256", results_digest),
        ("artifact_manifest_sha256", artifact_digest),
    ):
        if not _is_sha256(candidate):
            local_failures.append(f"receipt.{field}")
    if not isinstance(protocol, str) or not protocol:
        local_failures.append("receipt.protocol_version")
    if (
        not isinstance(pair_ids, list)
        or any(not isinstance(pair_id, str) for pair_id in pair_ids)
        or pair_ids != sorted(set(pair_ids))
    ):
        local_failures.append("receipt.validated_pair_ids")
    envelope = _parse_provenance_envelope(value.get("provenance_envelope"), [])
    failures.extend(local_failures)
    if (
        not isinstance(protocol, str)
        or not _is_sha256(manifest_digest)
        or not _is_sha256(results_digest)
        or not _is_sha256(artifact_digest)
        or not isinstance(pair_ids, list)
        or any(not isinstance(pair_id, str) for pair_id in pair_ids)
    ):
        return None
    assert isinstance(protocol, str)
    assert isinstance(manifest_digest, str)
    assert isinstance(results_digest, str)
    assert isinstance(artifact_digest, str)
    assert isinstance(pair_ids, list)
    return ValidationReceiptV2(
        schema_version="2",
        protocol_version=protocol,
        manifest_sha256=manifest_digest,
        validation_results_sha256=results_digest,
        artifact_manifest_sha256=artifact_digest,
        validated_pair_ids=tuple(pair_ids),
        provenance_envelope=envelope,
    )


def _parse_provenance_envelope(
    value: object, failures: list[str]
) -> ValidationProvenanceEnvelope | None:
    base = "receipt.provenance_envelope"
    expected = {
        "envelope_version",
        "algorithm",
        "key_id",
        "payload_sha256",
        "authentication_tag",
    }
    if not isinstance(value, dict):
        failures.append(base)
        return None
    if set(value) != expected:
        failures.append(f"{base}.fields")
    names = (
        "envelope_version",
        "algorithm",
        "key_id",
        "payload_sha256",
        "authentication_tag",
    )
    fields = tuple(value.get(name) for name in names)
    invalid = [name for name, item in zip(names, fields, strict=True) if not isinstance(item, str)]
    failures.extend(f"{base}.{name}" for name in invalid)
    if invalid:
        return None
    return ValidationProvenanceEnvelope(*fields)  # type: ignore[arg-type]


def _parse_validation_results_v2(
    value: object, failures: list[str], integrity_failures: list[str]
) -> tuple[ValidationResultV2, ...]:
    if not isinstance(value, dict) or value.get("schema_version") != "2":
        failures.append("validation_results.schema_version")
        return ()
    if set(value) != {
        "schema_version",
        "protocol_version",
        "manifest_sha256",
        "results",
    }:
        integrity_failures.append("validation_results.fields")
    rows = value.get("results")
    if not isinstance(rows, list):
        failures.append("validation_results.results")
        return ()
    parsed: list[ValidationResultV2] = []
    for index, row in enumerate(rows):
        base = f"validation_results.results[{index}]"
        if not isinstance(row, dict):
            failures.append(base)
            continue
        if set(row) != {
            "pair_id",
            "status",
            "buggy_sha",
            "fixed_sha",
            "accepted_attempt_id",
            "exclusion_reason",
            "attempts",
        }:
            integrity_failures.append(f"{base}.fields")
        attempts_value = row.get("attempts")
        if not isinstance(attempts_value, list) or not attempts_value:
            failures.append(f"{base}.attempts")
            continue
        attempts = _parse_validation_attempts(
            attempts_value, base, failures, integrity_failures
        )
        pair_id = row.get("pair_id")
        status = row.get("status")
        buggy_sha = row.get("buggy_sha")
        fixed_sha = row.get("fixed_sha")
        accepted_attempt_id = row.get("accepted_attempt_id")
        exclusion_reason = row.get("exclusion_reason")
        invalid: list[str] = []
        if not isinstance(pair_id, str):
            invalid.append("pair_id")
        if status not in {"validated", "excluded"}:
            invalid.append("status")
        if not isinstance(buggy_sha, str):
            invalid.append("buggy_sha")
        if not isinstance(fixed_sha, str):
            invalid.append("fixed_sha")
        if accepted_attempt_id is not None and not isinstance(
            accepted_attempt_id, str
        ):
            invalid.append("accepted_attempt_id")
        if exclusion_reason is not None and not isinstance(exclusion_reason, str):
            invalid.append("exclusion_reason")
        failures.extend(f"{base}.{field}" for field in invalid)
        if invalid:
            continue
        assert isinstance(pair_id, str)
        assert isinstance(status, str)
        assert isinstance(buggy_sha, str)
        assert isinstance(fixed_sha, str)
        parsed.append(
            ValidationResultV2(
                pair_id=pair_id,
                status=status,
                buggy_sha=buggy_sha,
                fixed_sha=fixed_sha,
                accepted_attempt_id=accepted_attempt_id,
                exclusion_reason=exclusion_reason,
                attempts=attempts,
            )
        )
    return tuple(parsed)


def _parse_validation_attempts(
    values: list[object],
    result_path: str,
    failures: list[str],
    integrity_failures: list[str],
) -> tuple[ValidationAttempt, ...]:
    parsed: list[ValidationAttempt] = []
    for index, value in enumerate(values):
        path = f"{result_path}.attempts[{index}]"
        if not isinstance(value, dict):
            failures.append(path)
            continue
        if set(value) != {
            "attempt_id",
            "pair_id",
            "attempt_index",
            "phase",
            "status",
            "reason",
            "runs",
        }:
            integrity_failures.append(f"{path}.fields")
        runs_value = value.get("runs")
        if not isinstance(runs_value, list):
            failures.append(f"{path}.runs")
            continue
        runs = _parse_validation_runs(
            runs_value, path, failures, integrity_failures
        )
        fields = (
            value.get("attempt_id"),
            value.get("pair_id"),
            value.get("attempt_index"),
            value.get("phase"),
            value.get("status"),
            value.get("reason"),
        )
        invalid: list[str] = []
        if not isinstance(fields[0], str):
            invalid.append("attempt_id")
        if not isinstance(fields[1], str):
            invalid.append("pair_id")
        if not isinstance(fields[2], int) or isinstance(fields[2], bool):
            invalid.append("attempt_index")
        if fields[3] not in {"preflight", "execution"}:
            invalid.append("phase")
        if fields[4] not in {"validated", "excluded"}:
            invalid.append("status")
        if fields[5] is not None and not isinstance(fields[5], str):
            invalid.append("reason")
        failures.extend(f"{path}.{field}" for field in invalid)
        if invalid:
            continue
        assert isinstance(fields[0], str)
        assert isinstance(fields[1], str)
        assert isinstance(fields[2], int)
        assert isinstance(fields[3], str)
        assert isinstance(fields[4], str)
        parsed.append(
            ValidationAttempt(
                attempt_id=fields[0],
                pair_id=fields[1],
                attempt_index=fields[2],
                phase=fields[3],
                status=fields[4],
                reason=fields[5],
                runs=runs,
            )
        )
    return tuple(parsed)


def _parse_validation_runs(
    values: list[object],
    attempt_path: str,
    failures: list[str],
    integrity_failures: list[str],
) -> tuple[ValidationRun, ...]:
    parsed: list[ValidationRun] = []
    for index, value in enumerate(values):
        path = f"{attempt_path}.runs[{index}]"
        if not isinstance(value, dict):
            failures.append(path)
            continue
        if set(value) != {
            "run_id",
            "revision",
            "ordinal",
            "outcome",
            "returncode",
            "timed_out",
            "failure_signature",
            "runner_id",
            "profile_id",
            "artifacts",
        }:
            integrity_failures.append(f"{path}.fields")
        artifacts_value = value.get("artifacts")
        artifacts = _parse_run_artifacts(artifacts_value, path, failures)
        fields = (
            value.get("run_id"),
            value.get("revision"),
            value.get("ordinal"),
            value.get("outcome"),
            value.get("returncode"),
            value.get("timed_out"),
            value.get("failure_signature"),
            value.get("runner_id"),
            value.get("profile_id"),
        )
        invalid: list[str] = []
        if not isinstance(fields[0], str):
            invalid.append("run_id")
        if fields[1] not in {"fixed", "buggy"}:
            invalid.append("revision")
        if not isinstance(fields[2], int) or isinstance(fields[2], bool):
            invalid.append("ordinal")
        if fields[3] not in {"pass", "fail"}:
            invalid.append("outcome")
        if not isinstance(fields[4], int) or isinstance(fields[4], bool):
            invalid.append("returncode")
        if not isinstance(fields[5], bool):
            invalid.append("timed_out")
        if fields[6] is not None and not isinstance(fields[6], str):
            invalid.append("failure_signature")
        if not isinstance(fields[7], str):
            invalid.append("runner_id")
        if not isinstance(fields[8], str):
            invalid.append("profile_id")
        failures.extend(f"{path}.{field}" for field in invalid)
        if invalid:
            continue
        assert isinstance(fields[0], str)
        assert isinstance(fields[1], str)
        assert isinstance(fields[2], int)
        assert isinstance(fields[3], str)
        assert isinstance(fields[4], int)
        assert isinstance(fields[5], bool)
        assert isinstance(fields[7], str)
        assert isinstance(fields[8], str)
        parsed.append(
            ValidationRun(
                run_id=fields[0],
                revision=fields[1],
                ordinal=fields[2],
                outcome=fields[3],
                returncode=fields[4],
                timed_out=fields[5],
                failure_signature=fields[6],
                runner_id=fields[7],
                profile_id=fields[8],
                artifacts=artifacts,
            )
        )
    return tuple(parsed)


def _parse_run_artifacts(
    value: object, run_path: str, failures: list[str]
) -> tuple[tuple[str, ArtifactRecord], ...]:
    expected = {
        "stdout": "validation_stdout",
        "junit": "validation_junit",
        "test": "validation_test",
        "command": "validation_command",
        "interpreter": "validation_interpreter",
        "environment": "validation_environment",
        "source": "validation_source",
        "executor": "validation_executor",
    }
    if not isinstance(value, dict) or set(value) != set(expected):
        failures.append(f"{run_path}.artifacts")
        return ()
    parsed: list[tuple[str, ArtifactRecord]] = []
    for name, expected_kind in expected.items():
        entry = value.get(name)
        path = f"{run_path}.artifacts.{name}"
        if not isinstance(entry, dict) or set(entry) != {
            "name", "kind", "sha256", "size_bytes", "truncated"
        }:
            failures.append(f"{path}.fields")
            continue
        invalid: list[str] = []
        if not isinstance(entry.get("name"), str):
            invalid.append("name")
        if entry.get("kind") != expected_kind:
            invalid.append("kind")
        if not _is_sha256(entry.get("sha256")):
            invalid.append("sha256")
        size = entry.get("size_bytes")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            invalid.append("size_bytes")
        if not isinstance(entry.get("truncated"), bool):
            invalid.append("truncated")
        failures.extend(f"{path}.{field}" for field in invalid)
        if invalid:
            continue
        try:
            record = ArtifactRecord(
                name=entry["name"],
                kind=entry["kind"],
                sha256=entry["sha256"],
                size_bytes=entry["size_bytes"],
                truncated=entry["truncated"],
            )
        except ArtifactError:
            failures.append(f"{path}.name")
            continue
        parsed.append((name, record))
    return tuple(parsed)


def _verify_v2_integrity(
    receipt: ValidationReceiptV2,
    receipt_value: Mapping[str, object],
    manifest_bytes: bytes | None,
    results_bytes: bytes,
    results_value: object,
    results: tuple[ValidationResultV2, ...],
    artifact_root: Path,
    typed_manifest: BenchmarkManifest | None,
    failures: list[str],
) -> None:
    if manifest_bytes is None or (
        hashlib.sha256(manifest_bytes).hexdigest() != receipt.manifest_sha256
    ):
        failures.append("receipt.manifest_sha256")
    if hashlib.sha256(results_bytes).hexdigest() != receipt.validation_results_sha256:
        failures.append("receipt.validation_results_sha256")
    if isinstance(results_value, dict):
        if results_value.get("protocol_version") != receipt.protocol_version:
            failures.append("validation_results.protocol_version")
        if results_value.get("manifest_sha256") != receipt.manifest_sha256:
            failures.append("validation_results.manifest_sha256")
    try:
        artifact_manifest_bytes = read_artifact_bytes(
            artifact_root,
            "artifacts.json",
            max_bytes=MAX_ARTIFACT_MANIFEST_BYTES,
        )
        artifact_manifest_value = json.loads(artifact_manifest_bytes)
    except (ArtifactError, json.JSONDecodeError, UnicodeError) as exc:
        failures.append(
            "artifacts.manifest.size_bytes"
            if isinstance(exc, ArtifactError) and "byte limit" in str(exc)
            else "artifacts.manifest"
        )
        records: tuple[ArtifactRecord, ...] = ()
        records_verified = False
    else:
        if artifact_manifest_bytes != _canonical_json_bytes(artifact_manifest_value):
            failures.append("artifacts.manifest.canonical_json")
        if (
            hashlib.sha256(artifact_manifest_bytes).hexdigest()
            != receipt.artifact_manifest_sha256
        ):
            failures.append("receipt.artifact_manifest_sha256")
        try:
            records = verify_artifacts(artifact_root)
        except ArtifactError as exc:
            failures.append(exc.failure_path or _artifact_error_path(str(exc)))
            records = ()
            records_verified = False
        else:
            records_verified = True
    if records_verified:
        indexed = {record.name: record for record in records}
        for result_index, result in enumerate(results):
            for attempt_index, attempt in enumerate(result.attempts):
                for run_index, run in enumerate(attempt.runs):
                    for name, reference in run.artifacts:
                        path = (
                            f"validation_results.results[{result_index}].attempts"
                            f"[{attempt_index}].runs[{run_index}].artifacts.{name}"
                        )
                        if indexed.get(reference.name) != reference:
                            failures.append(path)
    pair_ids = [result.pair_id for result in results]
    if len(pair_ids) != len(set(pair_ids)):
        failures.append("validation_results.results.pair_id")
    manifest_pair_ids = (
        set()
        if typed_manifest is None
        else {case.pair_id for case in typed_manifest.cases}
    )
    if set(pair_ids) != manifest_pair_ids:
        failures.append("validation_results.results.pair_id")
    validated = sorted(result.pair_id for result in results if result.status == "validated")
    if list(receipt.validated_pair_ids) != validated:
        failures.append("receipt.validated_pair_ids")
    if set(receipt_value) - {"provenance_envelope"} != {
        "schema_version",
        "protocol_version",
        "manifest_sha256",
        "validation_results_sha256",
        "artifact_manifest_sha256",
        "validated_pair_ids",
    }:
        failures.append("receipt.fields")


def _verify_v2_provenance_value(
    receipt_value: Mapping[str, object],
    authorized_keys: Mapping[str, bytes],
    failures: list[str],
) -> None:
    envelope = _parse_provenance_envelope(
        receipt_value.get("provenance_envelope"), failures
    )
    if envelope is None:
        failures.append("receipt.provenance_envelope")
        return
    if envelope.envelope_version != "1":
        failures.append("receipt.provenance_envelope.envelope_version")
    if envelope.algorithm != "hmac-sha256":
        failures.append("receipt.provenance_envelope.algorithm")
    key = authorized_keys.get(envelope.key_id)
    if key is None:
        failures.append("receipt.provenance_envelope.key_id")
        return
    body = {
        key_name: value
        for key_name, value in receipt_value.items()
        if key_name != "provenance_envelope"
    }
    payload = _canonical_json_bytes(body)
    if envelope.payload_sha256 != hashlib.sha256(payload).hexdigest():
        failures.append("receipt.provenance_envelope.payload_sha256")
    expected = hmac.new(key, payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(envelope.authentication_tag, expected):
        failures.append("receipt.provenance_envelope.authentication_tag")


def _verify_v2_semantics(
    results: tuple[ValidationResultV2, ...],
    artifact_root: Path,
    manifest: BenchmarkManifest | None,
    failures: list[str],
) -> None:
    manifest_pairs: dict[str, tuple[BenchmarkCase, ...]] = {}
    runtimes: dict[str, RuntimeDescriptor] = {}
    if manifest is not None:
        runtimes = {runtime.case_id: runtime for runtime in manifest.runtime}
        for case in manifest.cases:
            manifest_pairs.setdefault(case.pair_id, ())
            manifest_pairs[case.pair_id] += (case,)
    for result_index, result in enumerate(results):
        base = f"validation_results.results[{result_index}]"
        if not _is_commit(result.buggy_sha):
            failures.append(f"{base}.buggy_sha")
        if not _is_commit(result.fixed_sha):
            failures.append(f"{base}.fixed_sha")
        pair_cases = manifest_pairs.get(result.pair_id, ())
        replay = next(
            (case for case in pair_cases if case.role == "historical_bug_replay"),
            None,
        )
        control = next(
            (case for case in pair_cases if case.role == "developer_fix_control"),
            None,
        )
        if replay is not None and result.buggy_sha != replay.buggy_commit:
            failures.append(f"{base}.buggy_sha")
        if control is not None and result.fixed_sha != control.fixed_commit:
            failures.append(f"{base}.fixed_sha")
        if len(result.attempts) != 1:
            failures.append(f"{base}.attempts")
            continue
        if tuple(attempt.attempt_index for attempt in result.attempts) != tuple(
            range(1, len(result.attempts) + 1)
        ):
            failures.append(f"{base}.attempts.attempt_index")
        attempt_ids = [attempt.attempt_id for attempt in result.attempts]
        if len(attempt_ids) != len(set(attempt_ids)):
            failures.append(f"{base}.attempts.attempt_id")
        for attempt_index, attempt in enumerate(result.attempts):
            attempt_path = f"{base}.attempts[{attempt_index}]"
            if attempt.pair_id != result.pair_id:
                failures.append(f"{attempt_path}.pair_id")
            if attempt.phase == "execution" and not attempt.runs:
                failures.append(f"{attempt_path}.runs")
            if attempt.phase == "preflight" and attempt.runs:
                failures.append(f"{attempt_path}.runs")
        if result.status == "excluded":
            if result.accepted_attempt_id is not None:
                failures.append(f"{base}.accepted_attempt_id")
            if not result.exclusion_reason:
                failures.append(f"{base}.exclusion_reason")
            for attempt_index, attempt in enumerate(result.attempts):
                attempt_path = f"{base}.attempts[{attempt_index}]"
                if attempt.status != "excluded":
                    failures.append(f"{attempt_path}.status")
                if not attempt.reason:
                    failures.append(f"{attempt_path}.reason")
                if len(attempt.runs) > 6:
                    failures.append(f"{attempt_path}.runs")
                _verify_excluded_attempt(
                    result,
                    attempt,
                    artifact_root,
                    base,
                    attempt_path,
                    pair_cases,
                    runtimes,
                    failures,
                )
            if result.attempts[-1].reason != result.exclusion_reason:
                failures.append(f"{base}.attempts[-1].reason")
            continue
        if result.exclusion_reason is not None:
            failures.append(f"{base}.exclusion_reason")
        accepted = tuple(
            (attempt_index, attempt)
            for attempt_index, attempt in enumerate(result.attempts)
            if attempt.attempt_id == result.accepted_attempt_id
        )
        if len(accepted) != 1 or accepted[0][1].status != "validated":
            failures.append(f"{base}.accepted_attempt_id")
            continue
        accepted_index, accepted_attempt = accepted[0]
        accepted_path = f"{base}.attempts[{accepted_index}]"
        for attempt_index, attempt in enumerate(result.attempts):
            if attempt_index == accepted_index:
                continue
            attempt_path = f"{base}.attempts[{attempt_index}]"
            if attempt.status != "excluded":
                failures.append(f"{attempt_path}.status")
            if not attempt.reason:
                failures.append(f"{attempt_path}.reason")
            _verify_excluded_attempt(
                result,
                attempt,
                artifact_root,
                base,
                attempt_path,
                pair_cases,
                runtimes,
                failures,
            )
        if accepted_attempt.phase != "execution":
            failures.append(f"{accepted_path}.phase")
        if accepted_attempt.reason is not None:
            failures.append(f"{accepted_path}.reason")
        _verify_validated_attempt(
            result,
            accepted_attempt,
            artifact_root,
            base,
            accepted_path,
            pair_cases,
            runtimes,
            failures,
        )


def _verify_excluded_attempt(
    result: ValidationResultV2,
    attempt: ValidationAttempt,
    artifact_root: Path,
    result_path: str,
    attempt_path: str,
    pair_cases: tuple[BenchmarkCase, ...],
    runtimes: Mapping[str, RuntimeDescriptor],
    failures: list[str],
) -> None:
    runs = attempt.runs
    if not runs:
        if (
            attempt.phase != "preflight"
            or attempt.reason not in _PREFLIGHT_EXCLUSION_REASONS
        ):
            failures.append(f"{result_path}.exclusion_reason")
        return
    if len(runs) > 6:
        return
    if any(not _has_complete_run_artifacts(run) for run in runs):
        return
    expected_sequence = (
        ("fixed", 1),
        ("fixed", 2),
        ("fixed", 3),
        ("buggy", 1),
        ("buggy", 2),
        ("buggy", 3),
    )
    if tuple((run.revision, run.ordinal) for run in runs) != expected_sequence[
        : len(runs)
    ]:
        failures.append(f"{attempt_path}.runs")
    if (
        attempt.phase != "execution"
        or attempt.reason not in _EXECUTION_EXCLUSION_REASONS
    ):
        failures.append(f"{result_path}.exclusion_reason")
    run_ids = [run.run_id for run in runs]
    if len(run_ids) != len(set(run_ids)):
        failures.append(f"{attempt_path}.runs.run_id")
    for revision in ("fixed", "buggy"):
        ordinals = [run.ordinal for run in runs if run.revision == revision]
        if len(ordinals) != len(set(ordinals)) or any(
            ordinal not in {1, 2, 3} for ordinal in ordinals
        ):
            failures.append(f"{attempt_path}.runs.{revision}.ordinal")
    for index, run in enumerate(runs):
        path = f"{attempt_path}.runs[{index}]"
        if run.timed_out:
            if (
                run.outcome != "fail"
                or run.returncode == 0
                or run.failure_signature is not None
            ):
                failures.append(f"{path}.outcome")
        elif run.returncode == 0:
            if run.outcome != "pass" or run.failure_signature is not None:
                failures.append(f"{path}.outcome")
        elif run.outcome != "fail" or (
            run.failure_signature is not None
            and not _is_sha256(run.failure_signature)
        ):
            failures.append(f"{path}.outcome")
        if not run.timed_out or _run_artifact(run, "junit").size_bytes > 0:
            _verify_run_artifact_semantics(run, artifact_root, path, failures)
    derived_reason = _derive_execution_exclusion_reason(runs, artifact_root)
    if derived_reason != attempt.reason or derived_reason != result.exclusion_reason:
        failures.append(f"{result_path}.exclusion_reason")
    _verify_run_bindings(
        result,
        runs,
        artifact_root,
        result_path,
        attempt_path,
        pair_cases,
        runtimes,
        failures,
    )


def _verify_validated_attempt(
    result: ValidationResultV2,
    attempt: ValidationAttempt,
    artifact_root: Path,
    result_path: str,
    attempt_path: str,
    pair_cases: tuple[BenchmarkCase, ...],
    runtimes: Mapping[str, RuntimeDescriptor],
    failures: list[str],
) -> None:
    runs = attempt.runs
    if len(runs) != 6:
        failures.append(f"{attempt_path}.runs")
        return
    if any(not _has_complete_run_artifacts(run) for run in runs):
        return
    if tuple((run.revision, run.ordinal) for run in runs) != (
        ("fixed", 1),
        ("fixed", 2),
        ("fixed", 3),
        ("buggy", 1),
        ("buggy", 2),
        ("buggy", 3),
    ):
        failures.append(f"{attempt_path}.runs")
    run_ids = [run.run_id for run in runs]
    if len(run_ids) != len(set(run_ids)):
        failures.append(f"{attempt_path}.runs.run_id")
    fixed = tuple(run for run in runs if run.revision == "fixed")
    buggy = tuple(run for run in runs if run.revision == "buggy")
    if tuple(run.ordinal for run in fixed) != (1, 2, 3):
        failures.append(f"{attempt_path}.runs.fixed.ordinal")
    if tuple(run.ordinal for run in buggy) != (1, 2, 3):
        failures.append(f"{attempt_path}.runs.buggy.ordinal")
    for index, run in enumerate(runs):
        path = f"{attempt_path}.runs[{index}]"
        if run.timed_out:
            failures.append(f"{path}.timed_out")
        if run.revision == "fixed":
            if run.outcome != "pass" or run.returncode != 0 or run.failure_signature is not None:
                failures.append(f"{path}.outcome")
        elif (
            run.outcome != "fail"
            or run.returncode == 0
            or not _is_sha256(run.failure_signature)
        ):
            failures.append(f"{path}.outcome")
        _verify_run_artifact_semantics(run, artifact_root, path, failures)
    buggy_signatures = {run.failure_signature for run in buggy}
    if len(buggy_signatures) != 1:
        failures.append(f"{attempt_path}.runs.buggy.failure_signature")
    _verify_run_bindings(
        result,
        runs,
        artifact_root,
        result_path,
        attempt_path,
        pair_cases,
        runtimes,
        failures,
    )


def _derive_execution_exclusion_reason(
    runs: tuple[ValidationRun, ...], artifact_root: Path
) -> str | None:
    expected_sequence = (
        ("fixed", 1),
        ("fixed", 2),
        ("fixed", 3),
        ("buggy", 1),
        ("buggy", 2),
        ("buggy", 3),
    )
    if tuple((run.revision, run.ordinal) for run in runs) != expected_sequence[
        : len(runs)
    ]:
        return None
    timed_out = [index for index, run in enumerate(runs) if run.timed_out]
    if timed_out:
        return "timeout" if timed_out == [len(runs) - 1] else None
    fixed = tuple(run for run in runs if run.revision == "fixed")
    buggy = tuple(run for run in runs if run.revision == "buggy")
    fixed_failures = [index for index, run in enumerate(fixed) if run.returncode != 0]
    if fixed_failures:
        return (
            "dependency_or_setup_failure"
            if fixed_failures == [len(fixed) - 1] and not buggy
            else None
        )
    if len(fixed) < 3 or len(buggy) < 3:
        return "incomplete_execution"
    if any(run.returncode == 0 for run in buggy):
        return "flaky"
    signatures = [
        _failure_signature(
            _artifact_bytes(artifact_root, _run_artifact(run, "stdout"))
        )
        for run in buggy
    ]
    if any(signature is None for signature in signatures):
        return "dependency_or_setup_failure"
    if len(set(signatures)) != 1:
        return "inconsistent_failure_signature"
    return None


def _verify_run_bindings(
    result: ValidationResultV2,
    runs: tuple[ValidationRun, ...],
    artifact_root: Path,
    result_path: str,
    attempt_path: str,
    pair_cases: tuple[BenchmarkCase, ...],
    runtimes: Mapping[str, RuntimeDescriptor],
    failures: list[str],
) -> None:
    for index, run in enumerate(runs):
        path = f"{attempt_path}.runs[{index}]"
        role = (
            "developer_fix_control"
            if run.revision == "fixed"
            else "historical_bug_replay"
        )
        case = next((candidate for candidate in pair_cases if candidate.role == role), None)
        runtime = None if case is None else runtimes.get(case.case_id)

        executor = _read_artifact_json(artifact_root, _run_artifact(run, "executor"))
        if executor.get("runner_id") != run.runner_id:
            failures.append(f"{path}.runner_id")
        if executor.get("profile_id") != run.profile_id:
            failures.append(f"{path}.profile_id")
        capability = executor.get("isolation_capability")
        executor_digest = executor.get("executor_sha256")
        wrapper_argv = executor.get("wrapper_argv")
        expected_profile = (
            f"{capability}:{executor_digest}"
            if capability == "attest.network-deny.v1" and _is_sha256(executor_digest)
            else None
        )
        if (
            set(executor)
            != {
                "runner_id",
                "profile_id",
                "isolation_capability",
                "executor_sha256",
                "wrapper_argv",
            }
            or expected_profile != run.profile_id
            or not _is_string_list(wrapper_argv)
            or not wrapper_argv
        ):
            failures.append(f"{path}.artifacts.executor")

        interpreter = _read_artifact_json(
            artifact_root, _run_artifact(run, "interpreter")
        )
        interpreter_argv = interpreter.get("argv")
        if (
            set(interpreter) != {"argv", "executable_sha256"}
            or not _is_string_list(interpreter_argv)
            or not interpreter_argv
            or not _is_sha256(interpreter.get("executable_sha256"))
        ):
            failures.append(f"{path}.artifacts.interpreter")

        environment = _read_artifact_json(
            artifact_root, _run_artifact(run, "environment")
        )
        variables = environment.get("variables")
        if (
            set(environment) != {"variables", "sha256"}
            or not isinstance(variables, dict)
            or any(
                not isinstance(key, str) or not isinstance(value, str)
                for key, value in variables.items()
            )
            or environment.get("sha256")
            != hashlib.sha256(_canonical_json_bytes(variables)).hexdigest()
        ):
            failures.append(f"{path}.artifacts.environment")

        command = _read_artifact_json(artifact_root, _run_artifact(run, "command"))
        executed_argv = command.get("executed_argv")
        if (
            runtime is None
            or set(command)
            != {"executed_argv", "declared_tool", "declared_args", "declared_cwd"}
            or not _is_string_list(executed_argv)
            or not executed_argv
            or command.get("declared_tool") != runtime.tool
            or command.get("declared_args") != list(runtime.args)
            or command.get("declared_cwd") != runtime.cwd
        ):
            failures.append(f"{path}.artifacts.command")
        elif _is_string_list(wrapper_argv) and _is_string_list(interpreter_argv) and not (
            _matches_issued_command(
                executed_argv,
                wrapper_argv,
                interpreter_argv,
                runtime,
            )
        ):
            failures.append(f"{path}.artifacts.command.executed_argv")

        if case is not None:
            test = _run_artifact(run, "test")
            try:
                test_bytes = read_artifact_bytes(artifact_root, test.name)
            except ArtifactError:
                test_bytes = b""
            if not verify_descriptor_bytes(case.tests, test_bytes):
                failures.append(f"{path}.artifacts.test")
            elif runtime is not None:
                try:
                    declared_test_command = _command_from_test_descriptor(test_bytes)
                except _Excluded:
                    failures.append(f"{path}.artifacts.test")
                else:
                    if declared_test_command != {
                        "tool": runtime.tool,
                        "args": list(runtime.args),
                    }:
                        failures.append(f"{path}.artifacts.command")
    for field in ("runner_id", "profile_id"):
        values = {getattr(run, field) for run in runs}
        if len(values) != 1:
            mismatch = next(
                index
                for index, run in enumerate(runs)
                if getattr(run, field) != getattr(runs[0], field)
            )
            failures.append(f"{attempt_path}.runs[{mismatch}].{field}")
    for artifact_name in ("test", "interpreter", "environment", "executor"):
        digests = [_run_artifact(run, artifact_name).sha256 for run in runs]
        if len(set(digests)) != 1:
            mismatch = next(index for index, digest in enumerate(digests) if digest != digests[0])
            failures.append(
                f"{attempt_path}.runs[{mismatch}].artifacts.{artifact_name}"
            )
    for revision, repository_sha in (
        ("fixed", result.fixed_sha),
        ("buggy", result.buggy_sha),
    ):
        revision_runs = tuple(run for run in runs if run.revision == revision)
        if not revision_runs:
            continue
        sources = [_run_artifact(run, "source") for run in revision_runs]
        if len({source.sha256 for source in sources}) != 1:
            failures.append(f"{attempt_path}.runs.{revision}.artifacts.source")
            continue
        source = _read_artifact_json(artifact_root, sources[0])
        if (
            set(source) != {"revision", "repository_sha"}
            or source.get("revision") != revision
            or source.get("repository_sha") != repository_sha
        ):
            if set(source) != {"revision", "repository_sha"}:
                first_index = next(
                    index for index, run in enumerate(runs) if run.revision == revision
                )
                failures.append(
                    f"{attempt_path}.runs[{first_index}].artifacts.source"
                )
            else:
                failures.append(f"{result_path}.{revision}_sha")


def _matches_issued_command(
    executed_argv: list[str],
    wrapper_argv: list[str],
    interpreter_argv: list[str],
    runtime: RuntimeDescriptor,
) -> bool:
    prefix = [*wrapper_argv, *interpreter_argv, *runtime.args]
    if executed_argv[: len(prefix)] != prefix:
        return False
    suffix = executed_argv[len(prefix) :]
    if _is_pytest_command(runtime.tool, runtime.args):
        return len(suffix) == 1 and suffix[0].startswith("--junitxml=") and bool(
            suffix[0].removeprefix("--junitxml=")
        )
    return not suffix


def _is_string_list(value: object) -> TypeGuard[list[str]]:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


def _verify_run_artifact_semantics(
    run: ValidationRun, artifact_root: Path, path: str, failures: list[str]
) -> None:
    stdout = _run_artifact(run, "stdout")
    junit = _run_artifact(run, "junit")
    if stdout.size_bytes <= 0:
        failures.append(f"{path}.artifacts.stdout")
    if junit.size_bytes <= 0:
        failures.append(f"{path}.artifacts.junit")
        return
    try:
        stdout_bytes = read_artifact_bytes(artifact_root, stdout.name)
    except ArtifactError:
        stdout_bytes = b""
    if (
        run.outcome == "fail"
        and not run.timed_out
        and _failure_signature(stdout_bytes) != run.failure_signature
    ):
        failures.append(f"{path}.failure_signature")
    try:
        counts = validation_junit_counts(read_artifact_bytes(artifact_root, junit.name))
    except ArtifactError:
        counts = None
    if counts is None:
        failures.append(f"{path}.artifacts.junit")
        return
    tests, failures_count, errors, skipped = counts
    junit_passed = tests == 1 and failures_count == 0 and errors == 0 and skipped == 0
    junit_failed = tests == 1 and failures_count + errors == 1 and skipped == 0
    if (run.outcome == "pass" and not junit_passed) or (
        run.outcome == "fail" and not junit_failed
    ):
        failures.append(f"{path}.artifacts.junit")


def _run_artifact(run: ValidationRun, name: str) -> ArtifactRecord:
    return dict(run.artifacts)[name]


def _has_complete_run_artifacts(run: ValidationRun) -> bool:
    return set(dict(run.artifacts)) == _VALIDATION_RUN_ARTIFACT_NAMES


def _read_artifact_json(root: Path, record: ArtifactRecord) -> dict[str, object]:
    try:
        value = json.loads(read_artifact_bytes(root, record.name))
    except (ArtifactError, json.JSONDecodeError, UnicodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _artifact_bytes(root: Path, record: ArtifactRecord) -> bytes:
    try:
        return read_artifact_bytes(root, record.name)
    except ArtifactError:
        return b""


def _artifact_error_path(message: str) -> str:
    for pattern, suffix in (
        (r"^artifact (.+) digest does not match", ".sha256"),
        (r"^artifact (.+) size does not match", ".size_bytes"),
        (r"^artifact (.+) is missing$", ""),
        (r"^unknown artifact (.+) is not listed", ""),
    ):
        match = re.search(pattern, message)
        if match is not None:
            return f"artifacts.{match.group(1)}{suffix}"
    if "manifest" in message:
        return "artifacts.manifest"
    return "artifacts"


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _is_commit(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None


def load_validation_receipt(
    path: Path, manifest: Path, validation_results: Path
) -> ValidationReceipt:
    """Derive the allowlist from exact manifest-bound validation-results bytes."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("validation receipt must be valid JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "manifest_sha256",
        "validated_pair_ids",
        "validation_results_sha256",
    }:
        raise ValueError("validation receipt has invalid fields")
    schema_version = value["schema_version"]
    manifest_sha256 = value["manifest_sha256"]
    result_sha256 = value["validation_results_sha256"]
    pair_ids = value["validated_pair_ids"]
    if schema_version != "1":
        raise ValueError("unsupported validation receipt schema")
    if not isinstance(manifest_sha256, str) or re.fullmatch(
        r"[0-9a-f]{64}", manifest_sha256
    ) is None:
        raise ValueError("validation receipt manifest digest is invalid")
    if manifest_sha256 != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError("validation receipt manifest digest does not match")
    if not isinstance(result_sha256, str) or re.fullmatch(
        r"[0-9a-f]{64}", result_sha256
    ) is None:
        raise ValueError("validation receipt results digest is invalid")
    try:
        results_bytes = validation_results.read_bytes()
        results_value = json.loads(results_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("validation results must be valid JSON") from exc
    if result_sha256 != hashlib.sha256(results_bytes).hexdigest():
        raise ValueError("validation results digest does not match receipt")
    if results_bytes != _canonical_json_bytes(results_value):
        raise ValueError("validation results must use canonical JSON encoding")
    if not isinstance(results_value, dict) or set(results_value) != {
        "schema_version",
        "manifest_sha256",
        "results",
    }:
        raise ValueError("validation results have invalid fields")
    if (
        results_value["schema_version"] != "1"
        or results_value["manifest_sha256"] != manifest_sha256
    ):
        raise ValueError("validation results manifest digest does not match")
    result_rows = results_value["results"]
    if not isinstance(result_rows, list) or any(
        not isinstance(row, dict)
        or not isinstance(row.get("pair_id"), str)
        or row.get("status") not in {"validated", "excluded"}
        for row in result_rows
    ):
        raise ValueError("validation results rows are invalid")
    result_pair_ids = [row["pair_id"] for row in result_rows]
    manifest_pair_ids = {case.pair_id for case in load_manifest(manifest).cases}
    if len(result_pair_ids) != len(set(result_pair_ids)) or set(result_pair_ids) != (
        manifest_pair_ids
    ):
        raise ValueError("validation results must exactly cover manifest pairs")
    derived_pair_ids = sorted(
        row["pair_id"] for row in result_rows if row["status"] == "validated"
    )
    if (
        not isinstance(pair_ids, list)
        or any(
            not isinstance(pair_id, str)
            or re.fullmatch(r"pair-[0-9a-f]{12}", pair_id) is None
            for pair_id in pair_ids
        )
        or pair_ids != sorted(set(pair_ids))
    ):
        raise ValueError("validation receipt pair ids are invalid")
    if pair_ids != derived_pair_ids:
        raise ValueError("validation receipt validated pair allowlist does not match results")
    if not derived_pair_ids:
        raise ValueError("validation receipt must contain a validated pair")
    return ValidationReceipt(
        schema_version=schema_version,
        manifest_sha256=manifest_sha256,
        validated_pair_ids=tuple(derived_pair_ids),
        validation_results_sha256=result_sha256,
    )


def require_validated_pair(
    receipt: ValidationReceipt | ValidationReceiptV2 | ValidationVerification,
    pair_id: str,
) -> None:
    """Fail closed unless current verified v2 authority covers the pair."""
    if type(receipt) is ValidationVerification:
        if receipt.authority != "current_scoring_authority" or not isinstance(
            receipt.receipt, ValidationReceiptV2
        ):
            raise ValueError("validation receipt has no current scoring authority")
        pair_ids = receipt.receipt.validated_pair_ids
    elif isinstance(receipt, ValidationVerification):
        raise ValueError("validation receipt has no current scoring authority")
    elif isinstance(receipt, ValidationReceiptV2):
        raise ValueError("raw v2 receipt requires offline authority verification")
    else:
        raise ValueError("v1 receipt is historical_integrity_only")
    if pair_id not in pair_ids:
        raise ValueError(f"pair {pair_id} is not in validation receipt")


def _verify_pair_integrity(
    root: Path,
    replay: BenchmarkCase,
    control: BenchmarkCase,
    runtimes: Mapping[str, RuntimeDescriptor],
) -> None:
    patch_path = _contained_file(root, replay.patch.relative_path)
    test_path = _contained_file(root, replay.tests.relative_path)
    if not verify_descriptor_bytes(replay.patch, patch_path.read_bytes()):
        raise _IntegrityError("descriptor_hash_mismatch")
    if not verify_descriptor_bytes(replay.tests, test_path.read_bytes()):
        raise _IntegrityError("descriptor_hash_mismatch")
    if (runtimes[replay.case_id].tool, runtimes[replay.case_id].args) != (
        runtimes[control.case_id].tool,
        runtimes[control.case_id].args,
    ):
        raise _IntegrityError("test_command_mismatch")
    try:
        test_command = _command_from_test_descriptor(test_path.read_bytes())
    except _Excluded as exc:
        raise _IntegrityError("test_command_mismatch") from exc
    if test_command != {
        "tool": runtimes[replay.case_id].tool,
        "args": list(runtimes[replay.case_id].args),
    }:
        raise _IntegrityError("test_command_mismatch")
    for case, commit in ((replay, replay.buggy_commit), (control, control.fixed_commit)):
        cwd = _runtime_cwd(root, runtimes[case.case_id])
        if Path(_git(cwd, "rev-parse", "--show-toplevel")).resolve() != cwd:
            raise _IntegrityError("checkout_root_mismatch")
        if _git(cwd, "rev-parse", "HEAD") != commit:
            raise _IntegrityError("checkout_commit_mismatch")
        if _git(cwd, "status", "--porcelain"):
            raise _IntegrityError("dirty_checkout")
    patch_bytes = patch_path.read_bytes()
    diff_paths = _unified_diff_paths(patch_bytes)
    actual_patch = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--no-color",
            replay.buggy_commit,
            replay.fixed_commit,
            "--",
            *diff_paths,
        ],
        cwd=_runtime_cwd(root, runtimes[replay.case_id]),
        check=True,
        capture_output=True,
    ).stdout
    if normalize_unified_diff_bytes(actual_patch) != normalize_unified_diff_bytes(
        patch_bytes
    ):
        raise _IntegrityError("patch_mismatch")


def _run_three(
    case: BenchmarkCase,
    runtime: RuntimeDescriptor,
    root: Path,
    runner: CorpusRunner,
    outcomes: list[RunOutcome],
) -> list[RunOutcome]:
    cwd = _runtime_cwd(root, runtime)
    for _ in range(3):
        outcome = runner.run(case.source_id, runtime.tool, runtime.args, cwd)
        outcomes.append(outcome)
        if outcome.timed_out:
            break
        if case.role == "developer_fix_control" and outcome.returncode != 0:
            break
    return outcomes


def _fixed_failure_reason(outcomes: list[RunOutcome]) -> str | None:
    if any(outcome.timed_out for outcome in outcomes):
        return "timeout"
    if len(outcomes) != 3 or any(outcome.returncode != 0 for outcome in outcomes):
        return "dependency_or_setup_failure"
    return None


def _buggy_failure_reason(
    outcomes: list[RunOutcome], artifact_store: ArtifactStore | None = None
) -> tuple[str | None, str]:
    if any(outcome.timed_out for outcome in outcomes):
        return "timeout", ""
    if len(outcomes) != 3 or any(outcome.returncode == 0 for outcome in outcomes):
        return "flaky", ""
    raw_signatures = [_failure_signature(outcome.output) for outcome in outcomes]
    if any(signature is None for signature in raw_signatures):
        return "dependency_or_setup_failure", ""
    if len(set(raw_signatures)) != 1:
        return "inconsistent_failure_signature", ""
    outputs = [
        (
            outcome.output
            if artifact_store is None
            else artifact_store.render_bytes(
                "validation_stdout", outcome.output
            )[0]
        )
        for outcome in outcomes
    ]
    signatures = [_failure_signature(output) for output in outputs]
    if any(signature is None for signature in signatures):
        return "dependency_or_setup_failure", ""
    if len(set(signatures)) != 1:
        return "inconsistent_failure_signature", ""
    return None, signatures[0] or ""


def _failure_signature(output: bytes) -> str | None:
    return validation_failure_signature(output)


def _run_json(outcome: RunOutcome) -> dict[str, object]:
    return {
        "returncode": outcome.returncode,
        "timed_out": outcome.timed_out,
        "output_sha256": hashlib.sha256(outcome.output).hexdigest(),
    }


def _runtime_cwd(root: Path, runtime: RuntimeDescriptor) -> Path:
    path = root / runtime.cwd
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError("runtime cwd escapes corpus root") from exc
    if path.is_symlink() or not resolved.is_dir():
        raise ValueError("runtime cwd must be a real directory")
    return resolved


class _IntegrityError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _command_from_test_descriptor(contents: bytes) -> dict[str, object]:
    try:
        text = contents.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise _Excluded("missing_regression_test") from exc
    commands = [line.strip() for line in text.splitlines() if line.strip()]
    if len(commands) != 1 or any(
        token in commands[0] for token in ("&&", "||", ";", "`", "$(")
    ):
        raise _Excluded("missing_regression_test")
    try:
        argv = shlex.split(commands[0])
    except ValueError as exc:
        raise _Excluded("missing_regression_test") from exc
    if not argv:
        raise _Excluded("missing_regression_test")
    return _typed_command(argv)


def _contained_file(root: Path, relative_path: str) -> Path:
    path = root / relative_path
    if path.is_symlink():
        raise ValueError("artifact symlinks are forbidden")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise ValueError("artifact path escapes corpus root") from exc
    if not resolved.is_file():
        raise ValueError("artifact must be a file")
    return resolved


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def import_bugsinpy(
    source: Path,
    output: Path,
    limit: int,
    seed: int,
    *,
    project_cache: Path | None = None,
) -> dict[str, Any]:
    """Import deterministic, hash-addressed metadata from a pinned local BugsInPy tree."""
    source = source.resolve()
    project_cache = (project_cache or source.parent / "project-cache").resolve()
    if limit < 0:
        raise ValueError("limit must be non-negative")
    corpus_commit, corpus_url = _pinned_repository(source)
    corpus_license = _license_evidence(source, source / "LICENSE")
    candidates: list[dict[str, Any]] = []
    exclusions: list[dict[str, str]] = []
    bug_dirs = sorted(
        source.glob("projects/*/bugs/*"),
        key=lambda path: (path.parts[-3].casefold(), _natural_bug_key(path.name)),
    )
    for bug_dir in bug_dirs:
        upstream_case = f"{bug_dir.parts[-3]}/{bug_dir.name}"
        try:
            candidates.append(
                _import_candidate(source, bug_dir, corpus_commit, project_cache)
            )
        except _Excluded as exc:
            exclusions.append({"upstream_case": upstream_case, "reason": exc.reason})

    candidates.sort(key=lambda item: item["upstream_case"])
    chooser = random.Random(seed)
    chooser.shuffle(candidates)
    selected = candidates[:limit]
    selected.sort(key=lambda item: item["pair_id"])

    cases: list[dict[str, Any]] = []
    truths: list[dict[str, Any]] = []
    runtimes: list[dict[str, Any]] = []
    sources_by_id: dict[str, dict[str, Any]] = {}
    for candidate in selected:
        source_entry = candidate["source"]
        source_id = source_entry["source_id"]
        existing_source = sources_by_id.get(source_id)
        if existing_source is None:
            sources_by_id[source_id] = dict(source_entry)
        else:
            existing_commits = existing_source["license_commits_verified"]
            new_commits = source_entry["license_commits_verified"]
            assert isinstance(existing_commits, list) and isinstance(new_commits, list)
            existing_source["license_commits_verified"] = sorted(
                set(existing_commits) | set(new_commits)
            )
        base = candidate["case"]
        replay_id = _opaque("case", candidate["pair_id"] + ":replay")
        control_id = _opaque("case", candidate["pair_id"] + ":control")
        for case_id, role in (
            (replay_id, "historical_bug_replay"),
            (control_id, "developer_fix_control"),
        ):
            case = dict(base)
            case.update({"case_id": case_id, "role": role})
            cases.append(case)
            runtimes.append(
                {
                    "case_id": case_id,
                    "role": role,
                    "cwd": (
                        f"{base['source_id']}/{base['pair_id']}/replay"
                        if role == "historical_bug_replay"
                        else f"{base['source_id']}/{base['pair_id']}/control"
                    ),
                    "command": candidate["command"],
                    "python_version": candidate["python_version"],
                }
            )
        old_locations = [
            location for location in base["changed_locations"] if location["side"] == "old"
        ]
        for index, location in enumerate(old_locations, start=1):
            truths.append(
                {
                    "defect_id": f"truth_{candidate['pair_id'][5:]}_{index}",
                    "case_id": replay_id,
                    "file": location["path"],
                    "start_line": location["start_line"],
                    "end_line": location["end_line"],
                }
            )

    document: dict[str, Any] = {
        "schema_version": "1",
        "protocol_version": "1",
        "corpus_commit": corpus_commit,
        "provenance": {
            "kind": "BugsInPy",
            "source_url": corpus_url,
            "license_status": "DETECTED" if corpus_license else "UNSPECIFIED",
            "license": corpus_license[0] if corpus_license else None,
            "license_file": "LICENSE" if corpus_license else None,
            "license_sha256": corpus_license[1] if corpus_license else None,
        },
        "selection": {
            "seed": seed,
            "requested_pair_limit": limit,
            "eligible_pairs": len(candidates),
            "selected_pairs": len(selected),
        },
        "sources": [sources_by_id[key] for key in sorted(sources_by_id)],
        "cases": sorted(cases, key=lambda case: case["case_id"]),
        "truth_defects": sorted(truths, key=lambda truth: truth["defect_id"]),
        "runtime": sorted(runtimes, key=lambda runtime: runtime["case_id"]),
        "exclusions": exclusions,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(document, sort_keys=True, indent=2, ensure_ascii=True) + "\n",
        encoding="utf-8",
    )
    return document


class _Excluded(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _pinned_repository(source: Path) -> tuple[str, str]:
    if not source.is_dir():
        raise ValueError("source must be an existing local git repository")
    try:
        commit = _git(source, "rev-parse", "HEAD")
        top = Path(_git(source, "rev-parse", "--show-toplevel")).resolve()
        status = _git(source, "status", "--porcelain")
        url = _git(source, "remote", "get-url", "origin")
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ValueError("source must be an existing local git repository") from exc
    if top != source:
        raise ValueError("source must be the git repository root")
    if status:
        raise ValueError("source git repository must be clean")
    if re.fullmatch(r"[0-9a-f]{40,64}", commit) is None:
        raise ValueError("source commit must be a full hexadecimal object id")
    return commit, url


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def _import_candidate(
    source: Path, bug_dir: Path, corpus_commit: str, project_cache: Path
) -> dict[str, Any]:
    project_dir = bug_dir.parents[1]
    project = project_dir.name
    upstream_case = f"{project}/{bug_dir.name}"
    project_info = _read_info(_safe_file(source, project_dir / "project.info"))
    project_url = project_info.get("github_url")
    if not project_url:
        raise _Excluded("missing_source_url")

    info = _read_info(_safe_file(source, bug_dir / "bug.info"))
    buggy_commit = _full_commit(info.get("buggy_commit_id"), "buggy_commit")
    fixed_commit = _full_commit(info.get("fixed_commit_id"), "fixed_commit")
    if buggy_commit == fixed_commit:
        raise _Excluded("identical_commits")
    if not info.get("test_file"):
        raise _Excluded("missing_regression_test")
    license_evidence = _project_license_evidence(
        project_cache / project, project_url, buggy_commit, fixed_commit
    )
    if license_evidence is None:
        raise _Excluded("source_license_missing")
    declared_license, license_name, license_sha256 = license_evidence

    patch_path = _safe_file(source, bug_dir / "bug_patch.txt")
    run_test = _safe_file(source, bug_dir / "run_test.sh")
    _safe_file(source, bug_dir / "bug_buggy.txt")
    _safe_file(source, bug_dir / "bug_fixed.txt")
    patch_bytes = patch_path.read_bytes()
    if b"\x00" in patch_bytes:
        raise _Excluded("binary_patch")
    try:
        patch_text = patch_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise _Excluded("binary_patch") from exc
    locations = _changed_locations(patch_text)
    project_checkout = project_cache / project
    if not _project_patch_matches(project_checkout, buggy_commit, fixed_commit, patch_bytes):
        raise _Excluded("patch_mismatch")
    test_bytes = run_test.read_bytes()
    try:
        command_text = test_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise _Excluded("missing_regression_test") from exc
    commands = [line.strip() for line in command_text.splitlines() if line.strip()]
    if len(commands) != 1:
        raise _Excluded("missing_regression_test")
    try:
        test_argv = shlex.split(commands[0])
    except ValueError as exc:
        raise _Excluded("missing_regression_test") from exc
    if not test_argv or any(token in commands[0] for token in ("&&", "||", ";", "`", "$(`")):
        raise _Excluded("missing_regression_test")
    command = _typed_command(test_argv)

    pair_id = _opaque("pair", f"{corpus_commit}:{upstream_case}")
    source_id = _opaque("source", f"{corpus_commit}:{project_url}")
    relative_patch = patch_path.relative_to(source).as_posix()
    relative_test = run_test.relative_to(source).as_posix()
    source_entry = {
        "source_id": source_id,
        "project_url": project_url,
        "source_license": declared_license,
        "license_file": license_name,
        "license_sha256": license_sha256,
        "license_commits_verified": [buggy_commit, fixed_commit],
    }
    return {
        "upstream_case": upstream_case,
        "pair_id": pair_id,
        "source": source_entry,
        "python_version": info.get("python_version", "unknown"),
        "command": command,
        "case": {
            "pair_id": pair_id,
            "source_id": source_id,
            "provenance_kind": "historical_fix",
            "source_license": declared_license,
            "buggy_commit": buggy_commit,
            "fixed_commit": fixed_commit,
            "patch": {
                "relative_path": relative_patch,
                "sha256": hashlib.sha256(normalize_unified_diff_bytes(patch_bytes)).hexdigest(),
                "normalization": "unified_diff",
            },
            "tests": {
                "relative_path": relative_test,
                "sha256": hashlib.sha256(command_text.encode()).hexdigest(),
                "normalization": "normalized_text",
            },
            "changed_locations": locations,
            "split": "test",
        },
    }


def _safe_file(root: Path, path: Path) -> Path:
    if path.is_symlink():
        raise _Excluded("unsafe_symlink")
    try:
        resolved = path.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        if path.name == "run_test.sh":
            raise _Excluded("missing_regression_test") from exc
        raise _Excluded("missing_metadata") from exc
    if not resolved.is_file():
        raise _Excluded("missing_metadata")
    return resolved


def _license_evidence(root: Path, path: Path) -> tuple[str, str] | None:
    try:
        evidence_path = _safe_file(root, path)
        contents = evidence_path.read_bytes()
    except (_Excluded, OSError):
        return None
    identifier = _classify_license(contents)
    if identifier is None:
        return None
    return identifier, hashlib.sha256(contents).hexdigest()


def _project_license_evidence(
    checkout: Path, project_url: str, buggy_commit: str, fixed_commit: str
) -> tuple[str, str, str] | None:
    if not checkout.is_dir():
        return None
    try:
        top = Path(_git(checkout, "rev-parse", "--show-toplevel")).resolve()
        remote = _git(checkout, "remote", "get-url", "origin")
        if top != checkout.resolve() or _normalized_git_url(remote) != _normalized_git_url(
            project_url
        ):
            return None
        for commit in (buggy_commit, fixed_commit):
            _git(checkout, "cat-file", "-e", f"{commit}^{{commit}}")
        paths = set(_git(checkout, "ls-tree", "-r", "--name-only", buggy_commit).splitlines())
        paths &= set(_git(checkout, "ls-tree", "-r", "--name-only", fixed_commit).splitlines())
    except (OSError, subprocess.CalledProcessError):
        return None
    allowed_names = {
        "license",
        "license.txt",
        "license.md",
        "licence",
        "licence.txt",
        "licence.md",
        "copying",
        "copying.txt",
        "copying.md",
    }
    for path in sorted(paths, key=lambda value: (len(Path(value).parts), value.casefold())):
        if Path(path).name.casefold() not in allowed_names:
            continue
        try:
            buggy_bytes = subprocess.run(
                ["git", "show", f"{buggy_commit}:{path}"],
                cwd=checkout,
                check=True,
                capture_output=True,
            ).stdout
            fixed_bytes = subprocess.run(
                ["git", "show", f"{fixed_commit}:{path}"],
                cwd=checkout,
                check=True,
                capture_output=True,
            ).stdout
            buggy_license = _classify_license(buggy_bytes)
            fixed_license = _classify_license(fixed_bytes)
        except (OSError, subprocess.CalledProcessError):
            continue
        if buggy_license is not None and buggy_license == fixed_license:
            return fixed_license, path, hashlib.sha256(fixed_bytes).hexdigest()
    return None


def _normalized_git_url(value: str) -> str:
    return value.removesuffix("/").removesuffix(".git")


def _classify_license(contents: bytes) -> str | None:
    try:
        text = contents.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        return None
    lines = text.splitlines()
    matches: set[str] = set()
    for identifier, body_start in _LICENSE_BODY_STARTS.items():
        for index, line in enumerate(lines):
            if not line.strip().startswith(body_start):
                continue
            if not _allowed_license_prefix(lines[:index], identifier):
                continue
            normalized_body = _normalize_license_body(lines[index:])
            digest = hashlib.sha256(normalized_body.encode("utf-8")).hexdigest()
            if digest == _LICENSE_BODY_SHA256[identifier]:
                matches.add(identifier)
    return next(iter(matches)) if len(matches) == 1 else None


def _allowed_license_prefix(lines: list[str], identifier: str) -> bool:
    header_seen = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.casefold() in _LICENSE_HEADERS[identifier] and not header_seen:
            header_seen = True
            continue
        if _COPYRIGHT_LINE.fullmatch(stripped):
            continue
        if identifier.startswith("BSD-") and stripped.casefold() == "all rights reserved.":
            continue
        return False
    return True


def _normalize_license_body(lines: list[str]) -> str:
    without_list_markers = [
        re.sub(r"^\s*(?:\*|[123][.)])\s+", "", line) for line in lines
    ]
    normalized = " ".join(" ".join(without_list_markers).split())
    return _BSD3_HOLDER_NAME.sub("the copyright holder", normalized)


def _read_info(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _INFO_LINE.fullmatch(line.strip())
        if match:
            values[match.group(1)] = match.group(2)
    return values


def _full_commit(value: str | None, label: str) -> str:
    if value is None or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise _Excluded(f"invalid_{label}")
    return value


def _changed_locations(patch: str) -> list[dict[str, object]]:
    locations, changed_lines = parse_unified_diff(patch)
    if not locations or not any(location["side"] == "old" for location in locations):
        raise _Excluded("missing_python_hunk")
    if changed_lines > _MAX_CHANGED_LINES:
        raise _Excluded("oversized_diff")
    return locations


def parse_unified_diff(patch: str) -> tuple[list[dict[str, object]], int]:
    """Return contiguous changed ranges on both sides and their exact line count."""
    locations: list[dict[str, object]] = []
    current: str | None = None
    old_line: int | None = None
    new_line: int | None = None
    changed_lines = 0
    group_old = 0
    group_new = 0

    def flush_change_group() -> None:
        nonlocal changed_lines, group_old, group_new
        changed_lines += max(group_old, group_new)
        group_old = group_new = 0

    for line in patch.replace("\r\n", "\n").replace("\r", "\n").splitlines():
        path_match = _DIFF_PATH.fullmatch(line)
        if path_match:
            flush_change_group()
            if path_match.group(1) != path_match.group(2):
                raise _Excluded("renamed_file")
            current = path_match.group(1)
            if not current.endswith(".py"):
                raise _Excluded("non_python_change")
            if current.startswith("/") or ".." in Path(current).parts or "\\" in current:
                raise _Excluded("unsafe_patch_path")
            old_line = new_line = None
            continue
        hunk = _HUNK.match(line)
        if hunk and current:
            flush_change_group()
            old_line = int(hunk.group(1))
            new_line = int(hunk.group(3))
            continue
        if current is None or old_line is None or new_line is None:
            continue
        if line.startswith(" "):
            flush_change_group()
            old_line += 1
            new_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            _append_changed_line(locations, current, "old", old_line)
            old_line += 1
            group_old += 1
        elif line.startswith("+") and not line.startswith("+++"):
            _append_changed_line(locations, current, "new", new_line)
            new_line += 1
            group_new += 1
        elif line.startswith("\\"):
            continue
        else:
            flush_change_group()
    flush_change_group()
    return locations, changed_lines


def _append_changed_line(
    locations: list[dict[str, object]], path: str, side: str, line: int
) -> None:
    if (
        locations
        and locations[-1]["path"] == path
        and locations[-1]["side"] == side
        and locations[-1]["end_line"] == line - 1
    ):
        locations[-1]["end_line"] = line
        return
    locations.append({"path": path, "side": side, "start_line": line, "end_line": line})


def _project_patch_matches(
    checkout: Path, buggy_commit: str, fixed_commit: str, patch_bytes: bytes
) -> bool:
    try:
        paths = _unified_diff_paths(patch_bytes)
        actual = subprocess.run(
            [
                "git",
                "diff",
                "--no-ext-diff",
                "--no-color",
                buggy_commit,
                fixed_commit,
                "--",
                *paths,
            ],
            cwd=checkout,
            check=True,
            capture_output=True,
        ).stdout
        return normalize_unified_diff_bytes(actual) == normalize_unified_diff_bytes(patch_bytes)
    except (OSError, subprocess.CalledProcessError, ValueError):
        return False


def _unified_diff_paths(patch_bytes: bytes) -> tuple[str, ...]:
    try:
        text = patch_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as exc:
        raise ValueError("unified diff must be UTF-8 text") from exc
    paths: list[str] = []
    for line in text.splitlines():
        match = _DIFF_PATH.fullmatch(line)
        if match is None:
            continue
        old_path, new_path = match.groups()
        if old_path != new_path or old_path.startswith("/") or ".." in Path(old_path).parts:
            raise ValueError("unified diff contains an unsafe path")
        paths.append(old_path)
    if not paths or len(paths) != len(set(paths)):
        raise ValueError("unified diff paths must be non-empty and unique")
    return tuple(paths)


def _typed_command(argv: list[str]) -> dict[str, object]:
    executable, *args = argv
    name = Path(executable).name
    if name in {"python", "python3", "{python}"}:
        return {"tool": "python", "args": args}
    if name == "pytest":
        return {"tool": "python", "args": ["-m", "pytest", *args]}
    if name == "tox":
        return {"tool": "tox", "args": args}
    raise _Excluded("unsupported_test_tool")


def _opaque(prefix: str, material: str) -> str:
    return f"{prefix}-{hashlib.sha256(material.encode()).hexdigest()[:12]}"


def _natural_bug_key(value: str) -> tuple[int, int | str]:
    return (0, int(value)) if value.isdigit() else (1, value)
