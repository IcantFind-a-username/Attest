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

import hashlib
import json
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

ARTIFACT_SCHEMA_VERSION = "1"

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
    }
)

#: Kinds whose content is untrusted tool output: bounded by truncation to a
#: tail rather than refused, because a truncated tail is still evidence.
BOUNDED_KINDS = frozenset({"repro_output", "junit"})

MANIFEST_NAME = "artifacts.json"
REDACTION = "[REDACTED]"

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


@dataclass(frozen=True)
class ArtifactRecord:
    """One stored artifact and the digest that binds its exact bytes."""

    name: str
    kind: str
    sha256: str
    size_bytes: int
    truncated: bool = False

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
        max_bounded_bytes: int = 16_384,
        max_artifact_bytes: int = 1_048_576,
    ) -> None:
        if max_bounded_bytes <= 0 or max_artifact_bytes <= 0:
            raise ArtifactError("artifact size limits must be positive")
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
        if kind not in ARTIFACT_KINDS:
            raise ArtifactError(f"artifact kind {kind!r} is not allowlisted")
        relative = _relative_name(name)
        _reject_credential_name(relative)
        text, truncated = self._render(kind, payload)
        _reject_secret_content(text)
        encoded = text.encode("utf-8")
        if len(encoded) > self._max_artifact_bytes:
            raise ArtifactError(
                f"artifact {relative} exceeds the {self._max_artifact_bytes}-byte limit"
            )
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(target, encoded)
        record = ArtifactRecord(
            name=relative,
            kind=kind,
            sha256=hashlib.sha256(encoded).hexdigest(),
            size_bytes=len(encoded),
            truncated=truncated,
        )
        self._records = [existing for existing in self._records if existing.name != relative]
        self._records.append(record)
        return record

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
        path = self.root / MANIFEST_NAME
        _atomic_write(path, _canonical_json(document).encode("utf-8"))
        self._finalized = True
        return path

    def _render(self, kind: str, payload: object) -> tuple[str, bool]:
        redacted = redact(payload, self._secrets)
        if isinstance(redacted, str):
            text = redacted
        elif isinstance(redacted, bytes):
            text = redacted.decode("utf-8", errors="replace")
        else:
            text = _canonical_json(redacted)
        if kind not in BOUNDED_KINDS:
            return text, False
        encoded = text.encode("utf-8")
        if len(encoded) <= self._max_bounded_bytes:
            return text, False
        return encoded[-self._max_bounded_bytes :].decode("utf-8", errors="ignore"), True


def verify_artifacts(root: Path) -> tuple[ArtifactRecord, ...]:
    """Re-hash every listed artifact and refuse unknown files in the store."""
    manifest_path = root / MANIFEST_NAME
    try:
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactError("artifact manifest must be valid JSON") from exc
    if not isinstance(document, dict) or document.get("schema_version") != (
        ARTIFACT_SCHEMA_VERSION
    ):
        raise ArtifactError("unsupported artifact manifest schema")
    entries = document.get("artifacts")
    if not isinstance(entries, list):
        raise ArtifactError("artifact manifest must list artifacts")
    records = tuple(_record(entry) for entry in entries)
    listed = {record.name for record in records}
    for record in records:
        path = root / record.name
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise ArtifactError(f"artifact {record.name} is missing") from exc
        if hashlib.sha256(payload).hexdigest() != record.sha256:
            raise ArtifactError(f"artifact {record.name} digest does not match the manifest")
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative != MANIFEST_NAME and relative not in listed:
            raise ArtifactError(f"unknown artifact {relative} is not listed in the manifest")
    return records


def _record(entry: object) -> ArtifactRecord:
    if not isinstance(entry, dict):
        raise ArtifactError("artifact manifest entry must be an object")
    name = entry.get("name")
    kind = entry.get("kind")
    sha256 = entry.get("sha256")
    size = entry.get("size_bytes")
    if not isinstance(name, str) or not isinstance(kind, str) or not isinstance(sha256, str):
        raise ArtifactError("artifact manifest entry is malformed")
    if kind not in ARTIFACT_KINDS:
        raise ArtifactError(f"artifact kind {kind!r} is not allowlisted")
    if re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
        raise ArtifactError("artifact digest must be a SHA-256 hexadecimal digest")
    if not isinstance(size, int) or isinstance(size, bool) or size < 0:
        raise ArtifactError("artifact size must be a non-negative integer")
    return ArtifactRecord(
        name=_relative_name(name),
        kind=kind,
        sha256=sha256,
        size_bytes=size,
        truncated=bool(entry.get("truncated", False)),
    )


def _relative_name(name: str) -> str:
    if not isinstance(name, str) or name in {"", "."}:
        raise ArtifactError("artifact name must identify a file")
    windows = PureWindowsPath(name)
    posix = PurePosixPath(name)
    if (
        name.startswith(("/", "\\"))
        or windows.is_absolute()
        or windows.drive
        or "\\" in name
        or ".." in posix.parts
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


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(payload)
    os.replace(temporary, path)


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def bounded_records(records: Iterable[ArtifactRecord]) -> tuple[ArtifactRecord, ...]:
    """Artifacts whose content was truncated to its bound."""
    return tuple(record for record in records if record.truncated)
