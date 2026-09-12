"""The mutations-v1-recall report (work order PR 2 d of the 2026-09-13 window): forty
injected forward defects, what red certified, what D-232 sent to the drawer, and the
Wilson interval over forty. Free: reads the downloaded artifact.

    python scripts/acceptance/mutation_recall_report.py \\
        --artifact <downloaded artifact dir> --run-id <id> \\
        --out docs/acceptance/2026-09-13-mutation-recall.md
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
sys.path.insert(0, str(ROOT / "src"))

from mutation_recall import REPOSITORIES, classify, wilson  # noqa: E402

RUNS = "https://github.com/IcantFind-a-username/Attest/actions/runs"
STUDY = ROOT / "benchmarks" / "studies" / "mutations-v1-recall"
CLASS_TEXT = {
    "guard_raise": "an `if …: raise …` validation deleted",
    "boundary": "a `<=`/`<` (or `>=`/`>`) boundary swapped",
    "none_guard": "an `if x is None: return …` guard deleted",
}


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def build(artifact: Path, run_id: str) -> str:
    sample = _read_jsonl(STUDY / "sample.jsonl")
    assert sample, "the sample is empty"
    study_dir = artifact / "benchmarks" / "studies" / "mutations-v1-recall"
    trials = {r["unit_id"]: r for r in _read_jsonl(study_dir / "trials.jsonl")}
    lines = {r["unit_id"]: r for r in _read_jsonl(study_dir / "lines-trials.jsonl")}
    ledgers: dict[str, list[dict]] = {}
    for library in REPOSITORIES:
        path = (
            artifact
            / ".attest"
            / "corpora"
            / "mutations-v1-recall"
            / library
            / "repo"
            / ".attest"
            / "ledger.jsonl"
        )
        ledgers[library] = _read_jsonl(path)
    assert any(ledgers.values()), "no ledger in the artifact: the input is empty"
    rows = []
    for row in sample:
        unit = str(row["unit_id"])
        trial = trials.get(unit)
        site = f"{row['mutation']['path']}:{row['mutation']['line']}"
        if trial is None:
            rows.append(
                {
                    "case": unit,
                    "library": row["library"],
                    "kind": row["stratum"],
                    "site": site,
                    "class": "not run",
                    "why": "",
                    "spend": 0.0,
                    "lines": {},
                }
            )
            continue
        mine = [e for e in ledgers[str(row["library"])] if e.get("task_id") == trial["task_id"]]
        klass, why = classify(mine, str(trial.get("deferred_reason") or ""))
        entry = lines.get(unit, {}).get("lines", {})
        rows.append(
            {
                "case": unit,
                "library": row["library"],
                "kind": row["stratum"],
                "site": site,
                "class": klass,
                "why": why,
                "spend": float(trial.get("spend_usd") or 0.0),
                "candidates": trial.get("candidates"),
                "eligible": trial.get("eligible"),
                "attempted": trial.get("attempted"),
                "certified": trial.get("certified"),
                "lines": {k: len(v) for k, v in entry.items()},
                "shown": [item.get("line", "") for v in entry.values() for item in v],
            }
        )
    n = len(sample)
    certified = sum(1 for r in rows if r["class"] == "certified")
    drawer = sum(1 for r in rows if r["class"].startswith("drawer: D-232"))
    low, high = wilson(certified, n)
    ran = [r for r in rows if r["class"] != "not run"]
    classes = Counter(r["class"] for r in rows)
    spend = sum(r["spend"] for r in rows)
    out: list[str] = []
    out.append("# mutations-v1-recall, 2026-09-13 — forty injected defects, and what red certified")
    out.append("")
    out.append(
        f"**Work order PR 2 d of the 2026-09-13 window.** Run [`{run_id}`]({RUNS}/{run_id}) on the "
        "declared CI platform: forty forward cases of D-231's mutation corpus, five per library "
        "under seed 20260913, re-created on the runner from their recorded sites and reviewed "
        "through the local review path — no GitHub client, nothing written anywhere — at K=5, "
        "$1.00 per case, `linux-container-v1`, both yellow switches on, under the code of "
        "`release/batch2` (D-232, D-233, D-234). **The first recall figure on a corpus that is "
        "not reversed by construction.** Every case carries one injected defect; the denominator "
        "is forty whatever the cap or the runner did."
    )
    out.append("")
    out.append("## 1. The number")
    out.append("")
    out.append("| | |")
    out.append("|---|---|")
    out.append(f"| cases in the sample (the denominator) | **{n}** |")
    out.append(f"| cases run | **{len(ran)}** |")
    out.append(f"| **certified** (at least one accepted receipt) | **{certified}** |")
    out.append(f"| point estimate | **{certified / n:.1%}** |")
    out.append(f"| Wilson 95% | **[{low:.1%}, {high:.1%}]** |")
    out.append(
        f"| **sent to the drawer by D-232** (a rejection on a line the mutation wrote, or "
        f"reached through one) | **{drawer}** |"
    )
    out.append(f"| spend | ${spend:.4f} |")
    out.append("")
    out.append("Classes, counted:")
    out.append("")
    for klass, count in classes.most_common():
        out.append(f"- **{count}** — {klass}")
    out.append("")
    out.append("## 2. By mutation class")
    out.append("")
    out.append(
        "| class | what was injected | cases | certified | D-232 drawer | value class | other |"
    )
    out.append("|---|---|---|---|---|---|---|")
    for kind in ("guard_raise", "boundary", "none_guard"):
        of = [r for r in rows if r["kind"] == kind]
        c = sum(1 for r in of if r["class"] == "certified")
        d = sum(1 for r in of if r["class"].startswith("drawer: D-232"))
        v = sum(1 for r in of if r["class"] == "value class")
        rest = len(of) - c - d - v
        out.append(f"| `{kind}` | {CLASS_TEXT[kind]} | {len(of)} | {c} | {d} | {v} | {rest} |")
    out.append("")
    out.append("## 3. Every case")
    out.append("")
    out.append(
        "| case | library | class | site | verdict | cand | elig | att | lines | why | spend |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        shown = ", ".join(f"{k} {v}" for k, v in r["lines"].items() if v) or "none"
        out.append(
            f"| `{r['case']}` | `{r['library']}` | {r['kind']} | `{r['site']}` | "
            f"**{r['class']}** | "
            f"{r.get('candidates', '')} | {r.get('eligible', '')} | {r.get('attempted', '')} | "
            f"{shown} | {_cell(r['why'][:160])} | ${r['spend']:.4f} |"
        )
    out.append("")
    out.append("## 4. What is and is not claimed")
    out.append("")
    out.append(
        "- **Not natural traffic.** Three injection rules on lines the libraries' own tests reach "
        "(D-231); whether those tests catch each mutation was not measured."
    )
    out.append(
        "- **Not comparable to the held-out figure** (5 of 25 on the reversed SWE-bench slice): "
        "a different population and a different direction. Two corpora, two denominators."
    )
    out.append(
        "- **The D-232 count is the cost of the frame rule on this population**, stated beside the "
        "recall it leaves: a mutation that raises on the line it wrote is read as a behaviour "
        "change with unknown intent and shown as a yellow value line where the switch is on."
    )
    out.append(
        "- **A case the cap refused or the runner could not build is a miss**, named in §3, and "
        "the denominator did not shrink."
    )
    out.append("")
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    text = build(Path(args.artifact), args.run_id)
    Path(args.out).write_text(text, encoding="utf-8")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
