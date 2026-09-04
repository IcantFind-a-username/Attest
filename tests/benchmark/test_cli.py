"""Benchmark CLI fails closed and emits stable machine-readable output."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ._validation_v2 import KEY, KEY_ID, build_validation_v2_bundle
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


def test_validate_prepared_root_requires_verified_isolation_and_keeps_evidence_unsigned(
    tmp_path: Path,
) -> None:
    """A flag or passthrough wrapper cannot turn diagnostics into scoring authority."""
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
    passthrough.write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
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
    assert "issued_authority" not in unisolated_report
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
    assert report["receipt"] is None
    assert report["scorable"] is False
    assert "issued_authority" not in report
    assert not receipt.exists()
    assert not results.exists()


def test_validate_cli_rejects_legacy_v2_signing_before_nonempty_untrusted_runner(
    tmp_path: Path,
) -> None:
    """Legacy V2 signing inputs fail before the unsigned corpus runner executes."""
    manifest, prepared_root, source_id = _oracle_fixture(tmp_path)
    marker = tmp_path / "untrusted-runner-invoked"
    wrapper = tmp_path / "marker-wrapper"
    wrapper.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n", encoding="utf-8")
    wrapper.chmod(0o755)
    receipt = tmp_path / "issued-receipt.json"
    results = tmp_path / "issued-results.json"
    artifacts = tmp_path / "issued-artifacts"
    key_file = tmp_path / "issuer.key"
    raw_key = b"issuer-test-key-preserves-trailing-newline\n"
    key_file.write_bytes(raw_key)
    base = (
        "validate",
        "--manifest",
        str(manifest),
        "--offline",
        "--root",
        str(prepared_root),
        "--python",
        f"{source_id}={sys.executable}",
        "--isolation-wrapper",
        str(wrapper),
    )
    refused = _run(
        *base,
        "--receipt-out",
        str(receipt),
        "--validation-results-out",
        str(results),
        "--validation-artifacts",
        str(artifacts),
        "--validation-provenance-key-id",
        KEY_ID,
        "--validation-provenance-key-file",
        str(key_file),
    )
    assert refused.returncode == 2
    assert "X-01" in json.loads(refused.stderr)["error"]
    assert not marker.exists()
    assert not receipt.exists()
    assert not results.exists()
    assert not artifacts.exists()
    assert raw_key not in (refused.stdout + refused.stderr).encode()


def test_validate_cli_preserves_legacy_output_compatibility_without_authority(
    tmp_path: Path,
) -> None:
    """Old output flags remain inert compatibility inputs for unsigned validate."""
    manifest, _, _ = _oracle_fixture(tmp_path)
    ignored = tmp_path / "ignored.json"

    rootless_single = _run(
        "validate",
        "--manifest",
        str(manifest),
        "--offline",
        "--receipt-out",
        str(ignored),
    )

    assert rootless_single.returncode == 3, rootless_single.stderr
    assert json.loads(rootless_single.stdout)["receipt"] is None
    assert not ignored.exists()


def test_verify_validation_cli_is_pure_offline_and_reports_exact_failures(
    tmp_path: Path,
) -> None:
    """Current V2 authority is CLI-reachable only at a non-executing boundary."""
    manifest, root, _ = _oracle_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path / "verification", manifest, root)
    key_file = tmp_path / "verification.key"
    key_file.write_bytes(KEY)
    arguments = (
        "verify-validation",
        "--manifest",
        str(manifest),
        "--validation-receipt",
        str(bundle.receipt_path),
        "--validation-results",
        str(bundle.results_path),
        "--validation-artifacts",
        str(bundle.artifact_root),
        "--validation-provenance-key-id",
        KEY_ID,
        "--validation-provenance-key-file",
        str(key_file),
    )

    verified = _run(*arguments)

    assert verified.returncode == 0, verified.stderr
    payload = json.loads(verified.stdout)
    assert payload["authority"] == "current_scoring_authority"
    assert payload["integrity"] == {"accepted": True, "failure_paths": []}
    assert payload["authorized_provenance"] == {
        "accepted": True,
        "failure_paths": [],
    }
    assert payload["semantic_policy"] == {"accepted": True, "failure_paths": []}
    assert len(payload["binding_sha256"]) == 64
    assert KEY not in (verified.stdout + verified.stderr).encode()

    artifact_manifest = json.loads(
        (bundle.artifact_root / "artifacts.json").read_text(encoding="utf-8")
    )
    artifact = bundle.artifact_root / artifact_manifest["artifacts"][0]["name"]
    artifact.write_bytes(b"tampered")
    rejected = _run(*arguments)
    assert rejected.returncode == 2
    assert "artifact" in json.loads(rejected.stderr)["error"]
    assert KEY not in (rejected.stdout + rejected.stderr).encode()


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


def _receipt_artifacts(tmp_path: Path, manifest: Path) -> tuple[Path, Path]:
    """A validation receipt and results bound to this exact manifest's bytes."""
    document = json.loads(manifest.read_text(encoding="utf-8"))
    pair_ids = sorted({case["pair_id"] for case in document["cases"]})
    manifest_sha256 = hashlib.sha256(manifest.read_bytes()).hexdigest()
    results = {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "results": [{"pair_id": pair_id, "status": "validated"} for pair_id in pair_ids],
    }
    results_bytes = (
        json.dumps(results, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    receipt = {
        "schema_version": "1",
        "manifest_sha256": manifest_sha256,
        "validated_pair_ids": pair_ids,
        "validation_results_sha256": hashlib.sha256(results_bytes).hexdigest(),
    }
    receipt_path = tmp_path / "validation-receipt.json"
    results_path = tmp_path / "validation-results.json"
    results_path.write_bytes(results_bytes)
    receipt_path.write_bytes(
        (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    return receipt_path, results_path


def _replay_fixture(tmp_path: Path, *, control_proposal: str | None = None) -> tuple[
    Path, Path, Path, str, str
]:
    """Manifest, prepared root, cassettes, and both opaque case ids."""
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
                "def test_value_is_seven():\n"
                "    assert runpy.run_path('calc.py')['value']() == 7\n"
            }
        ),
    )
    _cassette(
        cassettes,
        control_id,
        json.dumps({"findings": []}) if control_proposal is None else control_proposal,
        json.dumps({"test_body": ""}),
    )
    return manifest, root, cassettes, replay_id, control_id


def test_replay_with_a_prepared_root_runs_the_real_product_path(tmp_path: Path) -> None:
    """A prepared checkout plus a cassette replays the whole product path offline.

    The corpus has no manifest-bound validation receipt yet, so the same run
    that measures latency and spend must refuse to publish accuracy (D-019),
    and must say which authorisation is missing.
    """
    from attest.benchmark.artifacts import verify_artifacts

    manifest, root, cassettes, _, _ = _replay_fixture(tmp_path)
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
    assert summary["metrics_status"] == "withheld"
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "replay"
    assert report["metrics"] is None
    assert report["metrics_withheld_reason"] == "validation_receipt_missing"
    assert report["operational"]["decided_cases"] == 2
    assert report["operational"]["delivery_rate"] is not None
    assert report["operational"]["abstained_cases"] == 0
    assert "validation receipt" in " ".join(report["limitations"])
    assert report["evidence_class_counts"] == {"regression_reproduced": 1}
    assert "replay regression" in " ".join(report["limitations"])
    assert len(verify_artifacts(output / "artifacts")) > 0


def test_replay_scores_only_when_a_receipt_for_this_manifest_authorises_it(
    tmp_path: Path,
) -> None:
    """The CLI must not upgrade a historical v1 receipt into current authority."""
    manifest, root, cassettes, _, _ = _replay_fixture(tmp_path)
    receipt, results = _receipt_artifacts(tmp_path, manifest)
    environment = dict(os.environ)
    environment["ANTHROPIC_API_KEY"] = "must-not-be-used"
    output = tmp_path / "out-receipted"

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
        "--validation-receipt",
        str(receipt),
        "--validation-results",
        str(results),
        "--k-samples",
        "2",
        "--repeats",
        "1",
        env=environment,
    )

    assert completed.returncode == 3, completed.stderr
    assert json.loads(completed.stdout)["metrics_status"] == "withheld"
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["validation_authority"]["authority"] == "historical_integrity_only"
    assert report["metrics"] is None
    assert report["operational"]["decided_cases"] == 0

    mixed_key = tmp_path / "mixed-v2.key"
    mixed_key.write_bytes(KEY)
    mixed_output = tmp_path / "mixed-v1-v2"
    mixed = _run(
        "replay",
        "--manifest",
        str(manifest),
        "--cassette-root",
        str(cassettes),
        "--root",
        str(root),
        "--output",
        str(mixed_output),
        "--validation-receipt",
        str(receipt),
        "--validation-results",
        str(results),
        "--validation-artifacts",
        str(tmp_path / "mixed-v2-artifacts"),
        "--validation-provenance-key-id",
        KEY_ID,
        "--validation-provenance-key-file",
        str(mixed_key),
    )
    assert mixed.returncode == 2
    assert "X-01" in json.loads(mixed.stderr)["error"]
    assert not mixed_output.exists()


def test_replay_cli_rejects_v2_hmac_authority_before_project_execution(
    tmp_path: Path,
) -> None:
    """Recorded providers do not make same-UID project execution secretless."""
    manifest, root, cassettes, _, _ = _replay_fixture(tmp_path)
    bundle = build_validation_v2_bundle(tmp_path / "replay-v2", manifest, root)
    key_file = tmp_path / "authority.key"
    key_file.write_bytes(KEY)
    output = tmp_path / "replay-v2-out"

    completed = _run(
        "replay",
        "--manifest",
        str(manifest),
        "--cassette-root",
        str(cassettes),
        "--root",
        str(root),
        "--validation-receipt",
        str(bundle.receipt_path),
        "--validation-results",
        str(bundle.results_path),
        "--validation-artifacts",
        str(bundle.artifact_root),
        "--validation-provenance-key-id",
        KEY_ID,
        "--validation-provenance-key-file",
        str(key_file),
        "--output",
        str(output),
        "--k-samples",
        "2",
        "--repeats",
        "1",
    )

    assert completed.returncode == 2
    assert "X-01" in json.loads(completed.stderr)["error"]
    assert not output.exists()
    assert KEY not in (completed.stdout + completed.stderr).encode()


def test_replay_records_a_deferral_as_an_abstention_not_as_earned_silence(
    tmp_path: Path,
) -> None:
    """A case the tool could not decide is not a case it correctly stayed silent on.

    Counting the deferral as a true negative would inflate specificity with a
    case the tool never judged.
    """
    manifest, root, cassettes, _, control_id = _replay_fixture(
        tmp_path, control_proposal="not-json-at-all"
    )
    environment = dict(os.environ)
    environment["ANTHROPIC_API_KEY"] = "must-not-be-used"
    output = tmp_path / "out-deferred"

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
    assert summary["evaluated_cases"] == 2
    assert summary["abstained_cases"] == 1
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert [row["case_id"] for row in report["abstained_cases"]] == [control_id]
    assert report["abstained_cases"][0]["reason"]
    assert control_id not in {row["case_id"] for row in report["excluded_cases"]}
    assert report["metrics"] is None
    assert report["metrics_withheld_reason"] == (
        "validation_receipt_missing"
    )
    assert report["operational"]["decided_cases"] == 1
    assert report["operational"]["abstained_cases"] == 1
    markdown = (output / "report.md").read_text(encoding="utf-8")
    assert "## Abstentions" in markdown
    assert f"| `{control_id}` |" in markdown
    assert "abstention" in " ".join(report["limitations"])


def test_compare_cli_reports_authoritative_mixed_outcome_counts(
    tmp_path: Path,
    local_ruff_executable: Path,
    comparison_cli_authority: tuple[Path, str],
) -> None:
    """Compare stdout must project the sealed product reducer, not top-level runs."""
    manifest, root, cassettes, _, _ = _replay_fixture(
        tmp_path, control_proposal="not-json-at-all"
    )
    output = tmp_path / "compare-mixed"
    authority_root, run_identity = comparison_cli_authority

    completed = _run(
        "compare",
        "--manifest",
        str(manifest),
        "--cassette-root",
        str(cassettes),
        "--root",
        str(root),
        "--output",
        str(output),
        "--comparison-authority-root",
        str(authority_root),
        "--comparison-run-id",
        run_identity,
        "--ruff-executable",
        str(local_ruff_executable),
        "--k-samples",
        "2",
        "--differential-repeats",
        "1",
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["outcome_accounting"] == {
        "abstentions": 1,
        "deployment_misses": None,
        "failures": 0,
        "metrics_withheld_reason": None,
        "operational_unadjudicated": 0,
        "operational_repeats": 2,
        "pr_any_wrong_withheld_reason": None,
        "published": 1,
        "reducer_semantics": "mixed_outcome_v3",
        "semantic_n": 2,
        "task_status_counts": {
            "completed": 1,
            "failed": 0,
            "fully_deferred": 1,
            "partially_deferred": 0,
        },
        "unadjudicated": 0,
        "unresolved": 0,
    }
    report = json.loads((output / "comparison.json").read_text(encoding="utf-8"))
    product = next(arm for arm in report["arms"] if arm["arm"] == "attest_product")
    assert product["outcome_accounting"] == summary["outcome_accounting"]
    assert product["accuracy"] is None
