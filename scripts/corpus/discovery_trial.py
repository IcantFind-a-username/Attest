"""R-01 discovery trial: candidates per arm on the same built corpus cases.

Runs the discovery stage only (proposal, clustering, eligibility, S/T ranking;
no reproduction, no publication) with the real provider, and records every
candidate so two arms can be compared on identical pull requests.

  discovery_trial.py <arm-name> <instance_id>...

Paid. Reserve in DEVSPEND.md first.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.candidates import CandidateStore  # noqa: E402
from attest.review.config import ReviewConfig  # noqa: E402
from attest.review.proposer import ApiProvider  # noqa: E402
from attest.review.run import run_review  # noqa: E402

CASES = ROOT / ".attest" / "corpora" / "swebench" / "cases"
TRIALS = ROOT / ".attest" / "corpora" / "swebench" / "trials"


def main(argv: list[str]) -> int:
    arm, instance_ids = argv[0], argv[1:]
    out_dir = TRIALS / arm
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0.0
    for instance_id in instance_ids:
        case = CASES / instance_id
        manifest = json.loads((case / "manifest.json").read_text(encoding="utf-8"))
        repo = case / "repo"
        config = ReviewConfig(k_samples=4, tier0_commands=[])
        review = run_review(repo, manifest["base_sha"], config, ApiProvider(config.model))
        stored = CandidateStore(repo).load(review.task_id)
        record = {
            "arm": arm,
            "instance_id": instance_id,
            "task_id": review.task_id,
            "spend_usd": review.budget.spent_usd,
            "elapsed_s": review.elapsed_s,
            "deferred_reason": review.deferred_reason,
            "notes": review.notes,
            "candidates": [
                {
                    "finding_id": c.finding.finding_id,
                    "file": c.finding.file,
                    "line": c.finding.line,
                    "claim": c.finding.claim,
                    "failure_scenario": c.finding.failure_scenario,
                    "votes": c.finding.votes,
                    "wealth": c.wealth,
                    "action": c.action,
                    "eligibility": c.eligibility,
                    "eligibility_reason": c.eligibility_reason,
                }
                for c in stored
            ],
        }
        (out_dir / f"{instance_id}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        total += review.budget.spent_usd
        print(
            f"{arm} {instance_id}: {len(stored)} candidates, "
            f"{sum(1 for c in stored if c.eligibility == 'regression')} eligible, "
            f"${review.budget.spent_usd:.4f}, defer={review.deferred_reason}"
        )
    print(f"{arm} total ${total:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
