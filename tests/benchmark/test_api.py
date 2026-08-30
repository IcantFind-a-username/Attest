"""The project-evaluation API is generic over any caller-owned Git repository."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from attest.benchmark.api import (
    ABSENT_BINDING_SHA256,
    ProjectEvaluationError,
    ProjectEvaluationRequest,
    ProjectTruth,
    _code_sha256,
    build_evaluation_binding,
    evaluate_project,
    evaluate_projects,
    freeze_evaluation_request,
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


def test_predeclaration_binding_resolves_every_drift_sensitive_input(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    request = _request(tmp_path, repo, base_sha, head_sha)

    binding = build_evaluation_binding(
        request,
        provider_id="cassette-v1",
        interpreter_id="cpython-3.11.5",
        environment_sha256="e" * 64,
        code_sha256="c" * 64,
        receipt_sha256=None,
    ).to_json_dict()

    assert binding["repository"] == "local/project"
    assert binding["base_sha"] == base_sha
    assert binding["head_sha"] == head_sha
    assert binding["fixed_sha"] is None
    assert binding["diff_sha256"] != ABSENT_BINDING_SHA256
    assert binding["truth_sha256"] == ABSENT_BINDING_SHA256
    assert binding["receipt_sha256"] == ABSENT_BINDING_SHA256
    assert binding["provider_id"] == "cassette-v1"
    assert binding["model_id"] == request.config.model
    assert binding["interpreter_id"] == "cpython-3.11.5"
    assert binding["environment_sha256"] == "e" * 64
    assert binding["code_sha256"] == "c" * 64
    assert binding["policy_sha256"] != ABSENT_BINDING_SHA256
    assert binding["prompt_sha256"] != ABSENT_BINDING_SHA256
    assert binding["schema_sha256"] != ABSENT_BINDING_SHA256


@pytest.mark.parametrize(
    ("field", "value"),
    (("line_slack", 1), ("pull_request_number", 2), ("repeat", 1)),
)
def test_evaluation_policy_binding_covers_scoring_and_run_identity(
    tmp_path: Path, field: str, value: int
) -> None:
    """A resumable evaluation digest changes for every execution-semantic field."""
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    request = _request(tmp_path, repo, base_sha, head_sha)
    kwargs = {
        "provider_id": "cassette-v1",
        "interpreter_id": "cpython-3.11.5",
        "environment_sha256": "e" * 64,
        "code_sha256": "c" * 64,
    }

    original = build_evaluation_binding(request, **kwargs).to_json_dict()
    drifted = build_evaluation_binding(
        replace(request, **{field: value}), **kwargs
    ).to_json_dict()

    assert original["schema_version"] == "2"
    assert drifted["schema_version"] == "2"
    assert original["policy_sha256"] != drifted["policy_sha256"]


def test_runtime_code_digest_includes_paid_controller_and_package_data(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repository"
    package = repository / "src" / "attest"
    controller = repository / "scripts" / "benchmark.py"
    package.mkdir(parents=True)
    controller.parent.mkdir(parents=True)
    (package / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    (package / "pricing.json").write_text('{"price": 1}\n', encoding="utf-8")
    controller.write_text("VALUE = 1\n", encoding="utf-8")
    initial = _code_sha256(package, repository)

    controller.write_text("VALUE = 2\n", encoding="utf-8")
    controller_changed = _code_sha256(package, repository)
    (package / "pricing.json").write_text('{"price": 2}\n', encoding="utf-8")
    data_changed = _code_sha256(package, repository)

    assert controller_changed != initial
    assert data_changed != controller_changed


def test_frozen_request_uses_predeclared_shas_even_if_symbolic_refs_move(
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    git(repo, "branch", "base-symbolic", base_sha)
    git(repo, "branch", "head-symbolic", head_sha)
    request = _request(
        tmp_path, repo, base_sha, head_sha, base_ref="base-symbolic", head_ref="head-symbolic"
    )
    binding = build_evaluation_binding(
        request,
        provider_id="cassette-v1",
        interpreter_id="cpython-3.11.5",
        environment_sha256="e" * 64,
        code_sha256="c" * 64,
    )

    git(repo, "branch", "-f", "head-symbolic", base_sha)
    frozen = freeze_evaluation_request(request, binding)

    assert frozen.base_ref == base_sha
    assert frozen.head_ref == head_sha


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("config", ReviewConfig(alpha=0.2)),
        ("limits", ExecutorLimits(wall_timeout_s=61.0)),
        ("verification_timeout_s", 601.0),
        ("repeats", 4),
        ("deadline_s", 61.0),
        ("line_slack", 1),
        ("pull_request_number", 2),
        ("repeat", 1),
    ),
)
def test_freeze_rejects_request_policy_drift(
    tmp_path: Path, field: str, value: object
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    request = _request(tmp_path, repo, base_sha, head_sha)
    binding = build_evaluation_binding(
        request,
        provider_id="cassette-v1",
        interpreter_id="cpython-3.11.5",
        environment_sha256="e" * 64,
        code_sha256="c" * 64,
    )

    with pytest.raises(ProjectEvaluationError, match="policy"):
        freeze_evaluation_request(replace(request, **{field: value}), binding)


def test_freeze_rejects_truth_drift_from_prebuilt_binding(tmp_path: Path) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    truth = ProjectTruth(
        fixed_ref=base_sha,
        defects=(
            TruthDefect(
                defect_id="defect-1",
                case_id=CASE_ID,
                file="app.py",
                start_line=1,
                end_line=1,
            ),
        ),
    )
    request = _request(tmp_path, repo, base_sha, head_sha, truth=truth)
    binding = build_evaluation_binding(
        request,
        provider_id="cassette-v1",
        interpreter_id="cpython-3.11.5",
        environment_sha256="e" * 64,
        code_sha256="c" * 64,
    )
    changed_truth = replace(
        truth, defects=(replace(truth.defects[0], file="different.py"),)
    )

    with pytest.raises(ProjectEvaluationError, match="truth"):
        freeze_evaluation_request(replace(request, truth=changed_truth), binding)


@pytest.mark.parametrize("field", ("prompt_sha256", "schema_sha256"))
def test_freeze_rejects_current_prompt_or_schema_drift(
    tmp_path: Path, field: str
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    request = _request(tmp_path, repo, base_sha, head_sha)
    binding = build_evaluation_binding(
        request,
        provider_id="cassette-v1",
        interpreter_id="cpython-3.11.5",
        environment_sha256="e" * 64,
        code_sha256="c" * 64,
    )

    with pytest.raises(ProjectEvaluationError, match="prompt|schema"):
        freeze_evaluation_request(replace(request), replace(binding, **{field: "0" * 64}))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("repeats", True),
        ("verification_timeout_s", float("inf")),
        ("deadline_s", float("nan")),
        ("line_slack", True),
        ("pull_request_number", True),
        ("repeat", -1),
    ),
)
def test_request_policy_is_rejected_before_git_workspace_or_provider(
    tmp_path: Path, field: str, value: object
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    request = replace(
        _request(tmp_path, repo, base_sha, head_sha), **{field: value}
    )

    with pytest.raises(ProjectEvaluationError, match=field):
        evaluate_project(request, provider=RefusingProvider())
    assert not request.workspace_root.exists()


@pytest.mark.parametrize(
    "field",
    ["provider_id", "interpreter_id", "environment_sha256", "code_sha256"],
)
def test_predeclaration_binding_rejects_missing_or_unversioned_runtime_fields(
    tmp_path: Path, field: str
) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    kwargs = {
        "provider_id": "cassette-v1",
        "interpreter_id": "cpython-3.11.5",
        "environment_sha256": "e" * 64,
        "code_sha256": "c" * 64,
    }
    kwargs[field] = ""

    with pytest.raises(ProjectEvaluationError, match=field):
        build_evaluation_binding(_request(tmp_path, repo, base_sha, head_sha), **kwargs)


def test_predeclaration_binding_rejects_empty_repository_identity(tmp_path: Path) -> None:
    repo, base_sha, head_sha = regression_repo(tmp_path / "project")
    request = _request(tmp_path, repo, base_sha, head_sha)

    with pytest.raises(ProjectEvaluationError, match="repository"):
        build_evaluation_binding(
            replace(request, repository=""),
            provider_id="cassette-v1",
            interpreter_id="cpython-3.11.5",
            environment_sha256="e" * 64,
            code_sha256="c" * 64,
        )


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
