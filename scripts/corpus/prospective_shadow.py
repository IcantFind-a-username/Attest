"""E-04 prospective shadow driver (mainline §2 step 15).

  freeze    write the study's freeze digest (protocol + preregistration + authorization)
  select    record every commit pushed to a population repository after the freeze, with
            its stratum and the silent-audit draw, BEFORE any outcome (sample.jsonl)
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
STUDY = ROOT / "benchmarks" / "studies" / "e04-prospective-v1"
CORPORA = ROOT / ".attest" / "corpora"

from attest.benchmark import prospective  # noqa: E402


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def cmd_freeze(_args: argparse.Namespace) -> int:
    print(prospective.freeze(STUDY))
    return 0


def _clone_name(repository: str) -> str:
    return repository.split("/")[-1].lower()


def cmd_select(args: argparse.Namespace) -> int:
    preregistration = prospective.load_preregistration(STUDY)
    freeze_at = datetime.fromisoformat(preregistration.freeze_at)
    units: list[prospective.TrafficUnit] = []
    for repository in preregistration.population:
        repo = CORPORA / _clone_name(repository)
        if not repo.is_dir():
            print(f"skip {repository}: no clone at {repo}", file=sys.stderr)
            continue
        if not args.no_fetch:
            subprocess.run(["git", "-C", str(repo), "fetch", "--all", "-q"], check=False)
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
            if datetime.fromisoformat(committed) < freeze_at:
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
    rows = prospective.record_sample(STUDY, units, recorded_at=datetime.now(UTC).isoformat())
    print(
        f"{len(units)} prospective units seen, {len(rows)} newly recorded -> "
        f"{STUDY / 'sample.jsonl'}"
    )
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from attest.review.config import load_config
    from attest.review.proposer import ApiProvider
    from attest.review.run import run_review

    preregistration = prospective.load_preregistration(STUDY)
    samples = prospective._read_jsonl(STUDY / prospective.SAMPLE_FILE)
    done = {row["unit_id"] for row in prospective._read_jsonl(STUDY / prospective.TRIALS_FILE)}
    pending = [row for row in samples if row["unit_id"] not in done]
    if args.limit:
        pending = pending[: args.limit]
    reserve = len(pending) * preregistration.per_pr_budget_usd
    preflight = prospective.preflight_prospective(
        STUDY,
        devspend_path=ROOT / "DEVSPEND.md",
        env=os.environ,
        allow_paid_api=args.allow_paid_api,
        reserve_usd=reserve,
    )
    print(json.dumps(preflight.to_json_dict()), flush=True)
    spent = sum(
        float(row.get("spend_usd", 0.0))
        for row in prospective._read_jsonl(STUDY / prospective.TRIALS_FILE)
    )
    for row in pending:
        if spent >= preregistration.cost_cap_usd:
            print(f"cost cap {preregistration.cost_cap_usd} reached; stopping", flush=True)
            break
        repo = CORPORA / _clone_name(str(row["repository"]))
        _git(repo, "checkout", "-q", "--detach", str(row["head_sha"]))
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
        ledger_rows = [
            json.loads(line)
            for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
        ]
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
        prospective.record_trial(STUDY, trial)
        spent += trial.spend_usd
        print(json.dumps(trial.to_json_dict(), ensure_ascii=False), flush=True)
    return 0


def cmd_report(_args: argparse.Namespace) -> int:
    result = prospective.report(STUDY)
    (STUDY / "report.json").write_text(json.dumps(result, indent=2, ensure_ascii=False))
    for key, value in result.items():
        print(f"{key}: {value}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("freeze").set_defaults(func=cmd_freeze)
    select = sub.add_parser("select")
    select.add_argument("--no-fetch", action="store_true")
    select.set_defaults(func=cmd_select)
    run = sub.add_parser("run")
    run.add_argument("--allow-paid-api", action="store_true")
    run.add_argument("--limit", type=int, default=0)
    run.set_defaults(func=cmd_run)
    sub.add_parser("report").set_defaults(func=cmd_report)
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
