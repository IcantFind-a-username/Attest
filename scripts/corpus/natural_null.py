"""E-01 natural-null driver (mainline §2 step 14) over the owner's us-stock-helper history.

  select   choose 20 real commits with no known defect (refactor/test, docs, feature classes,
           by subject; never a fix) from the corpus clone
  run      head = commit, base = parent, `attest review --base <parent> --k 4` through the
           container backend, sequential, stops at the spend cap
  table    the step-14 table from the run log

Paid: ``run``. Reserve in DEVSPEND.md first. Any publication is a RISK-CERT-01 root cause.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / ".attest" / "corpora" / "us-stock-helper"
PLAN = ROOT / "benchmarks" / "attest-v2" / "runs" / "2026-09-03-e01-natural-null-plan.json"
QUOTA = {"docs": 6, "refactor": 7, "feature": 7}


def _classify(message: str) -> str | None:
    head = message.lower().split(":")[0]
    if "fix" in head or "bug" in head or "revert" in head:
        return None
    if head.startswith(("docs", "doc")):
        return "docs"
    if head.startswith(("refactor", "chore", "style", "test", "tests", "build", "ci")):
        return "refactor"
    if head.startswith(("feat", "add")):
        return "feature"
    return None


def cmd_select(args: argparse.Namespace) -> int:
    log = subprocess.run(
        ["git", "-C", str(CORPUS), "log", "--format=%h|%s", "--no-merges", "-600", args.ref],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    picked: dict[str, list[dict]] = {k: [] for k in QUOTA}
    for line in log.splitlines():
        sha, _, message = line.partition("|")
        cls = _classify(message)
        if cls is None or len(picked[cls]) >= QUOTA[cls]:
            continue
        stat = subprocess.run(
            ["git", "-C", str(CORPUS), "show", "--stat", "--format=", sha],
            capture_output=True,
            text=True,
        ).stdout
        files = [item.split("|")[0].strip() for item in stat.splitlines() if "|" in item]
        if (
            not files
            or len(files) > 60
            or (cls != "docs" and not any(f.endswith(".py") for f in files))
        ):
            continue
        picked[cls].append({"sha": sha, "class": cls, "message": message, "files": len(files)})
    plan = picked["refactor"] + picked["docs"] + picked["feature"]
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(json.dumps(plan, indent=2, ensure_ascii=False))
    print(f"{len(plan)} commits -> {PLAN}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    plan = json.loads(PLAN.read_text())
    env = dict(os.environ)
    if args.code:
        env["PYTHONPATH"] = str(Path(args.code) / "src")
    spent = 0.0
    log = Path(args.log).open("a", encoding="utf-8")  # noqa: SIM115 - appended across the loop
    only = set(args.only.split(",")) if args.only else None
    for row in plan:
        sha = row["sha"]
        if only is not None and sha not in only:
            continue
        subprocess.run(["git", "-C", str(CORPUS), "checkout", "-q", "--detach", sha], check=True)
        parent = subprocess.run(
            ["git", "-C", str(CORPUS), "rev-parse", f"{sha}^"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        log.write(f"=== e01 {row['class']} {sha} {row['message'][:60]}\n")
        if spent >= args.cap:
            log.write("[skipped: budget cap]\n")
            continue
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "from attest.cli.main import main; import sys; sys.exit(main(sys.argv[1:]))",
                "--repo",
                str(CORPUS),
                "review",
                "--base",
                parent,
                "--k",
                "4",
                "--budget",
                "0.25",
                "--verification-timeout",
                "900",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        log.write(
            completed.stdout[-2500:] + completed.stderr[-800:] + f"\n[rc {completed.returncode}]\n"
        )
        found = re.search(r"spend \$([0-9.]+) of", completed.stdout)
        if found:
            spent += float(found.group(1))
        log.write(f"[cumulative spend ${spent:.4f}]\n")
        log.flush()
    log.write("=== e01 done\n")
    return 0


def cmd_table(args: argparse.Namespace) -> int:
    text = Path(args.log).read_text(encoding="utf-8")
    plan = {r["sha"]: r for r in json.loads(PLAN.read_text())}
    blocks = re.split(r"^=== e01 ", text, flags=re.M)[1:]
    print(
        "| class | commit | files | units | candidates | eligible | reproductions | "
        "published | spend |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    published_total = 0
    spend_total = 0.0
    for block in blocks:
        head, _, body = block.partition("\n")
        parts = head.split()
        if len(parts) < 2 or parts[0] == "done":
            continue
        cls, sha = parts[0], parts[1]
        status = re.search(
            # a budget-bound run says "read N of M units, budget-limited" instead
            r"(?:change units read: (?P<read>\d+)|read (?P<partial>\d+) of \d+ units, "
            r"budget-limited); candidates: (\d+); eligible: (\d+); "
            r"reproductions attempted: (\d+); certified: (\d+); published: (\d+)",
            body,
        )
        spend = re.search(r"spend \$([0-9.]+) of", body)
        cells = (
            (status.group("read") or status.group("partial"), *status.groups()[2:])
            if status
            else ("-",) * 6
        )
        amount = float(spend.group(1)) if spend else 0.0
        spend_total += amount
        published_total += int(cells[5]) if status else 0
        print(
            f"| {cls} | `{sha}` {plan[sha]['message'][:60]} | {plan[sha]['files']} | "
            f"{cells[0]} | {cells[1]} | {cells[2]} | {cells[3]} | {cells[5]} | ${amount:.4f} |"
        )
    print(f"\npublications: {published_total}/{len(plan)} commits; spend ${spend_total:.4f}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    select = sub.add_parser("select")
    select.add_argument("--ref", default="origin/feature/iphone-demo")
    select.set_defaults(func=cmd_select)
    run = sub.add_parser("run")
    run.add_argument("--log", required=True)
    run.add_argument(
        "--code", default=None, help="fixed checkout whose attest code runs the reviews"
    )
    run.add_argument("--cap", type=float, default=1.85)
    run.add_argument("--only", default=None, help="comma-separated commit ids to (re-)run")
    run.set_defaults(func=cmd_run)
    table = sub.add_parser("table")
    table.add_argument("--log", required=True)
    table.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
