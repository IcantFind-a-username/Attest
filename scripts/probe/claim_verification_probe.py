"""P-03: as a verification layer, how many claims can Attest confirm, and how many does it refuse?

The question this probe answers is not "how many defects does Attest find" but "given a defect
claim someone else made about a change, can Attest adjudicate it". The claimant here is not
Attest's own proposer: each claim names a change and a symbol, and the oracle is the
**repository's own test** that D-251 recorded as detecting that change. No model is called, no
probe is generated, and nothing is bought.

Two populations, both from `mutations-v1-recall`:

    true claims   the 21 cases whose own suite catches the planted change (D-251's dynamic run):
                  the claim "this change breaks behaviour" is true by construction
    null claims   the same 21 cases with a **no-op head** -- one comment line added to the same
                  file at the same place -- and the same claim made about it: false by construction

A claim is **confirmed** when the oracle passes on the parent in every repeat and fails on the
head in every repeat; **refused** when it does not. A confirmed null claim is a false
confirmation, and that number is what a verification layer lives or dies by.

    .venv/bin/python scripts/probe/claim_verification_probe.py --out probe.json

Each library is exercised in its own recorded virtual environment, in its own clone, and every
clone is restored to the revision it was on before the probe ran.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from mutation_recall import WORK  # noqa: E402

DYNAMIC = ROOT / "docs/acceptance/evidence/2026-09-15-evidence-supply/dynamic.json"
REPEATS = 3
TIMEOUT_S = 300.0


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def node_of(recorded: str, repo: Path) -> str:
    """D-251 recorded a node as a dotted path plus a name: everything up to the module is a
    file, and what follows it is a class. The file is the longest prefix that exists."""
    dotted, _, name = recorded.partition("::")
    parts = [p for p in dotted.split(".") if p]
    marker = "repo"
    if marker in parts:
        parts = parts[parts.index(marker) + 1:]
    for cut in range(len(parts), 0, -1):
        candidate = Path(*parts[:cut]).with_suffix(".py")
        if (repo / candidate).is_file():
            classes = parts[cut:]
            node = candidate.as_posix()
            if classes:
                node += "::" + "::".join(classes)
            return f"{node}::{name}" if name else node
    return Path(*parts).with_suffix(".py").as_posix() + (f"::{name}" if name else "")


def run_node(venv: Path, repo: Path, node: str) -> dict[str, Any]:
    """One run of the repository's own test, exactly as D-251 ran it."""
    python = venv / "bin" / "python"
    try:
        completed = subprocess.run(
            [str(python), "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
             "-o", "addopts=", "-W", "ignore", node],
            cwd=repo, capture_output=True, text=True, timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "timeout", "exit": None}
    tail = ((completed.stdout or "") + (completed.stderr or ""))[-600:]
    if completed.returncode == 0:
        outcome = "passed"
    elif completed.returncode == 1:
        outcome = "failed"
    else:
        outcome = "unusable"  # collection error, usage error, internal error
    return {"outcome": outcome, "exit": completed.returncode, "tail": tail.strip()[-200:]}


def repeats(venv: Path, repo: Path, node: str) -> list[dict[str, Any]]:
    return [run_node(venv, repo, node) for _ in range(REPEATS)]


def verdict(base: list[dict[str, Any]], head: list[dict[str, Any]]) -> str:
    base_set = {r["outcome"] for r in base}
    head_set = {r["outcome"] for r in head}
    if base_set == {"passed"} and head_set == {"failed"}:
        return "confirmed"
    if "unusable" in base_set | head_set or "timeout" in base_set | head_set:
        return "unusable"
    return "refused"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0, help="stop after N cases (0: all)")
    args = parser.parse_args(argv)

    cases = [
        row for row in json.loads(DYNAMIC.read_text(encoding="utf-8"))
        if row["outcome"] == "own tests catch the mutant" and row.get("detecting_nodes")
    ]
    if args.limit:
        cases = cases[: args.limit]
    rows: list[dict[str, Any]] = []
    for case in cases:
        unit = case["unit_id"]
        manifest = json.loads((WORK / "cases" / unit / "manifest.json").read_text())
        repo = Path(manifest["repo_path"])
        venv = repo.parent / ".venv"
        node = node_of(case["detecting_nodes"][0]["node"], repo)
        mutation = manifest["mutation"]
        restore = git(repo, "rev-parse", "HEAD")
        row: dict[str, Any] = {
            "unit_id": unit, "library": case["library"], "node": node,
            "claim": f"{mutation['path']}:{mutation['line']} -- {mutation['description']}",
            "base_sha": manifest["base_sha"], "head_sha": manifest["head_sha"],
        }
        try:
            # the true claim: the recorded change, adjudicated by the repository's own test
            git(repo, "checkout", "--quiet", "--force", manifest["base_sha"])
            base = repeats(venv, repo, node)
            git(repo, "checkout", "--quiet", "--force", manifest["head_sha"])
            head = repeats(venv, repo, node)
            row["true_claim"] = {"base": base, "head": head, "verdict": verdict(base, head)}

            # the null claim: the same claim about a head that changes nothing but a comment
            git(repo, "checkout", "--quiet", "--force", manifest["base_sha"])
            target = repo / mutation["path"]
            original = target.read_text(encoding="utf-8")
            lines = original.splitlines(keepends=True)
            index = max(0, min(len(lines), int(mutation["line"]) - 1))
            indent = len(lines[index]) - len(lines[index].lstrip()) if index < len(lines) else 0
            lines.insert(index, " " * indent + "# attest probe: a comment, and nothing else\n")
            target.write_text("".join(lines), encoding="utf-8")
            null_head = repeats(venv, repo, node)
            target.write_text(original, encoding="utf-8")
            null_base = base  # the same parent runs; the null head differs from it by a comment
            row["null_claim"] = {
                "base": null_base, "head": null_head, "verdict": verdict(null_base, null_head),
            }

            # the reversed claim: the same two revisions the other way round, so the change
            # under review is the repair. The behaviour does change, and the claim "the head
            # introduces this defect" is still false
            row["reversed_claim"] = {
                "base": head, "head": base, "verdict": verdict(head, base),
            }
        finally:
            git(repo, "checkout", "--quiet", "--force", restore)
        rows.append(row)
        print(json.dumps({
            "unit_id": unit, "true": row.get("true_claim", {}).get("verdict"),
            "null": row.get("null_claim", {}).get("verdict"),
            "reversed": row.get("reversed_claim", {}).get("verdict"),
        }), flush=True)

    def tally(kind: str) -> dict[str, int]:
        counts: dict[str, int] = {}
        for row in rows:
            v = row.get(kind, {}).get("verdict", "missing")
            counts[v] = counts.get(v, 0) + 1
        return counts

    summary = {
        "probe": "P-03 claim verification",
        "cases": len(rows),
        "repeats_per_side": REPEATS,
        "true_claims": tally("true_claim"),
        "null_claims": tally("null_claim"),
        "reversed_claims": tally("reversed_claim"),
        "limits": [
            "the oracle is the repository's own test that D-251 recorded as detecting the "
            "change; a claim whose behaviour no existing test covers is outside this probe",
            "line attribution is not checked: a confirmed claim shows the change causes the "
            "failure, not that the claimed line is the one that runs (the product's binding "
            "observation does that with a tracer, which this probe does not run)",
            "the claims are the corpus's planted changes, not a third party's prose claims",
            "the oracle is given: D-251 recorded which of the repository's tests detects each "
            "change, and choosing that test for an arbitrary claim is the part this probe does "
            "not do",
            "a claim's location is not adjudicated: a true claim that names the wrong file or "
            "line would still be confirmed here, because the probe runs no tracer",
        ],
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(
        {k: summary[k] for k in ("cases", "true_claims", "null_claims", "reversed_claims")},
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
