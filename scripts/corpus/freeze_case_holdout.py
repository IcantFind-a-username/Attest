"""Audit and freeze unused cases without reading further project or gold source."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "2a15d6b9354b61b028b0799cdaa6158936fbdc36"
STUDY = ROOT / "benchmarks/studies/case-holdout-v1"
OLD = ROOT / "benchmarks/studies/swebench-independent-v1"
METADATA = ROOT / ".attest/corpora/swebench-independent-v1-metadata"
SPLIT = "benchmarks/attest-v2/splits/swebench-verified-v1.json"
SEED = "attest-case-holdout-v1|"
WORK_DIRS = (
    "context-work", "repository-freeze-work", "runtime-parameter-work",
    "runtime-shadow-work", "presentation-baseline",
)


def main() -> None:
    destination = STUDY / "freeze.json"
    if destination.exists():
        raise ValueError("freeze already exists")
    access = json.loads((OLD / "metadata-access.json").read_bytes())
    pinned = json.loads((OLD / "pinned-metadata-check.json").read_bytes())
    metadata_bytes = (METADATA / "metadata.json").read_bytes()
    split_bytes = (ROOT / SPLIT).read_bytes()
    if (
        sha256_bytes(metadata_bytes) != access["metadata_sha256"]
        or sha256_bytes(split_bytes) != access["old_split_sha256"]
        or sha256_bytes((METADATA / "pinned-data.parquet").read_bytes())
        != pinned["parquet_sha256"]
        or pinned["all_projected_metadata_equal"] is not True
    ):
        raise ValueError("pinned input drift")
    rows = json.loads(metadata_bytes)
    split = json.loads(split_bytes)
    identities = {r["instance_id"] for r in rows}
    if (
        len(rows) != 500 or len(identities) != 500
        or identities != set(split["dev"] + split["held_out"])
        or set(split["dev"]) & set(split["held_out"])
        or any(not re.fullmatch(r"[0-9a-f]{40}", r["base_commit"]) for r in rows)
    ):
        raise ValueError("metadata identity mismatch")
    prior = json.loads((OLD / "frozen-candidates.json").read_bytes())
    previously_selected = {
        r["instance_id"] for repo in prior["repositories"] for r in repo["selected"]
    }
    paths = {
        p for directory in WORK_DIRS
        for p in (ROOT / ".attest" / directory).glob("**/*")
        if p.is_file() and not p.is_symlink() and p.suffix in {".json", ".jsonl", ".md", ".log"}
    }
    for name in ("result.json", "manifest.json", "summary.json"):
        paths.update((ROOT / ".attest/corpora").glob("*/" + name))
    ignored = {}
    for p in sorted(paths):
        if p.stat().st_size > 16_000_000:
            raise ValueError("unbounded exposure record requires explicit audit")
        ignored[p.relative_to(ROOT).as_posix()] = p.read_bytes()
    candidates = []
    for row in rows:
        if row["instance_id"] not in split["held_out"] or row["created_at"] < "2022-01-01":
            continue
        repo = row["repo"]
        number = row["instance_id"].rsplit("-", 1)[1]
        name = repo.split("/")[1]
        needles = [row["instance_id"], row["base_commit"], f"{name}-{number}",
                   f"{name}#{number}", f"{repo}/pull/{number}", f"{repo}/issues/{number}"]
        command = ["git", "grep", "-IlF"]
        for needle in needles:
            command.extend(["-e", needle])
        command.extend([BASELINE, "--", ".", ":(exclude)" + SPLIT])
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode not in (0, 1):
            raise ValueError("tracked exposure audit failed")
        matches = result.stdout.splitlines()
        ignored_matches = [
            path for path, content in ignored.items()
            if any(needle.encode() in content for needle in needles)
        ]
        eligible = (
            not matches and not ignored_matches
            and row["instance_id"] not in previously_selected
        )
        candidates.append({
            **row, "eligible": eligible, "tracked_references": matches,
            "ignored_references": ignored_matches,
            "previously_selected": row["instance_id"] in previously_selected,
        })
    repositories = sorted(
        {r["repo"] for r in candidates}, key=lambda repo: sha256_bytes((SEED + repo).encode()),
    )
    selected = []
    selected_repositories = []
    for repo in repositories:
        pool = [r for r in candidates if r["repo"] == repo and r["eligible"]]
        if len(pool) < 5 or len(selected_repositories) == 4:
            continue
        pool.sort(key=lambda r: sha256_bytes((SEED + repo + "|" + r["instance_id"]).encode()))
        selected_repositories.append(repo)
        selected.extend(pool[:5])
    write_canonical_json(destination, {
        "status": "frozen_pending_independent_review", "audit_baseline": BASELINE,
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((STUDY / "protocol.md").read_bytes()),
        "metadata_sha256": sha256_bytes(metadata_bytes), "split_sha256": sha256_bytes(split_bytes),
        "parquet_sha256": pinned["parquet_sha256"], "dataset_revision": pinned["revision"],
        "ignored_record_sha256": {p: sha256_bytes(b) for p, b in ignored.items()},
        "candidates": candidates, "selected_repositories": selected_repositories,
        "selected": selected, "source_or_hidden_columns_read": False,
        "qualified_defects": 0, "qualified_controls": 0, "model_api_spend_usd": 0,
    })
    print("Frozen candidates:", len(selected), "repositories:", selected_repositories)


if __name__ == "__main__":
    main()
