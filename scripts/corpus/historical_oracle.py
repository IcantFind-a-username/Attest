"""Try the first frozen development oracle in its recorded historical environment."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
from dataclasses import asdict
from pathlib import Path

from runtime_contract_shadow import archive

from attest.benchmark.artifacts import (
    _atomic_write,
    sha256_bytes,
    validation_junit_counts,
    write_canonical_json,
)
from attest.execution.container_adapter import ContainerAdapter, ContainerImage
from attest.execution.controller import Controller
from attest.execution.types import ResourceLimits

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/repository-holdout-v1"
CORPUS = ROOT / ".attest/corpora/repository-holdout-v1-metadata"
REPO = ROOT / ".attest/corpora/repository-holdout-v1-dev-keras"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    if not work.is_relative_to(ROOT / ".attest/corpora") or work.exists():
        raise ValueError("work must be a fresh directory under .attest/corpora")
    work.mkdir(parents=True)
    frozen = json.loads((STUDY / "frozen-candidates.json").read_text())
    development = [r for r in frozen["repositories"] if r["role"] == "development"]
    if len(development) != 1 or development[0]["project"] != "keras":
        raise ValueError("expected frozen Keras development repository")
    case = development[0]["candidates"][0]
    if case["upstream_case"] != "keras/8" or case["python_version_metadata"] != "3.7.3":
        raise ValueError("preregistered first candidate drift")
    record: dict = {
        "case": case["upstream_case"],
        "status": "started",
        "stages": [],
        "runs": [],
        "attest_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((STUDY / "historical-oracle.md").read_bytes()),
        "model_api_spend_usd": 0,
        "product_evaluations": 0,
        "receipt_eligible": False,
    }
    docker_env = {"PATH": os.environ["PATH"], "HOME": os.environ["HOME"]}
    docker_env["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"], text=True
    ).strip()
    config = work / "docker-config"
    config.mkdir()
    write_canonical_json(config / "config.json", {})
    docker_env["DOCKER_CONFIG"] = str(config)

    def command(label: str, argv: list[str], timeout: int, *, docker: bool = False) -> bytes:
        stage = {"label": label, "argv": argv, "status": "started"}
        record["stages"].append(stage)
        write_canonical_json(work / "result.json", record)
        try:
            result = subprocess.run(
                argv,
                capture_output=True,
                timeout=timeout,
                env=docker_env if docker else None,
            )
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code = exc.stdout or b"", exc.stderr or b"", None
        else:
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        _atomic_write(work, label + ".stdout", stdout)
        _atomic_write(work, label + ".stderr", stderr)
        stage.update(
            status="ok" if code == 0 else "failed",
            exit_code=code,
            stdout_sha256=sha256_bytes(stdout),
            stderr_sha256=sha256_bytes(stderr),
        )
        write_canonical_json(work / "result.json", record)
        if code != 0:
            raise RuntimeError(f"{label} failed (exit {code}); retained logs")
        return stdout

    try:
        folder = str(Path(case["metadata_path"]).parent)
        requirements = command(
            "requirements",
            [
                "git",
                "-C",
                str(CORPUS),
                "show",
                frozen["corpus"]["sha"] + ":" + folder + "/requirements.txt",
            ],
            45,
        )
        oracle = command(
            "oracle",
            [
                "git",
                "-C",
                str(CORPUS),
                "show",
                frozen["corpus"]["sha"] + ":" + folder + "/run_test.sh",
            ],
            45,
        )
        argv = shlex.split(oracle.decode())
        if len(argv) != 2 or argv[0] != "pytest":
            raise ValueError("expected one original pytest node")
        test_path = argv[1].split("::")[0]
        trees = {}
        for side in ("fixed", "buggy"):
            sha = case[side + "_sha"]
            command(
                side + "-fetch", ["git", "-C", str(REPO), "fetch", "--depth=1", "origin", sha], 120
            )
            listing = command(side + "-tree", ["git", "-C", str(REPO), "ls-tree", "-r", sha], 30)
            if any(line.startswith(b"120000 ") for line in listing.splitlines()):
                raise ValueError("symlink in export; archive refused")
            trees[side] = work / side
            archive(REPO, sha, trees[side])
        test = (trees["fixed"] / test_path).read_bytes()
        (trees["buggy"] / test_path).write_bytes(test)
        record.update(
            revisions={s: case[s + "_sha"] for s in trees},
            oracle_path=test_path,
            oracle_sha256=sha256_bytes(test),
            requirements_sha256=sha256_bytes(requirements),
        )
        base_tag = "python:3.7.3-slim"
        command("pull", ["docker", "pull", "--platform", "linux/amd64", base_tag], 180, docker=True)
        info = json.loads(
            command("base-image", ["docker", "image", "inspect", base_tag], 30, docker=True)
        )[0]
        record["base_image"] = {key: info[key] for key in ("Id", "RepoDigests", "Architecture")}
        context = work / "build"
        context.mkdir()
        (context / "requirements.txt").write_bytes(requirements)
        dockerfile = (
            f"FROM --platform=linux/amd64 {info['RepoDigests'][0]}\n"
            "ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1\n"
            "RUN python -m pip install pip==20.1.1 setuptools==46.4.0 wheel==0.34.2\n"
            "COPY requirements.txt /requirements.txt\n"
            "RUN python -m pip install -r /requirements.txt\n"
            "RUN python -m pip check && python -m pip freeze > /environment.txt\n"
        )
        (context / "Dockerfile").write_text(dockerfile)
        tag = "attest-historical:" + sha256_bytes(dockerfile.encode() + requirements)[:16]
        command(
            "build",
            [
                "docker",
                "build",
                "--platform",
                "linux/amd64",
                "-t",
                tag,
                str(context),
            ],
            900,
            docker=True,
        )
        image_info = json.loads(
            command("image", ["docker", "image", "inspect", tag], 30, docker=True)
        )[0]
        image = ContainerImage(image_info["Id"], image_info["Id"], tag)
        record["image"] = asdict(image)
        adapter = ContainerAdapter(image)
        bootstrap = (
            "import os,sys,keras; "
            "assert os.path.realpath(keras.__file__).startswith(os.getcwd()+'/keras/'); "
            "print('source',keras.__file__); import pytest; sys.exit(pytest.main(sys.argv[1:]))"
        )
        for repeat in range(3):
            pair = []
            for side, tree in trees.items():
                label = f"{side}-{repeat}"
                controller = Controller(work / "execution" / label)
                request = controller.issue(
                    task_id="historical-keras-8",
                    run_id=label,
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
                        "PYTHONPATH": "{tree}",
                        "PYTHONDONTWRITEBYTECODE": "1",
                        "OPENBLAS_NUM_THREADS": "1",
                        "OMP_NUM_THREADS": "1",
                        "TF_NUM_INTEROP_THREADS": "1",
                        "TF_NUM_INTRAOP_THREADS": "1",
                    },
                    inputs={},
                    limits=ResourceLimits(120, 120, 2048, 262144),
                    expected_artifacts=("stdout.txt", "stderr.txt", "junit.xml"),
                )
                outcome = controller.dispatch(request, adapter, tree=tree, inputs={})
                counts = validation_junit_counts(outcome.artifacts.get("junit.xml", b""))
                valid = outcome.accepted and outcome.envelope is not None
                code = outcome.envelope.exit_code if outcome.envelope else None
                expected = (1, 0, 0, 0) if side == "fixed" else (1, 1, 0, 0)
                matched = valid and counts == expected and code == (0 if side == "fixed" else 1)
                pair.append(matched)
                record["runs"].append(
                    {
                        "label": label,
                        "protocol_accepted": valid,
                        "envelope": asdict(outcome.envelope) if outcome.envelope else None,
                        "junit_counts": counts,
                        "oracle_pattern_matched": matched,
                    }
                )
                write_canonical_json(work / "result.json", record)
            if not all(pair):
                raise RuntimeError("first non-discriminating pair; no outcome-driven repair")
        record["status"] = "oracle_differential_only_semantic_qualification_pending"
    except (RuntimeError, ValueError, OSError, subprocess.SubprocessError) as exc:
        record.update(status="blocked", reason=str(exc))
    write_canonical_json(work / "result.json", record)
    print(record["status"], record.get("reason", ""))


if __name__ == "__main__":
    main()
