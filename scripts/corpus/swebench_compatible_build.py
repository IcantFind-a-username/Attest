"""One uniform, free wheel-build attempt for each frozen SWE-bench candidate."""

from __future__ import annotations

import argparse
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



def natural_cases(population: dict, study: Path) -> list[dict]:
    """Admit only complete, ordered entries derived from reviewed immutable inputs."""
    pairs_bytes = (study / "qualification-candidates.json").read_bytes()
    if population["qualification_sha256"] != sha256_bytes(pairs_bytes):
        raise ValueError("natural-pair qualification drift")
    qualification = json.loads(pairs_bytes)
    freeze_bytes = (study / "freeze.json").read_bytes()
    if qualification["freeze_sha256"] != sha256_bytes(freeze_bytes):
        raise ValueError("natural-pair freeze drift")
    selected = {c["instance_id"]: c for c in json.loads(freeze_bytes)["selected"]}
    expected = []
    for pair in qualification["pairs"]:
        source = selected[pair["case"]]
        if pair["repo"] != source["repo"]:
            raise ValueError("natural-pair repository drift")
        for side in ("parent", "head"):
            expected.append({
                "instance_id": pair["case"] + "-" + side,
                "source_case": pair["case"], "side": side,
                "base_commit": pair[side + "_sha"], "repo": pair["repo"],
                "created_at": source["created_at"],
            })
    if population["cases"] != expected:
        raise ValueError("natural-pair identity, order or cutoff drift")
    return expected


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study",
                        choices=("swebench", "natural-pairs", "remainder-pairs",
                                 "remainder-safe-links"),
                        default="swebench")
    args = parser.parse_args()
    safe_links = args.study == "remainder-safe-links"
    remainder = args.study in {"remainder-pairs", "remainder-safe-links"}
    natural = remainder or args.study == "natural-pairs"
    study = ROOT / "benchmarks/studies/metadata-exposed-v1/compatibility" if natural else STUDY
    work = ROOT / ".attest/corpora/natural-pair-compatible-build" if natural else WORK
    previous = ROOT / ".attest/corpora/metadata-exposed-runtime" if natural else PREVIOUS
    repo_base = ROOT / ".attest/corpora/metadata-exposed-v1" if natural else PREVIOUS
    if remainder:
        study = ROOT / "benchmarks/studies/remainder-v1/compatibility"
        work = ROOT / ".attest/corpora" / (
            "remainder-safe-link-build" if safe_links else "remainder-pair-compatible-build"
        )
    if work.exists():
        raise ValueError("fresh output directory required; no retry or overwrite")
    work.mkdir()
    env = {**os.environ, "DOCKER_CONFIG": str(previous / "docker-config")}
    env["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True, timeout=30,
    ).strip()
    frozen = (study / ("cases.json" if natural else "frozen-candidates.json")).read_bytes()
    population = json.loads(frozen)
    if natural:
        cases = natural_cases(population, study.parent)
    else:
        cases = [c for r in population["repositories"] for c in r["selected"]]
    if (not cases or (not remainder and (
        len(cases) != (4 if natural else 6) or len({c["repo"] for c in cases}) != 2
    ))):
        raise ValueError("population drift")
    record: dict = {
        "status": "started", "rows": [], "model_api_spend_usd": 0,
        "population_sha256": sha256_bytes(frozen),
        "protocol_sha256": sha256_bytes((study / (
            "safe-link-runtime.md" if safe_links else "compatible-runtime.md"
        )).read_bytes()),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "archive_helper_sha256": sha256_bytes(
            (ROOT / "scripts/corpus/runtime_contract_shadow.py").read_bytes()
        ),
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "qualified_defects": 0, "qualified_controls": 0,
    }
    write_canonical_json(work / "result.json", record)
    builder = (
        "python@sha256:94c362db08c5b38857943d31b10558ff1856e918605c474d205d72a534929d4e"
        if remainder else "python:3.10-bookworm"
    )
    subprocess.run(["docker", "pull", builder], env=env, check=True, timeout=300)
    base = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", builder], env=env, timeout=30,
    ))[0]
    reference = base["RepoDigests"][0]
    record["builder_reference"] = reference
    record["builder_id"] = base["Id"]
    for case in cases:
        row = {"case": case["instance_id"], "revision": case["base_commit"], "status": "started"}
        record["rows"].append(row)
        write_canonical_json(work / "result.json", record)
        directory = work / case["instance_id"]
        directory.mkdir()
        try:
            tree = directory / "tree"
            repo = repo_base / case["repo"].replace("/", "__") / "repo"
            listing = subprocess.check_output(
                ["git", "-C", str(repo), "ls-tree", "-r", case["base_commit"]], timeout=30,
            )
            if not safe_links and any(line.startswith(b"120000 ") for line in listing.splitlines()):
                raise ValueError("symlink export refused before extraction")
            archive(repo, case["base_commit"], tree, timeout=60)
            if not safe_links and any(p.is_symlink() for p in tree.rglob("*")):
                raise ValueError("symlink export refused")
            pyproject = tree / "pyproject.toml"
            if remainder:
                metadata = tomllib.loads(pyproject.read_text()) if pyproject.exists() else {}
                build = metadata.get("build-system", {}).get("requires", [])
                row["declared_build_requirements"] = build
                row["implicit_backend"] = not bool(build)
            else:
                build = tomllib.loads(pyproject.read_text())["build-system"]["requires"]
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
                + "RUN python -m pip wheel --no-clean --verbose --no-deps --wheel-dir /wheels .\n"
                "RUN sha256sum /wheels/* > /wheel-digests.txt"
                " && python -m pip freeze > /builder-freeze.txt\n"
                + (
                    "RUN find /tmp -path '/tmp/pip-build-env-*/*.dist-info/METADATA' -print"
                    " > /isolated-metadata-paths.txt"
                    + (" && test -s /isolated-metadata-paths.txt" if build else "")
                    + " && tar -cf /isolated-build-metadata.tar -T /isolated-metadata-paths.txt\n"
                    if remainder else
                    "RUN find /tmp/pip-build-env-* -path '*.dist-info/METADATA' -print"
                    " > /isolated-metadata-paths.txt && test -s /isolated-metadata-paths.txt"
                    " && tar -cf /isolated-build-metadata.tar -T /isolated-metadata-paths.txt\n"
                )
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
                container = subprocess.check_output(
                    ["docker", "create", row["image_id"]], env=env, text=True, timeout=30,
                ).strip()
                try:
                    for filename in (
                        "wheels", "wheel-digests.txt", "builder-freeze.txt",
                        "isolated-build-metadata.tar",
                    ):
                        subprocess.run(
                            ["docker", "cp", f"{container}:/{filename}", str(directory / filename)],
                            env=env, check=True, timeout=60,
                        )
                    row["artifacts"] = {
                        p.relative_to(directory).as_posix(): sha256_bytes(p.read_bytes())
                        for p in sorted(directory.rglob("*"))
                        if p.is_file() and "tree" not in p.relative_to(directory).parts
                    }
                finally:
                    subprocess.run(
                        ["docker", "rm", container], env=env, check=True, timeout=30,
                        stdout=subprocess.DEVNULL,
                    )
        except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as exc:
            row.update(status="refused", reason=str(exc))
        write_canonical_json(work / "result.json", record)
        print(row["case"], row["status"], flush=True)
    record["status"] = "complete"
    write_canonical_json(work / "result.json", record)


if __name__ == "__main__":
    main()
