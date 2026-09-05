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

``--independent`` selects the **second population** (owner instruction 1 of
2026-09-05c, D-136): the same eight clones and the same cutoff, a shifted
sampling seed, and every commit of the first 58-control population excluded, so
the two samples are disjoint. Its purpose is the one thing the first population
can no longer supply: n and a bound taken on controls no rule revision was
written against. **Its n and its bound are reported on their own and are never
merged into the first population's.**

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
RUNS = ROOT / "benchmarks" / "attest-v2" / "runs"
MANIFEST = RUNS / "2026-09-04-g-null-001a-population.json"
MANIFEST_INDEPENDENT = RUNS / "2026-09-05-g-null-001a-independent-population.json"

from qualify_controls import default_tip, qualify  # noqa: E402

# Preregistered before any qualification ran: the cutoff, the sampling seed and
# the per-repository quota. Changing one after seeing a result is p-hacking.
CUTOFF = "2026-03-04"  # six months before the measurement date
SEED = "g-null-001a/2026-09-04"
PER_REPO = 13
MAX_ATTEMPTS = 120  # qualification attempts per repository before giving up

# The independent population (D-136), preregistered here before it was sampled.
# Same eight clones, same cutoff, same control definition; a shifted seed, and
# the first population's commits removed from the pool. The quota **ladder** is
# part of the preregistration and not a knob: the smallest rung whose disjoint
# qualified count reaches `INDEPENDENT_TARGET` is the one used, and the rung
# that was reached is recorded in the manifest. Sampling is free, so the ladder
# costs nothing and settles before any paid call.
SEED_INDEPENDENT = "g-null-001a-independent/2026-09-05"
# (per-repository quota, qualification attempts per repository). The first
# rung is the first population's own setting; the ladder exists because the
# first draw has already taken the commits that qualify most easily, and the
# binding constraint turned out to be attempts, not quota. The draw is made
# once at the last rung and the chosen rung is read back from it -- the seeded
# order is fixed, so a smaller rung's draw is a prefix of a larger one's and
# the two constructions are identical.
INDEPENDENT_LADDER = ((13, 120), (16, 300), (20, 600), (25, 900))
INDEPENDENT_TARGET = 50


def git(repo: Path, *args: str, check: bool = True) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if check and result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()[:200]}")
    return result.stdout


def _order(sha: str, seed: str = SEED) -> str:
    """Deterministic sampling order: a fixed seed hashed with the commit id. No
    clock, no shuffle, and reproducible from the manifest alone."""
    return hashlib.sha256(f"{seed}\n{sha}".encode()).hexdigest()


def _manifest_path(independent: bool) -> Path:
    return MANIFEST_INDEPENDENT if independent else MANIFEST


def _seed_of(independent: bool) -> str:
    return SEED_INDEPENDENT if independent else SEED


def _first_population_shas() -> set[str]:
    """Every commit the first population examined -- qualified or not. Excluding
    the qualified 58 alone would leave the two samples disjoint in the controls
    they run; excluding everything the first draw looked at also keeps the
    second draw's *pool* clean of anything the first one has already touched."""
    if not MANIFEST.is_file():
        return set()
    population = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {str(row["sha"]) for row in population["controls"]}


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


def _draw(
    *,
    per_repo: int,
    seed: str,
    exclude: set[str],
    as_of: datetime,
    cache: dict[str, dict[str, object]],
    max_attempts: int = MAX_ATTEMPTS,
) -> list[dict[str, object]]:
    """One deterministic draw: per clone, walk the seeded order of the pre-cutoff
    pool, skipping `exclude`, qualifying until the quota is met."""
    rows: list[dict[str, object]] = []
    for clone in sorted(p for p in CORPORA.iterdir() if (p / ".git").exists()):
        tip = default_tip(clone)
        pool = [sha for sha in candidates(clone) if sha not in exclude]
        pool.sort(key=lambda sha: _order(sha, seed))
        kept = 0
        attempts = 0
        for sha in pool:
            if kept >= per_repo or attempts >= max_attempts:
                break
            attempts += 1
            row = cache.get(sha)
            if row is None:
                try:
                    verdict = qualify(clone, sha, as_of=as_of, tip=tip, early_stop=True)
                except RuntimeError as exc:
                    row = {
                        "repo": clone.name,
                        "sha": sha,
                        "qualified": False,
                        "reason": f"qualification failed: {exc}"[:200],
                    }
                else:
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
                cache[sha] = row
            rows.append({**row, "attempt": attempts})
            if row.get("qualified"):
                kept += 1
        print(f"{clone.name}: {kept} qualified of {attempts} examined ({len(pool)} in pool)")
    return rows


def _rung(rows: list[dict[str, object]], quota: int, attempts: int) -> list[dict[str, object]]:
    """The rows a draw at this rung would have produced, read off the deepest
    draw. The order is seeded and fixed, so this is the draw, not an estimate."""
    kept: dict[str, int] = {}
    chosen: list[dict[str, object]] = []
    for row in rows:
        repo = str(row["repo"])
        if int(row.get("attempt", 0)) > attempts or kept.get(repo, 0) >= quota:
            continue
        chosen.append(row)
        if row.get("qualified"):
            kept[repo] = kept.get(repo, 0) + 1
    return chosen


def cmd_sample(args: argparse.Namespace) -> int:
    as_of = datetime.now(UTC)
    seed = _seed_of(args.independent)
    exclude = _first_population_shas() if args.independent else set()
    cache: dict[str, dict[str, object]] = {}
    if args.independent:
        deepest_quota, deepest_attempts = INDEPENDENT_LADDER[-1]
        drawn = _draw(
            per_repo=deepest_quota,
            seed=seed,
            exclude=exclude,
            as_of=as_of,
            cache=cache,
            max_attempts=deepest_attempts,
        )
        quota, attempts_used = INDEPENDENT_LADDER[-1]
        rows = _rung(drawn, quota, attempts_used)
        for rung_quota, rung_attempts in INDEPENDENT_LADDER:
            candidate_rows = _rung(drawn, rung_quota, rung_attempts)
            reached = sum(1 for r in candidate_rows if r.get("qualified"))
            print(f"-- rung quota={rung_quota} attempts={rung_attempts}: n = {reached}")
            if reached >= INDEPENDENT_TARGET:
                quota, attempts_used = rung_quota, rung_attempts
                rows = candidate_rows
                break
    else:
        quota = args.per_repo
        rows = _draw(per_repo=quota, seed=seed, exclude=exclude, as_of=as_of, cache=cache)
    payload: dict[str, object] = {
        "schema_version": "attest.g-null-001a-population.v1",
        "gate": "G-NULL-001a",
        "cutoff": CUTOFF,
        "seed": seed,
        "per_repo_quota": quota,
        "as_of": as_of.isoformat(),
        "qualified": sum(1 for r in rows if r.get("qualified")),
        "examined": len(rows),
        "controls": rows,
    }
    if args.independent:
        payload["population"] = "independent"
        payload["disjoint_from"] = MANIFEST.name
        payload["excluded_commits"] = len(exclude)
        payload["ladder"] = [list(rung) for rung in INDEPENDENT_LADDER]
        payload["rung"] = [quota, attempts_used]
        payload["target_n"] = INDEPENDENT_TARGET
        payload["reporting"] = (
            "this sample carries its own n and its own bound; it is never merged "
            "into the 58-control population's"
        )
    path = _manifest_path(args.independent)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"n = {payload['qualified']} qualified controls -> {path}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    population = json.loads(_manifest_path(args.independent).read_text(encoding="utf-8"))
    seed = str(population["seed"])
    controls = [c for c in population["controls"] if c.get("qualified")]
    controls.sort(key=lambda c: (str(c["repo"]), _order(str(c["sha"]), seed)))
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


STATUS = re.compile(
    r"read (?P<read>\d+) of (?P<total>\d+) units; candidates: (?P<candidates>\d+); "
    r"eligible: (?P<eligible>\d+); reproductions attempted: (?P<attempted>\d+); "
    r"certified: (?P<certified>\d+); published: (?P<published>\d+)"
)
DEFER = re.compile(r"verification: [0-9a-f]+: (?P<reason>.+)")


def cmd_table(args: argparse.Namespace) -> int:
    """The result table, read from the **driver's own log**. The log is the only
    record that names the control beside its outcome: a `review_run` ledger row
    carries no head sha, so a ledger-only table cannot say which control a row
    is about, and a table that cannot do that is not a null study's table."""
    population = json.loads(_manifest_path(args.independent).read_text(encoding="utf-8"))
    by_sha = {str(c["sha"]): c for c in population["controls"] if c.get("qualified")}
    rows: list[dict[str, object]] = []
    text = Path(args.log).read_text(encoding="utf-8")
    for block in re.split(r"^=== gn ", text, flags=re.M)[1:]:
        head, _, body = block.partition("\n")
        parts = head.split()
        sha = parts[0]
        control = by_sha.get(sha)
        status = STATUS.search(body)
        spend = re.search(r"spend \$([0-9.]+) of", body)
        defers = [match.group("reason").strip()[:120] for match in DEFER.finditer(body)]
        rows.append(
            {
                "repo": parts[1] if len(parts) > 1 else "",
                "sha": sha[:10],
                "age_days": None if control is None else control["age_days"],
                "ran": "[rc " in body,
                "candidates": int(status["candidates"]) if status else None,
                "eligible": int(status["eligible"]) if status else None,
                "attempted": int(status["attempted"]) if status else None,
                "certified": int(status["certified"]) if status else None,
                "published": int(status["published"]) if status else None,
                "spend": float(spend.group(1)) if spend else 0.0,
                "verification_defers": defers,
            }
        )
    ran = [row for row in rows if row["ran"]]
    published = sum(int(row["published"] or 0) for row in ran)
    attempted = sum(int(row["attempted"] or 0) for row in ran)
    # A control that could not buy evidence cannot publish, so it carries no
    # information about wrong publication. `informative` is the denominator any
    # bound from this run must use, and it is **not** the number of controls run.
    informative = [
        row for row in ran if int(row["attempted"] or 0) > 0 and not row["verification_defers"]
    ]
    payload = {
        "schema_version": "attest.g-null-001a-result.v2",
        "gate": "G-NULL-001a",
        "population": "independent" if args.independent else "first",
        "manifest": _manifest_path(args.independent).name,
        "n_qualified": len(by_sha),
        "reviews": len(ran),
        "publications": published,
        "reproductions_attempted": attempted,
        "informative_controls": len(informative),
        "eligible_total": sum(int(row["eligible"] or 0) for row in ran),
        "spend_usd": round(sum(float(row["spend"] or 0.0) for row in ran), 6),
        "rows": rows,
    }
    if args.json:
        args.json.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"{len(ran)} of {len(by_sha)} controls reviewed, {payload['eligible_total']} eligible "
        f"candidates, {attempted} reproductions attempted, {len(informative)} informative "
        f"controls, {published} publications, ${payload['spend_usd']:.6f}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--per-repo", type=int, default=PER_REPO)
    s.add_argument("--independent", action="store_true", help="the second, disjoint population")
    s.set_defaults(func=cmd_sample)
    r = sub.add_parser("run")
    r.add_argument("--budget", type=float, required=True)
    r.add_argument("--cap", type=float, required=True, help="hard cumulative spend cap")
    r.add_argument("--log", required=True)
    r.add_argument("--verification-timeout", type=int, default=1200)
    r.add_argument("--independent", action="store_true", help="the second, disjoint population")
    r.set_defaults(func=cmd_run)
    t = sub.add_parser("table")
    t.add_argument("--json", type=Path)
    t.add_argument("--log", required=True, help="the driver log the run wrote")
    t.add_argument("--independent", action="store_true", help="the second, disjoint population")
    t.set_defaults(func=cmd_table)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
