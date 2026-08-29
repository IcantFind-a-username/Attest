#!/usr/bin/env python3
"""Offline command-line adapter for importing and validating benchmark corpora."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from attest.benchmark.corpus import (
    IsolationAdapter,
    SubprocessCorpusRunner,
    import_bugsinpy,
    validate_corpus,
)
from attest.benchmark.experiments import (
    DEFAULT_GAMMAS,
    DEFAULT_SEEDS,
    FACTORY_ALPHAS,
    run_rho_ablation,
)
from attest.benchmark.schema import load_manifest


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
    return parser


_COMMANDS = {
    "import-bugsinpy": lambda args: _import(args),
    "validate": lambda args: _validate(args),
    "experiment-rho": lambda args: _experiment(args),
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
