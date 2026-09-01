#!/usr/bin/env python3
"""Measure F's discrimination at the candidate unit, offline and unpriced.

Wave 5 (D-064) could not compare F's four graded fields at the unit the product
actually emits: its control arm produced one candidate against twenty-five, so
one side of the comparison was empty. This script changes the *measurement
population*, not the signal. It reuses D-064's four recorded raw values verbatim
and splits the candidates already on record by whether the anchor lands on the
corpus's own head-side labelled defect region.

Three properties of that split are load-bearing and are recorded in the artifact
rather than left to the reader:

*   The grouping is **anchor overlap**, not detection. ``INV-TRUTH-001`` states
    that location overlap cannot establish correctness or detection, and nothing
    here claims it does. The label defended is "does / does not anchor on the
    corpus's labelled defect region for this case".
*   It is deliberately **not** ``matcher.match_findings``. That function scores
    surfaced, differentially reproduced predictions one-to-one against truth.
    None of these candidates ever purchased V, so none is surfaced and none has a
    repro status; feeding them through it would return an empty set, and forging
    the two fields to get past the guard would be fabrication. The tolerance
    (``DEFAULT_LINE_SLACK``), the sweep ladder and the unlabelled-hunk rule are
    imported from that module so the numbers stay tied to D-062's
    pre-registration; the one-to-one assignment is dropped on purpose, because
    two candidates naming the same defect are both on it.
*   Everything is read from committed artifacts. No model call, no execution, no
    generation. D-063 recorded that the changed generation prompt makes any new
    run incomparable with D-059 on generation quality; no generation happens
    here, so that incomparability does not enter.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from attest.benchmark.artifacts import write_canonical_json
from attest.benchmark.matcher import (
    DEFAULT_LINE_SLACK,
    LINE_SLACK_SWEEP,
    hunk_labelling,
)
from attest.benchmark.schema import load_manifest

SCHEMA_VERSION = "attest.candidate-unit-discrimination.v1"
FIELDS = ("commits", "repair_share", "distinct_authors", "days_since_last_change")
ON = "on_labelled_defect"
OFF = "off_labelled_defect"
CONTROL = "developer_fix_control_head"
# Caps swept for the offline pricing counterfactual. 1.2 is the owner's figure;
# the rest bracket it so the reported zero is attributable to a number and not
# to the choice of one cap.
CAP_LADDER = (1.2, 1.5, 2.0, 3.0, 3.34, 4.0, 5.0)
SURFACING_THRESHOLD = 10.0


def _anchor_distance(line: int, start: int, end: int) -> int:
    if start <= line <= end:
        return 0
    return min(abs(line - start), abs(line - end))


def _normal(path: str) -> str:
    return path.replace("\\", "/")


def _nearest(
    truths: Sequence[Any], case_id: str, file: str, line: int
) -> tuple[int | None, str | None]:
    """Distance to the closest labelled span in the same case and file."""
    best: tuple[int, str] | None = None
    for truth in truths:
        if truth.case_id != case_id or _normal(truth.file) != _normal(file):
            continue
        distance = _anchor_distance(line, truth.start_line, truth.end_line)
        if best is None or distance < best[0]:
            best = (distance, truth.defect_id)
    return (None, None) if best is None else best


def _summary(values: Sequence[float]) -> dict[str, object]:
    if not values:
        return {"n": 0, "values": []}
    ordered = sorted(values)

    def percentile(fraction: float) -> float:
        if len(ordered) == 1:
            return ordered[0]
        position = fraction * (len(ordered) - 1)
        low = int(position)
        high = min(low + 1, len(ordered) - 1)
        return ordered[low] + (ordered[high] - ordered[low]) * (position - low)

    return {
        "n": len(ordered),
        "min": ordered[0],
        "p25": round(percentile(0.25), 6),
        "median": round(percentile(0.5), 6),
        "p75": round(percentile(0.75), 6),
        "max": ordered[-1],
        "mean": round(sum(ordered) / len(ordered), 6),
        "values": ordered,
    }


def _band(value: float, reference: Sequence[float]) -> str:
    """Which quartile band of the in-repository reference `value` falls in."""
    if not reference:
        return "no_reference"
    below = sum(1 for item in reference if item < value)
    tied = sum(1 for item in reference if item == value)
    fraction = (below + tied / 2) / len(reference)
    if fraction < 0.25:
        return "Q1"
    if fraction < 0.5:
        return "Q2"
    if fraction < 0.75:
        return "Q3"
    return "Q4"


def _rows(
    manifest: Any,
    wave5: dict[str, Any],
    heat: dict[str, Any],
    line_slack: int,
) -> list[dict[str, object]]:
    heat_rows = {
        (row["case_id"], row["finding_id"]): row for row in heat["per_candidate"]["rows"]
    }
    unlabelled = {
        case.case_id: hunk_labelling(case).unlabelled_hunks for case in manifest.cases
    }
    rows: list[dict[str, object]] = []
    for case in wave5["cases"]:
        case_id = case["case_id"]
        for candidate in case["candidates"]:
            key = (case_id, candidate["finding_id"])
            heat_row = heat_rows.get(key)
            if heat_row is None:
                raise ValueError(f"no recorded F row for {key}")
            file = candidate["anchor"]["file"]
            line = int(candidate["anchor"]["line"])
            distance, defect_id = _nearest(manifest.truth_defects, case_id, file, line)
            if case["role"] == "developer_fix_control":
                group = CONTROL
            elif distance is not None and distance <= line_slack:
                group = ON
            else:
                group = OFF
            rows.append(
                {
                    "case_id": case_id,
                    "pair_id": case["pair_id"],
                    "role": case["role"],
                    "finding_id": candidate["finding_id"],
                    "file": file,
                    "line": line,
                    "group": group,
                    "anchor_distance_to_nearest_label": distance,
                    "nearest_defect_id": defect_id,
                    "case_has_unlabelled_fix_hunks": unlabelled[case_id] > 0,
                    "S": candidate["S"],
                    "T": candidate["T"],
                    "wealth_ST": candidate["wealth"],
                    "claim": candidate["claim"],
                    "F_available": heat_row["available"],
                    "commits": heat_row["commits"],
                    "repair_share": heat_row["repair_share"],
                    "repair_commits": heat_row["repair_commits"],
                    "distinct_authors": heat_row["distinct_authors"],
                    "days_since_last_change": heat_row["days_since_last_change"],
                    "reference_date": heat_row["reference_date"],
                }
            )
    return rows


def _reference(heat: dict[str, Any], projects: Iterable[str]) -> dict[str, list[float]]:
    """Non-defect anchor lines from the same repository, as a percentile ruler."""
    prefixes = tuple(projects)
    reference: dict[str, list[float]] = {field: [] for field in FIELDS}
    for row in heat["per_anchor_line"]["rows"]:
        if row["group"] != "non_defect_line":
            continue
        if not row["file"].startswith(prefixes):
            continue
        for field in FIELDS:
            value = row.get(field)
            if value is not None:
                reference[field].append(float(value))
    return {field: sorted(values) for field, values in reference.items()}


def _within_case_variation(rows: Sequence[dict[str, Any]]) -> dict[str, object]:
    """How much of F's spread is between cases rather than inside one.

    A priced F would multiply one candidate against another **on the same head**.
    If F is near-constant inside a case it cannot re-order anything a reviewer
    sees in one review, whatever it does across a corpus. That is a property of
    the recorded values, so it is computed rather than argued.
    """
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_case.setdefault(str(row["case_id"]), []).append(row)
    per_field: dict[str, object] = {}
    for field in FIELDS:
        cases = []
        for case_id, case_rows in sorted(by_case.items()):
            values = [row[field] for row in case_rows if row[field] is not None]
            cases.append(
                {
                    "case_id": case_id,
                    "candidates": len(case_rows),
                    "defined": len(values),
                    "distinct_values": len(set(values)),
                    "spread": (max(values) - min(values)) if values else None,
                }
            )
        multi = [case for case in cases if case["candidates"] > 1]
        per_field[field] = {
            "cases": cases,
            "multi_candidate_cases": len(multi),
            "multi_candidate_cases_with_one_distinct_value": sum(
                1 for case in multi if case["distinct_values"] <= 1
            ),
        }
    return per_field


def _counterfactual(rows: Sequence[dict[str, Any]], caps: Sequence[float]) -> list[dict]:
    out = []
    for cap in caps:
        crossings = {ON: [], OFF: [], CONTROL: []}
        for row in rows:
            before = float(row["wealth_ST"])
            after = before * cap
            if before < SURFACING_THRESHOLD <= after:
                crossings[str(row["group"])].append(row["finding_id"])
        out.append(
            {
                "F_cap": cap,
                "required_wealth_ST": round(SURFACING_THRESHOLD / cap, 6),
                "crossings": {group: sorted(ids) for group, ids in crossings.items()},
                "crossing_counts": {group: len(ids) for group, ids in crossings.items()},
            }
        )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--wave5", type=Path, required=True)
    parser.add_argument("--heat", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--line-slack", type=int, default=DEFAULT_LINE_SLACK)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    wave5 = json.loads(args.wave5.read_text(encoding="utf-8"))
    heat = json.loads(args.heat.read_text(encoding="utf-8"))

    rows = _rows(manifest, wave5, heat, args.line_slack)
    projects = tuple(sorted({row["file"].split("/")[0] for row in rows}))
    reference = _reference(heat, projects)

    for row in rows:
        row["percentile_band"] = {
            field: _band(float(row[field]), reference[field])
            if row[field] is not None
            else None
            for field in FIELDS
        }

    groups = (ON, OFF, CONTROL)
    distributions = {
        group: {
            field: _summary(
                [
                    float(row[field])
                    for row in rows
                    if row["group"] == group and row[field] is not None
                ]
            )
            for field in FIELDS
        }
        for group in groups
    }
    bands = {
        group: {
            field: {
                band: sum(
                    1
                    for row in rows
                    if row["group"] == group and row["percentile_band"][field] == band
                )
                for band in ("Q1", "Q2", "Q3", "Q4")
            }
            for field in FIELDS
        }
        for group in groups
    }
    sweep = {
        str(slack): {
            group: sum(1 for row in _rows(manifest, wave5, heat, slack) if row["group"] == group)
            for group in groups
        }
        for slack in LINE_SLACK_SWEEP
    }

    document = {
        "schema_version": SCHEMA_VERSION,
        "signal_schema_version": heat["signal_schema_version"],
        "priced": False,
        "paid_calls": 0,
        "spend_usd": 0.0,
        "line_slack": args.line_slack,
        "line_slack_sweep_group_sizes": sweep,
        "surfacing_threshold": SURFACING_THRESHOLD,
        "grouping_rule": (
            "anchor overlap with the corpus head-side labelled defect span for the same "
            "case and file, within line_slack; not a detection claim (INV-TRUTH-001), and "
            "not matcher.match_findings, which scores surfaced reproduced predictions only"
        ),
        "percentile_reference": {
            "description": (
                "non-defect anchor lines recorded by D-064 for the same repository, used "
                "as an in-repository ruler"
            ),
            "projects": list(projects),
            "n": {field: len(values) for field, values in reference.items()},
        },
        "group_sizes": {group: sum(1 for row in rows if row["group"] == group) for group in groups},
        "distributions": distributions,
        "percentile_bands": bands,
        "pricing_counterfactual": _counterfactual(rows, CAP_LADDER),
        "pricing_counterfactual_note": (
            "A flat cap multiplies every candidate identically, so the crossing set is "
            "exactly {S*T >= 10/cap}: a function of S and T alone that carries no F "
            "information. At the owner's cap of 1.2 the question is moot for any "
            "grading of F, because a multiplier bounded by 1.2 needs S*T >= 8.334 and "
            "the observed maximum is 3.0."
        ),
        "within_case_variation": _within_case_variation(rows),
        "observed_max_wealth_ST": max(float(row["wealth_ST"]) for row in rows),
        "rows": rows,
        "limitations": [
            "F stays unpriced: it buys no wealth, orders nothing and reaches no "
            "publication path. The counterfactual is arithmetic on recorded values.",
            "Anchor overlap groups candidates; it does not establish that an off-label "
            "candidate is defect-free, nor that an on-label one is a true detection.",
            "A fix hunk that is a pure insertion has no head-side span, so an off-label "
            "candidate on such a case is weaker evidence; the flag is per row.",
            "n = 26 from one project and one run. No significance test was run and no "
            "statistical conclusion may be read into these distributions.",
            "The candidates never purchased V, so every recorded wealth is exactly S*T.",
            "No model call and no execution: this reuses committed artifacts only.",
        ],
    }
    write_canonical_json(args.output, document)
    print(json.dumps({"output": str(args.output), "group_sizes": document["group_sizes"]}))


if __name__ == "__main__":
    main()
