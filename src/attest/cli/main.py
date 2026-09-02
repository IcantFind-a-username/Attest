"""attest CLI: review, two-stage CI, verify, feedback, and stats commands."""

from __future__ import annotations

import argparse
import dataclasses
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from attest.github.client import GitHubClient
from attest.github.context import load_pull_request_context
from attest.review.candidates import CandidateStore
from attest.review.ci import run_ci
from attest.review.config import ReviewConfig, load_config
from attest.review.ledger import Ledger
from attest.review.proposer import ApiProvider, MockProvider, Provider
from attest.review.report import render
from attest.review.run import run_review
from attest.review.status import categorise_failure


def _positive_finite(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError("must be a finite number greater than zero")
    return parsed


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
    review = run_review(
        repo,
        args.base,
        config,
        provider,
        verify=True,
        verification_timeout_s=args.verification_timeout,
    )
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
            certified=review.published,
            status=review.status,
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

    # CI policy is base-owned: run_ci resolves the merge-base and reads the
    # committed .attest.toml there. The head checkout's file is never loaded.
    # Only the protected Action inputs are applied on top, validated here.
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
    try:
        protected = ReviewConfig(**overrides)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    # the model is a protected field: the provider is built before the base
    # policy is read, so the Action input (or factory default) always wins
    overrides["model"] = protected.model

    provider: Provider
    if args.mock is not None:
        try:
            payloads = [Path(path).read_text(encoding="utf-8") for path in args.mock]
        except (OSError, UnicodeError) as exc:
            print(f"error: cannot read mock payload: {exc}", file=sys.stderr)
            return 2
        provider = MockProvider(payloads)
    else:
        provider = ApiProvider(protected.model)

    client = GitHubClient(
        token,
        os.environ.get("GITHUB_API_URL", "https://api.github.com"),
    )
    try:
        result = run_ci(
            repo,
            context,
            client,
            None,
            provider,
            verification_timeout_s=args.verification_timeout,
            config_overrides=overrides,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(dataclasses.asdict(result), sort_keys=True))
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    if args.bundle is not None:
        return verify_bundle_offline(repo, Path(args.bundle), args.key, args.require_seal)
    if args.finding_id is None or args.reproduced is None:
        print(
            "error: attest verify needs a finding id with --reproduced/--not-reproduced, "
            "or --bundle DIR",
            file=sys.stderr,
        )
        return 2
    ledger = Ledger(repo)
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
    # INV-EVIDENCE-001: a human note lives in its own namespace. It buys no
    # channel, crosses no threshold, and never enters publication or precision.
    ledger.record_self_report(
        task_id=candidate.task_id,
        finding_id=args.finding_id,
        reproduced=args.reproduced,
        evidence=args.evidence,
    )
    status = "reproduced" if args.reproduced else "not reproduced"
    print(
        f"[{args.finding_id}] {candidate.finding.file}:{candidate.finding.line} "
        f"self-report recorded: {status}."
    )
    print(
        "  a self-report is a note for humans: it certifies nothing, publishes nothing, "
        "and is excluded from precision; automated certification needs a differential "
        "receipt from `attest ci`."
    )
    return 0


def verify_bundle_offline(repo: Path, bundle: Path, key_path: str | None, require: bool) -> int:
    """V-03: recompute every digest and the controller seal from the bundle
    alone; no repository access, no model, no execution."""
    from attest.certification.types import AcceptedReceipt
    from attest.execution.provenance import KEY_RELATIVE, load_key
    from attest.review.evidence import verify_bundle

    key: bytes | None = None
    candidate = Path(key_path) if key_path else repo / KEY_RELATIVE
    if candidate.is_file():
        try:
            key = load_key(candidate)
        except (OSError, ValueError) as exc:
            print(f"error: controller key unusable: {exc}", file=sys.stderr)
            return 2
    verdict = verify_bundle(bundle, key=key, require_seal=require)
    if isinstance(verdict, AcceptedReceipt):
        receipt = verdict.receipt
        sealed = "seal verified" if key is not None else "seal not checked (no key)"
        print(
            f"accepted: receipt {receipt.provenance_digest} for {receipt.candidate_id} "
            f"({receipt.executor_profile}); {sealed}"
        )
        return 0
    reasons = getattr(verdict, "reasons", None) or getattr(verdict, "codes", None) or ()
    print("rejected: " + "; ".join(str(getattr(reason, "value", reason)) for reason in reasons))
    return 1


def cmd_feedback(args: argparse.Namespace) -> int:
    ledger = Ledger(Path(args.repo).resolve())
    ledger.record_feedback(args.finding_id, args.label)
    print(f"recorded {args.label} for {args.finding_id}")
    return 0


def render_drawer(entries: list[dict[str, Any]], store: CandidateStore, limit: int) -> str:
    """Owner item 9 (2026-09-03): the candidates that entered the drawer but
    earned no receipt, newest task first, with their votes and why each
    reproduction failed. Read from the local ledger only; never a PR comment
    and never speech."""
    certified = {
        str(e.get("finding_id"))
        for e in entries
        if e.get("kind") == "certification" and e.get("outcome") == "accepted"
    }
    reasons: dict[str, str] = {}
    for e in entries:
        if e.get("kind") == "verification" and e.get("finding_id"):
            reasons[str(e["finding_id"])] = str(e.get("reason") or "")
    labels: dict[str, str] = {}
    for e in entries:
        if e.get("kind") == "feedback" and e.get("finding_id"):
            labels[str(e["finding_id"])] = str(e.get("feedback") or e.get("label") or "")
    rows = []
    seen: set[str] = set()
    for stored in reversed(store.load()):
        finding_id = stored.finding.finding_id
        if stored.action == "discard" or finding_id in certified or finding_id in seen:
            continue
        seen.add(finding_id)
        reason = reasons.get(finding_id, "")
        category = categorise_failure(reason) if reason else "not attempted"
        rows.append(
            f"  - [{finding_id}] {stored.finding.file}:{stored.finding.line} "
            f"votes {stored.finding.votes}; reproduction: {category}"
            + (f" ({reason[:120]})" if reason else "")
            + (f"; label: {labels[finding_id]}" if finding_id in labels else "")
            + f"\n      {stored.finding.claim}"
        )
        if len(rows) >= limit:
            break
    if not rows:
        return "drawer: empty (no uncertified candidates on record)"
    return (
        f"drawer ({len(rows)} uncertified candidate(s); label one with "
        "`attest feedback <id> --fix|--good|--dismiss`):\n" + "\n".join(rows)
    )


def cmd_stats(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo)
    ledger = Ledger(repo)
    entries = ledger.entries_strict()
    if getattr(args, "drawer", False):
        print(render_drawer(entries, CandidateStore(repo), args.limit))
        return 0
    final_runs = [e for e in entries if e.get("kind") == "ci_final"]
    final_tasks = {str(e.get("task_id", "")) for e in final_runs}
    runs = [
        e
        for e in entries
        if e.get("kind") == "review_run" and str(e.get("task_id", "")) not in final_tasks
    ] + final_runs
    reviews = [e for e in entries if e.get("kind") == "review"]
    surfaced = ledger.surfaced_finding_ids(entries)
    precision, n = ledger.surfaced_precision(entries=entries, surfaced_ids=surfaced)
    surfaced_tasks = {
        str(entry.get("task_id", ""))
        for entry in reviews
        if str(entry.get("finding_id", "")) in surfaced
    }
    run_tasks = [str(entry.get("task_id", "")) for entry in runs]
    abstentions = sum(task_id not in surfaced_tasks for task_id in run_tasks)
    abstention_rate = abstentions / len(run_tasks) if run_tasks else None
    spend = sum(float(e.get("spend_usd", 0)) for e in runs)
    lat = sorted(float(e["elapsed_s"]) for e in runs if "elapsed_s" in e)
    p50 = lat[len(lat) // 2] if lat else None
    print(f"runs: {len(runs)}; findings evaluated: {len(reviews)}; surfaced: {len(surfaced)}")
    print(f"self-reports: {len(ledger.self_reports())} (manual; excluded from precision)")
    print(f"total spend: ${spend:.4f}; p50 latency: {p50 if p50 is not None else 'n/a'}s")
    if precision is None:
        print("surfaced precision: undefined (no labeled surfaced outcomes)")
    else:
        print(f"surfaced precision: {precision} ({n} labeled)")
    if abstention_rate is None:
        print("abstention rate: undefined (no review runs)")
    else:
        anomaly = " — ANOMALY (> 0.5)" if abstention_rate > 0.5 else ""
        print(
            f"abstention rate: {abstention_rate:.6f} ({abstentions}/{len(run_tasks)} runs){anomaly}"
        )
    print("silence precision: undefined (no labeled silent outcomes)")
    print(f"alpha now: {ledger.current_alpha(config.alpha)}")
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
        "--verification-timeout",
        type=float,
        default=600.0,
        help="shared time limit for the differential reproduction stage, in seconds",
    )
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
        type=_positive_finite,
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

    p_verify = sub.add_parser(
        "verify",
        help="record a self-reported reproduction note for a finding (never a certificate)",
    )
    p_verify.add_argument("finding_id", nargs="?", default=None)
    p_verify.add_argument("--task-id", default=None, help="review task containing the finding")
    group = p_verify.add_mutually_exclusive_group(required=False)
    group.add_argument("--reproduced", dest="reproduced", action="store_true", default=None)
    group.add_argument("--not-reproduced", dest="reproduced", action="store_false", default=None)
    p_verify.add_argument(
        "--bundle",
        default=None,
        help="verify an evidence bundle offline (digests, bindings, controller seal)",
    )
    p_verify.add_argument(
        "--key", default=None, help="controller key file (default: .attest/controller.key)"
    )
    p_verify.add_argument(
        "--require-seal", action="store_true", help="reject a bundle whose seal cannot be verified"
    )
    p_verify.add_argument("--evidence", default=None, help="command + output that reproduces it")
    p_verify.set_defaults(func=cmd_verify)

    p_fb = sub.add_parser("feedback", help="label a finding (feeds the precision loop)")
    p_fb.add_argument("finding_id")
    fb_group = p_fb.add_mutually_exclusive_group(required=True)
    fb_group.add_argument(
        "--fix",
        dest="label",
        action="store_const",
        const="fix",
        help="finding was correct; the fix was applied (true label)",
    )
    fb_group.add_argument(
        "--good",
        dest="label",
        action="store_const",
        const="good",
        help="finding was correct (true label)",
    )
    fb_group.add_argument(
        "--wrong",
        dest="label",
        action="store_const",
        const="wrong",
        help="finding was incorrect: a genuine false positive (false label, "
        "counts against precision)",
    )
    fb_group.add_argument(
        "--wontfix",
        dest="label",
        action="store_const",
        const="wontfix",
        help="finding was correct but intentionally not acted on -- out of "
        "scope, known, or deferred (true label; the tool was right)",
    )
    fb_group.add_argument(
        "--dismiss",
        dest="label",
        action="store_const",
        const="dismiss",
        help="legacy label, ambiguous: prefer --wrong (false positive) or "
        "--wontfix (correct but not acted on). Excluded from precision.",
    )
    p_fb.set_defaults(func=cmd_feedback)

    p_stats = sub.add_parser("stats", help="ledger summary")
    p_stats.add_argument(
        "--drawer",
        action="store_true",
        help="list uncertified drawer candidates with votes and reproduction failure reasons",
    )
    p_stats.add_argument("--limit", type=int, default=20, help="drawer rows to show")
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
