"""Run original held-out oracles in already qualified product runtime images."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import asdict
from pathlib import Path

from runtime_contract_shadow import archive

from attest.benchmark.artifacts import sha256_bytes, validation_junit_counts, write_canonical_json
from attest.execution.container_adapter import ContainerAdapter, ContainerImage
from attest.execution.controller import Controller
from attest.execution.types import ResourceLimits
from attest.review.executor import project_roots

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/repository-holdout-v1"
WORK = ROOT / ".attest/corpora/heldout-paired-oracle"
METADATA = ROOT / ".attest/corpora/repository-holdout-v1-metadata"
RUNTIME = ROOT / ".attest/corpora/repository-holdout-runtime"


def main() -> None:
    if WORK.exists():
        raise ValueError("fresh work directory required")
    for name in ("ATTEST_PIP_CONSTRAINT", "ATTEST_PROJECT_PYTHON"):
        if os.environ.get(name):
            raise ValueError("runtime override refused: " + name)
    WORK.mkdir(parents=True)
    os.environ["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True,
        timeout=30,
    ).strip()
    os.environ["DOCKER_CONFIG"] = str(RUNTIME / "docker-config")
    frozen = json.loads((STUDY / "frozen-candidates.json").read_bytes())
    runtime_bytes = (RUNTIME / "result.json").read_bytes()
    runtime = json.loads(runtime_bytes)
    assert runtime["status"] == "complete" and len(runtime["rows"]) == 20
    candidates = {
        c["upstream_case"]: c
        for r in frozen["repositories"]
        if r["role"] == "held_out"
        for c in r["candidates"]
    }
    record = {
        "status": "started",
        "rows": [],
        "model_api_spend_usd": 0,
        "qualified_defects": 0,
        "qualified_controls": 0,
        "attest_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "source_tree": subprocess.check_output(["git", "rev-parse", "HEAD:src"], text=True).strip(),
        "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "archive_helper_sha256": sha256_bytes(
            (ROOT / "scripts/corpus/runtime_contract_shadow.py").read_bytes()
        ),
        "protocol_sha256": sha256_bytes((STUDY / "paired-oracle.md").read_bytes()),
        "runtime_result_sha256": sha256_bytes(runtime_bytes),
        "override_presence": {
            name: bool(os.environ.get(name))
            for name in ("ATTEST_PIP_CONSTRAINT", "ATTEST_PROJECT_PYTHON")
        },
    }
    write_canonical_json(WORK / "result.json", record)
    for prior in runtime["rows"]:
        case = candidates[prior["case"]]
        row = {"case": prior["case"], "status": "started", "runs": [], "paired_witness": False}
        record["rows"].append(row)
        write_canonical_json(WORK / "result.json", record)
        if not prior["importable"]:
            row.update(status="runtime_unqualified", reason=prior.get("reason", prior["stage"]))
            write_canonical_json(WORK / "result.json", record)
            continue
        label = prior["case"].replace("/", "-")
        work = WORK / label
        work.mkdir()
        repo = RUNTIME / prior["case"].split("/")[0] / "repo"
        try:
            folder = str(Path(case["metadata_path"]).parent)
            metadata = {}
            for name in ("bug.info", "run_test.sh"):
                data = subprocess.check_output(
                    [
                        "git",
                        "-C",
                        str(METADATA),
                        "show",
                        frozen["corpus"]["sha"] + ":" + folder + "/" + name,
                    ],
                    timeout=30,
                )
                (work / name).write_bytes(data)
                metadata[name] = data
            argv = shlex.split(metadata["run_test.sh"].decode())
            if len(argv) != 2 or argv[0] != "pytest" or not re.fullmatch(r"[\w./:\[\]-]+", argv[1]):
                raise ValueError("unsupported original oracle command")
            test_path = argv[1].split("::")[0]
            if Path(test_path).is_absolute() or ".." in Path(test_path).parts:
                raise ValueError("unsafe test path")
            paths = re.findall(
                r'^test_file="([^"]+)"$', metadata["bug.info"].decode(), re.MULTILINE
            )
            if paths != [test_path]:
                raise ValueError("oracle operand and original test-file metadata disagree")
            row.update(
                oracle_argv=argv,
                metadata_sha256={k: sha256_bytes(v) for k, v in metadata.items()},
                image=prior["image"],
                revisions={s: case[s + "_sha"] for s in ("fixed", "buggy")},
            )
            trees = {}
            for side in ("fixed", "buggy"):
                sha = case[side + "_sha"]
                subprocess.run(
                    ["git", "-C", str(repo), "fetch", "--depth=1", "origin", sha],
                    capture_output=True,
                    check=True,
                    timeout=120,
                )
                listing = subprocess.check_output(
                    ["git", "-C", str(repo), "ls-tree", "-r", sha], timeout=30
                )
                if any(line.startswith(b"120000 ") for line in listing.splitlines()):
                    raise ValueError("symlink export refused")
                trees[side] = work / side
                archive(repo, sha, trees[side], timeout=60)
            test = (trees["fixed"] / test_path).read_bytes()
            target = trees["buggy"] / test_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(test)
            row["oracle_sha256"] = sha256_bytes(test)
            adapter = ContainerAdapter(ContainerImage(**prior["image"]))
            bootstrap = (
                "import importlib,os,sys; "
                f"mods=[importlib.import_module(n) for n in {prior['packages']!r}]; "
                "assert all(os.path.realpath(m.__file__).startswith(os.getcwd()+'/') "
                "for m in mods); "
                "print('ORACLE_SOURCE_ORIGINS',"
                "[(m.__name__,m.__file__) for m in mods],flush=True); "
                "import pytest; sys.exit(pytest.main(sys.argv[1:]))"
            )
            first_failures = None
            for repeat in range(3):
                pair = []
                for side, tree in trees.items():
                    run_label = f"{side}-{repeat}"
                    job = {"label": run_label, "status": "started"}
                    row["runs"].append(job)
                    write_canonical_json(WORK / "result.json", record)
                    controller = Controller(work / "execution" / run_label)
                    request = controller.issue(
                        task_id="oracle-" + label,
                        run_id=run_label,
                        candidate_id="oracle",
                        revision_sha=case[side + "_sha"],
                        profile=adapter.profile,
                        interpreter="python3",
                        argv_template=(
                            "python3",
                            "-c",
                            bootstrap,
                            argv[1],
                            "--junitxml={outputs}/junit.xml",
                        ),
                        environment={
                            "PYTHONPATH": ":".join(project_roots(tree)),
                            "PYTHONDONTWRITEBYTECODE": "1",
                        },
                        inputs={},
                        limits=ResourceLimits(120, 120, 2048, 262144),
                        expected_artifacts=("stdout.txt", "stderr.txt", "junit.xml"),
                    )
                    outcome = controller.dispatch(request, adapter, tree=tree, inputs={})
                    # Persist terminal execution before parsing an untrusted artifact.
                    job.update(
                        status="complete",
                        protocol_accepted=outcome.accepted,
                        envelope=asdict(outcome.envelope) if outcome.envelope else None,
                        artifact_sha256={k: sha256_bytes(v) for k, v in outcome.artifacts.items()},
                    )
                    write_canonical_json(WORK / "result.json", record)
                    xml = outcome.artifacts.get("junit.xml", b"")
                    counts = validation_junit_counts(xml)
                    nodes, failures = [], []
                    if xml:
                        for node in ET.fromstring(xml).iter("testcase"):
                            identity = [node.get("classname", ""), node.get("name", "")]
                            nodes.append(identity)
                            if node.find("failure") is not None:
                                failures.append(identity)
                    valid = bool(
                        outcome.accepted
                        and outcome.envelope
                        and counts
                        and counts[0] > 0
                        and counts[2:] == (0, 0)
                        and len(nodes) == counts[0]
                    )
                    code = outcome.envelope.exit_code if outcome.envelope else None
                    matched = (
                        valid
                        and code == (0 if side == "fixed" else 1)
                        and ((counts[1] == 0) if side == "fixed" else (counts[1] > 0))
                    )
                    job.update(
                        junit_counts=counts,
                        nodes=sorted(nodes),
                        failures=sorted(failures),
                        pattern_matched=matched,
                    )
                    pair.append(job)
                    write_canonical_json(WORK / "result.json", record)
                if (
                    not all(j["pattern_matched"] for j in pair)
                    or pair[0]["nodes"] != pair[1]["nodes"]
                ):
                    raise ValueError("non-discriminating original oracle pair; no repair")
                if first_failures is not None and first_failures != pair[1]["failures"]:
                    raise ValueError("unstable failure identities")
                first_failures = pair[1]["failures"]
            row.update(status="paired_witness_semantics_pending", paired_witness=True)
        except (ValueError, OSError, subprocess.SubprocessError, ET.ParseError) as exc:
            row.update(status="unqualified", reason=str(exc))
        write_canonical_json(WORK / "result.json", record)
        print(row["case"], row["status"], row.get("reason", ""), flush=True)
    record["status"] = "complete"
    write_canonical_json(WORK / "result.json", record)


if __name__ == "__main__":
    main()
