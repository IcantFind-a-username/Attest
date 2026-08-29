"""Benchmark CLI fails closed and emits stable machine-readable output."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

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


def test_validate_prepared_root_requires_verified_isolation_and_writes_bound_artifacts(
    tmp_path: Path,
) -> None:
    """A flag or passthrough wrapper cannot self-assert isolation and sign a receipt."""
    manifest, root, source_id = _oracle_fixture(tmp_path)
    receipt = tmp_path / "validation-receipt.json"
    results = tmp_path / "validation-results.json"

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
    assert "isolation wrapper" in json.loads(refused.stderr)["error"]

    passthrough = tmp_path / "passthrough"
    passthrough.write_text("#!/bin/sh\nexec \"$@\"\n", encoding="utf-8")
    passthrough.chmod(0o755)
    unisolated = _run(
        "validate",
        "--manifest",
        str(manifest),
        "--offline",
        "--root",
        str(root),
        "--python",
        f"{source_id}={sys.executable}",
        "--isolation-wrapper",
        str(passthrough),
        "--receipt-out",
        str(receipt),
        "--validation-results-out",
        str(results),
    )
    unisolated_report = json.loads(unisolated.stdout)
    assert unisolated.returncode == 4
    assert unisolated_report["command_success"] is False
    assert unisolated_report["receipt"] is None
    assert not receipt.exists()
    assert not results.exists()

    sandbox = Path("/usr/bin/sandbox-exec")
    if sys.platform != "darwin" or not sandbox.is_file():
        pytest.skip("requires a real OS network sandbox")

    completed = _run(
        "validate",
        "--manifest",
        str(manifest),
        "--offline",
        "--root",
        str(root),
        "--python",
        f"{source_id}={sys.executable}",
        "--isolation-wrapper",
        str(sandbox),
        "--isolation-arg=-p",
        "--isolation-arg=(version 1) (allow default) (deny network*)",
        "--receipt-out",
        str(receipt),
        "--validation-results-out",
        str(results),
    )
    report = json.loads(completed.stdout)
    assert completed.returncode == 0
    assert report["command_success"] is True
    assert report["corpus_valid"] is True
    assert report["validation_status"] == "valid"
    assert json.loads(receipt.read_text()) == report["receipt"]
    assert json.loads(results.read_text()) == report["validation_results"]


def _cassette(root: Path, case_id: str, proposal: str, repro: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{case_id}.json").write_text(
        json.dumps(
            {"proposal": proposal, "repro": repro, "input_tokens": 800, "output_tokens": 200}
        ),
        encoding="utf-8",
    )


def test_replay_without_prepared_root_excludes_each_case_and_stays_offline(
    tmp_path: Path,
) -> None:
    """Replay never turns a missing environment into a negative, and never
    reaches git, gh, curl, or a credentialed provider."""
    source, _ = _source(tmp_path, bug_count=1)
    manifest = tmp_path / "manifest.json"
    imported = __import__("attest.benchmark.corpus", fromlist=["import_bugsinpy"])
    imported.import_bugsinpy(source, manifest, limit=1, seed=1)
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

    first = _run(
        "replay",
        "--manifest",
        str(manifest),
        "--cassette-root",
        str(tmp_path / "cassettes"),
        "--output",
        str(tmp_path / "out-1"),
        env=environment,
    )
    second = _run(
        "replay",
        "--manifest",
        str(manifest),
        "--cassette-root",
        str(tmp_path / "cassettes"),
        "--output",
        str(tmp_path / "out-2"),
        env=environment,
    )

    assert first.returncode == 3
    assert second.returncode == 3
    assert not marker.exists()
    summary = json.loads(first.stdout)
    assert summary["status"] == "not_executed"
    assert summary["offline"] is True
    assert summary["evaluated_cases"] == 0
    assert summary["excluded_cases"] == 2
    report = json.loads((tmp_path / "out-1" / "report.json").read_text(encoding="utf-8"))
    assert report["metrics"] is None
    assert {row["reason"] for row in report["excluded_cases"]} == {"cassette_missing"}
    assert (tmp_path / "out-2" / "report.json").read_bytes() == (
        tmp_path / "out-1" / "report.json"
    ).read_bytes()
    assert (tmp_path / "out-2" / "report.md").read_bytes() == (
        tmp_path / "out-1" / "report.md"
    ).read_bytes()


def test_replay_with_a_prepared_root_runs_the_real_product_path(tmp_path: Path) -> None:
    """A prepared checkout plus a cassette replays the whole product path offline."""
    from attest.benchmark.artifacts import verify_artifacts

    manifest, root, _ = _oracle_fixture(tmp_path)
    document = json.loads(manifest.read_text(encoding="utf-8"))
    replay_id = next(
        case["case_id"]
        for case in document["cases"]
        if case["role"] == "historical_bug_replay"
    )
    control_id = next(
        case["case_id"]
        for case in document["cases"]
        if case["role"] == "developer_fix_control"
    )
    cassettes = tmp_path / "cassettes"
    _cassette(
        cassettes,
        replay_id,
        json.dumps(
            {
                "findings": [
                    {
                        "claim": "value() returns 0 instead of the documented 1.",
                        "anchor": {"file": "calc.py", "line": 2},
                        "failure_scenario": "value() returns 0 and callers divide by it",
                        "falsification_plan": "call value() and require the documented 1",
                    }
                ]
            }
        ),
        json.dumps(
            {
                "test_body": "import runpy\n\n"
                "def test_value_is_one():\n"
                "    assert runpy.run_path('calc.py')['value']() == 1\n"
            }
        ),
    )
    _cassette(
        cassettes, control_id, json.dumps({"findings": []}), json.dumps({"test_body": ""})
    )
    environment = dict(os.environ)
    environment["ANTHROPIC_API_KEY"] = "must-not-be-used"
    output = tmp_path / "out"

    completed = _run(
        "replay",
        "--manifest",
        str(manifest),
        "--cassette-root",
        str(cassettes),
        "--root",
        str(root),
        "--output",
        str(output),
        "--k-samples",
        "2",
        "--repeats",
        "1",
        env=environment,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "ok"
    assert summary["offline"] is True
    assert summary["evaluated_cases"] == 2
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "replay"
    assert report["metrics"]["true_positives"] == 1
    assert report["metrics"]["true_negatives"] == 1
    assert report["metrics"]["finding_false_positives"] == 0
    assert report["evidence_class_counts"] == {"regression_reproduced": 1}
    assert "replay regression" in " ".join(report["limitations"])
    assert len(verify_artifacts(output / "artifacts")) > 0
