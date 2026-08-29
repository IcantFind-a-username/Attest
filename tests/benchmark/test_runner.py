"""The replay runner drives the real product path and observes only its output."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from attest.benchmark.runner import (
    REPRO_STATUS_BY_EVIDENCE_CLASS,
    BenchmarkRunner,
    Cassette,
    LoopbackGitHub,
    ReplayProvider,
    ReproReceipt,
    extract_predictions,
    load_cassette,
    run_differential_repro,
)
from attest.benchmark.schema import Placement
from attest.review.candidates import StoredCandidate
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits, ReproSpec
from attest.review.ledger import Ledger
from attest.review.schema import Finding

CASE_ID = "case-0123456789ab"


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


def test_overflow_surfaces_are_extracted_as_scored_predictions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A surfaced finding beyond the formatting cap is still visible, so it is scored."""
    from attest.review import tier0
    from attest.review.tier0 import Tier0Signal

    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    (repo / "app.py").write_text(
        "def average(items):\n"
        "    return sum(items) / len(items)\n\n\n"
        "# helpers below\n\n\n"
        "def ratio(a, b):\n"
        "    return a / b\n",
        encoding="utf-8",
    )
    git(repo, "add", "app.py")
    git(repo, "commit", "-m", "add an unguarded ratio")
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

    assert payloads[0] == payloads[1]
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
    from attest.review.candidates import CandidateStore
    from attest.review.gate import GateResult

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

    predictions = extract_predictions(
        repo,
        task_id="task-1",
        case_id=CASE_ID,
        repro_status={candidate.finding.finding_id: "buggy_fail_fixed_pass"},
        evidence_class={candidate.finding.finding_id: "regression_reproduced"},
    )

    assert len(predictions) == 1
    assert predictions[0].placement is Placement.OVERFLOW
    assert predictions[0].action == "surface"
    assert predictions[0].line == 2
    assert predictions[0].repro_status == "buggy_fail_fixed_pass"
    assert predictions[0].evidence_class == "regression_reproduced"

    assert extract_predictions(repo, task_id="task-2", case_id=CASE_ID) == ()


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
    assert len(interpreters) == 2
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
