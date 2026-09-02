"""Canonical encoding, strict decoding and result verification (X-01).

Every value crosses the boundary as canonical JSON. Decoding is strict: a
missing or unexpected field, an unsafe name (anything but one path component),
an unbounded size, a secret-looking environment name, or an unknown protocol
version raises ``ProtocolError`` and the caller DEFERs. ``verify_result`` is
the only judge of whether a result answers a request.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

from attest.execution.types import (
    EXECUTION_PROTOCOL_VERSION,
    MAX_ARGV,
    MAX_ARTIFACT_BYTES,
    MAX_ARTIFACTS,
    MAX_ENVIRONMENT,
    MAX_INPUTS,
    MAX_TEXT_CHARS,
    NONCE_HEX_CHARS,
    Artifact,
    DeclaredInput,
    ExecutionRequest,
    ExecutionResultEnvelope,
    ResourceLimits,
)


class ProtocolError(ValueError):
    """The payload is not a well-formed protocol value."""


_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_ENV_NAME_RE = re.compile(r"^[A-Z_][A-Z0-9_]{0,63}$")
_HEX_RE = re.compile(r"^[0-9a-f]+$")
SECRET_NAME_PARTS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")

REQUEST_FIELDS = (
    "protocol_version",
    "task_id",
    "nonce",
    "run_id",
    "candidate_id",
    "revision_sha",
    "profile",
    "interpreter",
    "argv_template",
    "environment",
    "inputs",
    "limits",
    "expected_artifacts",
)
LIMIT_FIELDS = ("wall_timeout_s", "cpu_timeout_s", "memory_mb", "output_bytes")
INPUT_FIELDS = ("name", "digest", "size")
RESULT_FIELDS = (
    "protocol_version",
    "nonce",
    "request_digest",
    "run_id",
    "profile",
    "backend_digest",
    "exit_code",
    "timed_out",
    "elapsed_s",
    "artifacts",
    "error",
)


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_secret_name(name: str) -> bool:
    upper = name.upper()
    return any(part in upper for part in SECRET_NAME_PARTS)


def _mapping(payload: bytes | Mapping[str, Any], what: str) -> dict[str, Any]:
    if isinstance(payload, bytes | bytearray):
        try:
            value = json.loads(bytes(payload).decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ProtocolError(f"{what}: not canonical JSON") from exc
    else:
        value = payload
    if not isinstance(value, Mapping):
        raise ProtocolError(f"{what}: not an object")
    return dict(value)


def _keys(raw: Mapping[str, Any], expected: tuple[str, ...], what: str) -> None:
    missing = [name for name in expected if name not in raw]
    extra = [name for name in raw if name not in expected]
    if missing:
        raise ProtocolError(f"{what}: missing field {missing[0]}")
    if extra:
        raise ProtocolError(f"{what}: unexpected field {extra[0]}")


def _text(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ProtocolError(f"{field}: not a string")
    if "\x00" in value or len(value) > MAX_TEXT_CHARS:
        raise ProtocolError(f"{field}: unbounded or contains NUL")
    if not value and not allow_empty:
        raise ProtocolError(f"{field}: empty")
    return value


def _safe_name(value: object, field: str) -> str:
    text = _text(value, field)
    if text in {".", ".."} or not _NAME_RE.match(text):
        raise ProtocolError(f"{field}: unsafe name {text!r}")
    return text


def _digest(value: object, field: str) -> str:
    text = _text(value, field)
    if len(text) != 64 or not _HEX_RE.match(text):
        raise ProtocolError(f"{field}: not a SHA-256 hex digest")
    return text


def _int(value: object, field: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"{field}: not an integer")
    if not minimum <= value <= maximum:
        raise ProtocolError(f"{field}: out of bounds")
    return value


def _number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ProtocolError(f"{field}: not a number")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ProtocolError(f"{field}: not a finite non-negative number")
    return number


def _sequence(value: object, field: str, maximum: int) -> list[Any]:
    if not isinstance(value, list | tuple):
        raise ProtocolError(f"{field}: not a sequence")
    if len(value) > maximum:
        raise ProtocolError(f"{field}: more than {maximum} entries")
    return list(value)


def _unique_names(names: list[str], field: str) -> tuple[str, ...]:
    if len(set(names)) != len(names):
        raise ProtocolError(f"{field}: duplicate name")
    return tuple(names)


def request_to_dict(request: ExecutionRequest) -> dict[str, Any]:
    return asdict(request)


def encode_request(request: ExecutionRequest) -> bytes:
    return canonical_bytes(request_to_dict(request))


def request_digest(request: ExecutionRequest) -> str:
    return sha256_hex(encode_request(request))


def decode_request(payload: bytes | Mapping[str, Any]) -> ExecutionRequest:
    raw = _mapping(payload, "request")
    _keys(raw, REQUEST_FIELDS, "request")
    if raw["protocol_version"] != EXECUTION_PROTOCOL_VERSION:
        raise ProtocolError("request: unknown protocol version")
    nonce = _text(raw["nonce"], "nonce")
    if len(nonce) != NONCE_HEX_CHARS or not _HEX_RE.match(nonce):
        raise ProtocolError("nonce: malformed")
    revision = _text(raw["revision_sha"], "revision_sha", allow_empty=True)
    if revision and (len(revision) not in {40, 64} or not _HEX_RE.match(revision)):
        raise ProtocolError("revision_sha: not a commit id")
    argv = tuple(
        _text(entry, "argv_template")
        for entry in _sequence(raw["argv_template"], "argv_template", MAX_ARGV)
    )
    if not argv:
        raise ProtocolError("argv_template: empty")
    environment: list[tuple[str, str]] = []
    for pair in _sequence(raw["environment"], "environment", MAX_ENVIRONMENT):
        if not isinstance(pair, list | tuple) or len(pair) != 2:
            raise ProtocolError("environment: entry is not a name/value pair")
        name = _text(pair[0], "environment name")
        if not _ENV_NAME_RE.match(name):
            raise ProtocolError(f"environment: unsafe name {name!r}")
        if is_secret_name(name):
            raise ProtocolError(f"environment: {name} looks like a credential")
        environment.append((name, _text(pair[1], f"environment {name}", allow_empty=True)))
    names = [name for name, _ in environment]
    if names != sorted(names) or len(set(names)) != len(names):
        raise ProtocolError("environment: not canonical (sorted, unique names)")
    inputs: list[DeclaredInput] = []
    for item in _sequence(raw["inputs"], "inputs", MAX_INPUTS):
        entry = _mapping(item, "input")
        _keys(entry, INPUT_FIELDS, "input")
        inputs.append(
            DeclaredInput(
                name=_safe_name(entry["name"], "input name"),
                digest=_digest(entry["digest"], "input digest"),
                size=_int(entry["size"], "input size", minimum=0, maximum=MAX_ARTIFACT_BYTES),
            )
        )
    _unique_names([item.name for item in inputs], "inputs")
    limits_raw = _mapping(raw["limits"], "limits")
    _keys(limits_raw, LIMIT_FIELDS, "limits")
    limits = ResourceLimits(
        wall_timeout_s=_number(limits_raw["wall_timeout_s"], "wall_timeout_s"),
        cpu_timeout_s=_int(limits_raw["cpu_timeout_s"], "cpu_timeout_s", minimum=1, maximum=86_400),
        memory_mb=_int(limits_raw["memory_mb"], "memory_mb", minimum=1, maximum=1 << 20),
        output_bytes=_int(
            limits_raw["output_bytes"], "output_bytes", minimum=1, maximum=MAX_ARTIFACT_BYTES
        ),
    )
    expected = _unique_names(
        [
            _safe_name(name, "expected artifact")
            for name in _sequence(raw["expected_artifacts"], "expected_artifacts", MAX_ARTIFACTS)
        ],
        "expected_artifacts",
    )
    return ExecutionRequest(
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        task_id=_safe_name(raw["task_id"], "task_id"),
        nonce=nonce,
        run_id=_safe_name(raw["run_id"], "run_id"),
        candidate_id=_safe_name(raw["candidate_id"], "candidate_id"),
        revision_sha=revision,
        profile=_safe_name(raw["profile"], "profile"),
        interpreter=_text(raw["interpreter"], "interpreter"),
        argv_template=argv,
        environment=tuple(environment),
        inputs=tuple(inputs),
        limits=limits,
        expected_artifacts=expected,
    )


def result_to_dict(envelope: ExecutionResultEnvelope) -> dict[str, Any]:
    return asdict(envelope)


def encode_result(envelope: ExecutionResultEnvelope) -> bytes:
    return canonical_bytes(result_to_dict(envelope))


def result_digest(envelope: ExecutionResultEnvelope) -> str:
    return sha256_hex(encode_result(envelope))


def decode_result(payload: bytes | Mapping[str, Any]) -> ExecutionResultEnvelope:
    raw = _mapping(payload, "result")
    _keys(raw, RESULT_FIELDS, "result")
    if raw["protocol_version"] != EXECUTION_PROTOCOL_VERSION:
        raise ProtocolError("result: unknown protocol version")
    nonce = _text(raw["nonce"], "nonce")
    if len(nonce) != NONCE_HEX_CHARS or not _HEX_RE.match(nonce):
        raise ProtocolError("nonce: malformed")
    exit_code = raw["exit_code"]
    if exit_code is not None:
        exit_code = _int(exit_code, "exit_code", minimum=-(1 << 31), maximum=1 << 31)
    if not isinstance(raw["timed_out"], bool):
        raise ProtocolError("timed_out: not a boolean")
    artifacts: list[Artifact] = []
    for item in _sequence(raw["artifacts"], "artifacts", MAX_ARTIFACTS):
        entry = _mapping(item, "artifact")
        _keys(entry, INPUT_FIELDS, "artifact")
        artifacts.append(
            Artifact(
                name=_safe_name(entry["name"], "artifact name"),
                digest=_digest(entry["digest"], "artifact digest"),
                size=_int(entry["size"], "artifact size", minimum=0, maximum=MAX_ARTIFACT_BYTES),
            )
        )
    _unique_names([item.name for item in artifacts], "artifacts")
    return ExecutionResultEnvelope(
        protocol_version=EXECUTION_PROTOCOL_VERSION,
        nonce=nonce,
        request_digest=_digest(raw["request_digest"], "request_digest"),
        run_id=_safe_name(raw["run_id"], "run_id"),
        profile=_safe_name(raw["profile"], "profile"),
        backend_digest=_digest(raw["backend_digest"], "backend_digest"),
        exit_code=exit_code,
        timed_out=raw["timed_out"],
        elapsed_s=_number(raw["elapsed_s"], "elapsed_s"),
        artifacts=tuple(artifacts),
        error=_text(raw["error"], "error", allow_empty=True),
    )


def verify_result(
    request: ExecutionRequest,
    envelope: ExecutionResultEnvelope,
    artifacts: Mapping[str, bytes],
) -> tuple[str, ...]:
    """Every reason the result does not answer the request; empty when it does.

    ``artifacts`` are the bytes the controller itself read back for the names
    the envelope lists -- never bytes the executor handed over in memory.
    """
    reasons: list[str] = []
    if envelope.protocol_version != request.protocol_version:
        reasons.append("protocol version mismatch")
    if envelope.nonce != request.nonce:
        reasons.append("nonce mismatch: the result does not answer this request")
    if envelope.request_digest != request_digest(request):
        reasons.append("request digest mismatch")
    if envelope.run_id != request.run_id:
        reasons.append("run id mismatch")
    if envelope.profile != request.profile:
        reasons.append("executor profile mismatch")
    listed = [artifact.name for artifact in envelope.artifacts]
    if len(set(listed)) != len(listed):
        reasons.append("duplicate artifact")
    for artifact in envelope.artifacts:
        if artifact.name not in request.expected_artifacts:
            reasons.append(f"undeclared artifact {artifact.name}")
            continue
        data = artifacts.get(artifact.name)
        if data is None:
            reasons.append(f"artifact {artifact.name} missing")
            continue
        if artifact.size > MAX_ARTIFACT_BYTES or len(data) > MAX_ARTIFACT_BYTES:
            reasons.append(f"artifact {artifact.name} exceeds the bound")
            continue
        if len(data) != artifact.size:
            reasons.append(f"artifact size mismatch for {artifact.name}")
        if sha256_hex(data) != artifact.digest:
            reasons.append(f"artifact digest mismatch for {artifact.name}")
    for name in artifacts:
        if name not in listed:
            reasons.append(f"unlisted artifact bytes for {name}")
    return tuple(reasons)
