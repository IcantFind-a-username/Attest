"""D-078 step a measurement: regenerate reproductions for named candidates.

For each (case, task_id, finding_id) the stored candidate is handed to the
current generator once (its schema-only retry budget is precommitted inside
generate_repro) and the resulting test is executed differentially. Nothing is
published and no result is fed back into generation. Paid; reserve first.

  regen_trial.py <label> case:task_id:finding_id ...
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.budget import Budget  # noqa: E402
from attest.review.candidates import CandidateStore  # noqa: E402
from attest.review.config import ReviewConfig  # noqa: E402
from attest.review.executor import (  # noqa: E402
    ExecutorLimits,
    execute_differential,
    generate_repro,
)
from attest.review.proposer import ApiProvider  # noqa: E402

CASES = ROOT / ".attest" / "corpora" / "swebench" / "cases"
OUT = ROOT / ".attest" / "corpora" / "swebench" / "regen"


def main(argv: list[str]) -> int:
    label, specs = argv[0], argv[1:]
    out_dir = OUT / label
    out_dir.mkdir(parents=True, exist_ok=True)
    config = ReviewConfig()
    faithful = 0
    total_spend = 0.0
    for spec in specs:
        case, task_id, finding_id = spec.split(":")
        manifest = json.loads((CASES / case / "manifest.json").read_text(encoding="utf-8"))
        repo = CASES / case / "repo"
        os.environ["ATTEST_PROJECT_PYTHON"] = manifest["project_python"]
        candidate = CandidateStore(repo).latest(finding_id, task_id)
        assert candidate is not None, spec
        budget = Budget(limit_usd=1.0, model=config.model)
        record: dict[str, object] = {"case": case, "task_id": task_id, "finding_id": finding_id}
        try:
            repro = generate_repro(
                repo, candidate, ApiProvider(config.model), budget, base_ref=manifest["base_sha"]
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never retried
            record.update(generation="failed", reason=f"{type(exc).__name__}: {exc}"[:300])
        else:
            execution = execute_differential(
                repo,
                candidate,
                repro,
                ExecutorLimits(wall_timeout_s=120.0),
                base_sha=manifest["base_sha"],
                head_sha=manifest["head_sha"],
                repeats=3,
            )
            record.update(
                generation="ok",
                test_body=repro.test_body,
                outcome=execution.outcome.value,
                evidence_class=execution.evidence_class.value,
                reason=execution.reason,
                head_runs=[r.outcome.value for r in execution.head_runs],
                base_runs=[r.outcome.value for r in execution.base_runs],
            )
            if execution.evidence_class.value == "regression_reproduced":
                faithful += 1
        record["spend_usd"] = budget.spent_usd
        total_spend += budget.spent_usd
        (out_dir / f"{case}--{finding_id}.json").write_text(
            json.dumps(record, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"{case} {finding_id}: {record.get('generation')} {record.get('outcome', '-')} "
            f"{record.get('evidence_class', '-')} ${budget.spent_usd:.4f} | "
            f"{str(record.get('reason', ''))[:90]}"
        )
    print(
        f"faithful (head FAIL n/n, base PASS n/n): {faithful}/{len(specs)}; "
        f"spend ${total_spend:.4f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
