#!/usr/bin/env python3
"""Offline command-line adapter for importing and validating benchmark corpora."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from attest.benchmark.api import (
    ProjectEvaluationRequest,
    ProjectEvaluationResult,
    evaluate_projects,
    manifest_project_truth,
)
from attest.benchmark.artifacts import ArtifactStore, process_secrets, write_canonical_json
from attest.benchmark.baselines import ComparisonPlan, compare_arms
from attest.benchmark.corpus import (
    MAX_VALIDATION_DOCUMENT_BYTES,
    IsolationAdapter,
    SubprocessCorpusRunner,
    ValidationAuthorityCheck,
    ValidationReceipt,
    import_bugsinpy,
    load_validation_receipt,
    load_validation_receipt_v2,
    require_validated_pair,
    validate_corpus,
    validation_receipt_binding_bytes,
)
from attest.benchmark.experiments import (
    DEFAULT_ALARM_POLL_EVERY,
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_CANARY_ACCURACY,
    DEFAULT_CANARY_SHIFT_FRACTION,
    DEFAULT_GAMMAS,
    DEFAULT_NULL_ASSUMPTIONS,
    DEFAULT_NULL_GAMMAS,
    DEFAULT_NULL_GRID_ALPHAS,
    DEFAULT_NULL_GRID_LENGTHS,
    DEFAULT_NULL_GRID_PANEL_GAMMAS,
    DEFAULT_NULL_GRID_SEEDS,
    DEFAULT_POLICY_SEEDS,
    DEFAULT_POLICY_TASKS,
    DEFAULT_RECALL_TARGETS,
    DEFAULT_SEEDS,
    DEFAULT_TWO_LEDGER_ALPHAS,
    DEFAULT_TWO_LEDGER_ASSUMPTIONS,
    DEFAULT_VILLE_ALPHAS,
    FACTORY_ALPHAS,
    NULL_GRID_ACCURACIES,
    NullAssumptions,
    TwoLedgerAssumptions,
    run_e_validity_experiment,
    run_monitor_policy_experiment,
    run_null_grid,
    run_rho_ablation,
    run_two_ledger_experiment,
)
from attest.benchmark.live import (
    REASON_PAID_API_NOT_ALLOWED,
    LiveCase,
    LivePreflightError,
    preflight_live,
    reserved_case_budget_usd,
    run_live_local,
)
from attest.benchmark.measurement import ARM_ATTEST_PRODUCT, TaskStatus
from attest.benchmark.report import (
    LIVE_MODE,
    REPLAY_MODE,
    ReportAbstention,
    ReportExclusion,
    build_comparison_report,
    build_report,
    write_comparison_report,
    write_report,
    write_stability_report,
)
from attest.benchmark.runner import (
    Cassette,
    ReplayProvider,
    load_cassette,
    replay_probe_generation,
)
from attest.benchmark.schema import BenchmarkCase, BenchmarkManifest, load_manifest
from attest.benchmark.stability import run_stability_study
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits
from attest.review.proposer import ApiProvider


def _add_validation_verification_arguments(
    command: argparse.ArgumentParser, *, required: bool = False
) -> None:
    command.add_argument(
        "--validation-artifacts",
        type=Path,
        required=required,
        help="content-addressed artifacts for pure V2 verification; execution "
        "commands reject this option before loading project code",
    )
    command.add_argument(
        "--validation-provenance-key-id",
        required=required,
        help="authorized local provenance key id for pure V2 verification",
    )
    command.add_argument(
        "--validation-provenance-key-file",
        type=Path,
        required=required,
        help="raw local provenance key bytes for pure V2 verification; never "
        "decoded, stripped, or printed",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    importer = commands.add_parser("import-bugsinpy")
    importer.add_argument("--source", type=Path, required=True)
    importer.add_argument("--project-cache", type=Path)
    importer.add_argument("--output", type=Path, required=True)
    importer.add_argument("--limit", type=int, required=True)
    importer.add_argument("--seed", type=int, required=True)

    validator = commands.add_parser(
        "validate",
        help="produce unsigned, hash-bound validation evidence without issuing authority",
        description="Run local corpus diagnostics and produce unsigned, hash-bound "
        "evidence. This command never issues a receipt or current scoring authority.",
    )
    validator.add_argument("--manifest", type=Path, required=True)
    validator.add_argument("--offline", action="store_true", required=True)
    validator.add_argument("--root", type=Path)
    validator.add_argument("--isolation-wrapper", type=Path)
    validator.add_argument("--isolation-arg", action="append", default=[])
    validator.add_argument(
        "--python",
        action="append",
        default=[],
        metavar="SOURCE_ID=INTERPRETER",
        help="caller-prepared Python interpreter for one opaque source id",
    )
    validator.add_argument(
        "--tool",
        action="append",
        default=[],
        metavar="SOURCE_ID:TOOL=EXECUTABLE",
        help="explicit executable for a non-Python typed tool",
    )
    validator.add_argument(
        "--receipt-out",
        type=Path,
        help="legacy compatibility path only; validate never writes a receipt or "
        "current scoring authority",
    )
    validator.add_argument(
        "--validation-results-out",
        type=Path,
        help="legacy compatibility path only; validate reports unsigned evidence "
        "without writing an authority bundle",
    )
    validator.add_argument(
        "--validation-artifacts",
        type=Path,
        help="V2 authority input is refused by validate before project execution; "
        "use verify-validation to inspect an existing V2 bundle",
    )
    validator.add_argument(
        "--validation-provenance-key-id",
        help="V2 provenance input is refused by validate; only verify-validation "
        "accepts it",
    )
    validator.add_argument(
        "--validation-provenance-key-file",
        type=Path,
        help="V2 secret input is refused by validate before it is read; only "
        "verify-validation accepts it",
    )
    validator.add_argument("--timeout", type=float, default=60)
    validator.add_argument("--max-output-bytes", type=int, default=65_536)

    verifier = commands.add_parser(
        "verify-validation",
        help="verify an existing V2 validation bundle without executing project code",
    )
    verifier.add_argument("--manifest", type=Path, required=True)
    verifier.add_argument("--validation-receipt", type=Path, required=True)
    verifier.add_argument("--validation-results", type=Path, required=True)
    _add_validation_verification_arguments(verifier, required=True)

    experiment = commands.add_parser(
        "experiment-rho",
        help="offline correlated-panel ablation: naive independent votes vs the "
        "production correlation discount (experiment only, changes no constant)",
    )
    experiment.add_argument("--gammas", type=float, nargs="+", default=list(DEFAULT_GAMMAS))
    experiment.add_argument("--alphas", type=float, nargs="+", default=list(FACTORY_ALPHAS))
    experiment.add_argument("--k", type=int, default=5)
    experiment.add_argument("--tasks", type=int, default=2000)
    experiment.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    experiment.add_argument("--theta-prior", type=float, default=0.5)
    experiment.add_argument(
        "--judge-accuracy",
        type=float,
        help="per-vote accuracy; defaults to the accuracy at which LR1 is exactly "
        "the likelihood ratio of one positive vote",
    )
    experiment.add_argument("--output", type=Path, required=True)

    replay = commands.add_parser(
        "replay",
        help="offline replay of the real product review path over a preregistered "
        "corpus: model responses come from recorded cassettes and GitHub is a "
        "loopback endpoint, so no network or credential is ever used",
    )
    replay.add_argument("--manifest", type=Path, required=True)
    replay.add_argument("--cassette-root", type=Path, required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument(
        "--root",
        type=Path,
        help="caller-prepared checkout root; without it every case is excluded",
    )
    replay.add_argument("--workspace", type=Path)
    replay.add_argument(
        "--validation-receipt",
        type=Path,
        help="historical V1 receipt for exclusion inspection only; execution "
        "reports always withhold accuracy, and V2 is verify-validation only",
    )
    replay.add_argument(
        "--validation-results",
        type=Path,
        help="the exact validation-results artifact the receipt was issued over",
    )
    _add_validation_verification_arguments(replay)
    replay.add_argument("--alpha", type=float, default=0.1)
    replay.add_argument("--budget-usd", type=float, default=0.25)
    replay.add_argument("--k-samples", type=int, default=5)
    replay.add_argument("--max-findings", type=int, default=3)
    replay.add_argument("--tier0-command", action="append", default=[])
    replay.add_argument(
        "--auto-tighten-alpha",
        action="store_true",
        help="allow the ledger alpha auto-tighten rule during replay (off by "
        "default so replayed runs stay comparable)",
    )
    replay.add_argument("--repeats", type=int, default=3)
    replay.add_argument("--line-slack", type=int, default=0)
    replay.add_argument("--deadline", type=float, default=60.0)
    replay.add_argument("--wall-timeout", type=float, default=60.0)
    replay.add_argument("--verification-timeout", type=float, default=600.0)

    stability = commands.add_parser(
        "stability",
        help="offline ten-repeat stability study of ONE preregistered case: every "
        "run replays the same recorded cassette through the real product path, "
        "every metric is operational variability (never accuracy), and no "
        "provider client or credential is ever used",
    )
    stability.add_argument("--manifest", type=Path, required=True)
    stability.add_argument("--case", required=True)
    stability.add_argument("--cassette-root", type=Path, required=True)
    stability.add_argument("--output", type=Path, required=True)
    stability.add_argument(
        "--root",
        type=Path,
        help="caller-prepared checkout root; without it the study is not executed",
    )
    stability.add_argument("--workspace", type=Path)
    stability.add_argument(
        "--state-dir",
        type=Path,
        help="resumable per-repeat state (default: OUTPUT/state); a completed "
        "repeat found here is loaded, never re-executed",
    )
    _add_review_arguments(stability)

    compare = commands.add_parser(
        "compare",
        help="offline three-arm comparison over identical blinded diff bytes: the "
        "real product path, one bare schema-constrained model call, and a local "
        "deterministic static analyzer (never described as an AI reviewer); "
        "model responses come from recorded cassettes only; Phase0 execution "
        "reports withhold accuracy and accept V1 receipts only for historical "
        "exclusion inspection",
    )
    compare.add_argument("--manifest", type=Path, required=True)
    compare.add_argument("--cassette-root", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument(
        "--root",
        type=Path,
        help="caller-prepared checkout root; without it every case is excluded",
    )
    compare.add_argument("--workspace", type=Path)
    compare.add_argument(
        "--comparison-authority-root",
        type=Path,
        help="external owner-controlled directory for write-once launch/final "
        "receipts; required when any case executes and must be outside OUTPUT, "
        "the checkout, and worktrees",
    )
    compare.add_argument(
        "--comparison-run-id",
        help="owner-provided unique SHA-256 run identity; required for a non-empty "
        "comparison and reused unchanged for crash resume",
    )
    compare.add_argument(
        "--validation-receipt",
        type=Path,
        help="historical V1 receipt for exclusion inspection only; execution "
        "reports always withhold accuracy, and V2 is verify-validation only",
    )
    compare.add_argument(
        "--validation-results",
        type=Path,
        help="the exact validation-results artifact the receipt was issued over",
    )
    _add_validation_verification_arguments(compare)
    compare.add_argument(
        "--ruff-executable",
        type=Path,
        help="explicit local ruff for the static arm; defaults to PATH discovery, "
        "and a missing tool defers that arm rather than scoring it",
    )
    _add_review_arguments(compare)

    live = commands.add_parser(
        "live-local",
        help="explicitly authorized PAID evaluation of the frozen corpus with the "
        "real provider: requires --allow-paid-api plus a key, a frozen "
        "preregistration, an immutable manifest, and development-cap headroom; "
        "the full selected-case budget is reserved before the first call, every "
        "case advances through an atomic checkpoint state machine, and "
        "--resume RUN_ID continues an interrupted run without repeating a "
        "completed model call",
    )
    live.add_argument("--manifest", type=Path, required=True)
    live.add_argument("--output", type=Path, required=True)
    live.add_argument(
        "--allow-paid-api",
        action="store_true",
        help="explicit opt-in to paid provider calls; a present credential is "
        "never taken as consent",
    )
    live.add_argument(
        "--root",
        type=Path,
        help="caller-prepared checkout root; a case without one is excluded "
        "before any budget is reserved",
    )
    live.add_argument("--workspace", type=Path)
    live.add_argument("--run-id", help="predeclared identifier for a NEW run")
    live.add_argument(
        "--resume",
        metavar="RUN_ID",
        help="continue an interrupted run: completed model calls are never "
        "repeated, artifact hashes are re-verified, and each cost is appended "
        "exactly once",
    )
    live.add_argument(
        "--state-dir",
        type=Path,
        help="resumable checkpoint state (default: OUTPUT/state)",
    )
    live.add_argument(
        "--devspend",
        type=Path,
        default=Path("DEVSPEND.md"),
        help="development spend ledger used for the hard-cap headroom check",
    )
    live.add_argument(
        "--validation-receipt",
        type=Path,
        help="historical V1 receipt for exclusion inspection only; execution "
        "reports always withhold accuracy, and V2 is verify-validation only",
    )
    live.add_argument(
        "--validation-results",
        type=Path,
        help="the exact validation-results artifact the receipt was issued over",
    )
    _add_validation_verification_arguments(live)
    live.add_argument(
        "--python",
        action="append",
        default=[],
        metavar="SOURCE_ID=INTERPRETER",
        help="caller-prepared project interpreter for one opaque source id, "
        "exported to the executor as ATTEST_PROJECT_PYTHON for that case",
    )
    live.add_argument(
        "--case",
        action="append",
        default=[],
        help="restrict the run to these opaque case ids (a preregistered pilot)",
    )
    _add_review_arguments(live)

    evalue = commands.add_parser(
        "experiment-evalue",
        help="offline e-value diagnostic: measures E[LR | theta=0] for each "
        "factory channel and compares the realized wrong-certification rate "
        "against the Ville bound (experiment only, changes no constant)",
    )
    evalue.add_argument("--gammas", type=float, nargs="+", default=list(DEFAULT_NULL_GAMMAS))
    evalue.add_argument("--alphas", type=float, nargs="+", default=list(DEFAULT_VILLE_ALPHAS))
    evalue.add_argument("--k", type=int, default=5)
    evalue.add_argument("--tasks", type=int, default=2000)
    evalue.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    evalue.add_argument(
        "--judge-accuracy",
        type=float,
        help="per-vote accuracy; defaults to the accuracy at which LR1 is exactly "
        "the likelihood ratio of one positive vote",
    )
    evalue.add_argument(
        "--tier0-signal-slots",
        type=int,
        default=DEFAULT_NULL_ASSUMPTIONS.tier0_signal_slots,
        help="ASSUMPTION (never measured): independent chances for a spurious "
        "static signal to overlap a false finding's anchor",
    )
    evalue.add_argument(
        "--tier0-signal-rate",
        type=float,
        default=DEFAULT_NULL_ASSUMPTIONS.tier0_signal_rate,
        help="ASSUMPTION (never measured): per-slot spurious static signal rate "
        "used by the Ville section",
    )
    evalue.add_argument(
        "--tier0-signal-rates",
        type=float,
        nargs="+",
        default=list(DEFAULT_NULL_ASSUMPTIONS.tier0_signal_rate_sweep),
        help="sweep of the same assumption, all points reported",
    )
    evalue.add_argument(
        "--verification-reproduce-rate",
        type=float,
        default=DEFAULT_NULL_ASSUMPTIONS.verification_reproduce_rate,
        help="ASSUMPTION (never measured): rate at which a false finding's "
        "generated reproduction is classified as a reproduced regression",
    )
    evalue.add_argument(
        "--verification-no-purchase-rate",
        type=float,
        default=DEFAULT_NULL_ASSUMPTIONS.verification_no_purchase_rate,
        help="ASSUMPTION (never measured): rate at which no V purchase happens "
        "at all (deferral or no attempt)",
    )
    evalue.add_argument(
        "--verification-reproduce-rates",
        type=float,
        nargs="+",
        default=list(DEFAULT_NULL_ASSUMPTIONS.verification_reproduce_rate_sweep),
        help="sweep of the same assumption, all points reported",
    )
    evalue.add_argument(
        "--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES
    )
    evalue.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    evalue.add_argument("--output", type=Path, required=True)

    nullgrid = commands.add_parser(
        "experiment-nullgrid",
        help="offline multi-seed null grid on the REAL core engine: null-only "
        "streams, independent and correlated panels, both alarm kinds "
        "(experiment only, changes no constant)",
    )
    nullgrid.add_argument(
        "--alphas", type=float, nargs="+", default=list(DEFAULT_NULL_GRID_ALPHAS)
    )
    nullgrid.add_argument(
        "--lengths", type=int, nargs="+", default=list(DEFAULT_NULL_GRID_LENGTHS)
    )
    nullgrid.add_argument(
        "--panel-gammas",
        type=float,
        nargs="+",
        default=list(DEFAULT_NULL_GRID_PANEL_GAMMAS),
        help="judge C's clone rate on judge B (a clone rate, not a correlation)",
    )
    nullgrid.add_argument(
        "--seeds", type=int, nargs="+", default=list(DEFAULT_NULL_GRID_SEEDS)
    )
    nullgrid.add_argument(
        "--accuracies",
        type=float,
        nargs=3,
        default=list(NULL_GRID_ACCURACIES),
        metavar=("ACC_A", "ACC_B", "ACC_C"),
    )
    nullgrid.add_argument(
        "--alarm-poll-every", type=int, default=DEFAULT_ALARM_POLL_EVERY
    )
    nullgrid.add_argument("--output", type=Path, required=True)

    policy = commands.add_parser(
        "experiment-monitor",
        help="offline monitor intervention policies: ledger-only baseline vs "
        "quarantine and exploration-only recovery on shared seeded streams, "
        "with a high-error canary (experiment only, changes no constant)",
    )
    policy.add_argument("--alpha", type=float, default=0.1)
    policy.add_argument("--tasks", type=int, default=DEFAULT_POLICY_TASKS)
    policy.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_POLICY_SEEDS))
    policy.add_argument("--gamma", type=float, default=0.0)
    policy.add_argument(
        "--accuracies",
        type=float,
        nargs=3,
        default=list(NULL_GRID_ACCURACIES),
        metavar=("ACC_A", "ACC_B", "ACC_C"),
    )
    policy.add_argument("--canary-accuracy", type=float, default=DEFAULT_CANARY_ACCURACY)
    policy.add_argument(
        "--canary-shift-fraction", type=float, default=DEFAULT_CANARY_SHIFT_FRACTION
    )
    policy.add_argument("--output", type=Path, required=True)

    twoledger = commands.add_parser(
        "experiment-twoledger",
        help="offline two-ledger comparison: factory wealth vs V-only "
        "certification wealth with S/T as verification priority, plus the "
        "VOI-vs-FCFS verification budget at fixed recall (experiment only, "
        "changes no constant)",
    )
    twoledger.add_argument(
        "--alphas", type=float, nargs="+", default=list(DEFAULT_TWO_LEDGER_ALPHAS)
    )
    twoledger.add_argument("--k", type=int, default=5)
    twoledger.add_argument(
        "--gamma",
        type=float,
        default=None,
        help="panel clone rate; defaults to the production discount's rho",
    )
    twoledger.add_argument("--tasks", type=int, default=2000)
    twoledger.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    twoledger.add_argument(
        "--judge-accuracy",
        type=float,
        help="per-vote accuracy; defaults to the accuracy at which LR1 is exactly "
        "the likelihood ratio of one positive vote",
    )
    twoledger.add_argument(
        "--true-reproduce-rate",
        type=float,
        default=DEFAULT_TWO_LEDGER_ASSUMPTIONS.true_reproduce_rate,
        help="ASSUMPTION (never measured): rate at which a true finding's "
        "generated reproduction is classified as a reproduced regression",
    )
    twoledger.add_argument(
        "--false-reproduce-rate",
        type=float,
        default=DEFAULT_TWO_LEDGER_ASSUMPTIONS.false_reproduce_rate,
        help="ASSUMPTION (anchored only by D-031's 0-in-296 interval): rate at "
        "which a false finding's reproduction is classified as reproduced",
    )
    twoledger.add_argument(
        "--false-reproduce-rates",
        type=float,
        nargs="+",
        default=list(DEFAULT_TWO_LEDGER_ASSUMPTIONS.false_reproduce_rate_sweep),
        help="sweep of the same assumption, all points reported",
    )
    twoledger.add_argument(
        "--no-purchase-rate",
        type=float,
        default=DEFAULT_TWO_LEDGER_ASSUMPTIONS.verification_no_purchase_rate,
        help="ASSUMPTION: rate at which no V purchase happens at all",
    )
    twoledger.add_argument(
        "--tier0-signal-slots",
        type=int,
        default=DEFAULT_TWO_LEDGER_ASSUMPTIONS.tier0_signal_slots,
    )
    twoledger.add_argument(
        "--tier0-true-signal-rate",
        type=float,
        default=DEFAULT_TWO_LEDGER_ASSUMPTIONS.tier0_true_signal_rate,
    )
    twoledger.add_argument(
        "--tier0-false-signal-rate",
        type=float,
        default=DEFAULT_TWO_LEDGER_ASSUMPTIONS.tier0_false_signal_rate,
    )
    twoledger.add_argument(
        "--recall-targets", type=float, nargs="+", default=list(DEFAULT_RECALL_TARGETS)
    )
    twoledger.add_argument("--verification-cost", type=float, default=1.0)
    twoledger.add_argument(
        "--bootstrap-resamples", type=int, default=DEFAULT_BOOTSTRAP_RESAMPLES
    )
    twoledger.add_argument("--bootstrap-seed", type=int, default=DEFAULT_BOOTSTRAP_SEED)
    twoledger.add_argument("--output", type=Path, required=True)
    return parser


def _add_review_arguments(command: argparse.ArgumentParser) -> None:
    """The shared product review configuration for offline evaluation modes."""
    command.add_argument("--alpha", type=float, default=0.1)
    command.add_argument("--budget-usd", type=float, default=0.25)
    command.add_argument("--k-samples", type=int, default=5)
    command.add_argument("--max-findings", type=int, default=3)
    command.add_argument("--tier0-command", action="append", default=[])
    command.add_argument(
        "--auto-tighten-alpha",
        action="store_true",
        help="allow the ledger alpha auto-tighten rule (off by default so runs "
        "stay comparable)",
    )
    command.add_argument(
        "--differential-repeats",
        dest="repeats",
        type=int,
        default=3,
        help="pytest repetitions per side of each differential verification; "
        "unrelated to the fixed ten-repeat stability design",
    )
    command.add_argument("--line-slack", type=int, default=0)
    command.add_argument("--deadline", type=float, default=60.0)
    command.add_argument("--wall-timeout", type=float, default=60.0)
    command.add_argument("--verification-timeout", type=float, default=600.0)


_COMMANDS = {
    "import-bugsinpy": lambda args: _import(args),
    "validate": lambda args: _validate(args),
    "verify-validation": lambda args: _verify_validation(args),
    "experiment-rho": lambda args: _experiment(args),
    "replay": lambda args: _replay(args),
    "stability": lambda args: _stability(args),
    "compare": lambda args: _compare(args),
    "live-local": lambda args: _live(args),
    "experiment-evalue": lambda args: _experiment_evalue(args),
    "experiment-nullgrid": lambda args: _experiment_nullgrid(args),
    "experiment-monitor": lambda args: _experiment_monitor(args),
    "experiment-twoledger": lambda args: _experiment_twoledger(args),
}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _COMMANDS[args.command](args)
    except (OSError, ValueError) as exc:
        _emit({"error": str(exc), "status": "error"}, stream=sys.stderr)
        return 2
    _emit(result, stream=sys.stdout)
    if args.command == "validate":
        status = result.get("validation_status")
        if status in {"not_executed", "empty"}:
            return 3
        if status != "valid":
            return 4
    if args.command in {"replay", "stability", "compare", "live-local"} and (
        result.get("status") == "not_executed"
    ):
        return 3
    return 0


def _import(args: argparse.Namespace) -> dict[str, object]:
    source: Path = args.source
    if not source.is_dir():
        raise ValueError("source must be an existing local directory")
    if args.project_cache is not None and not args.project_cache.is_dir():
        raise ValueError("project cache must be an existing local directory")
    document = import_bugsinpy(
        source,
        args.output,
        args.limit,
        args.seed,
        project_cache=args.project_cache,
    )
    selection = document["selection"]
    assert isinstance(selection, dict)
    exclusions = document["exclusions"]
    assert isinstance(exclusions, list)
    return {
        "status": "ok",
        "manifest": str(args.output),
        "eligible_pairs": selection["eligible_pairs"],
        "selected_pairs": selection["selected_pairs"],
        "excluded_pairs": len(exclusions),
    }


_V2_EXECUTION_BOUNDARY_ERROR = (
    "symmetric V2 validation authority is refused for commands that execute "
    "project code; use verify-validation for pure offline verification and wait "
    "for X-01/V-03 or a public-key protocol before execution"
)


def _reject_v2_execution_authority(
    args: argparse.Namespace, *, command: str
) -> None:
    """Keep HMAC signing authority outside every same-UID project executor."""
    v2_values = (
        getattr(args, "validation_artifacts", None),
        getattr(args, "validation_provenance_key_id", None),
        getattr(args, "validation_provenance_key_file", None),
    )
    if any(value is not None for value in v2_values):
        raise ValueError(f"{command}: {_V2_EXECUTION_BOUNDARY_ERROR}")
    receipt = getattr(args, "validation_receipt", None)
    if receipt is None:
        return
    try:
        if receipt.stat().st_size > MAX_VALIDATION_DOCUMENT_BYTES:
            raise ValueError("validation receipt exceeds its protocol byte limit")
        document = json.loads(receipt.read_bytes())
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("validation receipt must be valid JSON") from exc
    if isinstance(document, dict) and document.get("schema_version") == "2":
        raise ValueError(f"{command}: {_V2_EXECUTION_BOUNDARY_ERROR}")


def _verify_validation(args: argparse.Namespace) -> dict[str, object]:
    """Verify one existing V2 bundle without loading a checkout or executor."""
    key_id = args.validation_provenance_key_id
    if not key_id:
        raise ValueError("validation provenance key id must not be empty")
    try:
        key = args.validation_provenance_key_file.read_bytes()
    except OSError as exc:
        raise ValueError("validation provenance key file is unreadable") from exc
    if not key:
        raise ValueError("validation provenance key file must not be empty")
    verification = load_validation_receipt_v2(
        args.validation_receipt,
        args.manifest,
        args.validation_results,
        args.validation_artifacts,
        authorized_provenance_keys={key_id: key},
    )

    def check_payload(check: ValidationAuthorityCheck) -> dict[str, object]:
        return {
            "accepted": check.accepted,
            "failure_paths": list(check.failure_paths),
        }

    return {
        "status": "ok",
        "offline": True,
        "authority": verification.authority,
        "integrity": check_payload(verification.integrity),
        "authorized_provenance": check_payload(verification.provenance),
        "semantic_policy": check_payload(verification.semantic_policy),
        "binding_sha256": hashlib.sha256(
            validation_receipt_binding_bytes(verification)
        ).hexdigest(),
    }


def _validate(args: argparse.Namespace) -> dict[str, object]:
    _reject_v2_execution_authority(args, command="validate")
    manifest = load_manifest(args.manifest)
    raw = _read_object(args.manifest)
    import_exclusions = raw.get("exclusions", [])
    if not isinstance(import_exclusions, list):
        raise ValueError("manifest exclusions must be a list")
    if args.root is None:
        pair_ids = sorted({case.pair_id for case in manifest.cases})
        results: dict[str, object] = {
            "manifest": args.manifest.name,
            "manifest_sha256": hashlib.sha256(args.manifest.read_bytes()).hexdigest(),
            "command_success": False,
            "corpus_valid": False,
            "validation_status": "not_executed",
            "scorable": False,
            "validated_pairs": 0,
            "excluded_pairs": len(pair_ids),
            "results": [
                {
                    "pair_id": pair_id,
                    "status": "not_executed",
                    "reason": "prepared_environment_required",
                }
                for pair_id in pair_ids
            ],
            "receipt": None,
        }
    else:
        if not args.root.is_dir():
            raise ValueError("root must be an existing prepared directory")
        if args.isolation_wrapper is None:
            raise ValueError("an isolation wrapper is required for prepared execution")
        if not args.isolation_wrapper.is_file():
            raise ValueError("isolation wrapper must be an existing file")
        if (args.receipt_out is None) != (args.validation_results_out is None):
            raise ValueError("receipt and validation results output paths are both required")
        interpreters = _interpreters(args.python)
        allowed_tools = _allowed_tools(args.tool)
        wrapper = str(args.isolation_wrapper.absolute())
        isolation = IsolationAdapter(
            capability="attest.network-deny.v1",
            wrapper_argv=(wrapper, *args.isolation_arg),
            wrapper_sha256=hashlib.sha256(args.isolation_wrapper.read_bytes()).hexdigest(),
        )
        runner = SubprocessCorpusRunner(
            interpreters,
            allowed_tools=allowed_tools,
            isolation=isolation,
            timeout_s=args.timeout,
            max_output_bytes=args.max_output_bytes,
        )
        results = validate_corpus(args.manifest, args.root, runner)
        receipt = results.get("receipt")
        if (
            args.receipt_out is not None
            and args.validation_results_out is not None
            and receipt is not None
        ):
            args.receipt_out.parent.mkdir(parents=True, exist_ok=True)
            args.validation_results_out.parent.mkdir(parents=True, exist_ok=True)
            write_canonical_json(args.receipt_out, receipt)
            write_canonical_json(
                args.validation_results_out, results["validation_results"]
            )
    results.update({"offline": True, "import_exclusions": import_exclusions})
    return results


def _experiment(args: argparse.Namespace) -> dict[str, object]:
    """Offline by construction: pure numpy over seeded synthetic panels.

    The harness reads the production channel constants and compares an
    alternative aggregator; it patches nothing. Below 500 global ledger labels
    the emitted report is a recommendation only (architecture red line 5).
    """
    report = run_rho_ablation(
        gammas=tuple(args.gammas),
        alphas=tuple(args.alphas),
        k=args.k,
        n_tasks=args.tasks,
        seeds=tuple(args.seeds),
        theta_prior=args.theta_prior,
        judge_accuracy=args.judge_accuracy,
    )
    payload = report.to_json_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.output, payload)
    return {
        "status": "ok",
        "offline": True,
        "experiment": report.experiment,
        "recommendation_status": report.status,
        "output": str(args.output),
        "digest": report.digest,
        "cells": len(report.cells),
    }


def _replay(args: argparse.Namespace) -> dict[str, object]:
    """Offline by construction: recorded cassettes and a loopback GitHub only.

    No provider client is ever constructed, no credential is read, and no
    remote host is contacted, whatever the environment holds.

    Three outcomes are kept apart, and none of them is a negative. A case
    without a recording, without a prepared checkout, or outside the validation
    receipt's allowlist is an **exclusion**: the product path never ran. A case
    the product ran and DEFERRED is an **abstention**: attest could not decide
    it, which is not the same as correctly staying silent. Task state does not
    erase published precision/harm, positive misses remain deployment misses,
    and silent non-completed controls are not true negatives. Every run retains
    operational evidence, but
    Phase0 execution never publishes accuracy: V1 is historical inspection
    only and V2 is accepted only by ``verify-validation``.
    """
    _reject_v2_execution_authority(args, command="replay")
    manifest = load_manifest(args.manifest)
    manifest_sha256 = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    receipt = _replay_receipt(args)
    requests, cassettes, exclusions = _replay_plan(manifest, args, receipt)
    store = ArtifactStore(args.output / "artifacts", secrets=process_secrets())
    results = evaluate_projects(
        requests,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        artifact_store=store,
    )
    measured = tuple(result for result in results if result.task_id is not None)
    abstentions: list[ReportAbstention] = []
    for result in results:
        reason = result.abstain_reason
        if (
            result.task_id is not None
            and result.measurement.task_status
            in {TaskStatus.PARTIALLY_DEFERRED, TaskStatus.FULLY_DEFERRED}
            and reason is not None
        ):
            abstentions.append(ReportAbstention(result.case_id, reason))
    exclusions.extend(
        ReportExclusion(result.case_id, _exclusion_reason(result))
        for result in results
        if result.task_id is None
    )
    report = build_report(
        manifest,
        tuple(result.run for result in measured),
        mode=REPLAY_MODE,
        manifest_sha256=manifest_sha256,
        exclusions=exclusions,
        abstentions=abstentions,
        differential_repeats=args.repeats,
        line_slack=args.line_slack,
        validation_receipt=receipt,
        measurement_records=tuple(result.measurement for result in measured),
    )
    store.finalize()
    report_path, markdown_path = write_report(report, args.output)
    return {
        "status": "ok" if report.evaluated_cases else "not_executed",
        "offline": True,
        "mode": REPLAY_MODE,
        "manifest": args.manifest.name,
        "manifest_sha256": manifest_sha256,
        "evaluated_cases": report.evaluated_cases,
        "abstained_cases": len(report.abstained_cases),
        "excluded_cases": len(report.excluded_cases),
        "metrics_status": "reported" if report.metrics is not None else "withheld",
        "metrics_withheld_reason": report.metrics_withheld_reason,
        "scoring_semantics": report.scoring_semantics,
        "outcome_accounting": report.to_json_dict()["outcome_accounting"],
        "spend_usd": round(sum(result.spend_usd for result in results), 6),
        "oracle_spend_usd": round(sum(result.oracle_spend_usd for result in results), 6),
        "digest": report.digest,
        "report": str(report_path),
        "report_markdown": str(markdown_path),
    }


def _replay_receipt(
    args: argparse.Namespace,
) -> ValidationReceipt | None:
    """Load only historical V1 metadata for an execution command."""
    if (args.validation_receipt is None) != (args.validation_results is None):
        raise ValueError("a validation receipt requires its validation results file")
    v2_values = (
        args.validation_artifacts,
        args.validation_provenance_key_id,
        args.validation_provenance_key_file,
    )
    if any(value is not None for value in v2_values):
        raise ValueError(_V2_EXECUTION_BOUNDARY_ERROR)
    if args.validation_receipt is None:
        return None
    try:
        if args.validation_receipt.stat().st_size > MAX_VALIDATION_DOCUMENT_BYTES:
            raise ValueError("validation receipt exceeds its protocol byte limit")
        receipt_bytes = args.validation_receipt.read_bytes()
        receipt_document = json.loads(receipt_bytes)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("validation receipt must be valid JSON") from exc
    schema_version = (
        receipt_document.get("schema_version")
        if isinstance(receipt_document, dict)
        else None
    )
    if schema_version == "1":
        return load_validation_receipt(
            args.validation_receipt, args.manifest, args.validation_results
        )
    if schema_version == "2":
        raise ValueError(_V2_EXECUTION_BOUNDARY_ERROR)
    raise ValueError("unsupported validation receipt schema")


def _replay_plan(
    manifest: BenchmarkManifest,
    args: argparse.Namespace,
    receipt: ValidationReceipt | None,
) -> tuple[list[ProjectEvaluationRequest], dict[str, Cassette], list[ReportExclusion]]:
    """Build one request per case that has both a recording and a checkout."""
    # D-146: which generator a replay runs is decided by the recordings, not by
    # the default. A cassette set with no probe in it can only replay the legacy
    # generator, and pretending otherwise would turn every case into a deferral.
    config = ReviewConfig(
        alpha=args.alpha,
        budget_usd=args.budget_usd,
        k_samples=args.k_samples,
        max_findings=args.max_findings,
        auto_tighten_alpha=bool(args.auto_tighten_alpha),
        tier0_commands=list(args.tier0_command),
        probe_generation=False,
    )
    limits = ExecutorLimits(wall_timeout_s=args.wall_timeout)
    workspace_root = args.workspace or (args.output / "workspace")
    runtimes = {row.case_id: row for row in manifest.runtime}
    sources = {row.source_id: row for row in manifest.sources}
    requests: list[ProjectEvaluationRequest] = []
    cassettes: dict[str, Cassette] = {}
    exclusions: list[ReportExclusion] = []
    for case in manifest.cases:
        if receipt is not None:
            try:
                require_validated_pair(receipt, case.pair_id)
            except ValueError:
                exclusions.append(
                    ReportExclusion(case.case_id, "pair_not_in_validation_receipt")
                )
                continue
        try:
            cassette = load_cassette(args.cassette_root, case.case_id)
        except ValueError:
            exclusions.append(ReportExclusion(case.case_id, "cassette_missing"))
            continue
        runtime = runtimes.get(case.case_id)
        repo = None if args.root is None or runtime is None else args.root / runtime.cwd
        if repo is None or not (repo / ".git").exists():
            exclusions.append(ReportExclusion(case.case_id, "prepared_environment_required"))
            continue
        cassettes[case.case_id] = cassette
        requests.append(
            ProjectEvaluationRequest(
                case_id=case.case_id,
                repo=repo,
                base_ref=_base_ref(case),
                head_ref=_head_ref(case),
                workspace_root=workspace_root,
                config=config,
                limits=limits,
                verification_timeout_s=args.verification_timeout,
                repeats=args.repeats,
                deadline_s=args.deadline,
                line_slack=args.line_slack,
                truth=manifest_project_truth(manifest, case.case_id),
                repository=_repository_identity(sources, case.source_id, repo),
            )
        )
    if replay_probe_generation(cassettes.values()):
        # every cassette records a probe, so this replay can run the product's
        # default generator; a set with even one legacy-only recording cannot
        probe_config = dataclasses.replace(config, probe_generation=True)
        requests = [
            dataclasses.replace(request, config=probe_config) for request in requests
        ]
    return requests, cassettes, exclusions


def _base_ref(case: BenchmarkCase) -> str:
    """A replay reviews the inverse fix, so its base is the fixed revision."""
    return case.fixed_commit if case.role == "historical_bug_replay" else case.buggy_commit


def _head_ref(case: BenchmarkCase) -> str:
    return case.buggy_commit if case.role == "historical_bug_replay" else case.fixed_commit


def _repository_identity(
    sources: dict[str, Any], source_id: str, repo: Path
) -> str:
    """Use manifest provenance when present, otherwise bind the prepared checkout."""
    source = sources.get(source_id)
    if source is not None:
        return str(source.project_url)
    return f"local:{repo.resolve()}"


def _exclusion_reason(result: ProjectEvaluationResult) -> str:
    return result.abstain_reason or "not_executed"


def _stability(args: argparse.Namespace) -> dict[str, object]:
    """Offline by construction: ten repeats replayed from one recorded cassette.

    No provider client is ever constructed and no credential is read; the only
    provider is the cassette replayer. Every repeat is persisted atomically, so
    re-running the command resumes completed repeats instead of re-buying them.
    All emitted metrics are operational (run-to-run variability); the study
    consumes no hidden truth, claims no accuracy, and therefore needs no
    validation receipt (D-019/D-032). Live paid stability would go through the
    live mode's explicit opt-in, not through this command.
    """
    manifest = load_manifest(args.manifest)
    manifest_sha256 = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    case = next((row for row in manifest.cases if row.case_id == args.case), None)
    if case is None:
        raise ValueError("case is not part of the preregistered manifest")
    refusal: dict[str, object] = {
        "status": "not_executed",
        "offline": True,
        "mode": REPLAY_MODE,
        "case_id": case.case_id,
        "manifest_sha256": manifest_sha256,
    }
    try:
        cassette = load_cassette(args.cassette_root, case.case_id)
    except ValueError:
        return {**refusal, "reason": "cassette_missing"}
    runtime = next(
        (row for row in manifest.runtime if row.case_id == case.case_id), None
    )
    repo = None if args.root is None or runtime is None else args.root / runtime.cwd
    if repo is None or not (repo / ".git").exists():
        return {**refusal, "reason": "prepared_environment_required"}
    request = ProjectEvaluationRequest(
        case_id=case.case_id,
        repo=repo,
        base_ref=_base_ref(case),
        head_ref=_head_ref(case),
        workspace_root=args.workspace or (args.output / "workspace"),
        config=_review_config(args),
        limits=ExecutorLimits(wall_timeout_s=args.wall_timeout),
        verification_timeout_s=args.verification_timeout,
        repeats=args.repeats,
        deadline_s=args.deadline,
        line_slack=args.line_slack,
        truth=None,
        repository=_repository_identity(
            {source.source_id: source for source in manifest.sources},
            case.source_id,
            repo,
        ),
    )
    state_dir = args.state_dir or (args.output / "state")
    result = run_stability_study(
        request,
        provider_factory=lambda repeat: ReplayProvider(cassette),
        state_dir=state_dir,
        locations=case.changed_locations,
        manifest_sha256=manifest_sha256,
        line_slack=args.line_slack,
        provider_label="replay_cassette",
    )
    report_path, markdown_path = write_stability_report(result.report, args.output)
    return {
        "status": "ok",
        "offline": True,
        "mode": REPLAY_MODE,
        "case_id": case.case_id,
        "manifest": args.manifest.name,
        "manifest_sha256": manifest_sha256,
        "repeats": result.report.repeats,
        "executed_repeats": result.executed_repeats,
        "resumed_repeats": result.resumed_repeats,
        "semantic_n": result.report.semantic_n,
        "operational_repeats": result.report.operational_repeats,
        "task_status_counts": result.report.task_status_counts,
        "deferred_repeats": len(result.report.deferred_runs),
        "failed_repeats": len(result.report.failed_runs),
        "spend_usd": round(result.report.spend_total_usd, 6),
        "digest": result.report.digest,
        "report": str(report_path),
        "report_markdown": str(markdown_path),
        "state_dir": str(state_dir),
    }


def _compare(args: argparse.Namespace) -> dict[str, object]:
    """Offline by construction: cassettes for both model arms, local ruff only.

    Arm A replays the real product path, arm B makes the one recorded bare
    call, and arm C runs the local deterministic analyzer; nothing here can
    construct a provider client or read a credential. Accuracy follows the
    historical V1 receipt discipline: a receipt may exclude cases from the
    execution plan but never authorizes scoring.  The written report therefore
    withholds every accuracy metric, while operational accounting -- calls,
    tokens, spend, wall time, tool cost -- is always published, losing arms and
    deferred runs included.  V2 is accepted only by ``verify-validation``.
    """
    _reject_v2_execution_authority(args, command="compare")
    manifest = load_manifest(args.manifest)
    manifest_sha256 = hashlib.sha256(args.manifest.read_bytes()).hexdigest()
    receipt = _replay_receipt(args)
    requests, cassettes, exclusions = _replay_plan(manifest, args, receipt)
    cases_by_id = {case.case_id: case for case in manifest.cases}
    plans = [
        ComparisonPlan(
            manifest=manifest,
            manifest_sha256=manifest_sha256,
            case=cases_by_id[request.case_id],
            request=request,
        )
        for request in requests
    ]
    ruff_executable = (
        str(args.ruff_executable)
        if args.ruff_executable is not None
        else shutil.which("ruff")
    )
    if plans and (
        args.comparison_authority_root is None
        or args.comparison_run_id is None
    ):
        raise ValueError(
            "non-empty comparison requires --comparison-authority-root and "
            "--comparison-run-id before execution"
        )
    execution = compare_arms(
        plans,
        provider_factory=lambda request: ReplayProvider(cassettes[request.case_id]),
        bare_provider_factory=lambda case_id: ReplayProvider(cassettes[case_id]),
        ruff_executable=ruff_executable,
        line_slack=args.line_slack,
        checkpoint_root=args.output / "state" / "comparison-calls",
        authority_root=args.comparison_authority_root,
        run_identity=args.comparison_run_id,
        provider_id="replay-cassette-v1",
        validation_receipt=receipt,
        manifest=manifest,
        manifest_sha256=manifest_sha256,
    )
    if not plans:
        measurements = execution.measurements
        return {
            "status": "not_executed",
            "offline": True,
            "mode": REPLAY_MODE,
            "manifest": args.manifest.name,
            "manifest_sha256": manifest_sha256,
            "arms": len(measurements.arms),
            "evaluated_cases": 0,
            "excluded_cases": len(exclusions),
            "deferred_runs": 0,
            "metrics_status": "withheld",
            "metrics_withheld_reason": (
                "comparison_not_executed_no_publication_authority"
            ),
            "outcome_accounting": None,
            "spend_usd": 0.0,
            "oracle_spend_usd": 0.0,
            "digest": None,
            "report": None,
            "report_markdown": None,
        }
    report = build_comparison_report(
        manifest,
        execution,
        manifest_sha256=manifest_sha256,
        exclusions=exclusions,
        validation_receipt=receipt,
        publication_authority=execution.publication_authority,
    )
    report_path, markdown_path = write_comparison_report(report, args.output)
    measurements = report.measurements
    evaluated = len(measurements.evaluated_case_ids)
    reported = evaluated > 0 and report.metrics_withheld_reason is None
    report_payload = report.to_json_dict()
    arms_payload = report_payload.get("arms")
    if not isinstance(arms_payload, list):
        raise ValueError("comparison report arms payload is malformed")
    product_payload = next(
        (
            arm
            for arm in arms_payload
            if isinstance(arm, dict) and arm.get("arm") == ARM_ATTEST_PRODUCT
        ),
        None,
    )
    if not isinstance(product_payload, dict) or not isinstance(
        product_payload.get("outcome_accounting"), dict
    ):
        raise ValueError("comparison report lacks current product outcome accounting")
    return {
        "status": "ok" if evaluated else "not_executed",
        "offline": True,
        "mode": REPLAY_MODE,
        "manifest": args.manifest.name,
        "manifest_sha256": manifest_sha256,
        "arms": len(measurements.arms),
        "evaluated_cases": evaluated,
        "excluded_cases": len(report.excluded_cases),
        "deferred_runs": sum(
            len(summary.abstentions) for summary in measurements.arms
        ),
        "metrics_status": "reported" if reported else "withheld",
        "metrics_withheld_reason": report.metrics_withheld_reason,
        "outcome_accounting": product_payload["outcome_accounting"],
        "spend_usd": round(sum(run.spend_usd for run in measurements.runs), 6),
        "oracle_spend_usd": round(
            sum(run.oracle_spend_usd for run in measurements.runs), 6
        ),
        "digest": report.digest,
        "report": str(report_path),
        "report_markdown": str(markdown_path),
    }


def _live(args: argparse.Namespace) -> dict[str, object]:
    """PAID by explicit opt-in only, and fail-closed everywhere else.

    The opt-in flag is checked before the manifest is read and long before any
    provider client could be constructed; a present credential is never taken
    as consent. Selection and exclusion happen next, so the reservation covers
    exactly the cases that will run; preflight then verifies the key by
    presence and length only (never logging it), the frozen preregistration,
    the manifest's immutability against that freeze, and development-cap
    headroom for the full reservation. Only after all of that does the real
    ``ApiProvider`` exist, one case at a time, inside the atomic checkpoint
    state machine. GitHub is never touched: live-local reviews local
    checkouts and mutates nothing remote.

    Settled spend is printed so the operator can record it in DEVSPEND.md;
    this command never edits the ledger itself.
    """
    if not args.allow_paid_api:
        raise LivePreflightError(
            REASON_PAID_API_NOT_ALLOWED,
            "live-local is a paid mode; pass --allow-paid-api explicitly. "
            "Refused before the manifest is read or any provider client is "
            "constructed.",
        )
    _reject_v2_execution_authority(args, command="live-local")
    if (args.run_id is None) == (args.resume is None):
        raise ValueError(
            "exactly one of --run-id (a new run) or --resume RUN_ID is required"
        )
    run_id = args.resume if args.resume is not None else args.run_id
    resume = args.resume is not None
    manifest = load_manifest(args.manifest)
    receipt = _replay_receipt(args)
    cases, exclusions = _live_plan(manifest, args, receipt)
    interpreters = {
        source_id: argv[0] for source_id, argv in _interpreters(args.python).items()
    }
    preflight = preflight_live(
        allow_paid_api=True,
        manifest_path=args.manifest,
        devspend_path=args.devspend,
        case_budgets_usd=tuple(
            reserved_case_budget_usd(case.request) for case in cases
        ),
        env=os.environ,
    )
    if not cases:
        return {
            "status": "not_executed",
            "mode": LIVE_MODE,
            "offline": False,
            "manifest": args.manifest.name,
            "manifest_sha256": preflight.manifest_sha256,
            "reason": "no_selected_cases",
            "evaluated_cases": 0,
            "abstained_cases": 0,
            "excluded_cases": len(exclusions),
            "exclusions": [row.to_json_dict() for row in exclusions],
            "spend_usd": 0.0,
        }
    model = cases[0].request.config.model
    state_dir = args.state_dir or (args.output / "state")
    result = run_live_local(
        cases,
        run_id=run_id,
        state_dir=state_dir,
        output_dir=args.output,
        manifest=manifest,
        manifest_sha256=preflight.manifest_sha256,
        preregistration_sha256=preflight.preregistration_sha256,
        provider_factory=lambda request: ApiProvider(model),
        resume=resume,
        interpreters=interpreters,
        exclusions=exclusions,
        validation_receipt=receipt,
        line_slack=args.line_slack,
    )
    report = result.report
    return {
        "status": "ok",
        "mode": LIVE_MODE,
        "offline": False,
        "manifest": args.manifest.name,
        "manifest_sha256": preflight.manifest_sha256,
        "run_id": run_id,
        "resumed": resume,
        "evaluated_cases": report.underlying.evaluated_cases,
        "abstained_cases": len(report.underlying.abstained_cases),
        "excluded_cases": len(report.underlying.excluded_cases),
        "executed_cases": result.executed_cases,
        "resumed_cases": result.resumed_cases,
        "reserved_usd": round(result.reserved_total_usd, 6),
        "spend_usd": round(result.settled_spend_usd, 6),
        "oracle_spend_usd": round(result.settled_oracle_spend_usd, 6),
        "accuracy_status": (
            "withheld" if report.accuracy_withheld_reason is not None else "reported"
        ),
        "accuracy_withheld_reason": report.accuracy_withheld_reason,
        "sample_sufficiency": report.sample_sufficiency["status"],
        "digest": report.digest,
        "report": str(result.report_path),
        "report_markdown": str(result.markdown_path),
        "state_dir": str(state_dir / run_id),
        "devspend_note": (
            "record the settled spend in DEVSPEND.md before the next paid run; "
            "this command never edits the ledger itself"
        ),
    }


def _live_plan(
    manifest: BenchmarkManifest,
    args: argparse.Namespace,
    receipt: ValidationReceipt | None,
) -> tuple[list[LiveCase], list[ReportExclusion]]:
    """Select exactly the cases the reservation will cover, excluding the rest.

    Exclusion happens before any budget is reserved: an unreceipted pair, an
    unprepared checkout, or an unselected case can never cost anything.
    """
    config = _review_config(args)
    limits = ExecutorLimits(wall_timeout_s=args.wall_timeout)
    workspace_root = args.workspace or (args.output / "workspace")
    runtimes = {row.case_id: row for row in manifest.runtime}
    sources = {row.source_id: row for row in manifest.sources}
    selected = set(args.case)
    unknown = selected - {case.case_id for case in manifest.cases}
    if unknown:
        raise ValueError(
            "unknown --case id(s): " + ", ".join(sorted(unknown))
        )
    cases: list[LiveCase] = []
    exclusions: list[ReportExclusion] = []
    for case in manifest.cases:
        if selected and case.case_id not in selected:
            exclusions.append(ReportExclusion(case.case_id, "not_selected"))
            continue
        if receipt is not None:
            try:
                require_validated_pair(receipt, case.pair_id)
            except ValueError:
                exclusions.append(
                    ReportExclusion(case.case_id, "pair_not_in_validation_receipt")
                )
                continue
        runtime = runtimes.get(case.case_id)
        repo = None if args.root is None or runtime is None else args.root / runtime.cwd
        if repo is None or not (repo / ".git").exists():
            exclusions.append(
                ReportExclusion(case.case_id, "prepared_environment_required")
            )
            continue
        cases.append(
            LiveCase(
                request=ProjectEvaluationRequest(
                    case_id=case.case_id,
                    repo=repo,
                    base_ref=_base_ref(case),
                    head_ref=_head_ref(case),
                    workspace_root=workspace_root,
                    config=config,
                    limits=limits,
                    verification_timeout_s=args.verification_timeout,
                    repeats=args.repeats,
                    deadline_s=args.deadline,
                    line_slack=args.line_slack,
                    truth=manifest_project_truth(manifest, case.case_id),
                    repository=_repository_identity(sources, case.source_id, repo),
                ),
                source_id=case.source_id,
            )
        )
    return cases, exclusions


def _review_config(args: argparse.Namespace) -> ReviewConfig:
    return ReviewConfig(
        alpha=args.alpha,
        budget_usd=args.budget_usd,
        k_samples=args.k_samples,
        max_findings=args.max_findings,
        auto_tighten_alpha=bool(args.auto_tighten_alpha),
        tier0_commands=list(args.tier0_command),
    )


def _experiment_evalue(args: argparse.Namespace) -> dict[str, object]:
    """Offline by construction: pure numpy over seeded null-only panels.

    Reads the production channel functions and constants to ask whether each
    evidence purchase is a valid e-value under the null, and whether the
    realized wrong-certification rate stays inside the Ville bound. It measures;
    it proposes nothing. The T and V null rates are assumptions, surfaced as
    flags and swept, never fitted. Below 500 global ledger labels the emitted
    report is a recommendation only (architecture red line 5), and a channel
    schedule is an owner decision (ground rule 8).
    """
    assumptions = NullAssumptions(
        tier0_signal_slots=args.tier0_signal_slots,
        tier0_signal_rate=args.tier0_signal_rate,
        tier0_signal_rate_sweep=tuple(args.tier0_signal_rates),
        verification_reproduce_rate=args.verification_reproduce_rate,
        verification_no_purchase_rate=args.verification_no_purchase_rate,
        verification_reproduce_rate_sweep=tuple(args.verification_reproduce_rates),
    )
    report = run_e_validity_experiment(
        gammas=tuple(args.gammas),
        alphas=tuple(args.alphas),
        k=args.k,
        n_tasks=args.tasks,
        seeds=tuple(args.seeds),
        judge_accuracy=args.judge_accuracy,
        assumptions=assumptions,
        bootstrap_resamples=args.bootstrap_resamples,
        bootstrap_seed=args.bootstrap_seed,
    )
    payload = report.to_json_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.output, payload)
    derived = report.derived
    assert isinstance(derived, dict)
    return {
        "status": "ok",
        "offline": True,
        "experiment": report.experiment,
        "recommendation_status": report.status,
        "output": str(args.output),
        "digest": report.digest,
        "expectations": len(report.expectations),
        "ville_cells": len(report.ville),
        "e_value_violations": derived["e_value_violations"],
        "ville_bound_breaches": derived["ville_bound_breaches"],
    }


def _experiment_nullgrid(args: argparse.Namespace) -> dict[str, object]:
    """Offline by construction: the REAL core Engine over seeded null streams.

    Every stream's truth is null-only, so every certified-true decision is a
    wrong certification. The harness reads production code and constants and
    patches nothing; below 500 global ledger labels the emitted report is a
    recommendation only (architecture red line 5).
    """
    report = run_null_grid(
        alphas=tuple(args.alphas),
        stream_lengths=tuple(args.lengths),
        panel_gammas=tuple(args.panel_gammas),
        seeds=tuple(args.seeds),
        accuracies=(args.accuracies[0], args.accuracies[1], args.accuracies[2]),
        alarm_poll_every=args.alarm_poll_every,
    )
    payload = report.to_json_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.output, payload)
    derived = report.derived
    return {
        "status": "ok",
        "offline": True,
        "experiment": report.experiment,
        "recommendation_status": report.status,
        "output": str(args.output),
        "digest": report.digest,
        "cells": len(report.cells),
        "wrong_certification_totals_by_alpha": derived[
            "wrong_certification_totals_by_alpha"
        ],
        "cells_exceeding_alpha_per_task": derived["cells_exceeding_alpha_per_task"],
        "alarm_kinds_ever_fired": derived["alarm_kinds_ever_fired"],
    }


def _experiment_monitor(args: argparse.Namespace) -> dict[str, object]:
    """Offline by construction: monitor policies on shared seeded streams.

    Interventions are simulated in an engine-loop rebuild pinned equal to the
    shipped Engine; only winners_curse_optimism can trigger one, and drift is
    reported but never acted on. Nothing here changes factory monitor
    behaviour; below 500 global ledger labels the emitted report is a
    recommendation only (architecture red line 5).
    """
    report = run_monitor_policy_experiment(
        alpha=args.alpha,
        n_tasks=args.tasks,
        seeds=tuple(args.seeds),
        gamma=args.gamma,
        accuracies=(args.accuracies[0], args.accuracies[1], args.accuracies[2]),
        canary_accuracy=args.canary_accuracy,
        canary_shift_fraction=args.canary_shift_fraction,
    )
    payload = report.to_json_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.output, payload)
    derived = report.derived
    return {
        "status": "ok",
        "offline": True,
        "experiment": report.experiment,
        "recommendation_status": report.status,
        "output": str(args.output),
        "digest": report.digest,
        "cells": len(report.cells),
        "canary_caught_by_any_policy": derived["canary_caught_by_any_policy"],
        "policies_catching_canary": derived["policies_catching_canary"],
        "false_brake_rate_by_policy": derived["false_brake_rate_by_policy"],
        "missed_unsafe_run_rate_by_policy": derived["missed_unsafe_run_rate_by_policy"],
    }


def _experiment_twoledger(args: argparse.Namespace) -> dict[str, object]:
    """Offline by construction: the two-ledger model against the factory arm.

    S/T order the verification queue and buy nothing; certification wealth is
    purchased by V only; speech remains exactly certification_wealth >=
    1/alpha. The T and V rates are assumptions, surfaced as flags and swept.
    Nothing here patches the gate or the channels; adopting the model is an
    owner decision (ground rule 8), and below 500 global ledger labels the
    emitted report is a recommendation only (architecture red line 5).
    """
    assumptions = TwoLedgerAssumptions(
        true_reproduce_rate=args.true_reproduce_rate,
        false_reproduce_rate=args.false_reproduce_rate,
        false_reproduce_rate_sweep=tuple(args.false_reproduce_rates),
        verification_no_purchase_rate=args.no_purchase_rate,
        tier0_signal_slots=args.tier0_signal_slots,
        tier0_true_signal_rate=args.tier0_true_signal_rate,
        tier0_false_signal_rate=args.tier0_false_signal_rate,
    )
    kwargs: dict[str, Any] = {
        "alphas": tuple(args.alphas),
        "k": args.k,
        "n_tasks": args.tasks,
        "seeds": tuple(args.seeds),
        "judge_accuracy": args.judge_accuracy,
        "assumptions": assumptions,
        "recall_targets": tuple(args.recall_targets),
        "verification_cost": args.verification_cost,
        "bootstrap_resamples": args.bootstrap_resamples,
        "bootstrap_seed": args.bootstrap_seed,
    }
    if args.gamma is not None:
        kwargs["gamma"] = args.gamma
    report = run_two_ledger_experiment(**kwargs)
    payload = report.to_json_dict()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.output, payload)
    derived = report.derived
    return {
        "status": "ok",
        "offline": True,
        "experiment": report.experiment,
        "recommendation_status": report.status,
        "output": str(args.output),
        "digest": report.digest,
        "cells": len(report.cells),
        "budget_rows": len(report.budget),
        "speech_feasibility": derived["speech_feasibility"],
        "cells_where_arms_differ": derived["cells_where_arms_differ"],
    }


def _interpreters(values: list[str]) -> dict[str, tuple[str, ...]]:
    result: dict[str, tuple[str, ...]] = {}
    for value in values:
        source_id, separator, interpreter = value.partition("=")
        if not separator or not source_id or not interpreter:
            raise ValueError("--python must use SOURCE_ID=INTERPRETER")
        if source_id in result:
            raise ValueError("duplicate --python source id")
        path = Path(interpreter)
        if not path.is_file():
            raise ValueError("interpreter must be an existing file")
        result[source_id] = (str(path.absolute()),)
    return result


def _allowed_tools(values: list[str]) -> dict[tuple[str, str], tuple[str, ...]]:
    result: dict[tuple[str, str], tuple[str, ...]] = {}
    for value in values:
        binding, separator, executable = value.partition("=")
        source_id, tool_separator, tool = binding.partition(":")
        if (
            not separator
            or not tool_separator
            or not source_id
            or not tool
            or not executable
        ):
            raise ValueError("--tool must use SOURCE_ID:TOOL=EXECUTABLE")
        key = (source_id, tool)
        if key in result:
            raise ValueError("duplicate --tool source id and tool")
        path = Path(executable)
        if not path.is_file():
            raise ValueError("tool executable must be an existing file")
        result[key] = (str(path.absolute()),)
    return result


def _read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def _emit(value: object, *, stream: Any) -> None:
    stream.write(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
