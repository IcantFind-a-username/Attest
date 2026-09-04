"""The green level v0 measured offline on real traffic (D-130).

Runs `attest.review.structural` over a recorded population and reports how often
it would speak. **No model call and no execution** -- the detector cannot reach
one, which is the point of the level: the algorithm decides, and the model is
asked afterwards, once, only for the sentence.

Default population: the E-04 stratum-v2 sample -- 100 units of the owner's most
recent real traffic, the same population D-125's effect was measured on -- plus
the `G-NULL-001a` controls as a comparison group.

    .venv/bin/python scripts/corpus/structural_offline.py --json report.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.structural import (  # noqa: E402
    SIMILARITY_THRESHOLD,
    STRUCTURAL_POLICY_VERSION,
    collect,
    evidence_sentence,
    find_duplicate_implementations,
)

SAMPLE = ROOT / "benchmarks" / "studies" / "e04-prospective-v2" / "sample.jsonl"
CONTROLS = ROOT / "benchmarks" / "attest-v2" / "runs" / "2026-09-04-g-null-001a-population.json"
CORPORA = ROOT / ".attest" / "corpora"
CLONES = {
    "IcantFind-a-username/Attest": CORPORA / "attest",
    "IcantFind-a-username/Corum": CORPORA / "corum",
    "IcantFind-a-username/us-stock-helper": CORPORA / "us-stock-helper",
    "IcantFind-a-username/IcantFind-a-username": CORPORA / "icantfind-a-username",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def units_from_sample() -> list[dict]:
    rows = []
    for line in SAMPLE.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        clone = CLONES.get(str(row["repository"]))
        if clone is None:
            continue
        rows.append(
            {
                "unit_id": row["unit_id"],
                "clone": clone,
                "base": row["base_sha"],
                "head": row["head_sha"],
                "control": False,
                "stratum": row.get("stratum", ""),
            }
        )
    return rows


def units_from_controls() -> list[dict]:
    if not CONTROLS.exists():
        return []
    population = json.loads(CONTROLS.read_text(encoding="utf-8"))
    rows = []
    for control in population["controls"]:
        if not control.get("qualified"):
            continue
        rows.append(
            {
                "unit_id": f"{control['repo']}@{str(control['sha'])[:7]}",
                "clone": CORPORA / "gnull" / str(control["repo"]),
                "base": control["base"],
                "head": control["sha"],
                "control": True,
                "stratum": "null-control",
            }
        )
    return rows


def review(unit: dict, workspace: Path) -> dict:
    clone: Path = unit["clone"]
    tree = workspace / str(unit["head"])[:12]
    try:
        changed = [
            name
            for name in git(
                clone, "diff", "--name-only", f"{unit['base']}..{unit['head']}"
            ).split()
            if name.endswith(".py")
        ]
    except subprocess.CalledProcessError:
        return {**{k: v for k, v in unit.items() if k != "clone"}, "skipped": "revision missing"}
    if not changed:
        return {
            **{k: v for k, v in unit.items() if k != "clone"},
            "changed_python_files": 0,
            "findings": [],
        }
    try:
        git(clone, "worktree", "add", "--detach", str(tree), str(unit["head"]))
    except subprocess.CalledProcessError:
        return {**{k: v for k, v in unit.items() if k != "clone"}, "skipped": "worktree failed"}
    try:
        found = find_duplicate_implementations(collect(tree), changed_files=set(changed))
    finally:
        subprocess.run(
            ["git", "-C", str(clone), "worktree", "remove", "--force", str(tree)],
            check=False,
            capture_output=True,
        )
    return {
        **{k: v for k, v in unit.items() if k != "clone"},
        "changed_python_files": len(changed),
        "findings": [{**asdict(f), "sentence": evidence_sentence(f)} for f in found],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--no-controls", action="store_true")
    args = parser.parse_args(argv)

    units = units_from_sample() + ([] if args.no_controls else units_from_controls())
    rows: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="attest-structural-") as tmp:
        workspace = Path(tmp)
        for unit in units:
            rows.append(review(unit, workspace))

    def summarise(subset: list[dict]) -> dict:
        ran = [r for r in subset if "skipped" not in r]
        with_python = [r for r in ran if r.get("changed_python_files", 0) > 0]
        speaking = [r for r in ran if r.get("findings")]
        return {
            "units": len(subset),
            "ran": len(ran),
            "units_with_changed_python": len(with_python),
            "units_with_a_finding": len(speaking),
            "trigger_rate_over_ran": round(len(speaking) / len(ran), 4) if ran else 0.0,
            "trigger_rate_over_python_units": (
                round(len(speaking) / len(with_python), 4) if with_python else 0.0
            ),
            "findings": sum(len(r.get("findings", [])) for r in ran),
        }

    payload = {
        "schema_version": "attest.structural-offline.v1",
        "policy_version": STRUCTURAL_POLICY_VERSION,
        "similarity_threshold": SIMILARITY_THRESHOLD,
        "model_calls": 0,
        "spend_usd": 0.0,
        "traffic": summarise([r for r in rows if not r["control"]]),
        "controls": summarise([r for r in rows if r["control"]]),
        "rows": rows,
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(text + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in payload.items() if k != "rows"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
