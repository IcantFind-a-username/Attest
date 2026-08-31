#!/usr/bin/env python3
# ruff: noqa: E501, E702, I001
"""Run one fresh, local-only M-01 mixed-outcome measurement."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import threading
import traceback
from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any, cast

BASELINE = "0e58cd61a1a63c51a329d5c1a5509181be32adfa"
CASE_ID = "case-333333333333"
MARKER = "legacy_mixed_outcome_denominator"
CASSETTE_FIELDS = {"schema_version", "case_id", "fixture", "proposal", "generators"}
GENERATOR_FIELDS = {"claim", "claim_sha256", "response", "response_sha256",
                    "input_tokens", "output_tokens"}

def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _git(root: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()

def _exact(value: object, fields: set[str], label: str) -> dict[str, object]:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"{label} does not contain the exact frozen fields")
    return value

def _text(row: Mapping[str, object], key: str) -> str:
    value = row[key]
    if type(value) is not str or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value

def _count(row: Mapping[str, object], key: str) -> int:
    value = row[key]
    if type(value) is not int or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value

def _cassette(path: Path) -> tuple[dict[str, object], str]:
    raw = path.read_bytes(); doc = _exact(json.loads(raw), CASSETTE_FIELDS, "cassette")
    if doc["schema_version"] != "attest.m01-mixed-cassette.v1" or doc["case_id"] != CASE_ID:
        raise ValueError("unsupported cassette identity")
    fixture = _exact(doc["fixture"], {"buggy", "buggy_sha256", "fixed",
        "fixed_sha256", "test", "test_sha256"}, "fixture")
    proposal = _exact(doc["proposal"], {"response", "response_sha256",
        "input_tokens", "output_tokens"}, "proposal")
    values = doc["generators"]
    if type(values) is not list or len(values) != 5:
        raise ValueError("cassette must contain five generators")
    generators = [_exact(row, GENERATOR_FIELDS, "generator") for row in values]
    for row in (proposal, *generators):
        response = _text(row, "response")
        if _sha(response.encode()) != _text(row, "response_sha256"):
            raise ValueError("response hash mismatch")
        _count(row, "input_tokens"); _count(row, "output_tokens")
    tokens = [(_count(row, "input_tokens"), _count(row, "output_tokens"))
              for row in (proposal, *generators)]
    if tokens != [(23, 101), *[(7, 19)] * 4, (7, 1)]:
        raise ValueError("token count mismatch")
    for row in generators:
        if _sha(_text(row, "claim").encode()) != _text(row, "claim_sha256"):
            raise ValueError("claim hash mismatch")
    for name in ("buggy", "fixed", "test"):
        if _sha(_text(fixture, name).encode()) != _text(fixture, f"{name}_sha256"):
            raise ValueError("fixture hash mismatch")
    digest = _sha(raw); sums = (path.parent / "SHA256SUMS").read_text(encoding="ascii")
    if sums != f"{digest}  {path.name}\n":
        raise ValueError("cassette SHA256SUMS mismatch")
    return doc, digest

def _repository(root: Path, fixture: Mapping[str, object]) -> tuple[Path, str, str]:
    repo = root / "repository"; repo.mkdir(); _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "fixture@example.invalid")
    _git(repo, "config", "user.name", "Fixture")
    (repo / "calc.py").write_text(_text(fixture, "buggy"), encoding="utf-8")
    (repo / "test_calc.py").write_text(_text(fixture, "test"), encoding="utf-8")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "buggy")
    buggy = _git(repo, "rev-parse", "HEAD")
    (repo / "calc.py").write_text(_text(fixture, "fixed"), encoding="utf-8")
    _git(repo, "add", "."); _git(repo, "commit", "-qm", "fixed")
    return repo, buggy, _git(repo, "rev-parse", "HEAD")

def _run(args: argparse.Namespace) -> int:
    source = args.source_root.resolve(strict=True)
    sys.path.insert(0, str(source / "src"))
    import attest
    from attest.benchmark.api import ProjectEvaluationRequest, ProjectTruth, evaluate_project
    from attest.benchmark.artifacts import ArtifactStore, _atomic_write, canonical_json_bytes
    from attest.benchmark.live import LIVE_MODE, build_calibration_report, case_payload
    from attest.benchmark.schema import (BenchmarkCase, BenchmarkManifest,
        ChangedLocation, PatchDescriptor, TestDescriptor, TruthDefect, is_scored_placement)
    from attest.review.config import ReviewConfig
    from attest.review.executor import _CREDENTIAL_NAME_PARTS, ExecutorLimits
    from attest.review.proposer import ProviderResult

    module = Path(attest.__file__).resolve()
    dirty = _git(source, "status", "--porcelain", "--", "src")
    if not module.is_relative_to((source / "src").resolve()) or dirty:
        raise ValueError("source import or source tree guard failed")
    removed = tuple(name for name in os.environ
                    if any(part in name.upper() for part in _CREDENTIAL_NAME_PARTS))
    for name in removed:
        del os.environ[name]
    os.environ.update({"GIT_AUTHOR_DATE": "2001-01-01T00:00:00Z",
                       "GIT_COMMITTER_DATE": "2001-01-01T00:00:00Z",
                       "GIT_CONFIG_GLOBAL": "/dev/null"})
    violations: list[str] = []

    def audit(event: str, values: tuple[object, ...]) -> None:
        if event == "socket.connect":
            address = values[1]
            host = address[0] if isinstance(address, tuple) and address else None
            if host not in {"127.0.0.1", "::1"}:
                violations.append(str(host)); raise RuntimeError("external network denied")

    sys.addaudithook(audit)
    doc, cassette_sha = _cassette(args.cassette.resolve(strict=True))
    proposal = cast(Mapping[str, object], doc["proposal"])
    generators = cast(list[dict[str, object]], doc["generators"])

    class Provider:
        def __init__(self) -> None:
            self.proposals = 0; self.generators = 0; self.lock = threading.Lock()

        def sample(self, system: str, prompt: str, schema: dict[str, Any],
                   max_tokens: int, *, timeout_s: float | None = None) -> ProviderResult:
            with self.lock:
                if "focused pytest reproduction" not in system:
                    self.proposals += 1; row = proposal
                else:
                    self.generators += 1
                    matches = [row for row in generators if _text(row, "claim") in prompt]
                    if len(matches) != 1:
                        raise ValueError("generator prompt response mismatch")
                    row = matches[0]
            return ProviderResult(text=_text(row, "response"),
                input_tokens=_count(row, "input_tokens"),
                output_tokens=_count(row, "output_tokens"))

    with tempfile.TemporaryDirectory(prefix="attest-m01-", dir="/private/tmp") as temporary:
        root = Path(temporary)
        repo, buggy, fixed = _repository(root, cast(Mapping[str, object], doc["fixture"]))
        truth = TruthDefect("defect-1", CASE_ID, "calc.py", 2, 2)
        request = ProjectEvaluationRequest(case_id=CASE_ID, repo=repo, base_ref=fixed,
            head_ref=buggy, workspace_root=root / "workspace", repeat=args.repeat, repeats=1,
            config=ReviewConfig(k_samples=2, max_findings=3, tier0_commands=[]),
            limits=ExecutorLimits(wall_timeout_s=30.0),
            truth=ProjectTruth(defects=(truth,), fixed_ref=fixed))
        product, oracle = Provider(), Provider(); store = ArtifactStore(root / "artifacts")
        result = evaluate_project(request, provider=product, oracle_provider=oracle,
                                  artifact_store=store)
        store.finalize(); strict = case_payload(result)
        strict["paid_calls"] = [
            {"call_id": "m01:product", "role": "product", "cost_usd": result.spend_usd},
            {"call_id": "m01:oracle", "role": "benchmark_oracle",
             "cost_usd": result.oracle_spend_usd},
        ]
        if json.loads(canonical_json_bytes(strict)) != strict:
            raise ValueError("strict payload round-trip failed")
        report_input = dict(strict); report_input["repeat"] = 0
        measurement_input = report_input.get("measurement")
        if type(measurement_input) is dict:
            report_input["measurement"] = {**measurement_input, "repeat": 0}
        case = BenchmarkCase(CASE_ID, "pair-222222222222", "source-111111111111",
            "historical_bug_replay", "historical_fix", "MIT", buggy, fixed,
            PatchDescriptor("fix.patch", "a" * 64, "unified_diff"),
            TestDescriptor("test.argv", "b" * 64, "normalized_text"),
            (ChangedLocation("calc.py", 2, 2),), "test")
        manifest = BenchmarkManifest("1", "1", "5" * 64, (case,), (truth,))
        report = build_calibration_report(manifest, (report_input,), run_id="m01-offline",
            mode=LIVE_MODE, manifest_sha256="6" * 64,
            preregistration_sha256="7" * 64, validation_receipt=None).to_json_dict()
        visible = tuple(item for item in result.predictions if is_scored_placement(item.placement))
        placements = sorted(item.placement.value for item in visible)
        guards = (len(result.final_decisions) == 5, len(visible) == 4,
            placements == ["inline", "inline", "inline", "overflow"],
            result.task_id is not None, bool(result.abstain_reason and result.abstain_reason.strip()),
            product.proposals == 2, product.generators == 5,
            oracle.proposals == 0, oracle.generators == 4, not violations)
        if not all(guards):
            raise ValueError("common product execution guard failed")
        isolation_sha = _sha(str(root).encode())

    source_sha = _git(source, "rev-parse", "HEAD")
    payload: dict[str, object] = {
        "schema_version": "attest.m01-offline-probe.v1", "source_sha": source_sha,
        "source_sha256": _sha(source_sha.encode()),
        "source_tree_sha256": _sha(_git(source, "rev-parse", "HEAD^{tree}").encode()),
        "input_sha256": _sha(canonical_json_bytes(doc)),
        "probe_sha256": _sha(Path(__file__).read_bytes()), "cassette_sha256": cassette_sha,
        "fixture_sha256": _sha(canonical_json_bytes(doc["fixture"])),
        "repeat": args.repeat, "repeats": 1, "candidate_count": 5,
        "published": 4, "unresolved": 1, "partially_deferred": 1,
        "task_status": "partially_deferred", "semantic_n": 1,
        "operational_repeats": 1, "isolation_sha256": isolation_sha,
        "guards": {"credential_variables_removed": len(removed),
            "credentials_available": False, "external_network": False,
            "local_only_provider": True, "loopback_delivery": True,
            "paid_provider_calls": 0, "remote_writes": 0, "resume": False}}
    if source_sha == BASELINE:
        if report["evaluated_cases"] != 0 or len(cast(list[object], report["abstained_cases"])) != 1:
            raise ValueError("unexpected baseline legacy filter result")
        semantic = {key: payload[key] for key in ("candidate_count", "published",
                    "unresolved", "partially_deferred", "task_status")}
        payload["semantic_digest"] = _sha(canonical_json_bytes(semantic))
        payload["expected_failure"] = MARKER
        _atomic_write(args.output.parent.resolve(), args.output.name, canonical_json_bytes(payload))
        print(MARKER, file=sys.stderr)
        return 1
    from attest.benchmark.measurement import (decode_measurement_record,
        reduce_measurements, semantic_measurement_sha256)

    measurement = decode_measurement_record(result.measurement.to_json_dict())
    summary = reduce_measurements((replace(measurement, repeat=0),))
    current = (report["evaluated_cases"] == 1, measurement.candidate_count == 5,
        measurement.published_count == 4,
        measurement.unresolved_count == 1,
        measurement.task_status.value == "partially_deferred",
        summary.semantic_n == 1, summary.operational_repeats == 1,
        summary.published == 4, summary.unresolved == 1,
        summary.partially_deferred == 1)
    if not all(current):
        raise ValueError("current mixed-outcome denominator regression")
    payload["semantic_digest"] = semantic_measurement_sha256(measurement)
    _atomic_write(args.output.parent.resolve(), args.output.name, canonical_json_bytes(payload))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    for name in ("source-root", "cassette", "output"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    parser.add_argument("--repeat", type=int, required=True)
    parser.add_argument("--repeats", type=int, choices=(1,), required=True)
    args = parser.parse_args()
    if args.repeat < 0:
        parser.error("--repeat must be non-negative")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        return _run(args)
    except Exception:
        traceback.print_exc(); return 2


if __name__ == "__main__":
    raise SystemExit(main())
