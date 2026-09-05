"""Yellow (b) second class offline: how often does exception propagation speak?

D-164 builds the level; this runs it over the same 79 units the null/Optional
class was measured on -- 11 forward pairs and 68 null controls -- and reports
the numbers that decide whether it may ever be author-visible:

    the trigger rate, per population
    which premise voided each hypothesis that did not survive
    the number of control units it would speak on (> 3% is not adopted)

    scan --population forward|controls|both --json <out>

**Free.** Unlike the null/Optional class, every premise here is decided by
`ast` and `git`: the model is only asked to write the sentence, and only after
all three premises already hold. This driver never calls a model at all -- it
records the deterministic sentence, which is what is published when the model's
is refused anyway.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from nullability_scan import (  # noqa: E402
    changed_lines,
    clone_of,
    git,
    tree_sources,
    units,
)

from attest.review.impact import build_call_graph, changed_functions  # noqa: E402
from attest.review.propagation import (  # noqa: E402
    PROPAGATION_POLICY_VERSION,
    notes_for_change,
)

CONTROL_CEILING = 0.03  # the owner's bar: above this the class is not adopted


def scan_unit(unit: dict[str, str]) -> dict[str, object]:
    repo = clone_of(unit["repo"])
    row: dict[str, object] = {**unit, "ok": False}
    if not repo.is_dir():
        row["error"] = f"no clone at {repo}"
        return row
    try:
        touched = changed_lines(repo, unit["base"], unit["head"])
        head_sources = tree_sources(repo, unit["head"])
    except RuntimeError as error:
        row["error"] = str(error)[:160]
        return row

    base_sources: dict[str, str] = {}
    changed = []
    for path, lines in sorted(touched.items()):
        head_source = head_sources.get(path)
        if head_source is None:
            continue
        try:
            base_sources[path] = git(repo, "show", f"{unit['base']}:{path}")
        except RuntimeError:
            continue
        changed.extend(
            changed_functions(
                path=path,
                head_source=head_source,
                base_source=base_sources[path],
                changed_lines=lines,
            )
        )
    graph = build_call_graph(head_sources)
    trace: list[str] = []
    notes = notes_for_change(
        graph, changed, head_sources=head_sources, base_sources=base_sources, trace=trace
    )
    row.update(
        {
            "ok": True,
            "changed_functions": len(changed),
            "notes": len(notes),
            "lines": [
                {
                    "at": f"{note.path}:{note.line}",
                    "callee": note.callee,
                    "exception": note.exception,
                    "evidence": note.evidence,
                    "caller": f"{note.caller_path}:{note.caller_line}",
                    "sentence": note.sentence,
                }
                for note in notes
            ],
            "voided": dict(Counter(trace)),
            "spend_usd": 0.0,
        }
    )
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan")
    scan.add_argument("--population", choices=("forward", "controls", "both"), default="both")
    scan.add_argument("--json", required=True)
    args = parser.parse_args(argv)

    population = units(args.population)
    rows = []
    for index, unit in enumerate(population, start=1):
        row = scan_unit(unit)
        rows.append(row)
        print(
            f"[{index}/{len(population)}] {unit['population']} {unit['repo']} "
            f"{unit['head'][:10]} notes={row.get('notes', '-')} {row.get('error', '')}",
            flush=True,
        )

    by_population: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = by_population.setdefault(
            str(row["population"]), {"units": 0, "scanned": 0, "spoke": 0, "notes": 0}
        )
        bucket["units"] += 1
        if row.get("ok"):
            bucket["scanned"] += 1
            bucket["notes"] += int(row.get("notes", 0) or 0)
            bucket["spoke"] += 1 if row.get("notes") else 0
    for bucket in by_population.values():
        bucket["trigger_rate"] = (  # type: ignore[assignment]
            round(bucket["spoke"] / bucket["scanned"], 4) if bucket["scanned"] else None
        )
    controls = by_population.get("controls", {})
    control_rate = controls.get("trigger_rate")
    payload = {
        "schema_version": "attest.propagation-scan.v1",
        "policy_version": PROPAGATION_POLICY_VERSION,
        "generated": datetime.now(UTC).isoformat(),
        "control_ceiling": CONTROL_CEILING,
        "control_rate": control_rate,
        "adoptable": control_rate is not None and control_rate <= CONTROL_CEILING,
        "voided": dict(
            Counter(
                reason
                for row in rows
                for reason, count in (row.get("voided") or {}).items()  # type: ignore[union-attr]
                for _ in range(int(count))
            )
        ),
        "exceptions": dict(
            Counter(
                str(line["exception"]) for row in rows for line in row.get("lines", [])  # type: ignore[union-attr]
            )
        ),
        "by_population": by_population,
        "rows": rows,
    }
    Path(args.json).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    summary = {
        k: payload[k] for k in ("control_rate", "adoptable", "voided", "by_population")
    }
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
