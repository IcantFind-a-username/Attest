"""Benchmark artifacts are allowlisted, redacted, bounded, and hash-bound."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from attest.benchmark.artifacts import (
    ARTIFACT_KINDS,
    ArtifactError,
    ArtifactStore,
    verify_artifacts,
)


def _store(tmp_path: Path, **kwargs: object) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts", **kwargs)  # type: ignore[arg-type]


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
        }
    ) == ARTIFACT_KINDS


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
