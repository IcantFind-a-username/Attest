"""Benchmark artifacts are allowlisted, redacted, bounded, and hash-bound."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from attest.benchmark.artifacts import (
    ARTIFACT_KINDS,
    ArtifactError,
    ArtifactStore,
    canonical_json_bytes,
    sha256_bytes,
    verify_artifacts,
    write_canonical_json,
)


def _store(tmp_path: Path, **kwargs: object) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts", **kwargs)  # type: ignore[arg-type]


def test_artifact_store_rejects_bound_too_small_for_validation_signature(
    tmp_path: Path,
) -> None:
    """A valid store configuration cannot fail later while persisting a run attempt."""
    with pytest.raises(ArtifactError, match="at least 64"):
        ArtifactStore(tmp_path / "artifacts", max_bounded_bytes=32)


def test_artifact_store_requires_total_limit_to_cover_bounded_limit(
    tmp_path: Path,
) -> None:
    """Every accepted store configuration can persist its own bounded payloads."""
    with pytest.raises(ArtifactError, match="at least max_bounded_bytes"):
        ArtifactStore(
            tmp_path / "artifacts",
            max_bounded_bytes=64,
            max_artifact_bytes=63,
        )


def test_canonical_json_is_one_stable_utf8_record() -> None:
    """Changing key order or whitespace must not change a signed receipt payload."""
    assert canonical_json_bytes({"z": "é", "a": [2, 1]}) == (
        b'{"a":[2,1],"z":"\\u00e9"}\n'
    )


def test_canonical_json_write_preserves_target_after_partial_temporary_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "receipt.json"
    target.write_text('{"status":"old"}\n', encoding="utf-8")
    original_write = os.write

    def fail_after_partial_write(descriptor: int, payload: bytes) -> int:
        original_write(descriptor, payload[:8])
        raise OSError("injected temporary-write failure")

    monkeypatch.setattr(os, "write", fail_after_partial_write)

    with pytest.raises(ArtifactError, match="artifact write"):
        write_canonical_json(target, {"status": "new", "pairs": ["pair-1"]})

    assert target.read_text(encoding="utf-8") == '{"status":"old"}\n'
    assert list(tmp_path.iterdir()) == [target]


def test_sha256_bytes_hashes_only_exact_bytes() -> None:
    assert sha256_bytes(b"attest\n") == (
        "9d202405b53afe90b936a78cd43c32475467ef4f093bdc351f0978db305e4981"
    )
    with pytest.raises(TypeError, match="exact bytes"):
        sha256_bytes(bytearray(b"attest\n"))  # type: ignore[arg-type]


def test_allowlist_covers_the_preregistered_evidence_kinds() -> None:
    """The allowlist is the security boundary, so it is asserted literally."""
    assert frozenset(
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
    ) == ARTIFACT_KINDS


def test_validation_evidence_is_bounded_and_content_addressed(tmp_path: Path) -> None:
    """Dropping any raw validation artifact class would leave a summary-only receipt."""
    root = tmp_path / "artifacts"
    store = ArtifactStore(root, max_bounded_bytes=64)
    payloads = {
        "validation_stdout": "x" * 512,
        "validation_junit": "<testsuite tests='1' failures='0'>" + "x" * 512,
        "validation_test": "python -m pytest -q test_calc.py\n",
        "validation_command": {"argv": ["python", "-m", "pytest"]},
        "validation_interpreter": {"sha256": "a" * 64},
        "validation_environment": {"sha256": "b" * 64},
        "validation_source": {"repository_sha": "c" * 40},
        "validation_executor": {"sha256": "d" * 64},
    }

    records = {
        kind: store.write(f"{kind}.json", kind, payload)
        for kind, payload in payloads.items()
    }
    store.finalize()

    verified = {record.kind: record for record in verify_artifacts(root)}
    assert verified == records
    assert records["validation_stdout"].truncated is True
    assert records["validation_junit"].truncated is True


def test_unknown_kind_is_refused_before_any_bytes_are_written(tmp_path: Path) -> None:
    """A raw provider prompt/response has no allowlisted kind and cannot be stored."""
    store = _store(tmp_path)

    with pytest.raises(ArtifactError, match="artifact kind"):
        store.write("prompt.txt", "provider_prompt", "system prompt and full response")

    assert not (tmp_path / "artifacts" / "prompt.txt").exists()
    assert store.records() == ()


@pytest.mark.parametrize(
    "name",
    [
        "../escape.json",
        "/etc/passwd",
        "nested\\windows.json",
        "",
        ".",
    ],
)
def test_path_traversal_and_absolute_names_are_refused(tmp_path: Path, name: str) -> None:
    store = _store(tmp_path)

    with pytest.raises(ArtifactError):
        store.write(name, "predictions", {"findings": []})


def test_write_refuses_symlinked_parent_without_touching_outside(tmp_path: Path) -> None:
    """Issuance containment applies before bytes are written, not only while reading."""
    root = tmp_path / "artifacts"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "runs").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ArtifactError, match="symlink|contained"):
        ArtifactStore(root).write("runs/stdout.txt", "validation_stdout", "evidence")

    assert list(outside.iterdir()) == []


@pytest.mark.parametrize("operation", ["write", "finalize"])
def test_atomic_write_does_not_follow_preexisting_temp_symlink(
    tmp_path: Path, operation: str
) -> None:
    """A planted legacy .tmp link cannot redirect issuance outside the store."""
    root = tmp_path / "artifacts"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("sentinel", encoding="utf-8")
    target = "record.json" if operation == "write" else "artifacts.json"
    (root / f"{target}.tmp").symlink_to(outside)
    store = ArtifactStore(root)

    if operation == "write":
        store.write(target, "predictions", {"findings": []})
    else:
        store.finalize()

    assert outside.read_text(encoding="utf-8") == "sentinel"


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "deploy.pem", "server.key", "id_rsa", "secrets/.git-credentials"],
)
def test_credential_file_names_are_refused(tmp_path: Path, name: str) -> None:
    """Even an allowlisted kind cannot smuggle a credential file name through."""
    store = _store(tmp_path)

    with pytest.raises(ArtifactError, match="credential"):
        store.write(name, "predictions", {"findings": []})


@pytest.mark.parametrize(
    "payload",
    [
        "-----BEGIN RSA PRIVATE KEY-----\nMIIEow\n-----END RSA PRIVATE KEY-----",
        "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNz\n-----END OPENSSH PRIVATE KEY-----",
        "authorization: token ghp_0123456789abcdefghijklmnopqrstuvwx",
        "github_pat_11ABCDEFG0abcdefghijklmnopqrstuvwxyz0123456789",
        "ANTHROPIC_API_KEY=sk-ant-api03-0123456789abcdefghijklmnopqrst",
        "aws key AKIAIOSFODNN7EXAMPLE used",
        "slack xoxb-1234567890-abcdefghijkl",
    ],
)
def test_secret_shaped_content_is_refused(tmp_path: Path, payload: str) -> None:
    store = _store(tmp_path)

    with pytest.raises(ArtifactError, match="secret"):
        store.write("summary.md", "github_summary", payload)

    assert not (tmp_path / "artifacts" / "summary.md").exists()


def test_known_in_process_secret_values_are_recursively_redacted(tmp_path: Path) -> None:
    """A secret that the harness already holds is scrubbed at every nesting depth."""
    store = _store(tmp_path, secrets=("hunter2-live-token",))

    record = store.write(
        "run.json",
        "scored_run",
        {
            "reason": "GitHub comment: hunter2-live-token rejected",
            "runs": [{"env": {"header": "Bearer hunter2-live-token"}}],
        },
    )

    written = (tmp_path / "artifacts" / "run.json").read_text(encoding="utf-8")
    assert "hunter2-live-token" not in written
    assert written.count("[REDACTED]") == 2
    assert record.sha256 == __import__("hashlib").sha256(written.encode()).hexdigest()


def test_bounded_kinds_truncate_and_unbounded_oversize_is_refused(tmp_path: Path) -> None:
    """Repro/JUnit tails are bounded; an oversized ledger is refused, not silently cut."""
    store = _store(tmp_path, max_bounded_bytes=64, max_artifact_bytes=256)

    record = store.write("repro.txt", "repro_output", "x" * 500)
    stored = (tmp_path / "artifacts" / "repro.txt").read_bytes()

    assert len(stored) == 64
    assert record.truncated is True

    with pytest.raises(ArtifactError, match="exceeds"):
        store.write("ledger.jsonl", "product_ledger", "y" * 300)


def test_manifest_is_written_last_and_seals_the_store(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = ArtifactStore(root)
    store.write("manifest.json", "manifest", {"schema_version": "1"})
    store.write("predictions.json", "predictions", {"findings": [{"finding_id": "f1"}]})

    assert not (root / "artifacts.json").exists()

    manifest_path = store.finalize()

    assert manifest_path == root / "artifacts.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert [entry["name"] for entry in document["artifacts"]] == [
        "manifest.json",
        "predictions.json",
    ]
    assert all(len(entry["sha256"]) == 64 for entry in document["artifacts"])
    with pytest.raises(ArtifactError, match="finalized"):
        store.write("late.json", "predictions", {})


def test_verify_detects_tampering_and_unlisted_files(tmp_path: Path) -> None:
    root = tmp_path / "artifacts"
    store = ArtifactStore(root)
    store.write("predictions.json", "predictions", {"findings": []})
    store.finalize()

    assert len(verify_artifacts(root)) == 1

    (root / "predictions.json").write_text('{"findings": [1]}', encoding="utf-8")
    with pytest.raises(ArtifactError, match="digest"):
        verify_artifacts(root)

    (root / "predictions.json").write_text(
        json.dumps({"findings": []}, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    (root / "stowaway.txt").write_text("unknown", encoding="utf-8")
    with pytest.raises(ArtifactError, match="unknown artifact"):
        verify_artifacts(root)


def test_verify_rejects_forged_artifact_size_metadata(tmp_path: Path) -> None:
    """A digest match cannot turn an empty file into non-empty run evidence."""
    root = tmp_path / "artifacts"
    store = ArtifactStore(root)
    store.write("stdout.txt", "validation_stdout", b"")
    manifest = store.finalize()
    document = json.loads(manifest.read_text(encoding="utf-8"))
    document["artifacts"][0]["size_bytes"] = 1
    manifest.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ArtifactError, match="size"):
        verify_artifacts(root)


@pytest.mark.parametrize(
    "mutation",
    ["manifest_field", "entry_field", "truncated_string", "duplicate_name"],
)
def test_verify_rejects_unknown_or_mistyped_manifest_fields(
    tmp_path: Path, mutation: str
) -> None:
    """G-CODE-002: the artifact-manifest schema is exact, typed, and unique."""
    root = tmp_path / "artifacts"
    store = ArtifactStore(root)
    store.write("stdout.txt", "validation_stdout", b"evidence\n")
    manifest = store.finalize()
    document = json.loads(manifest.read_bytes())
    if mutation == "manifest_field":
        document["unexpected"] = True
    elif mutation == "entry_field":
        document["artifacts"][0]["unexpected"] = True
    elif mutation == "truncated_string":
        document["artifacts"][0]["truncated"] = "false"
    else:
        document["artifacts"].append(dict(document["artifacts"][0]))
    manifest.write_text(
        json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ArtifactError):
        verify_artifacts(root)


def test_two_identical_stores_produce_identical_manifests(tmp_path: Path) -> None:
    """Determinism: the same writes must yield byte-identical manifest bytes."""
    payloads = [
        ("predictions.json", "predictions", {"findings": [{"finding_id": "b"}, {"a": 1}]}),
        ("junit.xml", "junit", "<testsuite failures='1'/>"),
    ]
    manifests = []
    for index in range(2):
        store = ArtifactStore(tmp_path / f"run{index}")
        for name, kind, payload in payloads:
            store.write(name, kind, payload)
        manifests.append(store.finalize().read_bytes())

    assert manifests[0] == manifests[1]
