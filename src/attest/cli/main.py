"""attest CLI: review, two-stage CI, verify, feedback, and stats commands."""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
from pathlib import Path

from attest.github.client import GitHubClient
from attest.github.context import load_pull_request_context
from attest.review.candidates import CandidateStore
from attest.review.ci import run_ci
from attest.review.config import load_config
from attest.review.gate import GateResult, apply_verification
from attest.review.ledger import Ledger
from attest.review.proposer import ApiProvider, MockProvider, Provider
from attest.review.report import render
from attest.review.run import run_review


def cmd_review(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo)
    overrides = {
        key: value
        for key, value in [
            ("alpha", args.alpha),
            ("budget_usd", args.budget),
            ("model", args.model),
            ("k_samples", args.k),
        ]
        if value is not None
    }
    if overrides:  # replace() re-runs __post_init__ so CLI overrides are validated
        try:
            config = dataclasses.replace(config, **overrides)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    provider: Provider
    if args.mock is not None:
        provider = MockProvider([Path(p).read_text(encoding="utf-8") for p in args.mock])
    else:
        provider = ApiProvider(config.model)
    review = run_review(repo, args.base, config, provider)
    if review.notes == ["no diff to review."]:
        print(review.notes[0])
        return 0
    if review.deferred_reason == "unreachable gate":
        print(f"error: {review.notes[0]}", file=sys.stderr)
        return 2
    print(
        render(
            review.outcome,
            review.alpha,
            review.budget.spent_usd,
            config.budget_usd,
            review.elapsed_s,
            deferred_reason=review.deferred_reason,
            notes=review.notes,
        )
    )
    return 0


def cmd_ci(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        print("error: GITHUB_TOKEN is required for CI review", file=sys.stderr)
        return 2
    try:
        context = load_pull_request_context(Path(args.event_path))
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: malformed GitHub event: {exc}", file=sys.stderr)
        return 2

    config = load_config(repo)
    overrides = {
        key: value
        for key, value in [
            ("alpha", args.alpha),
            ("budget_usd", args.budget),
            ("model", args.model),
            ("k_samples", args.k),
        ]
        if value is not None
    }
    if overrides:
        try:
            config = dataclasses.replace(config, **overrides)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    provider: Provider
    if args.mock is not None:
        try:
            payloads = [Path(path).read_text(encoding="utf-8") for path in args.mock]
        except (OSError, UnicodeError) as exc:
            print(f"error: cannot read mock payload: {exc}", file=sys.stderr)
            return 2
        provider = MockProvider(payloads)
    else:
        provider = ApiProvider(config.model)

    client = GitHubClient(
        token,
        os.environ.get("GITHUB_API_URL", "https://api.github.com"),
    )
    try:
        result = run_ci(
            repo,
            context,
            client,
            config,
            provider,
            verification_timeout_s=args.verification_timeout,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(dataclasses.asdict(result), sort_keys=True))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo)
    ledger = Ledger(repo)
    alpha = ledger.current_alpha(config.alpha)
    store = CandidateStore(repo)
    task_id = args.task_id
    if task_id is None:
        matches = []
        for stored in store.load():
            if stored.finding.finding_id == args.finding_id:
                matches.append(stored)
        task_id = matches[-1].task_id if matches else None
    candidate = store.latest(args.finding_id, task_id) if task_id is not None else None
    if candidate is None:
        print(f"error: unknown finding id {args.finding_id}", file=sys.stderr)
        return 2
    reproduced = args.reproduced
    result = apply_verification(
        GateResult(finding=candidate.finding, wealth=candidate.wealth), alpha, reproduced
    )
    ledger.record_review(
        task_id=candidate.task_id,
        finding_id=args.finding_id,
        channels_bought=[purchase.channel for purchase in result.purchases],
        spend=0.0,
        wealth_final=result.wealth,
        action=f"verified_{result.action}",
    )
    if args.evidence:
        ledger.append(
            {"kind": "evidence", "finding_id": args.finding_id, "evidence": args.evidence}
        )
    status = "reproduced" if reproduced else "not reproduced"
    print(
        f"[{args.finding_id}] {candidate.finding.file}:{candidate.finding.line} {status}: "
        f"wealth {candidate.wealth:.1f} -> {result.wealth:.1f} => {result.action}"
    )
    if result.action == "surface":
        print(f"  {candidate.finding.claim}")
        print(f"  breaks when: {candidate.finding.failure_scenario}")
    return 0


def cmd_feedback(args: argparse.Namespace) -> int:
    ledger = Ledger(Path(args.repo).resolve())
    ledger.record_feedback(args.finding_id, args.label)
    print(f"recorded {args.label} for {args.finding_id}")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo)
    ledger = Ledger(repo)
    entries = ledger.entries()
    runs = [e for e in entries if e.get("kind") == "review_run"]
    reviews = [e for e in entries if e.get("kind") == "review"]
    surfaced = [e for e in reviews if str(e.get("action", "")).endswith("surface")]
    precision, n = ledger.surfaced_precision()
    spend = sum(float(e.get("spend_usd", 0)) for e in runs)
    lat = sorted(float(e["elapsed_s"]) for e in runs if "elapsed_s" in e)
    p50 = lat[len(lat) // 2] if lat else None
    print(f"runs: {len(runs)}; findings evaluated: {len(reviews)}; surfaced: {len(surfaced)}")
    print(f"total spend: ${spend:.4f}; p50 latency: {p50 if p50 is not None else 'n/a'}s")
    print(
        f"surfaced precision: {precision if precision is not None else 'n/a'} "
        f"({n} labeled); alpha now: {ledger.current_alpha(config.alpha)}"
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="attest",
        description="Evidence-first code review: speaks only past the betting gate.",
    )
    parser.add_argument("--repo", default=".", help="repo root (default: cwd)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_review = sub.add_parser("review", help="review the working-tree diff")
    p_review.add_argument("--base", default=None, help="diff base ref (default: HEAD)")
    p_review.add_argument("--alpha", type=float, default=None)
    p_review.add_argument("--budget", type=float, default=None, help="USD cap for this review")
    p_review.add_argument("--model", default=None)
    p_review.add_argument("--k", type=int, default=None, help="proposer samples")
    p_review.add_argument(
        "--mock",
        nargs="+",
        default=None,
        help="offline mode: JSON payload files replayed instead of model calls "
        "(at least one file — never silently falls through to real API calls)",
    )
    p_review.set_defaults(func=cmd_review)

    p_ci = sub.add_parser("ci", help="run a two-stage pull-request review")
    p_ci.add_argument("--event-path", required=True, help="GitHub pull_request event JSON")
    p_ci.add_argument(
        "--verification-timeout",
        type=float,
        default=600.0,
        help="shared verification deadline in seconds (default: 600)",
    )
    p_ci.add_argument("--alpha", type=float, default=None)
    p_ci.add_argument("--budget", type=float, default=None, help="USD cap for this review")
    p_ci.add_argument("--model", default=None)
    p_ci.add_argument("--k", type=int, default=None, help="proposer samples")
    p_ci.add_argument(
        "--mock",
        nargs="+",
        default=None,
        help="offline mode: JSON payload files replayed instead of model calls "
        "(at least one file — never silently falls through to real API calls)",
    )
    p_ci.set_defaults(func=cmd_ci)

    p_verify = sub.add_parser("verify", help="record a reproduction attempt for a finding")
    p_verify.add_argument("finding_id")
    p_verify.add_argument("--task-id", default=None, help="review task containing the finding")
    group = p_verify.add_mutually_exclusive_group(required=True)
    group.add_argument("--reproduced", dest="reproduced", action="store_true")
    group.add_argument("--not-reproduced", dest="reproduced", action="store_false")
    p_verify.add_argument("--evidence", default=None, help="command + output that reproduces it")
    p_verify.set_defaults(func=cmd_verify)

    p_fb = sub.add_parser("feedback", help="label a finding (feeds the precision loop)")
    p_fb.add_argument("finding_id")
    fb_group = p_fb.add_mutually_exclusive_group(required=True)
    fb_group.add_argument("--fix", dest="label", action="store_const", const="fix")
    fb_group.add_argument("--good", dest="label", action="store_const", const="good")
    fb_group.add_argument("--dismiss", dest="label", action="store_const", const="dismiss")
    p_fb.set_defaults(func=cmd_feedback)

    p_stats = sub.add_parser("stats", help="ledger summary")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
