"""Immutable, label-safe benchmark corpus manifest records."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast

_ROLES = frozenset(("historical_bug_replay", "developer_fix_control"))
_PROVENANCE_KINDS = frozenset(("historical_fix", "bug_introducing_commit"))
_SPLITS = frozenset(("train", "validation", "test"))
_NORMALIZATIONS = frozenset(("bytes", "normalized_text", "unified_diff"))
_EXPOSED_ID_PATTERNS = {
    "case_id": re.compile(r"case-[0-9a-f]{12}\Z"),
    "pair_id": re.compile(r"pair-[0-9a-f]{12}\Z"),
    "source_id": re.compile(r"source-[0-9a-f]{12}\Z"),
}
_HEX_RE = re.compile(r"[0-9a-f]+", re.IGNORECASE)
MANIFEST_SCHEMA_VERSION = "1"
MANIFEST_PROTOCOL_VERSION = "1"


class Placement(StrEnum):
    """Final ci_final placement, independent from the gate action."""

    INLINE = "inline"
    OVERFLOW = "overflow"
    DRAWER = "drawer"
    DISCARD = "discard"


def is_scored_placement(placement: Placement) -> bool:
    """Return whether a final placement was visible to the pull-request author."""
    return placement in (Placement.INLINE, Placement.OVERFLOW)


@dataclass(frozen=True)
class ChangedLocation:
    """A changed source range supplied by the preregistered corpus."""

    path: str
    start_line: int
    end_line: int
    side: str = "old"


@dataclass(frozen=True)
class PatchDescriptor:
    """A hash-addressed external patch artifact, without embedding its contents."""

    relative_path: str
    sha256: str
    normalization: str


@dataclass(frozen=True)
class TestDescriptor:
    """A hash-addressed external regression-test artifact, without embedding its contents."""

    __test__ = False

    relative_path: str
    sha256: str
    normalization: str


@dataclass(frozen=True)
class CorpusProvenance:
    """Adapter-neutral origin and licensing status for corpus metadata."""

    kind: str
    source_url: str
    license_status: str
    license: str | None
    license_file: str | None
    license_sha256: str | None


@dataclass(frozen=True)
class BenchmarkSource:
    """One upstream project and its commit-addressed local license evidence."""

    source_id: str
    project_url: str
    source_license: str
    license_file: str
    license_sha256: str
    license_commits_verified: tuple[str, ...]


@dataclass(frozen=True)
class RuntimeDescriptor:
    """Generic prepared checkout and argv for one opaque benchmark case."""

    case_id: str
    cwd: str
    tool: str
    args: tuple[str, ...]
    role: str | None
    python_version: str | None


@dataclass(frozen=True)
class CorpusExclusion:
    """An import-time candidate exclusion retained for denominator auditing."""

    upstream_case: str
    reason: str


@dataclass(frozen=True)
class SelectionMetadata:
    """Exact deterministic pair-selection design carried by imported v1 corpora."""

    seed: int
    requested_pair_limit: int
    eligible_pairs: int
    selected_pairs: int


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
    patch: PatchDescriptor
    tests: TestDescriptor
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
    """One candidate joined to its final CI placement and differential evidence.

    ``evidence_class`` records what the head/base pair actually showed (D-022).
    It is deliberately separate from ``repro_status``: only a reproduced
    regression can ever match truth, but a new-code candidate is unpriced
    signal rather than a failure, and a report that lumps the two together
    would misrepresent the tool.
    """

    finding_id: str
    case_id: str
    file: str
    line: int
    placement: Placement
    action: str
    repro_status: str
    evidence_class: str = "indeterminate"

    @classmethod
    def from_joined_ci_final(
        cls,
        candidate_row: Mapping[str, object],
        ci_final_row: Mapping[str, object],
        *,
        case_id: str,
        repro_status: str,
        evidence_class: str = "indeterminate",
    ) -> Prediction:
        """Join persisted candidate and ci_final rows with independent benchmark context."""
        finding_id = _mapping_string(candidate_row, "finding_id")
        if finding_id != _mapping_string(ci_final_row, "finding_id"):
            raise ValueError("candidate and ci_final finding_id must match")
        try:
            placement = Placement(_mapping_string(ci_final_row, "placement"))
        except ValueError as exc:
            raise ValueError("unknown ci_final placement") from exc
        line = candidate_row.get("line")
        if not isinstance(line, int) or isinstance(line, bool) or line < 1:
            raise ValueError("candidate line must be a positive integer")
        return cls(
            finding_id=finding_id,
            case_id=_opaque_id(_string_value(case_id, "case_id"), "case_id"),
            file=_mapping_string(candidate_row, "file"),
            line=line,
            placement=placement,
            action=_mapping_string(ci_final_row, "action"),
            repro_status=_string_value(repro_status, "repro_status"),
            evidence_class=_string_value(evidence_class, "evidence_class"),
        )


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
    sources: tuple[BenchmarkSource, ...] = ()
    runtime: tuple[RuntimeDescriptor, ...] = ()
    exclusions: tuple[CorpusExclusion, ...] = ()
    provenance: CorpusProvenance | None = None
    selection: SelectionMetadata | None = None
    _source_bytes: bytes | None = field(default=None, repr=False, compare=False)


def verify_descriptor_bytes(
    descriptor: PatchDescriptor | TestDescriptor, contents: bytes
) -> bool:
    """Compare bytes supplied by a later corpus validator to a typed descriptor."""
    if descriptor.normalization == "normalized_text":
        contents = contents.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    elif descriptor.normalization == "unified_diff":
        try:
            contents = normalize_unified_diff_bytes(contents)
        except ValueError:
            return False
    return hashlib.sha256(contents).hexdigest() == descriptor.sha256


def normalize_unified_diff_bytes(contents: bytes) -> bytes:
    """Canonicalize textual git diff bytes while retaining direction and hunks."""
    try:
        text = contents.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("unified diff must be UTF-8 text") from exc
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line for line in text.splitlines() if not line.startswith("index ")]
    return ("\n".join(lines) + "\n").encode()


def load_manifest(path: Path) -> BenchmarkManifest:
    """Load one canonical JSON manifest after rejecting malformed corpus metadata."""
    try:
        source_bytes = path.read_bytes()
        raw = _parse_json_document(source_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("manifest must be valid JSON") from exc
    return _load_manifest_document(raw, source_bytes=source_bytes)


def require_manifest_binding(
    manifest: BenchmarkManifest, manifest_sha256: str
) -> BenchmarkManifest:
    """Return the canonical manifest parsed from the exact authenticated bytes."""
    if type(manifest) is not BenchmarkManifest or manifest._source_bytes is None:
        raise ValueError("manifest bytes binding is unavailable")
    if type(manifest_sha256) is not str or re.fullmatch(
        r"[0-9a-f]{64}", manifest_sha256
    ) is None:
        raise ValueError("manifest digest must be an exact lowercase SHA-256 string")
    if not _manifest_tree_is_exact(manifest):
        raise ValueError("typed manifest is not an exact canonical manifest tree")
    if hashlib.sha256(manifest._source_bytes).hexdigest() != manifest_sha256:
        raise ValueError("manifest digest does not match its bound bytes")
    try:
        bound = _load_manifest_document(
            _parse_json_document(manifest._source_bytes),
            source_bytes=manifest._source_bytes,
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("manifest bytes binding is invalid") from exc
    if manifest != bound:
        raise ValueError("typed manifest does not match its bound bytes")
    return bound


def manifest_binding_bytes(manifest: BenchmarkManifest) -> bytes:
    """Return the single exact byte snapshot from which a manifest was parsed."""
    if type(manifest) is not BenchmarkManifest or manifest._source_bytes is None:
        raise ValueError("manifest bytes binding is unavailable")
    payload = manifest._source_bytes
    require_manifest_binding(manifest, hashlib.sha256(payload).hexdigest())
    return payload


_MANIFEST_RECORD_TYPES = frozenset(
    {
        BenchmarkManifest,
        BenchmarkCase,
        BenchmarkSource,
        ChangedLocation,
        CorpusExclusion,
        CorpusProvenance,
        PatchDescriptor,
        RuntimeDescriptor,
        SelectionMetadata,
        TestDescriptor,
        TruthDefect,
    }
)


def _manifest_tree_is_exact(value: object) -> bool:
    """Reject Python subclasses before any equality-based manifest join."""
    value_type = type(value)
    if value is None or value_type in {str, int, bytes}:
        return True
    if value_type is tuple:
        return all(
            _manifest_tree_is_exact(item)
            for item in cast(tuple[object, ...], value)
        )
    if value_type in _MANIFEST_RECORD_TYPES:
        record = cast(Any, value)
        return all(
            _manifest_tree_is_exact(getattr(record, field_name))
            for field_name in record.__dataclass_fields__
        )
    return False


def _load_manifest_document(raw: object, *, source_bytes: bytes) -> BenchmarkManifest:
    document = _object(raw, "manifest")
    _exact_fields(
        document,
        "manifest",
        required={
            "schema_version",
            "protocol_version",
            "corpus_commit",
            "cases",
            "truth_defects",
        },
        optional={"sources", "runtime", "exclusions", "provenance", "selection"},
    )
    schema_version = _nonempty_string(document, "schema_version")
    protocol_version = _nonempty_string(document, "protocol_version")
    if schema_version != MANIFEST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported manifest schema_version {schema_version!r}; supported version "
            f"is {MANIFEST_SCHEMA_VERSION}"
        )
    if protocol_version != MANIFEST_PROTOCOL_VERSION:
        raise ValueError(
            f"unsupported manifest protocol_version {protocol_version!r}; supported version "
            f"is {MANIFEST_PROTOCOL_VERSION}"
        )
    corpus_commit = _commit(_nonempty_string(document, "corpus_commit"), "corpus_commit")
    raw_cases = _list(document, "cases")
    raw_truth = _list(document, "truth_defects")
    cases = tuple(_case(_object(value, "case")) for value in raw_cases)
    truths = tuple(_truth(_object(value, "truth defect")) for value in raw_truth)
    _validate_pairs(cases)
    _validate_truth(cases, truths)
    sources = tuple(
        _source(_object(value, "source")) for value in _optional_list(document, "sources")
    )
    runtime = tuple(
        _runtime(_object(value, "runtime")) for value in _optional_list(document, "runtime")
    )
    exclusions = tuple(
        _exclusion(_object(value, "exclusion"))
        for value in _optional_list(document, "exclusions")
    )
    provenance_raw = document.get("provenance")
    provenance = (
        _provenance(_object(provenance_raw, "provenance"))
        if provenance_raw is not None
        else None
    )
    selection_raw = document.get("selection")
    selection = (
        _selection(_object(selection_raw, "selection"))
        if selection_raw is not None
        else None
    )
    _validate_extensions(cases, sources, runtime)
    if selection is not None:
        pair_count = len({case.pair_id for case in cases})
        if selection.selected_pairs != pair_count:
            raise ValueError("selection selected_pairs must match manifest pairs")
        if selection.selected_pairs > selection.eligible_pairs:
            raise ValueError("selection selected_pairs exceeds eligible_pairs")
        if selection.selected_pairs > selection.requested_pair_limit:
            raise ValueError("selection selected_pairs exceeds requested_pair_limit")
    return BenchmarkManifest(
        schema_version=schema_version,
        protocol_version=protocol_version,
        corpus_commit=corpus_commit,
        cases=cases,
        truth_defects=truths,
        sources=sources,
        runtime=runtime,
        exclusions=exclusions,
        provenance=provenance,
        selection=selection,
        _source_bytes=source_bytes,
    )


def _provenance(raw: dict[str, Any]) -> CorpusProvenance:
    _exact_fields(
        raw,
        "provenance",
        required={"kind", "source_url", "license_status"},
        optional={"license", "license_file", "license_sha256"},
    )
    license_status = _enum(
        _nonempty_string(raw, "license_status"),
        frozenset(("DETECTED", "UNSPECIFIED")),
        "license_status",
    )
    license_value = _optional_string(raw.get("license"), "license")
    license_file_value = _optional_string(raw.get("license_file"), "license_file")
    license_hash_value = _optional_string(raw.get("license_sha256"), "license_sha256")
    if license_status == "DETECTED":
        if license_value is None or license_file_value is None or license_hash_value is None:
            raise ValueError("detected provenance license requires complete evidence")
        license_file_value = _path(license_file_value)
        license_hash_value = _hash(license_hash_value, "license_sha256")
    elif any(
        value is not None for value in (license_value, license_file_value, license_hash_value)
    ):
        raise ValueError("unspecified provenance license must not claim evidence")
    return CorpusProvenance(
        kind=_nonempty_string(raw, "kind"),
        source_url=_nonempty_string(raw, "source_url"),
        license_status=license_status,
        license=license_value,
        license_file=license_file_value,
        license_sha256=license_hash_value,
    )


def _source(raw: dict[str, Any]) -> BenchmarkSource:
    _exact_fields(
        raw,
        "source",
        required={
            "source_id",
            "project_url",
            "source_license",
            "license_file",
            "license_sha256",
            "license_commits_verified",
        },
    )
    commits = tuple(
        _commit(_string_value(value, "license commit"), "license commit")
        for value in _list(raw, "license_commits_verified")
    )
    if not commits:
        raise ValueError("license_commits_verified must not be empty")
    return BenchmarkSource(
        source_id=_opaque_id(_nonempty_string(raw, "source_id"), "source_id"),
        project_url=_nonempty_string(raw, "project_url"),
        source_license=_nonempty_string(raw, "source_license"),
        license_file=_path(_nonempty_string(raw, "license_file")),
        license_sha256=_hash(_nonempty_string(raw, "license_sha256"), "license_sha256"),
        license_commits_verified=commits,
    )


def _runtime(raw: dict[str, Any]) -> RuntimeDescriptor:
    _exact_fields(
        raw,
        "runtime",
        required={"case_id", "cwd", "command"},
        optional={"role", "python_version"},
    )
    command = _object(raw.get("command"), "runtime command")
    _exact_fields(command, "runtime command", required={"tool", "args"})
    tool = _enum(
        _nonempty_string(command, "tool"), frozenset(("python", "tox")), "runtime tool"
    )
    args = tuple(_string_value(value, "command arg") for value in _list(command, "args"))
    role = _optional_string(raw.get("role"), "role")
    if role is not None:
        role = _enum(role, _ROLES, "role")
    return RuntimeDescriptor(
        case_id=_opaque_id(_nonempty_string(raw, "case_id"), "case_id"),
        cwd=_path(_nonempty_string(raw, "cwd")),
        tool=tool,
        args=args,
        role=role,
        python_version=_optional_string(raw.get("python_version"), "python_version"),
    )


def _exclusion(raw: dict[str, Any]) -> CorpusExclusion:
    _exact_fields(raw, "exclusion", required={"upstream_case", "reason"})
    return CorpusExclusion(
        upstream_case=_nonempty_string(raw, "upstream_case"),
        reason=_nonempty_string(raw, "reason"),
    )


def _selection(raw: dict[str, Any]) -> SelectionMetadata:
    _exact_fields(
        raw,
        "selection",
        required={
            "seed",
            "requested_pair_limit",
            "eligible_pairs",
            "selected_pairs",
        },
    )
    values: dict[str, int] = {}
    for field_name in (
        "seed",
        "requested_pair_limit",
        "eligible_pairs",
        "selected_pairs",
    ):
        value = raw.get(field_name)
        if type(value) is not int or value < 0:
            raise ValueError(f"selection {field_name} must be a non-negative integer")
        values[field_name] = value
    return SelectionMetadata(**values)


def _validate_extensions(
    cases: tuple[BenchmarkCase, ...],
    sources: tuple[BenchmarkSource, ...],
    runtime: tuple[RuntimeDescriptor, ...],
) -> None:
    case_ids = {case.case_id for case in cases}
    if sources:
        source_ids = [source.source_id for source in sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("duplicate source_id")
        if set(source_ids) != {case.source_id for case in cases}:
            raise ValueError("sources must exactly cover manifest cases")
    if runtime:
        runtime_ids = [row.case_id for row in runtime]
        if len(runtime_ids) != len(set(runtime_ids)):
            raise ValueError("duplicate runtime case_id")
        if set(runtime_ids) != case_ids:
            raise ValueError("runtime must exactly cover manifest cases")
        roles = {case.case_id: case.role for case in cases}
        if any(row.role is not None and row.role != roles[row.case_id] for row in runtime):
            raise ValueError("runtime role must match case role")
        cases_by_id = {case.case_id: case for case in cases}
        for row in runtime:
            case = cases_by_id[row.case_id]
            role_dir = "replay" if case.role == "historical_bug_replay" else "control"
            expected_cwd = f"{case.source_id}/{case.pair_id}/{role_dir}"
            if row.cwd != expected_cwd:
                raise ValueError("runtime cwd must identify its source, pair, and role")


def _case(raw: dict[str, Any]) -> BenchmarkCase:
    _exact_fields(
        raw,
        "case",
        required={
            "case_id",
            "pair_id",
            "source_id",
            "role",
            "provenance_kind",
            "source_license",
            "buggy_commit",
            "fixed_commit",
            "patch",
            "tests",
            "changed_locations",
            "split",
        },
    )
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
    patch = _patch_descriptor(_object(raw.get("patch"), "patch"))
    tests = _test_descriptor(_object(raw.get("tests"), "tests"))
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
        patch=patch,
        tests=tests,
        changed_locations=locations,
        split=_enum(_nonempty_string(raw, "split"), _SPLITS, "split"),
    )


def _truth(raw: dict[str, Any]) -> TruthDefect:
    _exact_fields(
        raw,
        "truth defect",
        required={"defect_id", "case_id", "file", "start_line", "end_line"},
    )
    return TruthDefect(
        defect_id=_nonempty_string(raw, "defect_id"),
        case_id=_opaque_id(_nonempty_string(raw, "case_id"), "case_id"),
        file=_path(_nonempty_string(raw, "file")),
        start_line=_line(raw.get("start_line"), "start_line"),
        end_line=_line(raw.get("end_line"), "end_line"),
    )


def _location(raw: dict[str, Any]) -> ChangedLocation:
    _exact_fields(
        raw,
        "changed location",
        required={"path", "start_line", "end_line"},
        optional={"side"},
    )
    start_line = _line(raw.get("start_line"), "start_line")
    end_line = _line(raw.get("end_line"), "end_line")
    if start_line > end_line:
        raise ValueError("changed location start_line exceeds end_line")
    return ChangedLocation(
        path=_path(_nonempty_string(raw, "path")),
        start_line=start_line,
        end_line=end_line,
        side=_enum(raw.get("side", "old"), frozenset(("old", "new")), "changed side"),
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
            raise ValueError(
                f"pair {pair_id} must contain historical_bug_replay and developer_fix_control"
            )
        first = members[0]
        for member in members[1:]:
            if (
                member.source_id,
                member.provenance_kind,
                member.source_license,
                member.buggy_commit,
                member.fixed_commit,
                member.patch,
                member.tests,
                member.split,
            ) != (
                first.source_id,
                first.provenance_kind,
                first.source_license,
                first.buggy_commit,
                first.fixed_commit,
                first.patch,
                first.tests,
                first.split,
            ):
                raise ValueError(f"pair {pair_id} members must share corpus identity")


def _validate_truth(cases: tuple[BenchmarkCase, ...], truths: tuple[TruthDefect, ...]) -> None:
    defect_ids = [truth.defect_id for truth in truths]
    if len(defect_ids) != len(set(defect_ids)):
        raise ValueError("duplicate defect_id")
    roles_by_case = {case.case_id: case.role for case in cases}
    truth_case_ids = {truth.case_id for truth in truths}
    for case in cases:
        if case.role == "historical_bug_replay" and case.case_id not in truth_case_ids:
            raise ValueError("historical_bug_replay case must contain at least one truth defect")
    for truth in truths:
        if roles_by_case.get(truth.case_id) != "historical_bug_replay":
            raise ValueError("truth defect must belong to a historical_bug_replay case")
        if truth.start_line > truth.end_line:
            raise ValueError("truth defect start_line exceeds end_line")


def _patch_descriptor(raw: dict[str, Any]) -> PatchDescriptor:
    relative_path, sha256, normalization = _descriptor_parts(raw, "patch")
    return PatchDescriptor(relative_path, sha256, normalization)


def _test_descriptor(raw: dict[str, Any]) -> TestDescriptor:
    relative_path, sha256, normalization = _descriptor_parts(raw, "tests")
    return TestDescriptor(relative_path, sha256, normalization)


def _descriptor_parts(raw: dict[str, Any], label: str) -> tuple[str, str, str]:
    _exact_fields(
        raw,
        label,
        required={"relative_path", "sha256", "normalization"},
    )
    relative_path = _path(_nonempty_string(raw, "relative_path"))
    sha256 = _hash(_nonempty_string(raw, "sha256"), f"{label}.sha256")
    normalization = _enum(_nonempty_string(raw, "normalization"), _NORMALIZATIONS, "normalization")
    return relative_path, sha256, normalization


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _parse_json_document(payload: bytes) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON field {key!r}")
            result[key] = value
        return result

    return json.loads(payload, object_pairs_hook=reject_duplicates)


def _exact_fields(
    raw: Mapping[str, object],
    label: str,
    *,
    required: set[str],
    optional: set[str] | None = None,
) -> None:
    allowed = required | (optional or set())
    missing = required - set(raw)
    unknown = set(raw) - allowed
    if missing or unknown:
        details = []
        if missing:
            details.append("missing " + ", ".join(sorted(missing)))
        if unknown:
            details.append("unknown " + ", ".join(sorted(unknown)))
        raise ValueError(f"{label} fields are invalid: {'; '.join(details)}")


def _list(raw: dict[str, Any], key: str) -> list[object]:
    value = raw.get(key)
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _optional_list(raw: dict[str, Any], key: str) -> list[object]:
    value = raw.get(key, [])
    if not isinstance(value, list):
        raise ValueError(f"{key} must be a list")
    return value


def _nonempty_string(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _mapping_string(raw: Mapping[str, object], key: str) -> str:
    return _string_value(raw.get(key), key)


def _string_value(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _optional_string(value: object, label: str) -> str | None:
    if value is None:
        return None
    return _string_value(value, label)


def _enum(value: str, allowed: frozenset[str], label: str) -> str:
    if value not in allowed:
        raise ValueError(f"unknown {label}")
    return value


def _opaque_id(value: str, label: str) -> str:
    if _EXPOSED_ID_PATTERNS[label].fullmatch(value) is None:
        raise ValueError(f"{label} must be opaque fixed-prefix hexadecimal")
    return value


def _path(value: str) -> str:
    candidate = PurePosixPath(value)
    windows = PureWindowsPath(value)
    if (
        value.startswith("/")
        or value.startswith("\\\\")
        or windows.is_absolute()
        or windows.drive
        or "\\" in value
        or ".." in candidate.parts
    ):
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
