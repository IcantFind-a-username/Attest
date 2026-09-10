#!/usr/bin/env python3
"""What changed between two runs of the same held-out population.

`heldout_v2.py table` says what one run measured. This says what *moved*, which
is the only question a re-measurement asks: the population is fixed by
construction (D-208 restores it rather than re-screening), so every difference
between two runs is the product's, not the corpus's.

Per case it compares the two facts a run records without needing its ledger --
whether anything surfaced, and the reason it deferred -- and it classifies the
reason into the loss categories the 2026-09-12 report is denominated in, so the
before/after table is the one already in `docs/acceptance/`.

Reads only. No model, no execution, no network.

    heldout_compare.py --old docs/acceptance/evidence/2026-09-12-heldout-supported-run.json \\
                       --new .attest/corpora/swebench/results
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from heldout_v2 import wilson  # noqa: E402 - the one definition, per green on PR #31

# The loss categories the 2026-09-12 report uses, longest-prefix first so
# "child process" is never swallowed by a broader phrase.
CATEGORIES: tuple[tuple[str, str], ...] = (
    ("surfaced", "surfaced"),
    ("collection/import/syntax", "probe does not collect"),
    ("attempted to create a child process", "process guard: child process"),
    ("attempted to create a thread", "process guard: thread"),
    ("behavior change confirmed", "intent clause"),
    ("value change confirmed", "intent clause"),
    ("intent unknown", "intent clause"),
    ("intent stated in", "intent clause"),
    ("intent:", "intent clause"),
    ("no observation", "probe recorded nothing"),
    ("not stable", "observation not stable"),
    ("unfaithful", "unfaithful generated test"),
    ("binding:", "binding"),
    ("bootstrap", "environment bootstrap failed"),
    ("unsupported", "stated refusal"),
)


def classify(row: dict) -> str:
    if int(row.get("surfaced_count") or 0) > 0:
        return "surfaced"
    reason = str(row.get("deferred_reason") or "").lower()
    if not reason:
        return "silent, no reason recorded"
    for marker, name in CATEGORIES:
        if marker.lower() in reason:
            return name
    return f"other: {reason[:50]}"


def load_old(path: Path) -> dict[str, dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload["results"] if isinstance(payload, dict) else payload
    return {str(r["case"]): r for r in rows}


def load_new(path: Path) -> dict[str, dict]:
    if path.is_file():
        return load_old(path)
    rows: dict[str, dict] = {}
    for entry in sorted(path.glob("*.json")):
        row = json.loads(entry.read_text(encoding="utf-8"))
        case = str(row.get("case") or entry.stem)
        rows[case] = row
    return rows


def _rate(rows: dict[str, dict]) -> tuple[int, int]:
    surfaced = sum(1 for r in rows.values() if int(r.get("surfaced_count") or 0) > 0)
    return surfaced, len(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--old", type=Path, required=True)
    parser.add_argument("--new", type=Path, required=True)
    args = parser.parse_args(argv)

    old, new = load_old(args.old), load_new(args.new)
    if not new:
        print(f"no results under {args.new}", file=sys.stderr)
        return 1

    print(f"old: {len(old)} cases   new: {len(new)} cases")
    print(
        "denominator here is every case RUN. `heldout_v2.py table` reports the\n"
        "crash-class denominator G-RECALL-002 is stated in (2 of 28 = 7.1% on\n"
        "2026-09-12); these two rates are not the same number."
    )
    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))
    if only_old:
        print(f"  run in the old only ({len(only_old)}): {', '.join(only_old)}")
    if only_new:
        print(f"  run in the new only ({len(only_new)}): {', '.join(only_new)}")

    for label, rows in (("old", old), ("new", new)):
        surfaced, total = _rate(rows)
        low, high = wilson(surfaced, total)
        spend = sum(float(r.get("spend_usd") or 0.0) for r in rows.values())
        pct = 100 * surfaced / total if total else 0.0
        print(
            f"\n{label}: surfaced {surfaced} of {total} cases RUN = {pct:.1f}%"
            f"  Wilson 95% [{100 * low:.1f}%, {100 * high:.1f}%]   spend ${spend:.4f}"
        )
        for name, n in Counter(classify(r) for r in rows.values()).most_common():
            print(f"  {n:3d}  {name}")

    shared = sorted(set(old) & set(new))
    moved = [(c, classify(old[c]), classify(new[c])) for c in shared]
    moved = [m for m in moved if m[1] != m[2]]
    print(f"\ncases whose class moved: {len(moved)} of {len(shared)} run in both")
    for case, before, after in moved:
        arrow = "  <-- NEW RECEIPT" if after == "surfaced" else ""
        lost = "  <-- LOST" if before == "surfaced" else ""
        print(f"  {case}: {before} -> {after}{arrow}{lost}")
    return 0


if __name__ == "__main__":  # pragma: no cover - a driver
    raise SystemExit(main())
