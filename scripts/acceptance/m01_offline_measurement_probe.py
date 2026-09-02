#!/usr/bin/env python3
# ruff: noqa: E501, E702, I001
"""Run and aggregate the isolated M-01 mixed-outcome measurement."""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, cast

BASELINE = "0e58cd61a1a63c51a329d5c1a5509181be32adfa"
CASE_ID, MARKER = "case-333333333333", "legacy_mixed_outcome_denominator"
ALLOWED_ENV = frozenset({"GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "HOME", "LC_ALL",
                         "PATH", "PYTHONDONTWRITEBYTECODE", "TMPDIR"})
CASSETTE_FIELDS = {"schema_version", "case_id", "fixture", "proposal", "generators"}
GENERATOR_FIELDS = {"claim", "claim_sha256", "response", "response_sha256",
                    "input_tokens", "output_tokens"}
STABLE_FIELDS = ("cassette_sha256", "fixture_sha256", "input_sha256", "probe_sha256",
                 "source_sha", "source_sha256", "source_tree_sha256")
RUN_FIELDS = {*STABLE_FIELDS, "guards", "isolation_sha256", "measurement", "repeat",
              "repeats", "schema_version", "semantic_digest"}
GUARD_FIELDS = {"delivery_transport", "entry_environment_variable_names",
                "environment_allowlist", "paid_provider_calls", "platform_environment_removed",
                "provider_transport", "python_external_connect_attempts"}
Support = tuple[Callable[[object], bytes], Callable[[bytes], str], Callable[..., Any], Callable[..., Any]]

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

def _support() -> Support:
    support_src = str(Path(__file__).resolve().parents[2] / "src")
    sys.path.insert(0, support_src)
    try:
        artifacts = importlib.import_module("attest.benchmark.artifacts")
        outcomes = importlib.import_module("attest.benchmark.outcomes")
        return (artifacts.canonical_json_bytes, artifacts.sha256_bytes,
                outcomes.read_canonical_json, outcomes.write_canonical_json_once)
    finally:
        sys.path.remove(support_src)
        for name in tuple(sys.modules):
            if name == "attest" or name.startswith("attest."):
                del sys.modules[name]

def _guard_environment() -> tuple[list[str], bool]:
    platform_value = os.environ.pop("__CF_USER_TEXT_ENCODING", None)
    platform_removed = platform_value is not None
    if platform_value is not None and re.fullmatch(
        r"0x[0-9A-Fa-f]+:0x[0-9A-Fa-f]+:0x[0-9A-Fa-f]+", platform_value
    ) is None:
        raise ValueError("invalid platform-injected environment value")
    unexpected = sorted(set(os.environ) - ALLOWED_ENV)
    if not unexpected:
        return sorted(os.environ), platform_removed
    support_src = str(Path(__file__).resolve().parents[2] / "src")
    sys.path.insert(0, support_src)
    try:
        is_secret_name = cast(
            Callable[[str], bool],
            importlib.import_module("attest.review.security").is_secret_name,
        )
    finally:
        sys.path.remove(support_src)
        for name in tuple(sys.modules):
            if name == "attest" or name.startswith("attest."):
                del sys.modules[name]
    credential = any(is_secret_name(name) for name in unexpected)
    raise ValueError(f"unexpected {'credential environment' if credential else 'environment'} variable name(s): {unexpected}")

def _source(source: Path) -> tuple[Path, str]:
    source = source.resolve(strict=True); sys.path.insert(0, str(source / "src"))
    module = Path(cast(str, importlib.import_module("attest").__file__)).resolve()
    if (not module.is_relative_to((source / "src").resolve())
            or _git(source, "status", "--porcelain", "--", "src")):
        raise ValueError("source import or clean-tree guard failed")
    return source, _git(source, "rev-parse", "HEAD")

def _cassette(path: Path, digest: Callable[[bytes], str]) -> tuple[dict[str, object], str]:
    raw = path.read_bytes(); doc = _exact(json.loads(raw), CASSETTE_FIELDS, "cassette")
    if doc["schema_version"] != "attest.m01-mixed-cassette.v1" or doc["case_id"] != CASE_ID:
        raise ValueError("unsupported cassette identity")
    fixture = _exact(doc["fixture"], {"buggy", "buggy_sha256", "fixed", "fixed_sha256",
        "test", "test_sha256"}, "fixture")
    proposal = _exact(doc["proposal"], {"response", "response_sha256",
        "input_tokens", "output_tokens"}, "proposal")
    values = doc["generators"]
    if type(values) is not list or len(values) != 5:
        raise ValueError("cassette must contain five generators")
    generators = [_exact(row, GENERATOR_FIELDS, "generator") for row in values]
    for row in (proposal, *generators):
        if digest(_text(row, "response").encode()) != _text(row, "response_sha256"):
            raise ValueError("response hash mismatch")
    tokens = [(_count(row, "input_tokens"), _count(row, "output_tokens"))
              for row in (proposal, *generators)]
    if tokens != [(23, 101), *[(7, 19)] * 4, (7, 1)]:
        raise ValueError("token count mismatch")
    for row in generators:
        if digest(_text(row, "claim").encode()) != _text(row, "claim_sha256"):
            raise ValueError("claim hash mismatch")
    for name in ("buggy", "fixed", "test"):
        if digest(_text(fixture, name).encode()) != _text(fixture, f"{name}_sha256"):
            raise ValueError("fixture hash mismatch")
    cassette_sha = digest(raw)
    if (path.parent / "SHA256SUMS").read_text(encoding="ascii") != f"{cassette_sha}  {path.name}\n":
        raise ValueError("cassette SHA256SUMS mismatch")
    return doc, cassette_sha

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
    canonical, digest, _, write_once = _support()
    source, source_sha = _source(args.source_root)
    from attest.benchmark.api import ProjectEvaluationRequest, ProjectTruth, evaluate_project
    from attest.benchmark.artifacts import ArtifactStore
    from attest.benchmark.live import LIVE_MODE, build_calibration_report, case_payload
    from attest.benchmark.schema import (BenchmarkCase, BenchmarkManifest, ChangedLocation,
        PatchDescriptor, TestDescriptor, TruthDefect, is_scored_placement)
    from attest.review.config import ReviewConfig
    from attest.review.executor import ExecutorLimits
    from attest.review.proposer import ProviderResult

    os.environ.update({"GIT_AUTHOR_DATE": "2001-01-01T00:00:00Z",
                       "GIT_COMMITTER_DATE": "2001-01-01T00:00:00Z"})
    external_attempts: list[str] = []
    def audit(event: str, values: tuple[object, ...]) -> None:
        if event == "socket.connect":
            address = values[1]; host = address[0] if isinstance(address, tuple) and address else None
            if host not in {"127.0.0.1", "::1"}:
                external_attempts.append(str(host)); raise RuntimeError("external network denied")
    sys.addaudithook(audit)
    doc, cassette_sha = _cassette(args.cassette.resolve(strict=True), digest)
    proposal = cast(Mapping[str, object], doc["proposal"])
    generators = cast(list[dict[str, object]], doc["generators"])
    class Provider:
        def __init__(self) -> None:
            self.proposals = 0; self.generators = 0; self.lock = threading.Lock()
        def sample(self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int,
                   *, timeout_s: float | None = None) -> ProviderResult:
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
                input_tokens=_count(row, "input_tokens"), output_tokens=_count(row, "output_tokens"))

    with tempfile.TemporaryDirectory(prefix="attest-m01-", dir="/private/tmp") as temporary:
        root = Path(temporary); repo, buggy, fixed = _repository(
            root, cast(Mapping[str, object], doc["fixture"]))
        truth = TruthDefect("defect-1", CASE_ID, "calc.py", 2, 2)
        request = ProjectEvaluationRequest(case_id=CASE_ID, repo=repo, base_ref=fixed,
            head_ref=buggy, workspace_root=root / "workspace", repeat=args.repeat, repeats=1,
            config=ReviewConfig(k_samples=2, max_findings=3, tier0_commands=[]),
            limits=ExecutorLimits(wall_timeout_s=30.0),
            truth=ProjectTruth(defects=(truth,), fixed_ref=fixed))
        product, oracle = Provider(), Provider(); store = ArtifactStore(root / "artifacts")
        result = evaluate_project(request, provider=product, oracle_provider=oracle, artifact_store=store)
        store.finalize(); strict = case_payload(result)
        strict["paid_calls"] = [
            {"call_id": "m01:product", "role": "product", "cost_usd": result.spend_usd},
            {"call_id": "m01:oracle", "role": "benchmark_oracle",
             "cost_usd": result.oracle_spend_usd}]
        if json.loads(canonical(strict)) != strict:
            raise ValueError("strict payload round-trip failed")
        # Report smoke normalizes only its copy; the persisted measurement below stays exact.
        report_input = dict(strict); report_input["repeat"] = 0
        if type(report_input.get("measurement")) is dict:
            report_input["measurement"] = {**cast(dict[str, object], strict["measurement"]), "repeat": 0}
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
        expected_product_generators = 5 if source_sha == BASELINE else 6
        # since C-05 the product publishes same-defect certified findings once and caps
        # author-visible claims; the four mixed findings of this cassette then surface
        # as one inline claim instead of three inline plus one overflow
        family_policy = importlib.util.find_spec("attest.certification.clustering") is not None
        expected_visible = ["inline"] if family_policy else ["inline", "inline", "inline", "overflow"]
        guards = (len(result.final_decisions) == 5, len(visible) == len(expected_visible),
            sorted(item.placement.value for item in visible) == expected_visible,
            result.task_id is not None, bool(result.abstain_reason and result.abstain_reason.strip()),
            product.proposals == 2, product.generators == expected_product_generators,
            oracle.proposals == 0, oracle.generators == len(expected_visible), not external_attempts)
        if not all(guards):
            detail = {
                "decisions": len(result.final_decisions),
                "visible": sorted(item.placement.value for item in visible),
                "generators": product.generators,
                "oracle": (oracle.proposals, oracle.generators),
            }
            raise ValueError(f"common product execution guard failed: {guards} {detail}")
        isolation_sha = digest(str(root).encode())
    payload: dict[str, object] = {
        "schema_version": "attest.m01-offline-run.v2", "source_sha": source_sha,
        "source_sha256": digest(source_sha.encode()),
        "source_tree_sha256": digest(_git(source, "rev-parse", "HEAD^{tree}").encode()),
        "input_sha256": digest(canonical(doc)), "probe_sha256": digest(Path(__file__).read_bytes()),
        "cassette_sha256": cassette_sha, "fixture_sha256": digest(canonical(doc["fixture"])),
        "repeat": args.repeat, "repeats": 1, "isolation_sha256": isolation_sha,
        "guards": {"delivery_transport": "loopback_http", "environment_allowlist": True,
            "entry_environment_variable_names": args.entry_environment_names,
            "paid_provider_calls": 0, "platform_environment_removed": args.platform_environment_removed,
            "provider_transport": "in_process_frozen_cassette", "python_external_connect_attempts": 0}}
    if source_sha == BASELINE:
        if report["evaluated_cases"] != 0 or len(
            cast(list[object], report["abstained_cases"])) != 1:
            raise ValueError("unexpected baseline legacy filter result")
        payload["observed"] = {"candidate_count": 5, "published": 4,
                               "task_status": "partially_deferred", "unresolved": 1}
        payload["expected_failure"] = MARKER
        write_once(args.output.parent.resolve(), args.output.name, payload)
        print(MARKER, file=sys.stderr); return 1
    from attest.benchmark.measurement import decode_measurement_record, semantic_measurement_sha256
    measurement_payload = result.measurement.to_json_dict()
    measurement = decode_measurement_record(measurement_payload)
    current = (report["evaluated_cases"] == 1, measurement.candidate_count == 5,
        measurement.published_count == 4,
        measurement.unresolved_count == 1,
        measurement.task_status.value == "partially_deferred")
    if not all(current):
        raise ValueError("current mixed-outcome denominator regression")
    payload["semantic_digest"] = semantic_measurement_sha256(measurement)
    payload["measurement"] = measurement_payload
    write_once(args.output.parent.resolve(), args.output.name, payload)
    return 0

def _aggregate(args: argparse.Namespace) -> int:
    canonical, digest, read_canonical, write_once = _support()
    source, source_sha = _source(args.source_root)
    from attest.benchmark.measurement import (decode_measurement_record,
        reduce_measurements, semantic_measurement_sha256)
    root = args.input_root.resolve(strict=True)
    expected = {f"current-{repeat}.json" for repeat in range(args.expected_repeats)}
    files = {path.name for path in root.iterdir() if path.is_file()}
    extra_dirs = {path.name for path in root.iterdir()
                  if path.is_dir() and path.name != ".outcome-staging"}
    if files != expected or extra_dirs:
        raise ValueError("aggregate input root does not contain the exact repeat files")
    payloads: list[dict[str, object]] = []; output_digests: dict[str, str] = {}; guards_seen = set()
    for repeat in range(args.expected_repeats):
        name = f"current-{repeat}.json"; document = read_canonical(root, name)
        payload = _exact(document.value, RUN_FIELDS, "aggregate run input")
        if (payload["schema_version"], payload["repeat"], payload["repeats"]) != (
            "attest.m01-offline-run.v2", repeat, 1):
            raise ValueError("aggregate repeat coverage mismatch")
        guard = _exact(payload["guards"], GUARD_FIELDS, "aggregate run guards")
        expected_guard = {"delivery_transport": "loopback_http", "environment_allowlist": True,
            "entry_environment_variable_names": sorted(ALLOWED_ENV), "paid_provider_calls": 0,
            "platform_environment_removed": guard["platform_environment_removed"],
            "provider_transport": "in_process_frozen_cassette", "python_external_connect_attempts": 0}
        if type(guard["platform_environment_removed"]) is not bool or guard != expected_guard:
            raise ValueError("aggregate run guard verdict mismatch")
        guards_seen.add(digest(canonical(guard)))
        payloads.append(payload); output_digests[name] = digest(document.data)
    if len(guards_seen) != 1:
        raise ValueError("aggregate run guards disagree")
    for field in STABLE_FIELDS:
        if len({cast(str, payload[field]) for payload in payloads}) != 1:
            raise ValueError(f"aggregate {field} mismatch")
    if payloads[0]["source_sha"] != source_sha:
        raise ValueError("aggregate source SHA does not match selected source")
    if payloads[0]["source_sha256"] != digest(source_sha.encode()):
        raise ValueError("aggregate source digest mismatch")
    if payloads[0]["source_tree_sha256"] != digest(_git(source, "rev-parse", "HEAD^{tree}").encode()):
        raise ValueError("aggregate source tree digest mismatch")
    if payloads[0]["probe_sha256"] != digest(Path(__file__).read_bytes()):
        raise ValueError("aggregate probe digest mismatch")
    measurements = []; semantic_digests: set[str] = set(); isolations: set[str] = set()
    for payload in payloads:
        measurement_value = payload["measurement"]
        if type(measurement_value) is not dict:
            raise ValueError("aggregate input is missing an exact measurement")
        measurement = decode_measurement_record(measurement_value)
        semantic = semantic_measurement_sha256(measurement)
        if measurement.repeat != payload["repeat"] or payload["semantic_digest"] != semantic:
            raise ValueError("aggregate measurement repeat or semantic digest mismatch")
        if measurement.candidate_count != 5:
            raise ValueError("aggregate candidate count mismatch")
        measurements.append(measurement); semantic_digests.add(semantic)
        isolations.add(_text(payload, "isolation_sha256"))
    if len(semantic_digests) != 1 or len(isolations) != args.expected_repeats:
        raise ValueError("aggregate semantic or isolation coverage mismatch")
    summary = reduce_measurements(tuple(measurements))
    facts = (summary.semantic_n, summary.operational_repeats, summary.published,
             summary.unresolved, summary.partially_deferred)
    if facts != (1, args.expected_repeats, 4, 1, 1):
        raise ValueError("aggregate authoritative reducer result mismatch")
    receipt = {"schema_version": "attest.m01-offline-aggregate.v1",
        **{field: payloads[0][field] for field in STABLE_FIELDS},
        "expected_repeats": args.expected_repeats,
        "candidate_count": measurements[0].candidate_count,
        "published": summary.published, "unresolved": summary.unresolved,
        "partially_deferred": summary.partially_deferred, "semantic_n": summary.semantic_n,
        "operational_repeats": summary.operational_repeats,
        "semantic_digest": next(iter(semantic_digests)), "isolation_count": len(isolations),
        "run_outputs_sha256": output_digests}
    write_once(args.output.parent.resolve(), args.output.name, receipt)
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(); commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run")
    for name in ("source-root", "cassette", "output"):
        run.add_argument(f"--{name}", type=Path, required=True)
    run.add_argument("--repeat", type=int, required=True)
    run.add_argument("--repeats", type=int, choices=(1,), required=True)
    aggregate = commands.add_parser("aggregate")
    for name in ("source-root", "input-root", "output"):
        aggregate.add_argument(f"--{name}", type=Path, required=True)
    aggregate.add_argument("--expected-repeats", type=int, choices=(20,), required=True)
    args = parser.parse_args()
    if args.command == "run" and args.repeat < 0:
        parser.error("--repeat must be non-negative")
    try:
        names, removed = _guard_environment()
        args.entry_environment_names, args.platform_environment_removed = names, removed
        return _run(args) if args.command == "run" else _aggregate(args)
    except Exception:
        traceback.print_exc(); return 2

if __name__ == "__main__":
    raise SystemExit(main())
