"""Census frozen development environments without executing project code or models."""

from __future__ import annotations

import argparse
import json
import platform
import shlex
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

from packaging.requirements import Requirement
from packaging.tags import cpython_tags
from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.benchmark.artifacts import (  # noqa: E402
    _atomic_write,
    sha256_bytes,
    write_canonical_json,
)
from attest.execution.container_images import AVAILABLE_PYTHONS  # noqa: E402

STUDY = ROOT / "benchmarks/studies/repository-holdout-v1"
CORPUS = ROOT / ".attest/corpora/repository-holdout-v1-metadata"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT) or output.exists():
        raise ValueError("output must be a fresh directory inside this repository")
    output.mkdir(parents=True)
    manifest = json.loads((STUDY / "frozen-candidates.json").read_text())
    repositories = [r for r in manifest["repositories"] if r["role"] == "development"]
    if len(repositories) != 1 or repositories[0]["project"] != "keras":
        raise ValueError("this preregistered preflight covers only the frozen Keras slice")
    candidates = repositories[0]["candidates"]
    if len(candidates) != 5:
        raise ValueError("expected all five development candidates")
    records: list[dict[str, object]] = []
    versions: set[str] = set()
    for candidate in candidates:
        folder = str(Path(candidate["metadata_path"]).parent)
        inputs: dict[str, bytes] = {}
        for name in ("bug.info", "requirements.txt", "run_test.sh"):
            inputs[name] = subprocess.check_output(
                [
                    "git",
                    "-C",
                    str(CORPUS),
                    "show",
                    manifest["corpus"]["sha"] + ":" + folder + "/" + name,
                ],
                timeout=45,
            )
        if sha256_bytes(inputs["bug.info"]) != candidate["metadata_sha256"]:
            raise ValueError("frozen bug metadata digest drift")
        pins = []
        for line in inputs["requirements.txt"].decode().splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            requirement = Requirement(line)
            if requirement.name.lower() == "tensorflow":
                specs = list(requirement.specifier)
                if len(specs) != 1 or specs[0].operator != "==" or requirement.marker:
                    raise ValueError("TensorFlow pin must be exact and unconditional")
                pins.append(specs[0].version)
        if len(pins) != 1:
            raise ValueError("expected one exact TensorFlow requirement")
        versions.add(pins[0])
        python = candidate["python_version_metadata"]
        minor = ".".join(python.split(".")[:2])
        command = inputs["run_test.sh"].decode().strip()
        argv = shlex.split(command)
        if "\n" in command or not argv or argv[0] != "pytest":
            raise ValueError("unexpected development oracle command; nothing executed")
        records.append(
            {
                "case": candidate["upstream_case"],
                "role": "development",
                "python_recorded": python,
                "python_minor_supported": minor in AVAILABLE_PYTHONS,
                "tensorflow_pin": pins[0],
                "oracle_argv_not_executed": argv,
                "inputs": {folder + "/" + name: sha256_bytes(raw) for name, raw in inputs.items()},
                "environment_group": python + ":" + sha256_bytes(inputs["requirements.txt"]),
                "paired_execution": "not_attempted",
                "qualified_defect": False,
            }
        )
    releases: list[dict[str, object]] = []
    for version in sorted(versions):
        url = f"https://pypi.org/pypi/tensorflow/{version}/json"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                raw = response.read()
            response_file = f"tensorflow-{version}-pypi.json"
            _atomic_write(output, response_file, raw)
            payload = json.loads(raw)
            files = payload["urls"]
            if not files or payload["info"]["version"] != version:
                raise ValueError("empty or mismatched PyPI release")
            distributions = [
                {
                    key: item[key]
                    for key in ("filename", "packagetype", "digests", "requires_python", "yanked")
                }
                for item in files
            ]
            matching = {}
            for python in AVAILABLE_PYTHONS:
                tags = set(
                    cpython_tags(
                        tuple(map(int, python.split("."))),
                        platforms=[
                            "manylinux1_x86_64",
                            "manylinux2010_x86_64",
                            "manylinux2014_x86_64",
                            "manylinux2014_aarch64",
                            "linux_x86_64",
                            "linux_aarch64",
                        ],
                    )
                )
                matching[python] = [
                    item["filename"]
                    for item in distributions
                    if item["packagetype"] == "bdist_wheel"
                    and parse_wheel_filename(item["filename"])[3] & tags
                ]
            releases.append(
                {
                    "url": url,
                    "response_file": response_file,
                    "response_sha256": sha256_bytes(raw),
                    "version": version,
                    "distributions": distributions,
                    "matching_linux_wheels": matching,
                    "source_distributions": [
                        i["filename"] for i in distributions if i["packagetype"] == "sdist"
                    ],
                    "status": "metadata_observed",
                }
            )
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as exc:
            releases.append(
                {"url": url, "version": version, "status": "unknown", "error": type(exc).__name__}
            )
    record = {
        "schema": "attest.development-environment-preflight.v1",
        "observed_utc": datetime.now(UTC).isoformat(),
        "host_python": platform.python_version(),
        "attest_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "script_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((STUDY / "development-preflight.md").read_bytes()),
        "frozen_manifest_sha256": sha256_bytes((STUDY / "frozen-candidates.json").read_bytes()),
        "corpus_sha": manifest["corpus"]["sha"],
        "supported_pythons": AVAILABLE_PYTHONS,
        "cases": records,
        "releases": releases,
        "candidate_count": len(records),
        "unsupported_recorded_interpreters": sum(not r["python_minor_supported"] for r in records),
        "environment_group_count": len({r["environment_group"] for r in records}),
        "release_metadata_errors": sum(r["status"] == "unknown" for r in releases),
        "project_executions": 0,
        "product_evaluations": 0,
        "model_api_spend_usd": 0,
        "held_out_inputs_read": False,
        "interpretation": (
            "Metadata prerequisite only. Unsupported recorded Python is a fidelity blocker, "
            "not proof every port is impossible or a product miss. "
            "Wheel matching alone does not qualify a runnable environment."
        ),
    }
    write_canonical_json(output / "preflight.json", record)
    print(
        f"{len(records)} development candidates; "
        f"{record['unsupported_recorded_interpreters']} "
        "recorded interpreters outside product matrix; "
        f"{record['release_metadata_errors']} release metadata errors"
    )


if __name__ == "__main__":
    main()
