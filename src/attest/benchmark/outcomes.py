"""Canonical write-once outcome artifacts with same-file-descriptor verification."""

from __future__ import annotations

import errno
import hashlib
import json
import math
import os
import secrets
import stat
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from attest.benchmark.measurement import (
    ARM_ATTEST_PRODUCT,
    FindingStatus,
    MeasurementRecord,
    TaskStatus,
    decode_measurement_record,
)

OUTCOME_SEAL_SCHEMA_VERSION = "1"
OUTCOME_SEAL_PATH = "outcomes.seal.json"
OUTCOME_PREDECLARATION_SCHEMA_VERSION = "1"
OUTCOME_PREDECLARATION_PROTOCOL = "comparison-authoritative-outcomes-v1"
OUTCOME_PREDECLARATION_PATH = "outcomes.predeclaration.json"
DEFAULT_MAX_OUTCOME_BYTES = 4 * 1024 * 1024
MAX_OUTCOME_CASES = 128
MAX_OUTCOME_REPEATS = 20
MAX_OUTCOME_SLOTS = 4096
_OUTCOME_ARMS = (ARM_ATTEST_PRODUCT, "bare_prompt", "ruff_static")
COMPARISON_ARM_OUTCOME_SCHEMA_VERSION = "1"
COMPARISON_OUTCOME_PREDECLARATION_SCHEMA_VERSION = "1"
COMPARISON_OUTCOME_PROTOCOL = "comparison-arm-outcomes-v1"
COMPARISON_OUTCOME_PREDECLARATION_PATH = (
    "comparison-outcomes.predeclaration.json"
)
COMPARISON_OUTCOME_SEAL_SCHEMA_VERSION = "1"
COMPARISON_OUTCOME_SEAL_PATH = "comparison-outcomes.seal.json"
COMPARISON_OUTCOME_DIRECTORY = "comparison-outcomes"
EMPTY_PAID_CALLS_SHA256 = hashlib.sha256(b"[]").hexdigest()
_SUPPORTED_DIR_FD_NAMES = frozenset(function.__name__ for function in os.supports_dir_fd)
_SUPPORTED_FOLLOW_SYMLINK_NAMES = frozenset(
    function.__name__ for function in os.supports_follow_symlinks
)
_SUPPORTED_FD_NAMES = frozenset(function.__name__ for function in os.supports_fd)


@dataclass(frozen=True)
class CanonicalDocument:
    """One exact canonical JSON snapshot read from a single regular-file handle."""

    relative_path: str
    data: bytes
    sha256: str
    size: int
    value: object


@dataclass(frozen=True, init=False)
class OutcomeSlot:
    """One predeclared immutable location for a semantic execution outcome."""

    ordinal: int
    case_id: str
    arm: str
    repeat: int
    bindings_sha256: str
    slot_id: str
    relative_path: str

    @classmethod
    def create(
        cls,
        *,
        ordinal: int,
        case_id: str,
        arm: str,
        repeat: int,
        bindings_sha256: str,
    ) -> OutcomeSlot:
        if type(ordinal) is not int or ordinal < 0:
            raise ValueError("outcome ordinal must be an exact non-negative integer")
        if type(repeat) is not int or repeat < 0:
            raise ValueError("outcome repeat must be an exact non-negative integer")
        if type(case_id) is not str or not case_id:
            raise ValueError("outcome case_id must be a non-empty exact string")
        if type(arm) is not str or not arm:
            raise ValueError("outcome arm must be a non-empty exact string")
        _require_sha256(bindings_sha256, "bindings_sha256")
        identity = {
            "arm": arm,
            "bindings_sha256": bindings_sha256,
            "case_id": case_id,
            "ordinal": ordinal,
            "repeat": repeat,
            "schema_version": OUTCOME_SEAL_SCHEMA_VERSION,
        }
        slot = object.__new__(cls)
        object.__setattr__(slot, "ordinal", ordinal)
        object.__setattr__(slot, "case_id", case_id)
        object.__setattr__(slot, "arm", arm)
        object.__setattr__(slot, "repeat", repeat)
        object.__setattr__(slot, "bindings_sha256", bindings_sha256)
        object.__setattr__(
            slot, "slot_id", hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
        )
        object.__setattr__(slot, "relative_path", f"outcomes/{ordinal:06d}.json")
        return slot

    def to_json_dict(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "ordinal": self.ordinal,
            "case_id": self.case_id,
            "arm": self.arm,
            "repeat": self.repeat,
            "bindings_sha256": self.bindings_sha256,
            "path": self.relative_path,
        }

    @classmethod
    def from_json_dict(cls, value: object) -> OutcomeSlot:
        fields = {
            "slot_id",
            "ordinal",
            "case_id",
            "arm",
            "repeat",
            "bindings_sha256",
            "path",
        }
        if type(value) is not dict or set(value) != fields:
            raise ValueError("outcome slot descriptor has an invalid field set")
        ordinal = value["ordinal"]
        case_id = value["case_id"]
        arm = value["arm"]
        repeat = value["repeat"]
        bindings_sha256 = value["bindings_sha256"]
        if type(ordinal) is not int or type(repeat) is not int:
            raise ValueError("outcome slot ordinal/repeat must be exact integers")
        if type(case_id) is not str or type(arm) is not str or type(bindings_sha256) is not str:
            raise ValueError("outcome slot identity fields must be exact strings")
        rebuilt = cls.create(
            ordinal=ordinal,
            case_id=case_id,
            arm=arm,
            repeat=repeat,
            bindings_sha256=bindings_sha256,
        )
        if rebuilt.to_json_dict() != value:
            raise ValueError("outcome slot derived identity/path does not match its fields")
        return rebuilt


@dataclass(frozen=True, init=False)
class ComparisonOutcomeSlot:
    """Domain-separated slot for one comparison case/arm/repeat outcome."""

    ordinal: int
    authority_id: str
    manifest_sha256: str
    case_id: str
    arm: str
    repeat: int
    bindings_sha256: str
    slot_id: str
    relative_path: str

    @classmethod
    def create(
        cls,
        *,
        ordinal: int,
        authority_id: str,
        manifest_sha256: str,
        case_id: str,
        arm: str,
        repeat: int,
        bindings_sha256: str,
    ) -> ComparisonOutcomeSlot:
        if type(ordinal) is not int or ordinal < 0:
            raise ValueError("comparison outcome ordinal must be an exact non-negative integer")
        if type(repeat) is not int or repeat < 0:
            raise ValueError("comparison outcome repeat must be an exact non-negative integer")
        if type(case_id) is not str or not case_id:
            raise ValueError("comparison outcome case_id must be a non-empty exact string")
        if type(arm) is not str or arm not in _OUTCOME_ARMS:
            raise ValueError("comparison outcome arm is not supported")
        _require_sha256(authority_id, "comparison outcome authority_id")
        _require_sha256(manifest_sha256, "comparison outcome manifest_sha256")
        _require_sha256(bindings_sha256, "comparison outcome bindings_sha256")
        identity = {
            "authority_id": authority_id,
            "authority_protocol": COMPARISON_OUTCOME_PROTOCOL,
            "arm": arm,
            "bindings_sha256": bindings_sha256,
            "case_id": case_id,
            "manifest_sha256": manifest_sha256,
            "ordinal": ordinal,
            "repeat": repeat,
            "schema_version": COMPARISON_OUTCOME_PREDECLARATION_SCHEMA_VERSION,
        }
        slot = object.__new__(cls)
        object.__setattr__(slot, "ordinal", ordinal)
        object.__setattr__(slot, "authority_id", authority_id)
        object.__setattr__(slot, "manifest_sha256", manifest_sha256)
        object.__setattr__(slot, "case_id", case_id)
        object.__setattr__(slot, "arm", arm)
        object.__setattr__(slot, "repeat", repeat)
        object.__setattr__(slot, "bindings_sha256", bindings_sha256)
        object.__setattr__(
            slot, "slot_id", hashlib.sha256(canonical_json_bytes(identity)).hexdigest()
        )
        object.__setattr__(
            slot,
            "relative_path",
            f"{COMPARISON_OUTCOME_DIRECTORY}/{ordinal:06d}.json",
        )
        return slot

    def to_json_dict(self) -> dict[str, object]:
        return {
            "slot_id": self.slot_id,
            "ordinal": self.ordinal,
            "authority_id": self.authority_id,
            "manifest_sha256": self.manifest_sha256,
            "case_id": self.case_id,
            "arm": self.arm,
            "repeat": self.repeat,
            "bindings_sha256": self.bindings_sha256,
            "path": self.relative_path,
        }

    @classmethod
    def from_json_dict(cls, value: object) -> ComparisonOutcomeSlot:
        fields = {
            "slot_id",
            "ordinal",
            "authority_id",
            "manifest_sha256",
            "case_id",
            "arm",
            "repeat",
            "bindings_sha256",
            "path",
        }
        if type(value) is not dict or set(value) != fields:
            raise ValueError("comparison outcome slot has an invalid field set")
        if type(value["ordinal"]) is not int or type(value["repeat"]) is not int:
            raise ValueError("comparison outcome slot ordinal/repeat must be exact integers")
        string_fields = (
            "authority_id",
            "manifest_sha256",
            "case_id",
            "arm",
            "bindings_sha256",
        )
        if any(type(value[field]) is not str for field in string_fields):
            raise ValueError("comparison outcome slot identity fields must be exact strings")
        rebuilt = cls.create(
            ordinal=value["ordinal"],
            authority_id=value["authority_id"],
            manifest_sha256=value["manifest_sha256"],
            case_id=value["case_id"],
            arm=value["arm"],
            repeat=value["repeat"],
            bindings_sha256=value["bindings_sha256"],
        )
        if rebuilt.to_json_dict() != value:
            raise ValueError("comparison outcome slot derived identity/path mismatch")
        return rebuilt


@dataclass(frozen=True)
class ComparisonSurfacedFinding:
    """One ordered author-visible or baseline-visible finding fact."""

    ordinal: int
    finding_id: str
    file: str
    line: int
    evidence_class: str

    def __post_init__(self) -> None:
        if type(self.ordinal) is not int or self.ordinal < 0:
            raise ValueError("comparison finding ordinal must be an exact non-negative integer")
        for name in ("finding_id", "file", "evidence_class"):
            value = getattr(self, name)
            if type(value) is not str or not value:
                raise ValueError(f"comparison finding {name} must be a non-empty exact string")
        if type(self.line) is not int or self.line < 1:
            raise ValueError("comparison finding line must be an exact positive integer")

    def to_json_dict(self) -> dict[str, object]:
        return {
            "ordinal": self.ordinal,
            "finding_id": self.finding_id,
            "file": self.file,
            "line": self.line,
            "evidence_class": self.evidence_class,
        }

    @classmethod
    def from_json_dict(cls, value: object) -> ComparisonSurfacedFinding:
        fields = {"ordinal", "finding_id", "file", "line", "evidence_class"}
        if type(value) is not dict or set(value) != fields:
            raise ValueError("comparison surfaced finding has an invalid field set")
        if type(value["ordinal"]) is not int or type(value["line"]) is not int:
            raise ValueError("comparison surfaced finding numeric fields must be exact integers")
        if any(
            type(value[field]) is not str
            for field in ("finding_id", "file", "evidence_class")
        ):
            raise ValueError("comparison surfaced finding identity must use exact strings")
        return cls(
            ordinal=value["ordinal"],
            finding_id=value["finding_id"],
            file=value["file"],
            line=value["line"],
            evidence_class=value["evidence_class"],
        )


@dataclass(frozen=True)
class ComparisonArmOutcome:
    """Irreducible execution facts for one predeclared comparison slot."""

    task_status: TaskStatus
    abstain_reason: str | None
    surfaced_findings: tuple[ComparisonSurfacedFinding, ...]
    product_measurement: MeasurementRecord | None
    paid_calls_sha256: str
    wall_time_s: float
    tool_cost_s: float | None

    def __post_init__(self) -> None:
        if type(self.task_status) is not TaskStatus:
            raise ValueError("comparison outcome task_status must be an exact TaskStatus")
        if self.task_status is TaskStatus.COMPLETED:
            if self.abstain_reason is not None:
                raise ValueError("completed comparison outcome cannot carry abstain_reason")
        elif type(self.abstain_reason) is not str or not self.abstain_reason:
            raise ValueError("non-completed comparison outcome requires abstain_reason")
        if type(self.surfaced_findings) is not tuple or any(
            type(finding) is not ComparisonSurfacedFinding
            for finding in self.surfaced_findings
        ):
            raise ValueError("comparison surfaced_findings must be an exact tuple")
        if tuple(finding.ordinal for finding in self.surfaced_findings) != tuple(
            range(len(self.surfaced_findings))
        ):
            raise ValueError("comparison finding ordinals must be contiguous from zero")
        finding_ids = tuple(finding.finding_id for finding in self.surfaced_findings)
        if len(set(finding_ids)) != len(finding_ids):
            raise ValueError("comparison surfaced finding_id is duplicate")
        if self.product_measurement is not None and type(
            self.product_measurement
        ) is not MeasurementRecord:
            raise ValueError("comparison product_measurement must be exact or null")
        _require_sha256(self.paid_calls_sha256, "comparison paid_calls_sha256")
        object.__setattr__(self, "wall_time_s", _canonical_nonnegative_number(
            self.wall_time_s, "comparison wall_time_s"
        ))
        if self.tool_cost_s is not None:
            object.__setattr__(self, "tool_cost_s", _canonical_nonnegative_number(
                self.tool_cost_s, "comparison tool_cost_s"
            ))

    def to_json_dict(self) -> dict[str, object]:
        return {
            "schema_version": COMPARISON_ARM_OUTCOME_SCHEMA_VERSION,
            "task_status": self.task_status.value,
            "abstain_reason": self.abstain_reason,
            "surfaced_findings": [
                finding.to_json_dict() for finding in self.surfaced_findings
            ],
            "product_measurement": (
                None
                if self.product_measurement is None
                else self.product_measurement.to_json_dict()
            ),
            "paid_calls_sha256": self.paid_calls_sha256,
            "wall_time_s": self.wall_time_s,
            "tool_cost_s": self.tool_cost_s,
        }

    @classmethod
    def from_json_dict(cls, value: object) -> ComparisonArmOutcome:
        fields = {
            "schema_version",
            "task_status",
            "abstain_reason",
            "surfaced_findings",
            "product_measurement",
            "paid_calls_sha256",
            "wall_time_s",
            "tool_cost_s",
        }
        if type(value) is not dict or set(value) != fields:
            raise ValueError("comparison arm outcome has an invalid field set")
        if value["schema_version"] != COMPARISON_ARM_OUTCOME_SCHEMA_VERSION:
            raise ValueError("comparison arm outcome has an unsupported version")
        if type(value["task_status"]) is not str:
            raise ValueError("comparison arm outcome task_status must be an exact string")
        try:
            task_status = TaskStatus(value["task_status"])
        except ValueError as exc:
            raise ValueError("comparison arm outcome task_status is unknown") from exc
        surfaced = value["surfaced_findings"]
        if type(surfaced) is not list:
            raise ValueError("comparison surfaced_findings must be a list")
        measurement_payload = value["product_measurement"]
        measurement = (
            None
            if measurement_payload is None
            else decode_measurement_record(measurement_payload)
        )
        paid_calls_sha256 = value["paid_calls_sha256"]
        if type(paid_calls_sha256) is not str:
            raise ValueError("comparison paid_calls_sha256 must be an exact string")
        abstain_reason = value["abstain_reason"]
        if abstain_reason is not None and type(abstain_reason) is not str:
            raise ValueError("comparison abstain_reason must be an exact string or null")
        return cls(
            task_status=task_status,
            abstain_reason=abstain_reason,
            surfaced_findings=tuple(
                ComparisonSurfacedFinding.from_json_dict(row) for row in surfaced
            ),
            product_measurement=measurement,
            paid_calls_sha256=paid_calls_sha256,
            wall_time_s=_exact_json_number(value["wall_time_s"], "comparison wall_time_s"),
            tool_cost_s=(
                None
                if value["tool_cost_s"] is None
                else _exact_json_number(value["tool_cost_s"], "comparison tool_cost_s")
            ),
        )


@dataclass(frozen=True, init=False)
class ComparisonOutcomeAuthority:
    """Provider-before capability bound to one exact comparison predeclaration."""

    root: Path
    predeclaration_sha256: str
    authority_id: str
    manifest_sha256: str
    slots: tuple[ComparisonOutcomeSlot, ...]

    @classmethod
    def _create(
        cls,
        *,
        root: Path,
        predeclaration_sha256: str,
        authority_id: str,
        manifest_sha256: str,
        slots: tuple[ComparisonOutcomeSlot, ...],
    ) -> ComparisonOutcomeAuthority:
        authority = object.__new__(cls)
        object.__setattr__(authority, "root", root)
        object.__setattr__(authority, "predeclaration_sha256", predeclaration_sha256)
        object.__setattr__(authority, "authority_id", authority_id)
        object.__setattr__(authority, "manifest_sha256", manifest_sha256)
        object.__setattr__(authority, "slots", slots)
        return authority


@dataclass(frozen=True)
class VerifiedComparisonOutcomes:
    """Fresh-decoded exact comparison outcomes accepted against an external anchor."""

    predeclaration_sha256: str
    authority_id: str
    manifest_sha256: str
    slots: tuple[ComparisonOutcomeSlot, ...]
    outcomes: tuple[ComparisonArmOutcome, ...]
    documents: tuple[CanonicalDocument, ...]


def canonical_json_bytes(value: object) -> bytes:
    """Return the sole accepted current-outcome JSON representation."""
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("authoritative outcome must contain finite canonical JSON") from exc
    return encoded + b"\n"


def read_canonical_json(
    root: Path,
    relative_path: str | Path,
    *,
    maximum_bytes: int = DEFAULT_MAX_OUTCOME_BYTES,
) -> CanonicalDocument:
    """Securely read one canonical file without a path check/reopen race."""
    _require_platform_capabilities()
    if type(maximum_bytes) is not int or maximum_bytes < 1:
        raise ValueError("maximum outcome bytes must be a positive exact integer")
    parts = _relative_parts(relative_path)
    descriptors: list[int] = []
    try:
        current = _open_root(root)
        descriptors.append(current)
        for component in parts[:-1]:
            current = _open_directory_component(current, component)
            descriptors.append(current)
        try:
            file_descriptor = _open_regular_component(current, parts[-1])
        except OSError as exc:
            raise ValueError("authoritative outcome path is missing or unsafe") from exc
        descriptors.append(file_descriptor)
        before = os.fstat(file_descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or before.st_size < 0
            or before.st_size > maximum_bytes
        ):
            raise ValueError(
                "authoritative outcome must be a single-link regular file within the size limit"
            )
        chunks: list[bytes] = []
        remaining = before.st_size
        while remaining:
            chunk = os.read(file_descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValueError("authoritative outcome changed while it was read")
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(file_descriptor, 1):
            raise ValueError("authoritative outcome grew while it was read")
        after = os.fstat(file_descriptor)
        identity_before = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
            before.st_nlink,
        )
        identity_after = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
            after.st_nlink,
        )
        if identity_before != identity_after:
            raise ValueError("authoritative outcome changed while it was read")
        data = b"".join(chunks)
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    value = _decode_canonical_json(data)
    normalized = PurePosixPath(*parts).as_posix()
    return CanonicalDocument(
        relative_path=normalized,
        data=data,
        sha256=hashlib.sha256(data).hexdigest(),
        size=len(data),
        value=value,
    )


def write_canonical_json_once(
    root: Path, relative_path: str | Path, value: object
) -> CanonicalDocument:
    """Create one canonical outcome exactly once; identical retries are read-only."""
    _require_platform_capabilities()
    data = canonical_json_bytes(value)
    if not 1 <= len(data) <= DEFAULT_MAX_OUTCOME_BYTES:
        raise ValueError("authoritative canonical JSON exceeds the size limit")
    parts = _relative_parts(relative_path)
    descriptors: list[int] = []
    temporary_name: str | None = None
    staging_descriptor: int | None = None
    final_parent_descriptor: int | None = None
    try:
        current = _open_root(root, create=True)
        descriptors.append(current)
        with suppress(FileExistsError):
            os.mkdir(".outcome-staging", mode=0o700, dir_fd=current)
            os.fsync(current)
        staging_descriptor = _open_directory_component(current, ".outcome-staging")
        descriptors.append(staging_descriptor)
        for component in parts[:-1]:
            try:
                os.mkdir(component, mode=0o700, dir_fd=current)
                os.fsync(current)
            except FileExistsError:
                pass
            current = _open_directory_component(current, component)
            descriptors.append(current)
        final_parent_descriptor = current
        _recover_published_staging_links(
            staging_descriptor, final_parent_descriptor, parts[-1], data
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        for _attempt in range(16):
            candidate = f".outcome-tmp-{secrets.token_hex(16)}"
            try:
                file_descriptor = os.open(
                    candidate, flags, 0o600, dir_fd=staging_descriptor
                )
            except FileExistsError:
                continue
            temporary_name = candidate
            break
        else:
            raise ValueError("could not allocate an authoritative outcome temporary file")
        descriptors.append(file_descriptor)
        view = memoryview(data)
        while view:
            written = os.write(file_descriptor, view)
            if written <= 0:
                raise OSError("short write of authoritative outcome")
            view = view[written:]
        os.fsync(file_descriptor)
        with suppress(FileExistsError):
            os.link(
                temporary_name,
                parts[-1],
                src_dir_fd=staging_descriptor,
                dst_dir_fd=final_parent_descriptor,
                follow_symlinks=False,
            )
        os.fsync(final_parent_descriptor)
        os.unlink(temporary_name, dir_fd=staging_descriptor)
        temporary_name = None
        os.fsync(staging_descriptor)
    finally:
        if temporary_name is not None and staging_descriptor is not None:
            with suppress(OSError):
                os.unlink(temporary_name, dir_fd=staging_descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    document = read_canonical_json(root, PurePosixPath(*parts).as_posix())
    if document.data != data:
        raise ValueError("write-once authoritative outcome already contains different bytes")
    return document


def write_measurement_outcome_once(
    root: Path, slot: OutcomeSlot, measurement: object
) -> CanonicalDocument:
    """Publish one strict current MeasurementRecord into its derived slot."""
    normalized_slot = _validated_slots((slot,))[0]
    from attest.benchmark.measurement import MeasurementRecord, decode_measurement_record

    if type(measurement) is not MeasurementRecord:
        raise ValueError("authoritative outcome requires an exact MeasurementRecord")
    measurement_payload = measurement.to_json_dict()
    decoded_payload = decode_measurement_record(measurement_payload).to_json_dict()
    if canonical_json_bytes(decoded_payload) != canonical_json_bytes(measurement_payload):
        raise ValueError("authoritative outcome MeasurementRecord did not round-trip")
    payload = {
        "schema_version": OUTCOME_SEAL_SCHEMA_VERSION,
        "slot": normalized_slot.to_json_dict(),
        "outcome": measurement_payload,
    }
    _validate_outcome_envelope(payload, normalized_slot)
    return write_canonical_json_once(root, normalized_slot.relative_path, payload)


def seal_outcomes(
    root: Path,
) -> CanonicalDocument:
    """Seal the exact predeclared slot set after every outcome is durable."""
    predeclaration = read_canonical_json(root, OUTCOME_PREDECLARATION_PATH)
    normalized = _outcome_slots_from_predeclaration(predeclaration.value)
    rows: list[dict[str, object]] = []
    expected_paths = {slot.relative_path for slot in normalized}
    try:
        actual_paths = _list_outcome_files(root, maximum_files=len(normalized) + 1)
    except ValueError:
        raise
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        if missing:
            raise ValueError(f"outcome seal is missing predeclared slot(s): {missing}")
        raise ValueError(f"outcome seal contains extra slot path(s): {extra}")
    for slot in normalized:
        document = read_canonical_json(root, slot.relative_path)
        _validate_outcome_envelope(document.value, slot)
        rows.append(
            {
                "slot_id": slot.slot_id,
                "path": slot.relative_path,
                "sha256": document.sha256,
                "size": document.size,
            }
        )
    payload = {
        "schema_version": OUTCOME_SEAL_SCHEMA_VERSION,
        "predeclaration_sha256": predeclaration.sha256,
        "slots": rows,
    }
    return write_canonical_json_once(root, OUTCOME_SEAL_PATH, payload)


def verify_outcome_seal(
    root: Path,
) -> dict[str, CanonicalDocument]:
    """Fresh-read a seal and every exact slot it commits to."""
    predeclaration = read_canonical_json(root, OUTCOME_PREDECLARATION_PATH)
    normalized = _outcome_slots_from_predeclaration(predeclaration.value)
    seal = read_canonical_json(root, OUTCOME_SEAL_PATH)
    value = seal.value
    if not isinstance(value, dict) or set(value) != {
        "schema_version",
        "predeclaration_sha256",
        "slots",
    }:
        raise ValueError("authoritative outcome seal has an invalid field set")
    if (
        value["schema_version"] != OUTCOME_SEAL_SCHEMA_VERSION
        or value["predeclaration_sha256"] != predeclaration.sha256
        or not isinstance(value["slots"], list)
    ):
        raise ValueError("authoritative outcome seal does not match its predeclaration")
    stored_rows = value["slots"]
    if len(stored_rows) != len(normalized):
        raise ValueError("authoritative outcome seal does not exactly cover predeclared slots")
    documents: dict[str, CanonicalDocument] = {}
    for row, slot in zip(stored_rows, normalized, strict=True):
        if not isinstance(row, dict) or set(row) != {"slot_id", "path", "sha256", "size"}:
            raise ValueError("authoritative outcome seal contains an invalid slot row")
        if row["slot_id"] != slot.slot_id or row["path"] != slot.relative_path:
            raise ValueError("authoritative outcome seal swaps predeclared slot rows")
        _require_sha256(row["sha256"], "outcome seal sha256")
        if type(row["size"]) is not int or row["size"] < 1:
            raise ValueError("authoritative outcome seal size must be an exact positive integer")
    if _list_outcome_files(root, maximum_files=len(normalized) + 1) != {
        slot.relative_path for slot in normalized
    }:
        raise ValueError("authoritative outcome tree does not exactly match its seal")
    for row, slot in zip(stored_rows, normalized, strict=True):
        document = read_canonical_json(root, slot.relative_path)
        if row["sha256"] != document.sha256 or row["size"] != document.size:
            raise ValueError("authoritative outcome digest or size differs from its seal")
        _validate_outcome_envelope(document.value, slot)
        documents[slot.slot_id] = document
    return documents


def build_comparison_outcome_predeclaration(
    *,
    authority_id: str,
    manifest_sha256: str,
    case_bindings: Mapping[str, str],
    repeats: int,
) -> dict[str, object]:
    """Build the exact domain-separated comparison arm predeclaration."""
    _require_sha256(authority_id, "comparison outcome authority_id")
    _require_sha256(manifest_sha256, "comparison outcome manifest_sha256")
    if type(repeats) is not int or repeats < 1:
        raise ValueError("comparison outcome repeats must be an exact positive integer")
    if type(case_bindings) is not dict or not case_bindings:
        raise ValueError("comparison outcome case bindings must be a non-empty mapping")
    _require_outcome_resource_bounds(case_count=len(case_bindings), repeats=repeats)
    normalized_bindings: dict[str, str] = {}
    for case_id, digest in case_bindings.items():
        if type(case_id) is not str or not case_id:
            raise ValueError("comparison outcome case_id must be a non-empty exact string")
        _require_sha256(digest, "comparison outcome bindings_sha256")
        normalized_bindings[case_id] = digest
    slots: list[ComparisonOutcomeSlot] = []
    for case_id in sorted(normalized_bindings):
        for repeat in range(repeats):
            for arm in _OUTCOME_ARMS:
                slots.append(
                    ComparisonOutcomeSlot.create(
                        ordinal=len(slots),
                        authority_id=authority_id,
                        manifest_sha256=manifest_sha256,
                        case_id=case_id,
                        arm=arm,
                        repeat=repeat,
                        bindings_sha256=normalized_bindings[case_id],
                    )
                )
    return {
        "schema_version": COMPARISON_OUTCOME_PREDECLARATION_SCHEMA_VERSION,
        "protocol": COMPARISON_OUTCOME_PROTOCOL,
        "authority_id": authority_id,
        "manifest_sha256": manifest_sha256,
        "repeats": repeats,
        "case_bindings": [
            {"case_id": case_id, "bindings_sha256": normalized_bindings[case_id]}
            for case_id in sorted(normalized_bindings)
        ],
        "outcome_slots": [slot.to_json_dict() for slot in slots],
    }


def predeclare_comparison_outcomes(
    root: Path,
    *,
    authority_id: str,
    manifest_sha256: str,
    case_bindings: Mapping[str, str],
    repeats: int,
) -> ComparisonOutcomeAuthority:
    """Durably predeclare every comparison slot before any arm dispatch."""
    payload = build_comparison_outcome_predeclaration(
        authority_id=authority_id,
        manifest_sha256=manifest_sha256,
        case_bindings=case_bindings,
        repeats=repeats,
    )
    document = write_canonical_json_once(
        root, COMPARISON_OUTCOME_PREDECLARATION_PATH, payload
    )
    slots = _comparison_slots_from_predeclaration(document.value)
    return ComparisonOutcomeAuthority._create(
        root=root,
        predeclaration_sha256=document.sha256,
        authority_id=authority_id,
        manifest_sha256=manifest_sha256,
        slots=slots,
    )


def write_comparison_arm_outcome_once(
    authority: ComparisonOutcomeAuthority,
    slot: ComparisonOutcomeSlot,
    outcome: ComparisonArmOutcome,
) -> CanonicalDocument:
    """Write one exact predeclared arm outcome after fresh capability validation."""
    slots = _fresh_comparison_authority_slots(authority)
    normalized_slot = _normalize_comparison_slot(slot)
    by_id = {candidate.slot_id: candidate for candidate in slots}
    if by_id.get(normalized_slot.slot_id) != normalized_slot:
        raise ValueError("comparison outcome slot is absent from the frozen predeclaration")
    if type(outcome) is not ComparisonArmOutcome:
        raise ValueError("comparison arm outcome must be an exact typed outcome")
    _validate_comparison_arm_outcome(outcome, normalized_slot)
    outcome_payload = outcome.to_json_dict()
    decoded = ComparisonArmOutcome.from_json_dict(outcome_payload)
    if canonical_json_bytes(decoded.to_json_dict()) != canonical_json_bytes(outcome_payload):
        raise ValueError("comparison arm outcome did not round-trip canonically")
    payload = {
        "schema_version": COMPARISON_ARM_OUTCOME_SCHEMA_VERSION,
        "protocol": COMPARISON_OUTCOME_PROTOCOL,
        "slot": normalized_slot.to_json_dict(),
        "outcome": outcome_payload,
    }
    _decode_comparison_outcome_envelope(payload, normalized_slot)
    return write_canonical_json_once(
        authority.root, normalized_slot.relative_path, payload
    )


def seal_comparison_outcomes(
    authority: ComparisonOutcomeAuthority,
) -> CanonicalDocument:
    """Seal the exact complete slot set owned by one frozen comparison capability."""
    slots = _fresh_comparison_authority_slots(authority)
    expected_paths = {slot.relative_path for slot in slots}
    actual_paths = _list_comparison_outcome_files(
        authority.root, maximum_files=len(slots) + 1
    )
    if actual_paths != expected_paths:
        missing = sorted(expected_paths - actual_paths)
        extra = sorted(actual_paths - expected_paths)
        if missing:
            raise ValueError(f"comparison outcome seal is missing slot(s): {missing}")
        raise ValueError(f"comparison outcome seal contains extra slot(s): {extra}")
    rows: list[dict[str, object]] = []
    for slot in slots:
        document = read_canonical_json(authority.root, slot.relative_path)
        _decode_comparison_outcome_envelope(document.value, slot)
        rows.append(
            {
                "slot_id": slot.slot_id,
                "path": slot.relative_path,
                "sha256": document.sha256,
                "size": document.size,
            }
        )
    payload = {
        "schema_version": COMPARISON_OUTCOME_SEAL_SCHEMA_VERSION,
        "protocol": COMPARISON_OUTCOME_PROTOCOL,
        "authority_id": authority.authority_id,
        "manifest_sha256": authority.manifest_sha256,
        "predeclaration_sha256": authority.predeclaration_sha256,
        "slots": rows,
    }
    return write_canonical_json_once(
        authority.root, COMPARISON_OUTCOME_SEAL_PATH, payload
    )


def verify_comparison_outcomes(
    root: Path,
    *,
    expected_predeclaration_sha256: str,
    expected_authority_id: str,
    expected_manifest_sha256: str,
    expected_domain: str = COMPARISON_OUTCOME_PROTOCOL,
) -> VerifiedComparisonOutcomes:
    """Verify and fresh-decode a comparison set against external frozen anchors."""
    for expected_value, label in (
        (expected_predeclaration_sha256, "expected comparison predeclaration"),
        (expected_authority_id, "expected comparison authority_id"),
        (expected_manifest_sha256, "expected comparison manifest_sha256"),
    ):
        _require_sha256(expected_value, label)
    if type(expected_domain) is not str or expected_domain != COMPARISON_OUTCOME_PROTOCOL:
        raise ValueError("comparison outcome authority domain is unsupported")
    predeclaration = read_canonical_json(root, COMPARISON_OUTCOME_PREDECLARATION_PATH)
    if predeclaration.sha256 != expected_predeclaration_sha256:
        raise ValueError("comparison outcome predeclaration differs from its frozen digest")
    slots = _comparison_slots_from_predeclaration(predeclaration.value)
    value = predeclaration.value
    assert isinstance(value, dict)
    if (
        value["authority_id"] != expected_authority_id
        or value["manifest_sha256"] != expected_manifest_sha256
    ):
        raise ValueError("comparison outcome predeclaration external binding mismatch")
    seal = read_canonical_json(root, COMPARISON_OUTCOME_SEAL_PATH)
    seal_value = seal.value
    seal_fields = {
        "schema_version",
        "protocol",
        "authority_id",
        "manifest_sha256",
        "predeclaration_sha256",
        "slots",
    }
    if type(seal_value) is not dict or set(seal_value) != seal_fields:
        raise ValueError("comparison outcome seal has an invalid field set")
    if (
        seal_value["schema_version"] != COMPARISON_OUTCOME_SEAL_SCHEMA_VERSION
        or seal_value["protocol"] != expected_domain
        or seal_value["authority_id"] != expected_authority_id
        or seal_value["manifest_sha256"] != expected_manifest_sha256
        or seal_value["predeclaration_sha256"] != expected_predeclaration_sha256
        or type(seal_value["slots"]) is not list
    ):
        raise ValueError("comparison outcome seal external binding mismatch")
    rows = seal_value["slots"]
    if len(rows) != len(slots):
        raise ValueError("comparison outcome seal does not exactly cover its slots")
    if _list_comparison_outcome_files(root, maximum_files=len(slots) + 1) != {
        slot.relative_path for slot in slots
    }:
        raise ValueError("comparison outcome tree does not exactly match its seal")
    outcomes: list[ComparisonArmOutcome] = []
    documents: list[CanonicalDocument] = []
    for row, slot in zip(rows, slots, strict=True):
        if type(row) is not dict or set(row) != {"slot_id", "path", "sha256", "size"}:
            raise ValueError("comparison outcome seal contains an invalid slot row")
        if row["slot_id"] != slot.slot_id or row["path"] != slot.relative_path:
            raise ValueError("comparison outcome seal swaps slot rows")
        _require_sha256(row["sha256"], "comparison outcome seal sha256")
        if type(row["size"]) is not int or row["size"] < 1:
            raise ValueError("comparison outcome seal size must be an exact positive integer")
        document = read_canonical_json(root, slot.relative_path)
        if document.sha256 != row["sha256"] or document.size != row["size"]:
            raise ValueError("comparison outcome differs from its seal")
        outcome = _decode_comparison_outcome_envelope(document.value, slot)
        documents.append(document)
        outcomes.append(outcome)
    return VerifiedComparisonOutcomes(
        predeclaration_sha256=expected_predeclaration_sha256,
        authority_id=expected_authority_id,
        manifest_sha256=expected_manifest_sha256,
        slots=slots,
        outcomes=tuple(outcomes),
        documents=tuple(documents),
    )


def _fresh_comparison_authority_slots(
    authority: ComparisonOutcomeAuthority,
) -> tuple[ComparisonOutcomeSlot, ...]:
    if type(authority) is not ComparisonOutcomeAuthority:
        raise ValueError("comparison outcome authority must be an exact capability")
    _require_sha256(authority.predeclaration_sha256, "comparison predeclaration digest")
    _require_sha256(authority.authority_id, "comparison authority_id")
    _require_sha256(authority.manifest_sha256, "comparison manifest_sha256")
    predeclaration = read_canonical_json(
        authority.root, COMPARISON_OUTCOME_PREDECLARATION_PATH
    )
    if predeclaration.sha256 != authority.predeclaration_sha256:
        raise ValueError("comparison outcome predeclaration differs from frozen authority")
    slots = _comparison_slots_from_predeclaration(predeclaration.value)
    value = predeclaration.value
    assert isinstance(value, dict)
    if (
        value["authority_id"] != authority.authority_id
        or value["manifest_sha256"] != authority.manifest_sha256
        or slots != authority.slots
    ):
        raise ValueError("comparison outcome authority binding mismatch")
    return slots


def _comparison_slots_from_predeclaration(
    value: object,
) -> tuple[ComparisonOutcomeSlot, ...]:
    fields = {
        "schema_version",
        "protocol",
        "authority_id",
        "manifest_sha256",
        "repeats",
        "case_bindings",
        "outcome_slots",
    }
    if type(value) is not dict or set(value) != fields:
        raise ValueError("comparison outcome predeclaration has an invalid field set")
    if (
        value["schema_version"] != COMPARISON_OUTCOME_PREDECLARATION_SCHEMA_VERSION
        or value["protocol"] != COMPARISON_OUTCOME_PROTOCOL
    ):
        raise ValueError("comparison outcome predeclaration protocol is unsupported")
    authority_id = value["authority_id"]
    manifest_sha256 = value["manifest_sha256"]
    if type(authority_id) is not str or type(manifest_sha256) is not str:
        raise ValueError("comparison outcome predeclaration digests must be strings")
    _require_sha256(authority_id, "comparison outcome authority_id")
    _require_sha256(manifest_sha256, "comparison outcome manifest_sha256")
    repeats = value["repeats"]
    case_rows = value["case_bindings"]
    slot_rows = value["outcome_slots"]
    if type(repeats) is not int or repeats < 1:
        raise ValueError("comparison outcome repeats must be an exact positive integer")
    if type(case_rows) is not list or not case_rows:
        raise ValueError("comparison outcome case_bindings must be a non-empty list")
    _require_outcome_resource_bounds(case_count=len(case_rows), repeats=repeats)
    bindings: dict[str, str] = {}
    for row in case_rows:
        if type(row) is not dict or set(row) != {"case_id", "bindings_sha256"}:
            raise ValueError("comparison outcome case binding has an invalid field set")
        case_id = row["case_id"]
        digest = row["bindings_sha256"]
        if type(case_id) is not str or not case_id or case_id in bindings:
            raise ValueError("comparison outcome case binding is duplicate or invalid")
        if type(digest) is not str:
            raise ValueError("comparison outcome binding digest must be an exact string")
        _require_sha256(digest, "comparison outcome bindings_sha256")
        bindings[case_id] = digest
    if type(slot_rows) is not list or not slot_rows:
        raise ValueError("comparison outcome slots must be a non-empty list")
    supplied = _validated_comparison_slots(
        tuple(ComparisonOutcomeSlot.from_json_dict(row) for row in slot_rows)
    )
    rebuilt = build_comparison_outcome_predeclaration(
        authority_id=authority_id,
        manifest_sha256=manifest_sha256,
        case_bindings=bindings,
        repeats=repeats,
    )
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(value):
        raise ValueError("comparison outcome predeclaration is not exactly derived")
    return supplied


def _normalize_comparison_slot(slot: ComparisonOutcomeSlot) -> ComparisonOutcomeSlot:
    if type(slot) is not ComparisonOutcomeSlot:
        raise ValueError("comparison outcome slot must be an exact typed slot")
    rebuilt = ComparisonOutcomeSlot.create(
        ordinal=slot.ordinal,
        authority_id=slot.authority_id,
        manifest_sha256=slot.manifest_sha256,
        case_id=slot.case_id,
        arm=slot.arm,
        repeat=slot.repeat,
        bindings_sha256=slot.bindings_sha256,
    )
    if rebuilt != slot:
        raise ValueError("comparison outcome slot derived identity/path mismatch")
    return rebuilt


def _validated_comparison_slots(
    slots: Sequence[ComparisonOutcomeSlot],
) -> tuple[ComparisonOutcomeSlot, ...]:
    normalized = tuple(_normalize_comparison_slot(slot) for slot in slots)
    identities = tuple((slot.case_id, slot.arm, slot.repeat) for slot in normalized)
    if (
        len({slot.slot_id for slot in normalized}) != len(normalized)
        or len({slot.relative_path for slot in normalized}) != len(normalized)
        or len(set(identities)) != len(normalized)
        or len({slot.ordinal for slot in normalized}) != len(normalized)
    ):
        raise ValueError("comparison outcome predeclaration contains duplicate slots")
    ordered = tuple(sorted(normalized, key=lambda slot: slot.ordinal))
    if tuple(slot.ordinal for slot in ordered) != tuple(range(len(ordered))):
        raise ValueError("comparison outcome ordinals must be contiguous from zero")
    if len({(slot.authority_id, slot.manifest_sha256) for slot in ordered}) != 1:
        raise ValueError("comparison outcome slots cross authority domains")
    return ordered


def _validate_comparison_arm_outcome(
    outcome: ComparisonArmOutcome, slot: ComparisonOutcomeSlot
) -> None:
    if slot.arm == ARM_ATTEST_PRODUCT:
        measurement = outcome.product_measurement
        if type(measurement) is not MeasurementRecord:
            raise ValueError("product comparison outcome requires current MeasurementRecord")
        if (
            measurement.case_id != slot.case_id
            or measurement.arm != slot.arm
            or measurement.repeat != slot.repeat
            or measurement.task_status is not outcome.task_status
        ):
            raise ValueError("product measurement does not match its comparison slot/status")
        published_ids = tuple(
            finding.finding_id
            for finding in measurement.findings
            if finding.finding_status is FindingStatus.PUBLISHED
        )
        surfaced_ids = tuple(finding.finding_id for finding in outcome.surfaced_findings)
        if published_ids != surfaced_ids:
            raise ValueError("product surfaced findings do not match its MeasurementRecord")
    elif outcome.product_measurement is not None:
        raise ValueError("baseline comparison outcomes cannot carry product measurement")
    if slot.arm == "ruff_static" and outcome.paid_calls_sha256 != EMPTY_PAID_CALLS_SHA256:
        raise ValueError("ruff comparison outcome must bind exact empty paid calls")


def _decode_comparison_outcome_envelope(
    value: object, slot: ComparisonOutcomeSlot
) -> ComparisonArmOutcome:
    fields = {"schema_version", "protocol", "slot", "outcome"}
    if type(value) is not dict or set(value) != fields:
        raise ValueError("comparison outcome envelope has an invalid field set")
    if (
        value["schema_version"] != COMPARISON_ARM_OUTCOME_SCHEMA_VERSION
        or value["protocol"] != COMPARISON_OUTCOME_PROTOCOL
    ):
        raise ValueError("comparison outcome envelope protocol is unsupported")
    if canonical_json_bytes(value["slot"]) != canonical_json_bytes(slot.to_json_dict()):
        raise ValueError("comparison outcome envelope slot binding mismatch")
    outcome = ComparisonArmOutcome.from_json_dict(value["outcome"])
    _validate_comparison_arm_outcome(outcome, slot)
    return outcome


def _exact_json_number(value: object, label: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} must be an exact finite number")
    return _canonical_nonnegative_number(value, label)


def _canonical_nonnegative_number(value: object, label: str) -> float:
    if type(value) not in {int, float}:
        raise ValueError(f"{label} must be a finite non-negative number")
    assert isinstance(value, (int, float)) and not isinstance(value, bool)
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return 0.0 if number == 0.0 else number


def _list_comparison_outcome_files(root: Path, *, maximum_files: int) -> set[str]:
    return _list_flat_outcome_files(
        root, COMPARISON_OUTCOME_DIRECTORY, maximum_files=maximum_files
    )


def _open_root(root: Path, *, create: bool = False) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    absolute = root if root.is_absolute() else Path.cwd() / root
    try:
        descriptor = os.open("/", flags)
        for component in absolute.parts[1:]:
            if create:
                with suppress(FileExistsError):
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                    os.fsync(descriptor)
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
    except OSError as exc:
        with suppress(UnboundLocalError, OSError):
            os.close(descriptor)
        raise ValueError("authoritative outcome root is missing, a symlink, or unsafe") from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        os.close(descriptor)
        raise ValueError("authoritative outcome root must be a directory")
    return descriptor


def _open_directory_component(parent: int, component: str) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW
    try:
        descriptor = os.open(component, flags, dir_fd=parent)
    except OSError as exc:
        raise ValueError("authoritative outcome parent is a symlink or unsafe") from exc
    opened = os.fstat(descriptor)
    if not stat.S_ISDIR(opened.st_mode):
        os.close(descriptor)
        raise ValueError("authoritative outcome parent must be a directory")
    return descriptor


def _open_regular_component(parent: int, component: str) -> int:
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_CLOEXEC | os.O_NOFOLLOW
    return os.open(component, flags, dir_fd=parent)


def _relative_parts(relative_path: str | Path) -> tuple[str, ...]:
    if isinstance(relative_path, Path):
        raw = relative_path.as_posix()
    elif type(relative_path) is str:
        raw = relative_path
    else:
        raise ValueError("authoritative outcome path must be an exact relative path")
    if "\\" in raw or (len(raw) >= 2 and raw[1] == ":"):
        raise ValueError("authoritative outcome path must be a portable relative path")
    if any(ord(character) < 32 or ord(character) == 127 for character in raw):
        raise ValueError("authoritative outcome path contains a control character")
    pure = PurePosixPath(raw)
    if (
        raw != pure.as_posix()
        or pure.is_absolute()
        or not pure.parts
        or any(part in ("", ".", "..") for part in pure.parts)
    ):
        raise ValueError("authoritative outcome path must stay below its root")
    return pure.parts


def _decode_canonical_json(data: bytes) -> object:
    if not data or data.startswith(b"\xef\xbb\xbf"):
        raise ValueError("authoritative outcome is not canonical UTF-8 JSON")

    def pairs(rows: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in rows:
            if key in result:
                raise ValueError("authoritative outcome contains a duplicate JSON key")
            result[key] = value
        return result

    def constant(_: str) -> object:
        raise ValueError("authoritative outcome contains a non-finite JSON number")

    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=pairs,
            parse_constant=constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("authoritative outcome is not canonical JSON") from exc
    _require_finite_tree(value)
    if canonical_json_bytes(value) != data:
        raise ValueError("authoritative outcome bytes are not canonical JSON")
    return value


def _require_finite_tree(value: object) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("authoritative outcome contains a non-finite JSON number")
    if isinstance(value, list):
        for item in value:
            _require_finite_tree(item)
    elif isinstance(value, dict):
        for item in value.values():
            _require_finite_tree(item)


def _validated_slots(slots: Sequence[OutcomeSlot]) -> tuple[OutcomeSlot, ...]:
    normalized = tuple(slots)
    if any(type(slot) is not OutcomeSlot for slot in normalized):
        raise ValueError("outcome slots must be exact OutcomeSlot values")
    for slot in normalized:
        if slot.arm not in _OUTCOME_ARMS:
            raise ValueError("outcome slot arm is not supported by this protocol")
        rebuilt = OutcomeSlot.create(
            ordinal=slot.ordinal,
            case_id=slot.case_id,
            arm=slot.arm,
            repeat=slot.repeat,
            bindings_sha256=slot.bindings_sha256,
        )
        if rebuilt != slot:
            raise ValueError("outcome slot derived identity/path does not match its fields")
    ids = tuple(slot.slot_id for slot in normalized)
    paths = tuple(slot.relative_path for slot in normalized)
    identities = tuple((slot.case_id, slot.arm, slot.repeat) for slot in normalized)
    ordinals = tuple(slot.ordinal for slot in normalized)
    if (
        len(set(ids)) != len(ids)
        or len(set(paths)) != len(paths)
        or len(set(identities)) != len(identities)
        or len(set(ordinals)) != len(ordinals)
    ):
        raise ValueError("outcome predeclaration contains duplicate slots")
    ordered = tuple(sorted(normalized, key=lambda slot: slot.ordinal))
    if tuple(slot.ordinal for slot in ordered) != tuple(range(len(ordered))):
        raise ValueError("outcome slot ordinals must be contiguous from zero")
    return ordered


def _outcome_slots_from_predeclaration(value: object) -> tuple[OutcomeSlot, ...]:
    fields = {
        "schema_version",
        "protocol",
        "manifest_sha256",
        "repeats",
        "case_bindings",
        "outcome_slots",
    }
    if type(value) is not dict or set(value) != fields:
        raise ValueError("outcome predeclaration has an invalid field set")
    if (
        value["schema_version"] != OUTCOME_PREDECLARATION_SCHEMA_VERSION
        or value["protocol"] != OUTCOME_PREDECLARATION_PROTOCOL
    ):
        raise ValueError("outcome predeclaration has an unsupported schema/protocol")
    _require_sha256(value["manifest_sha256"], "outcome manifest_sha256")
    repeats = value["repeats"]
    if type(repeats) is not int or repeats < 1:
        raise ValueError("outcome predeclaration repeats must be an exact positive integer")
    _require_outcome_resource_bounds(case_count=1, repeats=repeats)
    case_rows = value["case_bindings"]
    if type(case_rows) is not list or not case_rows:
        raise ValueError("outcome predeclaration case_bindings must be a non-empty list")
    _require_outcome_resource_bounds(case_count=len(case_rows), repeats=repeats)
    case_bindings: dict[str, str] = {}
    for row in case_rows:
        if type(row) is not dict or set(row) != {"case_id", "bindings_sha256"}:
            raise ValueError("outcome predeclaration case binding has an invalid field set")
        case_id = row["case_id"]
        binding = row["bindings_sha256"]
        if type(case_id) is not str or not case_id or case_id in case_bindings:
            raise ValueError("outcome predeclaration case binding is duplicate or invalid")
        _require_sha256(binding, "outcome bindings_sha256")
        assert isinstance(binding, str)
        case_bindings[case_id] = binding
    slot_rows = value["outcome_slots"]
    if type(slot_rows) is not list or not slot_rows:
        raise ValueError("outcome predeclaration slots must be a non-empty list")
    if len(slot_rows) > MAX_OUTCOME_SLOTS:
        raise ValueError("outcome predeclaration exceeds the slot limit")
    supplied_slots = _validated_slots(
        tuple(OutcomeSlot.from_json_dict(row) for row in slot_rows)
    )
    supplied_repeats = {slot.repeat for slot in supplied_slots}
    if supplied_repeats != set(range(repeats)):
        raise ValueError(
            "outcome predeclaration repeats must be contiguous from repeat zero"
        )
    rebuilt = build_outcome_predeclaration(
        manifest_sha256=str(value["manifest_sha256"]),
        case_bindings=case_bindings,
        repeats=repeats,
    )
    if canonical_json_bytes(rebuilt) != canonical_json_bytes(value):
        raise ValueError(
            "outcome predeclaration slots/bindings are not the exact derived protocol"
        )
    slots_value = rebuilt["outcome_slots"]
    assert isinstance(slots_value, list)
    return tuple(OutcomeSlot.from_json_dict(row) for row in slots_value)


def build_outcome_predeclaration(
    *,
    manifest_sha256: str,
    case_bindings: Mapping[str, str],
    repeats: int,
) -> dict[str, object]:
    """Construct the only supported comparison outcome predeclaration."""
    _require_sha256(manifest_sha256, "outcome manifest_sha256")
    if type(repeats) is not int or repeats < 1:
        raise ValueError("outcome predeclaration repeats must be an exact positive integer")
    if type(case_bindings) is not dict or not case_bindings:
        raise ValueError("outcome case bindings must be a non-empty exact mapping")
    _require_outcome_resource_bounds(case_count=len(case_bindings), repeats=repeats)
    normalized_bindings: dict[str, str] = {}
    for case_id, binding in case_bindings.items():
        if type(case_id) is not str or not case_id:
            raise ValueError("outcome case_id must be a non-empty exact string")
        _require_sha256(binding, "outcome bindings_sha256")
        normalized_bindings[case_id] = binding
    slots: list[OutcomeSlot] = []
    for case_id in sorted(normalized_bindings):
        for repeat in range(repeats):
            for arm in _OUTCOME_ARMS:
                slots.append(
                    OutcomeSlot.create(
                        ordinal=len(slots),
                        case_id=case_id,
                        arm=arm,
                        repeat=repeat,
                        bindings_sha256=normalized_bindings[case_id],
                    )
                )
    return {
        "schema_version": OUTCOME_PREDECLARATION_SCHEMA_VERSION,
        "protocol": OUTCOME_PREDECLARATION_PROTOCOL,
        "manifest_sha256": manifest_sha256,
        "repeats": repeats,
        "case_bindings": [
            {"case_id": case_id, "bindings_sha256": normalized_bindings[case_id]}
            for case_id in sorted(normalized_bindings)
        ],
        "outcome_slots": [slot.to_json_dict() for slot in slots],
    }


def _require_outcome_resource_bounds(*, case_count: int, repeats: int) -> None:
    if type(case_count) is not int or not 1 <= case_count <= MAX_OUTCOME_CASES:
        raise ValueError("outcome predeclaration exceeds the case limit")
    if type(repeats) is not int or not 1 <= repeats <= MAX_OUTCOME_REPEATS:
        raise ValueError("outcome predeclaration exceeds the repeat limit")
    if case_count * repeats * len(_OUTCOME_ARMS) > MAX_OUTCOME_SLOTS:
        raise ValueError("outcome predeclaration exceeds the slot limit")


def _validate_outcome_envelope(value: object, slot: OutcomeSlot) -> None:
    if not isinstance(value, dict) or set(value) != {"schema_version", "slot", "outcome"}:
        raise ValueError("authoritative outcome envelope has an invalid field set")
    if value["schema_version"] != OUTCOME_SEAL_SCHEMA_VERSION:
        raise ValueError("authoritative outcome envelope has an unsupported version")
    if canonical_json_bytes(value["slot"]) != canonical_json_bytes(slot.to_json_dict()):
        raise ValueError("outcome artifact slot identity does not match its predeclaration")
    if type(value["outcome"]) is not dict or not value["outcome"]:
        raise ValueError("authoritative outcome envelope requires a non-empty outcome")
    from attest.benchmark.measurement import decode_measurement_record

    try:
        measurement = decode_measurement_record(value["outcome"])
    except ValueError as exc:
        raise ValueError("authoritative outcome measurement is invalid") from exc
    if (
        measurement.case_id != slot.case_id
        or measurement.arm != slot.arm
        or measurement.repeat != slot.repeat
    ):
        raise ValueError("authoritative outcome measurement case/arm/repeat binding mismatch")


def _list_outcome_files(root: Path, *, maximum_files: int) -> set[str]:
    """List the flat outcomes directory through handles; reject extra structure."""
    return _list_flat_outcome_files(root, "outcomes", maximum_files=maximum_files)


def _list_flat_outcome_files(
    root: Path, directory: str, *, maximum_files: int
) -> set[str]:
    """List one authority-owned flat directory solely through safe handles."""
    descriptors: list[int] = []
    try:
        root_fd = _open_root(root)
        descriptors.append(root_fd)
        try:
            outcomes_fd = _open_directory_component(root_fd, directory)
        except ValueError as exc:
            if isinstance(exc.__cause__, OSError) and exc.__cause__.errno == errno.ENOENT:
                return set()
            raise
        descriptors.append(outcomes_fd)
        names = os.listdir(outcomes_fd)
        if len(names) > maximum_files:
            raise ValueError("authoritative outcome tree contains too many entries")
        found: set[str] = set()
        for name in names:
            metadata = os.stat(name, dir_fd=outcomes_fd, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise ValueError(
                    "authoritative outcome tree must be flat and contain regular files only"
                )
            found.add(PurePosixPath(directory, name).as_posix())
        return found
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _require_sha256(value: object, label: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256 digest")


def _require_platform_capabilities() -> None:
    required_constants = ("O_NOFOLLOW", "O_DIRECTORY", "O_NONBLOCK", "O_CLOEXEC")
    missing = [
        name
        for name in required_constants
        if not hasattr(os, name)
        or type(getattr(os, name)) is not int
        or getattr(os, name) == 0
    ]
    required_dir_fd_names = {"open", "mkdir", "stat", "unlink", "link"}
    if missing or not required_dir_fd_names.issubset(_SUPPORTED_DIR_FD_NAMES):
        detail = ", ".join(missing) if missing else "dir_fd operations"
        raise ValueError(
            f"authoritative outcome filesystem capability is unavailable: {detail}"
        )
    if not {"stat", "link"}.issubset(_SUPPORTED_FOLLOW_SYMLINK_NAMES):
        raise ValueError(
            "authoritative outcome filesystem capability lacks no-follow metadata operations"
        )
    if "listdir" not in _SUPPORTED_FD_NAMES:
        raise ValueError(
            "authoritative outcome filesystem capability lacks fd-based listdir"
        )


def _recover_published_staging_links(
    staging_descriptor: int,
    final_parent_descriptor: int,
    final_name: str,
    expected_data: bytes,
) -> None:
    """Recover only the unique, byte-identical hard-link crash state."""
    staging_names = os.listdir(staging_descriptor)
    try:
        final_descriptor = _open_regular_component(final_parent_descriptor, final_name)
    except FileNotFoundError as exc:
        if staging_names:
            raise ValueError(
                "authoritative outcome staging recovery is ambiguous"
            ) from exc
        return
    try:
        final_stat = os.fstat(final_descriptor)
        linked: list[str] = []
        unrelated: list[str] = []
        for name in staging_names:
            metadata = os.stat(name, dir_fd=staging_descriptor, follow_symlinks=False)
            if (
                stat.S_ISREG(metadata.st_mode)
                and metadata.st_dev == final_stat.st_dev
                and metadata.st_ino == final_stat.st_ino
            ):
                linked.append(name)
            else:
                unrelated.append(name)
        if final_stat.st_nlink == 1:
            if staging_names:
                raise ValueError("authoritative outcome staging recovery has an unrelated file")
            return
        if unrelated or len(linked) != 1 or final_stat.st_nlink != 2:
            raise ValueError("authoritative outcome staging recovery has ambiguous links")
        if final_stat.st_size != len(expected_data):
            raise ValueError("authoritative outcome staging recovery bytes differ")
        chunks: list[bytes] = []
        remaining = final_stat.st_size
        while remaining:
            chunk = os.read(final_descriptor, min(remaining, 64 * 1024))
            if not chunk:
                raise ValueError("authoritative outcome staging recovery is truncated")
            chunks.append(chunk)
            remaining -= len(chunk)
        if b"".join(chunks) != expected_data:
            raise ValueError("authoritative outcome staging recovery bytes differ")
        os.unlink(linked[0], dir_fd=staging_descriptor)
        os.fsync(staging_descriptor)
        os.fsync(final_parent_descriptor)
        if os.fstat(final_descriptor).st_nlink != 1:
            raise ValueError("authoritative outcome staging recovery did not settle links")
    finally:
        os.close(final_descriptor)
