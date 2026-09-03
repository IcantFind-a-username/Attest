"""`G-NULL-001a`: the affordable null study on public clones (D-122, D-127).

`G-NULL-001` needs n >= 300 controls to reach its <=1% bound and stays unpassed.
`G-NULL-001a` is the weaker gate whose claim must always carry its own n and
bound. This is its driver.

A control is the 2026-09-04 amendment's control, and nothing looser: a commit at
least six months old whose added lines no later commit on the default branch has
touched (`qualify_controls.py`, git only, no model call). This account owns no
such commits -- its repositories are weeks old -- so the population is read-only
clones of public repositories under `.attest/corpora/gnull/`.

  sample   walk each clone's pre-cutoff non-merge commits that touch Python,
           take a deterministic sample, qualify each, and write the manifest.
           Free. **The manifest is written and reviewed before anything is run.**
  run      one `attest review` per control, head = the control commit, base =
           its parent. Hard cumulative cap. **Any publication stops the whole
           run at once** for root cause under RISK-CERT-01.
  table    the result table, read from each clone's ledger.

Paid: `run`. Reserve in DEVSPEND.md first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
CORPORA = ROOT / ".attest" / "corpora" / "gnull"
MANIFEST = ROOT / "benchmarks" / "attest-v2" / "runs" / "2026-09-04-g-null-001a-population.json"

from qualify_controls import default_tip, qualify  # noqa: E402

# Preregistered before any qualification ran: the cutoff, the sampling seed and
# the per-repository quota. Changing one after seeing a result is p-hacking.
CUTOFF = "2026-03-04"  # six months before the measurement date
SEED = "g-null-001a/2026-09-04"
PER_REPO = 13
MAX_ATTEMPTS = 120  # qualification attempts per repository before giving up


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()[:200]}")
    return result.stdout


def _order(sha: str) -> str:
    """Deterministic sampling order: a fixed seed hashed with the commit id. No
    clock, no shuffle, and reproducible from the manifest alone."""
    return hashlib.sha256(f"{SEED}\n{sha}".encode()).hexdigest()


def candidates(repo: Path) -> list[str]:
    """Non-merge commits before the cutoff that touch a Python file and have a
    parent (a root commit has no base to review against)."""
    out = git(
        repo,
        "log",
        "--no-merges",
        f"--before={CUTOFF}",
        "--format=%H",
        "--min-parents=1",
        "--",
        "*.py",
    )
    return [line.strip() for line in out.splitlines() if line.strip()]


def cmd_sample(args: argparse.Namespace) -> int:
    as_of = datetime.now(UTC)
    rows: list[dict[str, object]] = []
    for clone in sorted(p for p in CORPORA.iterdir() if (p / ".git").exists()):
        tip = default_tip(clone)
        pool = sorted(candidates(clone), key=_order)
        kept = 0
        attempts = 0
        for sha in pool:
            if kept >= args.per_repo or attempts >= MAX_ATTEMPTS:
                break
            attempts += 1
            try:
                verdict = qualify(clone, sha, as_of=as_of, tip=tip, early_stop=True)
            except RuntimeError as exc:
                rows.append(
                    {
                        "repo": clone.name,
                        "sha": sha,
                        "qualified": False,
                        "reason": f"qualification failed: {exc}"[:200],
                    }
                )
                continue
            row = {
                "repo": clone.name,
                "sha": verdict.sha,
                "subject": verdict.subject[:120],
                "committed": verdict.committed,
                "age_days": round(verdict.age_days, 1),
                "added_lines": verdict.added,
                "surviving_lines": verdict.surviving,
                "qualified": verdict.qualifies,
                "reason": verdict.reason,
                "blame_truncated": verdict.truncated,
                "base": git(clone, "rev-parse", f"{sha}^").strip(),
            }
            rows.append(row)
            if verdict.qualifies:
                kept += 1
        print(f"{clone.name}: {kept} qualified of {attempts} examined ({len(pool)} in pool)")
    payload = {
        "schema_version": "attest.g-null-001a-population.v1",
        "gate": "G-NULL-001a",
        "cutoff": CUTOFF,
        "seed": SEED,
        "per_repo_quota": args.per_repo,
        "as_of": as_of.isoformat(),
        "qualified": sum(1 for r in rows if r.get("qualified")),
        "examined": len(rows),
        "controls": rows,
    }
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"n = {payload['qualified']} qualified controls -> {MANIFEST}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    population = json.loads(MANIFEST.read_text(encoding="utf-8"))
    controls = [c for c in population["controls"] if c.get("qualified")]
    controls.sort(key=lambda c: (str(c["repo"]), _order(str(c["sha"]))))
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")

    done: set[str] = set()
    spent = 0.0
    log_path = Path(args.log)
    if log_path.is_file():
        text = log_path.read_text(encoding="utf-8")
        for block in re.split(r"^=== gn ", text, flags=re.M)[1:]:
            head, _, body = block.partition("\n")
            if "[rc " in body:
                done.add(head.split()[0])
        seen = re.findall(r"\[cumulative spend \$([0-9.]+)\]", text)
        spent = float(seen[-1]) if seen else 0.0
    log = log_path.open("a", encoding="utf-8")  # noqa: SIM115 - appended across the loop

    for control in controls:
        sha = str(control["sha"])
        if sha in done:
            continue
        clone = CORPORA / str(control["repo"])
        log.write(
            f"=== gn {sha} {control['repo']} age={control['age_days']}d "
            f"{str(control['subject'])[:60]}\n"
        )
        if spent >= args.cap:
            log.write("[skipped: cumulative cap]\n")
            log.flush()
            continue
        git(clone, "checkout", "-q", "--detach", sha)
        completed = subprocess.run(
            [
                str(ROOT / ".venv" / "bin" / "python"),
                "-c",
                "from attest.cli.main import main; import sys; sys.exit(main(sys.argv[1:]))",
                "--repo",
                str(clone),
                "review",
                "--base",
                str(control["base"]),
                "--k",
                "4",
                "--budget",
                f"{args.budget:.2f}",
                "--verification-timeout",
                str(args.verification_timeout),
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
        if published and int(published.group(1)) > 0:
            log.write("=== gn STOP: a control published; RISK-CERT-01 root cause required\n")
            log.flush()
            print(f"STOP: control {control['repo']} {sha} published", file=sys.stderr)
            return 3
    log.write("=== gn done\n")
    return 0


def cmd_table(args: argparse.Namespace) -> int:
    population = json.loads(MANIFEST.read_text(encoding="utf-8"))
    by_sha = {str(c["sha"]): c for c in population["controls"] if c.get("qualified")}
    rows: list[dict[str, object]] = []
    for clone in sorted(p for p in CORPORA.iterdir() if (p / ".attest" / "ledger.jsonl").is_file()):
        text = (clone / ".attest" / "ledger.jsonl").read_text(encoding="utf-8")
        ledger = [json.loads(line) for line in text.splitlines()]
        runs = {r["task_id"]: r for r in ledger if r.get("kind") == "review_run"}
        for row in ledger:
            if row.get("kind") != "publication_policy":
                continue
            task = str(row["task_id"])
            run = runs.get(task, {})
            head = str(run.get("head_sha", ""))
            control = by_sha.get(head)
            rows.append(
                {
                    "repo": clone.name,
                    "task_id": task,
                    "head": head[:10],
                    "age_days": None if control is None else control["age_days"],
                    "eligible": row["eligible_count"],
                    "units": len(row.get("eligible_units", {}) or {}),
                    "published": len(row["published"]),
                    "suppressed": len(row["suppressed"]),
                    "spend": run.get("spend_usd"),
                }
            )
    published = sum(int(r["published"] or 0) for r in rows)
    payload = {
        "schema_version": "attest.g-null-001a-result.v1",
        "gate": "G-NULL-001a",
        "reviews": len(rows),
        "publications": published,
        "eligible_total": sum(int(r["eligible"] or 0) for r in rows),
        "rows": rows,
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(rows)} control reviews, {published} publications")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--per-repo", type=int, default=PER_REPO)
    s.set_defaults(func=cmd_sample)
    r = sub.add_parser("run")
    r.add_argument("--budget", type=float, required=True)
    r.add_argument("--cap", type=float, required=True, help="hard cumulative spend cap")
    r.add_argument("--log", required=True)
    r.add_argument("--verification-timeout", type=int, default=1200)
    r.set_defaults(func=cmd_run)
    t = sub.add_parser("table")
    t.add_argument("--json", type=Path)
    t.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
