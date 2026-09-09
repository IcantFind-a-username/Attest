"""Which review bought each receipt the score bar hid? (free, offline)

The 2026-09-12 census counted the suppressions. This answers the question the
census left open: **what population was each suppressing review drawn from** --
a defect case, a designated control, or neither.

It recomputes the census rather than reading it, then resolves every suppressing
task to the `(head, merge_base)` pair its own `task.json` records and matches
that pair against the committed run plans:

  benchmarks/attest-v2/runs/2026-09-03-real-traffic-plan.json   defect | control
  benchmarks/studies/e04-prospective-v2/sample.jsonl            E-04 shadow unit
  benchmarks/attest-v2/runs/2026-09-06-four-levels-plan*.json   four-levels unit
  benchmarks/attest-v2/runs/2026-09-05-forward-pairs.json       forward pair
  benchmarks/attest-v2/runs/2026-09-03-e01-natural-null-plan.json      E-01 null
  benchmarks/attest-v2/runs/2026-09-0*-g-null-001a-*population.json    null control

A pair is matched on **both** shas: `9b610f6a` is the head of a defect row and of
a control row in the same plan, and only the base separates them.

No model call, no execution, $0.00.

Usage: python scripts/acceptance/suppression_sources.py [--json OUT]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "benchmarks" / "attest-v2" / "runs"
REASON_BELOW = "below family threshold"
V_CAP = 20.0  # channels.verification_lr(reproduced=True); D-197


def _rows(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return out
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            out.append(entry)
    return out


def _sources() -> list[Path]:
    seen: dict[Path, None] = {}
    for root in (REPO / ".attest", REPO / "docs" / "acceptance" / "evidence"):
        if root.exists():
            for path in sorted(root.rglob("*.jsonl")):
                seen[path] = None
    return list(seen)


def census() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Every `below family threshold` suppression, with its score and bar."""
    suppressions: list[dict[str, Any]] = []
    files = _sources()
    policy_rows = 0
    for path in files:
        wealth: dict[tuple[str, str], float] = {}
        cert: dict[tuple[str, str], str] = {}
        verif: dict[tuple[str, str], str] = {}
        policies: list[dict[str, Any]] = []
        for row in _rows(path):
            key = (str(row.get("task_id", "")), str(row.get("finding_id", "")))
            kind = row.get("kind")
            if kind == "review":
                value = row.get("wealth_final")
                if isinstance(value, (int, float)):
                    wealth[key] = float(value)
            elif kind == "certification":
                cert[key] = str(row.get("outcome", ""))
            elif kind == "verification":
                verif[key] = str(row.get("outcome", ""))
            elif kind == "publication_policy":
                policies.append(row)
        policy_rows += len(policies)
        for policy in policies:
            task = str(policy.get("task_id", ""))
            for entry in policy.get("suppressed", []) or []:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("reason", "")) != REASON_BELOW:
                    continue
                fid = str(entry.get("finding_id", ""))
                key = (task, fid)
                pre = wealth.get(key)
                # v2 rows carry the per-unit bars D-125 actually applies; the
                # PR-level `family_threshold` beside them is the pre-D-125
                # aggregate and is not the bar. The row does not say which unit
                # the candidate sat in, so the *smallest* unit bar is quoted --
                # the one most favourable to publication.
                units = policy.get("unit_thresholds") or {}
                score = None if pre is None else pre * V_CAP
                if isinstance(units, dict) and units:
                    values = sorted({float(v) for v in units.values()
                                     if isinstance(v, (int, float))})
                    # The row does not say which unit the candidate sat in. It
                    # does say the candidate was *below* its bar, which excludes
                    # every bar at or under the score; the smallest bar that
                    # survives that is the one quoted, and it is the reading
                    # most favourable to publication.
                    above = [v for v in values if score is None or v > score]
                    bar = above[0] if above else (values[0] if values else None)
                    ambiguous = len(above) > 1
                else:
                    bar = policy.get("family_threshold")
                    ambiguous = False
                alpha = policy.get("alpha")
                if isinstance(bar, (int, float)) and isinstance(alpha, (int, float)) and alpha:
                    m_u = int(round(bar * alpha))
                else:
                    m_u = policy.get("eligible_count")
                suppressions.append(
                    {
                        "ledger": str(path.relative_to(REPO)),
                        "ts": str(policy.get("ts", "")),
                        "task_id": task,
                        "finding_id": fid,
                        "pre_verification_wealth": pre,
                        "score": None if pre is None else round(pre * V_CAP, 6),
                        "bar": bar,
                        "m_u": m_u,
                        "bar_ambiguous": ambiguous,
                        "policy_schema": policy.get("schema_version"),
                        "alpha": alpha,
                        "certification": cert.get(key, "<no row>"),
                        "verification": verif.get(key, "<no row>"),
                    }
                )
    return suppressions, {"jsonl_files": len(files), "publication_policy_rows": policy_rows}


def task_pair(ledger: Path, task_id: str) -> tuple[str | None, str | None]:
    """head/base from any receipt task.json this task wrote."""
    evidence = ledger.parent / "evidence" / task_id
    if not evidence.is_dir():
        return None, None
    for sub in sorted(evidence.iterdir()):
        candidate = sub / "task.json"
        if not candidate.exists():
            continue
        try:
            data = json.loads(candidate.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        head = data.get("head_sha")
        base = data.get("merge_base_sha")
        if head and base:
            return str(head), str(base)
    return None, None


def _plan_index() -> dict[tuple[str, str], dict[str, str]]:
    index: dict[tuple[str, str], dict[str, str]] = {}

    def put(head: Any, base: Any, **label: str) -> None:
        if isinstance(head, str) and isinstance(base, str):
            index.setdefault((head, base), label)

    plan = json.loads((RUNS / "2026-09-03-real-traffic-plan.json").read_text())
    for row in plan:
        put(
            row["head"],
            row["base"],
            run="real-traffic",
            group="defect" if row["population"] == "defect" else "control",
            case=row["id"],
            note=row["subject"][:70],
        )

    sample = REPO / "benchmarks" / "studies" / "e04-prospective-v2" / "sample.jsonl"
    for row in _rows(sample):
        put(
            row.get("head_sha"),
            row.get("base_sha"),
            run="e04-shadow-v2",
            group="neither",
            case=str(row.get("unit_id", "")),
            note=f"stratum {row.get('stratum')}: {str(row.get('subject',''))[:55]}",
        )

    for name in sorted(RUNS.glob("2026-09-0*-four-levels-plan*.json")):
        for row in json.loads(name.read_text()).get("units", []):
            put(row["head"], row["base"], run="four-levels", group="neither",
                case=f"{row['repo']}@{row['head'][:7]}", note=name.stem)

    for name in sorted(RUNS.glob("*forward-*.json")):
        data = json.loads(name.read_text())
        for row in data.get("pairs", []) or data.get("units", []):
            put(row.get("head"), row.get("base"), run=name.stem, group="defect",
                case=str(row.get("repo", "")), note="forward pair")

    # The two developer-directed us-stock-helper trials of 2026-09-03: each head
    # is a deliberate revert of a real fix, so each is a planted defect. Source:
    # docs/acceptance/2026-09-03-us-stock-helper-trial-rerun.md, which names both
    # heads and the shared base.
    for case, head in (
        ("trial-a", "259f7ee"),
        ("trial-b", "07485beafe243cb24c3e1d66d52d3db01290d290"),
    ):
        put(head, "9fc9408fb42b4a4625fcb4dbaa764e0f99c604cc", run="ush-trials",
            group="defect", case=case, note="planted revert of a real fix")

    for name in sorted(RUNS.glob("*g-null-001a*population.json")):
        for row in json.loads(name.read_text()).get("controls", []):
            put(row.get("sha"), row.get("base"), run=name.stem, group="control",
                case=str(row.get("repo", "")), note=str(row.get("subject", ""))[:60])
    return index


def classify(suppressions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = _plan_index()
    pairs: dict[str, tuple[str | None, str | None]] = {}
    out: list[dict[str, Any]] = []
    for row in suppressions:
        ledger = REPO / row["ledger"]
        task = row["task_id"]
        if task not in pairs:
            pairs[task] = task_pair(ledger, task)
        head, base = pairs[task]
        label = index.get((head or "", base or ""))
        out.append({**row, "head_sha": head, "merge_base_sha": base,
                    **(label or {"run": "unmatched", "group": "unclassified",
                                 "case": "", "note": ""})})
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="")
    args = parser.parse_args()
    suppressions, meta = census()
    rows = classify(suppressions)
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        groups.setdefault(str(row["group"]), []).append(row)

    print(f"jsonl files read              {meta['jsonl_files']}")
    print(f"publication_policy rows       {meta['publication_policy_rows']}")
    print(f"'{REASON_BELOW}' suppressions {len(rows)}"
          f"   over {len({r['task_id'] for r in rows})} reviews")
    print()
    for group in ("defect", "control", "neither", "unclassified"):
        rows_g = groups.get(group, [])
        print(f"== {group}: {len(rows_g)} suppression(s) over "
              f"{len({r['task_id'] for r in rows_g})} review(s)")
        for row in sorted(rows_g, key=lambda r: (str(r["ts"]), str(r["finding_id"]))):
            print(f"   {row['task_id']}  {row['finding_id']}  score "
                  f"{row['score']}  bar {row['bar']}  m_u {row['m_u']}  "
                  f"[{row['run']} {row['case']}] {row['note']}")
        print()
    print(f"CONTROL SIDE: {len(groups.get('control', []))}")
    if args.json:
        Path(args.json).write_text(json.dumps(
            {"produced_by": "scripts/acceptance/suppression_sources.py", **meta,
             "score_rule": "review-row wealth_final x verification_lr(True)=20.0 (D-197)",
             "rows": rows}, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
