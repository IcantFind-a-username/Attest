"""P-04b: do a repository's own stated values hold at runtime, and do they localise a defect?

The direction: a repository states things about itself; run it and see which statements break.
This probe uses the statements that are already executable -- **doctest examples**, a call and
the value it is stated to produce -- as checkpoints, and measures the two numbers that decide
whether the idea works at all:

    noise floor    how many checkpoints break on the healthy revision (they should be none,
                   and every one that does is a false alarm the idea has to survive)
    localisation   on a revision with one planted defect, do checkpoints break, and is the
                   file they break in the file the defect was planted in

The workload is the library's own package under `pytest --doctest-modules`; the planted defects
are the mutation corpus this project already has. No model, no probe generation, no spend.

    .venv/bin/python scripts/probe/checkpoint_runtime_probe.py --out probe.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
sys.path.insert(0, str(ROOT / "scripts" / "probe"))

from checkpoint_inventory import package_of  # noqa: E402
from mutation_recall import STUDY, WORK  # noqa: E402

TIMEOUT_S = 900.0
# the libraries whose own source states values a run can check (P-04a's inventory)
WITH_DOCTESTS = {"more-itertools", "packaging", "jinja", "urllib3"}
_FAILED = re.compile(r"^FAILED (\S+)", re.M)
_COUNTS = re.compile(r"(\d+) (passed|failed|error|errors)")


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def run_doctests(venv: Path, repo: Path, package: Path) -> dict[str, Any]:
    """Every doctest of the library's own source, as its own workload."""
    relative = package.relative_to(repo).as_posix()
    try:
        completed = subprocess.run(
            [str(venv / "bin" / "python"), "-m", "pytest", "-q", "--no-header",
             "-p", "no:cacheprovider", "-o", "addopts=", "-W", "ignore",
             "--doctest-modules", relative],
            cwd=repo, capture_output=True, text=True, timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "timeout", "failed_nodes": [], "passed": 0, "failed": 0}
    text = (completed.stdout or "") + (completed.stderr or "")
    counts = {kind: int(n) for n, kind in _COUNTS.findall(text)}
    nodes = sorted(set(_FAILED.findall(text)))
    return {
        "outcome": (
            "clean" if completed.returncode == 0
            else "failed" if completed.returncode == 1 else "unusable"
        ),
        "exit": completed.returncode,
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0),
        "failed_nodes": nodes[:40],
        "tail": text.strip()[-300:] if completed.returncode not in (0, 1) else "",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)

    sample = [
        row for row in (
            json.loads(line) for line in
            (STUDY / "sample.jsonl").read_text(encoding="utf-8").splitlines() if line
        )
        if row["library"] in WITH_DOCTESTS
    ]
    if args.limit:
        sample = sample[: args.limit]

    rows: list[dict[str, Any]] = []
    healthy: dict[str, dict[str, Any]] = {}
    for case in sample:
        unit = case["unit_id"]
        manifest = json.loads((WORK / "cases" / unit / "manifest.json").read_text())
        repo = Path(manifest["repo_path"])
        venv = repo.parent / ".venv"
        package = package_of(repo)
        if package is None:
            continue
        mutation = manifest["mutation"]
        restore = git(repo, "rev-parse", "HEAD")
        try:
            # the healthy revision is the same for every case of a library only when the
            # parents agree; they do not, so each case measures its own noise floor
            git(repo, "checkout", "--quiet", "--force", manifest["base_sha"])
            base = run_doctests(venv, repo, package)
            git(repo, "checkout", "--quiet", "--force", manifest["head_sha"])
            head = run_doctests(venv, repo, package)
        finally:
            git(repo, "checkout", "--quiet", "--force", restore)
        planted = mutation["path"]
        new_nodes = sorted(set(head["failed_nodes"]) - set(base["failed_nodes"]))
        in_planted_file = [n for n in new_nodes if planted.split("/")[-1] in n]
        row = {
            "unit_id": unit, "library": case["library"], "planted": f"{planted}:{mutation['line']}",
            "mutation": mutation["description"][:90],
            "base": {k: base[k] for k in ("outcome", "passed", "failed")},
            "head": {k: head[k] for k in ("outcome", "passed", "failed")},
            "noise_floor_nodes": base["failed_nodes"],
            "new_failures": new_nodes,
            "new_failures_in_planted_file": in_planted_file,
            "detected": bool(new_nodes),
            "localised": bool(in_planted_file),
        }
        rows.append(row)
        healthy[case["library"]] = {
            "checkpoints": base["passed"] + base["failed"], "broken": base["failed"],
        }
        print(json.dumps({
            "unit_id": unit, "checkpoints": base["passed"] + base["failed"],
            "noise": base["failed"], "detected": row["detected"],
            "localised": row["localised"],
        }), flush=True)

    summary = {
        "probe": "P-04b runtime checkpoints",
        "cases": len(rows),
        "libraries": healthy,
        "detected": sum(1 for r in rows if r["detected"]),
        "localised": sum(1 for r in rows if r["localised"]),
        "noise_floor": {
            library: facts for library, facts in sorted(healthy.items())
        },
        "limits": [
            "the checkpoints are doctest examples only: statements the repository already "
            "made executable. Prose the model would have to translate is not included",
            "a library whose source states no values has no checkpoints here, whatever its "
            "defects are",
            "localisation is at file granularity: the failing doctest's module against the "
            "file the defect was planted in",
        ],
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("cases", "detected", "localised", "noise_floor")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
