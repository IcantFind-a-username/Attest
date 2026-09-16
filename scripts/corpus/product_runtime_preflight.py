"""Check the frozen held-out heads with the product's own build and collection path."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path

from heldout_v2 import probe_stub_source, stub_packages
from runtime_contract_shadow import archive

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json
from attest.execution.backends import select_backend
from attest.execution.container_images import project_python
from attest.review.candidates import StoredCandidate
from attest.review.executor import ExecutorLimits, ReproSpec, execute_repro, project_roots
from attest.review.schema import Finding

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/repository-holdout-v1"
WORK = ROOT / ".attest/corpora/repository-holdout-runtime"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--study", choices=("historical", "swebench", "case-heldout", "metadata-exposed"),
        default="historical",
    )
    args = parser.parse_args()
    study = (
        STUDY if args.study == "historical" else ROOT / "benchmarks/studies/swebench-independent-v1"
    )
    work = (
        WORK
        if args.study == "historical"
        else ROOT / ".attest/corpora/swebench-independent-runtime"
    )
    if args.study in {"case-heldout", "metadata-exposed"}:
        name = "case-holdout" if args.study == "case-heldout" else "metadata-exposed"
        study = ROOT / "benchmarks/studies" / (name + "-v1")
        work = ROOT / ".attest/corpora" / (name + "-runtime")
    for name in ("ATTEST_PIP_CONSTRAINT", "ATTEST_PROJECT_PYTHON"):
        if os.environ.get(name):
            raise ValueError("runtime override refused: " + name)
    if work.exists():
        raise ValueError("runtime preflight requires a fresh work directory")
    work.mkdir(parents=True)
    (work / "tmp").mkdir()
    tempfile.tempdir = str(work / "tmp")
    os.environ["TMPDIR"] = tempfile.tempdir
    config = work / "docker-config"
    config.mkdir()
    plugins = json.loads(
        subprocess.check_output(
            ["docker", "info", "--format", "{{json .ClientInfo.Plugins}}"], text=True, timeout=30
        )
    )
    buildx = next(p for p in plugins if p["Name"] == "buildx")
    write_canonical_json(
        config / "config.json", {"cliPluginsExtraDirs": [str(Path(buildx["Path"]).parent)]}
    )
    os.environ["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True,
        timeout=30,
    ).strip()
    os.environ["DOCKER_CONFIG"] = str(config)
    os.environ["DOCKER_BUILDKIT"] = "1"
    input_name = (
        "qualification-candidates.json"
        if args.study in {"case-heldout", "metadata-exposed"} else "frozen-candidates.json"
    )
    frozen_bytes = (study / input_name).read_bytes()
    frozen = json.loads(frozen_bytes)
    if args.study == "historical":
        population = [r for r in frozen["repositories"] if r["role"] == "held_out"]
        expected_repositories, expected_cases = 4, 20
    elif args.study == "swebench":
        population = [
            {
                "project": r["repo"].replace("/", "__"),
                "url": "https://github.com/" + r["repo"] + ".git",
                "candidates": [
                    {"upstream_case": c["instance_id"], "buggy_sha": c["base_commit"]}
                    for c in r["selected"]
                ],
            }
            for r in frozen["repositories"]
            if r["selected"]
        ]
        expected_repositories, expected_cases = 2, 6
    else:
        if frozen["status"] != "agreed_source_pairs_pending_execution":
            raise ValueError("unreviewed natural pairs")
        selection_bytes = (study / "freeze.json").read_bytes()
        selection = {
            c["instance_id"]: c for c in json.loads(selection_bytes)["selected"]
        }
        if frozen["freeze_sha256"] != sha256_bytes(selection_bytes):
            raise ValueError("natural-pair selection drift")
        pairs = frozen["pairs"]
        if not pairs or len({p["case"] for p in pairs}) != len(pairs):
            raise ValueError("empty or duplicate natural pair identities")
        if any(
            p["case"] not in selection or p["repo"] != selection[p["case"]]["repo"]
            or any(not re.fullmatch(r"[0-9a-f]{40}", p[k])
                   for k in ("head_sha", "parent_sha"))
            for p in pairs
        ):
            raise ValueError("natural pair outside authorized selection")
        population = [
            {
                "project": name.replace("/", "__"),
                "url": "https://github.com/" + name + ".git",
                "candidates": [
                    {"upstream_case": p["case"], "buggy_sha": p["head_sha"]}
                    for p in pairs if p["repo"] == name
                ],
            }
            for name in dict.fromkeys(p["repo"] for p in pairs)
        ]
        expected_repositories, expected_cases = len(population), len(pairs)
    if (
        len(population) != expected_repositories
        or sum(len(r["candidates"]) for r in population) != expected_cases
    ):
        raise ValueError("frozen held-out population drift")
    record: dict = {
        "status": "started",
        "rows": [],
        "model_api_spend_usd": 0,
        "study": args.study,
        "runtime_overrides_absent": True,
        "archive_timeout_s": 60,
        "product_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "product_source_tree": subprocess.check_output(
            ["git", "rev-parse", "HEAD:src"], text=True
        ).strip(),
        "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((study / "product-runtime-preflight.md").read_bytes()),
        "population_sha256": sha256_bytes(frozen_bytes),
        "builder": {k: buildx[k] for k in ("Name", "Version", "Path")},
        "qualified_defects": 0,
        "qualified_controls": 0,
        "paid_reviews": 0,
    }
    write_canonical_json(work / "result.json", record)
    for repository in population:
        repo = work / repository["project"] / "repo"
        for case in repository["candidates"]:
            label = case["upstream_case"].replace("/", "-")
            row: dict = {
                "case": case["upstream_case"],
                "head_sha": case["buggy_sha"],
                "status": "started",
                "stage": "prepare",
                "importable": False,
            }
            record["rows"].append(row)
            write_canonical_json(work / "result.json", record)
            case_work = work / "cases" / label
            case_work.mkdir(parents=True)
            try:
                if not repo.exists():
                    repo.parent.mkdir(parents=True, exist_ok=True)
                    subprocess.run(
                        [
                            "git",
                            "clone",
                            "--no-checkout",
                            "--depth=1",
                            repository["url"],
                            str(repo),
                        ],
                        check=True,
                        capture_output=True,
                        timeout=180,
                    )
                subprocess.run(
                    ["git", "-C", str(repo), "fetch", "--depth=1", "origin", case["buggy_sha"]],
                    check=True,
                    capture_output=True,
                    timeout=120,
                )
                listing = subprocess.check_output(
                    ["git", "-C", str(repo), "ls-tree", "-r", case["buggy_sha"]], timeout=30
                )
                row["tree_listing_sha256"] = sha256_bytes(listing)
                if any(line.startswith(b"120000 ") for line in listing.splitlines()):
                    raise ValueError("harness refuses symlink-containing export")
                tree = case_work / "tree"
                archive(repo, case["buggy_sha"], tree, timeout=60)
                row["python"], row["python_reason"] = project_python(tree)
                row["packages"] = stub_packages(tree)
                if not row["packages"]:
                    raise ValueError("no package import could be witnessed")
                row["stage"] = "build"
                write_canonical_json(work / "result.json", record)
                backend = select_backend(tree, production=True, remaining_s=300)
                row["backend_reason"] = backend.reason
                row["profile"] = backend.profile
                row["image"] = asdict(backend.image) if backend.image else None
                if backend.adapter is None or backend.profile != "linux-container-v1":
                    raise ValueError("product container unavailable: " + backend.reason)
                anchor = next(
                    p.relative_to(tree).as_posix()
                    for import_root in project_roots(tree)
                    for package in row["packages"]
                    if (
                        p := tree
                        / import_root.replace("{tree}", "").lstrip("/")
                        / package
                        / "__init__.py"
                    ).is_file()
                )
                candidate = StoredCandidate(
                    task_id="runtime-" + label,
                    finding=Finding(
                        file=anchor,
                        line=1,
                        claim="runtime import diagnostic",
                        failure_scenario="package import may be unavailable",
                        falsification_plan="collect the fixed import stub",
                    ),
                    wealth=0.0,
                    action="drawer",
                    alpha=0.1,
                )
                row["stage"] = "collect"
                write_canonical_json(work / "result.json", record)
                result = execute_repro(
                    case_work,
                    candidate,
                    ReproSpec(probe_stub_source(tree)),
                    ExecutorLimits(60, 60, 1024, 16384),
                    tree=tree,
                    run_label="collect",
                    collect_only=True,
                    revision_sha=case["buggy_sha"],
                    adapter=backend.adapter,
                )
                row["execution"] = asdict(result)
                row["importable"] = (
                    result.exit_code == 0 and result.collected_count == 1 and result.network_blocked
                )
                row["status"] = "checked"
            except (ValueError, OSError, subprocess.SubprocessError, StopIteration) as exc:
                row.update(status="refused", reason=str(exc))
            write_canonical_json(work / "result.json", record)
            print(row["case"], row["stage"], row["status"], row["importable"], flush=True)
    record["status"] = "complete"
    write_canonical_json(work / "result.json", record)


if __name__ == "__main__":
    main()
