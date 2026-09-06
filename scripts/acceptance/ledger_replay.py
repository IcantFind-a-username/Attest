"""Free offline replay of every recorded publication decision (acceptance 0c).

Reads only `.attest/**/ledger.jsonl` and the sibling `candidates.jsonl`. Calls
no model, runs no test, spends nothing. It answers three questions the owner
asked before deciding whether the per-unit family cap should stay:

(i)   how many candidates reproduced under V **and** passed the intent
      discriminator and were suppressed *only* by the ``m_u / alpha`` bar;
(ii)  how many candidates were published with **no** differential reproduction;
(iii) what the published set would be under ``V and intent and per-unit top N``
      (N = 3), against what was actually published.

Only certified findings reach `select_for_publication`, so every id in a
`publication_policy` row's `published`/`suppressed` already carries an accepted
receipt -- V reproduced, intent admitted. (ii) is therefore a check of that
invariant against the raw rows, not a restatement of it.

Usage: python scripts/acceptance/ledger_replay.py [--root .attest] [--json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))

from attest.certification.units import change_unit  # noqa: E402

TOP_N = 3
REASON_BELOW = "below family threshold"
REASON_SAME = "same defect as a published finding"
REASON_CAP = "beyond the hard author-visible cap"


def _rows(path: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
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


def collect(root: Path) -> dict[str, Any]:
    files = sorted(root.rglob("ledger.jsonl"))
    # (task_id, finding_id) -> file path, wealth, certification outcome, V outcome
    anchor: dict[tuple[str, str], str] = {}
    wealth: dict[tuple[str, str], float] = {}
    cert: dict[tuple[str, str], str] = {}
    evclass: dict[tuple[str, str], str] = {}
    verif: dict[tuple[str, str], str] = {}
    policies: list[dict[str, Any]] = []

    for ledger in files:
        cand = ledger.parent / "candidates.jsonl"
        if cand.exists():
            for row in _rows(cand):
                key = (str(row.get("task_id", "")), str(row.get("finding_id", "")))
                if row.get("file"):
                    anchor[key] = str(row["file"])
        for row in _rows(ledger):
            kind = row.get("kind")
            key = (str(row.get("task_id", "")), str(row.get("finding_id", "")))
            if kind == "review":
                value = row.get("wealth_final")
                if isinstance(value, (int, float)):
                    wealth[key] = float(value)
            elif kind == "certification":
                cert[key] = str(row.get("outcome", ""))
                if row.get("evidence_class"):
                    evclass[key] = str(row["evidence_class"])
            elif kind == "verification":
                verif[key] = str(row.get("outcome", ""))
            elif kind == "ci_final":
                for decision in row.get("decisions", []) or []:
                    if not isinstance(decision, dict):
                        continue
                    dkey = (str(row.get("task_id", "")), str(decision.get("finding_id", "")))
                    value = decision.get("wealth_final")
                    if isinstance(value, (int, float)):
                        wealth.setdefault(dkey, float(value))
            elif kind == "publication_policy":
                policies.append({**row, "_ledger": str(ledger.relative_to(root.parent))})
    return {
        "ledger_files": [str(p.relative_to(root.parent)) for p in files],
        "anchor": anchor,
        "wealth": wealth,
        "cert": cert,
        "evclass": evclass,
        "verif": verif,
        "policies": policies,
    }


def replay(data: dict[str, Any]) -> dict[str, Any]:
    anchor = data["anchor"]
    wealth = data["wealth"]
    cert = data["cert"]
    verif = data["verif"]
    policies = data["policies"]

    suppressed_below: list[dict[str, Any]] = []
    published_rows: list[dict[str, Any]] = []
    published_without_v: list[dict[str, Any]] = []
    unknown_unit = 0
    diff_rows: list[dict[str, Any]] = []
    n_selections_with_findings = 0

    for policy in policies:
        task = str(policy.get("task_id", ""))
        published = [str(x) for x in policy.get("published", []) or []]
        suppressed = policy.get("suppressed", []) or []
        supp_pairs = [
            (str(s.get("finding_id", "")), str(s.get("reason", "")))
            for s in suppressed
            if isinstance(s, dict)
        ]
        certified_ids = published + [fid for fid, _ in supp_pairs]
        if certified_ids:
            n_selections_with_findings += 1

        for fid in published:
            key = (task, fid)
            row = {
                "task_id": task,
                "finding_id": fid,
                "certification": cert.get(key, "<no row>"),
                "verification": verif.get(key, "<no row>"),
                "ledger": policy["_ledger"],
            }
            published_rows.append(row)
            if cert.get(key) != "accepted" or verif.get(key) != "reproduced":
                published_without_v.append(row)

        for fid, reason in supp_pairs:
            if reason == REASON_BELOW:
                key = (task, fid)
                suppressed_below.append(
                    {
                        "task_id": task,
                        "finding_id": fid,
                        "certification": cert.get(key, "<no row>"),
                        "verification": verif.get(key, "<no row>"),
                        "wealth": wealth.get(key),
                        "unit": change_unit(anchor[key]) if key in anchor else None,
                        "ledger": policy["_ledger"],
                    }
                )

        # (iii) counterfactual: drop the m_u/alpha bar, keep clustering, take the
        # top N per change unit by priority score. The global hard cap is
        # reported both ways because the proposed rule does not say.
        clusters = policy.get("clusters", []) or []
        if not clusters:
            continue
        reps: list[tuple[str, float, str]] = []  # (finding_id, wealth, unit)
        for cluster in clusters:
            members = [str(x) for x in cluster]
            scored = sorted(
                ((m, wealth.get((task, m), 0.0)) for m in members),
                key=lambda item: (-item[1], item[0]),
            )
            rep_id, rep_wealth = scored[0]
            key = (task, rep_id)
            if key in anchor:
                unit = change_unit(anchor[key])
            else:
                unit = f"<unknown:{rep_id}>"
                unknown_unit += 1
            reps.append((rep_id, rep_wealth, unit))
        by_unit: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for rep_id, rep_wealth, unit in reps:
            by_unit[unit].append((rep_id, rep_wealth))
        kept: list[tuple[str, float]] = []
        for unit in sorted(by_unit):
            ranked = sorted(by_unit[unit], key=lambda item: (-item[1], item[0]))
            kept.extend(ranked[:TOP_N])
        kept.sort(key=lambda item: (-item[1], item[0]))
        hard_cap = policy.get("hard_cap")
        cap = hard_cap if isinstance(hard_cap, int) and hard_cap >= 0 else 3
        proposed_capped = [fid for fid, _ in kept[:cap]]
        proposed_uncapped = [fid for fid, _ in kept]
        if set(proposed_capped) != set(published) or set(proposed_uncapped) != set(published):
            diff_rows.append(
                {
                    "task_id": task,
                    "ledger": policy["_ledger"],
                    "actual_published": sorted(published),
                    "proposed_top3_per_unit_capped": sorted(proposed_capped),
                    "proposed_top3_per_unit_uncapped": sorted(proposed_uncapped),
                    "added_capped": sorted(set(proposed_capped) - set(published)),
                    "removed_capped": sorted(set(published) - set(proposed_capped)),
                    "added_uncapped": sorted(set(proposed_uncapped) - set(published)),
                    "removed_uncapped": sorted(set(published) - set(proposed_uncapped)),
                }
            )

    def _distinct(rows: list[dict[str, Any]]) -> int:
        return len({(r["task_id"], r["finding_id"]) for r in rows})

    added_capped = sum(len(r["added_capped"]) for r in diff_rows)
    removed_capped = sum(len(r["removed_capped"]) for r in diff_rows)
    added_uncapped = sum(len(r["added_uncapped"]) for r in diff_rows)
    removed_uncapped = sum(len(r["removed_uncapped"]) for r in diff_rows)

    return {
        "ledger_files": len(data["ledger_files"]),
        "publication_policy_rows": len(policies),
        "selections_with_certified_findings": n_selections_with_findings,
        "i_suppressed_only_by_family_cap": {
            "rows": len(suppressed_below),
            "distinct_task_finding": _distinct(suppressed_below),
            "distinct_finding_ids": len({r["finding_id"] for r in suppressed_below}),
            "all_certified_and_reproduced": all(
                r["certification"] == "accepted" and r["verification"] == "reproduced"
                for r in suppressed_below
            ),
            "detail": suppressed_below,
        },
        "ii_published_without_v": {
            "published_rows": len(published_rows),
            "distinct_published": _distinct(published_rows),
            "count": len(published_without_v),
            "detail": published_without_v,
        },
        "iii_top_n_per_unit": {
            "n": TOP_N,
            "selections_whose_set_would_differ": len(diff_rows),
            "added_capped": added_capped,
            "removed_capped": removed_capped,
            "added_uncapped": added_uncapped,
            "removed_uncapped": removed_uncapped,
            "unresolved_units": unknown_unit,
            "detail": diff_rows,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(REPO / ".attest"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = replay(collect(Path(args.root)))
    if args.json:
        print(json.dumps(result, indent=1, default=str))
        return 0
    i = result["i_suppressed_only_by_family_cap"]
    ii = result["ii_published_without_v"]
    iii = result["iii_top_n_per_unit"]
    print(f"ledger files                       {result['ledger_files']}")
    print(f"publication_policy rows            {result['publication_policy_rows']}")
    print(f"  ... carrying a certified finding {result['selections_with_certified_findings']}")
    print()
    print("(i)  V reproduced + intent passed, suppressed only by m_u/alpha")
    print(f"       rows {i['rows']}   distinct (task, finding) {i['distinct_task_finding']}"
          f"   distinct findings {i['distinct_finding_ids']}")
    print(f"       every one carries an accepted receipt: {i['all_certified_and_reproduced']}")
    print()
    print("(ii) published with no differential reproduction")
    print(f"       published rows {ii['published_rows']}"
          f"   distinct (task, finding) {ii['distinct_published']}")
    print(f"       without V: {ii['count']}")
    print()
    print(f"(iii) rule -> V and intent and per-unit top {iii['n']}")
    print(f"       selections whose published set changes: "
          f"{iii['selections_whose_set_would_differ']}")
    print(f"       with the hard cap kept:   +{iii['added_capped']} / -{iii['removed_capped']}")
    print(f"       with the hard cap dropped:+{iii['added_uncapped']} / -{iii['removed_uncapped']}")
    print(f"       clusters whose unit could not be resolved: {iii['unresolved_units']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
