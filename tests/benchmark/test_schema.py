"""Manifest validation protects the preregistered benchmark corpus."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from attest.benchmark.schema import load_manifest


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
                "role": "buggy",
                "provenance_kind": "upstream",
                "source_license": "Apache-2.0",
                "buggy_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "fixed_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "patch": {"files": ["src/app.py"]},
                "patch_hash": "529431251f17f34724808f96b9dbe574b21e4f7024d7ac194b52bdc4a8b04bbd",
                "tests": {"files": ["tests/test_app.py"]},
                "test_hash": "0196e5c8601c41054c1cf094880415c863acd293bbe908a56a96a1d9fc32593f",
                "changed_locations": [
                    {"path": "src/app.py", "start_line": 10, "end_line": 12}
                ],
                "split": "test",
            },
            {
                "case_id": "case_002",
                "pair_id": "pair_001",
                "source_id": "source_001",
                "role": "fixed",
                "provenance_kind": "upstream",
                "source_license": "Apache-2.0",
                "buggy_commit": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                "fixed_commit": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                "patch": {"files": ["src/app.py"]},
                "patch_hash": "529431251f17f34724808f96b9dbe574b21e4f7024d7ac194b52bdc4a8b04bbd",
                "tests": {"files": ["tests/test_app.py"]},
                "test_hash": "0196e5c8601c41054c1cf094880415c863acd293bbe908a56a96a1d9fc32593f",
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
        (lambda d: d["cases"][0].update({"patch_hash": "0" * 64}), "patch_hash"),  # type: ignore[index]
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
