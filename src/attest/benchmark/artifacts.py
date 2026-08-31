"""Allowlisted, redacted, hash-bound evidence artifacts for benchmark runs.

An artifact store is the only way benchmark output leaves the process. It fails
closed: a kind that is not preregistered, a name that escapes the store or
names a credential file, or content that still looks like a secret after
redaction is refused before any byte reaches disk. Raw provider prompts and
responses have no allowlisted kind on purpose.

The integrity manifest is written LAST, via atomic replace, and sealing the
store forbids further writes -- so a manifest can never describe a store that
kept growing behind it.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from xml.etree import ElementTree

ARTIFACT_SCHEMA_VERSION = "1"

# Protocol-level ceilings used by both issuance and offline verification.
MAX_BOUNDED_ARTIFACT_BYTES = 16_384
MAX_ARTIFACT_BYTES = 1_048_576
MAX_ARTIFACT_MANIFEST_BYTES = 8_388_608
MAX_VALIDATION_DOCUMENT_BYTES = 8_388_608

#: Every artifact class a benchmark run may persist. Anything else -- notably
#: raw proposer/generator prompts and responses -- is refused.
ARTIFACT_KINDS = frozenset(
    {
        "manifest",
        "product_ledger",
        "predictions",
        "repro_output",
        "junit",
        "scored_run",
        "github_summary",
        "validation_stdout",
        "validation_junit",
        "validation_test",
        "validation_command",
        "validation_interpreter",
        "validation_environment",
        "validation_source",
        "validation_executor",
    }
)

#: Kinds whose content is untrusted tool output: bounded by truncation to a
#: tail rather than refused, because a truncated tail is still evidence.
BOUNDED_KINDS = frozenset(
    {"repro_output", "junit", "validation_stdout", "validation_junit"}
)

MANIFEST_NAME = "artifacts.json"
REDACTION = "[REDACTED]"
_DEPENDENCY_FAILURE_MARKER = b"DEPENDENCY attest\n"
_JUNIT_SUMMARY = re.compile(
    rb"J attest:(\d+),(\d+),(\d+),(\d+):([A-Za-z0-9_-]{43})\n"
)

_CREDENTIAL_NAMES = frozenset(
    {
        ".git-credentials",
        ".netrc",
        ".npmrc",
        "credentials",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
    }
)
_CREDENTIAL_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore")

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{16,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bsk-ant-[A-Za-z0-9\-_]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9]{20,}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z\-_]{35}\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
)

_SECRET_NAME_PARTS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "CREDENTIAL")


class ArtifactError(ValueError):
    """An artifact was refused, or a stored artifact no longer matches its digest."""

    def __init__(self, message: str, *, failure_path: str | None = None) -> None:
        self.failure_path = failure_path
        super().__init__(message)


@dataclass(frozen=True)
class ArtifactRecord:
    """One stored artifact and the digest that binds its exact bytes."""

    name: str
    kind: str
    sha256: str
    size_bytes: int
    truncated: bool = False

    def __post_init__(self) -> None:
        """Reject references that could resolve outside their artifact root."""
        if _relative_name(self.name) != self.name:
            raise ArtifactError("artifact name must use normalized relative form")

    def to_json_dict(self) -> dict[str, object]:
        """Canonical mapping used inside the integrity manifest."""
        return {
            "name": self.name,
            "kind": self.kind,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "truncated": self.truncated,
        }


def process_secrets() -> tuple[str, ...]:
    """Secret values this process already holds, for recursive redaction."""
    return tuple(
        value
        for name, value in os.environ.items()
        if value and any(part in name.upper() for part in _SECRET_NAME_PARTS)
    )


def redact(value: object, secrets: Sequence[str]) -> object:
    """Replace every known secret value at every nesting depth."""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, REDACTION)
        return value
    if isinstance(value, Mapping):
        return {str(key): redact(item, secrets) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(item, secrets) for item in value]
    return value


class ArtifactStore:
    """Write-once, allowlisted artifact directory sealed by a digest manifest."""

    def __init__(
        self,
        root: Path,
        *,
        secrets: Sequence[str] = (),
        max_bounded_bytes: int = MAX_BOUNDED_ARTIFACT_BYTES,
        max_artifact_bytes: int = MAX_ARTIFACT_BYTES,
    ) -> None:
        if max_bounded_bytes < 64:
            raise ArtifactError("max_bounded_bytes must be at least 64")
        if max_bounded_bytes > MAX_BOUNDED_ARTIFACT_BYTES:
            raise ArtifactError(
                f"max_bounded_bytes must not exceed {MAX_BOUNDED_ARTIFACT_BYTES}"
            )
        if max_artifact_bytes <= 0:
            raise ArtifactError("artifact size limits must be positive")
        if max_artifact_bytes > MAX_ARTIFACT_BYTES:
            raise ArtifactError(
                f"max_artifact_bytes must not exceed {MAX_ARTIFACT_BYTES}"
            )
        if max_artifact_bytes < max_bounded_bytes:
            raise ArtifactError(
                "max_artifact_bytes must be at least max_bounded_bytes"
            )
        self.root = root
        self._secrets = tuple(secret for secret in secrets if secret)
        self._max_bounded_bytes = max_bounded_bytes
        self._max_artifact_bytes = max_artifact_bytes
        self._records: list[ArtifactRecord] = []
        self._finalized = False

    def records(self) -> tuple[ArtifactRecord, ...]:
        """Every artifact accepted so far, in write order."""
        return tuple(self._records)

    @property
    def finalized(self) -> bool:
        return self._finalized

    def write(self, name: str, kind: str, payload: object) -> ArtifactRecord:
        """Store one allowlisted artifact after redaction, bounding, and scanning."""
        if self._finalized:
            raise ArtifactError("artifact store is finalized and accepts no further writes")
        encoded, truncated = self.render_bytes(kind, payload)
        relative = _relative_name(name)
        _reject_credential_name(relative)
        _atomic_write(self.root, relative, encoded)
        record = ArtifactRecord(
            name=relative,
            kind=kind,
            sha256=sha256_bytes(encoded),
            size_bytes=len(encoded),
            truncated=truncated,
        )
        self._records = [existing for existing in self._records if existing.name != relative]
        self._records.append(record)
        return record

    def render_bytes(self, kind: str, payload: object) -> tuple[bytes, bool]:
        """Return the exact redacted, bounded bytes that ``write`` would persist."""
        if kind not in ARTIFACT_KINDS:
            raise ArtifactError(f"artifact kind {kind!r} is not allowlisted")
        text, truncated = self._render(kind, payload)
        _reject_secret_content(text)
        encoded = text.encode("utf-8")
        if len(encoded) > self._max_artifact_bytes:
            raise ArtifactError(
                f"artifact payload exceeds the {self._max_artifact_bytes}-byte limit"
            )
        return encoded, truncated

    def finalize(self) -> Path:
        """Write the digest manifest LAST via atomic replace and seal the store."""
        if self._finalized:
            raise ArtifactError("artifact store is finalized and accepts no further writes")
        self.root.mkdir(parents=True, exist_ok=True)
        document = {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            "artifacts": [
                record.to_json_dict() for record in sorted(self._records, key=lambda r: r.name)
            ],
        }
        encoded = canonical_json_bytes(document)
        if len(encoded) > MAX_ARTIFACT_MANIFEST_BYTES:
            raise ArtifactError(
                "artifact manifest exceeds its protocol byte limit",
                failure_path="artifacts.manifest.size_bytes",
            )
        path = self.root / MANIFEST_NAME
        _atomic_write(self.root, MANIFEST_NAME, encoded)
        self._finalized = True
        return path

    def _render(self, kind: str, payload: object) -> tuple[str, bool]:
        redacted = redact(payload, self._secrets)
        if kind == "validation_environment" and isinstance(redacted, Mapping):
            variables = redacted.get("variables")
            if isinstance(variables, Mapping):
                redacted = {
                    **redacted,
                    "sha256": hashlib.sha256(
                        canonical_json_bytes(variables)
                    ).hexdigest(),
                }
        if isinstance(redacted, str):
            text = redacted
        elif isinstance(redacted, bytes):
            text = redacted.decode("utf-8", errors="replace")
        else:
            text = canonical_json_bytes(redacted).decode("utf-8")
        if kind not in BOUNDED_KINDS:
            return text, False
        encoded = text.encode("utf-8")
        if len(encoded) <= self._max_bounded_bytes:
            return text, False
        if kind == "validation_junit":
            summary = _validation_junit_summary(encoded)
            if summary is not None and len(summary) <= self._max_bounded_bytes:
                tail_size = self._max_bounded_bytes - len(summary)
                tail = encoded[-tail_size:] if tail_size else b""
                return (summary + tail).decode("utf-8", errors="ignore"), True
        if kind == "validation_stdout":
            if _is_dependency_failure(encoded):
                tail_size = self._max_bounded_bytes - len(_DEPENDENCY_FAILURE_MARKER)
                tail = encoded[-tail_size:] if tail_size else b""
                return (
                    _DEPENDENCY_FAILURE_MARKER + tail
                ).decode("utf-8", errors="ignore"), True
            signature = validation_failure_signature(encoded)
            if signature is not None:
                token = base64.urlsafe_b64encode(bytes.fromhex(signature)).rstrip(b"=")
                marker = b"FAILED attest:" + token + b"\n"
                if len(marker) > self._max_bounded_bytes:
                    raise ArtifactError(
                        "validation stdout bound is too small for its failure signature"
                    )
                tail_size = self._max_bounded_bytes - len(marker)
                tail = encoded[-tail_size:] if tail_size else b""
                return (marker + tail).decode("utf-8", errors="ignore"), True
        return encoded[-self._max_bounded_bytes :].decode("utf-8", errors="ignore"), True


def verify_artifacts(root: Path) -> tuple[ArtifactRecord, ...]:
    """Re-hash every listed artifact and refuse unknown files in the store."""
    try:
        document = json.loads(
            read_artifact_bytes(
                root, MANIFEST_NAME, max_bytes=MAX_ARTIFACT_MANIFEST_BYTES
            )
        )
    except (ArtifactError, json.JSONDecodeError, UnicodeError) as exc:
        failure_path = (
            "artifacts.manifest.size_bytes"
            if isinstance(exc, ArtifactError) and "byte limit" in str(exc)
            else "artifacts.manifest"
        )
        raise ArtifactError(
            "artifact manifest must be valid contained JSON",
            failure_path=failure_path,
        ) from exc
    if not isinstance(document, dict):
        raise ArtifactError(
            "artifact manifest must be an object",
            failure_path="artifacts.manifest",
        )
    if set(document) != {"schema_version", "artifacts"}:
        raise ArtifactError(
            "artifact manifest has invalid fields",
            failure_path="artifacts.manifest.fields",
        )
    if document.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
        raise ArtifactError(
            "unsupported artifact manifest schema",
            failure_path="artifacts.manifest.schema_version",
        )
    entries = document.get("artifacts")
    if not isinstance(entries, list):
        raise ArtifactError(
            "artifact manifest must list artifacts",
            failure_path="artifacts.manifest.artifacts",
        )
    records = tuple(_record(entry, index) for index, entry in enumerate(entries))
    names: set[str] = set()
    for record in records:
        if record.name in names:
            raise ArtifactError(
                "artifact manifest contains duplicate artifact names",
                failure_path=f"artifacts.{record.name}.name",
            )
        names.add(record.name)
    listed = {record.name for record in records}
    for record in records:
        size_limit = _artifact_size_limit(record.kind)
        if record.size_bytes > size_limit:
            raise ArtifactError(
                f"artifact {record.name} exceeds its protocol byte limit",
                failure_path=f"artifacts.{record.name}.size_bytes",
            )
        try:
            payload = read_artifact_bytes(
                root, record.name, max_bytes=size_limit
            )
        except ArtifactError as exc:
            if "byte limit" in str(exc):
                raise ArtifactError(
                    f"artifact {record.name} exceeds its protocol byte limit",
                    failure_path=f"artifacts.{record.name}.size_bytes",
                ) from exc
            raise ArtifactError(
                f"artifact {record.name} is missing or not contained",
                failure_path=f"artifacts.{record.name}",
            ) from exc
        if hashlib.sha256(payload).hexdigest() != record.sha256:
            raise ArtifactError(
                f"artifact {record.name} digest does not match the manifest",
                failure_path=f"artifacts.{record.name}.sha256",
            )
        if len(payload) != record.size_bytes:
            raise ArtifactError(
                f"artifact {record.name} size does not match the manifest",
                failure_path=f"artifacts.{record.name}.size_bytes",
            )
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative != MANIFEST_NAME and relative not in listed:
            raise ArtifactError(
                f"unknown artifact {relative} is not listed in the manifest",
                failure_path=f"artifacts.{relative}",
            )
    return records


def read_artifact_bytes(
    root: Path, name: str, *, max_bytes: int = MAX_ARTIFACT_BYTES
) -> bytes:
    """Read one regular, non-symlink artifact contained by ``root``."""
    if max_bytes <= 0:
        raise ArtifactError("artifact byte limit must be positive")
    relative = _relative_name(name)
    try:
        root_resolved = root.resolve(strict=True)
    except OSError as exc:
        raise ArtifactError("artifact root is missing") from exc
    candidate = root
    for part in PurePosixPath(relative).parts:
        candidate /= part
        if candidate.is_symlink():
            raise ArtifactError(f"artifact {relative} uses a symlink")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root_resolved)
        if not resolved.is_file():
            raise ArtifactError(f"artifact {relative} is not a regular file")
        if resolved.stat().st_size > max_bytes:
            raise ArtifactError(f"artifact {relative} exceeds its protocol byte limit")
        with resolved.open("rb") as stream:
            payload = stream.read(max_bytes + 1)
        if len(payload) > max_bytes:
            raise ArtifactError(f"artifact {relative} exceeds its protocol byte limit")
        return payload
    except (OSError, ValueError, UnicodeError) as exc:
        raise ArtifactError(f"artifact {relative} is not a contained file") from exc


def _artifact_size_limit(kind: str) -> int:
    return (
        MAX_BOUNDED_ARTIFACT_BYTES
        if kind in BOUNDED_KINDS
        else MAX_ARTIFACT_BYTES
    )


def _record(entry: object, index: int) -> ArtifactRecord:
    if not isinstance(entry, dict):
        raise ArtifactError(
            "artifact manifest entry must be an object",
            failure_path=f"artifacts.manifest.artifacts[{index}]",
        )
    name = entry.get("name")
    base = _manifest_entry_path(name, index)
    if set(entry) != {
        "name",
        "kind",
        "sha256",
        "size_bytes",
        "truncated",
    }:
        raise ArtifactError(
            "artifact manifest entry has invalid fields",
            failure_path=f"{base}.fields",
        )
    kind = entry.get("kind")
    sha256 = entry.get("sha256")
    size = entry.get("size_bytes")
    truncated = entry.get("truncated")
    if not isinstance(name, str) or not isinstance(kind, str) or not isinstance(sha256, str):
        field = (
            "name"
            if not isinstance(name, str)
            else "kind"
            if not isinstance(kind, str)
            else "sha256"
        )
        raise ArtifactError(
            "artifact manifest entry is malformed",
            failure_path=f"{base}.{field}",
        )
    if kind not in ARTIFACT_KINDS:
        raise ArtifactError(
            f"artifact kind {kind!r} is not allowlisted",
            failure_path=f"{base}.kind",
        )
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise ArtifactError(
            "artifact digest must be a SHA-256 hexadecimal digest",
            failure_path=f"{base}.sha256",
        )
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ArtifactError(
            "artifact size must be a non-negative integer",
            failure_path=f"{base}.size_bytes",
        )
    if not isinstance(truncated, bool):
        raise ArtifactError(
            "artifact truncated flag must be a boolean",
            failure_path=f"{base}.truncated",
        )
    try:
        return ArtifactRecord(
            name=_relative_name(name),
            kind=kind,
            sha256=sha256,
            size_bytes=size,
            truncated=truncated,
        )
    except ArtifactError as exc:
        raise ArtifactError(str(exc), failure_path=f"{base}.name") from exc


def _manifest_entry_path(name: object, index: int) -> str:
    if isinstance(name, str):
        try:
            return f"artifacts.{_relative_name(name)}"
        except ArtifactError:
            pass
    return f"artifacts.manifest.artifacts[{index}]"


def _relative_name(name: str) -> str:
    if not isinstance(name, str) or name in {"", "."}:
        raise ArtifactError("artifact name must identify a file")
    try:
        os.fsencode(name)
    except UnicodeError as exc:
        raise ArtifactError("artifact name must be filesystem encodable") from exc
    windows = PureWindowsPath(name)
    posix = PurePosixPath(name)
    if (
        name.startswith(("/", "\\"))
        or windows.is_absolute()
        or windows.drive
        or "\\" in name
        or ".." in posix.parts
        or any(ord(character) < 32 or ord(character) == 127 for character in name)
    ):
        raise ArtifactError(f"artifact name {name!r} escapes the artifact store")
    return posix.as_posix()


def _reject_credential_name(relative: str) -> None:
    basename = PurePosixPath(relative).name
    lowered = basename.lower()
    if (
        lowered in _CREDENTIAL_NAMES
        or lowered.startswith(".env")
        or lowered.endswith(_CREDENTIAL_SUFFIXES)
    ):
        raise ArtifactError(f"artifact name {relative!r} names a credential file")


def _reject_secret_content(text: str) -> None:
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text):
            raise ArtifactError("artifact content matches a known secret pattern")


def _atomic_write(root: Path, relative: str, payload: bytes) -> None:
    """Atomically write below ``root`` without following parent or temp symlinks."""
    root.mkdir(parents=True, exist_ok=True)
    if root.is_symlink() or not root.is_dir():
        raise ArtifactError("artifact root must be a real directory")
    if os.name != "posix":  # pragma: no cover - exercised on Windows
        _portable_atomic_write(root, relative, payload)
        return
    directory_flags = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0)
    try:
        directory_fd = os.open(root, directory_flags)
    except OSError as exc:
        raise ArtifactError("artifact root must be a contained directory") from exc
    temporary_name: str | None = None
    try:
        parent_parts = PurePosixPath(relative).parent.parts
        for part in parent_parts:
            if part == ".":
                continue
            try:
                next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=directory_fd)
                    next_fd = os.open(part, directory_flags, dir_fd=directory_fd)
                except OSError as exc:
                    raise ArtifactError(
                        "artifact parent must be a contained directory"
                    ) from exc
            except OSError as exc:
                raise ArtifactError(
                    "artifact parent must not use a symlink"
                ) from exc
            os.close(directory_fd)
            directory_fd = next_fd
        filename = PurePosixPath(relative).name
        try:
            target_stat = os.stat(filename, dir_fd=directory_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            if stat.S_ISLNK(target_stat.st_mode):
                raise ArtifactError("artifact target must not be a symlink")
        temporary_name = f".{filename}.attest-{os.urandom(12).hex()}.tmp"
        temporary_flags = (
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
        )
        temporary_fd = os.open(
            temporary_name,
            temporary_flags,
            mode=0o600,
            dir_fd=directory_fd,
        )
        try:
            remaining = memoryview(payload)
            while remaining:
                written = os.write(temporary_fd, remaining)
                remaining = remaining[written:]
            os.fsync(temporary_fd)
        finally:
            os.close(temporary_fd)
        os.replace(
            temporary_name,
            filename,
            src_dir_fd=directory_fd,
            dst_dir_fd=directory_fd,
        )
        temporary_name = None
    except ArtifactError:
        raise
    except OSError as exc:
        raise ArtifactError("artifact write could not stay contained") from exc
    finally:
        if temporary_name is not None:
            with suppress(OSError):
                os.unlink(temporary_name, dir_fd=directory_fd)
        os.close(directory_fd)


def _portable_atomic_write(root: Path, relative: str, payload: bytes) -> None:
    """Best available no-follow/exclusive implementation without POSIX dir fds."""
    parent = root
    for part in PurePosixPath(relative).parent.parts:
        if part == ".":
            continue
        parent /= part
        if parent.is_symlink():
            raise ArtifactError("artifact parent must not use a symlink")
        parent.mkdir(exist_ok=True)
    target = parent / PurePosixPath(relative).name
    if target.is_symlink():
        raise ArtifactError("artifact target must not be a symlink")
    temporary = parent / f".{target.name}.attest-{os.urandom(12).hex()}.tmp"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        os.close(descriptor)
        with suppress(FileNotFoundError):
            temporary.unlink()


def canonical_json_bytes(value: object) -> bytes:
    """Encode one deterministic, ASCII-safe JSON record for hashing and envelopes."""
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def sha256_bytes(payload: bytes) -> str:
    """Return the lowercase SHA-256 digest of exact bytes."""

    if type(payload) is not bytes:
        raise TypeError("payload must be exact bytes")
    return hashlib.sha256(payload).hexdigest()


def validation_failure_signature(output: bytes) -> str | None:
    """Hash normalized failure-identifying lines from one stored or raw stdout."""
    text = output.decode("utf-8", errors="replace")
    if _is_dependency_failure(output):
        return None
    lines = [
        " ".join(line.split())
        for line in text.splitlines()
        if line.lstrip().startswith(("FAILED ", "ERROR "))
    ]
    if not lines:
        return None
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def validation_junit_counts(output: bytes) -> tuple[int, int, int, int] | None:
    """Return tests/failures/errors/skipped from raw XML or a bounded summary."""
    summary = _JUNIT_SUMMARY.match(output)
    if summary is not None:
        return tuple(int(value) for value in summary.groups()[:4])  # type: ignore[return-value]
    try:
        root = ElementTree.fromstring(output)
        suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))
        return (
            sum(int(suite.attrib.get("tests", "0")) for suite in suites),
            sum(int(suite.attrib.get("failures", "0")) for suite in suites),
            sum(int(suite.attrib.get("errors", "0")) for suite in suites),
            sum(int(suite.attrib.get("skipped", "0")) for suite in suites),
        )
    except (ElementTree.ParseError, ValueError):
        return None


def _validation_junit_summary(output: bytes) -> bytes | None:
    counts = validation_junit_counts(output)
    if counts is None:
        return None
    token = base64.urlsafe_b64encode(hashlib.sha256(output).digest()).rstrip(b"=")
    rendered_counts = b",".join(str(value).encode("ascii") for value in counts)
    return b"J attest:" + rendered_counts + b":" + token + b"\n"


def _is_dependency_failure(output: bytes) -> bool:
    """Recognize raw dependency failures and their bounded evidence marker."""
    lowered = output.decode("utf-8", errors="replace").casefold()
    return any(
        marker in lowered
        for marker in (
            "dependency attest",
            "modulenotfounderror",
            "importerror while importing",
            "not found:",
            "collected 0",
        )
    )
