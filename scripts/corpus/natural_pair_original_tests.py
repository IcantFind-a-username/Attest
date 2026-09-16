"""Original-human-test natural-pair witnesses through the existing guarded executor."""

from __future__ import annotations

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from heldout_v2 import stub_packages
from runtime_contract_shadow import archive
from swebench_compatible_build import natural_cases
from wheel_overlay import apply_wheel

from attest.benchmark.artifacts import sha256_bytes, validation_junit_counts, write_canonical_json
from attest.execution.container_adapter import ContainerAdapter, ContainerImage
from attest.execution.container_images import declared_version_file, discover_roots
from attest.review.candidates import StoredCandidate
from attest.review.executor import ExecutionOutcome, ExecutorLimits, ReproSpec, execute_repro
from attest.review.schema import Finding

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/metadata-exposed-v1"
RUNTIME = ROOT / ".attest/corpora/natural-pair-source-runtime"
BUILDS = ROOT / ".attest/corpora/natural-pair-compatible-build"
INPUTS = ROOT / ".attest/corpora/metadata-exposed-v1-oracles"
REPOS = ROOT / ".attest/corpora/metadata-exposed-v1"
WORK = ROOT / ".attest/corpora/natural-pair-original-tests"


def main() -> None:
    if WORK.exists():
        raise ValueError("fresh output directory required; no retry")
    if any(os.environ.get(n) for n in ("ATTEST_PROJECT_PYTHON", "ATTEST_PIP_CONSTRAINT")):
        raise ValueError("runtime override refused")
    cases_bytes = (STUDY / "compatibility/cases.json").read_bytes()
    cases = natural_cases(json.loads(cases_bytes), STUDY)
    runtime_bytes = (RUNTIME / "result.json").read_bytes()
    runtime = json.loads(runtime_bytes)
    evidence = json.loads(
        (STUDY / "compatibility/source-runtime-evidence/manifest.json").read_bytes()
    )
    builds_bytes = (BUILDS / "result.json").read_bytes()
    builds = json.loads(builds_bytes)
    oracle_manifest_bytes = (INPUTS / "manifest.json").read_bytes()
    oracle_manifest = json.loads(oracle_manifest_bytes)
    if (
        sha256_bytes(runtime_bytes) != evidence["artifacts"]["result.json"]["raw_sha256"]
        or runtime["status"] != "complete"
        or not runtime["fixture"]["runtime_ready"]
        or runtime["population_sha256"] != sha256_bytes(cases_bytes)
        or runtime["build_record_sha256"] != sha256_bytes(builds_bytes)
        or builds_bytes != (STUDY / "compatibility/build-evidence/result.json").read_bytes()
        or oracle_manifest_bytes != (STUDY / "oracle-inputs.json").read_bytes()
        or oracle_manifest["case_freeze_sha256"]
        != sha256_bytes((STUDY / "freeze.json").read_bytes())
        or [(r["case"], r["revision"]) for r in runtime["rows"]]
        != [(c["instance_id"], c["base_commit"]) for c in cases]
    ):
        raise ValueError("frozen input identity mismatch")
    WORK.mkdir(mode=0o700)
    os.environ["DOCKER_CONFIG"] = str(
        ROOT / ".attest/corpora/metadata-exposed-runtime/docker-config"
    )
    os.environ["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True,
        timeout=30,
    ).strip()
    pairs = [cases[i : i + 2] for i in range(0, len(cases), 2)]
    record = {
        "status": "started",
        "model_api_spend_usd": 0,
        "product_evaluations": 0,
        "qualified_defects": 0,
        "qualified_controls": 0,
        "development_witnesses": 0,
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((STUDY / "compatibility/original-tests.md").read_bytes()),
        "runtime_record_sha256": sha256_bytes(runtime_bytes),
        "oracle_manifest_sha256": sha256_bytes(oracle_manifest_bytes),
        "rows": [
            {"case": p[0]["source_case"], "status": "not_run", "runs": [], "paired_witness": False}
            for p in pairs
        ],
    }
    write_canonical_json(WORK / "result.json", record)
    for pair, row in zip(pairs, record["rows"], strict=True):
        label = row["case"]
        prior = [next(r for r in runtime["rows"] if r["case"] == c["instance_id"]) for c in pair]
        if not all(r["runtime_ready"] for r in prior):
            row.update(status="runtime_unqualified")
            write_canonical_json(WORK / "result.json", record)
            continue
        work = WORK / label
        work.mkdir()
        try:
            freezes = []
            for case in pair:
                key = case["instance_id"] + "/runtime-freeze.txt"
                payload = (RUNTIME / key).read_bytes()
                if sha256_bytes(payload) != evidence["artifacts"][key]["raw_sha256"]:
                    raise ValueError("runtime dependency record drift")
                freezes.append(payload)
            if freezes[0] != freezes[1]:
                raise ValueError("paired runtime dependencies differ")
            entry = next(r for r in oracle_manifest["rows"] if r["case"] == label)
            payload = (INPUTS / (label + ".json")).read_bytes()
            if sha256_bytes(payload) != entry["oracle_input_sha256"]:
                raise ValueError("original oracle drift")
            original = json.loads(payload)
            if original["instance_id"] != label or original["repo"] != pair[0]["repo"]:
                raise ValueError("original oracle identity mismatch")
            nodes = original["FAIL_TO_PASS"]
            nodes = json.loads(nodes) if isinstance(nodes, str) else nodes
            if len(nodes) != 1 or not re.fullmatch(r"[\w./]+::\w+", nodes[0]):
                raise ValueError("requires one original module-level test node")
            test_path, node = nodes[0].split("::")
            paths = re.findall(r"^diff --git a/(\S+) b/\1$", original["test_patch"], re.MULTILINE)
            anchors = re.findall(r"^diff --git a/(\S+) b/\1$", original["patch"], re.MULTILINE)
            if (
                paths != [test_path]
                or len(anchors) != 1
                or original["test_patch"].count("diff --git ") != 1
                or original["patch"].count("diff --git ") != 1
                or any(
                    PurePosixPath(p).is_absolute()
                    or ".." in PurePosixPath(p).parts
                    or not p.endswith(".py")
                    for p in [*paths, *anchors]
                )
                or anchors[0] == test_path
                or not PurePosixPath(test_path).name.startswith("test_")
            ):
                raise ValueError("unsupported original test or anchor paths")
            repo = REPOS / pair[0]["repo"].replace("/", "__") / "repo"
            oracle = work / "oracle"
            destination = oracle / test_path
            destination.parent.mkdir(parents=True)
            destination.write_bytes(
                subprocess.check_output(
                    ["git", "-C", str(repo), "show", original["base_commit"] + ":" + test_path],
                    timeout=30,
                )
            )
            subprocess.run(
                ["git", "apply", "--whitespace=nowarn", "-"],
                cwd=oracle,
                env={**os.environ, "GIT_CEILING_DIRECTORIES": str(oracle.parent)},
                input=original["test_patch"].encode(),
                check=True,
                capture_output=True,
                timeout=30,
            )
            test_bytes = destination.read_bytes()
            trees = []
            for case in pair:
                tree = work / case["side"]
                listing = subprocess.check_output(
                    ["git", "-C", str(repo), "ls-tree", "-r", case["base_commit"]],
                    timeout=30,
                )
                if any(line.startswith(b"120000 ") for line in listing.splitlines()):
                    raise ValueError("symlink export refused")
                archive(repo, case["base_commit"], tree, timeout=60)
                built = next(r for r in builds["rows"] if r["case"] == case["instance_id"])
                wheels = [(p, d) for p, d in built["artifacts"].items() if p.endswith(".whl")]
                if len(wheels) != 1 or built["revision"] != case["base_commit"]:
                    raise ValueError("revision wheel mismatch")
                version = declared_version_file(tree, discover_roots(tree))
                transfer = apply_wheel(
                    tree,
                    BUILDS / case["instance_id"] / wheels[0][0],
                    revision=case["base_commit"],
                    expected_revision=built["revision"],
                    expected_digest=wheels[0][1],
                    packages=tuple(stub_packages(tree)),
                    version_path=version.relative_to(tree).as_posix() if version else None,
                )
                write_canonical_json(work / (case["side"] + "-transfer.json"), transfer)
                if not (tree / test_path).is_file() or not (tree / anchors[0]).is_file():
                    raise ValueError("original test or anchored source absent")
                (tree / test_path).write_bytes(test_bytes)
                trees.append(tree)
            row.update(
                nodes=nodes,
                oracle_sha256=sha256_bytes(test_bytes),
                original_input_sha256=sha256_bytes(payload),
                revisions={c["side"]: c["base_commit"] for c in pair},
            )
            candidate = StoredCandidate(
                task_id="original-" + label,
                finding=Finding(
                    file=anchors[0],
                    line=1,
                    claim="original test witness",
                    failure_scenario="natural parent/head differential",
                    falsification_plan="run the unchanged original test",
                ),
                wealth=0.0,
                action="drawer",
                alpha=0.1,
            )
            for repeat in range(3):
                matched_pair = []
                for index, (case, ready, tree) in enumerate(zip(pair, prior, trees, strict=True)):
                    job = {"side": case["side"], "repeat": repeat, "status": "started"}
                    row["runs"].append(job)
                    write_canonical_json(WORK / "result.json", record)
                    result = execute_repro(
                        work,
                        candidate,
                        ReproSpec(test_bytes.decode()),
                        ExecutorLimits(120, 120, 2048, 262144),
                        tree=tree,
                        run_label=case["side"] + "-" + str(repeat),
                        node=node,
                        revision_sha=case["base_commit"],
                        tree_target=test_path,
                        adapter=ContainerAdapter(ContainerImage(ready["image"], ready["image"])),
                    )
                    counts = validation_junit_counts(result.junit_xml.encode())
                    identities = (
                        [
                            (n.get("classname"), n.get("name"))
                            for n in ET.fromstring(result.junit_xml).iter("testcase")
                        ]
                        if result.junit_xml
                        else []
                    )
                    matched = bool(
                        result.exit_code == index
                        and counts == (1, index, 0, 0)
                        and result.collected_count == 1
                        and result.skipped_count == result.xfailed_count == 0
                        and identities == [(test_path[:-3].replace("/", "."), node)]
                        and result.network_blocked
                        and result.fresh_state
                        and result.executed_lines
                        and not result.import_origins
                        and result.executor_profile == "linux-container-v1"
                        and result.outcome
                        is (
                            ExecutionOutcome.NOT_REPRODUCED
                            if index == 0
                            else ExecutionOutcome.REPRODUCED
                        )
                        and (tree / test_path).read_bytes() == test_bytes
                    )
                    job.update(status="complete", matched=matched, execution=asdict(result))
                    matched_pair.append(matched)
                    write_canonical_json(WORK / "result.json", record)
                if not all(matched_pair):
                    raise ValueError(
                        "original tests did not produce a complete parent PASS/head FAIL pair"
                    )
            row.update(status="development_original_test_witness", paired_witness=True)
            record["development_witnesses"] += 1
        except (
            ValueError,
            OSError,
            subprocess.SubprocessError,
            KeyError,
            StopIteration,
            ET.ParseError,
        ) as exc:
            row.update(status="unqualified", reason=str(exc))
        write_canonical_json(WORK / "result.json", record)
        print(label, row["status"], row.get("reason", ""), flush=True)
    record["status"] = "complete"
    write_canonical_json(WORK / "result.json", record)


if __name__ == "__main__":
    main()
