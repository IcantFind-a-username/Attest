"""One uniform, free wheel-build attempt for each frozen SWE-bench candidate."""

from __future__ import annotations

import json
import os
import subprocess
import tomllib
from datetime import datetime
from pathlib import Path

from era_constraints import _fetch, direct_dependencies, latest_before, normalise
from packaging.requirements import Requirement
from runtime_contract_shadow import archive

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json
from attest.execution.container_images import discover_roots, scm_pretend_version

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/swebench-independent-v1"
PREVIOUS = ROOT / ".attest/corpora/swebench-independent-runtime"
WORK = ROOT / ".attest/corpora/swebench-compatible-build"


def main() -> None:
    if WORK.exists():
        raise ValueError("fresh output directory required; no retry or overwrite")
    WORK.mkdir()
    env = {**os.environ, "DOCKER_CONFIG": str(PREVIOUS / "docker-config")}
    env["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True, timeout=30,
    ).strip()
    frozen = (STUDY / "frozen-candidates.json").read_bytes()
    cases = [c for r in json.loads(frozen)["repositories"] for c in r["selected"]]
    if len(cases) != 6 or len({c["repo"] for c in cases}) != 2:
        raise ValueError("population drift")
    record: dict = {
        "status": "started", "rows": [], "model_api_spend_usd": 0,
        "population_sha256": sha256_bytes(frozen),
        "protocol_sha256": sha256_bytes((STUDY / "compatible-runtime.md").read_bytes()),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "qualified_defects": 0, "qualified_controls": 0,
    }
    write_canonical_json(WORK / "result.json", record)
    subprocess.run(["docker", "pull", "python:3.10-bookworm"], env=env, check=True, timeout=300)
    base = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", "python:3.10-bookworm"], env=env, timeout=30,
    ))[0]
    reference = base["RepoDigests"][0]
    record["builder_reference"] = reference
    record["builder_id"] = base["Id"]
    for case in cases:
        row = {"case": case["instance_id"], "revision": case["base_commit"], "status": "started"}
        record["rows"].append(row)
        write_canonical_json(WORK / "result.json", record)
        directory = WORK / case["instance_id"]
        directory.mkdir()
        try:
            tree = directory / "tree"
            repo = PREVIOUS / case["repo"].replace("/", "__") / "repo"
            archive(repo, case["base_commit"], tree, timeout=60)
            if any(p.is_symlink() for p in tree.rglob("*")):
                raise ValueError("symlink export refused")
            build = tomllib.loads((tree / "pyproject.toml").read_text())["build-system"]["requires"]
            names = sorted(set(direct_dependencies(tree)) | {
                normalise(Requirement(r).name) for r in build
            } | {"pip", "setuptools", "wheel", "pytest", "numpy"})
            cutoff = datetime.fromisoformat(case["created_at"].replace("Z", "+00:00"))
            pins = []
            for name in names:
                payload = _fetch(name)
                version = latest_before(payload, cutoff) if payload else None
                if version is None:
                    raise ValueError("unresolved era constraint: " + name)
                pins.append(f"{name}<={version}")
            constraints = "\n".join(pins) + "\n"
            (directory / "constraints.txt").write_text(constraints)
            row["constraints_sha256"] = sha256_bytes(constraints.encode())
            version = scm_pretend_version(tree, discover_roots(tree))
            dockerfile = (
                f"FROM {reference}\nCOPY constraints.txt /constraints.txt\n"
                "ENV PIP_CONSTRAINT=/constraints.txt\n"
                "RUN python -m pip install pip setuptools wheel\n"
                "COPY tree /source\nWORKDIR /source\n"
                + (f"ENV SETUPTOOLS_SCM_PRETEND_VERSION={version}\n" if version else "")
                + "RUN python -m pip wheel --no-deps --wheel-dir /wheels .\n"
                "RUN sha256sum /wheels/* > /wheel-digests.txt"
                " && python -m pip freeze > /builder-freeze.txt\n"
            )
            (directory / "Dockerfile").write_text(dockerfile)
            row["dockerfile_sha256"] = sha256_bytes(dockerfile.encode())
            tag = "attest-compatible-wheel-" + case["base_commit"][:12]
            with (directory / "build.log").open("wb") as log:
                result = subprocess.run(
                    ["docker", "build", "--progress=plain", "-t", tag, str(directory)],
                    env=env, stdout=log, stderr=subprocess.STDOUT, timeout=900,
                )
            row["exit_code"] = result.returncode
            row["log_sha256"] = sha256_bytes((directory / "build.log").read_bytes())
            row["status"] = "built" if result.returncode == 0 else "build_failed"
            if result.returncode == 0:
                row["image_id"] = subprocess.check_output(
                    ["docker", "image", "inspect", "--format", "{{.Id}}", tag],
                    env=env, text=True, timeout=30,
                ).strip()
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            row.update(status="refused", reason=str(exc))
        write_canonical_json(WORK / "result.json", record)
        print(row["case"], row["status"], flush=True)
    record["status"] = "complete"
    write_canonical_json(WORK / "result.json", record)


if __name__ == "__main__":
    main()
