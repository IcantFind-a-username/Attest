"""Free source-mounted qualification using the six recorded compatible wheels."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import asdict
from datetime import datetime
from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

from era_constraints import _fetch, latest_before, normalise
from heldout_v2 import stub_packages
from packaging.markers import default_environment
from packaging.requirements import Requirement
from runtime_contract_shadow import archive
from wheel_overlay import apply_wheel

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json
from attest.execution.container_adapter import ContainerAdapter, ContainerImage
from attest.execution.container_images import declared_version_file, discover_roots
from attest.review.candidates import StoredCandidate
from attest.review.executor import ExecutionOutcome, ExecutorLimits, ReproSpec, execute_repro
from attest.review.schema import Finding

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/swebench-independent-v1"
BUILDS = ROOT / ".attest/corpora/swebench-compatible-build"
PREVIOUS = ROOT / ".attest/corpora/swebench-independent-runtime"
WORK = ROOT / ".attest/corpora/swebench-source-runtime-r3"


def constraints(wheel: Path, cutoff: str) -> tuple[str, str]:
    with ZipFile(wheel) as z:
        names = [n for n in z.namelist() if n.endswith(".dist-info/METADATA")]
        if len(names) != 1:
            raise ValueError("wheel metadata identity ambiguous")
        metadata = Parser().parsestr(z.read(names[0]).decode())
    extras = sorted(set(metadata.get_all("Provides-Extra", [])) & {"test", "tests"})
    environment = {
        **default_environment(), "python_version": "3.10", "python_full_version": "3.10.0",
        "sys_platform": "linux", "platform_system": "Linux", "platform_machine": "aarch64",
        "implementation_name": "cpython", "platform_python_implementation": "CPython",
    }
    packages = {"pip", "pytest", "setuptools", "wheel"}
    for value in metadata.get_all("Requires-Dist", []):
        requirement = Requirement(value)
        if requirement.marker is None or any(
            requirement.marker.evaluate({**environment, "extra": extra}) for extra in ["", *extras]
        ):
            packages.add(normalise(requirement.name))
    pins = []
    timestamp = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
    for name in sorted(packages):
        payload = _fetch(name)
        version = latest_before(payload, timestamp) if payload else None
        if version is None:
            raise ValueError("unresolved runtime constraint: " + name)
        pins.append(f"{name}<={version}")
    return "\n".join(pins) + "\n", "[" + ",".join(extras) + "]" if extras else ""


def build(
    directory: Path, dockerfile: str, tag: str, env: dict[str, str], *, label: str = "runtime",
) -> str:
    path = directory / f"{label}.Dockerfile"
    path.write_text(dockerfile)
    with (directory / f"{label}-build.log").open("wb") as log:
        subprocess.run(
            ["docker", "build", "--progress=plain", "-f", str(path), "-t", tag, str(directory)],
            env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=600,
        )
    return subprocess.check_output(
        ["docker", "image", "inspect", "--format", "{{.Id}}", tag],
        env=env, text=True, timeout=30,
    ).strip()


def check_runtime(
    directory: Path, tree: Path, wheel: Path, revision: str, wheel_digest: str,
    expected_revision: str, cutoff: str, runtime: str, env: dict[str, str], state: dict, *,
    builder: str, fixture: bool = False,
) -> dict:
    state["stage"] = "transfer"
    packages = tuple(stub_packages(tree))
    if not packages:
        raise ValueError("empty package set")
    version_file = declared_version_file(tree, discover_roots(tree))
    transfer = apply_wheel(
        tree, wheel, revision=revision, expected_revision=expected_revision,
        expected_digest=wheel_digest, packages=packages,
        version_path=version_file.relative_to(tree).as_posix() if version_file else None,
    )
    if not any(n.endswith(".so") for n in transfer["added"]):
        raise ValueError("no native artifact witnessed")
    write_canonical_json(directory / "transfer.json", transfer)
    state["stage"] = "constraints"
    pins, extras = constraints(wheel, cutoff)
    (directory / "constraints.txt").write_text(pins)
    shutil.copyfile(wheel, directory / wheel.name)
    dockerfile = (
        f"FROM {builder} AS dependencies\n"
        "COPY constraints.txt /constraints.txt\nENV PIP_CONSTRAINT=/constraints.txt\n"
        f"COPY {wheel.name} /wheel/{wheel.name}\n"
        "RUN python -m pip wheel --wheel-dir /wheelhouse pip pytest"
        f" '/wheel/{wheel.name}{extras}'\n"
        f"FROM {runtime}\n"
        "RUN apt-get update && apt-get install -y --no-install-recommends libgomp1"
        " && rm -rf /var/lib/apt/lists/*\n"
        "COPY constraints.txt /constraints.txt\nENV PIP_CONSTRAINT=/constraints.txt\n"
        "COPY --from=dependencies /wheelhouse /wheelhouse\n"
        "RUN python -m pip install --no-index --find-links /wheelhouse"
        f" pip pytest '/wheelhouse/{wheel.name}{extras}'\n"
        "RUN python -m pip freeze > /runtime-freeze.txt\n"
    )
    state["stage"] = "runtime_image"
    image = build(directory, dockerfile, "attest-source-runtime-" + revision[:12], env)
    container = subprocess.check_output(
        ["docker", "create", image], env=env, text=True, timeout=30,
    ).strip()
    try:
        subprocess.run(
            ["docker", "cp", f"{container}:/runtime-freeze.txt",
             str(directory / "runtime-freeze.txt")],
            env=env, check=True, timeout=30,
        )
    finally:
        subprocess.run(
            ["docker", "rm", container], env=env, check=True, capture_output=True, timeout=30,
        )
    imports = "".join(f"import {name}\n" for name in packages)
    assertions = "".join(
        f"    assert {name}.__file__.startswith('/attest/tree/')\n" for name in packages
    )
    if fixture:
        imports += "import native_fixture._native\n"
        assertions += "    assert native_fixture._native.answer() == 7\n"
    source = imports + "\ndef test_runtime_source():\n" + assertions
    anchor = packages[0] + "/__init__.py"
    candidate = StoredCandidate(
        task_id="source-runtime-" + revision[:12],
        finding=Finding(
            file=anchor, line=1, claim="source-mounted runtime diagnostic",
            failure_scenario="native source package may fail to import",
            falsification_plan="execute the frozen source-origin import test",
        ), wealth=0.0, action="drawer", alpha=0.1,
    )
    state["stage"] = "execute"
    execution = execute_repro(
        directory, candidate, ReproSpec(source), ExecutorLimits(60, 60, 1024, 16384),
        tree=tree, run_label="runtime", revision_sha=revision,
        adapter=ContainerAdapter(ContainerImage(reference=image, digest=image)),
    )
    return {
        "image": image, "transfer": transfer, "execution": asdict(execution),
        "runtime_ready": execution.exit_code == 0 and execution.collected_count == 1
        and execution.skipped_count == 0 and execution.xfailed_count == 0
        and execution.network_blocked and execution.outcome is ExecutionOutcome.NOT_REPRODUCED,
    }


def check_fixture(build_record: dict, runtime: str, env: dict[str, str], state: dict) -> dict:
    state["stage"] = "fixture_build"
    fixture = WORK / "fixture"
    fixture.mkdir()
    tree = fixture / "tree"
    shutil.copytree(STUDY / "native-fixture", tree)
    fixture_image = build(
        fixture, f"FROM {build_record['builder_reference']}\nCOPY tree /source\n"
        "RUN python -m pip install setuptools==67.1.0 wheel==0.38.4\n"
        "WORKDIR /source\nRUN python setup.py bdist_wheel -d /wheels\n",
        "attest-source-runtime-fixture-builder", env, label="fixture",
    )
    container = subprocess.check_output(
        ["docker", "create", fixture_image], env=env, text=True, timeout=30,
    ).strip()
    try:
        subprocess.run(["docker", "cp", f"{container}:/wheels", str(fixture / "wheels")],
                       env=env, check=True, timeout=30)
    finally:
        subprocess.run(
            ["docker", "rm", container], env=env, check=True, capture_output=True, timeout=30,
        )
    wheels = list((fixture / "wheels").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("fixture wheel count")
    return check_runtime(
        fixture, tree, wheels[0], "f" * 40, sha256_bytes(wheels[0].read_bytes()), "f" * 40,
        "2022-05-09T14:16:30Z", runtime, env, state,
        builder=build_record["builder_reference"], fixture=True,
    )


def main() -> None:
    if WORK.exists():
        raise ValueError("fresh output directory required")
    WORK.mkdir()
    os.environ["TMPDIR"] = str(WORK)
    env = {**os.environ, "DOCKER_CONFIG": str(PREVIOUS / "docker-config")}
    env["DOCKER_HOST"] = subprocess.check_output(
        ["docker", "context", "inspect", "--format", "{{.Endpoints.docker.Host}}"],
        text=True, timeout=30,
    ).strip()
    build_record = json.loads((BUILDS / "result.json").read_text())
    if (BUILDS / "result.json").read_bytes() != (
        STUDY / "compatible-build-evidence/result.json"
    ).read_bytes():
        raise ValueError("build record differs from committed evidence")
    frozen = json.loads((STUDY / "frozen-candidates.json").read_text())
    cases = [c for r in frozen["repositories"] for c in r["selected"]]
    if (
        len(cases) != 6 or len(build_record["rows"]) != 6
        or {r["case"] for r in build_record["rows"]} != {c["instance_id"] for c in cases}
        or any(r["status"] != "built" for r in build_record["rows"])
    ):
        raise ValueError("build population is incomplete")
    subprocess.run(
        ["docker", "pull", "python:3.10-slim-bookworm"], env=env, check=True, timeout=300,
    )
    runtime = json.loads(subprocess.check_output(
        ["docker", "image", "inspect", "python:3.10-slim-bookworm"], env=env, timeout=30,
    ))[0]["RepoDigests"][0]
    record = {
        "status": "started", "rows": [
            {"case": c["instance_id"], "revision": c["base_commit"],
             "status": "not_run", "stage": "prepare", "runtime_ready": False} for c in cases
        ], "model_api_spend_usd": 0,
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "overlay_sha256": sha256_bytes((ROOT / "scripts/corpus/wheel_overlay.py").read_bytes()),
        "protocol_sha256": sha256_bytes((STUDY / "source-runtime.md").read_bytes()),
        "build_record_sha256": sha256_bytes((BUILDS / "result.json").read_bytes()),
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "runtime_reference": runtime, "qualified_defects": 0, "qualified_controls": 0,
    }
    write_canonical_json(WORK / "result.json", record)
    record["fixture"] = {"status": "started"}
    try:
        record["fixture"].update(check_fixture(build_record, runtime, env, record["fixture"]))
        record["fixture"]["status"] = "checked"
        if not record["fixture"]["runtime_ready"]:
            raise ValueError("generic fixture runtime refused; no corpus execution")
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, TypeError) as exc:
        record["fixture"].update(status="refused", reason=str(exc))
        record["status"] = "fixture_failed"
        write_canonical_json(WORK / "result.json", record)
        return
    for case, row in zip(cases, record["rows"], strict=True):
        row["status"] = "started"
        write_canonical_json(WORK / "result.json", record)
        directory = WORK / case["instance_id"]
        directory.mkdir()
        try:
            prior = next(r for r in build_record["rows"] if r["case"] == case["instance_id"])
            wheels = list((BUILDS / case["instance_id"] / "wheels").glob("*.whl"))
            if len(wheels) != 1:
                raise ValueError("wheel count")
            wheel = wheels[0]
            tree = directory / "tree"
            repo = PREVIOUS / case["repo"].replace("/", "__") / "repo"
            archive(repo, case["base_commit"], tree, timeout=60)
            row.update(check_runtime(
                directory, tree, wheel, case["base_commit"],
                prior["artifacts"]["wheels/" + wheel.name], prior["revision"],
                case["created_at"], runtime, env, row, builder=build_record["builder_reference"],
            ))
            row["status"] = "checked"
        except (
            ValueError, OSError, subprocess.SubprocessError, KeyError, StopIteration, TypeError,
        ) as exc:
            row.update(status="refused", reason=str(exc), runtime_ready=False)
        write_canonical_json(WORK / "result.json", record)
        print(row["case"], row["status"], row.get("runtime_ready"), flush=True)
    record["status"] = "complete"
    write_canonical_json(WORK / "result.json", record)


if __name__ == "__main__":
    main()
