"""Immutable, label-safe benchmark corpus manifest records."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

_ROLES = frozenset(("buggy", "fixed"))
_PROVENANCE_KINDS = frozenset(("upstream",))
_SPLITS = frozenset(("train", "validation", "test"))
_OPAQUE_ID_RE = re.compile(r"bug|clean|defect", re.IGNORECASE)
_HEX_RE = re.compile(r"[0-9a-f]+", re.IGNORECASE)


@dataclass(frozen=True)
class ChangedLocation:
    """A changed source range supplied by the preregistered corpus."""

    path: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class BenchmarkCase:
    """Product-visible metadata for one buggy or fixed member of a pair."""

    case_id: str
    pair_id: str
    source_id: str
    role: str
    provenance_kind: str
    source_license: str
    buggy_commit: str
    fixed_commit: str
    patch_hash: str
    test_hash: str
    changed_locations: tuple[ChangedLocation, ...]
    split: str


@dataclass(frozen=True)
class TruthDefect:
    """Hidden defect location for scoring a buggy case."""

    defect_id: str
    case_id: str
    file: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class Prediction:
    """One candidate joined to its final CI placement and differential evidence."""

    finding_id: str
    case_id: str
    file: str
    line: int
    placement: str
    action: str
    repro_status: str


@dataclass(frozen=True)
class RunRecord:
    """Predictions and delivery timing for one benchmark case execution."""

    run_id: str
    case_id: str
    repeat: int
    predictions: tuple[Prediction, ...]
    delivery_at_s: float | None
    deadline_s: float


@dataclass(frozen=True)
class BenchmarkManifest:
    """The versioned corpus metadata and its separately held hidden truth."""

    schema_version: str
    protocol_version: str
    corpus_commit: str
    cases: tuple[BenchmarkCase, ...]
    truth_defects: tuple[TruthDefect, ...]


def load_manifest(path: Path) -> BenchmarkManifest:
    """Load one canonical JSON manifest after rejecting malformed corpus metadata."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("manifest must be valid JSON") from exc
    document = _object(raw, "manifest")
    schema_version = _nonempty_string(document, "schema_version")
    protocol_version = _nonempty_string(document, "protocol_version")
    corpus_commit = _commit(_nonempty_string(document, "corpus_commit"), "corpus_commit")
    raw_cases = _list(document, "cases")
    raw_truth = _list(document, "truth_defects")
    cases = tuple(_case(_object(value, "case")) for value in raw_cases)
    truths = tuple(_truth(_object(value, "truth defect")) for value in raw_truth)
    _validate_pairs(cases)
    _validate_truth(cases, truths)
    return BenchmarkManifest(
        schema_version=schema_version,
        protocol_version=protocol_version,
        corpus_commit=corpus_commit,
        cases=cases,
        truth_defects=truths,
    )


def _case(raw: dict[str, Any]) -> BenchmarkCase:
    case_id = _opaque_id(_nonempty_string(raw, "case_id"), "case_id")
    pair_id = _opaque_id(_nonempty_string(raw, "pair_id"), "pair_id")
    source_id = _opaque_id(_nonempty_string(raw, "source_id"), "source_id")
    role = _enum(_nonempty_string(raw, "role"), _ROLES, "role")
    provenance_kind = _enum(
        _nonempty_string(raw, "provenance_kind"), _PROVENANCE_KINDS, "provenance_kind"
    )
    source_license = _nonempty_string(raw, "source_license")
    buggy_commit = _commit(_nonempty_string(raw, "buggy_commit"), "buggy_commit")
    fixed_commit = _commit(_nonempty_string(raw, "fixed_commit"), "fixed_commit")
    patch = _object(raw.get("patch"), "patch")
    tests = _object(raw.get("tests"), "tests")
    patch_hash = _hash(_nonempty_string(raw, "patch_hash"), "patch_hash")
    test_hash = _hash(_nonempty_string(raw, "test_hash"), "test_hash")
    if _canonical_hash(patch) != patch_hash:
        raise ValueError("patch_hash does not match patch")
    if _canonical_hash(tests) != test_hash:
        raise ValueError("test_hash does not match tests")
    locations = tuple(
        _location(_object(value, "changed location")) for value in _list(raw, "changed_locations")
    )
    if not locations:
        raise ValueError("changed_locations must not be empty")
    return BenchmarkCase(
        case_id=case_id,
        pair_id=pair_id,
        source_id=source_id,
        role=role,
        provenance_kind=provenance_kind,
        source_license=source_license,
        buggy_commit=buggy_commit,
        fixed_commit=fixed_commit,
        patch_hash=patch_hash,
        test_hash=test_hash,
        changed_locations=locations,
        split=_enum(_nonempty_string(raw, "split"), _SPLITS, "split"),
    )


def _truth(raw: dict[str, Any]) -> TruthDefect:
    return TruthDefect(
        defect_id=_nonempty_string(raw, "defect_id"),
        case_id=_opaque_id(_nonempty_string(raw, "case_id"), "case_id"),
        file=_path(_nonempty_string(raw, "file")),
        start_line=_line(raw.get("start_line"), "start_line"),
        end_line=_line(raw.get("end_line"), "end_line"),
    )


def _location(raw: dict[str, Any]) -> ChangedLocation:
    start_line = _line(raw.get("start_line"), "start_line")
    end_line = _line(raw.get("end_line"), "end_line")
    if start_line > end_line:
        raise ValueError("changed location start_line exceeds end_line")
    return ChangedLocation(
        path=_path(_nonempty_string(raw, "path")), start_line=start_line, end_line=end_line
    )


def _validate_pairs(cases: tuple[BenchmarkCase, ...]) -> None:
    case_ids = [case.case_id for case in cases]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate case_id")
    by_pair: dict[str, list[BenchmarkCase]] = {}
    for case in cases:
        by_pair.setdefault(case.pair_id, []).append(case)
    for pair_id, members in by_pair.items():
        if len(members) != 2 or {member.role for member in members} != _ROLES:
            raise ValueError(f"pair {pair_id} must contain one buggy and one fixed role")


def _validate_truth(cases: tuple[BenchmarkCase, ...], truths: tuple[TruthDefect, ...]) -> None:
    defect_ids = [truth.defect_id for truth in truths]
    if len(defect_ids) != len(set(defect_ids)):
        raise ValueError("duplicate defect_id")
    roles_by_case = {case.case_id: case.role for case in cases}
    for truth in truths:
        if roles_by_case.get(truth.case_id) != "buggy":
            raise ValueError("truth defect must belong to a buggy case")
        if truth.start_line > truth.end_line:
            raise ValueError("truth defect start_line exceeds end_line")


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _list(raw: dict[str, Any], key: str) -> list[object]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _nonempty_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _enum(value: str, allowed: frozenset[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"unknown {label}")
    return value


def _opaque_id(value: str, label: str) -> str:
    if _OPAQUE_ID_RE.search(value):
        raise ValueError(f"{label} must be opaque")
    return value


def _path(value: str) -> str:
    candidate = PurePosixPath(value)
    if value.startswith("/") or "\\" in value or ".." in candidate.parts:
        raise ValueError("path traversal is not allowed")
    if value in {"", "."}:
        raise ValueError("path must identify a file")
    return candidate.as_posix()


def _line(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _commit(value: str, label: str) -> str:
    if len(value) not in (40, 64) or _HEX_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a full hexadecimal commit")
    return value


def _hash(value: str, label: str) -> str:
    if len(value) != 64 or _HEX_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a SHA-256 digest")
    return value
