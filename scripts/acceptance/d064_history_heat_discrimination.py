#!/usr/bin/env python3
"""Measure the graded F signal's discrimination, not its trigger rate.

D-064 redefines F from a boolean ("is the anchor line owned by a recent revert
or hotfix?", which fired 0/26) to four graded raw values per anchor. The
question this script answers is whether those values separate defect regions
from non-defect regions at all. It is a measurement, not a promotion: F stays
unpriced, buys no wealth, and touches no decision.

Two units are reported, because the two answer different questions.

* **Per candidate** -- the unit the review actually produces. Every candidate
  of the 2026-09-01 history counterfactual gets its four raw values. This is
  the honest picture of what the product would record, and it shows directly
  how few control-arm candidates exist to compare against.
* **Per anchor line** -- the unit that can carry a balanced comparison. For
  each replay case the labelled head-side defect lines form the bug group, and
  an equal number of deterministically chosen lines from the same file and the
  same revision, far from every changed location, form the control group.

Nothing here is a significance test. The samples are small and the script
prints distributions, never a p-value or a conclusion drawn from one.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from attest.benchmark.artifacts import write_canonical_json
from attest.benchmark.schema import load_manifest, manifest_binding_bytes
from attest.review.history import (
    HISTORY_LOOKBACK_DAYS,
    HISTORY_SIGNAL_SCHEMA_VERSION,
    REPAIR_SUBJECT_PATTERN,
    inspect_history_signal,
)
from attest.review.schema import Finding

COUNTERFACTUAL = Path(
    "docs/acceptance/evidence/2026-09-01-wave5-history-counterfactual/result.json"
)
CONTROL_EXCLUSION_RADIUS = 10
FIELDS = ("commits", "repair_share", "distinct_authors", "days_since_last_change")


def _finding(path: str, line: int) -> Finding:
    return Finding(
        claim="observation only",
        file=path,
        line=line,
        failure_scenario="observation only",
        falsification_plan="observation only",
    )


def _checkout(root: Path, source_id: str, pair_id: str, role: str) -> Path:
    folder = "replay" if role == "historical_bug_replay" else "control"
    path = root / source_id / pair_id / folder
    if not (path / ".git").exists():
        raise SystemExit(f"missing prepared checkout {path}")
    return path


def _file_length(repo: Path, path: str) -> int:
    completed = subprocess.run(
        ["git", "-C", str(repo), "show", f"HEAD:{path}"],
        capture_output=True,
        text=True,
        errors="replace",
    )
    if completed.returncode != 0:
        return 0
    return len(completed.stdout.splitlines())


def _control_lines(
    repo: Path, path: str, excluded: list[tuple[int, int]], count: int
) -> list[int]:
    """Deterministic non-defect lines from the same file at the same revision.

    Chosen by walking the file at a fixed stride from a fixed offset, so the
    selection depends only on the file and the requested count -- never on what
    the signal turns out to say about any line.
    """
    length = _file_length(repo, path)
    if length <= 0 or count <= 0:
        return []

    def blocked(line: int) -> bool:
        return any(
            start - CONTROL_EXCLUSION_RADIUS <= line <= end + CONTROL_EXCLUSION_RADIUS
            for start, end in excluded
        )

    stride = max(1, length // (count + 1))
    chosen: list[int] = []
    line = stride
    while line <= length and len(chosen) < count:
        if not blocked(line):
            chosen.append(line)
        line += stride
    line = 1
    while line <= length and len(chosen) < count:
        if not blocked(line) and line not in chosen:
            chosen.append(line)
        line += 1
    return sorted(chosen)


def _row(repo: Path, path: str, line: int, **extra: object) -> dict[str, object]:
    signal = inspect_history_signal(repo, _finding(path, line))
    return {"file": path, "line": line, **extra, **signal.to_json_dict()}


def _distribution(rows: list[dict[str, object]], field: str) -> dict[str, object]:
    values = sorted(
        float(row[field]) for row in rows if row.get(field) is not None
    )
    if not values:
        return {"n": 0, "min": None, "p25": None, "median": None, "p75": None, "max": None}

    def at(fraction: float) -> float:
        index = min(len(values) - 1, max(0, int(round(fraction * (len(values) - 1)))))
        return values[index]

    return {
        "n": len(values),
        "min": values[0],
        "p25": at(0.25),
        "median": at(0.5),
        "p75": at(0.75),
        "max": values[-1],
        "mean": round(sum(values) / len(values), 6),
        "values": values,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", required=True, type=Path)
    parser.add_argument(
        "--manifest", type=Path, default=Path("benchmarks/attest-v1/manifest.json")
    )
    parser.add_argument("--counterfactual", type=Path, default=COUNTERFACTUAL)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    cases = {case.case_id: case for case in manifest.cases}
    truths: dict[str, list] = {}
    for defect in manifest.truth_defects:
        truths.setdefault(defect.case_id, []).append(defect)

    counterfactual = json.loads(args.counterfactual.read_text(encoding="utf-8"))

    # ---- unit 1: per candidate -------------------------------------------
    candidate_rows: list[dict[str, object]] = []
    for case_payload in counterfactual["cases"]:
        case_id = str(case_payload["case_id"])
        case = cases.get(case_id)
        if case is None:
            continue
        repo = _checkout(args.corpus_root, case.source_id, case.pair_id, case.role)
        for candidate in case_payload["candidates"]:
            anchor = candidate["anchor"]
            candidate_rows.append(
                _row(
                    repo,
                    str(anchor["file"]),
                    int(anchor["line"]),
                    case_id=case_id,
                    pair_id=case.pair_id,
                    role=case.role,
                    finding_id=candidate["finding_id"],
                )
            )

    # ---- unit 2: per anchor line, balanced -------------------------------
    line_rows: list[dict[str, object]] = []
    for case in manifest.cases:
        if case.role != "historical_bug_replay":
            continue
        defects = truths.get(case.case_id, [])
        if not defects:
            continue
        repo = _checkout(args.corpus_root, case.source_id, case.pair_id, case.role)
        by_file: dict[str, list] = {}
        for defect in defects:
            by_file.setdefault(defect.file, []).append(defect)
        for path, file_defects in by_file.items():
            excluded = [
                (location.start_line, location.end_line)
                for location in case.changed_locations
                if location.path == path
            ]
            for defect in file_defects:
                for line in range(defect.start_line, defect.end_line + 1):
                    line_rows.append(
                        _row(
                            repo,
                            path,
                            line,
                            case_id=case.case_id,
                            pair_id=case.pair_id,
                            group="defect_line",
                        )
                    )
            wanted = sum(
                defect.end_line - defect.start_line + 1 for defect in file_defects
            )
            for line in _control_lines(repo, path, excluded, wanted):
                line_rows.append(
                    _row(
                        repo,
                        path,
                        line,
                        case_id=case.case_id,
                        pair_id=case.pair_id,
                        group="non_defect_line",
                    )
                )

    bug_candidates = [r for r in candidate_rows if r["role"] == "historical_bug_replay"]
    control_candidates = [
        r for r in candidate_rows if r["role"] == "developer_fix_control"
    ]
    defect_lines = [r for r in line_rows if r["group"] == "defect_line"]
    non_defect_lines = [r for r in line_rows if r["group"] == "non_defect_line"]

    artifact = {
        "schema_version": "attest.history-heat-discrimination.v1",
        "signal_schema_version": HISTORY_SIGNAL_SCHEMA_VERSION,
        "lookback_days": HISTORY_LOOKBACK_DAYS,
        "repair_pattern": REPAIR_SUBJECT_PATTERN,
        "manifest_sha256": __import__(
            "attest.benchmark.artifacts", fromlist=["sha256_bytes"]
        ).sha256_bytes(manifest_binding_bytes(manifest)),
        "priced": False,
        "paid_calls": 0,
        "spend_usd": 0.0,
        "per_candidate": {
            "rows": candidate_rows,
            "distributions": {
                "historical_bug_replay": {
                    field: _distribution(bug_candidates, field) for field in FIELDS
                },
                "developer_fix_control": {
                    field: _distribution(control_candidates, field) for field in FIELDS
                },
            },
        },
        "per_anchor_line": {
            "control_selection": (
                "fixed-stride lines from the same file and revision, at least "
                f"{CONTROL_EXCLUSION_RADIUS} lines from every changed location"
            ),
            "rows": line_rows,
            "distributions": {
                "defect_line": {
                    field: _distribution(defect_lines, field) for field in FIELDS
                },
                "non_defect_line": {
                    field: _distribution(non_defect_lines, field) for field in FIELDS
                },
            },
        },
        "limitations": [
            "F is unpriced: it buys no wealth, orders nothing and reaches no "
            "publication path.",
            "Samples are small. No significance test is run and no statistical "
            "conclusion is drawn; the distributions are printed side by side.",
            "The control-arm candidate group is whatever the product actually "
            "produced, which on this corpus is nearly empty.",
            "One corpus, one project. Nothing here generalises.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.out, artifact)
    print(
        f"candidates: bug {len(bug_candidates)}, control {len(control_candidates)}; "
        f"lines: defect {len(defect_lines)}, non-defect {len(non_defect_lines)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
