#!/usr/bin/env python3
"""Offline command-line adapter for importing and validating benchmark corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from attest.benchmark.api import (
    ProjectEvaluationRequest,
    ProjectEvaluationResult,
    ProjectTruth,
    evaluate_projects,
)
from attest.benchmark.artifacts import ArtifactStore, process_secrets
from attest.benchmark.corpus import (
    IsolationAdapter,
    SubprocessCorpusRunner,
    ValidationReceipt,
    import_bugsinpy,
    load_validation_receipt,
    require_validated_pair,
    validate_corpus,
)
from attest.benchmark.experiments import (
    DEFAULT_BOOTSTRAP_RESAMPLES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_GAMMAS,
    DEFAULT_NULL_ASSUMPTIONS,
    DEFAULT_NULL_GAMMAS,
    DEFAULT_SEEDS,
    DEFAULT_VILLE_ALPHAS,
    FACTORY_ALPHAS,
    NullAssumptions,
    run_e_validity_experiment,
    run_rho_ablation,
)
from attest.benchmark.report import (
    REPLAY_MODE,
    ReportAbstention,
    ReportExclusion,
    build_report,
    write_report,
)
from attest.benchmark.runner import Cassette, ReplayProvider, load_cassette
from attest.benchmark.schema import BenchmarkCase, BenchmarkManifest, load_manifest
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    importer = commands.add_parser("import-bugsinpy")
    importer.add_argument("--source", type=Path, required=True)
    importer.add_argument("--project-cache", type=Path)
    importer.add_argument("--output", type=Path, required=True)
    importer.add_argument("--limit", type=int, required=True)
    importer.add_argument("--seed", type=int, required=True)

    validator = commands.add_parser("validate")
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
    validator.add_argument("--receipt-out", type=Path)
    validator.add_argument("--validation-results-out", type=Path)
    validator.add_argument("--timeout", type=float, default=60)
    validator.add_argument("--max-output-bytes", type=int, default=65_536)

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
        help="validation receipt bound to this manifest digest; without it the "
        "report withholds every accuracy metric and says so",
    )
    replay.add_argument(
        "--validation-results",
        type=Path,
        help="the exact validation-results artifact the receipt was issued over",
    )
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
    return parser


_COMMANDS = {
    "import-bugsinpy": lambda args: _import(args),
    "validate": lambda args: _validate(args),
    "experiment-rho": lambda args: _experiment(args),
    "replay": lambda args: _replay(args),
    "experiment-evalue": lambda args: _experiment_evalue(args),
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
    if args.command == "replay" and result.get("status") == "not_executed":
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


def _validate(args: argparse.Namespace) -> dict[str, object]:
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
            _write_canonical_json(args.receipt_out, receipt)
            _write_canonical_json(
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
    _write_canonical_json(args.output, payload)
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
    it, which is not the same as correctly staying silent, so it enters no
    accuracy denominator. Only a completed run is **scored**, and only when a
    receipt bound to this manifest digest authorises scoring at all (D-019).
    """
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
    scored = tuple(
        result
        for result in results
        if result.task_id is not None and result.abstain_reason is None
    )
    abstentions: list[ReportAbstention] = []
    for result in results:
        reason = result.abstain_reason
        if result.task_id is not None and reason is not None:
            abstentions.append(ReportAbstention(result.case_id, reason))
    exclusions.extend(
        ReportExclusion(result.case_id, _exclusion_reason(result))
        for result in results
        if result.task_id is None
    )
    report = build_report(
        manifest,
        tuple(result.run for result in scored),
        mode=REPLAY_MODE,
        manifest_sha256=manifest_sha256,
        exclusions=exclusions,
        abstentions=abstentions,
        differential_repeats=args.repeats,
        line_slack=args.line_slack,
        validation_receipt=receipt,
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
        "spend_usd": round(sum(result.spend_usd for result in results), 6),
        "oracle_spend_usd": round(sum(result.oracle_spend_usd for result in results), 6),
        "digest": report.digest,
        "report": str(report_path),
        "report_markdown": str(markdown_path),
    }


def _replay_receipt(args: argparse.Namespace) -> ValidationReceipt | None:
    """Load the corpus validator's own receipt, or record that there is none.

    The receipt loader is the single gate: it verifies the manifest digest, the
    exact validation-results bytes, and the derived allowlist. A supplied but
    unverifiable receipt fails the command closed rather than being downgraded
    to a run without one.
    """
    if (args.validation_receipt is None) != (args.validation_results is None):
        raise ValueError("a validation receipt requires its validation results file")
    if args.validation_receipt is None:
        return None
    return load_validation_receipt(
        args.validation_receipt, args.manifest, args.validation_results
    )


def _replay_plan(
    manifest: BenchmarkManifest,
    args: argparse.Namespace,
    receipt: ValidationReceipt | None,
) -> tuple[list[ProjectEvaluationRequest], dict[str, Cassette], list[ReportExclusion]]:
    """Build one request per case that has both a recording and a checkout."""
    config = ReviewConfig(
        alpha=args.alpha,
        budget_usd=args.budget_usd,
        k_samples=args.k_samples,
        max_findings=args.max_findings,
        auto_tighten_alpha=bool(args.auto_tighten_alpha),
        tier0_commands=list(args.tier0_command),
    )
    limits = ExecutorLimits(wall_timeout_s=args.wall_timeout)
    workspace_root = args.workspace or (args.output / "workspace")
    runtimes = {row.case_id: row for row in manifest.runtime}
    truths: dict[str, tuple[Any, ...]] = {}
    for truth in manifest.truth_defects:
        truths[truth.case_id] = (*truths.get(truth.case_id, ()), truth)
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
                truth=(
                    ProjectTruth(fixed_ref=case.fixed_commit, defects=truths[case.case_id])
                    if case.case_id in truths
                    else None
                ),
            )
        )
    return requests, cassettes, exclusions


def _base_ref(case: BenchmarkCase) -> str:
    """A replay reviews the inverse fix, so its base is the fixed revision."""
    return case.fixed_commit if case.role == "historical_bug_replay" else case.buggy_commit


def _head_ref(case: BenchmarkCase) -> str:
    return case.buggy_commit if case.role == "historical_bug_replay" else case.fixed_commit


def _exclusion_reason(result: ProjectEvaluationResult) -> str:
    return result.abstain_reason or "not_executed"


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
    _write_canonical_json(args.output, payload)
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


def _write_canonical_json(path: Path, value: object) -> None:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
