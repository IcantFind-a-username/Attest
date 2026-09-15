"""Freeze the separately authorized SWE-bench metadata stratum before source access."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json  # noqa: E402

STUDY = ROOT / "benchmarks/studies/swebench-independent-v1"
WORK = ROOT / ".attest/corpora/swebench-independent-v1-metadata"
BASELINE = "4697d98f28cbfd539e321988ff3271af070871c1"
DATASET = "princeton-nlp/SWE-bench_Verified"
ELIGIBLE = ("astropy/astropy", "scikit-learn/scikit-learn")
FIELDS = ("instance_id", "repo", "base_commit", "created_at", "version")


def main() -> None:
    if WORK.exists():
        raise ValueError("fresh metadata directory required")
    WORK.mkdir(parents=True)
    split_path = ROOT / "benchmarks/attest-v2/splits/swebench-verified-v1.json"
    split = json.loads(split_path.read_bytes())
    all_ids = set(split["dev"] + split["held_out"])
    assert len(all_ids) == 500 and not set(split["dev"]) & set(split["held_out"])
    record: dict = {
        "status": "started",
        "baseline": BASELINE,
        "pages": [],
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((STUDY / "protocol.md").read_bytes()),
        "old_split_sha256": sha256_bytes(split_path.read_bytes()),
        "dataset": DATASET,
        "actual_model_api_spend_usd": 0,
    }
    write_canonical_json(WORK / "access.json", record)
    url = "https://huggingface.co/api/datasets/" + DATASET
    with urllib.request.urlopen(url, timeout=90) as response:
        before_bytes = response.read()
    before = json.loads(before_bytes)
    record["dataset_revision_before"] = before["sha"]
    record["revision_metadata_sha256"] = sha256_bytes(before_bytes)
    rows = []
    for offset in range(0, 500, 100):
        page_url = (
            "https://datasets-server.huggingface.co/rows"
            "?dataset=princeton-nlp%2FSWE-bench_Verified&config=default&split=test"
            f"&offset={offset}&length=100"
        )
        with urllib.request.urlopen(page_url, timeout=120) as response:
            raw = response.read()
        page = json.loads(raw)
        if page["num_rows_total"] != 500 or len(page["rows"]) != 100:
            raise ValueError("unexpected corpus page size")
        rows.extend({field: item["row"][field] for field in FIELDS} for item in page["rows"])
        record["pages"].append({"offset": offset, "raw_response_sha256": sha256_bytes(raw)})
        write_canonical_json(WORK / "access.json", record)
    with urllib.request.urlopen(url, timeout=90) as response:
        after = json.loads(response.read())
    if after["sha"] != before["sha"]:
        raise ValueError("dataset head drift during pagination")
    if len({r["instance_id"] for r in rows}) != 500 or {r["instance_id"] for r in rows} != all_ids:
        raise ValueError("dataset identity drift from frozen split")
    if not all(re.fullmatch(r"[0-9a-f]{40}", r["base_commit"]) for r in rows):
        raise ValueError("invalid base revision")
    write_canonical_json(WORK / "metadata.json", rows)
    repositories = []
    for repo in sorted({r["repo"] for r in rows}):
        aliases = sorted({repo, repo.replace("/", "__"), repo.split("/")[1]})
        audit = {}
        for alias in aliases:
            result = subprocess.run(
                [
                    "git",
                    "grep",
                    "-ilF",
                    alias,
                    BASELINE,
                    "--",
                    "docs",
                    "benchmarks",
                    "scripts",
                    "DECISIONS.md",
                ],
                text=True,
                capture_output=True,
                check=False,
                timeout=30,
            )
            if result.returncode not in (0, 1):
                raise ValueError("audit search failed")
            audit[alias] = result.stdout.splitlines()
        pool = [
            r
            for r in rows
            if r["repo"] == repo
            and r["instance_id"] in split["held_out"]
            and r["created_at"] >= "2022-01-01"
        ]
        pool.sort(
            key=lambda r: sha256_bytes(
                ("attest-swebench-independent-v1|" + r["instance_id"]).encode()
            )
        )
        repositories.append(
            {
                "repo": repo,
                "audit_eligible_pending_review": repo in ELIGIBLE,
                "audit_references": audit,
                "contemporary_heldout_count": len(pool),
                "selected": pool[:3] if repo in ELIGIBLE else [],
                "reason": "administrative exclusions only; independently review aliases before source access"
                if repo in ELIGIBLE
                else "prior substantive/uncertain exposure; not selected",
            }
        )
    selected = [r for repo in repositories for r in repo["selected"]]
    record.update(
        status="metadata_frozen_pending_independent_audit",
        selected_count=len(selected),
        dataset_revision_after=after["sha"],
        metadata_sha256=sha256_bytes((WORK / "metadata.json").read_bytes()),
        source_access=False,
    )
    write_canonical_json(WORK / "access.json", record)
    write_canonical_json(STUDY / "metadata-access.json", record)
    write_canonical_json(
        STUDY / "frozen-candidates.json", {"record": record, "repositories": repositories}
    )
    print("selected", [r["instance_id"] for r in selected], flush=True)


if __name__ == "__main__":
    main()
