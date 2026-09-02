"""The replay runner drives the real product path and observes only its output."""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Iterator, Mapping
from dataclasses import replace
from pathlib import Path

import pytest

import attest.review.ci as ci_module
from attest.benchmark.api import (
    ProjectEvaluationRequest,
    ProjectTruth,
    _adjudicate_measurement,
    _score,
)
from attest.benchmark.measurement import TaskDeliveryTerminalStatus, reduce_measurements
from attest.benchmark.runner import (
    REPRO_STATUS_BY_EVIDENCE_CLASS,
    BenchmarkRunner,
    Cassette,
    ExecutionResultAuthority,
    LoopbackGitHub,
    ReplayProvider,
    ReproReceipt,
    _deferred_reason_from_rows,
    ci_final_decisions,
    extract_predictions,
    load_cassette,
    rebuild_case_run_from_ledger,
    run_differential_repro,
)
from attest.benchmark.schema import Placement, TruthDefect
from attest.github.client import GitHubApiError, PreparedGitHubWrite
from attest.review.candidates import CandidateStore, StoredCandidate
from attest.review.ci import CiPublicationEvent, reconcile_delivery_rows
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits, ReproSpec
from attest.review.gate import GateResult
from attest.review.ledger import Ledger, ci_final_decisions_from_rows
from attest.review.schema import Finding

CASE_ID = "case-0123456789ab"


class _SwitchingEvidenceClasses(Mapping[str, str]):
    """Return one trusted snapshot, then a different caller-controlled snapshot."""

    def __init__(self, trusted: Mapping[str, str]) -> None:
        self._snapshots = (dict(trusted), {"forged": "caller-controlled"})
        self._active = self._snapshots[0]
        self._reads = 0

    def __iter__(self) -> Iterator[str]:
        self._active = self._snapshots[min(self._reads, 1)]
        self._reads += 1
        return iter(self._active)

    def __len__(self) -> int:
        return len(self._active)

    def __getitem__(self, key: str) -> str:
        return self._active[key]


@pytest.mark.parametrize("field", ("spend_usd", "oracle_spend_usd", "elapsed_s"))
def test_execution_authority_normalizes_negative_zero(
    tmp_path: Path, field: str
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    authority = ExecutionResultAuthority.from_case_run(
        replace(result, **{field: -0.0})
    )

    assert math.copysign(1.0, getattr(authority, field)) == 1.0


def test_taskless_rebuild_rejects_caller_fields_outside_frozen_authority(
    tmp_path: Path,
) -> None:
    from attest.benchmark.measurement import (
        DeliveryStatus,
        StopKind,
        TaskStatus,
        empty_delivery_transcript_receipt,
    )

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    empty_measurement = replace(
        result.measurement,
        stop_kind=StopKind.NONE,
        task_status=TaskStatus.COMPLETED,
        findings=(),
        candidate_count=0,
        published_count=0,
        unresolved_count=0,
        publication_events=(),
        task_delivery_events=(),
        delivery_transcript=empty_delivery_transcript_receipt(),
        delivery_status=DeliveryStatus.NO_PUBLICATION,
    )
    authority = ExecutionResultAuthority(
        measurement=empty_measurement,
        oracle_receipts=(),
        product_evidence_classes=(),
        predictions=(),
        candidate_count=0,
        surfaced_count=0,
        spend_usd=1.0,
        oracle_spend_usd=2.0,
        elapsed_s=3.0,
    )
    caller = replace(
        result,
        task_id=None,
        run=replace(result.run, run_id="taskless", predictions=()),
        candidate_count=0,
        surfaced_count=123,
        spend_usd=999.0,
        oracle_spend_usd=888.0,
        elapsed_s=777.0,
        product_evidence_classes={"x": "y"},
        oracle_receipts=(),
        measurement=empty_measurement,
    )

    with pytest.raises(ValueError, match="fresh outcome.*mismatch"):
        rebuild_case_run_from_ledger(
            repo,
            caller,
            (),
            repository="local/project",
            head_sha=head_sha,
            pull_request_number=1,
            deadline_s=60.0,
            expected_authority=authority,
        )


@pytest.mark.parametrize(
    ("stop_kind", "task_status", "caller_reason", "expected_reason"),
    (
        ("failure", "failed", None, "measurement task status was failed"),
        (
            "task_defer",
            "fully_deferred",
            None,
            "measurement task status was fully_deferred",
        ),
        ("none", "completed", "synthetic caller defer", None),
    ),
)
def test_taskless_rebuild_derives_deferred_reason_from_frozen_measurement(
    tmp_path: Path,
    stop_kind: str,
    task_status: str,
    caller_reason: str | None,
    expected_reason: str | None,
) -> None:
    from attest.benchmark.measurement import (
        DeliveryStatus,
        StopKind,
        TaskStatus,
        empty_delivery_transcript_receipt,
    )

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    measurement = replace(
        result.measurement,
        stop_kind=StopKind(stop_kind),
        task_status=TaskStatus(task_status),
        findings=(),
        candidate_count=0,
        published_count=0,
        unresolved_count=0,
        publication_events=(),
        task_delivery_events=(),
        delivery_transcript=empty_delivery_transcript_receipt(),
        delivery_status=DeliveryStatus.NO_PUBLICATION,
    )
    authority = ExecutionResultAuthority(
        measurement=measurement,
        oracle_receipts=(),
        product_evidence_classes=(),
        predictions=(),
        candidate_count=0,
        surfaced_count=0,
        spend_usd=1.0,
        oracle_spend_usd=2.0,
        elapsed_s=3.0,
    )
    caller = replace(
        result,
        task_id=None,
        run=replace(
            result.run,
            run_id="taskless",
            predictions=(),
            delivery_at_s=None,
        ),
        candidate_count=0,
        surfaced_count=0,
        deferred_reason=caller_reason,
        delivered=False,
        spend_usd=1.0,
        oracle_spend_usd=2.0,
        elapsed_s=3.0,
        product_evidence_classes={},
        oracle_receipts=(),
        measurement=measurement,
    )

    rebuilt = rebuild_case_run_from_ledger(
        repo,
        caller,
        (),
        repository="local/project",
        head_sha=head_sha,
        pull_request_number=1,
        deadline_s=60.0,
        expected_authority=authority,
    )

    assert rebuilt.deferred_reason == expected_reason


def test_fresh_rebuild_replaces_stateful_caller_mappings_with_frozen_values(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    authority = ExecutionResultAuthority.from_case_run(result)
    trusted = dict(result.product_evidence_classes)
    caller = replace(
        result,
        product_evidence_classes=_SwitchingEvidenceClasses(trusted),
    )

    rebuilt = rebuild_case_run_from_ledger(
        repo,
        caller,
        Ledger(repo).entries_strict(),
        repository="local/project",
        head_sha=head_sha,
        pull_request_number=1,
        deadline_s=60.0,
        expected_authority=authority,
    )

    assert type(rebuilt.product_evidence_classes) is dict
    assert rebuilt.product_evidence_classes == trusted
    assert rebuilt.scored_payload()["product_evidence_classes"] == trusted


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def regression_repo(root: Path) -> tuple[Path, str, str]:
    """A repository whose head deletes an empty-input guard its base had."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "fixture@example.invalid")
    git(root, "config", "user.name", "Fixture")
    (root / "app.py").write_text(
        "def average(items):\n"
        "    if not items:\n"
        "        return 0\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    git(root, "add", "app.py")
    git(root, "commit", "-m", "guarded")
    base_sha = git(root, "rev-parse", "HEAD")
    (root / "app.py").write_text(
        "def average(items):\n    return sum(items) / len(items)\n", encoding="utf-8"
    )
    git(root, "add", "app.py")
    git(root, "commit", "-m", "drop the guard")
    return root, base_sha, git(root, "rev-parse", "HEAD")


PROPOSAL = json.dumps(
    {
        "findings": [
            {
                "claim": "average() divides by zero when items is empty.",
                "anchor": {"file": "app.py", "line": 2},
                "failure_scenario": "average([]) raises ZeroDivisionError",
                "falsification_plan": "call average([]) and require a safe empty result",
            }
        ]
    }
)

REPRO = json.dumps(
    {
        "test_body": "import runpy\n\n"
        "def test_average_handles_empty_input():\n"
        "    average = runpy.run_path('app.py')['average']\n"
        "    assert average([]) == 0\n"
    }
)


def cassette() -> Cassette:
    return Cassette(proposal=PROPOSAL, repro=REPRO, input_tokens=1200, output_tokens=340)


def stored_candidate(task_id: str = "benchmark-task") -> StoredCandidate:
    finding = Finding(
        claim="average() divides by zero when items is empty.",
        file="app.py",
        line=2,
        failure_scenario="average([]) raises ZeroDivisionError",
        falsification_plan="call average([]) and require a safe empty result",
        votes=2,
        sample_ids=[0, 1],
    )
    return StoredCandidate(
        task_id=task_id, finding=finding, wealth=3.0, action="drawer", alpha=0.1
    )


def test_replay_runner_drives_the_real_review_gate_executor_and_ledger(tmp_path: Path) -> None:
    """Only the model is replayed: gate, executor, ledger and delivery are real."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    runner = BenchmarkRunner(limits=ExecutorLimits(wall_timeout_s=30.0), repeats=1)

    with LoopbackGitHub() as github:
        result = runner.run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
            fixed_sha=base_sha,
        )
        delivered = list(github.review_comments)

    assert result.case_id == CASE_ID
    assert result.task_id
    rows = Ledger(repo).entries()
    assert {row["task_id"] for row in rows if row.get("kind") == "ci_final"} == {result.task_id}

    assert result.candidate_count == 1
    assert result.surfaced_count == 1
    assert result.deferred_reason is None
    assert result.spend_usd > 0

    verification = next(row for row in rows if row["kind"] == "verification")
    assert verification["outcome"] == "reproduced"
    assert verification["evidence_class"] == "regression_reproduced"
    assert result.product_evidence_classes[verification["finding_id"]] == (
        "regression_reproduced"
    )

    prediction = result.run.predictions[0]
    assert prediction.case_id == CASE_ID
    assert prediction.file == "app.py"
    assert prediction.placement is Placement.INLINE
    assert prediction.action == "surface"
    assert prediction.repro_status == "buggy_fail_fixed_pass"
    assert prediction.evidence_class == "regression_reproduced"

    receipt = result.oracle_receipts[0]
    assert receipt.finding_id == prediction.finding_id
    assert receipt.buggy_sha == head_sha
    assert receipt.fixed_sha == base_sha
    assert receipt.confirmed is True

    assert len(delivered) == 1
    assert "average() divides by zero" in delivered[0]["body"]
    assert result.run.delivery_at_s is not None


def test_replay_report_preserves_generation_defer_reason_from_ledger(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    invalid_repro = replace(cassette(), repro="{}")

    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(invalid_repro),
            client=github.client(),
        )

    assert result.deferred_reason is not None
    assert "verification deferred: generation failed: ValueError" in result.deferred_reason
    assert 'raw="{}"' in result.deferred_reason


def test_deferred_reason_reports_each_verification_cause() -> None:
    task_id = "task-mixed-defer"
    rows = [
        {
            "kind": "verification",
            "task_id": task_id,
            "outcome": "deferred",
            "reason": reason,
        }
        for reason in ("child process blocked", "schema invalid", "child process blocked")
    ]

    reason = _deferred_reason_from_rows(
        rows,
        task_id,
        TaskDeliveryTerminalStatus.DEFERRED,
    )

    assert reason == (
        "verification deferred: child process blocked (2 candidates); "
        "schema invalid (1 candidate)"
    )


def test_overflow_surfaces_are_extracted_as_scored_predictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A surfaced finding beyond the formatting cap is still visible, so it is scored."""
    from attest.review import tier0
    from attest.review.tier0 import Tier0Signal

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    # both defects are regressions: the guards exist at base and vanish at head
    git(repo, "checkout", "-q", "--detach", base_sha)
    (repo / "app.py").write_text(
        "def average(items):\n"
        "    if not items:\n"
        "        return 0\n"
        "    return sum(items) / len(items)\n\n\n"
        "# helpers below\n\n\n"
        "def ratio(a, b):\n"
        "    if b == 0:\n"
        "        return 0\n"
        "    return a / b\n",
        encoding="utf-8",
    )
    git(repo, "add", "app.py")
    git(repo, "commit", "-m", "guarded ratio alongside guarded average")
    base_sha = git(repo, "rev-parse", "HEAD")
    (repo / "app.py").write_text(
        "def average(items):\n"
        "    return sum(items) / len(items)\n\n\n"
        "# helpers below\n\n\n"
        "def ratio(a, b):\n"
        "    return a / b\n",
        encoding="utf-8",
    )
    git(repo, "add", "app.py")
    git(repo, "commit", "-m", "drop both guards")
    head_sha = git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(
        tier0,
        "run_ruff",
        lambda _repo, _files: [
            Tier0Signal("ruff", "app.py", 1, "first corroborating signal"),
            Tier0Signal("ruff", "app.py", 2, "second corroborating signal"),
            Tier0Signal("ruff", "app.py", 8, "third corroborating signal"),
            Tier0Signal("ruff", "app.py", 9, "fourth corroborating signal"),
        ],
    )
    proposal = json.dumps(
        {
            "findings": [
                {
                    "claim": "average() divides by zero when items is empty.",
                    "anchor": {"file": "app.py", "line": 2},
                    "failure_scenario": "average([]) raises ZeroDivisionError",
                    "falsification_plan": "call average([]) and require an empty result",
                },
                {
                    "claim": "ratio() divides by zero when b is zero.",
                    "anchor": {"file": "app.py", "line": 8},
                    "failure_scenario": "ratio(1, 0) raises ZeroDivisionError",
                    "falsification_plan": "call ratio(1, 0) and require a guarded result",
                },
            ]
        }
    )
    runner = BenchmarkRunner(repeats=1)

    with LoopbackGitHub() as github:
        result = runner.run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(alpha=0.15, k_samples=2, max_findings=1),
            provider=ReplayProvider(Cassette(proposal=proposal, repro=REPRO)),
            client=github.client(),
        )

    placements = sorted(
        (prediction.placement.value, prediction.action) for prediction in result.run.predictions
    )
    assert placements == [("inline", "surface"), ("overflow", "surface")]
    assert result.surfaced_count == 2


def test_identical_cassettes_produce_identical_scored_output(tmp_path: Path) -> None:
    """Replay regression: the same cassette scores identically, timestamps excluded."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    payloads = []
    results = []
    for _ in range(2):
        with LoopbackGitHub() as github:
            result = BenchmarkRunner(
                limits=ExecutorLimits(wall_timeout_s=30.0), repeats=1
            ).run_case(
                repo,
                case_id=CASE_ID,
                base_sha=base_sha,
                head_sha=head_sha,
                config=ReviewConfig(k_samples=2, tier0_commands=[]),
                provider=ReplayProvider(cassette()),
                client=github.client(),
                fixed_sha=base_sha,
            )
        payloads.append(result.scored_payload())
        results.append(result)

    from attest.benchmark.measurement import decode_measurement_record

    assert [payload["schema_version"] for payload in payloads] == [2, 2]
    assert [
        decode_measurement_record(payload["measurement"])
        for payload in payloads
    ] == [result.measurement for result in results]
    assert (
        payloads[0]["semantic_measurement_sha256"]
        == payloads[1]["semantic_measurement_sha256"]
    )
    assert "task_id" not in payloads[0]
    assert "elapsed_s" not in payloads[0]


def test_cassettes_are_loaded_from_disk_and_never_reach_the_network(tmp_path: Path) -> None:
    """A replay provider answers from recorded bytes; a missing recording fails closed."""
    root = tmp_path / "cassettes"
    root.mkdir()
    (root / f"{CASE_ID}.json").write_text(
        json.dumps(
            {"proposal": PROPOSAL, "repro": REPRO, "input_tokens": 5, "output_tokens": 7}
        ),
        encoding="utf-8",
    )

    loaded = load_cassette(root, CASE_ID)
    assert loaded == Cassette(proposal=PROPOSAL, repro=REPRO, input_tokens=5, output_tokens=7)

    provider = ReplayProvider(loaded)
    proposal = provider.sample("You are a code reviewer", "diff", {}, 100)
    repro = provider.sample("Write one focused pytest reproduction", "claim", {}, 100)
    assert proposal.text == PROPOSAL
    assert repro.text == REPRO
    assert proposal.input_tokens == 5

    with pytest.raises(ValueError, match="cassette"):
        load_cassette(root, "case-ffffffffffff")
    (root / "case-aaaaaaaaaaaa.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="cassette"):
        load_cassette(root, "case-aaaaaaaaaaaa")


def test_predictions_join_candidate_rows_to_the_authoritative_ci_final(
    tmp_path: Path,
) -> None:
    """Placement comes from ci_final, anchors come from the candidate store."""
    repo = tmp_path / "project"
    repo.mkdir()
    candidate = stored_candidate("task-1")
    CandidateStore(repo).append(
        "task-1", 0.1, [GateResult(finding=candidate.finding, wealth=12.0, decision=1)]
    )
    Ledger(repo).record_ci_final(
        task_id="task-1",
        decisions=[
            {
                "finding_id": candidate.finding.finding_id,
                "action": "surface",
                "wealth_final": 12.0,
                "placement": "overflow",
            }
        ],
        spend_usd=0.01,
    )
    Ledger(repo).append(
        {
            "kind": "publication_event",
            "task_id": "task-1",
            "event_id": "github:101:status:one",
            "finding_id": candidate.finding.finding_id,
            "placement": "overflow",
            "channel": "status_summary",
            "outcome": "succeeded",
            "delivered_at_s": 1.0,
        }
    )

    predictions = extract_predictions(
        repo,
        task_id="task-1",
        case_id=CASE_ID,
        repro_status={candidate.finding.finding_id: "buggy_fail_fixed_pass"},
        evidence_class={candidate.finding.finding_id: "regression_reproduced"},
        publication_events=(
            CiPublicationEvent(
                event_id="e" * 64,
                attempt_id="a" * 64,
                attempt_ordinal=0,
                repository="local/project",
                pull_request_number=1,
                head_sha="1" * 40,
                channel="status_summary",
                members=((candidate.finding.finding_id, "overflow"),),
                body_sha256="b" * 64,
                request_sha256="c" * 64,
                outcome="succeeded",
                remote_response_id="101",
                delivered_at_s=1.0,
                deadline_s=60.0,
            ),
        ),
    )

    assert len(predictions) == 1
    assert predictions[0].placement is Placement.OVERFLOW
    assert predictions[0].action == "surface"
    assert predictions[0].line == 2
    assert predictions[0].repro_status == "buggy_fail_fixed_pass"
    assert predictions[0].evidence_class == "regression_reproduced"

    assert extract_predictions(repo, task_id="task-2", case_id=CASE_ID) == ()


@pytest.mark.parametrize("mutation", ["unknown", "duplicate"])
def test_prediction_join_rejects_unknown_or_duplicate_ci_final_ids(
    tmp_path: Path, mutation: str
) -> None:
    """A caller cannot hide malformed final decisions behind a partial join."""
    repo = tmp_path / "project"
    repo.mkdir()
    candidate = stored_candidate("task-1")
    CandidateStore(repo).append(
        "task-1", 0.1, [GateResult(finding=candidate.finding, wealth=12.0, decision=1)]
    )
    decision = {
        "finding_id": candidate.finding.finding_id,
        "action": "surface",
        "wealth_final": 12.0,
        "placement": "inline",
    }
    decisions = (
        [{**decision, "finding_id": "unknown-finding"}]
        if mutation == "unknown"
        else [decision, dict(decision)]
    )
    Ledger(repo).record_ci_final(
        task_id="task-1",
        decisions=decisions,
        spend_usd=0.01,
    )

    with pytest.raises(ValueError, match="unknown|duplicate"):
        extract_predictions(repo, task_id="task-1", case_id=CASE_ID)


def test_prediction_join_rejects_a_delivered_non_surface_decision(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "project"
    repo.mkdir()
    candidate = stored_candidate("task-1")
    CandidateStore(repo).append(
        "task-1", 0.1, [GateResult(finding=candidate.finding, wealth=3.0, decision=None)]
    )
    Ledger(repo).record_ci_final(
        task_id="task-1",
        decisions=[
            {
                "finding_id": candidate.finding.finding_id,
                "action": "drawer",
                "wealth_final": 3.0,
                "placement": "drawer",
            }
        ],
        spend_usd=0.01,
    )
    publication = CiPublicationEvent(
        event_id="e" * 64,
        attempt_id="a" * 64,
        attempt_ordinal=0,
        repository="local/project",
        pull_request_number=1,
        head_sha="1" * 40,
        channel="status_summary",
        members=((candidate.finding.finding_id, "drawer"),),
        body_sha256="b" * 64,
        request_sha256="c" * 64,
        outcome="succeeded",
        remote_response_id="101",
        delivered_at_s=1.0,
        deadline_s=60.0,
    )

    with pytest.raises(ValueError, match="surface decision"):
        extract_predictions(
            repo,
            task_id="task-1",
            case_id=CASE_ID,
            publication_events=(publication,),
        )


@pytest.mark.parametrize(
    ("action", "placement"),
    (
        ("surface", "drawer"),
        ("drawer", "inline"),
        ("discard", "overflow"),
    ),
)
def test_ci_final_rejects_action_placement_mismatches_before_measurement(
    tmp_path: Path, action: str, placement: str
) -> None:
    repo = tmp_path / "project"
    repo.mkdir()
    Ledger(repo).record_ci_final(
        task_id="task-1",
        decisions=[
            {
                "finding_id": "finding-1",
                "action": action,
                "wealth_final": 12.0,
                "placement": placement,
            }
        ],
        spend_usd=0.01,
    )

    with pytest.raises(ValueError, match="action|placement"):
        ci_final_decisions(repo, "task-1")


@pytest.mark.parametrize(
    "mutation",
    ("missing_ts", "extra_field", "invalid_spend", "negative_elapsed"),
)
def test_ci_final_rejects_malformed_outer_rows_before_measurement(mutation: str) -> None:
    row: dict[str, object] = {
        "ts": "2026-08-31T00:00:00Z",
        "kind": "ci_final",
        "task_id": "task-1",
        "decisions": [
            {
                "finding_id": "finding-1",
                "action": "surface",
                "wealth_final": 12.0,
                "placement": "inline",
            }
        ],
        "spend_usd": 0.01,
    }
    if mutation == "missing_ts":
        del row["ts"]
    elif mutation == "extra_field":
        row["forged"] = True
    elif mutation == "invalid_spend":
        row["spend_usd"] = "free"
    else:
        row["elapsed_s"] = -1.0

    with pytest.raises(ValueError, match="ci_final|spend|elapsed"):
        ci_final_decisions_from_rows([row], "task-1")


def test_failed_publication_is_not_author_visible_measurement(tmp_path: Path) -> None:
    """Planned ci_final placement is not proof that an API publication succeeded."""

    class FailedPublicationClient:
        def __init__(self) -> None:
            self.status_calls = 0

        def upsert_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> dict[str, object]:
            self.status_calls += 1
            if self.status_calls > 2:
                raise GitHubApiError("forced status failure")
            return {"id": 1}

        def create_review(
            self,
            repository: str,
            number: int,
            commit_id: str,
            comments: list[dict[str, object]],
        ) -> dict[str, object]:
            raise GitHubApiError("forced review failure")

        def prepare_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> PreparedGitHubWrite:
            return PreparedGitHubWrite(
                method="POST",
                path=f"/repos/{repository}/issues/{number}/comments",
                payload={"body": f"{marker}\n{body}"},
            )

        def execute_prepared_write(
            self, request: PreparedGitHubWrite
        ) -> dict[str, object]:
            self.status_calls += 1
            if self.status_calls > 2:
                raise GitHubApiError("forced status failure")
            return {"id": self.status_calls}

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    result = BenchmarkRunner(repeats=1).run_case(
        repo,
        case_id=CASE_ID,
        base_sha=base_sha,
        head_sha=head_sha,
        config=ReviewConfig(k_samples=2, tier0_commands=[]),
        provider=ReplayProvider(cassette()),
        client=FailedPublicationClient(),  # type: ignore[arg-type]
    )

    assert result.deferred_reason is not None
    final = next(row for row in Ledger(repo).entries() if row.get("kind") == "ci_final")
    assert any(
        decision.get("placement") in {"inline", "overflow"}
        for decision in final["decisions"]
    )
    assert result.run.predictions == ()
    assert result.measurement.published_count == 0
    assert result.measurement.delivery_status.value == "no_publication"
    assert result.measurement.metrics_withheld_reason == "ambiguous_publication"
    assert result.measurement.delivery_withheld_reason == "ambiguous_publication"
    assert Ledger(repo).surfaced_finding_ids() == ()


def test_ci_final_without_delivery_authority_is_not_a_surface(tmp_path: Path) -> None:
    ledger = Ledger(tmp_path)
    ledger.record_ci_final(
        task_id="task-crashed-before-delivery",
        decisions=[
            {
                "finding_id": "planned",
                "action": "surface",
                "wealth_final": 40.0,
                "placement": "inline",
            }
        ],
        spend_usd=0.01,
    )

    assert ledger.surfaced_finding_ids() == ()


def test_non_integer_github_response_identity_is_ambiguous(tmp_path: Path) -> None:
    class InvalidIdentityClient:
        def upsert_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> dict[str, object]:
            return {"id": 1}

        def create_review(
            self,
            repository: str,
            number: int,
            commit_id: str,
            comments: list[dict[str, object]],
        ) -> dict[str, object]:
            return {"id": " "}

        def prepare_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> PreparedGitHubWrite:
            return PreparedGitHubWrite(
                method="POST",
                path=f"/repos/{repository}/issues/{number}/comments",
                payload={"body": f"{marker}\n{body}"},
            )

        def execute_prepared_write(
            self, request: PreparedGitHubWrite
        ) -> dict[str, object]:
            return {"id": " "}

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    result = BenchmarkRunner(repeats=1).run_case(
        repo,
        case_id=CASE_ID,
        base_sha=base_sha,
        head_sha=head_sha,
        config=ReviewConfig(k_samples=2, tier0_commands=[]),
        provider=ReplayProvider(cassette()),
        client=InvalidIdentityClient(),  # type: ignore[arg-type]
    )

    assert result.measurement.publication_events
    assert all(
        event.outcome.value == "ambiguous"
        and event.remote_response_id is None
        for event in result.measurement.publication_events
    )


def test_definitive_review_rejection_then_defer_summary_success_is_visible(
    tmp_path: Path,
) -> None:
    class RejectedReviewClient:
        def __init__(self) -> None:
            self.status_calls = 0

        def upsert_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> dict[str, object]:
            self.status_calls += 1
            return {"id": self.status_calls}

        def create_review(
            self,
            repository: str,
            number: int,
            commit_id: str,
            comments: list[dict[str, object]],
        ) -> dict[str, object]:
            raise GitHubApiError(
                "forced HTTP 422 rejection", definitive_rejection=True
            )

        def prepare_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> PreparedGitHubWrite:
            return PreparedGitHubWrite(
                method="POST",
                path=f"/repos/{repository}/issues/{number}/comments",
                payload={"body": f"{marker}\n{body}"},
            )

        def execute_prepared_write(
            self, request: PreparedGitHubWrite
        ) -> dict[str, object]:
            self.status_calls += 1
            return {"id": self.status_calls}

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    result = BenchmarkRunner(repeats=1).run_case(
        repo,
        case_id=CASE_ID,
        base_sha=base_sha,
        head_sha=head_sha,
        config=ReviewConfig(k_samples=2, tier0_commands=[]),
        provider=ReplayProvider(cassette()),
        client=RejectedReviewClient(),  # type: ignore[arg-type]
    )

    assert result.deferred_reason is not None
    assert result.measurement.task_status.value == "failed"
    assert result.measurement.published_count == 1
    assert result.measurement.unresolved_count == 0
    assert result.measurement.metrics_withheld_reason is None
    assert tuple(event.outcome.value for event in result.measurement.publication_events) == (
        "failed",
        "succeeded",
    )
    assert result.measurement.task_delivered is True


def test_inline_success_survives_a_failed_final_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful inline members remain visible; an unposted overflow does not."""
    from attest.review import tier0
    from attest.review.tier0 import Tier0Signal

    class InlineOnlyClient:
        def __init__(self) -> None:
            self.status_calls = 0

        def upsert_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> dict[str, object]:
            self.status_calls += 1
            if self.status_calls > 2:
                raise GitHubApiError("forced final-summary failure")
            return {"id": self.status_calls}

        def create_review(
            self,
            repository: str,
            number: int,
            commit_id: str,
            comments: list[dict[str, object]],
        ) -> dict[str, object]:
            assert len(comments) == 1
            return {"id": 202}

        def prepare_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> PreparedGitHubWrite:
            return PreparedGitHubWrite(
                method="POST",
                path=f"/repos/{repository}/issues/{number}/comments",
                payload={"body": f"{marker}\n{body}"},
            )

        def execute_prepared_write(
            self, request: PreparedGitHubWrite
        ) -> dict[str, object]:
            self.status_calls += 1
            if self.status_calls > 2:
                raise GitHubApiError("forced final-summary failure")
            return {"id": self.status_calls}

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    monkeypatch.setattr(
        tier0,
        "run_ruff",
        lambda _repo, _files: [
            Tier0Signal("ruff", "app.py", 1, "first"),
            Tier0Signal("ruff", "app.py", 2, "second"),
            Tier0Signal("ruff", "app.py", 3, "third"),
            Tier0Signal("ruff", "app.py", 4, "fourth"),
        ],
    )
    proposal = json.dumps(
        {
            "findings": [
                {
                    "claim": "average() divides by zero for empty input.",
                    "anchor": {"file": "app.py", "line": 1},
                    "failure_scenario": "empty input",
                    "falsification_plan": "call average([])",
                },
                {
                    "claim": "average() cannot process a vacant collection.",
                    "anchor": {"file": "app.py", "line": 2},
                    "failure_scenario": "vacant collection",
                    "falsification_plan": "evaluate a vacant collection",
                },
            ]
        }
    )

    result = BenchmarkRunner(repeats=1).run_case(
        repo,
        case_id=CASE_ID,
        base_sha=base_sha,
        head_sha=head_sha,
        config=ReviewConfig(alpha=0.15, k_samples=2, max_findings=1),
        provider=ReplayProvider(Cassette(proposal=proposal, repro=REPRO)),
        client=InlineOnlyClient(),  # type: ignore[arg-type]
    )

    assert result.deferred_reason is not None
    assert tuple(prediction.placement.value for prediction in result.run.predictions) == (
        "inline",
    )
    assert result.measurement.published_count == 1
    assert result.measurement.unresolved_count == 1
    assert result.measurement.metrics_withheld_reason == "ambiguous_publication"
    assert result.measurement.delivery_withheld_reason == "ambiguous_publication"
    assert result.measurement.task_delivery_withheld_reason == (
        "ambiguous_task_delivery"
    )
    assert result.run.delivery_at_s is None
    assert any(
        event.channel.value == "inline_review" and event.succeeded
        for event in result.measurement.publication_events
    )
    assert any(
        any(member.placement.value == "overflow" for member in event.members)
        and not event.succeeded
        for event in result.measurement.publication_events
    )
    prediction = result.run.predictions[0]
    request = ProjectEvaluationRequest(
        case_id=CASE_ID,
        repo=repo,
        base_ref=base_sha,
        head_ref=head_sha,
        workspace_root=tmp_path / "adjudication",
        truth=ProjectTruth(
            defects=(
                TruthDefect(
                    defect_id="truth-1",
                    case_id=CASE_ID,
                    file=prediction.file,
                    start_line=prediction.line,
                    end_line=prediction.line,
                ),
            ),
            fixed_ref=base_sha,
        ),
    )
    measurement = _adjudicate_measurement(
        request, result.measurement, result.run.predictions
    )
    assert reduce_measurements((measurement,)).metrics_withheld_reason == (
        "ambiguous_publication"
    )
    assert _score(measurement) is None


def test_inline_success_survives_final_status_prepare_read_failure(
    tmp_path: Path,
) -> None:
    class PrepareFailureClient:
        def upsert_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> dict[str, object]:
            return {"id": 101}

        def create_review(
            self,
            repository: str,
            number: int,
            commit_id: str,
            comments: list[dict[str, object]],
        ) -> dict[str, object]:
            return {"id": 202}

        def prepare_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> object:
            raise GitHubApiError("forced final status lookup failure")

        def execute_prepared_write(self, request: object) -> dict[str, object]:
            raise AssertionError("a failed prepare must not produce a write attempt")

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    result = BenchmarkRunner(repeats=1).run_case(
        repo,
        case_id=CASE_ID,
        base_sha=base_sha,
        head_sha=head_sha,
        config=ReviewConfig(k_samples=2, tier0_commands=[]),
        provider=ReplayProvider(cassette()),
        client=PrepareFailureClient(),  # type: ignore[arg-type]
    )

    assert result.deferred_reason is not None
    assert "lookup failure" in result.deferred_reason
    assert result.measurement.published_count == 1
    assert tuple(
        event.channel.value for event in result.measurement.publication_events
    ) == ("inline_review",)
    assert result.measurement.task_delivery_events == ()


def test_status_delivery_requires_an_exact_prepared_write_protocol() -> None:
    from attest.github.context import PullRequestContext
    from attest.review.ci import _prepare_status_delivery

    context = PullRequestContext(
        repository="local/project",
        number=1,
        base_sha="0" * 40,
        head_sha="1" * 40,
        is_fork=False,
    )

    with pytest.raises(GitHubApiError, match="prepared|protocol"):
        _prepare_status_delivery(object(), context, "Review complete.")  # type: ignore[arg-type]


def test_status_delivery_rejects_malicious_prepared_write_before_dispatch() -> None:
    from attest.github.context import PullRequestContext
    from attest.review.ci import _prepare_status_delivery

    class MaliciousPreparedClient:
        def __init__(self) -> None:
            self.execute_calls = 0

        def prepare_issue_comment(
            self, repository: str, number: int, marker: str, body: str
        ) -> PreparedGitHubWrite:
            return PreparedGitHubWrite(
                method="DELETE",
                path=f"/repos/{repository}/issues/17",
                payload={"body": "wrong body"},
            )

        def execute_prepared_write(
            self, request: PreparedGitHubWrite
        ) -> dict[str, object]:
            self.execute_calls += 1
            return {"id": 17}

    context = PullRequestContext(
        repository="local/project",
        number=1,
        base_sha="0" * 40,
        head_sha="1" * 40,
        is_fork=False,
    )
    client = MaliciousPreparedClient()

    with pytest.raises(GitHubApiError, match="prepared|method|path|payload"):
        _prepare_status_delivery(  # type: ignore[arg-type]
            client, context, "Review complete."
        )
    assert client.execute_calls == 0


def test_legacy_run_record_withholds_ambiguous_task_delivery_point_estimate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from attest.review.ci import CiDeliveryTranscript, CiRun, CiTaskDeliveryEvent

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    common = {
        "repository": "local/project",
        "pull_request_number": 1,
        "head_sha": head_sha,
        "channel": "status_summary",
        "members": (),
        "terminal_status": "completed",
        "deadline_s": 60.0,
    }
    ambiguous = CiTaskDeliveryEvent(
        event_id="task:ambiguous",
        attempt_id="attempt:ambiguous",
        attempt_ordinal=0,
        body_sha256="a" * 64,
        request_sha256="b" * 64,
        outcome="ambiguous",
        remote_response_id=None,
        delivered_at_s=None,
        **common,
    )
    success = CiTaskDeliveryEvent(
        event_id="task:success",
        attempt_id="attempt:success",
        attempt_ordinal=1,
        body_sha256="c" * 64,
        request_sha256="d" * 64,
        outcome="succeeded",
        remote_response_id="102",
        delivered_at_s=70.0,
        **common,
    )
    task_id = "task-synthetic-ambiguous-delivery"
    transcript = CiDeliveryTranscript(
        schema_version=1,
        protocol="attest.delivery-transcript.v1",
        task_id=task_id,
        expected_attempt_count=2,
        last_attempt_ordinal=1,
        transcript_sha256="e" * 64,
    )
    monkeypatch.setattr(
        "attest.benchmark.runner.run_ci",
        lambda *args, **kwargs: CiRun(
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=None,
            spend_usd=0.0,
            elapsed_s=1.0,
            task_delivery_events=(ambiguous, success),
            delivery_transcript=transcript,
        ),
    )

    result = BenchmarkRunner(repeats=1).run_case(
        repo,
        case_id=CASE_ID,
        base_sha=base_sha,
        head_sha=head_sha,
        config=ReviewConfig(k_samples=2, tier0_commands=[]),
        provider=ReplayProvider(cassette()),
        client=object(),  # type: ignore[arg-type]
        deadline_s=60.0,
    )

    assert result.measurement.task_delivery_withheld_reason == (
        "ambiguous_task_delivery"
    )
    assert result.run.delivery_at_s is None
    assert result.delivered is False


def test_runner_rejects_a_non_exact_delivery_transcript_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from types import SimpleNamespace

    from attest.review.ci import CiRun

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    task_id = "task-forged-transcript"
    forged = SimpleNamespace(
        schema_version=999,
        protocol="evil",
        task_id=task_id,
        expected_attempt_count=0,
        last_attempt_ordinal=None,
        transcript_sha256="e" * 64,
    )
    monkeypatch.setattr(
        "attest.benchmark.runner.run_ci",
        lambda *args, **kwargs: CiRun(
            task_id=task_id,
            candidate_count=0,
            surfaced_count=0,
            deferred_reason=None,
            spend_usd=0.0,
            elapsed_s=1.0,
            delivery_transcript=forged,  # type: ignore[arg-type]
        ),
    )

    with pytest.raises(ValueError, match="exact.*transcript|schema|protocol"):
        BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=object(),  # type: ignore[arg-type]
        )


def test_inline_event_names_only_the_three_comments_actually_sent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from attest.review import tier0
    from attest.review.tier0 import Tier0Signal

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    # four regressions across four files: guarded at base, unguarded at head
    git(repo, "checkout", "-q", "--detach", base_sha)
    for index in range(4):
        (repo / f"module_{index}.py").write_text(
            f"def defect_{index}(items):\n    if not items:\n        return 0\n"
            f"    return {index} / len(items)\n",
            encoding="utf-8",
        )
    git(repo, "add", *[f"module_{index}.py" for index in range(4)])
    git(repo, "commit", "-m", "four guarded modules")
    base_sha = git(repo, "rev-parse", "HEAD")
    (repo / "app.py").write_text(
        "def average(items):\n    return sum(items) / len(items)\n", encoding="utf-8"
    )
    for index in range(4):
        (repo / f"module_{index}.py").write_text(
            f"def defect_{index}(items):\n    return {index} / len(items)\n", encoding="utf-8"
        )
    git(repo, "add", "app.py", *[f"module_{index}.py" for index in range(4)])
    git(repo, "commit", "-m", "drop every guard")
    head_sha = git(repo, "rev-parse", "HEAD")
    monkeypatch.setattr(
        tier0,
        "run_ruff",
        lambda _repo, _files: [
            Tier0Signal("ruff", f"module_{index}.py", 1, f"signal {index}")
            for index in range(4)
        ],
    )
    proposal = json.dumps(
        {
            "findings": [
                    {
                        "claim": f"Distinct empty-input defect {index}.",
                        "anchor": {"file": f"module_{index}.py", "line": 1},
                    "failure_scenario": f"empty input path {index}",
                    "falsification_plan": f"exercise empty input path {index}",
                }
                for index in range(4)
            ]
        }
    )

    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(alpha=0.15, k_samples=2, max_findings=4),
            provider=ReplayProvider(Cassette(proposal=proposal, repro=REPRO)),
            client=github.client(),
        )
        assert len(github.review_comments) == 3

    review_event = next(
        event
        for event in result.measurement.publication_events
        if event.channel.value == "inline_review"
    )
    summary_event = next(
        event
        for event in result.measurement.publication_events
        if event.channel.value == "status_summary"
    )
    assert len(review_event.members) == 3
    assert len(summary_event.members) == 4
    assert sum(
        member.placement.value == "overflow" for member in summary_event.members
    ) == 1
    assert result.measurement.published_count == 4
    assert len({prediction.finding_id for prediction in result.run.predictions}) == 4


def test_silent_complete_retains_task_delivery_without_a_finding_publication(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")

    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(Cassette(proposal='{"findings": []}', repro="{}")),
            client=github.client(),
        )

    assert result.deferred_reason is None
    assert result.run.delivery_at_s is not None
    assert result.measurement.published_count == 0
    assert result.measurement.publication_events == ()
    assert len(result.measurement.task_delivery_events) == 1
    assert result.measurement.task_delivery_events[0].outcome.value == "succeeded"
    assert result.measurement.task_delivered is True
    from attest.benchmark.measurement import reduce_measurements

    summary = reduce_measurements((result.measurement,))
    assert summary.task_delivered == 1
    assert summary.published == 0
    assert summary.finding_precision is None


def test_delivery_ledger_reconciliation_is_exact_and_fail_closed(tmp_path: Path) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")

    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = Ledger(repo).entries()
    publications, task_deliveries = reconcile_delivery_rows(rows, result.task_id)
    assert len(publications) == 2
    assert len(task_deliveries) == 1
    intents = [row for row in rows if row.get("kind") == "delivery_attempt_intent"]
    assert [row["attempt_ordinal"] for row in intents] == [0, 1]
    assert all(isinstance(row.get("request"), dict) for row in intents)
    assert all("Finding ID:" in json.dumps(row["request"]) for row in intents)
    review_intent = next(row for row in intents if row["channel"] == "inline_review")
    summary_intent = next(row for row in intents if row["channel"] == "status_summary")
    wire_review = next(
        request["body"]
        for request in github.requests
        if str(request["path"]).endswith("/reviews")
    )
    wire_summary = [
        request["body"]
        for request in github.requests
        if request["method"] in {"POST", "PATCH"}
        and "/comments" in str(request["path"])
    ][-1]
    assert review_intent["request"]["body"] == wire_review
    assert summary_intent["request"]["body"] == wire_summary
    review_wire_request = next(
        request
        for request in github.requests
        if str(request["path"]).endswith("/reviews")
    )
    summary_wire_request = [
        request
        for request in github.requests
        if request["method"] in {"POST", "PATCH"}
        and "/comments" in str(request["path"])
    ][-1]
    assert (review_intent["request"]["method"], review_intent["request"]["path"]) == (
        review_wire_request["method"],
        review_wire_request["path"],
    )
    assert (summary_intent["request"]["method"], summary_intent["request"]["path"]) == (
        summary_wire_request["method"],
        summary_wire_request["path"],
    )

    first_attempt_id = str(intents[0]["attempt_id"])
    intent_only = [
        row
        for row in rows
        if not (
            row.get("kind") == "delivery_attempt_settlement"
            and row.get("attempt_id") == first_attempt_id
        )
    ]
    with pytest.raises(ValueError, match="transcript|finalization"):
        reconcile_delivery_rows(intent_only, result.task_id)

    orphan = [
        row
        for row in rows
        if not (
            row.get("kind") == "delivery_attempt_intent"
            and row.get("attempt_id") == first_attempt_id
        )
    ]
    with pytest.raises(ValueError, match="orphan delivery attempt settlement"):
        reconcile_delivery_rows(orphan, result.task_id)

    with pytest.raises(ValueError, match="duplicate|physical|ordinal"):
        reconcile_delivery_rows([*rows, dict(intents[0])], result.task_id)

    settlement = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_settlement"
        and row.get("attempt_id") == first_attempt_id
    )
    with pytest.raises(ValueError, match="duplicate|physical|finalization"):
        reconcile_delivery_rows([*rows, dict(settlement)], result.task_id)

    mismatched = [dict(row) for row in rows]
    target = next(
        row
        for row in mismatched
        if row.get("kind") == "delivery_attempt_intent"
        and row.get("channel") == "status_summary"
    )
    request = dict(target["request"])
    request["body"] = {
        "body": "<!-- attest:status -->\nReview complete.\nFinding ID: forged-id",
    }
    target["request"] = request
    target["body_sha256"] = _canonical_test_sha256(request["body"])
    target["request_sha256"] = _canonical_test_sha256(request)
    with pytest.raises(ValueError, match="body.*members"):
        reconcile_delivery_rows(mismatched, result.task_id)


def test_delivery_reconciliation_rejects_deleted_attempt_prefix(tmp_path: Path) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = Ledger(repo).entries()
    first = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_intent"
        and row.get("attempt_ordinal") == 0
    )
    stripped = [
        row
        for row in rows
        if not (
            row.get("attempt_id") == first["attempt_id"]
            and row.get("kind")
            in {"delivery_attempt_intent", "delivery_attempt_settlement"}
        )
    ]

    with pytest.raises(ValueError, match="ordinal|contiguous|expected.*count"):
        reconcile_delivery_rows(stripped, result.task_id)


@pytest.mark.parametrize(
    "path",
    (
        "/repos/local/project/issues/comments/not-a-number",
        "/repos/local/project/issues/comments/12/extra",
        "/repos/local/project/issues/comments/12?query=1",
        "/repos/local/project/issues/comments/01",
    ),
)
def test_delivery_reconciliation_rejects_noncanonical_patch_comment_paths(
    tmp_path: Path, path: str
) -> None:
    import hashlib

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = [dict(row) for row in Ledger(repo).entries()]
    intent = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_intent"
        and row.get("channel") == "status_summary"
    )
    request = dict(intent["request"])
    request["method"] = "PATCH"
    request["path"] = path
    intent["request"] = request
    intent["request_sha256"] = _canonical_test_sha256(request)
    previous_attempt_id = str(intent["attempt_id"])
    replacement_attempt_id = hashlib.sha256(
        f"{result.task_id}:{intent['attempt_ordinal']}:{intent['request_sha256']}".encode()
    ).hexdigest()
    intent["attempt_id"] = replacement_attempt_id
    settlement = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_settlement"
        and row.get("attempt_id") == previous_attempt_id
    )
    settlement["attempt_id"] = replacement_attempt_id

    with pytest.raises(ValueError, match="method/path|comment.*path"):
        reconcile_delivery_rows(rows, result.task_id)


def test_status_summary_body_cannot_hide_finding_markers_behind_empty_members(
    tmp_path: Path,
) -> None:
    import hashlib

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = [dict(row) for row in Ledger(repo).entries()]
    intent = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_intent"
        and row.get("channel") == "status_summary"
    )
    request = dict(intent["request"])
    request["members"] = []
    intent["members"] = []
    intent["request"] = request
    intent["request_sha256"] = _canonical_test_sha256(request)
    previous_attempt_id = str(intent["attempt_id"])
    replacement_attempt_id = hashlib.sha256(
        f"{result.task_id}:{intent['attempt_ordinal']}:{intent['request_sha256']}".encode()
    ).hexdigest()
    intent["attempt_id"] = replacement_attempt_id
    settlement = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_settlement"
        and row.get("attempt_id") == previous_attempt_id
    )
    settlement["attempt_id"] = replacement_attempt_id

    with pytest.raises(ValueError, match="body.*members|marker"):
        reconcile_delivery_rows(rows, result.task_id)


def test_delivery_journal_finalizes_the_expected_attempt_count(tmp_path: Path) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    rows = Ledger(repo).entries()
    finalizations = [
        row
        for row in rows
        if row.get("kind") == "delivery_journal_finalization"
        and row.get("task_id") == result.task_id
    ]

    assert len(finalizations) == 1
    assert finalizations[0]["expected_attempt_count"] == 2
    assert finalizations[0]["schema_version"] == 1
    assert finalizations[0]["protocol"] == "attest.delivery-transcript.v1"
    assert finalizations[0]["last_attempt_ordinal"] == 1
    assert len(str(finalizations[0]["transcript_sha256"])) == 64
    assert (
        result.measurement.delivery_transcript.transcript_sha256
        == finalizations[0]["transcript_sha256"]
    )


def test_delivery_finalization_rejects_coordinated_tail_rewrite(tmp_path: Path) -> None:
    """RED: finalization must be bound into the sealed current outcome authority."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = [dict(row) for row in Ledger(repo).entries()]
    tail = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_intent"
        and row.get("attempt_ordinal") == 1
    )
    rewritten = [
        row
        for row in rows
        if not (
            row.get("attempt_id") == tail["attempt_id"]
            and row.get("kind")
            in {"delivery_attempt_intent", "delivery_attempt_settlement"}
        )
    ]
    finalization = next(
        row
        for row in rewritten
        if row.get("kind") == "delivery_journal_finalization"
    )
    finalization["expected_attempt_count"] = 1

    with pytest.raises(ValueError, match="transcript|sealed|finalization"):
        reconcile_delivery_rows(rewritten, result.task_id)


def test_sealed_measurement_rejects_a_self_consistent_rewritten_transcript(
    tmp_path: Path,
) -> None:
    """A digest recomputed from one mutable ledger is not external authority."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = [dict(row) for row in Ledger(repo).entries()]
    tail = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_intent"
        and row.get("attempt_ordinal") == 1
    )
    rewritten = [
        row
        for row in rows
        if not (
            row.get("attempt_id") == tail["attempt_id"]
            and row.get("kind")
            in {"delivery_attempt_intent", "delivery_attempt_settlement"}
        )
    ]
    forged = ci_module.build_delivery_transcript(
        [
            row
            for row in rewritten
            if row.get("kind") != "delivery_journal_finalization"
        ],
        result.task_id,
    )
    finalization = next(
        row
        for row in rewritten
        if row.get("kind") == "delivery_journal_finalization"
    )
    finalization.update(forged.to_finalization_dict())

    reconcile_delivery_rows(rewritten, result.task_id)
    with pytest.raises(ValueError, match="sealed.*transcript|transcript.*mismatch"):
        reconcile_delivery_rows(
            rewritten,
            result.task_id,
            expected_transcript_sha256=(
                result.measurement.delivery_transcript.transcript_sha256
            ),
        )


def test_delivery_settlement_rejects_a_noncanonical_response_identity(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = [dict(row) for row in Ledger(repo).entries()]
    settlement = next(
        row
        for row in rows
        if row.get("kind") == "delivery_attempt_settlement"
        and row.get("outcome") == "succeeded"
    )
    settlement["remote_response_id"] = " "
    without_finalization = [
        row for row in rows if row.get("kind") != "delivery_journal_finalization"
    ]

    with pytest.raises(ValueError, match="response|identity|canonical|positive"):
        ci_module.build_delivery_transcript(
            without_finalization, result.task_id
        )


def test_current_delivery_ledger_reader_rejects_malformed_rows(tmp_path: Path) -> None:
    repo = tmp_path / "project"
    repo.mkdir()
    ledger = Ledger(repo)
    ledger.append_durable({"kind": "delivery_journal_finalization", "task_id": "t"})
    with ledger.path.open("a", encoding="utf-8") as stream:
        stream.write('{"kind":"delivery_attempt_intent"\n')

    assert hasattr(ledger, "entries_strict"), "current ledger needs a strict reader"
    with pytest.raises(ValueError, match="ledger|JSON|malformed"):
        ledger.entries_strict()


@pytest.mark.parametrize("entrypoint", ("ci_final", "predictions"))
def test_current_benchmark_wrappers_reject_a_truncated_ledger(
    tmp_path: Path, entrypoint: str
) -> None:
    repo = tmp_path / "project"
    repo.mkdir()
    ledger = Ledger(repo)
    ledger.record_ci_final(task_id="task-1", decisions=[], spend_usd=0.0)
    with ledger.path.open("a", encoding="utf-8") as stream:
        stream.write('{"kind":"feedback"\n')

    with pytest.raises(ValueError, match="ledger|JSON|malformed"):
        if entrypoint == "ci_final":
            ci_final_decisions(repo, "task-1")
        else:
            extract_predictions(repo, task_id="task-1", case_id=CASE_ID)


def test_current_delivery_ledger_reader_rejects_an_ancestor_symlink(
    tmp_path: Path,
) -> None:
    outside = tmp_path / "outside"
    project = outside / "project"
    project.mkdir(parents=True)
    ledger = Ledger(project)
    ledger.append_durable({"kind": "safe", "task_id": "task-1"})
    anchor = tmp_path / "anchor"
    anchor.mkdir()
    (anchor / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="ledger|symlink|unsafe"):
        Ledger(anchor / "link" / "project").entries_strict()


def test_current_delivery_ledger_reader_rejects_an_oversize_row_before_json(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "project"
    path = repo / ".attest" / "ledger.jsonl"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"blob":"' + b"x" * (1024 * 1024) + b'"}\n')

    with pytest.raises(ValueError, match="ledger.*row|row.*size|size.*row"):
        Ledger(repo).entries_strict()


@pytest.mark.parametrize(
    "mutation",
    ("settlement_before_intent", "nonmonotonic_intents", "row_after_finalization"),
)
def test_delivery_reconciliation_rejects_noncausal_physical_row_order(
    tmp_path: Path, mutation: str
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = Ledger(repo).entries()
    delivery_rows = [
        row
        for row in rows
        if row.get("task_id") == result.task_id
        and row.get("kind")
        in {
            "delivery_attempt_intent",
            "delivery_attempt_settlement",
            "delivery_journal_finalization",
        }
    ]
    intents = sorted(
        (row for row in delivery_rows if row["kind"] == "delivery_attempt_intent"),
        key=lambda row: int(row["attempt_ordinal"]),
    )
    settlements = {
        row["attempt_id"]: row
        for row in delivery_rows
        if row["kind"] == "delivery_attempt_settlement"
    }
    finalization = next(
        row for row in delivery_rows if row["kind"] == "delivery_journal_finalization"
    )
    canonical = [
        item
        for intent in intents
        for item in (intent, settlements[intent["attempt_id"]])
    ]
    if mutation == "settlement_before_intent":
        mutated = [canonical[1], canonical[0], *canonical[2:], finalization]
    elif mutation == "nonmonotonic_intents":
        mutated = [canonical[2], canonical[3], canonical[0], canonical[1], finalization]
    else:
        mutated = [canonical[0], canonical[1], finalization, *canonical[2:]]

    with pytest.raises(ValueError, match="physical|order|intent|finalization|ordinal"):
        reconcile_delivery_rows(mutated, result.task_id)


def test_delivery_journal_fsyncs_intent_before_publish_and_settlement_and_finalization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.review.ledger as ledger_module
    from attest.github.context import PullRequestContext
    from attest.review.ci import _ci_run, _DeliveryJournal

    repo = tmp_path / "project"
    repo.mkdir()
    context = PullRequestContext(
        repository="local/project",
        number=1,
        base_sha="0" * 40,
        head_sha="1" * 40,
        is_fork=False,
    )
    events: list[str] = []
    real_fsync = ledger_module.os.fsync

    def recording_fsync(file_descriptor: int) -> None:
        events.append("fsync")
        real_fsync(file_descriptor)

    monkeypatch.setattr(ledger_module.os, "fsync", recording_fsync)
    journal = _DeliveryJournal(
        context=context,
        ledger=Ledger(repo),
        task_id="task-1",
        deadline_s=60.0,
        started=0.0,
        clock=lambda: 1.0,
    )

    def publish() -> dict[str, object]:
        assert "fsync" in events
        events.append("publish")
        return {"id": 101}

    assert (
        journal.attempt(
            channel="inline_review",
            members=(("deadbeef00", "inline"),),
            body={
                "commit_id": "1" * 40,
                "body": "Attest review.",
                "event": "COMMENT",
                "comments": [
                    {
                        "path": "app.py",
                        "line": 1,
                        "body": (
                            "<!-- attest:finding-id:deadbeef00 -->\n"
                            "A durable finding."
                        ),
                    }
                ],
            },
            terminal_status=None,
            method="POST",
            path="/repos/local/project/pulls/1/reviews",
            publish=publish,
        )
        is None
    )
    fsyncs_after_settlement = events.count("fsync")
    assert fsyncs_after_settlement >= 2
    assert events.index("fsync") < events.index("publish")

    _ci_run(
        repo=repo,
        task_id="task-1",
        candidate_count=1,
        surfaced_count=1,
        deferred_reason=None,
        spend_usd=0.0,
        started=0.0,
        clock=lambda: 2.0,
    )
    assert events.count("fsync") > fsyncs_after_settlement


def test_status_summary_uses_one_bound_attempt_for_publication_and_task_delivery(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(cassette()),
            client=github.client(),
        )
    assert result.task_id is not None
    rows = Ledger(repo).entries()
    assert not any(
        row.get("kind")
        in {
            "publication_intent",
            "publication_settlement",
            "task_delivery_intent",
            "task_delivery_settlement",
        }
        for row in rows
    )
    intents = [row for row in rows if row.get("kind") == "delivery_attempt_intent"]
    summary = next(row for row in intents if row["channel"] == "status_summary")
    assert summary["members"]
    assert summary["terminal_status"] == "completed"
    request = summary["request"]
    assert request["terminal_status"] == "completed"
    assert request["method"] in {"POST", "PATCH"}
    assert str(request["path"]).startswith("/repos/")

    mutated = [dict(row) for row in rows]
    changed = next(
        row
        for row in mutated
        if row.get("kind") == "delivery_attempt_intent"
        and row.get("channel") == "status_summary"
    )
    changed["terminal_status"] = "deferred"
    with pytest.raises(ValueError, match="terminal|request|digest"):
        reconcile_delivery_rows(mutated, result.task_id)

    missing_intent = [
        row
        for row in rows
        if not (
            row.get("kind") == "delivery_attempt_intent"
            and row.get("attempt_id") == summary["attempt_id"]
        )
    ]
    with pytest.raises(ValueError, match="orphan delivery attempt settlement"):
        reconcile_delivery_rows(missing_intent, result.task_id)


def test_model_text_cannot_inject_a_publication_membership_marker(tmp_path: Path) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    proposal = json.loads(cassette().proposal)
    proposal["findings"][0]["claim"] += " Ordinary prose: Finding ID: deadbeef00"

    with LoopbackGitHub() as github:
        result = BenchmarkRunner(repeats=1).run_case(
            repo,
            case_id=CASE_ID,
            base_sha=base_sha,
            head_sha=head_sha,
            config=ReviewConfig(k_samples=2, tier0_commands=[]),
            provider=ReplayProvider(
                Cassette(proposal=json.dumps(proposal), repro=cassette().repro)
            ),
            client=github.client(),
        )

    assert result.deferred_reason is None
    assert result.measurement.published_count == 1
    assert all(
        member.finding_id != "deadbeef00"
        for event in result.measurement.publication_events
        for member in event.members
    )


def _canonical_test_sha256(value: object) -> str:
    import hashlib

    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    return hashlib.sha256(canonical).hexdigest()


def test_evidence_class_to_repro_status_map_is_total_and_only_one_status_scores() -> None:
    """Only a regression reproduced against the fixed reference can ever match truth."""
    from attest.review.executor import EvidenceClass

    assert set(REPRO_STATUS_BY_EVIDENCE_CLASS) == {member.value for member in EvidenceClass}
    scoring = [
        evidence
        for evidence, status in REPRO_STATUS_BY_EVIDENCE_CLASS.items()
        if status == "buggy_fail_fixed_pass"
    ]
    assert scoring == ["regression_reproduced"]


def _repro_case(
    tmp_path: Path, body: str, *, repeats: int = 1
) -> tuple[str, str, Path, ReproReceipt]:
    repo, fixed_sha, buggy_sha = regression_repo(tmp_path / "project")
    record = tmp_path / "interpreters.txt"
    spec = ReproSpec(
        test_body=(
            "import pathlib\n"
            "import runpy\n"
            "import sys\n\n"
            f"pathlib.Path({str(record)!r}).open('a').write(sys.executable + '\\n')\n\n"
            f"{body}"
        )
    )
    receipt = run_differential_repro(
        repo,
        stored_candidate(),
        spec,
        ExecutorLimits(wall_timeout_s=30.0),
        buggy_sha=buggy_sha,
        fixed_sha=fixed_sha,
        repeats=repeats,
    )
    return buggy_sha, fixed_sha, record, receipt


def test_fail_on_buggy_and_pass_on_fixed_is_confirmed_under_identical_limits(
    tmp_path: Path,
) -> None:
    buggy_sha, fixed_sha, record, receipt = _repro_case(
        tmp_path,
        "def test_average_handles_empty_input():\n"
        "    average = runpy.run_path('app.py')['average']\n"
        "    assert average([]) == 0\n",
    )

    assert receipt.outcome == "reproduced"
    assert receipt.evidence_class == "regression_reproduced"
    assert receipt.repro_status == "buggy_fail_fixed_pass"
    assert receipt.confirmed is True
    assert receipt.buggy_sha == buggy_sha
    assert receipt.fixed_sha == fixed_sha
    assert receipt.buggy_runs == ("reproduced",)
    assert receipt.fixed_runs == ("not_reproduced",)

    interpreters = record.read_text(encoding="utf-8").split()
    # collect-only run, then one head and one base repeat, all on one interpreter
    assert len(interpreters) == 3
    assert len(set(interpreters)) == 1


def test_failing_on_both_trees_is_an_unfaithful_generated_test(tmp_path: Path) -> None:
    _, _, _, receipt = _repro_case(
        tmp_path,
        "def test_average_is_impossible():\n"
        "    average = runpy.run_path('app.py')['average']\n"
        "    assert average([1]) == 99\n",
    )

    assert receipt.outcome == "deferred"
    assert receipt.evidence_class == "unfaithful"
    assert receipt.repro_status == "buggy_fail_fixed_fail"
    assert receipt.confirmed is False


def test_passing_on_both_trees_is_not_reproduced(tmp_path: Path) -> None:
    _, _, _, receipt = _repro_case(
        tmp_path,
        "def test_average_of_one_value():\n"
        "    average = runpy.run_path('app.py')['average']\n"
        "    assert average([2]) == 2\n",
    )

    assert receipt.outcome == "not_reproduced"
    assert receipt.evidence_class == "not_reproduced"
    assert receipt.repro_status == "buggy_pass"
    assert receipt.confirmed is False


def test_collection_failure_defers_and_never_scores(tmp_path: Path) -> None:
    _, _, _, receipt = _repro_case(
        tmp_path, "def test_broken(:\n    pass\n"
    )

    assert receipt.outcome == "deferred"
    assert receipt.evidence_class == "indeterminate"
    assert receipt.repro_status == "deferred"
    assert receipt.confirmed is False
    assert "collection" in receipt.reason or "deferred" in receipt.reason
