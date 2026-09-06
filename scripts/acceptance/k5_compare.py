"""The K=4 → K=5 difference on the fixed sample, read off the two runs' own records.

Nothing here buys anything: both columns are JSON the drivers already wrote.

  forward   the 11 distinct forward pairs, from `forward_pair_reviews.py table --json`
  heldout   the 16 crash/exception held-out cases (D-158), from the pilot's result files
            and each case's ledger
  notes     green / yellow (a) / yellow (b) rows a run appended to a clone's ledger,
            counted from a line-count snapshot taken before the run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / ".attest" / "corpora" / "swebench" / "results"
CASES = ROOT / ".attest" / "corpora" / "swebench" / "cases"

FIELDS = ("candidates", "eligible", "attempted", "certified", "published")


def _verdicts(row: dict[str, object]) -> dict[str, str]:
    return {
        str(v["finding"]): str(v["reason"]) for v in (row.get("verdicts") or [])  # type: ignore[index]
    }


def cmd_forward(args: argparse.Namespace) -> int:
    a = json.loads(Path(args.k4).read_text(encoding="utf-8"))
    b = json.loads(Path(args.k5).read_text(encoding="utf-8"))
    rows_a = {f"{r['repo']} {r['head'][:10]}": r for r in a["rows"]}
    rows_b = {f"{r['repo']} {r['head'][:10]}": r for r in b["rows"]}
    print("| pair | " + " | ".join(f"{f} 4→5" for f in FIELDS) + " | verdicts changed |")
    print("|---|" + "---|" * (len(FIELDS) + 1))
    changed: list[str] = []
    for key in rows_a:
        ra, rb = rows_a[key], rows_b.get(key, {})
        cells = []
        for f in FIELDS:
            x, y = ra.get(f), rb.get(f)
            # `eligible` is not in the local closing line, so the K=5 column does
            # not carry it. That is *unknown*, not *changed*, and the table says
            # so rather than printing a fall to zero that did not happen.
            if y is None:
                cells.append(f"{x} → n/a")
            else:
                cells.append(f"{x}" if x == y else f"**{x}→{y}**")
        va, vb = _verdicts(ra), _verdicts(rb)
        moved = [k for k in set(va) | set(vb) if va.get(k) != vb.get(k)]
        if moved:
            changed.append(key)
        print(f"| {key} | " + " | ".join(cells) + f" | {len(moved)} |")
    print()
    for key in changed:
        va, vb = _verdicts(rows_a[key]), _verdicts(rows_b.get(key, {}))
        for finding in sorted(set(va) | set(vb)):
            if va.get(finding) != vb.get(finding):
                print(f"- **{key} `{finding}`**")
                print(f"  - K=4: {va.get(finding, '(no such candidate)')}")
                print(f"  - K=5: {vb.get(finding, '(no such candidate)')}")
    for name in ("certified", "published", "policy_answered", "attempted_reproductions"):
        print(f"\n{name}: K=4 {a.get(name)} -> K=5 {b.get(name)}")
    return 0


def _case_row(iid: str, suffix: str) -> dict[str, object] | None:
    path = RESULTS / f"{iid}{suffix}.json"
    if not path.is_file():
        return None
    summary = json.loads(path.read_text(encoding="utf-8"))
    ledger = CASES / summary["case"] / "repo" / ".attest" / "ledger.jsonl"
    rows = [
        json.loads(line)
        for line in ledger.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    mine = [r for r in rows if r.get("task_id") == summary["task_id"]]
    verdicts = {
        str(r.get("finding_id")): (
            "reproduced" if r.get("outcome") == "reproduced" else str(r.get("reason", ""))
        )
        for r in mine
        if r.get("kind") == "verification"
    }
    return {
        "task_id": summary["task_id"],
        "candidates": summary["candidate_count"],
        "eligible": sum(
            1
            for r in mine
            if r.get("kind") == "eligibility" and r.get("eligibility") == "regression"
        ),
        "certified": sum(
            1 for r in mine if r.get("kind") == "certification" and r.get("outcome") == "accepted"
        ),
        "published": summary["surfaced_count"],
        "spend": summary.get("spend_usd", 0.0),
        "samples": sum(
            len(r.get("provider_samples") or []) for r in mine if r.get("kind") == "review_run"
        ),
        "verdicts": verdicts,
        "deferred_reason": summary.get("deferred_reason"),
    }


def cmd_heldout(args: argparse.Namespace) -> int:
    ids = [i for i in args.only.split(",") if i]
    print(
        "| case | cand 4→5 | elig 4→5 | cert 4→5 | pub 4→5 | samples 4→5 | $ 4→5 | moved |"
    )
    print("|---|---|---|---|---|---|---|---|")
    totals = {"a": [0, 0, 0, 0, 0.0], "b": [0, 0, 0, 0, 0.0]}
    moved_all: list[tuple[str, str, str, str]] = []
    for iid in ids:
        ra = _case_row(iid, args.k4_suffix)
        rb = _case_row(iid, args.k5_suffix)
        if ra is None or rb is None:
            print(f"| {iid} | missing ({'K=4' if ra is None else 'K=5'}) | | | | | | |")
            continue
        cells = []
        for f in ("candidates", "eligible", "certified", "published", "samples"):
            x, y = ra[f], rb[f]
            cells.append(f"{x}" if x == y else f"**{x}→{y}**")
        cells.append(f"{ra['spend']:.4f}→{rb['spend']:.4f}")
        moved = [
            k for k in set(ra["verdicts"]) | set(rb["verdicts"])
            if ra["verdicts"].get(k) != rb["verdicts"].get(k)
        ]
        for k in moved:
            moved_all.append(
                (iid, k, ra["verdicts"].get(k, "(absent)"), rb["verdicts"].get(k, "(absent)"))
            )
        print(f"| {iid} | " + " | ".join(cells) + f" | {len(moved)} |")
        for i, f in enumerate(("candidates", "eligible", "certified", "published")):
            totals["a"][i] += int(ra[f])
            totals["b"][i] += int(rb[f])
        totals["a"][4] += float(ra["spend"])
        totals["b"][4] += float(rb["spend"])
    print(
        f"\ntotals K=4 candidates {totals['a'][0]} eligible {totals['a'][1]} "
        f"certified {totals['a'][2]} published {totals['a'][3]} ${totals['a'][4]:.4f}"
    )
    print(
        f"totals K=5 candidates {totals['b'][0]} eligible {totals['b'][1]} "
        f"certified {totals['b'][2]} published {totals['b'][3]} ${totals['b'][4]:.4f}"
    )
    print("\nverdicts that moved:")
    for iid, finding, old, new in moved_all:
        print(f"- **{iid} `{finding}`**\n  - K=4: {old}\n  - K=5: {new}")
    return 0


def cmd_notes(args: argparse.Namespace) -> int:
    """Green / yellow rows a run appended, from a `<clone>=<line count>` snapshot."""
    counts: dict[str, int] = {}
    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    for clone, before in snapshot.items():
        ledger = Path(clone)
        if not ledger.is_file():
            continue
        lines = ledger.read_text(encoding="utf-8").splitlines()[int(before):]
        for line in lines:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            kind = str(row.get("kind", ""))
            if kind in {"structural_note", "impact_note", "propagation_note", "nullability_note"}:
                counts[kind] = counts.get(kind, 0) + 1
    print(json.dumps(counts, indent=1, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    f = sub.add_parser("forward")
    f.add_argument("--k4", required=True)
    f.add_argument("--k5", required=True)
    f.set_defaults(func=cmd_forward)
    h = sub.add_parser("heldout")
    h.add_argument("--only", required=True)
    h.add_argument("--k4-suffix", default=".probe")
    h.add_argument("--k5-suffix", default=".k5")
    h.set_defaults(func=cmd_heldout)
    n = sub.add_parser("notes")
    n.add_argument("--snapshot", required=True)
    n.set_defaults(func=cmd_notes)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
