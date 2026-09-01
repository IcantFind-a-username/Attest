#!/usr/bin/env python3
"""Run an unpriced F-history counterfactual over receipt-validated pairs."""

from __future__ import annotations

import argparse
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from attest.benchmark.artifacts import sha256_bytes, write_canonical_json
from attest.benchmark.corpus import load_validation_receipt
from attest.benchmark.schema import BenchmarkCase, load_manifest, manifest_binding_bytes
from attest.review.config import ReviewConfig
from attest.review.ledger import Ledger
from attest.review.proposer import ApiProvider
from attest.review.run import run_review

CAPS = (1.25, 1.5, 2.0, 3.0)
SCHEMA_VERSION = "attest.history-counterfactual.v1"
_TOTAL_RE = re.compile(r"\*\*Total API spend: \$([0-9]+(?:\.[0-9]+)?) of \$10\.00\.\*\*")


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _spend_total(path: Path) -> float:
    match = _TOTAL_RE.search(path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError("DEVSPEND total is missing")
    return float(match.group(1))


def _factor(result: Any, channel: str) -> float:
    return next((float(row.lr) for row in result.purchases if row.channel == channel), 1.0)


def _counterfactual_row(
    case: BenchmarkCase,
    result: Any,
    history_row: dict[str, Any],
    cap: float,
) -> dict[str, object] | None:
    before = float(result.wealth)
    after = before * cap if history_row["triggered"] else before
    threshold = 1.0 / float(result.alpha) if hasattr(result, "alpha") else 10.0
    if not before < threshold <= after:
        return None
    finding = result.finding
    return {
        "pair_id": case.pair_id,
        "case_id": case.case_id,
        "role": case.role,
        "finding_id": finding.finding_id,
        "claim": finding.claim,
        "anchor": {"file": finding.file, "line": finding.line},
        "failure_scenario": finding.failure_scenario,
        "wealth": {
            "S": _factor(result, "S"),
            "T": _factor(result, "T"),
            "F": cap,
            "before": before,
            "after": after,
            "threshold": threshold,
        },
        "history_commit": history_row["commit_sha"],
        "history_message": history_row["commit_message"],
    }


def _case_source(root: Path, case: BenchmarkCase) -> Path:
    role = "replay" if case.role == "historical_bug_replay" else "control"
    source = root / case.source_id / case.pair_id / role
    if not source.is_dir():
        raise ValueError(f"missing prepared checkout for {case.case_id}")
    return source


def _case_result(
    case: BenchmarkCase,
    source: Path,
    provider: ApiProvider,
    budget_usd: float,
) -> tuple[dict[str, object], list[tuple[Any, dict[str, Any]]], float]:
    with tempfile.TemporaryDirectory(prefix="attest-history-cf-", dir="/private/tmp") as tmp:
        repo = Path(tmp) / "repo"
        subprocess.run(
            ["git", "clone", "--quiet", "--shared", str(source), str(repo)],
            check=True,
            capture_output=True,
        )
        head = case.buggy_commit if case.role == "historical_bug_replay" else case.fixed_commit
        base = case.fixed_commit if case.role == "historical_bug_replay" else case.buggy_commit
        if _git(repo, "rev-parse", "HEAD") != head:
            raise ValueError(f"prepared checkout HEAD mismatch for {case.case_id}")
        run = run_review(
            repo,
            base,
            ReviewConfig(
                budget_usd=budget_usd,
                auto_tighten_alpha=False,
                tier0_commands=["ruff"],
            ),
            provider,
            task_id=f"history-counterfactual-{case.case_id}",
        )
        rows = {
            str(row["finding_id"]): row
            for row in Ledger(repo).entries()
            if row.get("kind") == "history_signal"
        }
        candidates = [(result, rows[result.finding.finding_id]) for result in run.results]
        record: dict[str, object] = {
            "pair_id": case.pair_id,
            "case_id": case.case_id,
            "role": case.role,
            "head_sha": head,
            "base_sha": base,
            "candidate_count": len(run.results),
            "spend_usd": run.budget.spent_usd,
            "deferred_reason": run.deferred_reason,
            "candidates": [
                {
                    "finding_id": result.finding.finding_id,
                    "claim": result.finding.claim,
                    "anchor": {"file": result.finding.file, "line": result.finding.line},
                    "failure_scenario": result.finding.failure_scenario,
                    "S": _factor(result, "S"),
                    "T": _factor(result, "T"),
                    "wealth": result.wealth,
                    "F_triggered": row["triggered"],
                    "history_commit": row["commit_sha"],
                    "history_message": row["commit_message"],
                }
                for result, row in candidates
            ],
        }
        return record, candidates, run.budget.spent_usd


def run(args: argparse.Namespace) -> dict[str, object]:
    if not args.allow_paid_api:
        raise ValueError("--allow-paid-api is required")
    if args.output.exists():
        raise ValueError("output already exists")
    manifest = load_manifest(args.manifest)
    receipt = load_validation_receipt(args.receipt, args.manifest, args.validation_results)
    cases = sorted(
        (case for case in manifest.cases if case.pair_id in receipt.validated_pair_ids),
        key=lambda case: (case.pair_id, case.role),
    )
    if len(receipt.validated_pair_ids) != 9 or len(cases) != 18:
        raise ValueError("counterfactual requires exactly nine validated pairs and both roles")
    reserved = len(cases) * args.budget_usd
    prior_spend = _spend_total(args.devspend)
    if reserved > (10.0 - prior_spend) / 2.0:
        raise ValueError("predeclared spend exceeds half the remaining DEVSPEND allowance")

    provider = ApiProvider(ReviewConfig().model)
    case_records: list[dict[str, object]] = []
    observed: list[tuple[BenchmarkCase, Any, dict[str, Any]]] = []
    spend = 0.0
    for case in cases:
        record, candidates, case_spend = _case_result(
            case,
            _case_source(args.corpus_root, case),
            provider,
            args.budget_usd,
        )
        case_records.append(record)
        observed.extend((case, result, row) for result, row in candidates)
        spend += case_spend

    triggers = sum(bool(row["triggered"]) for _case, _result, row in observed)
    counterfactuals: dict[str, object] = {}
    for cap in CAPS:
        crossings = [
            row
            for case, result, history in observed
            if (row := _counterfactual_row(case, result, history, cap)) is not None
        ]
        counterfactuals[str(cap)] = {
            "historical_bug_replay": [
                row for row in crossings if row["role"] == "historical_bug_replay"
            ],
            "developer_fix_control": [
                row for row in crossings if row["role"] == "developer_fix_control"
            ],
        }
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "code_sha": _git(Path.cwd(), "rev-parse", "HEAD"),
        "manifest_sha256": sha256_bytes(manifest_binding_bytes(manifest)),
        "receipt_sha256": sha256_bytes(args.receipt.read_bytes()),
        "validated_pair_count": len(receipt.validated_pair_ids),
        "case_count": len(cases),
        "budget_usd_per_case": args.budget_usd,
        "reserved_usd": reserved,
        "spend_usd": spend,
        "accuracy_status": "not_estimated_historical_integrity_only",
        "candidate_count": len(observed),
        "F_trigger_count": triggers,
        "F_trigger_rate": None if not observed else triggers / len(observed),
        "cases": case_records,
        "counterfactuals": counterfactuals,
        "limitations": [
            "F is unpriced and this artifact does not alter product wealth or publication.",
            "The V1 receipt is historical-integrity-only; accuracy, precision, and recall "
            "are not estimated.",
            "Model samples are one paid observation under the recorded configuration.",
        ],
    }
    write_canonical_json(args.output, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--validation-results", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--devspend", type=Path, required=True)
    parser.add_argument("--budget-usd", type=float, default=0.15)
    parser.add_argument("--allow-paid-api", action="store_true")
    args = parser.parse_args()
    payload = run(args)
    print(
        f"cases={payload['case_count']} candidates={payload['candidate_count']} "
        f"F={payload['F_trigger_count']} spend_usd={payload['spend_usd']:.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
