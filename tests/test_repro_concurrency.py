"""Two candidates' reproductions may overlap; the journal still reads serially (D-157).

A reproduction is three container runs of a generated test on two revisions,
and a review that has five candidates pays that latency five times over. The
runs *inside* one candidate stay strictly serial -- the repeat count is what
makes a reproduction stable, and a concurrent repeat is a different experiment
-- but two different candidates have nothing to say to each other.

What must not change is the evidence. The ledger is the record a later reader
reconciles, and its order must not depend on which container finished first, so
each concurrent candidate journals into a buffer and the buffers are written in
the ranked order the serial path would have used. These tests pin exactly that:
same bytes, less wall clock.
"""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from attest.execution.local_adapter import LocalDevelopmentAdapter
from attest.review import verification as verification_module
from attest.review.budget import Budget
from attest.review.candidates import CandidateStore
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutionOutcome, VerificationRun
from attest.review.gate import GateResult
from attest.review.run import ReviewRun
from attest.review.schema import Finding

CANDIDATES = 4
SLEEP_S = 0.30


def _repo(tmp_path: Path) -> tuple[Path, str, str]:
    tmp_path.mkdir(parents=True, exist_ok=True)

    def git(*args: str) -> str:
        done = subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        )
        return done.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "app.py").write_text("\n".join(f"x{i} = {i}" for i in range(20)), encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "app.py").write_text("\n".join(f"x{i} = {i + 1}" for i in range(20)), "utf-8")
    git("add", "-A")
    git("commit", "-m", "head")
    return tmp_path, base, git("rev-parse", "HEAD")


def _results() -> list[GateResult]:
    return [
        GateResult(
            Finding(
                claim=f"candidate {index} is wrong.",
                file="app.py",
                line=index + 1,
                failure_scenario=f"scenario {index}",
                falsification_plan=f"plan {index}",
            ),
            wealth=10.0 - index,
            decision=None,
        )
        for index in range(CANDIDATES)
    ]


@dataclass
class _Execution:
    outcome: ExecutionOutcome
    reason: str
    elapsed_s: float = 0.0
    network_blocked: bool = False
    base_sha: str = ""
    head_sha: str = ""
    head_runs: tuple[()] = ()
    base_runs: tuple[()] = ()
    repeats: int = 3
    probe: None = None
    executed_spec: None = None
    intent: None = None


def _stub_verify(concurrent: list[int], live: list[int], lock: threading.Lock):
    """A reproduction that takes time, journals two rows, and counts overlap."""

    def verify(repo, candidate, gate_result, *args, ledger=None, **kwargs):
        with lock:
            live[0] += 1
            concurrent.append(live[0])
        time.sleep(SLEEP_S)
        with lock:
            live[0] -= 1
        journal = ledger if ledger is not None else verification_module.Ledger(repo)
        journal.append(
            {"kind": "probe_observation", "finding_id": candidate.finding.finding_id}
        )
        journal.record_verification(
            task_id=candidate.task_id,
            finding_id=candidate.finding.finding_id,
            outcome=ExecutionOutcome.NOT_REPRODUCED.value,
            reason="stub",
            elapsed_s=0.0,
            network_blocked=False,
            evidence="",
        )
        return VerificationRun(
            execution=_Execution(ExecutionOutcome.NOT_REPRODUCED, "stub"),
            gate_result=gate_result,
            spec=None,
        )

    return verify


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, concurrency: int):
    repo, base, head = _repo(tmp_path)
    results = _results()
    task_id = "20260906-120000-abcdef01"
    CandidateStore(repo).append(task_id, 0.1, results)
    concurrent: list[int] = []
    live = [0]
    monkeypatch.setattr(
        verification_module, "verify_candidate", _stub_verify(concurrent, live, threading.Lock())
    )
    monkeypatch.setattr(
        verification_module,
        "attempt_certification",
        lambda *a, **k: _Attempt(),
    )
    review = ReviewRun(
        task_id=task_id,
        alpha=0.1,
        budget=Budget(limit_usd=10.0, model="claude-sonnet-5"),
        results=results,
        outcome=verification_module.GateOutcome()
        if hasattr(verification_module, "GateOutcome")
        else None,
        notes=[],
        deferred_reason=None,
        elapsed_s=0.0,
        diff_digest="d" * 64,
    )
    started = time.monotonic()
    verification_module.run_verification_stage(
        repo,
        task_id=task_id,
        repository_id="o/r",
        base_sha=base,
        head_sha=head,
        review=review,
        review_policy_digest="p" * 64,
        config=ReviewConfig(
            probe_generation=False,
            k_samples=1,
            tier0_commands=[],
            repro_concurrency=concurrency,
        ),
        provider=None,
        adapter=LocalDevelopmentAdapter(),
        production=False,
    )
    elapsed = time.monotonic() - started
    rows = [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    return rows, elapsed, max(concurrent)


@dataclass
class _Attempt:
    outcome: str = "rejected"
    reason: str = "stub"
    rejection_codes: tuple[str, ...] = ("not_reproduced",)
    finding: None = None
    bundle: None = None

    def to_ledger_row(self, task_id: str) -> dict[str, object]:
        return {"kind": "certification", "task_id": task_id, "outcome": self.outcome}


def _signature(rows: list[dict]) -> list[tuple[str, str]]:
    return [
        (str(row.get("kind")), str(row.get("finding_id", "")))
        for row in rows
        if row.get("kind") in {"probe_observation", "verification", "certification"}
    ]


def test_the_ledger_order_is_the_same_whether_or_not_reproductions_overlap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serial, serial_elapsed, serial_peak = _run(tmp_path / "serial", monkeypatch, 1)
    parallel, parallel_elapsed, parallel_peak = _run(tmp_path / "parallel", monkeypatch, 2)

    assert serial_peak == 1, "the serial path overlapped two reproductions"
    assert parallel_peak == 2, "the parallel path never overlapped anything"
    assert _signature(serial) == _signature(parallel)
    assert len(_signature(serial)) == CANDIDATES * 3


def test_overlapping_reproductions_take_less_wall_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serial, serial_elapsed, _ = _run(tmp_path / "serial", monkeypatch, 1)
    _parallel, parallel_elapsed, _ = _run(tmp_path / "parallel", monkeypatch, 2)

    assert serial_elapsed >= CANDIDATES * SLEEP_S
    assert parallel_elapsed < serial_elapsed * 0.75


def test_dispatch_follows_the_ranking_even_when_two_are_in_flight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D-111 under D-157: the queue is still the ranked list, so a deadline or
    an exhausted budget still stops at the weakest candidate -- what overlap
    changes is that the *tail* of the budget may be held by a candidate the
    serial path would not yet have started."""
    rows, _elapsed, peak = _run(tmp_path / "ranked", monkeypatch, 2)

    assert peak == 2
    verifications = [row for row in rows if row.get("kind") == "verification"]
    order = [row["finding_id"] for row in verifications]
    ranked = [result.finding.finding_id for result in _results()]
    assert order == ranked, "the journal did not read in wealth order"


def test_concurrency_is_bounded_by_the_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _rows, _elapsed, peak = _run(tmp_path / "three", monkeypatch, 3)
    assert peak == 3

    with pytest.raises(ValueError, match="repro_concurrency"):
        ReviewConfig(repro_concurrency=0)
    with pytest.raises(ValueError, match="repro_concurrency"):
        ReviewConfig(repro_concurrency=9)
