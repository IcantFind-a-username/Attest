"""attest CLI: review (diff -> proposer -> gate -> report), verify, feedback, stats."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
import time
from pathlib import Path

from attest.core.betting import decide
from attest.review.budget import Budget, BudgetExceeded
from attest.review.channels import gate_feasibility, verification_lr
from attest.review.config import load_config
from attest.review.diffs import git_diff
from attest.review.gate import GateOutcome, apply_gate, evaluate_finding
from attest.review.ledger import Ledger
from attest.review.proposer import ApiProvider, MockProvider, Provider, propose
from attest.review.report import render
from attest.review.tier0 import collect_signals, signals_near


def _candidates_path(repo: Path) -> Path:
    return repo / ".attest" / "candidates.jsonl"


def _load_candidates(repo: Path) -> list[dict]:
    path = _candidates_path(repo)
    if not path.is_file():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def cmd_review(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    t0 = time.monotonic()
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

    ledger = Ledger(repo)
    alpha = ledger.current_alpha(config.alpha) if config.auto_tighten_alpha else config.alpha
    alpha, tighten_note = ledger.maybe_tighten_alpha(alpha, config.auto_tighten_alpha)
    notes = [tighten_note] if tighten_note else []

    feas = gate_feasibility(alpha)
    if not feas["reachable_with_verification"]:
        print(
            f"error: gate 1/alpha = {1 / alpha:.0f} exceeds the factory evidence "
            "ceiling even with verification; refusing to run an unreachable gate.",
            file=sys.stderr,
        )
        return 2
    if not feas["reachable_without_verification"]:
        notes.append(
            f"at alpha={alpha} the gate (wealth >= {1 / alpha:.0f}) is reachable only "
            "with reproduction evidence: drawer candidates surface via 'attest verify'."
        )

    diff = git_diff(repo, args.base)
    if not diff.hunks:
        print("no diff to review.")
        return 0

    budget = Budget(limit_usd=config.budget_usd, model=config.model)
    provider: Provider
    if args.mock is not None:
        provider = MockProvider([Path(p).read_text(encoding="utf-8") for p in args.mock])
    else:
        provider = ApiProvider(config.model)

    task_id = (
        time.strftime("%Y%m%d-%H%M%S") + "-" + hashlib.sha256(diff.text.encode()).hexdigest()[:8]
    )

    deferred_reason = None
    outcome = GateOutcome(formal=[], drawer_overflow=[], drawer=[], discarded=[])
    try:
        run = propose(diff, config, budget, provider)
        signals = collect_signals(repo, diff.files, config.tier0_commands)
        results = [
            evaluate_finding(f, alpha, signals_near(signals, f.file, f.line), verification=None)
            for f in run.candidates
        ]
        outcome = apply_gate(results, config.max_findings)

        n = max(1, len(results))
        _candidates_path(repo).parent.mkdir(parents=True, exist_ok=True)
        with _candidates_path(repo).open("a", encoding="utf-8") as fh:
            for r in results:
                f = r.finding
                ledger.record_review(
                    task_id=task_id,
                    finding_id=f.finding_id,
                    channels_bought=[p.channel for p in r.purchases],
                    spend=budget.spent_usd / n,
                    wealth_final=r.wealth,
                    # overflow findings DID pass the gate and are spoken in the
                    # drawer section; the action must keep counting as surfaced
                    action=r.action if r not in outcome.drawer_overflow else "overflow_surface",
                )
                fh.write(
                    json.dumps(
                        {
                            "task_id": task_id,
                            "finding_id": f.finding_id,
                            "file": f.file,
                            "line": f.line,
                            "claim": f.claim,
                            "failure_scenario": f.failure_scenario,
                            "falsification_plan": f.falsification_plan,
                            "votes": f.votes,
                            "wealth": r.wealth,
                            "action": r.action,
                            "alpha": alpha,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
        for err in run.sample_errors:
            notes.append(f"sample error: {err}")
        if run.rejected:
            notes.append(
                f"{len(run.rejected)} finding(s) voided (schema/anchor): "
                + "; ".join(run.rejected[:3])
            )
    except BudgetExceeded as exc:
        deferred_reason = f"budget: {exc.reason}"
        ledger.append({"kind": "defer", "task_id": task_id, "reason": deferred_reason})

    elapsed = time.monotonic() - t0
    ledger.append(
        {
            "kind": "review_run",
            "task_id": task_id,
            "elapsed_s": round(elapsed, 2),
            "spend_usd": round(budget.spent_usd, 6),
            "model": config.model,
            "alpha": alpha,
            "files": len(diff.files),
        }
    )
    print(
        render(
            outcome,
            alpha,
            budget.spent_usd,
            config.budget_usd,
            elapsed,
            deferred_reason=deferred_reason,
            notes=notes,
        )
    )
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo).resolve()
    config = load_config(repo)
    ledger = Ledger(repo)
    alpha = ledger.current_alpha(config.alpha)
    matches = [c for c in _load_candidates(repo) if c["finding_id"] == args.finding_id]
    if not matches:
        print(f"error: unknown finding id {args.finding_id}", file=sys.stderr)
        return 2
    cand = matches[-1]
    reproduced = args.reproduced
    wealth = float(cand["wealth"]) * verification_lr(reproduced)
    decision = decide(wealth, alpha)
    action = {1: "surface", 0: "discard", None: "drawer"}[decision]
    ledger.record_review(
        task_id=cand["task_id"],
        finding_id=args.finding_id,
        channels_bought=["V"],
        spend=0.0,
        wealth_final=wealth,
        action=f"verified_{action}",
    )
    if args.evidence:
        ledger.append(
            {"kind": "evidence", "finding_id": args.finding_id, "evidence": args.evidence}
        )
    status = "reproduced" if reproduced else "not reproduced"
    print(
        f"[{args.finding_id}] {cand['file']}:{cand['line']} {status}: "
        f"wealth {cand['wealth']:.1f} -> {wealth:.1f} => {action}"
    )
    if action == "surface":
        print(f"  {cand['claim']}")
        print(f"  breaks when: {cand['failure_scenario']}")
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

    p_verify = sub.add_parser("verify", help="record a reproduction attempt for a finding")
    p_verify.add_argument("finding_id")
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
