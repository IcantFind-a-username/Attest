"""Manifest validation protects the preregistered benchmark corpus."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from attest.benchmark.schema import (
    PatchDescriptor,
    TestDescriptor,
    load_manifest,
    verify_descriptor_bytes,
)


def _literal_manifest() -> dict[str, object]:
    return {
        "schema_version": "1",
        "protocol_version": "1",
        "corpus_commit": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
        "cases": [
            {
                "case_id": "case_001",
                "pair_id": "pair_001",
                "source_id": "source_001",
                "role": "historical_bug_replay",
                "provenance_kind": "historical_fix",
                "source_license": "Apache-2.0",
                "buggy_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "fixed_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "patch": {
                    "relative_path": "patches/app.patch",
                    "sha256": "af4749a1580b936481c1c087bc72d5031e256c38e266d0ee8d4f2707d3aa0e58",
                    "normalization": "bytes",
                },
                "tests": {
                    "relative_path": "tests/test_app.py",
                    "sha256": "52ece453f7dd506d2a37a0f2e36732132f489cd662a1b92fad16545a56a3c3bd",
                    "normalization": "normalized_text",
                },
                "changed_locations": [
                    {"path": "src/app.py", "start_line": 10, "end_line": 12}
                ],
                "split": "test",
            },
            {
                "case_id": "case_002",
                "pair_id": "pair_001",
                "source_id": "source_001",
                "role": "developer_fix_control",
                "provenance_kind": "historical_fix",
                "source_license": "Apache-2.0",
                "buggy_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "fixed_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "patch": {
                    "relative_path": "patches/app.patch",
                    "sha256": "af4749a1580b936481c1c087bc72d5031e256c38e266d0ee8d4f2707d3aa0e58",
                    "normalization": "bytes",
                },
                "tests": {
                    "relative_path": "tests/test_app.py",
                    "sha256": "52ece453f7dd506d2a37a0f2e36732132f489cd662a1b92fad16545a56a3c3bd",
                    "normalization": "normalized_text",
                },
                "changed_locations": [
                    {"path": "src/app.py", "start_line": 10, "end_line": 12}
                ],
                "split": "test",
            },
        ],
        "truth_defects": [
            {
                "defect_id": "truth_001",
                "case_id": "case_001",
                "file": "src/app.py",
                "start_line": 11,
                "end_line": 11,
            }
        ],
    }


def _write_manifest(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_load_manifest_preserves_product_metadata_and_keeps_truth_separate(tmp_path: Path) -> None:
    """Dropping a required provenance or truth field must invalidate the corpus."""
    manifest = load_manifest(_write_manifest(tmp_path, _literal_manifest()))

    assert manifest.schema_version == "1"
    assert manifest.cases[0].case_id == "case_001"
    assert manifest.cases[0].changed_locations[0].start_line == 10
    assert manifest.cases[0].patch == PatchDescriptor(
        relative_path="patches/app.patch",
        sha256="af4749a1580b936481c1c087bc72d5031e256c38e266d0ee8d4f2707d3aa0e58",
        normalization="bytes",
    )
    assert manifest.cases[0].tests == TestDescriptor(
        relative_path="tests/test_app.py",
        sha256="52ece453f7dd506d2a37a0f2e36732132f489cd662a1b92fad16545a56a3c3bd",
        normalization="normalized_text",
    )
    assert manifest.truth_defects[0].defect_id == "truth_001"
    assert not hasattr(manifest.cases[0], "truth_defects")
    with pytest.raises(AttributeError):
        manifest.cases[0].case_id = "case_003"  # type: ignore[misc]


def test_load_manifest_keeps_hidden_defect_identifiers_out_of_opaque_metadata_rules(
    tmp_path: Path,
) -> None:
    """Applying the product-facing opacity rule to hidden truth would reject valid labels."""
    document = _literal_manifest()
    document["truth_defects"][0]["defect_id"] = "defect_001"  # type: ignore[index]

    manifest = load_manifest(_write_manifest(tmp_path, document))

    assert manifest.truth_defects[0].defect_id == "defect_001"


def test_load_manifest_requires_truth_for_each_historical_bug_replay(tmp_path: Path) -> None:
    """A replay without truth cannot be scored as a positive benchmark case."""
    document = _literal_manifest()
    document["truth_defects"] = []

    with pytest.raises(ValueError, match="historical_bug_replay"):
        load_manifest(_write_manifest(tmp_path, document))


def test_descriptor_bytes_verify_against_external_fixture_content(tmp_path: Path) -> None:
    """A descriptor must retain the expected external bytes without self-hashing JSON."""
    manifest = load_manifest(_write_manifest(tmp_path, _literal_manifest()))

    assert verify_descriptor_bytes(
        manifest.cases[0].patch, b"--- a/src/app.py\n+++ b/src/app.py\n"
    )
    assert not verify_descriptor_bytes(
        manifest.cases[0].patch, b"--- a/src/app.py\n+++ b/src/tampered.py\n"
    )


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda d: d.pop("schema_version"), "schema_version"),
        (lambda d: d.pop("protocol_version"), "protocol_version"),
        (lambda d: d["cases"][0].update({"role": "unknown"}), "role"),  # type: ignore[index]
        (lambda d: d["cases"][0].update({"provenance_kind": "unknown"}), "provenance_kind"),  # type: ignore[index]
        (lambda d: d["cases"][0].update({"split": "unknown"}), "split"),  # type: ignore[index]
        (lambda d: d["cases"][0].update({"case_id": "case_bug_001"}), "opaque"),  # type: ignore[index]
        (lambda d: d["cases"][0].update({"source_id": "source_clean_001"}), "opaque"),  # type: ignore[index]
        (lambda d: d["cases"][0]["changed_locations"][0].update({"path": "../app.py"}), "path"),  # type: ignore[index]
        (lambda d: d["cases"][0]["changed_locations"][0].update({"path": "/app.py"}), "path"),  # type: ignore[index]
        (lambda d: d["cases"][0]["changed_locations"][0].update({"path": "C:/app.py"}), "path"),  # type: ignore[index]
        (
            lambda d: d["cases"][0]["changed_locations"][0].update({"path": "//server/app.py"}),
            "path",
        ),  # type: ignore[index]
        (
            lambda d: d["cases"][0]["changed_locations"][0].update({"path": "\\\\server\\app.py"}),
            "path",
        ),  # type: ignore[index]
        (lambda d: d["cases"][0].update({"patch": {"files": ["src/app.py"]}}), "relative_path"),  # type: ignore[index]
        (lambda d: d["cases"].append(copy.deepcopy(d["cases"][0])), "duplicate"),  # type: ignore[index]
        (lambda d: d["cases"].pop(), "pair"),  # type: ignore[index]
    ],
)
def test_load_manifest_rejects_invalid_or_leaky_corpus_metadata(
    tmp_path: Path, mutation: object, message: str
) -> None:
    """A validation hole could leak labels or detach a case from its paired truth."""
    document = _literal_manifest()
    mutation(document)  # type: ignore[operator]

    with pytest.raises(ValueError, match=message):
        load_manifest(_write_manifest(tmp_path, document))


def test_load_manifest_accepts_future_bug_introducing_commit_provenance(tmp_path: Path) -> None:
    """Rejecting the preregistered future provenance kind would block later corpus imports."""
    document = _literal_manifest()
    for case in document["cases"]:  # type: ignore[union-attr]
        case["provenance_kind"] = "bug_introducing_commit"

    manifest = load_manifest(_write_manifest(tmp_path, document))

    assert manifest.cases[0].provenance_kind == "bug_introducing_commit"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d["cases"][1].update({"source_id": "source_002"}),  # type: ignore[index]
        lambda d: d["cases"][1].update({"fixed_commit": "c" * 40}),  # type: ignore[index]
        lambda d: d["cases"][1]["patch"].update({"sha256": "0" * 64}),  # type: ignore[index]
        lambda d: d["cases"][1].update({"split": "validation"}),  # type: ignore[index]
        lambda d: d["cases"][1].update({"source_license": "MIT"}),  # type: ignore[index]
        lambda d: d["cases"][1].update({"provenance_kind": "bug_introducing_commit"}),  # type: ignore[index]
    ],
)
def test_load_manifest_rejects_pair_members_with_nonshared_corpus_identity(
    tmp_path: Path, mutation: object
) -> None:
    """A pair with swapped source or fix metadata is not a valid counterfactual control."""
    document = _literal_manifest()
    mutation(document)  # type: ignore[operator]

    with pytest.raises(ValueError, match="pair"):
        load_manifest(_write_manifest(tmp_path, document))
