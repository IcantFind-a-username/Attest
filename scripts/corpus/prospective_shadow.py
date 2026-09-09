"""E-04 prospective shadow driver (mainline §2 step 15).

  freeze    write the study's freeze digest (protocol + preregistration + authorization)
  select    record every commit pushed to a population repository after the freeze, with
            its stratum and the silent-audit draw, BEFORE any outcome (sample.jsonl)
  select-prs  the same, but the unit is a PULL REQUEST (stratum v3): head =
            refs/pull/N/head, base = merge-base(head, the pull request's base branch),
            which is the pair the shipped Action reviews
  run       one shadow review per sampled unit not yet run: head = the commit, base = its
            parent, the local review path (no GitHub client exists), K and per-PR budget
            from the preregistration, results to trials.jsonl; stops at the cost cap
  report    report.json + the table

Paid: ``run`` (pass --allow-paid-api). Reserve in DEVSPEND.md first. Population
repositories are clones under .attest/corpora/<name>/ (AGENTS.md §7).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
STUDIES = ROOT / "benchmarks" / "studies"
# stratum v1 stays the default so every recorded command keeps meaning what it
# meant; `--study` selects another stratum (v2 is the 100-unit run of 2026-09-04)
STUDY = STUDIES / "e04-prospective-v1"
CORPORA = ROOT / ".attest" / "corpora"

from attest.benchmark import prospective  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def cmd_freeze(args: argparse.Namespace) -> int:
    print(prospective.freeze(_study(args)))
    return 0


def _study(args: argparse.Namespace) -> Path:
    return STUDIES / args.study if getattr(args, "study", None) else STUDY


def _clone_name(repository: str) -> str:
    # a repository name may begin with "-" (the owner has one); a leading dash is
    # not a legal argument prefix and the clone drops it
    return repository.split("/")[-1].lower().lstrip("-")


# Declared in the v3 protocol before any unit ran: a drill carries a planted
# defect, so a publication on it is a true positive and it may not sit in the
# false-publication denominator. Matched case-insensitively on the title.
DRILL_MARKERS = ("throwaway", "do not merge")


def _drill(title: str) -> bool:
    lowered = title.lower()
    return any(marker in lowered for marker in DRILL_MARKERS)


def cmd_select_prs(args: argparse.Namespace) -> int:
    """Stratum v3: one unit per pull request, resolved in the clone.

    `gh` lists the pull requests; the shas are resolved locally against
    `refs/pull/N/head`, which survives a deleted branch, so a merged pull
    request is reviewable exactly as it was opened."""
    study = _study(args)
    raw = json.loads((study / "preregistration.json").read_text(encoding="utf-8"))
    target = int(raw.get("target_units", 0))
    per_repo: dict[str, list[prospective.TrafficUnit]] = {}
    excluded: list[dict[str, str]] = []
    for repository in raw["population"]:
        repo = CORPORA / _clone_name(repository)
        if not repo.is_dir():
            print(f"skip {repository}: no clone at {repo}", file=sys.stderr)
            continue
        listed = subprocess.run(
            ["gh", "pr", "list", "--repo", repository, "--state", "all", "--limit", "100",
             "--json", "number,title,createdAt,baseRefName,changedFiles,state"],
            capture_output=True, text=True, check=False,
        )
        if listed.returncode != 0:
            print(f"skip {repository}: {listed.stderr.strip()[:120]}", file=sys.stderr)
            continue
        pulls = sorted(json.loads(listed.stdout or "[]"),
                       key=lambda item: str(item["createdAt"]), reverse=True)
        if not pulls:
            continue
        subprocess.run(
            [
                "git", "-C", str(repo), "fetch", "-q", "origin",
                "+refs/pull/*/head:refs/remotes/origin/pr/*",
                "+refs/heads/*:refs/remotes/origin/*",
            ],
            check=False,
        )
        for pull in pulls:
            number = int(pull["number"])
            title = str(pull["title"])
            if _drill(title):
                excluded.append({"unit_id": f"{repository}#{number}", "title": title,
                                 "reason": "drill: the title declares a planted defect"})
                continue
            # The base is the sha the pull request was opened against, taken
            # from the API, **not** `merge-base(head, the base branch today)`.
            # For a merged pull request the base branch already contains the
            # head, so that merge-base is the head itself and the diff is empty
            # -- which is how this driver's first draft reviewed nine units of
            # nothing. `base.sha` is the field the shipped Action resolves.
            api = subprocess.run(
                ["gh", "api", f"repos/{repository}/pulls/{number}",
                 "--jq", "[.base.sha, .head.sha] | @tsv"],
                capture_output=True, text=True, check=False,
            )
            if api.returncode != 0 or not api.stdout.strip():
                print(f"skip {repository}#{number}: {api.stderr.strip()[:100]}", file=sys.stderr)
                continue
            base_sha, head_sha = api.stdout.strip().split("\t")
            try:
                head = _git(repo, "rev-parse", f"refs/remotes/origin/pr/{number}")
                if head != head_sha:
                    # the pull request was force-pushed after the ref was cached;
                    # the API's head is the authority
                    head = _git(repo, "rev-parse", head_sha)
                base = _git(repo, "merge-base", head, base_sha)
            except subprocess.CalledProcessError as exc:
                print(f"skip {repository}#{number}: {exc}", file=sys.stderr)
                continue
            if base == head:
                print(f"skip {repository}#{number}: empty diff at its own base", file=sys.stderr)
                continue
            per_repo.setdefault(repository, []).append(
                prospective.TrafficUnit(
                    unit_id=f"{repository}#{number}",
                    repository=repository,
                    head_sha=head,
                    base_sha=base,
                    subject=title[:120],
                    stratum=prospective.classify_subject(title),
                    changed_files=int(pull.get("changedFiles") or 0),
                    pushed_at=str(pull["createdAt"]),
                )
            )
    # newest first within a repository, round-robin across repositories in name
    # order, so a cost cap removes units evenly rather than by alphabet
    units: list[prospective.TrafficUnit] = []
    index = 0
    limit = target or sum(len(group) for group in per_repo.values())
    while len(units) < limit and any(index < len(g) for g in per_repo.values()):
        for name in sorted(per_repo):
            if len(units) >= limit:
                break
            group = per_repo[name]
            if index < len(group):
                units.append(group[index])
        index += 1
    rows = prospective.record_sample(study, units, recorded_at=datetime.now(UTC).isoformat())
    (study / "excluded.json").write_text(
        json.dumps({"rule": raw["exclusion_declared_before_any_run"], "units": excluded},
                   indent=2, ensure_ascii=False) + "\n"
    )
    print(f"{len(units)} pull requests selected, {len(rows)} newly recorded; "
          f"{len(excluded)} excluded as drills -> {study / 'sample.jsonl'}")
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    study = _study(args)
    preregistration = prospective.load_preregistration(study)
    raw = json.loads((study / "preregistration.json").read_text(encoding="utf-8"))
    # stratum v2 (2026-09-04): the units are the most recent commits, not the
    # ones made after the freeze. `prospective: false` in the preregistration is
    # what selects this mode, and the protocol says out loud that a claim from
    # such a stratum may not be called prospective.
    recent = raw.get("prospective") is False
    target = int(raw.get("target_units", 0))
    freeze_at = datetime.fromisoformat(preregistration.freeze_at)
    units: list[prospective.TrafficUnit] = []
    for repository in preregistration.population:
        repo = CORPORA / _clone_name(repository)
        if not repo.is_dir():
            print(f"skip {repository}: no clone at {repo}", file=sys.stderr)
            continue
        if not args.no_fetch:
            subprocess.run(["git", "-C", str(repo), "fetch", "--all", "-q"], check=False)
        if recent:
            # the protocol's rule is "newest first, up to target_units" over the
            # population as a whole: take at most `target` from each repository
            # here and cut to the newest `target` across all of them below, so a
            # repository with a short history does not shrink the sample
            log = _git(
                repo, "log", "--no-merges", f"--max-count={target}", "--format=%H|%cI|%s"
            )
        else:
            log = _git(
                repo,
                "log",
                "--all",
                "--no-merges",
                f"--since={freeze_at.isoformat()}",
                "--format=%H|%cI|%s",
            )
        for line in log.splitlines():
            sha, committed, subject = line.split("|", 2)
            if not recent and datetime.fromisoformat(committed) < freeze_at:
                continue
            try:
                parent = _git(repo, "rev-parse", f"{sha}^")
            except subprocess.CalledProcessError:
                continue
            files = _git(repo, "show", "--format=", "--name-only", sha).splitlines()
            units.append(
                prospective.TrafficUnit(
                    unit_id=f"{repository}@{sha[:7]}",
                    repository=repository,
                    head_sha=sha,
                    base_sha=parent,
                    subject=subject[:120],
                    stratum=prospective.classify_subject(subject),
                    changed_files=len([f for f in files if f]),
                    pushed_at=committed,
                )
            )
    if recent and target:
        # newest first within each repository, round-robin across repositories in
        # name order: breadth first, and a short history costs only its own share
        per_repo: dict[str, list[prospective.TrafficUnit]] = {}
        for unit in units:
            per_repo.setdefault(unit.repository, []).append(unit)
        for group in per_repo.values():
            group.sort(key=lambda unit: unit.pushed_at, reverse=True)
        allocated: list[prospective.TrafficUnit] = []
        index = 0
        while len(allocated) < target and any(index < len(g) for g in per_repo.values()):
            for name in sorted(per_repo):
                if len(allocated) >= target:
                    break
                group = per_repo[name]
                if index < len(group):
                    allocated.append(group[index])
            index += 1
        units = allocated
    rows = prospective.record_sample(study, units, recorded_at=datetime.now(UTC).isoformat())
    print(
        f"{len(units)} units seen ({'recent' if recent else 'prospective'}), "
        f"{len(rows)} newly recorded -> {study / 'sample.jsonl'}"
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from attest.review.config import load_config
    from attest.review.proposer import ApiProvider
    from attest.review.run import run_review

    study = _study(args)
    preregistration = prospective.load_preregistration(study)
    samples = prospective._read_jsonl(study / prospective.SAMPLE_FILE)
    done = {row["unit_id"] for row in prospective._read_jsonl(study / prospective.TRIALS_FILE)}
    pending = [row for row in samples if row["unit_id"] not in done]
    if args.limit:
        pending = pending[: args.limit]
    # The reservation basis is the owner's ceiling for the item when one is
    # given, and the driver's own cumulative cap enforces it; otherwise it is
    # every pending unit's per-review maximum (D-172).
    reserve = args.reserve or len(pending) * preregistration.per_pr_budget_usd
    preflight = prospective.preflight_prospective(
        study,
        devspend_path=ROOT / "DEVSPEND.md",
        env=os.environ,
        allow_paid_api=args.allow_paid_api,
        reserve_usd=reserve,
    )
    print(json.dumps(preflight.to_json_dict()), flush=True)
    spent = sum(
        float(row.get("spend_usd", 0.0))
        for row in prospective._read_jsonl(study / prospective.TRIALS_FILE)
    )
    skipped: list[str] = []
    for row in pending:
        if spent >= preregistration.cost_cap_usd:
            print(f"cost cap {preregistration.cost_cap_usd} reached; stopping", flush=True)
            break
        repo = CORPORA / _clone_name(str(row["repository"]))
        # A population repository this host cannot clone -- a private one on a
        # runner whose token does not reach it -- is **skipped by name**, not a
        # crash that ends the run. The unit stays in the sample and its absence
        # is reported; it is never quietly dropped from the denominator.
        if not (repo / ".git").is_dir():
            print(json.dumps({"unit_id": str(row["unit_id"]), "skipped": "no clone",
                              "repository": str(row["repository"])}), flush=True)
            skipped.append(str(row["unit_id"]))
            continue
        try:
            _git(repo, "checkout", "-q", "--detach", str(row["head_sha"]))
        except subprocess.CalledProcessError as exc:
            print(json.dumps({"unit_id": str(row["unit_id"]), "skipped": "checkout failed",
                              "detail": str(exc)[:200]}), flush=True)
            skipped.append(str(row["unit_id"]))
            continue
        config = load_config(repo)
        config = config.__class__(
            **{
                **config.__dict__,
                "k_samples": preregistration.k_samples,
                "budget_usd": preregistration.per_pr_budget_usd,
            }
        )
        started = datetime.now(UTC)
        review = run_review(
            repo,
            str(row["base_sha"]),
            config,
            ApiProvider(config.model),
            verify=True,
            verification_timeout_s=900.0,
        )
        # A review refused before it buys anything writes no ledger at all -- a
        # project outside the supported interpreter range, or one with no pytest
        # (D-185, D-186, D-190). That is a recordable outcome, not a crash: the
        # trial is written from the review's own refusal reason with no rows.
        ledger_path = repo / ".attest" / "ledger.jsonl"
        ledger_rows = (
            [
                json.loads(line)
                for line in ledger_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if ledger_path.exists()
            else []
        )
        trial = prospective.trial_from_ledger(
            ledger_rows,
            unit_id=str(row["unit_id"]),
            task_id=review.task_id,
            recorded_at=started.isoformat(),
            would_publish=tuple(
                sorted(f.accepted_receipt.receipt.candidate_id for f in review.published)
            ),
            deferred_reason=review.deferred_reason,
            spend_usd=review.budget.spent_usd,
            elapsed_s=review.elapsed_s,
        )
        prospective.record_trial(study, trial)
        spent += trial.spend_usd
        print(json.dumps(trial.to_json_dict(), ensure_ascii=False), flush=True)
    if skipped:
        print(json.dumps({"skipped_units": skipped}), flush=True)
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    study = _study(args)
    result = prospective.report(study)
    (study / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--study", default="", help="study directory name under benchmarks/studies"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze").set_defaults(func=cmd_freeze)
    select = sub.add_parser("select")
    select.add_argument("--no-fetch", action="store_true")
    select.set_defaults(func=cmd_select)
    select_prs = sub.add_parser("select-prs")
    select_prs.set_defaults(func=cmd_select_prs)
    run = sub.add_parser("run")
    run.add_argument("--allow-paid-api", action="store_true")
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--reserve", type=float, default=0.0,
                     help="the owner's reservation for this item; the study's cost cap enforces it")
    run.set_defaults(func=cmd_run)
    sub.add_parser("report").set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
