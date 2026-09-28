"""Offline presentation replay: four saved receipts, seven real-PR notes and six layouts.

Run with PYTHONPATH=<source-tree>/src to compare renderers against the same inputs.
No provider, reviewed project execution or GitHub client is constructed. Composite layouts
combine saved findings from different tasks; they are layout exercises, not additional PRs.
Bundle verification checks recorded evidence; no controller key is used to authenticate seals.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import fields
from pathlib import Path

import attest.github.presentation as presentation
from attest.benchmark.artifacts import sha256_bytes, write_canonical_json
from attest.certification.types import AcceptedReceipt, CertifiedFinding, FindingAnchor
from attest.review.evidence import verify_bundle
from attest.review.finding_evidence import evidence_from_bundle
from attest.review.output_contract import check_comment, check_summary
from attest.review.structural import (
    find_duplicate_implementations,
    functions_of,
    structural_note,
)
from attest.review.value_note import ValueNote

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/acceptance/evidence"
BUNDLES = EVIDENCE / "2026-09-15-contract-binding/bundles-b1-E61.jsonl"
CONTROLS = EVIDENCE / "2026-09-15-frozen-e2e/controls-f3-E.jsonl"
GREEN_PATHS = ("scripts/corpus/impact_scan.py", "scripts/corpus/qualify_controls.py")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    inputs = {p: sha256_bytes((ROOT / p).read_bytes()) for p in GREEN_PATHS}
    for path in (BUNDLES, CONTROLS):
        inputs[str(path.relative_to(ROOT))] = sha256_bytes(path.read_bytes())
    findings, bundles, evidence = [], [], {}
    for line in BUNDLES.read_text().splitlines():
        record = json.loads(line)
        bundle = ROOT / ".attest/corpora" / record["bundle"]
        accepted = verify_bundle(bundle)
        if not isinstance(accepted, AcceptedReceipt):
            raise ValueError(f"saved bundle no longer validates: {record['bundle']}")
        binding = json.loads((bundle / "binding.json").read_text())
        # These frozen proposals were mechanically anchored at the first changed line.
        anchor = FindingAnchor(binding["path"], min(binding["changed_lines"]))
        findings.append(CertifiedFinding.from_accepted_receipt(accepted, (anchor,)))
        block = evidence_from_bundle(bundle, repo=ROOT)
        if block is None:
            raise ValueError("saved bundle has no readable presentation evidence")
        evidence[accepted.receipt.candidate_id] = block
        bundles.append({
            "bundle": record["bundle"],
            "receipt": accepted.receipt.provenance_digest,
            "manifest_sha256": sha256_bytes((bundle / "manifest.json").read_bytes()),
        })
    notes = []
    for line in CONTROLS.read_text().splitlines():
        for row in json.loads(line)["rows"]:
            if row["kind"] == "value_observation_note":
                data = {f.name: row[f.name] for f in fields(ValueNote) if f.name in row}
                data["pinned_values"] = tuple(data["pinned_values"])
                data["specified_by"] = tuple(tuple(p) for p in data["specified_by"])
                notes.append(ValueNote(**data))
    units = [
        unit for path in GREEN_PATHS
        for unit in functions_of(path, (ROOT / path).read_text())
    ]
    green = [structural_note(f) for f in find_duplicate_implementations(
        units, changed_files=set(GREEN_PATHS)
    )]
    if len(findings) != 4 or len(notes) != 7 or not green:
        raise ValueError("incomplete replay inputs; a missing population cannot count as zero")
    layouts = {
        "single": dict(findings=findings[:1]),
        "multiple": dict(findings=findings[:3], structural=green, value_notes=notes[:1]),
        "yellow-only": dict(findings=[], value_notes=notes[:2]),
        "green-only": dict(findings=[], structural=green),
        "partial": dict(findings=findings[:1], units=(1, 4), unverified=2),
        "silent": dict(findings=[], units=(4, 4)),
    }
    rendered = {}
    for name, options in layouts.items():
        body = presentation.render_complete(**options, spend_usd=0.0, elapsed_s=0.0,
                                            evidence=evidence)
        body = body.replace(str(ROOT), "<repo>")
        (args.out / f"{name}.md").write_text(body + "\n")
        rendered[name] = {"admitted": bool(check_summary(body)),
                          "sha256": sha256_bytes(body.encode())}
    comments = presentation.inline_comments(findings, evidence)
    # Render the fourth receipt separately, since the inline renderer caps each review at three.
    comments.extend(presentation.inline_comments(findings[3:], evidence))
    for note in notes:
        comments.extend(presentation.value_comments([note]))
    comments.extend(presentation.structural_comments(green))
    for i, comment in enumerate(comments):
        body = str(comment["body"]).replace(str(ROOT), "<repo>")
        (args.out / f"inline-{i + 1}.md").write_text(body + "\n")
    source = Path(presentation.__file__)
    result = {
        "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
        "checkout_sha": subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
        ).strip(),
        "renderer_sha256": sha256_bytes(source.read_bytes()),
        "inputs": inputs, "bundles": bundles, "layouts": rendered,
        "inline": [{"path": c["path"], "line": c["line"],
                    "member": str(c["body"]).splitlines()[0],
                    "admitted": bool(check_comment(str(c["body"])))} for c in comments],
        "independent_saved_defect_cases": len(findings),
        "saved_value_notes": len(notes), "structural_pairs_measured": len(green),
        "paid_calls": 0, "remote_writes": 0,
        "limits": "Presentation replay only; composite layouts are not independent PRs. "
                  "No new search, execution, semantic labelling, recall or precision measurement.",
    }
    if args.compare is not None:
        before = json.loads((args.compare / "manifest.json").read_text())
        result["comparison"] = {
            key: result[key] == before[key] for key in ("inputs", "bundles", "inline")
        }
        if not all(result["comparison"].values()):
            raise ValueError("replay inputs, receipt identities or inline membership changed")
    write_canonical_json(args.out / "manifest.json", result)
    print(f"Rendered {len(layouts)} layouts and {len(comments)} comments from non-empty inputs.")


if __name__ == "__main__":
    main()
