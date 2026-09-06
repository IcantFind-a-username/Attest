"""The gate level's shadow run (D-137, `docs/design/gate-level.md`).

Three commands, and only one of them spends anything:

  witness  free. The static witness over every **recorded** new-code candidate
           of a named study's reviews: `(b)` complete annotations, `(a)` a call
           site outside the added lines, `(c)` a documented domain. This is the
           first measurement the design says it owes -- *what fraction of
           new-code candidates can produce a through-caller witness at all* --
           and it costs nothing, because it is read off the head trees.
  run      paid. For the candidates the witness admits, one reproduction and
           three head-only runs each, plus one environment control for an
           observation that has already passed everything else. Hard cumulative
           cap; **no author-visible output exists on this path at all** -- the
           run reuses the study's recorded candidates and never constructs a
           GitHub client, a comment or a `CertifiedFinding`.
  replay   free. The same adjudicator over every **recorded receipt bundle** in
           the corpora. A bundle's `intent.json` already carries the three
           coordinates the gate needs -- path, origin line, exception type --
           and its `test_repro.py` carries the reproduction, so the gate
           question can be asked of work already paid for. This is where a
           receipt red drawered is looked at again.

Paid: `run`. Reserve in DEVSPEND.md first.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from driver_budget import DriverCap  # noqa: E402

from attest.execution.backends import select_backend  # noqa: E402
from attest.review.budget import Budget  # noqa: E402
from attest.review.candidates import CandidateStore  # noqa: E402
from attest.review.config import ReviewConfig  # noqa: E402
from attest.review.executor import ExecutorLimits  # noqa: E402
from attest.review.gate_level import (  # noqa: E402
    GATE_REPEATS,
    ControlRun,
    Origin,
    added_lines,
    adjudicate,
    run_gate_shadow_stage,
    show,
    witness,
    write_record,
)
from attest.review.ledger import Ledger  # noqa: E402
from attest.review.proposer import ApiProvider  # noqa: E402

CORPORA = ROOT / ".attest" / "corpora"
STUDY = ROOT / "benchmarks" / "studies" / "e04-prospective-v2"
OUT = ROOT / "benchmarks" / "attest-v2" / "runs"
REPO_OF = {
    "IcantFind-a-username/Attest": "attest",
    "IcantFind-a-username/us-stock-helper": "us-stock-helper",
    "IcantFind-a-username/Corum": "corum",
    "IcantFind-a-username/IcantFind-a-username": "github-profile",
}


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    ).stdout


def units() -> list[dict[str, object]]:
    """The study's 100 units, each with the task id of the review that ran it,
    plus the supplementary unit named in the 2026-09-05c instruction."""
    rows = [json.loads(line) for line in (STUDY / "trials.jsonl").read_text().splitlines()]
    sample = {
        json.loads(line)["unit_id"]: json.loads(line)
        for line in (STUDY / "sample.jsonl").read_text().splitlines()
    }
    out: list[dict[str, object]] = []
    for row in rows:
        unit = sample[row["unit_id"]]
        out.append(
            {
                "unit_id": row["unit_id"],
                "task_id": row["task_id"],
                "repo": REPO_OF[unit["repository"]],
                "head": unit["head_sha"],
                "base": unit["base_sha"],
                "subject": unit["subject"],
                "supplementary": False,
            }
        )
    return out


# The pair the 2026-09-05b adjudication's row 7 sits on. It is **not** in the
# stratum-v2 population -- that stratum is the 40 newest Attest commits at its
# freeze and this one is six hours older than the oldest of them -- so it runs
# as a named supplementary unit and is reported as one, never inside the 100.
SUPPLEMENTARY = {
    "unit_id": "IcantFind-a-username/Attest@506aae1",
    "task_id": "",
    "repo": "attest",
    "head": "506aae1a134a4f6d249eb44d3a0325b9324887dd",
    "base": "69921e0a3c520b80a82dc7ffb60b6065181fe3bf",
    "subject": "docs: supplementary held-out run, erratum, spend, and the window handoff",
    "supplementary": True,
}


# ------------------------------------------------------------------- witness


def cmd_witness(args: argparse.Namespace) -> int:
    rows: list[dict[str, object]] = []
    for unit in units():
        repo = CORPORA / str(unit["repo"])
        candidates = [
            candidate
            for candidate in CandidateStore(repo).load(str(unit["task_id"]))
            if candidate.eligibility == "new_code" and candidate.action != "discard"
        ]
        if not candidates:
            continue
        added = added_lines(repo, str(unit["base"]), str(unit["head"]))
        for candidate in candidates:
            path = candidate.finding.file
            source = show(repo, str(unit["head"]), path)
            reach = witness(
                repo,
                str(unit["head"]),
                path=path,
                origin_line=candidate.finding.line,
                added=added,
                head_source=source,
                test_source="",
            )
            rows.append(
                {
                    "unit_id": unit["unit_id"],
                    "task_id": unit["task_id"],
                    "finding_id": candidate.finding.finding_id,
                    "repo": unit["repo"],
                    "path": path,
                    "line": candidate.finding.line,
                    "symbol": reach.symbol,
                    "annotated": bool(reach.parameters)
                    and all(reach.annotations)
                    and bool(reach.annotations),
                    "call_site": (
                        None
                        if reach.call_site is None
                        else f"{reach.call_site.path}:{reach.call_site.line}"
                    ),
                    "documented": reach.documented,
                    "admissible": reach.admissible,
                    "reason": reach.reason,
                }
            )
        print(f"{unit['unit_id']}: {len(candidates)} new-code candidate(s)", flush=True)
    payload = {
        "schema_version": "attest.gate-witness.v1",
        "study": STUDY.name,
        "candidates": len(rows),
        "admissible": sum(1 for r in rows if r["admissible"]),
        "with_call_site": sum(1 for r in rows if r["call_site"]),
        "fully_annotated": sum(1 for r in rows if r["annotated"]),
        "rows": rows,
    }
    path = Path(args.json) if args.json else OUT / "2026-09-05-gate-witness.json"
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{payload['candidates']} new-code candidates, {payload['fully_annotated']} fully "
        f"annotated, {payload['with_call_site']} with a call site, "
        f"{payload['admissible']} admissible -> {path}"
    )
    return 0


# ----------------------------------------------------------------------- run


def cmd_run(args: argparse.Namespace) -> int:
    population = units()
    if args.supplementary:
        population = [SUPPLEMENTARY]
    elif args.with_supplementary:
        population = [*population, SUPPLEMENTARY]
    config = ReviewConfig(budget_usd=args.budget, gate_shadow=True)
    witness_file = OUT / "2026-09-05-gate-witness.json"
    reachable: set[str] = set()
    if witness_file.is_file() and not args.supplementary:
        reachable = {
            str(row["finding_id"])
            for row in json.loads(witness_file.read_text(encoding="utf-8"))["rows"]
            if row["admissible"] and row["call_site"]
        }
    provider = ApiProvider(config.generation_model)
    log = Path(args.log).open("a", encoding="utf-8")  # noqa: SIM115 - appended across the loop
    done: set[str] = set()
    spent = 0.0
    if Path(args.log).is_file():
        text = Path(args.log).read_text(encoding="utf-8")
        done = set(re.findall(r"^=== gate (\S+)", text, flags=re.M))
        seen = re.findall(r"\[cumulative \$([0-9.]+)\]", text)
        spent = float(seen[-1]) if seen else 0.0
    # D-172: the cap reserves a unit's *maximum* -- one gate stage at
    # `budget_usd` -- before the unit starts, and releases it for a unit that
    # bought nothing. Gating on money already spent let the 2026-09-07 run end
    # $0.62 above its own cumulative cap.
    cap = DriverCap(cap=args.cap, reservation_usd=config.budget_usd, spent=spent)
    for unit in population:
        key = f"{unit['repo']}@{str(unit['head'])[:10]}"
        if key in done:
            continue
        repo = CORPORA / str(unit["repo"])
        log.write(f"=== gate {key} {unit['unit_id']}\n")
        refusal = cap.refusal(key)
        if refusal is not None:
            log.write(f"[{refusal}]\n")
            log.flush()
            continue
        cap.start(key)
        task_id = str(unit["task_id"])
        candidates = (
            [c for c in CandidateStore(repo).load(task_id) if c.action != "discard"]
            if task_id
            else []
        )
        if not task_id:
            # the supplementary unit's review predates the study; its candidates
            # are read from the same store by the task that produced its receipts
            candidates = _candidates_for_head(repo, str(unit["head"]))
            task_id = candidates[0].task_id if candidates else ""
        new_code = [c for c in candidates if c.eligibility == "new_code"]
        if not new_code:
            cap.settle(0.0)
            log.write(f"[no new-code candidate]\n[cumulative ${cap.spent:.6f}]\n")
            log.flush()
            continue
        # The free witness has already been taken over this study's candidates,
        # so a unit none of whose new-code candidates carries a call site cannot
        # produce a publishable grade and is skipped before an image is built.
        if reachable and not (reachable & {c.finding.finding_id for c in new_code}):
            cap.settle(0.0)
            log.write(f"[no candidate with a call site]\n[cumulative ${cap.spent:.6f}]\n")
            log.flush()
            continue
        git(repo, "checkout", "-q", "--detach", str(unit["head"]))
        budget = Budget(limit_usd=config.budget_usd, model=config.model)
        started = time.monotonic()
        # X-02, as red uses it: the container backend, built from the head tree,
        # or nothing. A gate observation taken on the host adapter would not be
        # the design's `linux-container-v1` and is not worth buying.
        backend = select_backend(repo, production=True, remaining_s=args.timeout)
        if backend.adapter is None:
            cap.settle(0.0)
            log.write(f"[no container backend: {backend.reason}]\n")
            log.flush()
            continue
        try:
            stage = run_gate_shadow_stage(
                repo,
                task_id=task_id,
                base_sha=str(unit["base"]),
                head_sha=str(unit["head"]),
                candidates=candidates,
                provider=provider,
                budget=budget,
                limits=ExecutorLimits(wall_timeout_s=args.wall_timeout),
                deadline=started + args.timeout,
                clock=time.monotonic,
                adapter=backend.adapter,
                generation_model=config.generation_model,
                ledger=Ledger(repo),
            )
        except Exception as exc:  # noqa: BLE001 - a driver records, it does not raise
            # whatever the stage bought before it raised is still spent
            cap.settle(budget.spent_usd)
            log.write(f"[error {type(exc).__name__}: {str(exc)[:200]}]\n")
            log.flush()
            continue
        cap.settle(budget.spent_usd)
        log.write(
            f"[considered {stage.considered} admissible {stage.admissible} attempted "
            f"{stage.attempted} would_publish {stage.would_publish} "
            f"spend ${budget.spent_usd:.6f}]\n"
        )
        for finding_id, observation in stage.observations:
            log.write(
                f"  {finding_id} {observation.reachability.kind} {observation.reason[:110]}\n"
            )
        log.write(f"[cumulative ${cap.spent:.6f}]\n")
        log.flush()
    log.write("=== gate done\n")
    log.close()
    return 0


def _candidates_for_head(repo: Path, head: str):
    """Every recorded candidate of the review whose head was this commit."""
    ledger = [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    tasks = {
        str(row["task_id"])
        for row in ledger
        if row.get("kind") == "verification" and str(row.get("head_sha", "")) == head
    }
    store = CandidateStore(repo)
    return [c for task in sorted(tasks) for c in store.load(task) if c.action != "discard"]


# -------------------------------------------------------------------- replay


def cmd_replay(args: argparse.Namespace) -> int:
    """The gate adjudicator over recorded receipt bundles. Free: every field it
    reads was paid for once already, and nothing is executed again."""
    rows: list[dict[str, object]] = []
    for evidence in sorted(CORPORA.glob("*/.attest/evidence/*/*")):
        intent_path = evidence / "intent.json"
        repro_path = evidence / "test_repro.py"
        task_path = evidence / "task.json"
        if not (intent_path.is_file() and task_path.is_file()):
            continue
        intent = json.loads(intent_path.read_text(encoding="utf-8"))
        task = json.loads(task_path.read_text(encoding="utf-8"))
        repo = evidence.parents[3]  # <clone>/.attest/evidence/<task>/<candidate>
        head = str(task.get("head_sha", ""))
        base = str(task.get("merge_base_sha", ""))
        path = str(intent.get("path", ""))
        line = intent.get("origin_line")
        if not (head and base and path) or not isinstance(line, int):
            continue
        source = show(repo, head, path)
        if not source:
            continue
        added = added_lines(repo, base, head)
        test_source = repro_path.read_text(encoding="utf-8") if repro_path.is_file() else ""
        reach = witness(
            repo,
            head,
            path=path,
            origin_line=line,
            added=added,
            head_source=source,
            test_source=test_source,
        )
        statement = str(intent.get("origin_statement", "other"))
        exception_type = str(intent.get("exception_type", ""))
        origin: Origin | None = None
        origin_reason = ""
        if line not in added.get(path, set()):
            origin_reason = f"line {line} is not a line the diff added"
        elif statement in {"raise", "assert"}:
            origin_reason = f"line {line} is a deliberate {statement} (D-102, unchanged)"
        else:
            origin = Origin(
                line=line, statement=statement, exception_type=exception_type, escaped=True
            )
        runs = ((line, exception_type),) * int(intent.get("head_runs_observed", 0) or 0)
        # the replay cannot run an environment control; a bundle whose base runs
        # all passed in the same image is the strongest control the record holds,
        # and it is recorded as *that*, never as the design's §3 control
        control = ControlRun(
            target="(replay: the receipt's own base runs, in the same image)",
            passed=True,
            reason="replayed from a recorded bundle; no §3 control was executed",
        )
        observation = adjudicate(
            path=path,
            reachability=reach,
            origin=origin,
            origin_reason=origin_reason,
            runs=runs,
            repeats=GATE_REPEATS,
            control=control,
            source="replay",
        )
        rows.append(
            {
                "clone": repo.name,
                "task_id": str(task.get("task_id", "")),
                "candidate_id": evidence.name,
                "head": head[:10],
                **{
                    key: value
                    for key, value in observation.to_ledger_row(
                        str(task.get("task_id", "")), evidence.name
                    ).items()
                    if key not in {"kind", "schema_version", "task_id", "finding_id"}
                },
            }
        )
        write_record(repo, f"replay-{str(task.get('task_id', ''))}", evidence.name, observation)
    payload = {
        "schema_version": "attest.gate-replay.v1",
        "receipts": len(rows),
        "would_publish": sum(1 for r in rows if r["would_publish"]),
        "through_caller": sum(1 for r in rows if r["reachability"] == "through_caller"),
        "admissible": sum(1 for r in rows if r["admissible"]),
        "rows": rows,
    }
    path = Path(args.json) if args.json else OUT / "2026-09-05-gate-replay.json"
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{payload['receipts']} recorded receipts replayed, {payload['admissible']} admissible, "
        f"{payload['through_caller']} through-caller, {payload['would_publish']} would publish "
        f"-> {path}"
    )
    return 0


# --------------------------------------------------------------------- table


def cmd_table(args: argparse.Namespace) -> int:
    records = sorted(CORPORA.glob("*/.attest/shadow/gate/*/*.json"))
    print("| clone | task | finding | reachability | call site | exception | line | verdict |")
    print("|---|---|---|---|---|---|---|---|")
    for record in records:
        payload = json.loads(record.read_text(encoding="utf-8"))
        reach = payload["reachability"]
        origin = payload.get("origin") or {}
        site = reach.get("call_site") or {}
        print(
            f"| `{record.parents[3].name}` | `{record.parent.name[:18]}` | "
            f"`{record.stem}` | {reach['kind']} | "
            f"{('`' + site['path'] + ':' + str(site['line']) + '`') if site else '—'} | "
            f"{origin.get('exception_type') or '—'} | {origin.get('line') or '—'} | "
            f"{'would publish' if payload['would_publish'] else 'drawer'} |"
        )
    print(f"\n{len(records)} shadow records")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    w = sub.add_parser("witness")
    w.add_argument("--json", default=None)
    w.set_defaults(func=cmd_witness)
    r = sub.add_parser("run")
    r.add_argument("--budget", type=float, default=1.00)
    r.add_argument("--cap", type=float, required=True, help="hard cumulative spend cap")
    r.add_argument("--log", required=True)
    r.add_argument("--timeout", type=float, default=1200.0)
    r.add_argument(
        "--wall-timeout",
        type=float,
        default=60.0,
        help=(
            "per-run wall clock; red's default is 60s and a shadow run that raises it "
            "must say so, because a timeout is an environment fact and not evidence"
        ),
    )
    r.add_argument("--with-supplementary", action="store_true")
    r.add_argument("--supplementary", action="store_true", help="only the supplementary unit")
    r.set_defaults(func=cmd_run)
    p = sub.add_parser("replay")
    p.add_argument("--json", default=None)
    p.set_defaults(func=cmd_replay)
    t = sub.add_parser("table")
    t.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    os.environ.setdefault("PYTHONPATH", str(ROOT / "src"))
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
