"""Freeze bounded natural-control commit identities before reading their diffs."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/case-holdout-v1"
WORK = ROOT / ".attest/corpora/case-holdout-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study", choices=("case-heldout", "metadata-exposed", "remainder"),
                        default="case-heldout")
    args = parser.parse_args()
    name = {"case-heldout": "case-holdout-v1", "metadata-exposed": "metadata-exposed-v1",
            "remainder": "remainder-v1"}[args.study]
    study = ROOT / "benchmarks/studies" / name
    work = ROOT / ".attest/corpora" / ("metadata-exposed-v1" if args.study == "remainder" else name)
    destination = study / "control-candidates.json"
    if destination.exists():
        raise ValueError("control candidates already frozen")
    freeze_bytes = (study / "freeze.json").read_bytes()
    freeze = json.loads(freeze_bytes)
    validation = json.loads((study / "validation.json").read_bytes())
    if (
        validation["freeze_sha256"] != sha256_bytes(freeze_bytes)
        or validation["status"] != "freeze_cleared_for_qualification"
    ):
        raise ValueError("unreviewed population")
    repositories = []
    for name in freeze["selected_repositories"]:
        repo = work / name.replace("/", "__") / "repo"
        origin = subprocess.check_output(
            ["git", "-C", str(repo), "remote", "get-url", "origin"], text=True, timeout=30,
        ).strip()
        if origin != "https://github.com/" + name + ".git":
            raise ValueError("clone origin mismatch")
        commits: set[str] = set()
        roots = []
        for case in freeze["selected"]:
            if case["repo"] != name:
                continue
            revision = case["base_commit"]
            rows = subprocess.check_output(
                ["git", "-C", str(repo), "rev-list", "--no-merges", "--max-count=256", revision],
                text=True, timeout=60,
            ).splitlines()
            if not rows or any(not re.fullmatch(r"[0-9a-f]{40}", c) for c in rows):
                raise ValueError("invalid ancestor identities")
            commits.update(rows)
            roots.append({"revision": revision, "ancestor_count": len(rows)})
        ordered = sorted(commits, key=lambda c: sha256_bytes(
            ("attest-" + study.name + "|control|" + name + "|" + c).encode(),
        ))
        repositories.append({
            "repo": name, "origin": origin, "roots": roots,
            "ordered_commits": ordered, "inspection_limit": 20,
            "selected_for_inspection": ordered[:20],
        })
    write_canonical_json(destination, {
        "status": "frozen_before_control_diff_inspection",
        "freeze_sha256": sha256_bytes(freeze_bytes),
        "protocol_sha256": sha256_bytes((study / "protocol.md").read_bytes()),
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "repositories": repositories, "qualified_controls": 0, "model_api_spend_usd": 0,
    })
    print("Control commit lists frozen for", len(repositories), "repositories")


if __name__ == "__main__":
    main()
