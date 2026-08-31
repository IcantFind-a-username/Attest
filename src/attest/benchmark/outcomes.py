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

OUTCOME_SEAL_SCHEMA_VERSION = "1"
OUTCOME_SEAL_PATH = "outcomes.seal.json"
OUTCOME_PREDECLARATION_SCHEMA_VERSION = "1"
OUTCOME_PREDECLARATION_PROTOCOL = "comparison-authoritative-outcomes-v1"
OUTCOME_PREDECLARATION_PATH = "outcomes.predeclaration.json"
DEFAULT_MAX_OUTCOME_BYTES = 4 * 1024 * 1024
MAX_OUTCOME_CASES = 128
MAX_OUTCOME_REPEATS = 20
MAX_OUTCOME_SLOTS = 4096
_OUTCOME_ARMS = ("attest_product", "bare_prompt", "ruff_static")
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
    if decode_measurement_record(measurement_payload) != measurement:
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
    descriptors: list[int] = []
    try:
        root_fd = _open_root(root)
        descriptors.append(root_fd)
        try:
            outcomes_fd = _open_directory_component(root_fd, "outcomes")
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
            found.add(PurePosixPath("outcomes", name).as_posix())
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
