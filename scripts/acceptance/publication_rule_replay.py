"""Replay every recorded publication decision under the new rule (D-199).

Free and offline: reads ledgers already on disk, calls no model, runs nothing.

For every ``publication_policy`` row in every ledger under ``.attest/`` and
``docs/acceptance/evidence/``, this rebuilds the inputs ``select_for_publication``
was given and asks it twice:

  **record**  under the rule the row's own ``schema_version`` names. It must
              reproduce the row's ``published`` list exactly; a row it does not
              reproduce is reported as ``unreplayable`` and excluded from the
              comparison rather than silently counted.
  **new**     under ``attest.publication-policy.v4`` -- D-199's rule: a certified
              finding publishes subject only to same-defect clustering and the
              hard cap.

Every changed row is then attributed to the population its review was drawn
from (`suppression_sources`), so the owner's condition -- *no control review
gains a publication* -- is read off the table rather than argued.

**How the inputs are rebuilt, and why it is faithful.** The recorded row carries
its own cluster partition, so each certified finding is given the test digest of
its recorded cluster and an anchor whose *path* is the candidate's real one (the
change unit, hence the bar) and whose *line* is spaced far enough apart that no
two recorded clusters can merge on proximity. The reconstruction is not trusted:
the ``record`` replay above is the check, row by row.

Usage: .venv/bin/python scripts/acceptance/publication_rule_replay.py [--json OUT]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "src"))
sys.path.insert(0, str(REPO / "scripts" / "acceptance"))

from suppression_sources import _plan_index, _rows, _sources, task_pair  # noqa: E402

from attest.certification.selection import (  # noqa: E402
    PUBLICATION_POLICY_SCHEMA_VERSION,
    FamilyPolicy,
    ScoredFinding,
    select_for_publication,
)
from attest.certification.types import (  # noqa: E402
    _ACCEPTED_RECEIPT_TOKEN,
    AcceptedReceipt,
    CertificationReceipt,
    CertifiedFinding,
    FindingAnchor,
)
from attest.certification.units import unit_counts  # noqa: E402
from attest.review.channels import V_CAP  # noqa: E402

CLUSTER_STRIDE = 1_000_000  # keeps two recorded clusters out of LINE_SLACK of each other

# The intent-policy families whose verdict is the one the product applies today.
# A receipt written under one of these was adjudicated by today's discriminator
# when it was made; anything older has to be re-judged.
CURRENT_INTENT = ("attest.intent.v4.1", "attest.intent.v4.2")
# The re-judgement on record: the 2026-09-05 replay of every receipt then on
# disk under intent v4 and v4.1 (D-134). `v4_1_class` is its verdict.
INTENT_REPLAY = REPO / "docs" / "acceptance" / "evidence" / "2026-09-05-intent-v41-replay.json"

_TEMPLATE: dict[str, Any] = {
    "schema_version": "attest.certification-receipt.v1",
    "policy_version": "attest.certification-policy.v1",
    "task_id": "t",
    "repository_id": "local",
    "merge_base_sha": "2" * 40,
    "head_sha": "1" * 40,
    "diff_digest": "9" * 64,
    "candidate_id": "x",
    "normalized_claim": "replayed",
    "claim_digest": "4" * 64,
    "test_digest": "5" * 64,
    "test_node": "test_repro.py::test_x",
    "policy_source_sha": "3" * 40,
    "policy_digest": "3" * 64,
    "environment_digest": "6" * 64,
    "interpreter_digest": "7" * 64,
    "executor_profile": "container-v1",
    "executor_digest": "8" * 64,
    "head_runs": (),
    "base_runs": (),
    "result_class": "regression",
    "evidence_class": "regression_reproduced",
    "provenance_digest": "c" * 64,
}


def _stand_in(candidate_id: str, cluster_digest: str, path: str, line: int) -> CertifiedFinding:
    """A certified finding carrying only what selection reads: the candidate id,
    the cluster's test digest, and the anchor whose path is the change unit."""
    fields = dict(_TEMPLATE, candidate_id=candidate_id, test_digest=cluster_digest)
    receipt = CertificationReceipt(**fields)  # type: ignore[arg-type]
    accepted = AcceptedReceipt._from_validated(receipt, _ACCEPTED_RECEIPT_TOKEN)
    return CertifiedFinding.from_accepted_receipt(accepted, (FindingAnchor(path=path, line=line),))


def _intent_today(
    ledger: Path, task: str, candidate: str, replay: dict[tuple[str, str], str]
) -> str:
    """Would this receipt still be certified under the intent policy in force?

    Three sources, in order: the receipt's own recorded intent policy when that
    is already today's family; the 2026-09-05 re-judgement when it is not; and
    otherwise `unknown`, which is never counted as either answer."""
    path = ledger.parent / "evidence" / task / candidate / "intent.json"
    try:
        version = str(json.loads(path.read_text()).get("policy_version", ""))
    except (OSError, ValueError):
        version = ""
    if version in CURRENT_INTENT:
        return "certifies"
    verdict = replay.get((task, candidate))
    if verdict == "regression_reproduced":
        return "certifies"
    if verdict:
        return "drawered"
    return "unknown"


def _intent_replay() -> dict[tuple[str, str], str]:
    try:
        data = json.loads(INTENT_REPLAY.read_text())
    except (OSError, ValueError):
        return {}
    return {
        (str(r.get("task_id", "")), str(r.get("candidate_id", ""))): str(r.get("v4_1_class", ""))
        for r in data.get("receipt_rows", [])
    }


def _candidates_beside(ledger: Path) -> dict[str, dict[str, dict[str, Any]]]:
    path = ledger.parent / "candidates.jsonl"
    by_task: dict[str, dict[str, dict[str, Any]]] = {}
    for row in _rows(path):
        by_task.setdefault(str(row.get("task_id", "")), {})[str(row.get("finding_id", ""))] = row
    return by_task


def replay_row(
    row: dict[str, Any], stored: dict[str, dict[str, Any]], wealth: dict[str, float]
) -> dict[str, Any] | None:
    """One recorded selection, replayed under its own rule and under v4."""
    clusters = [[str(x) for x in cluster] for cluster in (row.get("clusters") or [])]
    recorded = sorted(str(x) for x in (row.get("published") or []))
    suppressed = [
        str(s.get("finding_id", "")) for s in (row.get("suppressed") or []) if isinstance(s, dict)
    ]
    certified = sorted({*recorded, *suppressed})
    if not certified:
        return None
    if not clusters:  # a row that certified something records its partition
        clusters = [[cid] for cid in certified]
    version = str(row.get("schema_version", ""))
    alpha = float(row.get("alpha") or 0.1)
    cap = int(row.get("hard_cap") or 3)

    scored: list[ScoredFinding] = []
    unresolved: list[str] = []
    for index, cluster in enumerate(clusters):
        digest = hashlib.sha256(f"cluster-{index}".encode()).hexdigest()
        for member, cid in enumerate(cluster):
            candidate = stored.get(cid)
            if candidate is None or not candidate.get("file"):
                unresolved.append(cid)
                continue
            score = wealth.get(cid)
            if score is None:
                value = candidate.get("wealth")
                score = float(value) * V_CAP if isinstance(value, (int, float)) else None
            if score is None:
                unresolved.append(cid)
                continue
            scored.append(
                ScoredFinding(
                    _stand_in(cid, digest, str(candidate["file"]),
                              1 + index * CLUSTER_STRIDE + member * 100),
                    float(score),
                )
            )
    if unresolved or not scored:
        return {"task_id": str(row.get("task_id", "")), "unreplayable": True,
                "why": f"inputs missing for {sorted(set(unresolved))}" if unresolved
                       else "no candidate resolved"}

    eligible = [
        c for c in stored.values()
        if c.get("eligibility") == "regression" and c.get("action") != "discard"
    ]
    e_values = [
        float(c["wealth"]) * V_CAP for c in eligible if isinstance(c.get("wealth"), (int, float))
    ]
    units = dict(unit_counts(str(c["file"]) for c in eligible if c.get("file")))
    if version == "attest.publication-policy.v1":
        # the pre-D-125 rule expressed in the same code path: every unit carries
        # the whole review's eligible count, so every bar is m/alpha
        units_for_record = dict.fromkeys(units, len(eligible)) or {}
    else:
        units_for_record = units

    def run(unit_map: dict[str, int], schema: str) -> Any:
        return select_for_publication(
            scored,
            FamilyPolicy(alpha=alpha, eligible_count=len(eligible), hard_cap=cap,
                         eligible_units=unit_map, schema_version=schema),
            e_values,
        )

    record = run(units_for_record, version or "attest.publication-policy.v1")
    new = run(units, PUBLICATION_POLICY_SCHEMA_VERSION)

    def ids(selection: Any) -> list[str]:
        return sorted(f.accepted_receipt.receipt.candidate_id for f in selection.published)

    replayed = ids(record)
    return {
        "task_id": str(row.get("task_id", "")),
        "schema_version": version,
        "alpha": alpha,
        "hard_cap": cap,
        "eligible_count": len(eligible),
        "certified": certified,
        "recorded_published": recorded,
        "record_replay": replayed,
        "reproduces_record": replayed == recorded,
        "new_published": ids(new),
        "added": sorted(set(ids(new)) - set(recorded)),
        "removed": sorted(set(recorded) - set(ids(new))),
        "unreplayable": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default="")
    args = parser.parse_args()

    index = _plan_index()
    intent_replay = _intent_replay()
    pairs: dict[tuple[str, str], tuple[str | None, str | None]] = {}
    results: list[dict[str, Any]] = []
    files = 0
    policy_rows = 0
    for ledger in _sources():
        rows = _rows(ledger)
        policies = [r for r in rows if r.get("kind") == "publication_policy"]
        if not policies:
            continue
        files += 1
        policy_rows += len(policies)
        stored_by_task = _candidates_beside(ledger)
        wealth: dict[tuple[str, str], float] = {}
        for row in rows:
            if row.get("kind") == "review" and isinstance(row.get("wealth_final"), (int, float)):
                wealth[(str(row.get("task_id", "")), str(row.get("finding_id", "")))] = (
                    float(row["wealth_final"]) * V_CAP
                )
        for row in policies:
            task = str(row.get("task_id", ""))
            outcome = replay_row(
                row,
                stored_by_task.get(task, {}),
                {fid: v for (t, fid), v in wealth.items() if t == task},
            )
            if outcome is None:
                continue
            key = (str(ledger), task)
            if key not in pairs:
                pairs[key] = task_pair(ledger, task)
            head, base = pairs[key]
            label = index.get((head or "", base or "")) or {
                "run": "unmatched", "group": "unclassified", "case": "", "note": ""}
            outcome["intent_today"] = {
                cid: _intent_today(ledger, task, cid, intent_replay)
                for cid in outcome.get("added", [])
            }
            results.append({**outcome, "ledger": str(ledger.relative_to(REPO)), **label})

    comparable = [r for r in results if not r["unreplayable"] and r["reproduces_record"]]
    unreplayable = [r for r in results if r["unreplayable"]]
    mismatched = [r for r in results if not r["unreplayable"] and not r["reproduces_record"]]
    changed = [r for r in comparable if r["added"] or r["removed"]]

    added_by_group: Counter[str] = Counter()
    removed_by_group: Counter[str] = Counter()
    added_live: Counter[str] = Counter()  # restricted to receipts today's intent policy keeps
    intent_split: Counter[str] = Counter()
    for row in changed:
        added_by_group[row["group"]] += len(row["added"])
        removed_by_group[row["group"]] += len(row["removed"])
        for cid in row["added"]:
            verdict = row["intent_today"][cid]
            intent_split[verdict] += 1
            if verdict == "certifies":
                added_live[row["group"]] += 1

    print(f"ledgers with publication rows   {files}")
    print(f"publication_policy rows         {policy_rows}")
    print(f"  ... carrying a certified set  {len(results)}")
    print(f"  ... reproducing their record  {len(comparable)}")
    print(f"  ... unreplayable (excluded)   {len(unreplayable)}")
    print(f"  ... replay disagrees (excluded) {len(mismatched)}")
    print()
    print("under D-199's rule, by the population the review was drawn from:")
    print(f"  {'group':13s} {'as recorded':>13s} {'removed':>9s} {'intent v4.1+':>14s}")
    for group in ("defect", "control", "neither", "unclassified"):
        print(f"  {group:13s} {'+' + str(added_by_group[group]):>13s}"
              f" {'-' + str(removed_by_group[group]):>9s} {'+' + str(added_live[group]):>14s}")
    print()
    print(f"  intent re-judgement of the {sum(intent_split.values())} added: "
          f"{dict(sorted(intent_split.items()))}")
    print()
    print(f"CONTROL SIDE as recorded:   +{added_by_group['control']}")
    print(f"CONTROL SIDE under intent v4.1+: +{added_live['control']}")
    for row in sorted(changed, key=lambda r: (r["group"], r["task_id"])):
        print(f"  [{row['group']:11s}] {row['task_id']}  +{row['added']}  -{row['removed']}"
              f"  ({row['run']} {row['case']})")
    if args.json:
        Path(args.json).write_text(json.dumps({
            "produced_by": "scripts/acceptance/publication_rule_replay.py",
            "new_rule": PUBLICATION_POLICY_SCHEMA_VERSION,
            "ledgers_with_publication_rows": files,
            "publication_policy_rows": policy_rows,
            "rows_with_a_certified_set": len(results),
            "comparable": len(comparable),
            "unreplayable": unreplayable,
            "replay_disagrees": mismatched,
            "added_by_group": dict(added_by_group),
            "removed_by_group": dict(removed_by_group),
            "added_by_group_intent_current": dict(added_live),
            "intent_today_split": dict(intent_split),
            "changed": changed,
        }, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
