#!/usr/bin/env python3
"""Re-verify the one oracle receipt that refuted a product certificate.

D-059 surfaced four findings and its benchmark oracle re-verified them
independently, confirming three and refuting the fourth as ``unfaithful``. The
refutation came from the oracle's own reproduction, which opened with an
API probe (``black.Mode(line_length=88)`` falling back to
``format_str(src, line_length=88)``). Neither name exists at the 2019-era
revision under test, so both branches raised ``TypeError`` on *both* sides.

A test that raises identically on head and base has zero discriminating power
whatever the truth is; that is why this replay is justified independently of
its result, and why both the before and the after number are reported.

Nothing here is paid. The reproduction bodies are inputs, the differential is
the product's own ``execute_differential``, and the corpus interpreter is the
project's frozen 3.8.3 venv.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from attest.benchmark.artifacts import write_canonical_json
from attest.benchmark.runner import run_differential_repro
from attest.review.candidates import StoredCandidate
from attest.review.executor import ExecutorLimits, ReproSpec
from attest.review.schema import Finding

CASE_ID = "case-c6f141a2be09"
PAIR_ID = "pair-dee2edc00ad8"
FINDING_ID = "ed1d3ea89b"
HEAD_SHA = "1bbb01b854d168d76ebe4bf78961c2152ae075d9"
BASE_SHA = "9394de150ebf0adc426523f46dc08e8b2b2b0b63"
PROJECT = "black"
ANCHOR_FILE = "black.py"
ANCHOR_LINE = 2495
REPEATS = 3

SOURCE = (
    "def very_long_function_name_that_forces_a_split("
    "argument_name_that_is_long) -> ReturnType:\n    pass\n"
)

# Verbatim reconstruction of the probe the D-059 oracle body opened with, as
# quoted in docs/2026-09-01-d059-audit-window-and-repeat-semantics.md.
BROKEN_BODY = (
    "import black\n\n\n"
    "def test_single_argument_def_keeps_a_trailing_comma():\n"
    "    src = " + repr(SOURCE) + "\n"
    "    try:\n"
    "        mode = black.Mode(line_length=88)\n"
    "        formatted = black.format_str(src, mode=mode)\n"
    "    except AttributeError:\n"
    "        formatted = black.format_str(src, line_length=88)\n"
    '    assert "argument_name_that_is_long," in formatted\n'
)

# The same intent, using the API this revision actually exposes.
FIXED_BODY = (
    "import black\n\n\n"
    "def _format(src):\n"
    '    """Use whichever entry point this revision actually exposes."""\n'
    '    factory = getattr(black, "Mode", None) or getattr(black, "FileMode", None)\n'
    "    if factory is None:\n"
    '        raise AssertionError("no black mode type exists at this revision")\n'
    "    return black.format_str(src, mode=factory(line_length=88))\n\n\n"
    "def test_single_argument_def_keeps_a_trailing_comma():\n"
    "    src = " + repr(SOURCE) + "\n"
    "    formatted = _format(src)\n"
    '    assert "argument_name_that_is_long," in formatted\n'
)


def _candidate() -> StoredCandidate:
    finding = Finding(
        claim=(
            "Removing the no_commas branch in bracket_split_build_line drops the "
            "trailing comma a split single-argument def used to receive."
        ),
        file=ANCHOR_FILE,
        line=ANCHOR_LINE,
        failure_scenario=(
            "A long single-argument def is exploded across lines without the "
            "trailing comma the fix guarantees."
        ),
        falsification_plan=(
            "Format a long single-argument def and check for the trailing comma."
        ),
        votes=5,
        sample_ids=[1, 2, 3, 4, 5],
    )
    return StoredCandidate(
        task_id="d060-oracle-api-replay",
        finding=finding,
        wealth=1.0,
        action="drawer",
        alpha=0.1,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-cache", required=True, type=Path)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args(argv)

    upstream = args.corpus_cache / "upstream" / PROJECT
    interpreter = args.corpus_cache / "venvs" / PROJECT / "bin" / "python"
    if not (upstream / ".git").exists():
        print(f"missing corpus checkout {upstream}", file=sys.stderr)
        return 2
    if not interpreter.is_file():
        print(f"missing corpus interpreter {interpreter}", file=sys.stderr)
        return 2

    repo = args.workspace / "repo"
    if not repo.exists():
        subprocess.run(
            ["git", "clone", "--quiet", "--no-checkout", str(upstream), str(repo)],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo), "checkout", "--detach", "--quiet", HEAD_SHA],
            check=True,
            capture_output=True,
        )

    candidate = _candidate()
    os.environ["ATTEST_PROJECT_PYTHON"] = str(interpreter)
    receipts = {}
    try:
        for label, body in (("before", BROKEN_BODY), ("after", FIXED_BODY)):
            receipt = run_differential_repro(
                repo,
                candidate,
                ReproSpec(test_body=body),
                ExecutorLimits(),
                buggy_sha=HEAD_SHA,
                fixed_sha=BASE_SHA,
                repeats=REPEATS,
            )
            payload = receipt.to_json_dict()
            payload["test_body"] = body
            receipts[label] = payload
    finally:
        os.environ.pop("ATTEST_PROJECT_PYTHON", None)

    artifact = {
        "schema_version": "attest.oracle-api-replay.v1",
        "case_id": CASE_ID,
        "pair_id": PAIR_ID,
        "product_finding_id": FINDING_ID,
        "head_sha": HEAD_SHA,
        "base_sha": BASE_SHA,
        "repeats": REPEATS,
        "paid_calls": 0,
        "spend_usd": 0.0,
        "receipts": receipts,
        "limitations": [
            "The reproduction bodies are inputs; this measures the differential, "
            "not a generator.",
            "One finding of one pair. No accuracy, precision or recall follows.",
        ],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(args.out, artifact)
    print(json.dumps({k: v["repro_status"] for k, v in receipts.items()}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
