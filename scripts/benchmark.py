#!/usr/bin/env python3
"""Offline command-line adapter for importing and validating benchmark corpora."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from attest.benchmark.corpus import (
    SubprocessCorpusRunner,
    import_bugsinpy,
    validate_corpus,
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
    validator.add_argument(
        "--python",
        action="append",
        default=[],
        metavar="SOURCE_ID=INTERPRETER",
        help="caller-prepared Python interpreter for one opaque source id",
    )
    validator.add_argument("--timeout", type=float, default=60)
    validator.add_argument("--max-output-bytes", type=int, default=65_536)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = _import(args) if args.command == "import-bugsinpy" else _validate(args)
    except (OSError, ValueError) as exc:
        _emit({"error": str(exc), "status": "error"}, stream=sys.stderr)
        return 2
    _emit(result, stream=sys.stdout)
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
            "validated_pairs": 0,
            "excluded_pairs": len(pair_ids),
            "results": [
                {
                    "pair_id": pair_id,
                    "status": "excluded",
                    "reason": "prepared_environment_required",
                }
                for pair_id in pair_ids
            ],
        }
    else:
        if not args.root.is_dir():
            raise ValueError("root must be an existing prepared directory")
        interpreters = _interpreters(args.python)
        runner = SubprocessCorpusRunner(
            interpreters,
            timeout_s=args.timeout,
            max_output_bytes=args.max_output_bytes,
        )
        results = validate_corpus(args.manifest, args.root, runner)
    results.update(
        {"status": "ok", "offline": True, "import_exclusions": import_exclusions}
    )
    return results


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
        result[source_id] = (str(path.resolve()),)
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
