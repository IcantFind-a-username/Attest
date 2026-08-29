from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.acceptance.phase3 import (  # noqa: E402
    MODEL_KEY_ENV,
    AcceptanceError,
    AcceptanceResult,
    AcceptanceService,
    CommandResult,
    PreflightError,
    SubprocessRunner,
    _workflow_text,
    build_private_repo_command,
    classify_comments,
    parse_ledger,
    render_report,
    sticky_seconds,
)


@dataclass
class FakeRunner:
    results: list[CommandResult | Exception]
    calls: list[tuple[tuple[str, ...], str | None, Path | None]] = field(default_factory=list)

    def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str | None = None,
        cwd: Path | None = None,
    ) -> CommandResult:
        self.calls.append((args, input_text, cwd))
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


@dataclass
class MemoryFileSystem:
    files: dict[Path, str]

    def read_text(self, path: Path) -> str:
        return self.files[path]

    def write_text(self, path: Path, text: str) -> None:
        self.files[path] = text

    def exists(self, path: Path) -> bool:
        return path in self.files

    def mkdir(self, path: Path) -> None:
        return


def _service(
    runner: FakeRunner,
    *,
    key: str = "sk-ant-test-012345678901234567890123456789",
    files: dict[Path, str] | None = None,
) -> AcceptanceService:
    return AcceptanceService(
        runner=runner,
        filesystem=MemoryFileSystem(files or {}),
        environ={"ANTHROPIC_API_KEY": key},
        workspace=Path("/workspace"),
    )


def test_preflight_reports_missing_gh_without_leaking_model_key() -> None:
    runner = FakeRunner([FileNotFoundError("gh")])
    secret = "sk-ant-test-secret-that-must-not-appear"

    with pytest.raises(PreflightError, match="GitHub CLI.*not installed") as caught:
        _service(runner, key=secret).preflight()

    assert secret not in str(caught.value)


def test_preflight_rejects_unauthenticated_cli() -> None:
    runner = FakeRunner([CommandResult(1, stderr="not logged in")])

    with pytest.raises(PreflightError, match="not authenticated"):
        _service(runner).preflight()


def test_preflight_requires_repo_and_workflow_scopes() -> None:
    runner = FakeRunner(
        [CommandResult(0, stdout="Logged in to github.com\nToken scopes: 'read:org'")]
    )

    with pytest.raises(PreflightError, match="repo.*workflow"):
        _service(runner).preflight()


@pytest.mark.parametrize("key", ["", "sk-ant-short", "wrong-prefix-012345678901234567890"])
def test_preflight_rejects_missing_or_implausible_model_key_without_printing_it(key: str) -> None:
    runner = FakeRunner(
        [CommandResult(0, stdout="Logged in\nToken scopes: 'repo', 'workflow'")]
    )

    with pytest.raises(PreflightError, match="model API key") as caught:
        _service(runner, key=key).preflight()

    assert not key or key not in str(caught.value)


def test_preflight_accepts_authenticated_cli_with_required_scopes() -> None:
    runner = FakeRunner(
        [CommandResult(0, stdout="Logged in\nToken scopes: 'repo', 'workflow'")]
    )

    _service(runner).preflight()

    assert runner.calls == [(('gh', 'auth', 'status'), None, None)]


def test_subprocess_adapter_uses_only_its_sanitized_environment() -> None:
    result = SubprocessRunner({"ATTEST_ACCEPTANCE_SAFE": "yes"}).run(("/usr/bin/env",))

    assert result.returncode == 0
    assert result.stdout == "ATTEST_ACCEPTANCE_SAFE=yes\n"
    assert MODEL_KEY_ENV not in result.stdout


def test_private_repo_command_is_owner_scoped_and_explicitly_private() -> None:
    assert build_private_repo_command("octocat", "attest-phase3-20260829-123456") == (
        "gh",
        "repo",
        "create",
        "octocat/attest-phase3-20260829-123456",
        "--private",
        "--confirm",
    )


def test_scratch_workflow_keeps_run_specific_artifact_name_exact() -> None:
    workflow = _workflow_text("feature/phase-3-action")

    assert (
        "name: attest-ledger-pr-${{ github.event.pull_request.number }}"
        "-run-${{ github.run_id }}"
    ) in workflow
    assert "uses: ./_attest_action" in workflow
    assert "ref: feature/phase-3-action" in workflow


def test_sticky_timing_excludes_runner_queue_time() -> None:
    assert sticky_seconds("2026-08-29T00:02:00Z", "2026-08-29T00:02:42.250Z") == 42.25


def test_sticky_timing_rejects_comment_before_job_start() -> None:
    with pytest.raises(AcceptanceError, match="precedes job start"):
        sticky_seconds("2026-08-29T00:02:00Z", "2026-08-29T00:01:59Z")


def test_comment_classification_separates_sticky_and_verified_inline_findings() -> None:
    issue_comments = [
        {
            "id": 11,
            "body": "<!-- attest:status -->\nReview running; candidates are under verification.",
            "created_at": "2026-08-29T00:02:12Z",
        },
        {"id": 12, "body": "human note", "created_at": "2026-08-29T00:02:13Z"},
    ]
    review_comments = [
        {
            "id": 21,
            "body": "Crash on empty input\nEvidence purchases: S x2.64; V x20.00",
            "path": "sample/stats.py",
            "line": 3,
        },
        {"id": 22, "body": "ordinary review", "path": "README.md", "line": 1},
    ]

    comments = classify_comments(issue_comments, review_comments)

    assert [comment["id"] for comment in comments.sticky] == [11]
    assert [comment["id"] for comment in comments.findings] == [21]


def test_comment_classification_rejects_malformed_api_payload() -> None:
    with pytest.raises(AcceptanceError, match="issue comment"):
        classify_comments([{"id": 11}], [])


def test_parse_ledger_validates_json_objects_and_required_event_fields() -> None:
    text = "\n".join(
        [
            json.dumps(
                {
                    "kind": "review",
                    "task_id": "task-1",
                    "finding_id": "finding-1",
                    "spend": 0.012,
                    "action": "formal_surface",
                }
            ),
            json.dumps(
                {
                    "kind": "verification",
                    "task_id": "task-1",
                    "finding_id": "finding-1",
                    "outcome": "reproduced",
                }
            ),
            json.dumps(
                {
                    "kind": "github_comment",
                    "task_id": "task-1",
                    "phase": "review",
                    "outcome": "posted",
                }
            ),
        ]
    )

    ledger = parse_ledger(text)

    assert ledger.spend_usd == pytest.approx(0.012)
    assert ledger.task_ids == frozenset({"task-1"})
    ledger.assert_event_coverage(require_verified_finding=True)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("not json", "line 1"),
        ("[]", "JSON object"),
        ('{"kind":"verification","task_id":"task-1"}', "finding_id"),
    ],
)
def test_parse_ledger_rejects_malformed_artifact(text: str, message: str) -> None:
    with pytest.raises(AcceptanceError, match=message):
        parse_ledger(text)


def test_ledger_coverage_rejects_unaccounted_review_comment() -> None:
    ledger = parse_ledger(
        json.dumps(
            {
                "kind": "review",
                "task_id": "task-1",
                "finding_id": "finding-1",
                "spend": 0.01,
                "action": "formal_surface",
            }
        )
    )

    with pytest.raises(AcceptanceError, match="verification.*comment"):
        ledger.assert_event_coverage(require_verified_finding=True)


def test_spend_cap_rejects_cumulative_development_spend() -> None:
    spend_path = Path("/workspace/DEVSPEND.md")
    original = (
        "# Development spend ledger\n\n"
        "| 2026-08-29 | prior run | $9.90 |\n\n"
        "**Total API spend: $9.90 of $10.00.**\n"
    )
    files = {
        spend_path: original
    }
    service = _service(FakeRunner([]), files=files)

    with pytest.raises(AcceptanceError, match=r"\$10.00 development spend cap"):
        service.record_spend("run-2", 0.11, "https://github.com/octocat/scratch")

    assert service.filesystem.read_text(spend_path) == original


def test_live_acceptance_requires_headroom_for_both_pr_budgets() -> None:
    spend_path = Path("/workspace/DEVSPEND.md")
    service = _service(
        FakeRunner([]),
        files={spend_path: "**Total API spend: $9.60 of $10.00.**\n"},
    )

    with pytest.raises(AcceptanceError, match=r"\$10.00 development spend cap"):
        service.ensure_spend_headroom(0.50)


def test_spend_insertion_is_idempotent_by_run_id_and_updates_total() -> None:
    spend_path = Path("/workspace/DEVSPEND.md")
    files = {
        spend_path: (
            "# Development spend ledger\n\n"
            "## API spend (counts against the $10 cap)\n\n"
            "| date | item | cost |\n"
            "|---|---|---|\n"
            "| 2026-08-29 | prior run | $0.15 |\n\n"
            "**Total API spend: $0.15 of $10.00.**\n"
        )
    }
    service = _service(FakeRunner([]), files=files)

    service.record_spend("98765", 0.05, "https://github.com/octocat/scratch")
    service.record_spend("98765", 0.05, "https://github.com/octocat/scratch")

    updated = service.filesystem.read_text(spend_path)
    assert updated.count("phase-3 acceptance run 98765") == 1
    assert (
        "| 2026-08-29 | phase-3 acceptance run 98765 "
        "(https://github.com/octocat/scratch) | $0.0500 |"
    ) in updated
    assert "**Total API spend: $0.2000 of $10.00.**" in updated


def test_report_contains_inspectable_repository_pr_and_run_urls() -> None:
    result = AcceptanceResult(
        repository_url="https://github.com/octocat/attest-phase3-20260829",
        bug_pr_url="https://github.com/octocat/attest-phase3-20260829/pull/1",
        control_pr_url="https://github.com/octocat/attest-phase3-20260829/pull/2",
        bug_sticky_seconds=12.5,
        control_sticky_seconds=8.0,
        queue_seconds={101: 4.25, 102: 1.5},
        spend_usd=0.0345,
        run_urls={
            101: "https://github.com/octocat/attest-phase3-20260829/actions/runs/101",
            102: "https://github.com/octocat/attest-phase3-20260829/actions/runs/102",
        },
    )

    report = render_report(result)

    assert "https://github.com/octocat/attest-phase3-20260829" in report
    assert result.bug_pr_url in report
    assert result.control_pr_url in report
    assert result.run_urls[101] in report
    assert result.run_urls[102] in report
    assert "12.500s" in report
    assert "$0.0345" in report
