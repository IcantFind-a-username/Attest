"""Replay a recorded run's frozen probes through the differential, with no model call.

For every case of the forty whose ledger holds a probe that produced a differential
-- a base observation and a differing head observation, recorded by the arm named --
re-execute exactly that probe (its imports, setup and expression as the ledger
carries them) through `execute_differential` on the rebuilt trees: record on the
merge base, write the replay test from the recording, run it three times each side,
and judge intent under the observer as it stands in this checkout. Nothing is asked
of a model; the probe is the arm's own. What comes out is the verdict the current
rules give the very evidence the arm bought -- the pairing a rule change (D-249,
`attest.intent.v6`) is measured by, case by case, at $0.00.

    .venv/bin/python scripts/corpus/frozen_probe_replay.py run [--arm C] [--only a,b]
    .venv/bin/python scripts/corpus/frozen_probe_replay.py table [--arm C]

Production backend only (`linux-container-v1`): without a docker daemon the run
records the refusal and stops rather than fall back to the host adapter.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from evidence_supply import _checkout, _read_jsonl  # noqa: E402
from mutation_recall import STUDY, WORK, classify  # noqa: E402

from attest.execution.backends import select_backend  # noqa: E402
from attest.review.candidates import StoredCandidate  # noqa: E402
from attest.review.executor import (  # noqa: E402
    ExecutionResult,
    ExecutorLimits,
    ReproSpec,
    execute_differential,
)
from attest.review.probe import ProbeSpec  # noqa: E402
from attest.review.schema import Finding  # noqa: E402

ARMS = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-14-probe-arms"
OUT = ROOT / "docs" / "acceptance" / "evidence" / "2026-09-15-frozen-probe-replay"
WALL_TIMEOUT_S = 180.0
REPEATS = 3


def frozen_probe(rows: list[dict]) -> tuple[dict | None, str]:
    """The arm's probe that produced the differential for this case, or why none did.

    A differential probe recorded a base observation and a differing head
    observation and was not screened out. The finding whose verification was
    reproduced is preferred; otherwise the last such probe the arm bought."""
    reproduced = {
        r.get("finding_id") for r in rows
        if r.get("kind") == "verification" and r.get("outcome") == "reproduced"
    }
    candidates = [
        r for r in rows
        if r.get("kind") == "probe_observation"
        and r.get("observed_kind") in ("value", "exception")
        and r.get("head_kind")
        and (r.get("head_kind"), r.get("head_detail"))
        != (r.get("observed_kind"), r.get("observed_detail"))
        and not r.get("screened")
    ]
    if not candidates:
        probes = [r for r in rows if r.get("kind") == "probe_observation"]
        return None, (
            f"no frozen probe with a differential ({len(probes)} probe(s) recorded, none "
            "with a base observation and a differing head observation)"
        )
    preferred = [r for r in candidates if r.get("finding_id") in reproduced]
    return (preferred or candidates)[-1], ""


def _run_record(run: ExecutionResult) -> dict:
    return {
        "outcome": run.outcome.value,
        "reason": run.reason,
        "failure_message": run.failure_message,
        "failure_detail": run.failure_detail,
        "raise_origins": [asdict(o) for o in run.raise_origins],
        "raise_origins_truncated": bool(run.raise_origins_truncated),
        "executed_lines": list(run.executed_lines),
        "executor_profile": run.executor_profile,
        "interpreter_version": run.interpreter_version,
    }


def cmd_run(args: argparse.Namespace) -> int:
    arm = args.arm
    arm_dir = ARMS / f"arm-{arm}"
    trials = {r["unit_id"]: r for r in _read_jsonl(arm_dir / f"trials-arm-{arm}.jsonl")}
    sample = _read_jsonl(STUDY / "sample.jsonl")
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    OUT.mkdir(parents=True, exist_ok=True)
    out_path = OUT / f"replay-arm-{arm}.jsonl"
    done = {r["unit_id"] for r in _read_jsonl(out_path)} if not args.fresh else set()
    if args.fresh:
        out_path.unlink(missing_ok=True)
    ledgers: dict[str, list[dict]] = {}
    for row in sample:
        unit_id = str(row["unit_id"])
        library = str(row["library"])
        if (only and unit_id not in only) or unit_id in done:
            continue
        trial = trials.get(unit_id)
        manifest_path = WORK / "cases" / unit_id / "manifest.json"
        record: dict = {"unit_id": unit_id, "library": library, "stratum": row["stratum"],
                        "site": f"{row['mutation']['path']}:{row['mutation']['line']}",
                        "arm": arm}
        if trial is None or not manifest_path.is_file():
            record["skipped"] = "no trial" if trial is None else "case not built"
            _append(out_path, record)
            continue
        if library not in ledgers:
            ledgers[library] = _read_jsonl(arm_dir / f"{library}-ledger.jsonl")
        rows = [r for r in ledgers[library] if r.get("task_id") == trial["task_id"]]
        klass, why = classify(rows, str(trial.get("deferred_reason") or ""),
                              site=(str(row["mutation"]["path"]), int(row["mutation"]["line"])))
        record["recorded"] = {"class": klass, "reason": why[:240]}
        probe_row, reason = frozen_probe(rows)
        if probe_row is None:
            record["skipped"] = reason
            _append(out_path, record)
            print(json.dumps({"unit_id": unit_id, "skipped": reason}), flush=True)
            continue
        probe = ProbeSpec(
            imports=str(probe_row.get("imports") or ""),
            setup=str(probe_row.get("setup") or ""),
            expression=str(probe_row.get("expression") or ""),
        )
        record["probe"] = asdict(probe)
        record["recorded"].update({
            "finding_id": probe_row.get("finding_id"),
            "base": f"{probe_row.get('observed_kind')}:"
                    f"{str(probe_row.get('observed_detail'))[:200]}",
            "head": f"{probe_row.get('head_kind')}:{str(probe_row.get('head_detail'))[:200]}",
        })
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        repo = Path(manifest["repo_path"])
        base_sha, head_sha = manifest["base_sha"], manifest["head_sha"]
        _checkout(repo, head_sha)
        backend = select_backend(repo, production=True)
        if backend.adapter is None:
            record["skipped"] = f"backend unavailable: {backend.reason}"
            _append(out_path, record)
            print(json.dumps({"unit_id": unit_id, "skipped": record["skipped"]}), flush=True)
            return 1
        candidate = StoredCandidate(
            task_id=f"frozen-{arm}-{unit_id}",
            finding=Finding(
                claim=f"frozen probe replay of {probe_row.get('finding_id')} (arm {arm})",
                file=str(row["mutation"]["path"]),
                line=int(row["mutation"]["line"]),
                failure_scenario="",
                falsification_plan="",
            ),
            wealth=0.0,
            action="verify",
            alpha=0.1,
        )
        started = time.monotonic()
        result = execute_differential(
            repo, candidate, ReproSpec(test_body=""), ExecutorLimits(wall_timeout_s=WALL_TIMEOUT_S),
            base_sha=base_sha, head_sha=head_sha, repeats=REPEATS,
            adapter=backend.adapter, probe=probe,
        )
        record.update({
            "backend": backend.profile,
            "outcome": result.outcome.value,
            "evidence_class": result.evidence_class.value,
            "reason": result.reason,
            "head_runs": [_run_record(r) for r in result.head_runs],
            "base_runs": [r.outcome.value for r in result.base_runs],
            "intent": asdict(result.intent) if result.intent is not None else None,
            "probe_observation": asdict(result.probe) if result.probe is not None else None,
            "test_body": result.executed_spec.test_body if result.executed_spec else "",
            "bound": bool(result.binding and result.binding.executed_changed_lines),
            "elapsed_s": round(time.monotonic() - started, 1),
        })
        _append(out_path, record)
        print(json.dumps({"unit_id": unit_id, "recorded": klass, "outcome": record["outcome"],
                          "class": record["evidence_class"], "reason": record["reason"][:120],
                          "elapsed_s": record["elapsed_s"]}, ensure_ascii=False), flush=True)
    print(f"wrote {out_path}")
    return 0


def _append(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def replay_class(record: dict) -> str:
    """The replay's class in the words of the recorded table."""
    if "skipped" in record:
        return "skipped"
    if record.get("outcome") == "reproduced":
        return "certified"
    reason = str(record.get("reason", ""))
    if "no symbol to specify" in reason:
        return "no receipt"
    if "value change confirmed" in reason or "intent unknown" in reason:
        return "value class"
    return "no receipt"


def cmd_table(args: argparse.Namespace) -> int:
    rows = _read_jsonl(OUT / f"replay-arm-{args.arm}.jsonl")
    lines = ["| case | stratum | recorded (arm) | replay | reason |", "|---|---|---|---|---|"]
    counts: dict[str, int] = {}
    moved = []
    for r in rows:
        before = r.get("recorded", {}).get("class", "?")
        after = replay_class(r)
        counts[f"{before} -> {after}"] = counts.get(f"{before} -> {after}", 0) + 1
        if before != after and after != "skipped":
            moved.append((r["unit_id"], before, after))
        reason = r.get("skipped") or r.get("reason", "")
        lines.append(f"| `{r['unit_id']}` | {r['stratum']} | {before} | {after} | {reason[:140]} |")
    (OUT / f"table-arm-{args.arm}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    certified = sum(1 for r in rows if replay_class(r) == "certified")
    print(json.dumps({"cases": len(rows), "replay_certified": certified,
                      "transitions": counts, "moved": moved}, indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--arm", default="C")
    r.add_argument("--only", default="")
    r.add_argument("--fresh", action="store_true")
    r.set_defaults(func=cmd_run)
    t = sub.add_parser("table")
    t.add_argument("--arm", default="C")
    t.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
