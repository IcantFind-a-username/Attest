"""Real-traffic corpus driver (owner decision 1 of 2026-09-03g, mainline §5 decision C).

The population is frozen in ``docs/corpus/real-traffic-plan.md`` and is read from there,
never retyped: 20 defect pairs and 50 controls across ``Attest``, ``us-stock-helper`` and
``Corum``.

  plan      parse the frozen plan into ``benchmarks/attest-v2/runs/…-real-traffic-plan.json``
  qualify   D-116: for every defect pair, copy the repairing commit's own test files onto
            head (= ``F^``) and base (= ``F``) and run them there. A pair enters the run only
            when at least one test fails on head and every selected test passes on base.
            Free: no model call, no product code, no spend.
  run       one ``attest review`` per case, K=4, ``--budget 0.60`` (**not** the $0.25
            default), containers, local only. ``--cap`` stops the stream before the next
            case when the cumulative spend would pass it. A **control that publishes stops
            the stream at once** (``RISK-CERT-01``).
  table     the owner's table, one row per case, read from each case's ledger:
            repository, SHA, m (eligible candidates), certified, published, certified but
            below the family threshold, backend, spend.

Paid: ``run``. Reserve in DEVSPEND.md first.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPORA = ROOT / ".attest" / "corpora"
PLAN_SOURCE = ROOT / "docs" / "corpus" / "real-traffic-plan.md"
PLAN = ROOT / "benchmarks" / "attest-v2" / "runs" / "2026-09-03-real-traffic-plan.json"
REPO_DIR = {"Attest": "attest", "us-stock-helper": "us-stock-helper", "Corum": "corum"}
TEST_NAME = re.compile(r"(^|/)(test_[^/]+\.py|[^/]+_test\.py)$")
MAX_TEST_FILES = 3  # bound the free discrimination check per pair
# RISK-CERT-01 root cause, 2026-09-03: control c03 published, and it should have.
# `445c5a1` is the planted regression from the 2026-09-03d Action drill -- it removes
# the backslash normalisation in the benchmark matcher and its message calls that a
# redundant-replace cleanup, on purpose. The plan's control filter reads the subject
# and walks every ref, so a throwaway drill branch entered the control population. A
# commit reachable **only** from a `throwaway/` branch is a drill, not traffic.
MIS_STRATIFIED = {
    "c03": "a planted regression from the 2026-09-03d Action drill, reachable only from "
    "`throwaway/runner-check-2026-09-03`; its publication is a true positive and it is "
    "not in the control denominator"
}


def repo_path(repo: str) -> Path:
    return CORPORA / REPO_DIR[repo]


def git(repo: Path, *args: str, check: bool = True) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=check
    ).stdout.strip()


# --------------------------------------------------------------------------- plan


def _rows(section: str) -> list[list[str]]:
    return [
        [cell.strip().strip("`") for cell in line.strip().strip("|").split("|")]
        for line in section.splitlines()
        if line.startswith("|") and not set(line) <= set("|- ")
    ][1:]


def cmd_plan(args: argparse.Namespace) -> int:
    text = PLAN_SOURCE.read_text(encoding="utf-8")
    defects_section = text.split("## 4. The 20 defect pairs")[1].split("## 5.")[0]
    controls_section = text.split("## 5. The 50 controls")[1].split("## 6.")[0]
    cases = []
    for index, repo, fix, head, subject in _rows(defects_section):
        cases.append(
            {
                "id": f"d{int(index):02d}",
                "population": "defect",
                "repo": repo,
                "head": head,  # F^: the revision under review
                "base": fix,  # F: the repairing commit
                "subject": subject,
            }
        )
    for index, repo, commit, stratum, subject in _rows(controls_section):
        cases.append(
            {
                "id": f"c{int(index):02d}",
                "population": "control",
                "repo": repo,
                "head": commit,
                "base": "",  # the commit's own parent, resolved at run time
                "stratum": stratum,
                "subject": subject,
            }
        )
    for case in cases:  # every revision must exist before a single call is made
        resolved = git(repo_path(case["repo"]), "rev-parse", f"{case['head']}^{{commit}}")
        case["head"] = resolved
        if case["base"]:
            case["base"] = git(repo_path(case["repo"]), "rev-parse", f"{case['base']}^{{commit}}")
        else:
            case["base"] = git(repo_path(case["repo"]), "rev-parse", f"{resolved}^")
    PLAN.parent.mkdir(parents=True, exist_ok=True)
    PLAN.write_text(json.dumps(cases, indent=2, ensure_ascii=False), encoding="utf-8")
    defects = sum(1 for case in cases if case["population"] == "defect")
    print(f"{defects} defect pairs + {len(cases) - defects} controls -> {PLAN}")
    return 0


# ------------------------------------------------------------------------ qualify


def _fix_test_files(repo: Path, fix: str) -> list[str]:
    names = git(repo, "show", "--name-only", "--format=", "--diff-filter=AM", fix).splitlines()
    return [name for name in names if TEST_NAME.search(name)][:MAX_TEST_FILES]


def _project_root(tree: Path, test_file: str) -> Path:
    current = (tree / test_file).parent
    while current != tree and current != current.parent:
        if (current / "pyproject.toml").is_file() or (current / "setup.py").is_file():
            return current
        current = current.parent
    return tree


def _import_path(tree: Path, cwd: Path) -> list[str]:
    """Every place this tree publishes importable code: the project root the test
    belongs to, and every sibling project in the same checkout. A repository of
    several packages (``services/*/src``) does not install itself for a free
    discrimination check, so its own layout is the path."""
    places = [str(cwd), str(cwd / "src"), str(tree), str(tree / "src")]
    for manifest in sorted(tree.glob("*/*/pyproject.toml")) + sorted(
        tree.glob("*/pyproject.toml")
    ):
        places.extend([str(manifest.parent), str(manifest.parent / "src")])
    seen: list[str] = []
    for place in places:
        if place not in seen and Path(place).is_dir():
            seen.append(place)
    return seen


def _pytest(tree: Path, test_file: str, node: str | None = None) -> tuple[set[str], int, str]:
    """(failed node ids, passed count, note) for one test file -- or one node of it --
    run where the project declares itself. An empty note means pytest ran."""
    cwd = _project_root(tree, test_file)
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(_import_path(tree, cwd))
    relative = os.path.relpath(tree / test_file, cwd)
    target = f"{relative}::{node}" if node else relative
    completed = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            "-m",
            "pytest",
            target,
            "-p",
            "no:cacheprovider",
            "-o",
            "addopts=",  # a project's own -q would hide the summary this reads
            "-q",
            "--tb=no",
            "-rf",
        ],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=env,
        timeout=900,
    )
    text = completed.stdout + completed.stderr
    failed = {
        match.split("::", 1)[1]
        for match in re.findall(r"^FAILED (\S+)", text, flags=re.M)
        if "::" in match
    }
    passed = sum(int(count) for count in re.findall(r"(\d+) passed", text))
    if not failed and passed == 0:  # collection error, missing dependency, ...
        tail = text.strip().splitlines()[-1][:160] if text.strip() else "no output"
        return set(), 0, tail
    return failed, passed, ""


def cmd_qualify(args: argparse.Namespace) -> int:
    cases = json.loads(PLAN.read_text(encoding="utf-8"))
    out = []
    for case in cases:
        if case["population"] != "defect" or (args.repo and case["repo"] != args.repo):
            continue
        repo = repo_path(case["repo"])
        files = _fix_test_files(repo, case["base"])
        record = {**case, "test_files": files, "qualified": False, "reason": ""}
        if not files:
            record["reason"] = "the repairing commit ships no test file"
            out.append(record)
            print(json.dumps(record, ensure_ascii=False), flush=True)
            continue
        work = Path(tempfile.mkdtemp(prefix=f"qualify-{case['id']}-"))
        try:
            trees = {}
            for side, sha in (("head", case["head"]), ("base", case["base"])):
                tree = work / side
                git(repo, "worktree", "add", "--detach", "--force", str(tree), sha)
                trees[side] = tree
                for name in files:  # the fix's own tests, on both sides
                    target = tree / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_text(git(repo, "show", f"{case['base']}:{name}"), encoding="utf-8")
            for name in files:
                head_failed, head_passed, head_note = _pytest(trees["head"], name)
                base_failed, base_passed, base_note = _pytest(trees["base"], name)
                discriminating = sorted(head_failed - base_failed)
                record["observed"] = {
                    "file": name,
                    "head": head_note or f"{len(head_failed)} failed, {head_passed} passed",
                    "base": base_note or f"{len(base_failed)} failed, {base_passed} passed",
                    "head_only_failures": discriminating[:8],
                }
                if head_note or base_note:
                    record["reason"] = f"{name}: environment — {head_note or base_note}"
                    continue
                # the node must also be seen *passing* on base, not merely absent there
                confirmed = [
                    node
                    for node in discriminating[:8]
                    if _pytest(trees["base"], name, node)[1] == 1
                ]
                if confirmed:
                    record["qualified"] = True
                    record["reason"] = (
                        f"{name}: {len(confirmed)} test(s) fail on head and pass on base "
                        f"(first: {confirmed[0]})"
                    )
                    record["observed"]["confirmed"] = confirmed
                    break
                record["reason"] = (
                    f"{name}: head {len(head_failed)}F/{head_passed}P, "
                    f"base {len(base_failed)}F/{base_passed}P, no node discriminates"
                )
        finally:
            for tree in (work / "head", work / "base"):
                subprocess.run(
                    ["git", "-C", str(repo), "worktree", "remove", "--force", str(tree)],
                    capture_output=True,
                )
            shutil.rmtree(work, ignore_errors=True)
        out.append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    path = Path(args.out)
    existing = json.loads(path.read_text()) if path.is_file() and args.repo else []
    path.write_text(json.dumps(existing + out, indent=2, ensure_ascii=False), encoding="utf-8")
    qualified = sum(1 for row in out if row["qualified"])
    print(f"{qualified}/{len(out)} pairs qualified -> {path}")
    return 0


# ---------------------------------------------------------------------------- run


def cmd_run(args: argparse.Namespace) -> int:
    cases = json.loads(PLAN.read_text(encoding="utf-8"))
    qualified = {
        row["id"] for row in json.loads(Path(args.qualified).read_text()) if row["qualified"]
    }
    repo = repo_path(args.repo)
    env = dict(os.environ)
    env["PYTHONPATH"] = str(Path(args.code) / "src") if args.code else str(ROOT / "src")
    # Resume: a case whose block already ends in an "[rc …]" line ran to completion
    # and is not paid for twice; the cumulative figure carries over with it.
    done: set[str] = set()
    spent = 0.0
    log_path = Path(args.log)
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        for block in re.split(r"^=== rt ", text, flags=re.M)[1:]:
            head, _, body = block.partition("\n")
            # a case skipped for the cap has not run and is not "done": raising the
            # cap and resuming must reach it
            if "[rc " in body or "[dropped" in head:
                done.add(head.split()[0])
        cumulative = re.findall(r"\[cumulative spend \$([0-9.]+)\]", text)
        spent = float(cumulative[-1]) if cumulative else 0.0
    log = log_path.open("a", encoding="utf-8")  # noqa: SIM115 - appended across the loop
    order = [case for case in cases if case["repo"] == args.repo]
    order.sort(key=lambda case: (case["population"] != "defect", case["id"]))
    for case in order:
        if case["id"] in done:
            continue
        if case["id"] in MIS_STRATIFIED:
            log.write(
                f"=== rt {case['id']} {args.repo} {case['head']} "
                f"[dropped: mis-stratified — {MIS_STRATIFIED[case['id']]}]\n"
            )
            continue
        if case["population"] == "defect" and case["id"] not in qualified:
            log.write(f"=== rt {case['id']} {args.repo} {case['head']} [dropped: not qualified]\n")
            continue
        log.write(f"=== rt {case['id']} {args.repo} {case['head']} {case['subject'][:60]}\n")
        if spent >= args.cap:
            log.write("[skipped: cumulative cap]\n")
            log.flush()
            continue
        git(repo, "checkout", "-q", "--detach", case["head"])
        completed = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-c",
                "from attest.cli.main import main; import sys; sys.exit(main(sys.argv[1:]))",
                "--repo",
                str(repo),
                "review",
                "--base",
                case["base"],
                "--k",
                "4",
                "--budget",
                "0.60",
                "--verification-timeout",
                "1800",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        log.write(
            completed.stdout[-4000:] + completed.stderr[-1200:] + f"\n[rc {completed.returncode}]\n"
        )
        found = re.search(r"spend \$([0-9.]+) of", completed.stdout)
        if found:
            spent += float(found.group(1))
        log.write(f"[cumulative spend ${spent:.6f}]\n")
        log.flush()
        published = re.search(r"published: (\d+)", completed.stdout)
        if case["population"] == "control" and published and int(published.group(1)) > 0:
            log.write("=== rt STOP: a control published; RISK-CERT-01 root cause required\n")
            log.flush()
            print(f"STOP: control {case['id']} published", file=sys.stderr)
            return 3
    log.write("=== rt done\n")
    return 0


# -------------------------------------------------------------------------- table


def _ledger_rows(repo: Path) -> list[dict]:
    path = repo / ".attest" / "ledger.jsonl"
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return rows


def _completed_runs(repo: Path) -> list[tuple[str, float]]:
    """(task id, spend) for every review that finished, in ledger order."""
    return [
        (str(row["task_id"]), float(row.get("spend_usd") or 0.0))
        for row in _ledger_rows(repo)
        if row.get("kind") == "review_run" and row.get("task_id")
    ]


def _case_stats(repo: Path, task_id: str) -> dict:
    rows = [row for row in _ledger_rows(repo) if row.get("task_id") == task_id]
    policy = next((row for row in rows if row.get("kind") == "publication_policy"), {})
    run = next((row for row in rows if row.get("kind") == "review_run"), {})
    certifications = [row for row in rows if row.get("kind") == "certification"]
    accepted = [row for row in certifications if row.get("outcome") == "accepted"]
    # the backend the review actually selected; the per-candidate profile on an
    # ineligible candidate is the development default and says nothing about it
    backend_row = next((row for row in rows if row.get("kind") == "executor_backend"), {})
    backend = str(backend_row.get("profile") or "")
    if backend and not backend_row.get("available", True):
        backend += " (unavailable)"
    below = sum(
        1
        for item in policy.get("suppressed", [])
        if item.get("reason") == "below family threshold"
    )
    return {
        "m": policy.get("eligible_count", 0),
        "threshold": policy.get("family_threshold"),
        "certified": len(accepted),
        "published": len(policy.get("published", [])),
        "below": below,
        "behavior_change": sum(
            1 for row in accepted if row.get("evidence_class") == "behavior_change"
        ),
        "backend": backend or "—",
        "spend": run.get("spend_usd", 0.0),
    }


def cmd_table(args: argparse.Namespace) -> int:
    cases = {case["id"]: case for case in json.loads(PLAN.read_text(encoding="utf-8"))}
    print(
        "| # | repo | SHA | m | certified | published | certified, below family threshold "
        "| backend | spend |"
    )
    print("|---|---|---|---|---|---|---|---|---|")
    totals = {"m": 0, "certified": 0, "published": 0, "below": 0, "spend": 0.0}
    counted = 0
    blocks: dict[str, tuple[str, str]] = {}  # case id -> its LAST block: a cap-skipped
    position: dict[str, int] = {}  # execution order, which is what the ledger records
    for log_path in args.log:
        text = Path(log_path).read_text(encoding="utf-8")
        for block in re.split(r"^=== rt ", text, flags=re.M)[1:]:
            head, _, body = block.partition("\n")
            parts = head.split()
            if len(parts) < 3 or parts[0] in {"done", "STOP:"}:
                continue
            blocks[parts[0]] = (head, body)
            position[parts[0]] = len(position) + len(blocks)  # last occurrence wins
    # The log carries no task id. Each repository's completed reviews are matched to
    # its ledger runs in order, keyed on the spend the log printed: a review whose
    # driver was killed still finishes and still writes a ledger row, so position
    # alone is not enough.
    finished = [
        (key, blocks[key])
        for key in sorted(blocks, key=lambda name: position[name])
        if "budget;" in blocks[key][1] and "[dropped" not in blocks[key][0]
    ]
    for repo_name in {head.split()[1] for _key, (head, _body) in finished}:
        rows = [
            (key, float(re.search(r"spend \$([0-9.]+) of", body).group(1)))
            for key, (head, body) in finished
            if head.split()[1] == repo_name
        ]
        tasks = _completed_runs(repo_path(repo_name))
        cursor = 0
        for key, logged in rows:
            while cursor < len(tasks) and round(tasks[cursor][1], 4) != round(logged, 4):
                cursor += 1
            if cursor >= len(tasks):  # no run with that spend: leave the row unmatched
                continue
            head, body = blocks[key]
            blocks[key] = (f"{head} [task {tasks[cursor][0]}]", body)
            cursor += 1
    for head, body in [blocks[key] for key in sorted(blocks)]:
        parts = head.split()
        case_id, repo_name, sha = parts[0], parts[1], parts[2]
        stratum = cases.get(case_id, {}).get("stratum", "defect")
        if "[dropped" in head or "[skipped" in body:
            note = (
                "dropped: mis-stratified"
                if "mis-stratified" in head
                else "dropped: not qualified"
                if "[dropped" in head
                else "skipped: cap"
            )
            print(
                f"| {case_id} ({stratum}) | {repo_name} | `{sha[:10]}` | — | — | — | — "
                f"| — | {note} |"
            )
            continue
        task = re.search(r"\[task (\d{8}-\d{6}-[0-9a-f]{8})\]", head)
        stats = (
            _case_stats(repo_path(repo_name), task.group(1))
            if task
            else {
                "m": "—",
                "certified": "—",
                "published": "—",
                "below": "—",
                "backend": "—",
                "spend": 0.0,
            }
        )
        mis = case_id in MIS_STRATIFIED
        if not mis:  # a drill commit's numbers are real but belong to no population
            counted += 1
            for key in ("m", "certified", "published", "below", "spend"):
                if isinstance(stats[key], (int, float)):
                    totals[key] += stats[key]
        label = f"{case_id} (**mis-stratified**)" if mis else f"{case_id} ({stratum})"
        print(
            f"| {label} | {repo_name} | `{sha[:10]}` | {stats['m']} "
            f"| {stats['certified']} "
            f"| {stats['published']} | {stats['below']} | {stats['backend']} "
            f"| ${stats['spend']:.6f} |"
        )
    print(
        f"\n{counted} reviewed (mis-stratified rows excluded); eligible {totals['m']}; "
        f"certified {totals['certified']}; "
        f"published {totals['published']}; certified-but-below-threshold {totals['below']}; "
        f"spend ${totals['spend']:.6f} (mis-stratified spend excluded)"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan")
    plan.set_defaults(func=cmd_plan)
    qualify = sub.add_parser("qualify")
    qualify.add_argument("--out", required=True)
    qualify.add_argument("--repo", default=None)
    qualify.set_defaults(func=cmd_qualify)
    run = sub.add_parser("run")
    run.add_argument("--repo", required=True)
    run.add_argument("--log", required=True)
    run.add_argument("--qualified", required=True)
    run.add_argument("--cap", type=float, required=True)
    run.add_argument("--code", default=None, help="fixed checkout whose attest code runs")
    run.set_defaults(func=cmd_run)
    table = sub.add_parser("table")
    table.add_argument("--log", nargs="+", required=True)
    table.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
