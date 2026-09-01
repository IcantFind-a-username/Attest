"""End-to-end certification path on a receipt-validated corpus pair.

D-058 names this shape the highest-value test in the repository: given a real
historical defect and a correct reproduction, the whole verification path must
produce a certified receipt. Nothing on the path under test is stubbed -- the
corpus project's own Python runs the real pytest, `execute_differential` builds
real detached worktrees at the pair's exact SHAs, and the containment guards,
repeat semantics and evidence classification all run for real. Only the
generator is supplied, because the reproduction content is an input to this
test, not the thing being measured.

The environment is a read-only local input, so the test skips unless
ATTEST_CORPUS_CACHE points at a prepared corpus cache.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.channels import V_CAP
from attest.review.config import load_pricing
from attest.review.executor import (
    EvidenceClass,
    ExecutionOutcome,
    ExecutorLimits,
    verify_candidate,
)
from attest.review.gate import evaluate_finding
from attest.review.ledger import Ledger
from attest.review.proposer import ProviderResult
from attest.review.schema import Finding

# The receipt-validated pair this test binds to: black bug 17, whose fix commit
# is "Fix handling of empty files". On the buggy revision `lib2to3_parse` indexes
# `src_txt[-1]` unguarded, so formatting an empty string raises IndexError; the
# fixed revision slices instead and returns "".
PAIR_ID = "pair-acc00ce9f068"
CASE_ID = "case-c22190aa4fc9"
PROJECT = "black"
ANCHOR_FILE = "black.py"
ANCHOR_LINE = 626

REPRO_TEST_BODY = '''\
import black


def test_empty_source_formats_to_empty_output():
    assert black.format_str("", line_length=88) == ""
'''

ALPHA = 0.1
REPEATS = 3


def _corpus_cache() -> Path:
    raw = os.environ.get("ATTEST_CORPUS_CACHE", "")
    if not raw:
        pytest.skip("ATTEST_CORPUS_CACHE is unset; the corpus environment is not available")
    cache = Path(raw)
    if not cache.is_dir():
        pytest.skip(f"corpus cache {cache} does not exist")
    return cache


def _validated_case(repo_root: Path) -> dict[str, Any]:
    """The manifest case for PAIR_ID, refusing to run unless the corpus receipt
    actually validated that pair. A pair the receipt excluded proves nothing."""
    corpus = repo_root / "benchmarks" / "attest-v1"
    results = json.loads((corpus / "validation-results.json").read_text(encoding="utf-8"))
    validated = {
        row["pair_id"] for row in results["results"] if row.get("status") == "validated"
    }
    assert PAIR_ID in validated, f"{PAIR_ID} is not receipt-validated"
    manifest = json.loads((corpus / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest["cases"]:
        if case["case_id"] == CASE_ID:
            assert case["role"] == "historical_bug_replay"
            return case
    raise AssertionError(f"{CASE_ID} is missing from the corpus manifest")


class _CannedGenerator:
    """Supplies the known-correct reproduction. The generator is an input here;
    every downstream decision still runs for real."""

    def __init__(self, body: str):
        self.body = body
        self.calls = 0

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.calls += 1
        return ProviderResult(
            text=json.dumps({"test_body": self.body}),
            input_tokens=0,
            output_tokens=0,
            stop_reason="end_turn",
        )


@pytest.mark.corpus
def test_receipt_validated_regression_certifies_end_to_end(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    cache = _corpus_cache()
    case = _validated_case(repo_root)

    upstream = cache / "upstream" / PROJECT
    interpreter = cache / "venvs" / PROJECT / "bin" / "python"
    if not (upstream / ".git").exists():
        pytest.skip(f"corpus checkout {upstream} is not available")
    if not interpreter.is_file():
        pytest.skip(f"corpus interpreter {interpreter} is not available")

    # a private clone: the reviewed revision must never be a worktree of the
    # shared read-only corpus checkout
    review_repo = tmp_path / "review"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-checkout", str(upstream), str(review_repo)],
        check=True,
        capture_output=True,
    )
    head_sha = case["buggy_commit"]
    base_sha = case["fixed_commit"]
    subprocess.run(
        ["git", "-C", str(review_repo), "checkout", "--detach", "--quiet", head_sha],
        check=True,
        capture_output=True,
    )

    finding = Finding(
        claim="Formatting an empty source string raises IndexError instead of returning it.",
        file=ANCHOR_FILE,
        line=ANCHOR_LINE,
        failure_scenario="black.format_str(\"\", line_length=88) on an empty file.",
        falsification_plan="Format an empty string and compare against an empty result.",
        votes=5,
        sample_ids=[1, 2, 3, 4, 5],
    )
    gate_result = evaluate_finding(finding, ALPHA, tier0=[])
    candidate = StoredCandidate(
        task_id="corpus-e2e",
        finding=finding,
        wealth=gate_result.wealth,
        action=gate_result.action,
        alpha=ALPHA,
    )

    os.environ["ATTEST_PROJECT_PYTHON"] = str(interpreter)
    try:
        verification = verify_candidate(
            review_repo,
            candidate,
            gate_result,
            _CannedGenerator(REPRO_TEST_BODY),
            Budget(limit_usd=1.0, model=str(load_pricing()["default_model"])),
            ExecutorLimits(),
            base_sha=base_sha,
            head_sha=head_sha,
            repeats=REPEATS,
        )
    finally:
        os.environ.pop("ATTEST_PROJECT_PYTHON", None)

    execution = verification.execution
    assert [run.outcome for run in execution.head_runs] == [
        ExecutionOutcome.REPRODUCED
    ] * REPEATS, f"head runs: {[(r.outcome.value, r.reason) for r in execution.head_runs]}"
    assert [run.outcome for run in execution.base_runs] == [
        ExecutionOutcome.NOT_REPRODUCED
    ] * REPEATS, f"base runs: {[(r.outcome.value, r.reason) for r in execution.base_runs]}"
    assert execution.outcome is ExecutionOutcome.REPRODUCED, execution.reason
    assert execution.evidence_class is EvidenceClass.REGRESSION_REPRODUCED
    assert execution.network_blocked

    # the certified receipt: V purchased at the reproduction LR, and the gate
    # decides to speak
    assert [purchase.channel for purchase in verification.gate_result.purchases][-1] == "V"
    assert verification.gate_result.purchases[-1].lr == V_CAP
    assert verification.gate_result.decision == 1

    rows = [e for e in Ledger(review_repo).entries() if e.get("kind") == "verification"]
    row = rows[-1]
    assert row["evidence_class"] == "regression_reproduced"
    assert row["head_runs"] == ["reproduced"] * REPEATS
    assert row["base_runs"] == ["not_reproduced"] * REPEATS
