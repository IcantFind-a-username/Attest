"""D-102 replay (owner decision 1, 2026-09-03): the intent discriminator on the real bundles.

Re-executes, through the container backend and with no model call, every generated test
that certified in the E-02 held-out run (5 defects, 7 candidates) and the one E-01 natural
null publication (`3a32c92`, candidate `7ecf2fb275`), and records what the discriminator
decides for each: regression (publishes as before), behavior change with a base-tree
witness (publishes worded as such), or behavior change with intent unknown (drawer).

The RED the owner named: the `3a32c92` receipt goes to the drawer; the five held-out
regressions still publish.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
CASES = ROOT / ".attest" / "corpora" / "swebench" / "cases"
RESULTS = ROOT / ".attest" / "corpora" / "swebench" / "results"
NATURAL_NULL = {
    "repo": ROOT / ".attest" / "corpora" / "us-stock-helper",
    "case": "us-stock-helper 3a32c92",
    "task_id": "20260903-021750-af3b3ea7",
    "base_sha": "2d4a0d8ab042b4dc0ac5e5157fe2d7786939b9bf",
    "head_sha": "3a32c923a992796ee379ec135deb3b98fc47fdcc",
}
OUT = RESULTS / "intent-replay.json"

from attest.execution.backends import select_backend  # noqa: E402
from attest.review.candidates import CandidateStore  # noqa: E402
from attest.review.executor import ExecutorLimits, ReproSpec, execute_differential  # noqa: E402


def certified_bundles(repo: Path, task_id: str) -> list[tuple[str, str]]:
    """(candidate id, test source) for every accepted bundle of the task."""
    evidence = repo / ".attest" / "evidence" / task_id
    if not evidence.is_dir():
        return []
    out = []
    for bundle in sorted(evidence.iterdir()):
        test = bundle / "test_repro.py"
        if (bundle / "receipt.json").is_file() and test.is_file():
            out.append((bundle.name, test.read_text(encoding="utf-8")))
    return out


def jobs() -> list[dict[str, object]]:
    found: list[dict[str, object]] = []
    for path in sorted(RESULTS.glob("*.heldout.json")):
        summary = json.loads(path.read_text())
        if summary["control"] or not summary["surfaced_count"]:
            continue
        case = CASES / summary["case"]
        manifest = json.loads((case / "manifest.json").read_text())
        found.append(
            {
                "repo": case / "repo",
                "case": summary["case"],
                "task_id": summary["task_id"],
                "base_sha": manifest["base_sha"],
                "head_sha": manifest["head_sha"],
            }
        )
    found.append(dict(NATURAL_NULL))
    return found


def main(argv: list[str] | None = None) -> int:
    args = list(argv or [])
    out = OUT
    if "--out" in args:
        index = args.index("--out")
        out = RESULTS / args[index + 1]
        del args[index : index + 2]
    only = set(args)
    rows: list[dict[str, object]] = []
    for job in jobs():
        if only and not any(token in str(job["case"]) for token in only):
            continue
        repo = Path(str(job["repo"]))
        task_id = str(job["task_id"])
        store = CandidateStore(repo)
        backend = select_backend(repo, production=True)
        if backend.adapter is None:
            rows.append({"case": job["case"], "verdict": f"backend unavailable: {backend.reason}"})
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
            continue
        for candidate_id, source in certified_bundles(repo, task_id):
            stored = store.latest(candidate_id, task_id)
            if stored is None:
                rows.append(
                    {"case": job["case"], "candidate": candidate_id, "verdict": "no candidate"}
                )
                continue
            result = execute_differential(
                repo,
                stored,
                ReproSpec(source),
                ExecutorLimits(wall_timeout_s=180.0),
                base_sha=str(job["base_sha"]),
                head_sha=str(job["head_sha"]),
                adapter=backend.adapter,
            )
            intent = None if result.intent is None else asdict(result.intent)
            if intent is not None:
                intent.pop("changed_lines", None)
            rows.append(
                {
                    "case": job["case"],
                    "candidate": candidate_id,
                    "path": stored.finding.file,
                    "outcome": result.outcome.value,
                    "evidence_class": result.evidence_class.value,
                    "reason": result.reason,
                    "head_runs": [run.outcome.value for run in result.head_runs],
                    "base_runs": [run.outcome.value for run in result.base_runs],
                    "bound": bool(result.binding and result.binding.executed_changed_lines),
                    "intent": intent,
                }
            )
            print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print()
    print(
        "| case | candidate | outcome | evidence class | new rejection | origin | "
        "rejected inputs | witnesses |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for row in rows:
        intent = row.get("intent") or {}
        origin = (
            f"{intent.get('exception_type') or '-'} {intent.get('origin_statement') or ''} "
            f"@{intent.get('origin_line', 0)}"
            if intent
            else "-"
        )
        print(
            f"| {row['case']} | {row.get('candidate', '-')} | {row.get('outcome', '-')} | "
            f"{row.get('evidence_class', row.get('verdict', '-'))} | "
            f"{intent.get('new_rejection', '-') if intent else '-'} | {origin} | "
            f"{', '.join(repr(i) for i in intent.get('rejected_inputs', [])) if intent else '-'} | "
            f"{len(intent.get('witnesses', [])) if intent else '-'} |"
        )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
