"""Reconcile frozen independent source reviews; never claim runtime qualification."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "benchmarks/studies/remainder-v1"
WORK = ROOT / ".attest/remainder-qualification-work"
REPOS = ROOT / ".attest/corpora/metadata-exposed-v1"


def main() -> None:
    destination = STUDY / "qualification-candidates.json"
    if destination.exists():
        raise ValueError("qualification already recorded; no overwrite")
    freeze_bytes = (STUDY / "freeze.json").read_bytes()
    freeze = json.loads(freeze_bytes)
    protocol_digest = sha256_bytes((STUDY / "protocol.md").read_bytes())
    controls_bytes = (STUDY / "control-candidates.json").read_bytes()
    controls = json.loads(controls_bytes)
    expected = [c["instance_id"] for c in freeze["selected"]]
    control_ids = [
        (r["repo"], sha) for r in controls["repositories"] for sha in r["selected_for_inspection"]
    ]
    reviews = {}
    digests = {}
    for name in ("semantic-a", "semantic-b", "controls-a", "controls-b"):
        payload = (WORK / (name + ".json")).read_bytes()
        review = json.loads(payload)
        if (
            review["freeze_sha256"] != sha256_bytes(freeze_bytes)
            or review["protocol_sha256"] != protocol_digest
        ):
            raise ValueError("review input drift: " + name)
        rows = review["rows"]
        identities = (
            [r["case"] for r in rows]
            if name.startswith("semantic")
            else [(r["repo"], r["head_sha"]) for r in rows]
        )
        if identities != (expected if name.startswith("semantic") else control_ids):
            raise ValueError("review population/order drift: " + name)
        if any(r["semantic_class"].startswith(("pending", "not_reviewed")) for r in rows):
            raise ValueError("incomplete review: " + name)
        if name.startswith("controls") and review["control_candidates_sha256"] != sha256_bytes(
            controls_bytes
        ):
            raise ValueError("control input drift")
        reviews[name] = rows
        digests[name] = sha256_bytes(payload)

    # Prior inspected controls and natural defect pairs are excluded even when
    # the new case identity differs. Full ranked but uninspected lists are not truth.
    prior: set[str] = set()
    prior_inputs = {}
    for study in sorted((ROOT / "benchmarks/studies").iterdir()):
        if study == STUDY:
            continue
        for filename in ("control-candidates.json", "qualification-candidates.json"):
            path = study / filename
            if not path.is_file():
                continue
            payload = path.read_bytes()
            prior_inputs[str(path.relative_to(ROOT))] = sha256_bytes(payload)
            value = json.loads(payload)
            for repo in value.get("repositories", []):
                prior.update(repo["selected_for_inspection"])
            for pair in value.get("pairs", []):
                prior.update((pair["parent_sha"], pair["head_sha"]))

    rows = []
    pairs = []
    seen: set[tuple[str, str, str]] = set()
    for source, a, b in zip(
        freeze["selected"], reviews["semantic-a"], reviews["semantic-b"], strict=True
    ):
        if a["repo"] != source["repo"] or b["repo"] != source["repo"]:
            raise ValueError("review repository drift")
        agreed = (
            a["plausible_forward"] is True
            and b["plausible_forward"] is True
            and a["parent_sha"] == b["parent_sha"]
            and a["head_sha"] == b["head_sha"]
        )
        reason = "source_pair_agreement" if agreed else "refused_or_unresolved_review"
        if agreed:
            repo = REPOS / source["repo"].replace("/", "__") / "repo"
            actual = subprocess.check_output(
                [
                    "git",
                    "-c",
                    "gc.auto=0",
                    "-C",
                    str(repo),
                    "rev-list",
                    "--parents",
                    "-n",
                    "1",
                    a["head_sha"],
                ],
                text=True,
                timeout=60,
            ).split()
            if actual != [a["head_sha"], a["parent_sha"]]:
                raise ValueError("not an exact single-parent introducing pair")
            key = (source["repo"], a["parent_sha"], a["head_sha"])
            if prior.intersection(key[1:]):
                agreed, reason = False, "prior_inspected_pair_overlap"
            elif key in seen:
                agreed, reason = False, "duplicate_natural_pair"
            else:
                seen.add(key)
                pairs.append(
                    {
                        "case": source["instance_id"],
                        "repo": source["repo"],
                        "parent_sha": a["parent_sha"],
                        "head_sha": a["head_sha"],
                    }
                )
        rows.append(
            {
                "case": source["instance_id"],
                "agreed_pair": agreed,
                "reason": reason,
                "review_a_class": a["semantic_class"],
                "review_b_class": b["semantic_class"],
            }
        )
    defects = {sha for pair in pairs for sha in (pair["parent_sha"], pair["head_sha"])}
    control_rows = []
    for a, b in zip(reviews["controls-a"], reviews["controls-b"], strict=True):
        agrees = (
            a["admitted"] is True and b["admitted"] is True and a["parent_sha"] == b["parent_sha"]
        )
        overlap = bool({a["parent_sha"], a["head_sha"]} & (prior | defects))
        control_rows.append(
            {
                "repo": a["repo"],
                "head_sha": a["head_sha"],
                "parent_sha": a["parent_sha"],
                "source_agreement": agrees,
                "prior_or_defect_overlap": overlap,
                "source_admitted": agrees and not overlap,
                "runtime_qualified": False,
            }
        )
    write_canonical_json(
        destination,
        {
            "status": "source_reviews_reconciled_pending_execution_and_semantic_dedup",
            "freeze_sha256": sha256_bytes(freeze_bytes),
            "protocol_sha256": protocol_digest,
            "reviews": digests,
            "prior_inputs": prior_inputs,
            "driver_sha256": sha256_bytes(Path(__file__).read_bytes()),
            "code_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
            "rows": rows,
            "pairs": pairs,
            "controls": control_rows,
            "qualified_defects": 0,
            "qualified_controls": 0,
            "model_api_spend_usd": 0,
        },
    )
    print("Source reviews reconciled; runtime qualification and semantic dedup remain.")


if __name__ == "__main__":
    main()
