"""All four levels, over real commits, in shadow (owner instruction 7 of 2026-09-06c).

One row per commit and one column per level, so the question "what does this
product actually say about ordinary work?" has an answer a person can read
without running anything:

  plan   free. The population: the most recent N commits of each named
         repository, newest first, each paired with its own parent.
  run    paid. One `attest review --base <parent> --explain` per commit, in a
         **clone**, head checked out detached. Local review only: no GitHub
         client is constructed, so **no publication surface exists** and every
         level's output is the terminal contract line (D-152). Afterwards the
         gate level's free static witness is computed over the review's own
         recorded new-code candidates, and its grade -- `through_caller`,
         `direct` or none -- is appended to the unit's block.
  table  free. The four-level table, read out of the run's log.

`red`, `yellow (a)`, `yellow (b)` and `green` come from the review itself;
`gate` is head-only and shadow by construction (D-137) -- it never reaches an
author and is recorded here only as a grade and a coordinate.

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
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.review.candidates import CandidateStore  # noqa: E402
from attest.review.gate_level import added_lines, show, witness  # noqa: E402

CORPORA = ROOT / ".attest" / "corpora"
LEVELS = ("red", "gate", "yellow", "green", "silent")
LINE = re.compile(r"^-?\s*\[(red|gate|yellow|green|silent)\] (.*)$")
ACCOUNTING = re.compile(
    r"^read (\d+)/(\d+) units, candidates (\d+), drawer (\d+)", flags=re.M
)
TASK = re.compile(r"^\[task (\S+)\]$")


def git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        raise RuntimeError(done.stderr.strip()[:200] or "git failed")
    return done.stdout.strip()


def cmd_plan(args: argparse.Namespace) -> int:
    units: list[dict[str, str]] = []
    for name in args.repos.split(","):
        repo = CORPORA / name.strip()
        if not repo.is_dir():
            print(f"no clone at {repo}", file=sys.stderr)
            return 2
        # newest first, and only commits that have a parent: a root commit has
        # no merge base and is not a change unit at all
        shas = git(repo, "log", "--format=%H %P", "-n", str(args.per_repo * 2), args.ref)
        taken = 0
        for row in shas.splitlines():
            parts = row.split()
            if len(parts) < 2 or taken >= args.per_repo:
                continue
            units.append({"repo": name.strip(), "head": parts[0], "base": parts[1]})
            taken += 1
    payload = {
        "schema_version": "attest.four-levels-plan.v1",
        "generated": datetime.now(UTC).isoformat(),
        "rule": (
            f"the most recent {args.per_repo} commits of each of {args.repos}, newest first, "
            "each paired with its first parent; root and parentless commits excluded"
        ),
        "units": units,
    }
    Path(args.json).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"{len(units)} units -> {args.json}")
    return 0


def _gate_grades(repo: Path, task_id: str, head: str, base: str) -> list[dict[str, object]]:
    """The gate level's free static witness over this review's new-code candidates.

    Head-only and author-invisible by construction: nothing here can publish, and
    the grade is the whole record (D-137)."""
    try:
        candidates = [
            candidate
            for candidate in CandidateStore(repo).load(task_id)
            if candidate.eligibility == "new_code" and candidate.action != "discard"
        ]
    except Exception:  # noqa: BLE001 - a study row, never a review
        return []
    if not candidates:
        return []
    try:
        added = added_lines(repo, base, head)
    except Exception:  # noqa: BLE001
        return []
    out: list[dict[str, object]] = []
    for candidate in candidates:
        path = candidate.finding.file
        try:
            source = show(repo, head, path)
            reach = witness(
                repo,
                head,
                path=path,
                origin_line=candidate.finding.line,
                added=added,
                head_source=source,
                test_source="",
            )
        except Exception:  # noqa: BLE001
            continue
        out.append(
            {
                "finding_id": candidate.finding.finding_id,
                "at": f"{path}:{candidate.finding.line}",
                "symbol": reach.symbol,
                "kind": reach.kind,
                "admissible": reach.admissible,
                "call_site": (
                    None
                    if reach.call_site is None
                    else f"{reach.call_site.path}:{reach.call_site.line}"
                ),
                "reason": reach.reason,
            }
        )
    return out


def _image_cache_rows(repo: Path, task_id: str) -> list[dict[str, object]]:
    """This task's `image_cache` rows: was the reproduction image reused? (D-156)"""
    ledger = repo / ".attest" / "ledger.jsonl"
    if not ledger.is_file() or not task_id:
        return []
    out: list[dict[str, object]] = []
    with ledger.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("kind") == "image_cache" and row.get("task_id") == task_id:
                out.append(
                    {
                        "tag": row.get("tag"),
                        "cached": row.get("cached"),
                        "build_elapsed_s": row.get("build_elapsed_s"),
                    }
                )
    return out


def cmd_run(args: argparse.Namespace) -> int:
    plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    log_path = Path(args.log)
    done: set[str] = set()
    spent = 0.0
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        for block in re.split(r"^=== unit ", text, flags=re.M)[1:]:
            head, _, body = block.partition("\n")
            if "[rc " in body:
                done.add(head.split()[0])
        seen = re.findall(r"\[cumulative spend \$([0-9.]+)\]", text)
        spent = float(seen[-1]) if seen else 0.0
    log = log_path.open("a", encoding="utf-8")  # noqa: SIM115 - appended across the loop
    env = dict(os.environ)
    # ``--code`` pins the *product* code to a fixed checkout, so an edit to the
    # working tree during a run cannot change what is being measured. It is the
    # standing fix for the 2026-09-06c operator error.
    code_root = Path(args.code) if args.code else ROOT
    env["PYTHONPATH"] = str(code_root / "src")
    if args.code:
        sha = subprocess.run(
            ["git", "-C", str(code_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
        ).stdout.strip()
        log.write(f"[code {code_root} {sha}]\n")
        print(f"product code from {code_root} ({sha})", flush=True)
    only = {value.strip() for value in args.only.split(",")} if args.only else None
    for unit in plan["units"]:
        head = str(unit["head"])
        if head in done:
            continue
        if only is not None and not any(head.startswith(prefix) for prefix in only):
            continue
        repo = CORPORA / str(unit["repo"])
        log.write(f"=== unit {head} {unit['repo']} base={str(unit['base'])[:10]}\n")
        if spent >= args.cap:
            log.write("[skipped: cumulative cap]\n")
            log.flush()
            continue
        try:
            git(repo, "checkout", "-q", "--detach", head)
        except RuntimeError as error:
            log.write(f"[skipped: {error}]\n[rc 99]\n")
            log.flush()
            continue
        unit_started = time.monotonic()
        done_run = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-c",
                "from attest.cli.main import main; import sys; sys.exit(main(sys.argv[1:]))",
                "--repo",
                str(repo),
                "review",
                "--base",
                str(unit["base"]),
                "--k",
                "4",
                "--budget",
                f"{args.budget:.2f}",
                "--explain",
                "--verification-timeout",
                str(args.verification_timeout),
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        log.write(
            done_run.stdout[-40000:] + done_run.stderr[-1500:] + f"\n[rc {done_run.returncode}]\n"
        )
        found = re.search(r"spend \$([0-9.]+) of", done_run.stdout)
        if found:
            spent += float(found.group(1))
        elapsed = time.monotonic() - unit_started
        task = _latest_task(repo)
        grades = _gate_grades(repo, task, head, str(unit["base"])) if task else []
        log.write("[gate " + json.dumps(grades) + "]\n")
        log.write("[images " + json.dumps(_image_cache_rows(repo, task)) + "]\n")
        log.write(f"[elapsed {elapsed:.2f}]\n")
        log.write(f"[cumulative spend ${spent:.6f}]\n")
        log.flush()
        print(
            f"{unit['repo']} {head[:10]} rc={done_run.returncode} "
            f"${spent:.4f} {elapsed:.1f}s",
            flush=True,
        )
    log.write("=== unit done\n")
    return 0


def _latest_task(repo: Path) -> str:
    """The task id of the review just run, read from the ledger's last row."""
    ledger = repo / ".attest" / "ledger.jsonl"
    if not ledger.is_file():
        return ""
    task = ""
    with ledger.open(encoding="utf-8") as handle:
        for row in handle:
            try:
                value = json.loads(row).get("task_id")
            except json.JSONDecodeError:
                continue
            if isinstance(value, str) and value:
                task = value
    return task


def cmd_table(args: argparse.Namespace) -> int:
    text = Path(args.log).read_text(encoding="utf-8")
    rows: list[dict[str, object]] = []
    for block in re.split(r"^=== unit ", text, flags=re.M)[1:]:
        header, _, body = block.partition("\n")
        parts = header.split()
        if len(parts) < 2:
            continue
        head, repo = parts[0], parts[1]
        spoken: dict[str, list[str]] = {level: [] for level in LEVELS}
        for line in body.splitlines():
            found = LINE.match(line.strip())
            if found:
                spoken[found.group(1)].append(line.strip())
        accounting = ACCOUNTING.search(body)
        elapsed_row = re.search(r"^\[elapsed ([0-9.]+)\]$", body, flags=re.M)
        images: list[dict[str, object]] = []
        images_row = re.search(r"^\[images (.*)\]$", body, flags=re.M)
        if images_row:
            try:
                images = json.loads(images_row.group(1))
            except json.JSONDecodeError:
                images = []
        spend_row = re.search(r"spend \$([0-9.]+) of", body)
        grades = []
        gate_row = re.search(r"^\[gate (.*)\]$", body, flags=re.M)
        if gate_row:
            try:
                grades = json.loads(gate_row.group(1))
            except json.JSONDecodeError:
                grades = []
        # yellow (a) and yellow (b) share the marker; the sentence tells them
        # apart, and it is the sentence a reader sees
        yellow_a = [
            line
            for line in spoken["yellow"]
            if "named by no test" in line or "gained a required parameter" in line
        ]
        yellow_b = [line for line in spoken["yellow"] if line not in yellow_a]
        rows.append(
            {
                "repo": repo,
                "head": head,
                "red": spoken["red"],
                "yellow_a": yellow_a,
                "yellow_b": yellow_b,
                "green": spoken["green"],
                "silent": spoken["silent"],
                "gate": grades,
                "units_read": int(accounting.group(1)) if accounting else None,
                "units_planned": int(accounting.group(2)) if accounting else None,
                "candidates": int(accounting.group(3)) if accounting else None,
                "drawer": int(accounting.group(4)) if accounting else None,
                "accounting": accounting.group(0) if accounting else "",
                "elapsed_s": float(elapsed_row.group(1)) if elapsed_row else None,
                "spend_usd": float(spend_row.group(1)) if spend_row else None,
                "images": images,
                "ran": "[rc 0]" in body,
            }
        )
    n = len(rows) or 1
    summary = {
        "units": len(rows),
        "ran": sum(1 for r in rows if r["ran"]),
        "red_spoke": sum(1 for r in rows if r["red"]),
        "yellow_a_spoke": sum(1 for r in rows if r["yellow_a"]),
        "yellow_b_spoke": sum(1 for r in rows if r["yellow_b"]),
        "green_spoke": sum(1 for r in rows if r["green"]),
        "gate_candidates": sum(len(r["gate"]) for r in rows),  # type: ignore[arg-type]
        "gate_admissible": sum(
            1
            for r in rows
            for g in r["gate"]
            if g.get("admissible")  # type: ignore[union-attr]
        ),
        "gate_through_caller": sum(
            1
            for r in rows
            for g in r["gate"]
            if g.get("kind") == "through_caller"  # type: ignore[union-attr]
        ),
        "gate_direct": sum(
            1
            for r in rows
            for g in r["gate"]
            if g.get("kind") == "direct"  # type: ignore[union-attr]
        ),
        "image_lookups": sum(len(r["images"]) for r in rows),  # type: ignore[arg-type]
        "image_hits": sum(
            1
            for r in rows
            for image in r["images"]
            if image.get("cached")  # type: ignore[union-attr]
        ),
        "all_silent": sum(
            1 for r in rows if not (r["red"] or r["yellow_a"] or r["yellow_b"] or r["green"])
        ),
    }
    timings = sorted(float(r["elapsed_s"]) for r in rows if r["elapsed_s"] is not None)
    if timings:
        middle = len(timings) // 2
        summary["median_elapsed_s"] = round(
            timings[middle] if len(timings) % 2 else (timings[middle - 1] + timings[middle]) / 2, 2
        )
        summary["total_elapsed_s"] = round(sum(timings), 2)
    spends = [float(r["spend_usd"]) for r in rows if r["spend_usd"] is not None]
    if spends:
        summary["total_spend_usd"] = round(sum(spends), 6)
    if summary["image_lookups"]:
        summary["image_hit_rate"] = round(
            summary["image_hits"] / summary["image_lookups"], 4  # type: ignore[operator]
        )
    summary["speech_rate"] = {
        level: round(summary[f"{level}_spoke"] / n, 4)  # type: ignore[operator]
        for level in ("red", "yellow_a", "yellow_b", "green")
    }
    payload = {
        "schema_version": "attest.four-levels.v1",
        "generated": datetime.now(UTC).isoformat(),
        "summary": summary,
        "rows": rows,
    }
    if args.json:
        Path(args.json).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=1))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("--repos", default="attest,us-stock-helper")
    plan.add_argument("--per-repo", type=int, default=20)
    plan.add_argument("--ref", default="HEAD")
    plan.add_argument("--json", required=True)
    plan.set_defaults(func=cmd_plan)
    run = sub.add_parser("run")
    run.add_argument("--plan", required=True)
    run.add_argument("--log", required=True)
    run.add_argument("--budget", type=float, default=1.00)
    run.add_argument("--cap", type=float, required=True)
    run.add_argument("--verification-timeout", type=float, default=600.0)
    run.add_argument("--code", default=None, help="fixed checkout whose attest code runs")
    run.add_argument("--only", default=None, help="comma-separated head sha prefixes")
    run.set_defaults(func=cmd_run)
    table = sub.add_parser("table")
    table.add_argument("--log", required=True)
    table.add_argument("--json")
    table.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
