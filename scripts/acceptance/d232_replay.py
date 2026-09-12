"""D-232 replay: every reproduced differential of the 2026-09-11/12 runs, re-judged
under the frame rule (`attest.intent.v5`) from the ledgers already on disk.

Reads three ledger sets -- the 35 held-out cases of the 2026-09-12 supported-corpus
run, the 24 units of e05-external-v1 (run B) and the 2 units of run A -- and for
every `verification` row whose outcome is `reproduced` asks what v5 says:

    unchanged     the row was already a behaviour change (a raise/assert statement
                  on a changed line, D-102), or a value mismatch, or its exception
                  never passed through the anchored file at all
    moved         the row certified as a regression under v4.2 and v5 reads it as a
                  new rejection: the exception was raised on a line the change wrote,
                  or on an unchanged line of the anchored file and passed back through
                  one the change wrote (the lazy-iterator shape)
    kept          the row certified as a regression and v5 keeps it: head raises on an
                  unchanged line and no written line is on the exception's path

The exception's path is read from the pytest longrepr the ledger row carries for each
head run (the frames of the anchored file, outermost first); the lines the change
wrote are `git diff -U0` of the anchored file in the local clone. No execution, no
model, $0.00. The RED the owner named: both `python-attrs/attrs#1603` receipts move.

    .venv/bin/python scripts/acceptance/d232_replay.py \\
        --out docs/acceptance/evidence/2026-09-13-d232-replay.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.diffs import parse_diff  # noqa: E402

EVIDENCE = ROOT / "docs" / "acceptance" / "evidence"
HELDOUT_RESULTS = EVIDENCE / "2026-09-12-heldout-supported-run.json"
HELDOUT_CASES = ROOT / ".attest" / "corpora" / "swebench" / "cases"
RUN_B = EVIDENCE / "2026-09-12-lines-on-real-prs" / "run-b"
RUN_A = EVIDENCE / "2026-09-12-lines-on-real-prs" / "run-a"
E05 = ROOT / "benchmarks" / "studies" / "e05-external-v1"
E04 = ROOT / "benchmarks" / "studies" / "e04-prospective-v3"
GNULL = ROOT / ".attest" / "corpora" / "gnull"
CORPORA = ROOT / ".attest" / "corpora"
# a frame line of a pytest longrepr: "<path>:<line>: in <function>" for an outer
# frame, "<path>:<line>: <ExceptionType>" for the frame the exception left
_FRAME = re.compile(r"^(?P<path>[^\s:]+):(?P<line>\d+): (?P<rest>in \S+|\S+)\s*$")
_HEAD_RUN = re.compile(r"^head run (\d+):", re.MULTILINE)


def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _clone_name(repository: str) -> str:
    return repository.split("/")[-1].lower().lstrip("-")


def added_lines(repo: Path, base: str, head: str, path: str) -> tuple[int, ...] | None:
    proc = subprocess.run(
        ["git", "-C", str(repo), "diff", "--no-color", "-U0", base, head, "--", path],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        return None
    return tuple(sorted(parse_diff(proc.stdout).added_lines.get(path, set())))


def anchored_frames(evidence: str, path: str) -> list[list[tuple[int, str]]]:
    """Per head run, the anchored file's frames in the longrepr, outermost first."""
    starts = [m.start() for m in _HEAD_RUN.finditer(evidence)]
    if not starts:
        return []
    sections = [
        evidence[s:e] for s, e in zip(starts, [*starts[1:], len(evidence)], strict=True)
    ]
    runs: list[list[tuple[int, str]]] = []
    for section in sections:
        # only the head part of a section: a "base run" block may follow in the same text
        cut = section.find("\nbase run ")
        text = section if cut < 0 else section[:cut]
        frames: list[tuple[int, str]] = []
        for raw in text.splitlines():
            m = _FRAME.match(raw.strip())
            if not m:
                continue
            frame_path = m.group("path")
            if frame_path == path or frame_path.endswith("/" + path):
                frames.append((int(m.group("line")), m.group("rest")))
        runs.append(frames)
    return runs


def judge(row: dict, repo: Path, base: str, head: str) -> dict:
    intent = row.get("intent") or {}
    path = str(intent.get("path", ""))
    out = {
        "finding_id": row.get("finding_id"),
        "path": path,
        "before_class": row.get("evidence_class"),
        "before_outcome": row.get("outcome"),
        "origin_line_recorded": intent.get("origin_line"),
        "origin_statement_recorded": intent.get("origin_statement"),
        "exception_type": intent.get("exception_type"),
        "new_rejection_recorded": bool(intent.get("new_rejection")),
        "value_mismatch_recorded": bool(intent.get("value_mismatch")),
    }
    if intent.get("new_rejection"):
        out.update(after="unchanged", after_class="behavior_change",
                   why="already a new rejection under the statement rule")
        return out
    if intent.get("value_mismatch"):
        out.update(after="unchanged", after_class=row.get("evidence_class"),
                   why="a value mismatch: the frame rule does not apply")
        return out
    runs = anchored_frames(str(row.get("evidence", "")), path)
    written = added_lines(repo, base, head, path)
    out["added_lines"] = list(written) if written is not None else None
    frames_per_run = [[line for line, _ in run] for run in runs]
    out["anchored_frames_per_head_run"] = frames_per_run
    if written is None:
        out.update(after="unreadable", after_class=row.get("evidence_class"),
                   why="the local clone cannot diff these revisions")
        return out
    if not runs or not any(frames_per_run):
        out.update(
            after="unchanged",
            after_class=row.get("evidence_class"),
            why=(
                "no frame of the anchored file on the exception's path "
                "(raised at the call site or in another file)"
            ),
        )
        return out
    if len({tuple(f) for f in frames_per_run}) != 1:
        out.update(after="unreadable", after_class=row.get("evidence_class"),
                   why="head runs disagree on the anchored frames")
        return out
    frames = frames_per_run[0]
    innermost, outer = frames[-1], frames[:-1]
    hit = [line for line in frames if line in written]
    out.update(origin_line=innermost, path_lines=outer, written_hits=hit)
    if innermost in written:
        out.update(after="moved", after_class="behavior_change",
                   why=f"raised on a line the change wrote ({path}:{innermost})")
    elif hit:
        out.update(
            after="moved",
            after_class="behavior_change",
            why=(
                f"raised on an unchanged line ({path}:{innermost}) reached through a "
                f"written line ({path}:{hit[0]})"
            ),
        )
    else:
        out.update(
            after="kept",
            after_class="regression_reproduced",
            why=f"raised on an unchanged line ({path}:{innermost}); no written line on the path",
        )
    if intent.get("origin_line") and intent.get("origin_line") != innermost:
        out["note"] = (
            f"the tracer recorded origin line {intent.get('origin_line')}, the longrepr's "
            f"innermost anchored frame is {innermost}"
        )
    return out


def heldout_jobs() -> list[dict]:
    results = json.loads(HELDOUT_RESULTS.read_text(encoding="utf-8"))["results"]
    jobs = []
    for r in results:
        case = HELDOUT_CASES / r["case"]
        manifest = json.loads((case / "manifest.json").read_text(encoding="utf-8"))
        jobs.append({
            "source": "heldout 2026-09-12 (35 cases)", "unit": r["case"], "task_id": r["task_id"],
            "ledger": case / "repo" / ".attest" / "ledger.jsonl", "repo": case / "repo",
            "base": manifest["base_sha"], "head": manifest["head_sha"],
        })
    return jobs


def e05_jobs() -> list[dict]:
    sample = {row["unit_id"]: row for row in _read_jsonl(E05 / "sample.jsonl")}
    jobs = []
    for trial in _read_jsonl(E05 / "trials.jsonl"):
        unit = sample[trial["unit_id"]]
        name = _clone_name(unit["repository"])
        jobs.append({
            "source": "e05-external-v1 run B (24 units)", "unit": trial["unit_id"],
            "task_id": trial["task_id"], "ledger": RUN_B / f"{name}-ledger.jsonl",
            "repo": GNULL / name, "base": unit["base_sha"], "head": unit["head_sha"],
        })
    return jobs


def run_a_jobs() -> list[dict]:
    sample = {row["unit_id"]: row for row in _read_jsonl(E04 / "sample.jsonl")}
    jobs = []
    for trial in _read_jsonl(E04 / "trials-runner-only5.jsonl"):
        unit = sample[trial["unit_id"]]
        name = _clone_name(unit["repository"])
        jobs.append({
            "source": "e04 run A (2 units)", "unit": trial["unit_id"], "task_id": trial["task_id"],
            "ledger": RUN_A / f"{name}-ledger.jsonl", "repo": CORPORA / name,
            "base": unit["base_sha"], "head": unit["head_sha"],
        })
    return jobs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    rows: list[dict] = []
    sources = Counter()
    for job in [*heldout_jobs(), *e05_jobs(), *run_a_jobs()]:
        ledger = _read_jsonl(job["ledger"])
        mine = [e for e in ledger if e.get("task_id") == job["task_id"]]
        assert mine, f"no ledger rows for {job['unit']} ({job['task_id']})"
        certified = {e["finding_id"] for e in mine
                     if e.get("kind") == "certification" and e.get("outcome") == "accepted"}
        for e in mine:
            if e.get("kind") != "verification":
                continue
            sources[job["source"]] += 1
            if e.get("outcome") != "reproduced":
                continue
            verdict = judge(e, job["repo"], job["base"], job["head"])
            verdict.update(source=job["source"], unit=job["unit"], task_id=job["task_id"],
                           certified=e["finding_id"] in certified)
            rows.append(verdict)
    assert rows, "no reproduced row in any ledger: the input is empty"
    reproduced = [r for r in rows]
    moved = [r for r in rows if r["after"] == "moved"]
    kept = [r for r in rows if r["after"] == "kept"]
    summary = {
        "verification_rows_read": dict(sources),
        "reproduced_rows": len(reproduced),
        "certified_rows": sum(1 for r in rows if r["certified"]),
        "moved_to_the_drawer": len(moved),
        "moved_certified": sum(1 for r in moved if r["certified"]),
        "kept_as_regression": len(kept),
        "unchanged": sum(1 for r in rows if r["after"] == "unchanged"),
        "unreadable": sum(1 for r in rows if r["after"] == "unreadable"),
        "by_source": {
            source: {
                "reproduced": sum(1 for r in rows if r["source"] == source),
                "certified": sum(1 for r in rows if r["source"] == source and r["certified"]),
                "moved": sum(1 for r in moved if r["source"] == source),
                "kept": sum(1 for r in kept if r["source"] == source),
            }
            for source in sorted({r["source"] for r in rows})
        },
    }
    attrs = {r["finding_id"]: r["after"] for r in rows if r["unit"] == "python-attrs/attrs#1603"}
    summary["attrs_1603"] = attrs
    payload = {"what": "D-232 replay: reproduced rows re-judged under attest.intent.v5",
               "policy": "attest.intent.v5", "summary": summary, "rows": rows}
    Path(args.out).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                              encoding="utf-8")
    print(json.dumps(summary, indent=2))
    for r in rows:
        print(f"{r['after']:10} {r['source'][:22]:22} {r['unit']:40} {str(r['finding_id']):12} "
              f"cert={r['certified']!s:5} {r['why']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
