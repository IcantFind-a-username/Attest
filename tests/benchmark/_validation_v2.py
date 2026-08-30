"""Independent canonical v2 validation fixtures for receipt-boundary tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from attest.benchmark.artifacts import ArtifactRecord, ArtifactStore
from attest.benchmark.corpus import (
    ValidationVerification,
    verify_validation_receipt,
)
from attest.benchmark.schema import load_manifest

PROTOCOL_VERSION = "attest-validation-v2"
KEY_ID = "local-test-authority"
KEY = b"test-only-local-validation-authority-key"


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


@dataclass
class ValidationV2Bundle:
    manifest: Path
    receipt_path: Path
    results_path: Path
    artifact_root: Path
    receipt: dict[str, Any]
    results: dict[str, Any]

    @property
    def authorized_keys(self) -> dict[str, bytes]:
        return {KEY_ID: KEY}

    def reseal(self) -> None:
        self.results_path.write_bytes(canonical_bytes(self.results))
        self.reseal_receipt()

    def reseal_receipt(self) -> None:
        body = {
            key: value
            for key, value in self.receipt.items()
            if key != "provenance_envelope"
        }
        body["validation_results_sha256"] = hashlib.sha256(
            self.results_path.read_bytes()
        ).hexdigest()
        self.receipt.update(body)
        payload = canonical_bytes(body)
        self.receipt["provenance_envelope"] = {
            "envelope_version": "1",
            "algorithm": "hmac-sha256",
            "key_id": KEY_ID,
            "payload_sha256": hashlib.sha256(payload).hexdigest(),
            "authentication_tag": hmac.new(KEY, payload, hashlib.sha256).hexdigest(),
        }
        self.receipt_path.write_bytes(canonical_bytes(self.receipt))

    def replace_artifact(self, name: str, payload: object) -> None:
        encoded = payload if isinstance(payload, bytes) else canonical_bytes(payload)
        if isinstance(encoded, str):
            encoded = encoded.encode()
        (self.artifact_root / name).write_bytes(encoded)
        digest = hashlib.sha256(encoded).hexdigest()
        manifest_path = self.artifact_root / "artifacts.json"
        artifact_manifest = json.loads(manifest_path.read_bytes())
        entry = next(
            item for item in artifact_manifest["artifacts"] if item["name"] == name
        )
        entry["sha256"] = digest
        entry["size_bytes"] = len(encoded)
        for result in self.results["results"]:
            for attempt in result["attempts"]:
                for run in attempt["runs"]:
                    for reference in run["artifacts"].values():
                        if reference["name"] == name:
                            reference["sha256"] = digest
                            reference["size_bytes"] = len(encoded)
        manifest_path.write_bytes(canonical_bytes(artifact_manifest))
        self.receipt["artifact_manifest_sha256"] = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()
        self.reseal()


def build_validation_v2_bundle(
    tmp_path: Path, manifest: Path, corpus_root: Path | None = None
) -> ValidationV2Bundle:
    tmp_path.mkdir(parents=True, exist_ok=True)
    typed = load_manifest(manifest)
    runtimes = {runtime.case_id: runtime for runtime in typed.runtime}
    root = corpus_root or manifest.parent / "cache"
    artifact_root = tmp_path / "validation-artifacts"
    store = ArtifactStore(artifact_root)
    environment_variables = {
        "LANG": "C.UTF-8",
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_ADDOPTS": "-p no:cacheprovider",
    }
    executor_sha256 = "3" * 64
    profile_id = f"attest.network-deny.v1:{executor_sha256}"
    result_rows: list[dict[str, object]] = []
    pair_ids = sorted({case.pair_id for case in typed.cases})
    for pair_id in pair_ids:
        pair_cases = tuple(case for case in typed.cases if case.pair_id == pair_id)
        replay = next(
            case for case in pair_cases if case.role == "historical_bug_replay"
        )
        control = next(
            case for case in pair_cases if case.role == "developer_fix_control"
        )
        replay_runtime = runtimes[replay.case_id]
        control_runtime = runtimes[control.case_id]
        assert replay_runtime.tool == control_runtime.tool
        execution_prefix = [
            "/fixture/python"
            if control_runtime.tool == "python"
            else f"/fixture/{control_runtime.tool}"
        ]
        test_bytes = (root / replay.tests.relative_path).read_bytes()
        prefix = f"pairs/{pair_id}"
        shared = {
            "test": store.write(
                f"{prefix}/test.txt", "validation_test", test_bytes
            ),
            "interpreter": store.write(
                f"{prefix}/interpreter.json",
                "validation_interpreter",
                {"argv": execution_prefix, "executable_sha256": "1" * 64},
            ),
            "environment": store.write(
                f"{prefix}/environment.json",
                "validation_environment",
                {
                    "variables": environment_variables,
                    "sha256": hashlib.sha256(
                        canonical_bytes(environment_variables)
                    ).hexdigest(),
                },
            ),
            "executor": store.write(
                f"{prefix}/executor.json",
                "validation_executor",
                {
                    "executor_sha256": executor_sha256,
                    "runner_id": "local-runner-v1",
                    "profile_id": profile_id,
                    "isolation_capability": "attest.network-deny.v1",
                    "wrapper_argv": ["/fixture/isolation-wrapper"],
                },
            ),
        }
        sources = {
            "fixed": store.write(
                f"{prefix}/source-fixed.json",
                "validation_source",
                {"revision": "fixed", "repository_sha": control.fixed_commit},
            ),
            "buggy": store.write(
                f"{prefix}/source-buggy.json",
                "validation_source",
                {"revision": "buggy", "repository_sha": replay.buggy_commit},
            ),
        }
        runs: list[dict[str, object]] = []
        for revision, outcome, returncode in (
            ("fixed", "pass", 0),
            ("buggy", "fail", 1),
        ):
            case = control if revision == "fixed" else replay
            runtime = runtimes[case.case_id]
            junit_suffix = (
                ["--junitxml=/fixture/junit.xml"]
                if runtime.tool == "python" and runtime.args[:2] == ("-m", "pytest")
                else []
            )
            command = store.write(
                f"{prefix}/command-{revision}.json",
                "validation_command",
                {
                    "executed_argv": [
                        "/fixture/isolation-wrapper",
                        *execution_prefix,
                        *runtime.args,
                        *junit_suffix,
                    ],
                    "declared_tool": runtime.tool,
                    "declared_args": list(runtime.args),
                    "declared_cwd": runtime.cwd,
                },
            )
            for ordinal in range(1, 4):
                run_prefix = f"{prefix}/runs/{revision}-{ordinal}"
                stdout_text = (
                    "1 passed\n"
                    if outcome == "pass"
                    else "FAILED test_calc.py::test_value\n"
                )
                stdout = store.write(
                    f"{run_prefix}/stdout.txt", "validation_stdout", stdout_text
                )
                junit = store.write(
                    f"{run_prefix}/junit.xml",
                    "validation_junit",
                    (
                        '<testsuite tests="1" failures="0" errors="0" skipped="0" />\n'
                        if outcome == "pass"
                        else '<testsuite tests="1" failures="1" errors="0" skipped="0">'
                        '<testcase name="test_value"><failure /></testcase></testsuite>\n'
                    ),
                )
                artifacts = {
                    **{key: _record(record) for key, record in shared.items()},
                    "command": _record(command),
                    "source": _record(sources[revision]),
                    "stdout": _record(stdout),
                    "junit": _record(junit),
                }
                runs.append(
                    {
                        "run_id": f"run-{pair_id}-{revision}-{ordinal}",
                        "revision": revision,
                        "ordinal": ordinal,
                        "outcome": outcome,
                        "returncode": returncode,
                        "timed_out": False,
                        "failure_signature": (
                            hashlib.sha256(stdout_text.strip().encode()).hexdigest()
                            if revision == "buggy"
                            else None
                        ),
                        "runner_id": "local-runner-v1",
                        "profile_id": profile_id,
                        "artifacts": artifacts,
                    }
                )
        attempt_id = f"attempt-{pair_id.removeprefix('pair-')}"
        result_rows.append(
            {
                "pair_id": pair_id,
                "status": "validated",
                "buggy_sha": replay.buggy_commit,
                "fixed_sha": control.fixed_commit,
                "accepted_attempt_id": attempt_id,
                "exclusion_reason": None,
                "attempts": [
                    {
                        "attempt_id": attempt_id,
                        "pair_id": pair_id,
                        "attempt_index": 1,
                        "phase": "execution",
                        "status": "validated",
                        "reason": None,
                        "runs": runs,
                    }
                ],
            }
        )
    artifact_manifest = store.finalize()
    results: dict[str, Any] = {
        "schema_version": "2",
        "protocol_version": PROTOCOL_VERSION,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "results": result_rows,
    }
    results_path = tmp_path / "validation-results-v2.json"
    receipt_path = tmp_path / "validation-receipt-v2.json"
    receipt: dict[str, Any] = {
        "schema_version": "2",
        "protocol_version": PROTOCOL_VERSION,
        "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "validation_results_sha256": "0" * 64,
        "artifact_manifest_sha256": hashlib.sha256(artifact_manifest.read_bytes()).hexdigest(),
        "validated_pair_ids": pair_ids,
        "provenance_envelope": {},
    }
    bundle = ValidationV2Bundle(
        manifest=manifest,
        receipt_path=receipt_path,
        results_path=results_path,
        artifact_root=artifact_root,
        receipt=receipt,
        results=results,
    )
    bundle.reseal()
    return bundle


def verified_validation_authority(
    tmp_path: Path, manifest: Path, corpus_root: Path | None = None
) -> ValidationVerification:
    """Return a real verifier-minted capability for report integration tests."""
    bundle = build_validation_v2_bundle(tmp_path, manifest, corpus_root)
    return verify_validation_receipt(
        bundle.receipt_path,
        manifest,
        bundle.results_path,
        bundle.artifact_root,
        authorized_provenance_keys=bundle.authorized_keys,
    )


def _record(record: ArtifactRecord) -> dict[str, object]:
    return record.to_json_dict()
