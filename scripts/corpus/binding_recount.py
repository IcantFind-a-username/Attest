#!/usr/bin/env python3
"""Re-adjudicate every recorded gate `through_caller` witness under name binding,
and measure the S.T wealth of every control candidate. D-174.

Free: `ast`, `git`, and evidence/ledger files already on disk. No model call, no
execution, no network, $0.00.

    python scripts/corpus/binding_recount.py \
        --out docs/acceptance/evidence/2026-09-08-binding-recount.json
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.diffs import parse_diff  # noqa: E402
from attest.review.gate_level import (  # noqa: E402
    calls_in,
    enclosing_qualname,
    find_call_sites,
    show,
)

CORPORA = ROOT / ".attest" / "corpora"
# where each recorded population's repository lives in the gitignored corpus tree
REPOS: dict[str, Path] = {
    "attest": CORPORA / "attest",
    "corum": CORPORA / "corum",
    "us-stock-helper": CORPORA / "us-stock-helper",
    "click": CORPORA / "gnull" / "click",
    "IcantFind-a-username/Attest": CORPORA / "attest",
    "IcantFind-a-username/Corum": CORPORA / "corum",
    "IcantFind-a-username/us-stock-helper": CORPORA / "us-stock-helper",
}
EVIDENCE = ROOT / "docs" / "acceptance" / "evidence"
WITNESS_FILE = EVIDENCE / "2026-09-05-gate-witness.json"
SHADOW_FILES = (
    ("forward", EVIDENCE / "2026-09-06c-gate-shadow-forward.json"),
    ("attest-40", EVIDENCE / "2026-09-06c-four-levels-attest.json"),
    ("corum-10", EVIDENCE / "2026-09-06c-four-levels-corum.json"),
    ("ush-40", EVIDENCE / "2026-09-06c-four-levels-us-stock-helper.json"),
    ("budget-17-attest", EVIDENCE / "2026-09-07-budget-attest.json"),
    ("budget-17-ush", EVIDENCE / "2026-09-07-budget-ush.json"),
    ("forward-fix-13", EVIDENCE / "2026-09-07-forward-fix.json"),
)
NULL_LEDGERS = CORPORA / "gnull"
V_REPRODUCED_LR = 20.0
V_FAILED_LR = 0.5


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    return result.stdout if result.returncode == 0 else ""


def has_commit(repo: Path, sha: str) -> bool:
    return (
        subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{sha}^{{commit}}"],
            capture_output=True,
            check=False,
        ).returncode
        == 0
    )


_added: dict[tuple[str, str, str], dict[str, set[int]]] = {}


def added_lines(repo: Path, base: str, head: str) -> dict[str, set[int]]:
    key = (str(repo), base, head)
    if key not in _added:
        diff = parse_diff(git(repo, "diff", "-U0", base, head))
        _added[key] = {path: set(lines) for path, lines in diff.added_lines.items()}
    return _added[key]


def name_matched_sites(
    repo: Path, sha: str, symbol: str, anchored: str, added: dict[str, set[int]]
) -> list[str]:
    """The pre-binding search: every written call of the name, outside added lines."""
    root = git(repo, "rev-parse", "--show-toplevel").strip() or str(repo)
    listed = git(Path(root), "grep", "-l", "-w", "-e", symbol, sha, "--", "*.py")
    paths = [line.split(":", 1)[1] for line in listed.splitlines() if ":" in line]
    found: list[str] = []
    for path in sorted(paths)[:40]:
        source = show(repo, sha, path)
        if not source:
            continue
        here = added.get(path, set())
        for call in calls_in(source, symbol):
            if call.line in here or (path == anchored and call.caller == symbol):
                continue
            found.append(f"{path}:{call.line}")
    return found


def bound_sites(
    repo: Path, sha: str, symbol: str, anchored: str, line: int, added: dict[str, set[int]]
) -> list[str]:
    source = show(repo, sha, anchored)
    qualname = enclosing_qualname(source, line) if source else ""
    sites, _truncated = find_call_sites(
        repo,
        sha,
        symbol,
        anchored_path=anchored,
        anchored_qualname=qualname or symbol,
        added=added,
    )
    return [f"{site.path}:{site.line}" for site in sites]


def recount_static_witness() -> dict[str, object]:
    """The 224 candidates of E-04 stratum v2, (a) re-counted both ways."""
    rows = json.loads(WITNESS_FILE.read_text())["rows"]
    old = new = 0
    lost: list[dict[str, object]] = []
    for row in rows:
        name, sha = row["unit_id"].split("@")
        repo = REPOS[name]
        if not has_commit(repo, sha):
            continue
        added = added_lines(repo, f"{sha}^", sha)
        matched = name_matched_sites(repo, sha, row["symbol"], row["path"], added)
        bound = bound_sites(repo, sha, row["symbol"], row["path"], row["line"], added)
        old += bool(matched)
        new += bool(bound)
        if matched and not bound:
            lost.append(
                {
                    "unit": row["unit_id"],
                    "path": row["path"],
                    "symbol": row["symbol"],
                    "recorded_call_site": row["call_site"],
                    "name_matched": matched[:3],
                }
            )
    return {
        "candidates": len(rows),
        "recorded_with_call_site": sum(1 for r in rows if r["call_site"]),
        "name_matched": old,
        "bound": new,
        "lost": lost,
    }


def recount_through_caller() -> dict[str, object]:
    """Every recorded `through_caller` grade of every shadow population."""
    kept = 0
    rows: list[dict[str, object]] = []
    for population, path in SHADOW_FILES:
        if not path.exists():
            continue
        for unit in json.loads(path.read_text()).get("rows", []):
            for grade in unit.get("gate") or []:
                if grade.get("kind") != "through_caller":
                    continue
                repo = REPOS.get(unit.get("repo", ""))
                head = unit.get("head") or ""
                if repo is None or not head or not has_commit(repo, head):
                    rows.append({"population": population, "at": grade.get("at"), "bound": None})
                    continue
                added = added_lines(repo, unit.get("base") or f"{head}^", head)
                anchored, line = str(grade["at"]).rsplit(":", 1)
                bound = bound_sites(
                    repo, head, grade["symbol"], anchored, int(line), added
                )
                kept += bool(bound)
                rows.append(
                    {
                        "population": population,
                        "repo": unit.get("repo"),
                        "head": head,
                        "at": grade.get("at"),
                        "symbol": grade.get("symbol"),
                        "recorded_call_site": grade.get("call_site"),
                        "bound": bound[:2],
                    }
                )
    return {"recorded": len(rows), "kept_under_binding": kept, "rows": rows}


def control_wealth() -> dict[str, object]:
    """The S.T wealth of every candidate of every control review on disk."""
    per_repo: dict[str, list[float]] = collections.defaultdict(list)
    models: collections.Counter[tuple[str, str]] = collections.Counter()
    channels: collections.Counter[tuple[str, ...]] = collections.Counter()
    runs = 0
    for ledger in sorted(NULL_LEDGERS.glob("*/.attest/ledger.jsonl")):
        repo = ledger.parts[-3]
        rows = []
        for line in ledger.read_text(errors="replace").splitlines():
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        outcome = {
            (r.get("task_id"), r.get("finding_id")): r.get("outcome")
            for r in rows
            if r.get("kind") == "verification"
        }
        for row in rows:
            if row.get("kind") == "review_run":
                runs += 1
                models[(row.get("model"), row.get("generation_model"))] += 1
            if row.get("kind") != "review" or row.get("wealth_final") is None:
                continue
            bought = tuple(row.get("channels_bought") or ())
            channels[bought] += 1
            wealth = float(row["wealth_final"])
            if "V" in bought:
                # divide V back out: the question is what S.T alone is worth
                seen = outcome.get((row.get("task_id"), row.get("finding_id")))
                wealth /= V_REPRODUCED_LR if seen == "reproduced" else V_FAILED_LR
            per_repo[repo].append(wealth)
    values = [v for group in per_repo.values() for v in group]
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    se = math.sqrt(variance / n)
    return {
        "review_runs": runs,
        "candidates": n,
        "mean": mean,
        "sd": math.sqrt(variance),
        "se": se,
        "ci95": [mean - 1.96 * se, mean + 1.96 * se],
        "t_against_one": (mean - 1.0) / se,
        "minimum": min(values),
        "maximum": max(values),
        "channels_bought": {"+".join(k) or "(none)": c for k, c in channels.items()},
        "models": {f"{s}/{g}": c for (s, g), c in models.items()},
        "per_repo": {
            repo: {"n": len(group), "mean": sum(group) / len(group)}
            for repo, group in sorted(per_repo.items())
        },
        "distribution": {
            str(value): count
            for value, count in sorted(collections.Counter(round(v, 4) for v in values).items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=None)
    arguments = parser.parse_args()

    payload = {
        "schema_version": "attest.binding-recount.v1",
        "decision": "D-174",
        "spend_usd": 0.0,
        "static_witness_224": recount_static_witness(),
        "through_caller": recount_through_caller(),
        "control_wealth": control_wealth(),
    }
    text = json.dumps(payload, indent=1, sort_keys=True)
    if arguments.out:
        arguments.out.write_text(text + "\n", encoding="utf-8")
        print(f"wrote {arguments.out}")
    static = payload["static_witness_224"]
    through = payload["through_caller"]
    wealth = payload["control_wealth"]
    print(
        f"224 candidates: name-matched {static['name_matched']} -> bound {static['bound']}"
    )
    print(
        f"through_caller: {through['recorded']} recorded -> "
        f"{through['kept_under_binding']} kept"
    )
    print(
        f"control S.T wealth: n={wealth['candidates']} mean={wealth['mean']:.4f} "
        f"min={wealth['minimum']} t={wealth['t_against_one']:.1f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
