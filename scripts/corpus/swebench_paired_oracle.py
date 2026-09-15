"""Original-test repair discrimination; never a product or forward-recall score."""

from __future__ import annotations

import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path, PurePosixPath

from runtime_contract_shadow import archive
from wheel_overlay import apply_wheel

from attest.benchmark.artifacts import (
    canonical_json_bytes,
    sha256_bytes,
    validation_junit_counts,
    write_canonical_json,
)
from attest.execution.container_adapter import ContainerAdapter, ContainerImage
from attest.execution.controller import Controller
from attest.execution.types import ResourceLimits

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/swebench-independent-v1"
INPUTS = ROOT / ".attest/corpora/swebench-oracle-inputs"
RUNTIME = ROOT / ".attest/corpora/swebench-source-runtime-r3"
BUILDS = ROOT / ".attest/corpora/swebench-compatible-build"
PREVIOUS = ROOT / ".attest/corpora/swebench-independent-runtime"
REPO = PREVIOUS / "scikit-learn__scikit-learn/repo"
WORK = ROOT / ".attest/corpora/swebench-paired-oracle"
REPAIRS = {
    "scikit-learn__scikit-learn-25232": "e3e65048ecae271a9afc850816ff50e64c0ca01d",
    "scikit-learn__scikit-learn-25973": "e6c6eea1872ee42ec6d0bc290ed7ae0bedd81b12",
    "scikit-learn__scikit-learn-26323": "5bf7a7cace408349b0bd41506ff2ba839aa42fbe",
}


def main() -> None:
    if WORK.exists():
        raise ValueError("fresh output directory required")
    manifest_bytes = (INPUTS / "manifest.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    runtime_bytes = (RUNTIME / "result.json").read_bytes()
    runtime = json.loads(runtime_bytes)
    if (
        manifest["status"] != "frozen" or runtime["status"] != "complete"
        or manifest["runtime_record_sha256"] != sha256_bytes(runtime_bytes)
        or {r["case"] for r in manifest["rows"]} != set(REPAIRS)
    ):
        raise ValueError("frozen input mismatch")
    builds = json.loads((BUILDS / "result.json").read_bytes())
    WORK.mkdir(mode=0o700)
    os.environ["DOCKER_CONFIG"] = str(PREVIOUS / "docker-config")
    os.environ["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True, timeout=30,
    ).strip()
    record = {
        "status": "started", "rows": [], "not_run": manifest["not_accessed"],
        "qualified_defects": 0, "qualified_controls": 0, "model_api_spend_usd": 0,
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((STUDY / "paired-oracle.md").read_bytes()),
        "input_manifest_sha256": sha256_bytes(manifest_bytes),
        "runtime_record_sha256": sha256_bytes(runtime_bytes),
        "tree_kind": "frozen_base_with_python_repair_and_identical_original_test_overlay",
    }
    for entry in manifest["rows"]:
        label = entry["case"]
        row = {"case": label, "status": "started", "runs": [], "paired_witness": False}
        record["rows"].append(row)
        write_canonical_json(WORK / "result.json", record)
        try:
            payload = (INPUTS / (label + ".json")).read_bytes()
            if sha256_bytes(payload) != entry["oracle_input_sha256"]:
                raise ValueError("oracle input drift")
            original = json.loads(payload)
            revision = entry["base_commit"]
            prior = next(r for r in runtime["rows"] if r["case"] == label)
            built = next(r for r in builds["rows"] if r["case"] == label)
            if not prior["runtime_ready"] or prior["revision"] != revision:
                raise ValueError("runtime identity mismatch")
            nodes = original["FAIL_TO_PASS"]
            nodes = json.loads(nodes) if isinstance(nodes, str) else nodes
            if not nodes or any(not re.fullmatch(r"[\w./:\[\]-]+", n) for n in nodes):
                raise ValueError("unsupported original nodes")
            if any(len(n.split("::")) != 2 or "[" in n for n in nodes):
                raise ValueError("only original module-level nonparameterized nodes supported")
            expected_identities = sorted(
                (n.split("::")[0][:-3].replace("/", "."), n.split("::")[1]) for n in nodes
            )
            patch_paths = {}
            for field in ("patch", "test_patch"):
                paths = re.findall(r"^diff --git a/(\S+) b/\1$", original[field], re.MULTILINE)
                if not paths or len(paths) != original[field].count("diff --git ") or any(
                    PurePosixPath(p).is_absolute() or ".." in PurePosixPath(p).parts
                    or not p.startswith("sklearn/") or not p.endswith(".py") for p in paths
                ):
                    raise ValueError("unsupported original patch paths")
                patch_paths[field] = paths
            if set(patch_paths["patch"]) & set(patch_paths["test_patch"]):
                raise ValueError("repair/test overlap")
            if any(n.split("::")[0] not in patch_paths["test_patch"] for n in nodes):
                raise ValueError("node outside original test patch")
            work = WORK / label
            work.mkdir()
            wheels = [(p, d) for p, d in built["artifacts"].items() if p.endswith(".whl")]
            if len(wheels) != 1 or built["revision"] != revision:
                raise ValueError("wheel identity mismatch")
            wheel_path, wheel_digest = wheels[0]
            trees = {}
            maps = {}
            for side in ("repaired", "buggy"):
                tree = work / side
                archive(REPO, revision, tree, timeout=60)
                transfer = apply_wheel(
                    tree, BUILDS / label / wheel_path, revision=revision,
                    expected_revision=built["revision"], expected_digest=wheel_digest,
                    packages=("sklearn",),
                )
                write_canonical_json(work / (side + "-transfer.json"), transfer)
                for field in (["patch", "test_patch"] if side == "repaired" else ["test_patch"]):
                    if any(not (tree / p).is_file() for p in patch_paths[field]):
                        raise ValueError("patch must modify existing files")
                    subprocess.run(
                        ["git", "apply", "--whitespace=nowarn", "-"], cwd=tree,
                        env={**os.environ, "GIT_CEILING_DIRECTORIES": str(tree.parent)},
                        input=original[field].encode(), capture_output=True, check=True, timeout=30,
                    )
                    for path in patch_paths[field]:
                        upstream = subprocess.check_output(
                            ["git", "-C", str(REPO), "show", REPAIRS[label] + ":" + path],
                            timeout=30,
                        )
                        if (tree / path).read_bytes() != upstream:
                            raise ValueError("original patch does not match upstream file")
                maps[side] = {
                    p.relative_to(tree).as_posix(): sha256_bytes(p.read_bytes())
                    for p in tree.rglob("*") if p.is_file()
                }
                trees[side] = tree
            if any(maps["repaired"][p] != maps["buggy"][p] for p in patch_paths["test_patch"]):
                raise ValueError("oracle bytes differ")
            row.update(
                base_revision=revision, upstream_repair_reference=REPAIRS[label],
                image=prior["image"], nodes=nodes,
                final_tree_digests={
                    s: sha256_bytes(canonical_json_bytes(m)) for s, m in maps.items()
                },
                oracle_digests={p: maps["buggy"][p] for p in patch_paths["test_patch"]},
            )
            adapter = ContainerAdapter(ContainerImage(prior["image"], prior["image"]))
            bootstrap = (
                "import os,sys,sklearn; "
                "assert os.path.realpath(sklearn.__file__).startswith(os.getcwd()+'/'); "
                "import pytest; sys.exit(pytest.main(sys.argv[1:]))"
            )
            first_nodes = None
            for repeat in range(3):
                pair = []
                for side, tree in trees.items():
                    run = f"{side}-{repeat}"
                    job = {"run": run, "status": "started"}
                    row["runs"].append(job)
                    write_canonical_json(WORK / "result.json", record)
                    controller = Controller(work / "execution" / run)
                    request = controller.issue(
                        task_id="oracle-" + label, run_id=run, candidate_id="oracle",
                        revision_sha=revision, profile=adapter.profile, interpreter="python3",
                        argv_template=("python3", "-c", bootstrap, *nodes,
                                       "-p", "no:cacheprovider", "--junitxml={outputs}/junit.xml"),
                        environment={
                            "PYTHONPATH": "/attest/tree", "PYTHONDONTWRITEBYTECODE": "1",
                            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                            "MKL_NUM_THREADS": "1",
                        }, inputs={}, limits=ResourceLimits(120, 120, 2048, 262144),
                        expected_artifacts=("stdout.txt", "stderr.txt", "junit.xml"),
                    )
                    outcome = controller.dispatch(request, adapter, tree=tree, inputs={})
                    job.update(
                        status="complete", accepted=outcome.accepted,
                        envelope=asdict(outcome.envelope) if outcome.envelope else None,
                        artifact_digests={k: sha256_bytes(v) for k, v in outcome.artifacts.items()},
                    )
                    write_canonical_json(WORK / "result.json", record)
                    xml = outcome.artifacts.get("junit.xml", b"")
                    counts = validation_junit_counts(xml)
                    identities = sorted(
                        (n.get("classname", ""), n.get("name", ""))
                        for n in ET.fromstring(xml).iter("testcase")
                    ) if xml else []
                    expected_failures = 0 if side == "repaired" else len(nodes)
                    matched = bool(
                        outcome.accepted and outcome.envelope
                        and outcome.envelope.exit_code == (0 if side == "repaired" else 1)
                        and counts == (len(nodes), expected_failures, 0, 0)
                        and identities == expected_identities
                    )
                    job.update(counts=counts, identities=identities, matched=matched)
                    pair.append(job)
                    write_canonical_json(WORK / "result.json", record)
                if (
                    not all(j["matched"] for j in pair)
                    or pair[0]["identities"] != pair[1]["identities"]
                ):
                    raise ValueError("original oracle pair did not discriminate; no repair")
                if first_nodes is not None and first_nodes != pair[0]["identities"]:
                    raise ValueError("unstable original test population")
                first_nodes = pair[0]["identities"]
            row.update(status="paired_witness_semantics_and_direction_pending", paired_witness=True)
        except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError) as exc:
            row.update(status="unqualified", reason=str(exc))
        write_canonical_json(WORK / "result.json", record)
        print(label, row["status"], row.get("reason", ""), flush=True)
    record["status"] = "complete"
    write_canonical_json(WORK / "result.json", record)


if __name__ == "__main__":
    main()
