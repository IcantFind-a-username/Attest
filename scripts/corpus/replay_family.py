"""Replay the publication policy over recorded corpus reviews (D-125).

Offline and free: no model call, no execution, no product run. For every task in
the given clones that has a `publication_policy` ledger row, this rebuilds the
inputs C-05 was given -- the eligible candidates with their anchors and
e-values, and the accepted receipts -- and asks `select_for_publication` twice:

  old   the PR-wide family, `m/alpha` over every eligible candidate in the review
  new   the per-change-unit family (D-125), `m_u/alpha` inside the anchor's file

The old replay is checked against what the run actually recorded; a task whose
old replay does not reproduce its own ledger row is reported as `unreplayable`
and excluded from the comparison rather than silently counted.

    .venv/bin/python scripts/corpus/replay_family.py --json report.json

`--exclude-unverifiable` drops receipts whose evidence bundle does not verify
offline (D-124), which is the corrected population.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.certification.selection import (  # noqa: E402
    FamilyPolicy,
    ScoredFinding,
    select_for_publication,
)
from attest.certification.types import (  # noqa: E402
    _ACCEPTED_RECEIPT_TOKEN,
    AcceptedReceipt,
    CertificationReceipt,
    CertifiedFinding,
    ExecutionRun,
    FindingAnchor,
)
from attest.certification.units import unit_counts  # noqa: E402
from attest.review.channels import V_CAP  # noqa: E402

CORPORA = ROOT / ".attest" / "corpora"
DEFAULT_CLONES = ("attest", "corum", "us-stock-helper")


@dataclass
class TaskReplay:
    """One review, replayed three ways.

    ``record_replay`` is the old rule over everything the run certified: it must
    reproduce the ledger, and a task where it does not is excluded from the
    comparison. ``old_published`` and ``new_published`` are the old and the new
    rule over the **D-124-corrected** certified set, which is the population the
    comparison is about.
    """

    task_id: str
    clone: str
    head_sha: str
    alpha: float
    eligible: int
    units: dict[str, int]
    recorded_published: list[str]
    record_replay: list[str]
    old_published: list[str]
    new_published: list[str]
    old_matches_record: bool
    recorded_under_new_rule: bool
    unverifiable_dropped: list[str]


def _rows(clone: Path) -> list[dict]:
    path = clone / ".attest" / "ledger.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _candidates(clone: Path) -> dict[str, list[dict]]:
    path = clone / ".attest" / "candidates.jsonl"
    if not path.exists():
        return {}
    by_task: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        by_task.setdefault(row["task_id"], []).append(row)
    return by_task


def _load_finding(bundle: Path, candidate: dict) -> CertifiedFinding | None:
    """Rebuild the certified finding from its bundle: the receipt gives the test
    digest the clusterer needs, the candidate row gives the anchor."""
    try:
        raw = json.loads((bundle / "receipt.json").read_bytes())
    except (OSError, ValueError):
        return None
    try:
        raw["head_runs"] = tuple(ExecutionRun(**run) for run in raw["head_runs"])
        raw["base_runs"] = tuple(ExecutionRun(**run) for run in raw["base_runs"])
        receipt = CertificationReceipt(**raw)
    except (TypeError, ValueError, KeyError):
        return None
    accepted = AcceptedReceipt._from_validated(receipt, _ACCEPTED_RECEIPT_TOKEN)
    anchor = FindingAnchor(path=candidate["file"], line=int(candidate["line"]))
    return CertifiedFinding.from_accepted_receipt(accepted, (anchor,))


def replay_clone(clone: Path, unverifiable: set[str], exclude: bool) -> list[TaskReplay]:
    rows = _rows(clone)
    candidates = _candidates(clone)
    certifications: dict[str, list[dict]] = {}
    for row in rows:
        if row.get("kind") == "certification":
            certifications.setdefault(str(row["task_id"]), []).append(row)
    out: list[TaskReplay] = []
    for row in rows:
        if row.get("kind") != "publication_policy":
            continue
        task_id = str(row["task_id"])
        stored = {c["finding_id"]: c for c in candidates.get(task_id, [])}
        eligible = [
            c
            for c in stored.values()
            if c.get("eligibility") == "regression" and c.get("action") != "discard"
        ]
        every: list[ScoredFinding] = []  # everything the run certified
        scored: list[ScoredFinding] = []  # the D-124-corrected certified set
        dropped: list[str] = []
        head_sha = ""
        for cert in certifications.get(task_id, []):
            if cert.get("outcome") != "accepted" or "bundle_path" not in cert:
                continue
            candidate = stored.get(str(cert["finding_id"]))
            if candidate is None:
                continue
            bundle = Path(str(cert["bundle_path"]))
            finding = _load_finding(bundle, candidate)
            if finding is None:
                continue
            head_sha = finding.accepted_receipt.receipt.head_sha
            # the e-value C-05 saw: the ranking wealth after the V channel
            item = ScoredFinding(finding, float(candidate["wealth"]) * V_CAP)
            every.append(item)
            if exclude and str(bundle.resolve()) in unverifiable:
                dropped.append(str(cert["finding_id"]))
                continue
            scored.append(item)
        alpha = float(row["alpha"])
        e_values = [float(c["wealth"]) * V_CAP for c in eligible]
        units = dict(unit_counts(c["file"] for c in eligible))
        cap = int(row["hard_cap"])
        # the pre-D-125 rule, expressed in the same code path: every unit is
        # given the whole review's eligible count, so every bar is m/alpha
        pr_wide = {unit: len(eligible) for unit in units}
        pr_policy = FamilyPolicy(
            alpha=alpha,
            eligible_count=len(eligible),
            hard_cap=cap,
            eligible_units=pr_wide,
        )
        record = select_for_publication(every, pr_policy, e_values)
        old = select_for_publication(scored, pr_policy, e_values)
        new = select_for_publication(
            scored,
            FamilyPolicy(
                alpha=alpha,
                eligible_count=len(eligible),
                hard_cap=cap,
                eligible_units=units,
            ),
            e_values,
        )

        def ids(selection) -> list[str]:  # type: ignore[no-untyped-def]
            return sorted(f.accepted_receipt.receipt.candidate_id for f in selection.published)

        recorded = sorted(str(x) for x in row["published"])
        # A row written under publication-policy v2 was produced by the new rule,
        # so it is the *new* replay that must reproduce it. Validating such a row
        # against the old rule reports a disagreement that is the decision, not a
        # replay failure -- and on the E-04 stratum-v2 units that disagreement is
        # exactly the finding: the old rule publishes nothing there.
        under_new_rule = str(row.get("schema_version", "")) == "attest.publication-policy.v2"
        out.append(
            TaskReplay(
                task_id=task_id,
                clone=clone.name,
                head_sha=head_sha,
                alpha=alpha,
                eligible=len(eligible),
                units=units,
                recorded_published=recorded,
                record_replay=ids(record),
                old_published=ids(old),
                new_published=ids(new),
                old_matches_record=(
                    ids(new) == recorded if under_new_rule else ids(record) == recorded
                ),
                recorded_under_new_rule=under_new_rule,
                unverifiable_dropped=dropped,
            )
        )
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clone", action="append", default=[], help="clone name under .attest/corpora"
    )
    parser.add_argument("--json", type=Path)
    parser.add_argument(
        "--exclude-unverifiable",
        action="store_true",
        help="drop receipts whose bundle does not verify offline (D-124)",
    )
    parser.add_argument(
        "--reverification",
        type=Path,
        default=ROOT / "docs/acceptance/evidence/2026-09-04-bundle-reverification.json",
    )
    args = parser.parse_args(argv)

    unverifiable: set[str] = set()
    if args.reverification.exists():
        report = json.loads(args.reverification.read_text(encoding="utf-8"))
        unverifiable = {b["path"] for b in report["bundles"] if not b["ok"]}

    clones = args.clone or list(DEFAULT_CLONES)
    replays: list[TaskReplay] = []
    for name in clones:
        replays.extend(replay_clone(CORPORA / name, unverifiable, args.exclude_unverifiable))

    unreplayable = [r for r in replays if not r.old_matches_record]
    comparable = [r for r in replays if r.old_matches_record]
    changed = [r for r in comparable if r.old_published != r.new_published]
    payload = {
        "schema_version": "attest.family-replay.v1",
        "clones": clones,
        "exclude_unverifiable": args.exclude_unverifiable,
        "tasks": len(replays),
        "comparable": len(comparable),
        "unreplayable": [r.task_id for r in unreplayable],
        "old_published_total": sum(len(r.old_published) for r in comparable),
        "new_published_total": sum(len(r.new_published) for r in comparable),
        "rows": [
            {
                "task_id": r.task_id,
                "clone": r.clone,
                "head_sha": r.head_sha,
                "alpha": r.alpha,
                "eligible": r.eligible,
                "units": r.units,
                "recorded_published": r.recorded_published,
                "record_replay": r.record_replay,
                "old_published": r.old_published,
                "new_published": r.new_published,
                "replayable": r.old_matches_record,
                "recorded_under_new_rule": r.recorded_under_new_rule,
                "unverifiable_dropped": r.unverifiable_dropped,
            }
            for r in replays
        ],
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{len(replays)} tasks, {len(comparable)} replayable, "
        f"published old {payload['old_published_total']} -> new {payload['new_published_total']}, "
        f"{len(changed)} tasks changed"
    )
    for r in unreplayable:
        print(
            f"  UNREPLAYABLE {r.clone} {r.task_id}: "
            f"replay {r.record_replay} vs record {r.recorded_published}"
        )
    for r in changed:
        print(
            f"  {r.clone} {r.task_id} head={r.head_sha[:10]} m={r.eligible} "
            f"units={len(r.units)}: {r.old_published} -> {r.new_published}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
