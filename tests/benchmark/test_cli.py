"""Benchmark CLI fails closed and emits stable machine-readable output."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from .test_corpus import _oracle_fixture, _source

_SCRIPT = Path(__file__).parents[2] / "scripts" / "benchmark.py"


def _run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


def test_import_bugsinpy_cli_requires_existing_local_source(tmp_path: Path) -> None:
    """A typo must not make import clone or discover a corpus from the network."""
    completed = _run(
        "import-bugsinpy",
        "--source",
        str(tmp_path / "missing"),
        "--output",
        str(tmp_path / "manifest.json"),
        "--limit",
        "1",
        "--seed",
        "7",
    )

    assert completed.returncode == 2
    assert json.loads(completed.stderr) == {
        "error": "source must be an existing local directory",
        "status": "error",
    }
    assert not (tmp_path / "manifest.json").exists()


def test_import_bugsinpy_cli_prints_deterministic_summary(tmp_path: Path) -> None:
    """CLI output must expose selected and excluded counts without timestamps or path noise."""
    source, _ = _source(tmp_path, bug_count=2)
    output = tmp_path / "manifest.json"

    completed = _run(
        "import-bugsinpy",
        "--source",
        str(source),
        "--project-cache",
        str(tmp_path / "project-cache"),
        "--output",
        str(output),
        "--limit",
        "1",
        "--seed",
        "7",
    )

    assert completed.returncode == 0
    assert json.loads(completed.stdout) == {
        "eligible_pairs": 2,
        "excluded_pairs": 0,
        "manifest": str(output),
        "selected_pairs": 1,
        "status": "ok",
    }


def test_validate_offline_never_invokes_network_provider_or_credentials(tmp_path: Path) -> None:
    """Offline validation must remain local even when tempting credentials and tools exist."""
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "schema_version": "1",
                "protocol_version": "1",
                "corpus_commit": "a" * 64,
                "cases": [],
                "truth_defects": [],
                "runtime": [],
                "exclusions": [
                    {"upstream_case": "sample/1", "reason": "source_license_missing"}
                ],
            }
        )
    )
    traps = tmp_path / "traps"
    traps.mkdir()
    marker = tmp_path / "invoked"
    for command in ("git", "gh", "curl"):
        trap = traps / command
        trap.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n")
        trap.chmod(0o755)
    environment = dict(os.environ)
    environment.update(
        {
            "PATH": str(traps),
            "ANTHROPIC_API_KEY": "must-not-be-used",
            "OPENAI_API_KEY": "must-not-be-used",
        }
    )

    first = _run("validate", "--manifest", str(manifest), "--offline", env=environment)
    second = _run("validate", "--manifest", str(manifest), "--offline", env=environment)

    assert first.returncode == 3
    assert first.stdout == second.stdout
    assert json.loads(first.stdout) == {
        "excluded_pairs": 0,
        "import_exclusions": [
            {"reason": "source_license_missing", "upstream_case": "sample/1"}
        ],
        "manifest": "manifest.json",
        "offline": True,
        "results": [],
        "command_success": False,
        "corpus_valid": False,
        "validation_status": "not_executed",
        "scorable": False,
        "receipt": None,
        "manifest_sha256": __import__("hashlib").sha256(manifest.read_bytes()).hexdigest(),
        "validated_pairs": 0,
    }
    assert not marker.exists()


def test_validate_offline_without_prepared_root_excludes_each_pair(tmp_path: Path) -> None:
    """Default validation cannot silently treat an unmaterialized pair as a negative."""
    source, _ = _source(tmp_path, bug_count=1)
    manifest = tmp_path / "manifest.json"
    imported = __import__("attest.benchmark.corpus", fromlist=["import_bugsinpy"])
    document = imported.import_bugsinpy(source, manifest, limit=1, seed=1)

    completed = _run("validate", "--manifest", str(manifest), "--offline")

    assert completed.returncode == 3
    assert json.loads(completed.stdout)["results"] == [
        {
            "pair_id": document["cases"][0]["pair_id"],
            "reason": "prepared_environment_required",
            "status": "not_executed",
        }
    ]


def test_validate_prepared_root_requires_network_isolation_and_writes_receipt(
    tmp_path: Path,
) -> None:
    """A prepared root is only executable behind an explicit isolation boundary."""
    manifest, root, source_id = _oracle_fixture(tmp_path)
    receipt = tmp_path / "validation-receipt.json"

    refused = _run(
        "validate",
        "--manifest",
        str(manifest),
        "--offline",
        "--root",
        str(root),
        "--python",
        f"{source_id}={sys.executable}",
    )
    assert refused.returncode == 2
    assert "network isolation" in json.loads(refused.stderr)["error"]

    completed = _run(
        "validate",
        "--manifest",
        str(manifest),
        "--offline",
        "--root",
        str(root),
        "--python",
        f"{source_id}={sys.executable}",
        "--network-isolated",
        "--receipt-out",
        str(receipt),
    )
    report = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert report["command_success"] is True
    assert report["corpus_valid"] is True
    assert report["validation_status"] == "valid"
    assert json.loads(receipt.read_text()) == report["receipt"]
