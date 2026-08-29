"""The project-evaluation API is generic over any caller-owned Git repository."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from attest.benchmark.api import (
    ProjectEvaluationError,
    ProjectEvaluationRequest,
    ProjectTruth,
    evaluate_project,
    evaluate_projects,
)
from attest.benchmark.artifacts import ArtifactStore, verify_artifacts
from attest.benchmark.runner import Cassette, ReplayProvider
from attest.benchmark.schema import TruthDefect
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits
from attest.review.proposer import ProviderResult

from .test_runner import PROPOSAL, REPRO, git, regression_repo

CASE_ID = "case-0123456789ab"
OTHER_CASE_ID = "case-cafe12345678"


class RefusingProvider:
    """Any provider call at all is a contract violation for a rejected request."""

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        raise AssertionError("the provider must not be reached before refs are resolved")


def _provider() -> ReplayProvider:
    return ReplayProvider(Cassette(proposal=PROPOSAL, repro=REPRO, input_tokens=900))


def _request(tmp_path: Path, repo: Path, base_sha: str, head_sha: str, **kwargs: Any):
    defaults: dict[str, Any] = {
        "case_id": CASE_ID,
        "repo": repo,
        "base_ref": base_sha,
        "head_ref": head_sha,
        "workspace_root": tmp_path / "workspace",
        "config": ReviewConfig(k_samples=2, tier0_commands=[]),
        "limits": ExecutorLimits(wall_timeout_s=30.0),
        "repeats": 1,
    }
    defaults.update(kwargs)
    return ProjectEvaluationRequest(**defaults)


def test_evaluate_project_measures_a_caller_owned_repository_without_truth(
    tmp_path: Path,
) -> None:
    """No truth means operational measurements and no score -- never a negative label."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    store = ArtifactStore(tmp_path / "artifacts")

    result = evaluate_project(
        _request(tmp_path, repo, base_sha, head_sha),
        provider=_provider(),
        artifact_store=store,
    )

    assert result.case_id == CASE_ID
    assert result.status == "completed"
    assert result.task_id
    assert result.base_sha == base_sha
    assert result.head_sha == head_sha
    assert result.score is None
    assert result.abstain_reason is None
    assert result.latency_s >= 0
    assert result.spend_usd > 0
    assert [prediction.action for prediction in result.predictions] == ["surface"]
    assert [decision["placement"] for decision in result.final_decisions] == ["inline"]
    assert result.evidence_class_counts == {"regression_reproduced": 1}
    assert {record.kind for record in result.artifacts} >= {
        "product_ledger",
        "predictions",
        "scored_run",
    }

    assert git(repo, "status", "--porcelain") == ""
    assert (tmp_path / "workspace").exists()
    assert not any((tmp_path / "workspace").iterdir())
    assert len(git(repo, "worktree", "list").splitlines()) == 1
    assert str(tmp_path / "workspace") not in git(repo, "worktree", "list")


def test_evaluate_project_scores_surfaced_findings_against_supplied_truth(
    tmp_path: Path,
) -> None:
    """A fixed reference plus truth turns operational output into a scored match."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    truth = ProjectTruth(
        fixed_ref=base_sha,
        defects=(
            TruthDefect(
                defect_id="defect-1",
                case_id=CASE_ID,
                file="app.py",
                start_line=1,
                end_line=2,
            ),
        ),
    )

    result = evaluate_project(
        _request(tmp_path, repo, base_sha, head_sha, truth=truth),
        provider=_provider(),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
    )

    assert result.score is not None
    assert result.score.surfaced == 1
    assert result.score.matched == 1
    assert result.score.unmatched == 0
    assert result.score.matches[0].defect_id == "defect-1"
    assert result.predictions[0].repro_status == "buggy_fail_fixed_pass"
    assert result.oracle_receipts[0].confirmed is True


def test_rejections_happen_before_any_provider_call(tmp_path: Path) -> None:
    """Every refusal is decided from git and identity alone, never from model output."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    provider = RefusingProvider()
    store = ArtifactStore(tmp_path / "artifacts")

    def refuse(**kwargs: Any) -> str:
        with pytest.raises(ProjectEvaluationError) as excinfo:
            evaluate_project(
                _request(tmp_path, repo, base_sha, head_sha, **kwargs),
                provider=provider,
                artifact_store=store,
            )
        return str(excinfo.value)

    assert "opaque" in refuse(case_id="buggy-case-1")
    assert "opaque" in refuse(case_id="case-not-hex-xx")
    assert "identical" in refuse(base_ref=head_sha)
    assert "resolve" in refuse(base_ref="refs/heads/nope")
    assert "resolve" in refuse(head_ref="0" * 40)
    assert "fixed reference" in refuse(
        truth=ProjectTruth(
            fixed_ref=None,
            defects=(
                TruthDefect(
                    defect_id="d", case_id=CASE_ID, file="app.py", start_line=1, end_line=2
                ),
            ),
        )
    )
    assert "resolve" in refuse(
        truth=ProjectTruth(
            fixed_ref="refs/heads/absent",
            defects=(
                TruthDefect(
                    defect_id="d", case_id=CASE_ID, file="app.py", start_line=1, end_line=2
                ),
            ),
        )
    )

    missing = tmp_path / "absent"
    with pytest.raises(ProjectEvaluationError, match="git repository"):
        evaluate_project(
            _request(tmp_path, missing, base_sha, head_sha),
            provider=provider,
            artifact_store=store,
        )

    (repo / "app.py").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ProjectEvaluationError, match="clean"):
        evaluate_project(
            _request(tmp_path, repo, base_sha, head_sha),
            provider=provider,
            artifact_store=store,
        )


def test_evaluate_projects_preserves_order_and_defers_one_failing_case(
    tmp_path: Path,
) -> None:
    """A broken case becomes an explicit DEFER; completed results are still returned."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    store = ArtifactStore(tmp_path / "artifacts")
    requests = (
        _request(tmp_path, repo, base_sha, head_sha),
        _request(
            tmp_path,
            repo,
            base_sha,
            head_sha,
            case_id=OTHER_CASE_ID,
            base_ref="refs/heads/absent",
        ),
        _request(tmp_path, repo, base_sha, head_sha, case_id="case-999999999999"),
    )

    results = evaluate_projects(
        requests,
        provider_factory=lambda _request: _provider(),
        artifact_store=store,
    )

    assert [result.case_id for result in results] == [
        CASE_ID,
        OTHER_CASE_ID,
        "case-999999999999",
    ]
    assert [result.status for result in results] == ["completed", "deferred", "completed"]
    assert results[1].task_id is None
    assert results[1].predictions == ()
    assert results[1].score is None
    assert results[1].abstain_reason is not None
    assert "resolve" in results[1].abstain_reason
    assert results[0].task_id != results[2].task_id
    assert results[0].spend_usd > 0
    assert results[2].spend_usd > 0

    names = {record.name for record in store.records()}
    assert f"cases/{CASE_ID}/repeat-0/predictions.json" in names
    assert "cases/case-999999999999/repeat-0/predictions.json" in names
    assert not any(name.startswith(f"cases/{OTHER_CASE_ID}/predictions") for name in names)

    store.finalize()
    assert len(verify_artifacts(tmp_path / "artifacts")) == len(names)


def test_result_is_json_serializable_and_excludes_secrets(tmp_path: Path) -> None:
    """A result must round-trip to JSON so callers can persist it verbatim."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")

    result = evaluate_project(
        _request(tmp_path, repo, base_sha, head_sha),
        provider=_provider(),
        artifact_store=ArtifactStore(tmp_path / "artifacts"),
    )

    payload = json.loads(json.dumps(result.to_json_dict(), sort_keys=True))
    assert payload["case_id"] == CASE_ID
    assert payload["status"] == "completed"
    assert payload["score"] is None
    assert payload["predictions"][0]["evidence_class"] == "regression_reproduced"
    assert "provider_prompt" not in json.dumps(payload)
