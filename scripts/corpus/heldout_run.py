"""E-02 held-out driver (mainline §2 step 13): plan, build, run, tabulate.

Runs from a fixed checkout of the attest code (pass ``--code <worktree>``) against the
primary checkout's corpus, so editing ``src/`` during the run cannot change later cases.

  plan      write the population by id only (held-out slice, feasible repositories, first 40)
  build     build every planned case without a host virtualenv (the container builds its image)
  run       one run per case, K=4, through linux-container-v1, results suffixed ``.heldout``
  table     the step-13 table: per population and per case, silence reasons, truncation,
            diff boundary hits, cache-read share, spend

Paid: ``run``. Reserve in DEVSPEND.md first.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAN = ROOT / "benchmarks" / "attest-v2" / "runs" / "2026-09-03-e02-heldout-plan.json"
SPLIT = ROOT / "benchmarks" / "attest-v2" / "splits" / "swebench-verified-v1.json"
RESULTS = ROOT / ".attest" / "corpora" / "swebench" / "results"
CASES = ROOT / ".attest" / "corpora" / "swebench" / "cases"
FEASIBLE = ("psf__requests", "pytest-dev__pytest", "pylint-dev__pylint")
K = 4


def cmd_plan(_args: argparse.Namespace) -> int:
    held = json.loads(SPLIT.read_text())["held_out"]
    ids = sorted(i for i in held if any(i.startswith(p + "-") for p in FEASIBLE))
    defects = ids[:40]
    controls = [(i, "test-only") for i in ids[:40]] + [
        (i, "docs-only") for i in ids[: max(0, 40 - len(ids))]
    ]
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(
        json.dumps(
            {
                "defects": defects,
                "controls": controls,
                "rule": (
                    "held-out slice, feasible repositories, sorted ids, first 40; "
                    "controls: test-only per defect, docs-only for the first 40-n"
                ),
            },
            indent=2,
        )
    )
    print(f"{len(defects)} defects, {len(controls)} controls -> {PLAN}")
    return 0


def _jobs() -> list[tuple[str, str | None]]:
    plan = json.loads(PLAN.read_text())
    return [(i, None) for i in plan["defects"]] + [(i, c) for i, c in plan["controls"]]


def cmd_build(_args: argparse.Namespace) -> int:
    for iid, control in _jobs():
        argv = [
            sys.executable,
            str(ROOT / "scripts" / "corpus" / "swebench_pilot.py"),
            "build",
            iid,
            "--no-env",
        ]
        if control:
            argv += ["--control", control]
        print("build", iid, control or "regression", flush=True)
        subprocess.run(argv, check=False)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    pilot = (
        Path(args.code) / "scripts" / "corpus" / "swebench_pilot.py"
        if args.code
        else ROOT / "scripts" / "corpus" / "swebench_pilot.py"
    )
    env = dict(**__import__("os").environ)
    if args.code:
        env["PYTHONPATH"] = str(Path(args.code) / "src")
    only = set(args.only.split(",")) if args.only else None
    for iid, control in _jobs():
        if only is not None and iid not in only:
            continue
        if args.defects_only and control:
            continue
        argv = [
            sys.executable,
            str(pilot),
            "run",
            iid,
            "--k",
            str(K),
            "--verification-timeout",
            "900",
            "--results-suffix",
            ".heldout",
        ]
        if control:
            argv += ["--control", control]
        print("run", iid, control or "regression", flush=True)
        subprocess.run(argv, check=False, env=env)
    return 0


def cmd_table(_args: argparse.Namespace) -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from attest.review.status import categorise_failure

    rows = []
    for path in sorted(RESULTS.glob("*.heldout.json")):
        summary = json.loads(path.read_text())
        case = CASES / summary["case"]
        ledger = [
            json.loads(line)
            for line in (case / "repo" / ".attest" / "ledger.jsonl").read_text().splitlines()
        ]
        mine = [e for e in ledger if e.get("task_id") == summary["task_id"]]
        eligible = sum(
            1
            for e in mine
            if e.get("kind") == "eligibility" and e.get("eligibility") == "regression"
        )
        certified = sum(
            1 for e in mine if e.get("kind") == "certification" and e.get("outcome") == "accepted"
        )
        verifications = [e for e in mine if e.get("kind") == "verification"]
        reasons = [
            str(e.get("reason", "")) for e in verifications if e.get("outcome") != "reproduced"
        ]
        categories = Counter(
            "unfaithful test" if "passed on head" in r else categorise_failure(r) for r in reasons
        )
        samples = [
            s
            for e in mine
            if e.get("kind") == "review_run"
            for s in (e.get("provider_samples") or [])
        ]
        truncated = sum(1 for s in samples if s.get("stop_reason") == "max_tokens")
        plan_units = max(
            (len(e.get("units") or []) for e in mine if e.get("kind") == "review_plan"), default=0
        )
        boundary_hits = max(0, plan_units - len(samples) // K) if plan_units else 0
        prompt = sum(
            int(s.get("input_tokens") or 0)
            + int(s.get("cache_creation_input_tokens") or 0)
            + int(s.get("cache_read_input_tokens") or 0)
            for s in samples
        )
        read = sum(int(s.get("cache_read_input_tokens") or 0) for s in samples)
        rows.append(
            {
                "case": summary["case"],
                "control": summary["control"] or "-",
                "candidates": summary["candidate_count"],
                "eligible": eligible,
                "certified": certified,
                "published": summary["surfaced_count"],
                "attempts": len(verifications),
                "failures": dict(categories),
                "samples": len(samples),
                "truncated": truncated,
                "boundary_hits": boundary_hits,
                "prompt_tokens": prompt,
                "cache_read": read,
                "spend": summary["spend_usd"],
            }
        )
    defects = [r for r in rows if r["control"] == "-"]
    controls = [r for r in rows if r["control"] != "-"]

    def agg(group: list[dict]) -> dict:
        keys = (
            "candidates",
            "eligible",
            "certified",
            "published",
            "samples",
            "truncated",
            "boundary_hits",
            "spend",
            "prompt_tokens",
            "cache_read",
        )
        out = {k: sum(r[k] for r in group) for k in keys}
        out["n"] = len(group)
        return out

    print(
        "| population | n | candidates | eligible | certified | published | samples | "
        "truncated | boundary hits | cache read share | spend |"
    )
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for name, group in (("defects", defects), ("controls", controls)):
        a = agg(group)
        share = a["cache_read"] / a["prompt_tokens"] if a["prompt_tokens"] else 0.0
        print(
            f"| {name} | {a['n']} | {a['candidates']} | {a['eligible']} | {a['certified']} | "
            f"{a['published']} | {a['samples']} | {a['truncated']} | {a['boundary_hits']} | "
            f"{share:.0%} | ${a['spend']:.4f} |"
        )
    cert_defects = sum(1 for r in defects if r["certified"] > 0)
    pub_defects = sum(1 for r in defects if r["published"] > 0)
    elig_defects = sum(1 for r in defects if r["eligible"] > 0)
    fp = sum(r["published"] for r in controls)
    print()
    print(
        f"per defect: certified on {cert_defects}/{len(defects)}, published on "
        f"{pub_defects}/{len(defects)}, with an eligible candidate {elig_defects}/{len(defects)}"
    )
    print(f"control false publications: {fp}/{len(controls)} cases")
    if pub_defects + fp:
        print(
            f"precision (published defect findings / all published): "
            f"{pub_defects}/{pub_defects + fp} = {pub_defects / (pub_defects + fp):.2f}"
        )
    if defects:
        print(
            f"recall per defect: {cert_defects}/{len(defects)} = "
            f"{cert_defects / len(defects):.2f}; eligible detection: {cert_defects}/{elig_defects}"
        )
    silent = [r for r in defects if r["published"] == 0]
    reasons = Counter()
    for r in silent:
        if r["candidates"] == 0:
            reasons["no candidates"] += 1
        elif r["eligible"] == 0:
            reasons["no eligible candidate"] += 1
        elif r["attempts"] == 0:
            reasons["not attempted"] += 1
        else:
            for cat, n in r["failures"].items():
                reasons[cat] += n
    print(f"silence rate on defects: {len(silent)}/{len(defects)}; reasons: {dict(reasons)}")
    total = agg(rows)
    print(
        f"truncation rate: {total['truncated']}/{total['samples']} samples; "
        f"diff boundary hits: {total['boundary_hits']}"
    )
    print()
    print("| case | control | candidates | eligible | certified | published | failures | spend |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        print(
            f"| {r['case']} | {r['control']} | {r['candidates']} | {r['eligible']} | "
            f"{r['certified']} | {r['published']} | {r['failures'] or '-'} | ${r['spend']:.4f} |"
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan").set_defaults(func=cmd_plan)
    sub.add_parser("build").set_defaults(func=cmd_build)
    run = sub.add_parser("run")
    run.add_argument("--code", default=None, help="fixed checkout whose attest code runs the cases")
    run.add_argument("--only", default=None, help="comma-separated instance ids to (re-)run")
    run.add_argument("--defects-only", action="store_true", help="skip the control cases")
    run.set_defaults(func=cmd_run)
    sub.add_parser("table").set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
