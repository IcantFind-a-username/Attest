"""Replay D-218's rule over every ledger this machine holds. Free (D-218).

The question the owner has to answer tomorrow is not *is the rule reasonable*.
It is **how often does it fire, and on what** — and in particular how often it
fires on a population with no defect in it, because that number is the noise
floor of a level nobody has seen yet.

Nothing here calls a model, executes anything or opens a socket. It reads
`.attest/**/ledger.jsonl`, applies the rule to the rows already there, renders
the line each one would have produced, and prints the counts by arm.

    python scripts/corpus/value_note_census.py --json out.json

**Two denominators, and they are not the same.** A ledger accumulates over every
run ever made against that case, under several policy versions; a *rate per run*
cannot be read out of it. What can be read is how many verification rows exist
and how many of them carry the drawer, and both are printed. D-177: a zero is
only reported beside the size of the input that produced it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.value_note import drawered_for_unknown_intent  # noqa: E402

# `E   AssertionError: assert <head> == <base>` -- the replay asserts what base
# produced, so the left side of a failing head run is what head produced. Used
# only for the ledgers written before the head observation was recorded (D-216).
_ASSERTION = re.compile(r"^E\s+AssertionError: assert (.+?) == (.+?)\s*$", re.M)

ARMS = {
    "held-out control": "a SWE-bench case with no defect: docs-only or test-only",
    "held-out defect": "a SWE-bench case carrying a reverted gold patch",
    "null control": "the G-NULL-001a populations, public clones with no known defect",
    "us-stock-helper": "the owner's own repository, real history",
    "corum": "a third-party clone, real history",
    "attest": "this repository's own reviews",
}


def _arm(relative: str) -> str:
    head = relative.split("/")
    if head[0] == "swebench" and len(head) > 2 and head[1] == "cases":
        return "held-out control" if "--" in head[2] else "held-out defect"
    if head[0] == "gnull":
        return "null control"
    return head[0]


def _unit(relative: str) -> str:
    head = relative.split("/")
    if head[0] == "swebench" and len(head) > 2:
        return head[2]
    return head[0] if len(head) < 2 else f"{head[0]}/{head[1]}"


def _head_side(row: dict) -> tuple[str, str]:
    """(head detail, base detail) recovered from a head run's captured output."""
    for entry in row.get("run_evidence") or []:
        if entry.get("side") != "head":
            continue
        found = _ASSERTION.search(str(entry.get("stdout") or ""))
        if found:
            return found.group(1).strip(), found.group(2).strip()
    return "", ""


def census(root: Path) -> dict:
    rows: list[dict] = []
    verifications = Counter()
    ledgers = Counter()
    for path in sorted(root.rglob("ledger.jsonl")):
        relative = path.relative_to(root).as_posix()
        arm, unit = _arm(relative), _unit(relative)
        ledgers[arm] += 1
        entries = []
        for line in path.read_text(errors="replace").splitlines():
            try:
                entries.append(json.loads(line))
            except ValueError:
                continue
        probes = {
            entry.get("finding_id"): entry
            for entry in entries
            if entry.get("kind") == "probe_observation"
        }
        for entry in entries:
            if entry.get("kind") != "verification":
                continue
            verifications[arm] += 1
            reason = str(entry.get("reason") or "")
            if not drawered_for_unknown_intent(reason):
                continue
            intent = entry.get("intent") or {}
            probe = probes.get(entry.get("finding_id")) or {}
            head_detail, base_detail = _head_side(entry)
            rows.append(
                {
                    "arm": arm,
                    "unit": unit,
                    "ledger": relative,
                    "finding_id": entry.get("finding_id"),
                    "path": intent.get("path", ""),
                    "line": intent.get("failing_assertion_line") or 0,
                    "expression": probe.get("expression", ""),
                    "base_kind": probe.get("observed_kind", ""),
                    "base_detail": probe.get("observed_detail", "") or base_detail,
                    # the head observation is only recorded from D-216 on; for
                    # everything already on disk it is recovered from the failing
                    # assertion, and where neither exists the row is counted and
                    # marked unrenderable rather than dropped
                    "head_detail": probe.get("head_detail", "") or head_detail,
                    "policy_version": intent.get("policy_version", ""),
                    "pinned_values": intent.get("pinned_values") or [],
                    "value_specified": intent.get("value_specified") or [],
                    "reason": reason[:200],
                }
            )
    return {
        "schema_version": "attest.value-note-census.v1",
        "arms": {
            arm: {
                "description": ARMS.get(arm, ""),
                "ledgers": ledgers[arm],
                "verification_rows": verifications[arm],
                "notes": sum(1 for row in rows if row["arm"] == arm),
                "renderable": sum(
                    1
                    for row in rows
                    if row["arm"] == arm and row["expression"] and row["head_detail"]
                ),
                "units_with_a_note": len({row["unit"] for row in rows if row["arm"] == arm}),
            }
            for arm in sorted(set(ledgers) | {row["arm"] for row in rows})
        },
        "rows": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT / ".attest" / "corpora")
    parser.add_argument("--json", dest="output", type=Path, default=None)
    parser.add_argument("--arm", default="", help="print every rendered line of one arm")
    args = parser.parse_args(argv)

    if not args.root.is_dir():
        print(f"no ledgers under {args.root}", file=sys.stderr)
        return 2
    result = census(args.root)
    width = max(len(arm) for arm in result["arms"]) if result["arms"] else 10
    print(f"{'arm'.ljust(width)} {'ledgers':>8} {'verif rows':>11} {'notes':>6} {'renderable':>11}")
    for arm, summary in result["arms"].items():
        print(
            f"{arm.ljust(width)} {summary['ledgers']:8} {summary['verification_rows']:11} "
            f"{summary['notes']:6} {summary['renderable']:11}"
        )
    if args.arm:
        print()
        for row in result["rows"]:
            if row["arm"] != args.arm:
                continue
            print(f"{row['unit']}  {row['path']}:{row['line']}  {row['expression']}")
            print(f"    base {row['base_detail']!r} -> head {row['head_detail']!r}")
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", "utf-8")
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
