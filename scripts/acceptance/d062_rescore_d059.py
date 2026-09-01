#!/usr/bin/env python3
"""Re-score D-059's recorded findings under the old and the new matcher rule.

No model call and no execution: the four surfaced findings, their anchors and
their oracle receipts are read out of the frozen D-059 record, and the frozen
`attest-v1` manifest supplies the truth spans and the changed locations. Only
the matcher runs.

Two receipt sets are scored, because D-061 corrected one of them:

* ``as_recorded``   -- the receipts exactly as D-059 wrote them.
* ``d061_corrected`` -- with the one refutation that came from the oracle's own
  broken API probe replaced by the receipt its corrected reproduction produced.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json
from attest.benchmark.matcher import (
    DEFAULT_LINE_SLACK,
    LINE_SLACK_SWEEP,
    hunk_labelling,
    match_findings,
)
from attest.benchmark.schema import (
    Placement,
    Prediction,
    load_manifest,
    manifest_binding_bytes,
)

RUN_ID = "d059-wave4-replay-9b"
OLD_LINE_SLACK = 0

# The four author-visible findings of the D-059 wave-4 replay, as recorded in
# docs/2026-09-01-d059-audit-window-and-repeat-semantics.md.
FINDINGS = (
    ("fdbff9370c", "case-2dad0cb4c5b5", "black.py", 735, "buggy_fail_fixed_pass"),
    ("b1e7f57dc2", "case-99a012693940", "black.py", 2949, "buggy_fail_fixed_pass"),
    ("ed1d3ea89b", "case-c6f141a2be09", "black.py", 2495, "buggy_fail_fixed_fail"),
    ("20d686ba82", "case-c22190aa4fc9", "black.py", 610, "buggy_fail_fixed_pass"),
)
# D-061: the oracle's refutation of ed1d3ea89b was its own test raising on both
# sides; the corrected reproduction returns buggy_fail_fixed_pass.
D061_CORRECTIONS = {"ed1d3ea89b": "buggy_fail_fixed_pass"}


def _predictions(corrected: bool) -> tuple[Prediction, ...]:
    return tuple(
        Prediction(
            finding_id=finding_id,
            case_id=case_id,
            file=path,
            line=line,
            placement=Placement.INLINE,
            action="surface",
            repro_status=(
                D061_CORRECTIONS.get(finding_id, status) if corrected else status
            ),
            evidence_class="regression_reproduced",
        )
        for finding_id, case_id, path, line, status in FINDINGS
    )


def _score(manifest, predictions, line_slack: int) -> dict[str, object]:
    cases = {case.case_id: case for case in manifest.cases}
    truths: dict[str, tuple] = {}
    for defect in manifest.truth_defects:
        truths[defect.case_id] = truths.get(defect.case_id, ()) + (defect,)
    rows = []
    for prediction in predictions:
        case = cases[prediction.case_id]
        result = match_findings(
            truths.get(prediction.case_id, ()),
            (prediction,),
            line_slack=line_slack,
            cases=(case,),
        )[0]
        labelling = hunk_labelling(case)
        rows.append(
            {
                "finding_id": prediction.finding_id,
                "case_id": prediction.case_id,
                "anchor": f"{prediction.file}:{prediction.line}",
                "repro_status": prediction.repro_status,
                "matched": result.matched,
                "defect_id": result.defect_id,
                "unlabelled_hunks_present": result.unlabelled_hunks_present,
                "labelled_truth_spans": [
                    f"{defect.start_line}-{defect.end_line}"
                    for defect in truths.get(prediction.case_id, ())
                ],
                "hunk_labelling": labelling.to_json_dict(),
            }
        )
    return {
        "line_slack": line_slack,
        "matched": sum(1 for row in rows if row["matched"]),
        "surfaced": len(rows),
        "findings": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=Path("benchmarks/attest-v1/manifest.json")
    )
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    arms: dict[str, object] = {}
    for label, corrected in (("as_recorded", False), ("d061_corrected", True)):
        predictions = _predictions(corrected)
        cases = {case.case_id: case for case in manifest.cases}
        truths: dict[str, tuple] = {}
        for defect in manifest.truth_defects:
            truths[defect.case_id] = truths.get(defect.case_id, ()) + (defect,)
        sweep = {}
        for value in (*LINE_SLACK_SWEEP, 16, 20):
            total = 0
            for prediction in predictions:
                total += sum(
                    1
                    for result in match_findings(
                        truths.get(prediction.case_id, ()),
                        (prediction,),
                        line_slack=value,
                        cases=(cases[prediction.case_id],),
                    )
                    if result.matched
                )
            sweep[str(value)] = total
        arms[label] = {
            "old_rule": _score(manifest, predictions, OLD_LINE_SLACK),
            "new_rule": _score(manifest, predictions, DEFAULT_LINE_SLACK),
            "line_slack_sweep": sweep,
        }

    artifact = {
        "schema_version": "attest.matcher-rescore.v1",
        "source_run_id": RUN_ID,
        "manifest_sha256": sha256_bytes(manifest_binding_bytes(manifest)),
        "old_line_slack": OLD_LINE_SLACK,
        "new_line_slack": DEFAULT_LINE_SLACK,
        "paid_calls": 0,
        "spend_usd": 0.0,
        "arms": arms,
        "limitations": [
            "Location binding only: per INV-TRUTH-001 an anchor overlapping a "
            "labelled span establishes neither correctness nor detection.",
            "No precision or recall statement may be derived from these counts.",
            "Four findings from one run; the matcher is re-scored, nothing is re-executed.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.out, artifact)
    for label, arm in arms.items():
        print(
            label,
            "old",
            arm["old_rule"]["matched"],
            "new",
            arm["new_rule"]["matched"],
            "sweep",
            json.dumps(arm["line_slack_sweep"]),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
