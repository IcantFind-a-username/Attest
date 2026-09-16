"""Validate fresh safe exports of the unchanged frozen natural revision population."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from runtime_contract_shadow import archive
from swebench_compatible_build import natural_cases

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/remainder-v1"
WORK = ROOT / ".attest/corpora/remainder-safe-export"


def main() -> None:
    population = (STUDY / "compatibility/cases.json").read_bytes()
    cases = natural_cases(json.loads(population), STUDY)
    if not cases or WORK.exists():
        raise ValueError("nonempty frozen population and fresh output required")
    WORK.mkdir(mode=0o700)
    record = {
        "status": "started",
        "rows": [],
        "model_api_spend_usd": 0,
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "population_sha256": sha256_bytes(population),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "archive_helper_sha256": sha256_bytes(
            (ROOT / "scripts/corpus/runtime_contract_shadow.py").read_bytes()
        ),
        "protocol_sha256": sha256_bytes(
            (STUDY / "compatibility/safe-link-runtime.md").read_bytes()
        ),
    }
    for case in cases:
        repo = (
            ROOT / ".attest/corpora/metadata-exposed-v1" / case["repo"].replace("/", "__") / "repo"
        )
        tree = WORK / case["instance_id"]
        row = {"case": case["instance_id"], "revision": case["base_commit"]}
        record["rows"].append(row)
        write_canonical_json(WORK / "result.json", record)
        try:
            archive(repo, case["base_commit"], tree, timeout=120)
            links = {
                p.relative_to(tree).as_posix(): os.readlink(p)
                for p in sorted(tree.rglob("*"))
                if p.is_symlink()
            }
            for name, target in links.items():
                original = subprocess.check_output(
                    [
                        "git",
                        "-c",
                        "gc.auto=0",
                        "-C",
                        str(repo),
                        "show",
                        case["base_commit"] + ":" + name,
                    ],
                    timeout=30,
                )
                if original != os.fsencode(target) or not (tree / name).resolve(
                    strict=True
                ).is_relative_to(tree):
                    raise ValueError("exported link differs from original or leaves tree")
            row.update(status="exported", links=links)
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            row.update(status="refused", reason=str(exc))
        write_canonical_json(WORK / "result.json", record)
        print(row["case"], row["status"], flush=True)
    record["status"] = "complete"
    write_canonical_json(WORK / "result.json", record)


if __name__ == "__main__":
    main()
