"""Audit and freeze unused cases without reading further project or gold source."""

from __future__ import annotations

import argparse
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", choices=("case-heldout", "metadata-exposed", "remainder"),
                        default="case-heldout")
    args = parser.parse_args()
    remainder = args.study == "remainder"
    metadata_exposed = args.study in {"metadata-exposed", "remainder"}
    study = ROOT / "benchmarks/studies/metadata-exposed-v1" if metadata_exposed else STUDY
    baseline = "1a3fbb9bb6011051532bf52437ce020fc9aeb6dd" if metadata_exposed else BASELINE
    seed = "attest-metadata-exposed-v1|" if metadata_exposed else SEED
    if remainder:
        study = ROOT / "benchmarks/studies/remainder-v1"
        baseline = "ea73b72d4cde9086018183b633a8daebcde431b3"
        seed = "attest-remainder-v1|"
    destination = study / "freeze.json"
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
    screening_path = "docs/acceptance/evidence/2026-09-12-heldout-supported-probe.json"
    administrative_path = "benchmarks/studies/case-holdout-v1/freeze.json"
    screening = {}
    remainder_path = "benchmarks/studies/metadata-exposed-v1/freeze.json"
    remainder_bytes = b""
    remainder_pool: set[str] = set()
    if metadata_exposed:
        earlier = json.loads((ROOT / administrative_path).read_bytes())
        previously_selected.update(r["instance_id"] for r in earlier["selected"])
        screening = json.loads((ROOT / screening_path).read_bytes())
        if set(screening) != {"screen", "probe"}:
            raise ValueError("unknown screening sections")
    if remainder:
        remainder_bytes = (ROOT / remainder_path).read_bytes()
        if remainder_bytes != subprocess.check_output(
            ["git", "show", baseline + ":" + remainder_path], cwd=ROOT, timeout=30,
        ):
            raise ValueError("prior remainder inventory drift")
        previous = json.loads(remainder_bytes)
        previously_selected.update(r["instance_id"] for r in previous["selected"])
        remainder_pool = {r["instance_id"] for r in previous["candidates"]
                          if r["eligible"] and r["instance_id"] not in previously_selected}
    directories = WORK_DIRS + (("case-holdout-work",) if metadata_exposed else ())
    if remainder:
        directories = tuple(sorted(set(directories) | {
            p.name for p in (ROOT / ".attest").glob("*-work")
            if p.is_dir() and not p.is_symlink() and p.name != "remainder-freeze-work"
        }))
    paths = {
        p for directory in directories
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
        if remainder and row["instance_id"] not in remainder_pool:
            continue
        repo = row["repo"]
        number = row["instance_id"].rsplit("-", 1)[1]
        name = repo.split("/")[1]
        needles = [row["instance_id"], row["base_commit"], f"{name}-{number}",
                   f"{name}#{number}", f"{repo}/pull/{number}", f"{repo}/issues/{number}"]
        command = ["git", "grep", "-IlF"]
        for needle in needles:
            command.extend(["-e", needle])
        command.extend([baseline, "--", ".", ":(exclude)" + SPLIT])
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        if result.returncode not in (0, 1):
            raise ValueError("tracked exposure audit failed")
        matches = result.stdout.splitlines()
        ignored_matches = [
            path for path, content in ignored.items()
            if any(needle.encode() in content for needle in needles)
        ]
        allowed_matches = []
        if metadata_exposed:
            # The preceding freeze is an administrative metadata inventory;
            # every selected identity remains excluded separately.
            allowed_matches = [m for m in matches if m == baseline + ":" + administrative_path]
            if remainder:
                allowed_matches.extend(m for m in matches if m == baseline + ":" + remainder_path)
            screen_rows = [r for r in screening["screen"]
                           if r["instance_id"] == row["instance_id"]]
            keys = {"instance_id", "repo", "base_commit", "created_at", "difficulty",
                    "python", "reason", "manifests_read", "supported"}
            probe_text = json.dumps(screening["probe"])
            if (len(screen_rows) == 1 and set(screen_rows[0]) == keys
                and all(screen_rows[0][k] == row[k]
                        for k in ("instance_id", "repo", "base_commit"))
                and not any(n in probe_text for n in needles)):
                allowed_matches.extend(m for m in matches
                                       if m == baseline + ":" + screening_path)
        eligible = (
            not (set(matches) - set(allowed_matches)) and not ignored_matches
            and row["instance_id"] not in previously_selected
        )
        candidates.append({
            **row, "eligible": eligible, "tracked_references": matches,
            "permitted_metadata_references": allowed_matches,
            "ignored_references": ignored_matches,
            "previously_selected": row["instance_id"] in previously_selected,
        })
    repositories = sorted(
        {r["repo"] for r in candidates}, key=lambda repo: sha256_bytes((seed + repo).encode()),
    )
    selected = []
    selected_repositories = []
    if remainder:
        selected = sorted(
            (r for r in candidates if r["eligible"]),
            key=lambda r: sha256_bytes((seed + r["repo"] + "|" + r["instance_id"]).encode()),
        )
        selected_repositories = sorted({r["repo"] for r in selected})
    for repo in ([] if remainder else repositories):
        pool = [r for r in candidates if r["repo"] == repo and r["eligible"]]
        if len(pool) < (3 if metadata_exposed else 5) or len(selected_repositories) == 4:
            continue
        pool.sort(key=lambda r: sha256_bytes((seed + repo + "|" + r["instance_id"]).encode()))
        selected_repositories.append(repo)
        selected.extend(pool[:5])
    write_canonical_json(destination, {
        "status": "frozen_pending_independent_review", "audit_baseline": baseline,
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "protocol_sha256": sha256_bytes((study / "protocol.md").read_bytes()),
        "metadata_sha256": sha256_bytes(metadata_bytes), "split_sha256": sha256_bytes(split_bytes),
        "parquet_sha256": pinned["parquet_sha256"], "dataset_revision": pinned["revision"],
        **({"parent_inventory_sha256": sha256_bytes(remainder_bytes),
            "prior_pool_size": len(remainder_pool), "audited_work_directories": directories}
           if remainder else {}),
        "ignored_record_sha256": {p: sha256_bytes(b) for p, b in ignored.items()},
        "candidates": candidates, "selected_repositories": selected_repositories,
        "selected": selected, "source_or_hidden_columns_read": False,
        "qualified_defects": 0, "qualified_controls": 0, "model_api_spend_usd": 0,
    })
    print("Frozen candidates:", len(selected), "repositories:", selected_repositories)


if __name__ == "__main__":
    main()
