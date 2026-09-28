"""Which recorded contract searches D-255 changes: rerun the fixed rule on the same inputs.

For every `contract_search` ledger row of the frozen end-to-end records (forty, the
counterexample variants, the controls) this rebuilds the search's exact input -- the base
tree at the recorded base commit, the candidate's anchored file, the touched symbols -- and
runs `contract_probes` on it with the code at `--src`. Run once with the earlier commit's
source and once with the new one; the rows that differ are the searches the change touches,
and the cases they belong to are the ones to replay. Base trees are extracted with
`git archive` into `--work`; the corpora are only read.

    .venv/bin/python scripts/corpus/contract_search_diff.py --src <checkout>/src --out x.jsonl
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-frozen-e2e"
RECORDS = ("forty-f2-E.jsonl", "counterexamples-f2-E.jsonl", "controls-f3-E.jsonl")
CONTROLS = ROOT / ".attest" / "corpora" / "e05-controls"


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _repo(label: str) -> Path:
    if "#" in label:
        return CONTROLS / label.split("/", 1)[1].split("#", 1)[0] / "repo"
    sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
    from mutation_recall import WORK

    unit_id = label.split("@", 1)[0]
    manifest = json.loads((WORK / "cases" / unit_id / "manifest.json").read_text())
    return Path(manifest["repo_path"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", required=True)
    parser.add_argument("--work", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(args.src).resolve()))
    from attest.review.contracts import contract_probes

    work = Path(args.work)
    rows = []
    for name in RECORDS:
        for record in _jsonl(EVIDENCE / name):
            searches = [r for r in record["rows"] if r.get("kind") == "contract_search"]
            files = {r["finding_id"]: r["file"] for r in record["rows"]
                     if r.get("kind") == "history_signal"}
            for search in searches:
                if not search["symbols"]:
                    continue
                repo = _repo(record["label"])
                tree = work / f"{repo.parent.name}-{record['base_sha'][:12]}"
                if not tree.is_dir():
                    tree.mkdir(parents=True)
                    archive = subprocess.run(
                        ["git", "-C", str(repo), "archive", record["base_sha"]],
                        capture_output=True, check=True,
                    ).stdout
                    subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
                result = contract_probes(tree, files[search["finding_id"]], search["symbols"])
                recorded = search["probes"]
                recorded = json.loads(recorded) if isinstance(recorded, str) else recorded
                rows.append({
                    "record": name, "label": record["label"], "finding_id": search["finding_id"],
                    "file": files[search["finding_id"]], "symbols": search["symbols"],
                    "probes": [[p.origin, p.spec.setup, p.spec.expression] for p in result.probes],
                    "refused": [list(r) for r in result.refused], "truncated": result.truncated,
                    "recorded_probes": [[p["origin"], p["setup"], p["expression"]]
                                        for p in recorded],
                })
    Path(args.out).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                              encoding="utf-8")
    print(f"{len(rows)} searches with symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
