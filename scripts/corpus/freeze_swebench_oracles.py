"""Freeze original hidden oracle inputs only for runtime-qualified frozen rows."""

from __future__ import annotations

import json
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

import pyarrow.parquet as pq

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/swebench-independent-v1"
RUNTIME = ROOT / ".attest/corpora/swebench-source-runtime-r3/result.json"
PARQUET = ROOT / ".attest/corpora/swebench-independent-v1-metadata/pinned-data.parquet"
WORK = ROOT / ".attest/corpora/swebench-oracle-inputs"
COLUMNS = [
    "instance_id", "repo", "base_commit", "patch", "test_patch", "FAIL_TO_PASS", "PASS_TO_PASS",
]


def main() -> None:
    if WORK.exists():
        raise ValueError("fresh oracle directory required")
    frozen = json.loads((STUDY / "frozen-candidates.json").read_bytes())
    cases = {c["instance_id"]: c for r in frozen["repositories"] for c in r["selected"]}
    runtime_bytes = RUNTIME.read_bytes()
    runtime = json.loads(runtime_bytes)
    rows = runtime["rows"]
    if (
        runtime["status"] != "complete" or len(rows) != 6 or len(cases) != 6
        or {r["case"] for r in rows} != set(cases)
        or any(r["revision"] != cases[r["case"]]["base_commit"] for r in rows)
    ):
        raise ValueError("runtime population mismatch")
    selected = [r["case"] for r in rows if r["runtime_ready"] is True]
    if not selected:
        raise ValueError("no runtime-qualified input")
    digest = sha256_bytes(PARQUET.read_bytes())
    pinned = json.loads((STUDY / "pinned-metadata-check.json").read_bytes())
    if digest != pinned["parquet_sha256"]:
        raise ValueError("immutable dataset digest mismatch")
    original = pq.read_table(
        PARQUET, columns=COLUMNS, filters=[("instance_id", "in", selected)],
    ).to_pylist()
    if len(original) != len(selected) or {r["instance_id"] for r in original} != set(selected):
        raise ValueError("oracle projection mismatch")
    WORK.mkdir(mode=0o700)
    manifest = {
        "status": "frozen", "qualified_defects": 0, "qualified_controls": 0,
        "model_api_spend_usd": 0, "runtime_record_sha256": sha256_bytes(runtime_bytes),
        "parquet_sha256": digest, "columns_read": COLUMNS,
        "python": sys.version, "pyarrow_version": version("pyarrow"),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((STUDY / "oracle-inputs.md").read_bytes()),
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "not_accessed": sorted(set(cases) - set(selected)), "rows": [],
    }
    for row in sorted(original, key=lambda r: r["instance_id"]):
        label = row["instance_id"]
        case = cases[label]
        if row["repo"] != case["repo"] or row["base_commit"] != case["base_commit"]:
            raise ValueError("oracle identity drift")
        for field in ("patch", "test_patch"):
            if not isinstance(row[field], str) or not row[field].strip():
                raise ValueError("empty original patch")
        nodes = {}
        for field in ("FAIL_TO_PASS", "PASS_TO_PASS"):
            value = row[field]
            value = json.loads(value) if isinstance(value, str) else value
            if not isinstance(value, list) or not all(isinstance(n, str) and n for n in value):
                raise ValueError("malformed original nodes")
            if len(value) != len(set(value)):
                raise ValueError("duplicate original nodes")
            nodes[field] = len(value)
        if not nodes["FAIL_TO_PASS"]:
            raise ValueError("empty failure oracle")
        path = WORK / (label + ".json")
        write_canonical_json(path, row)
        path.chmod(0o600)
        manifest["rows"].append({
            "case": label, "base_commit": row["base_commit"], "nodes": nodes,
            "oracle_input_sha256": sha256_bytes(path.read_bytes()),
        })
    write_canonical_json(WORK / "manifest.json", manifest)
    print("Original oracle inputs frozen; no project execution or model call.")


if __name__ == "__main__":
    main()
