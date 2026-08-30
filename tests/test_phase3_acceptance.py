from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.acceptance.phase3 import (  # noqa: E402
    CONTROL_COMMENT_PHASES,
    MODEL_KEY_ENV,
    NEW_CODE_COMMENT_PHASES,
    NEW_CODE_EVIDENCE_CLASS,
    REGRESSION_COMMENT_PHASES,
    REGRESSION_EVIDENCE_CLASS,
    AcceptanceError,
    AcceptanceResult,
    AcceptanceService,
    CommandResult,
    CommentClassification,
    LedgerArtifact,
    PreflightError,
    SubprocessRunner,
    _PullRequest,
    _workflow_text,
    _WorkflowRun,
    build_private_repo_command,
    classify_comments,
    parse_ledger,
    render_report,
    sticky_seconds,
)

TEST_SOURCE_TOKEN_SECRET = "ATTEST_SOURCE_TOKEN"


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
    # A fixed clock keeps date-bearing assertions (spend rows) stable: without
    # it the suite is a snapshot that starts failing the day after it is written.
    return AcceptanceService(
        runner=runner,
        filesystem=MemoryFileSystem(files or {}),
        environ={"ANTHROPIC_API_KEY": key},
        workspace=Path("/workspace"),
        clock=lambda: datetime(2026, 8, 29, 12, 0, 0, tzinfo=UTC),
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
    assert set(result.stdout.splitlines()) == {
        "ATTEST_ACCEPTANCE_SAFE=yes",
        "GIT_TERMINAL_PROMPT=0",
    }
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
    assert "ref: ${{ github.event.pull_request.head.sha }}" in workflow


def test_seed_configures_repo_scoped_gh_credential_helper_before_push() -> None:
    runner = FakeRunner([CommandResult(0)] * 9)
    service = _service(runner)

    service._seed_repository(
        Path("/scratch"), "octocat/attest-phase3-test", "feature/phase-3-action"
    )

    commands = [call[0] for call in runner.calls]
    push_index = commands.index(("git", "push", "-u", "origin", "main"))
    assert commands.index(
        ("git", "config", "--local", "credential.https://github.com.helper", "")
    ) < push_index
    assert commands.index(
        (
            "git",
            "config",
            "--local",
            "--add",
            "credential.https://github.com.helper",
            "!gh auth git-credential",
        )
    ) < push_index
    assert all("token" not in " ".join(command).lower() for command in commands)


SCRATCH = Path("/scratch")
STATS_PATH = SCRATCH / "sample" / "stats.py"
SCRATCH_REPOSITORY = "octocat/attest-phase3-test"
_PR_VIEW = CommandResult(
    0, stdout=json.dumps({"number": 7, "url": "https://github.invalid/pull/7"})
)


def _seeded_service(git_commands: int) -> tuple[AcceptanceService, FakeRunner]:
    """A service whose scratch checkout already holds the seeded base tree."""
    runner = FakeRunner([CommandResult(0)] * (9 + git_commands + 1) + [_PR_VIEW])
    service = _service(runner)
    service._seed_repository(SCRATCH, SCRATCH_REPOSITORY, "feature/phase-3-action")
    return service, runner


def test_seed_base_tree_guards_the_empty_case_and_tests_it() -> None:
    service, _ = _seeded_service(0)

    stats = service.filesystem.read_text(STATS_PATH)
    suite = service.filesystem.read_text(SCRATCH / "tests" / "test_stats.py")

    assert "def average(items: list[int]) -> float:" in stats
    assert "    if not items:\n        return 0.0\n" in stats
    assert "assert average([]) == 0.0" in suite


def test_regression_pr_deletes_a_guard_that_already_exists_on_base() -> None:
    service, runner = _seeded_service(4)
    base_stats = service.filesystem.read_text(STATS_PATH)

    pull_request = service._create_regression_pr(SCRATCH, SCRATCH_REPOSITORY)

    head_stats = service.filesystem.read_text(STATS_PATH)
    assert "    if not items:\n        return 0.0\n" in base_stats
    assert "def average(items: list[int]) -> float:" in head_stats
    assert "if not items:" not in head_stats
    assert pull_request.branch == "acceptance/average-drops-empty-input-guard"
    assert all("plant" not in " ".join(call[0]).lower() for call in runner.calls)


def test_new_code_pr_adds_a_helper_that_is_absent_on_base() -> None:
    service, _ = _seeded_service(5)
    base_stats = service.filesystem.read_text(STATS_PATH)

    pull_request = service._create_new_code_pr(SCRATCH, SCRATCH_REPOSITORY)

    head_stats = service.filesystem.read_text(STATS_PATH)
    assert "truncate" not in base_stats
    assert "def truncate(text: str, limit: int) -> str:" in head_stats
    assert 'return text[:limit] + "..."' in head_stats
    # only the added symbol differs, so the base run can fail for exactly one
    # reason: the symbol does not exist there
    assert base_stats in head_stats
    assert pull_request.branch == "acceptance/new-truncate-helper"


def test_control_pr_carries_every_base_behaviour_through_unchanged() -> None:
    service, _ = _seeded_service(5)

    service._create_control_pr(SCRATCH, SCRATCH_REPOSITORY)

    head_stats = service.filesystem.read_text(STATS_PATH)
    assert "values = tuple(items)" in head_stats
    assert "    if not items:\n        return 0.0\n" in head_stats
    assert "truncate" not in head_stats


def test_source_repository_secret_uses_gh_token_only_through_stdin() -> None:
    source_token = "github_pat_source_repo_capable_0123456789"
    runner = FakeRunner([CommandResult(0), CommandResult(0)])
    service = AcceptanceService(
        runner=runner,
        filesystem=MemoryFileSystem({}),
        environ={
            MODEL_KEY_ENV: "sk-ant-test-012345678901234567890123456789",
            "GH_TOKEN": source_token,
        },
        workspace=Path("/workspace"),
    )

    service._install_secrets("octocat/attest-phase3-test")

    model_call, source_call = runner.calls
    assert model_call[0] == (
        "gh",
        "secret",
        "set",
        MODEL_KEY_ENV,
        "--repo",
        "octocat/attest-phase3-test",
    )
    assert source_call[0] == (
        "gh",
        "secret",
        "set",
        TEST_SOURCE_TOKEN_SECRET,
        "--repo",
        "octocat/attest-phase3-test",
    )
    assert model_call[1] == service.environ[MODEL_KEY_ENV]
    assert source_call[1] == source_token
    assert source_token not in " ".join(source_call[0])


def test_source_repository_secret_falls_back_to_authenticated_gh_token() -> None:
    source_token = "github_pat_from_gh_auth_0123456789"
    runner = FakeRunner(
        [CommandResult(0), CommandResult(0, stdout=source_token + "\n"), CommandResult(0)]
    )
    service = _service(runner)

    service._install_secrets("octocat/attest-phase3-test")

    assert runner.calls[1] == (("gh", "auth", "token"), None, None)
    assert runner.calls[2][0][3] == TEST_SOURCE_TOKEN_SECRET
    assert runner.calls[2][1] == source_token
    assert source_token not in " ".join(runner.calls[2][0])


def test_scratch_workflow_uses_source_secret_for_cross_repository_checkout() -> None:
    workflow = _workflow_text("feature/phase-3-action")
    source_checkout = workflow.split("- name: Check out action", 1)[1].split(
        "- name: Review pull request", 1
    )[0]

    assert f"token: ${{{{ secrets.{TEST_SOURCE_TOKEN_SECRET} }}}}" in source_checkout
    assert "secrets.GITHUB_TOKEN" not in source_checkout
    assert "persist-credentials: false" in source_checkout


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
            "body": (
                "Crash on empty input\nFinding ID: fba33419e5\n"
                "Evidence purchases: S x2.64; V x20.00"
            ),
            "path": "sample/stats.py",
            "line": 3,
        },
        {"id": 22, "body": "ordinary review", "path": "README.md", "line": 1},
    ]

    comments = classify_comments(issue_comments, review_comments)

    assert [comment["id"] for comment in comments.sticky] == [11]
    assert [comment["id"] for comment in comments.findings] == [21]
    assert comments.finding_ids == ("fba33419e5",)


def test_comment_classification_rejects_malformed_api_payload() -> None:
    with pytest.raises(AcceptanceError, match="issue comment"):
        classify_comments([{"id": 11}], [])


def test_comment_classification_rejects_verified_finding_without_stable_id() -> None:
    review_comment = {
        "id": 21,
        "body": "Crash on empty input\nEvidence purchases: S x2.64; V x20.00",
        "path": "sample/stats.py",
        "line": 3,
    }

    with pytest.raises(AcceptanceError, match="finding ID"):
        classify_comments([], [review_comment])


def _ledger_text(
    *,
    phases: tuple[str, ...] = REGRESSION_COMMENT_PHASES,
    task_id: str = "task-1",
    review_id: str = "finding-1",
    verification_id: str = "finding-1",
    comment_outcome: str = "posted",
    evidence_class: str = REGRESSION_EVIDENCE_CLASS,
) -> str:
    rows = [
        {
            "kind": "review",
            "task_id": task_id,
            "finding_id": review_id,
            "spend": 0.012,
            "action": "drawer",
        },
        {
            "kind": "verification",
            "task_id": task_id,
            "finding_id": verification_id,
            "outcome": "reproduced",
            "evidence_class": evidence_class,
        },
        *[
            {
                "kind": "github_comment",
                "task_id": task_id,
                "phase": phase,
                "outcome": comment_outcome,
            }
            for phase in phases
        ],
    ]
    return "\n".join(json.dumps(row) for row in rows)


def test_parse_ledger_validates_json_objects_and_required_event_fields() -> None:
    ledger = parse_ledger(_ledger_text())

    assert ledger.spend_usd == pytest.approx(0.012)
    assert ledger.task_ids == frozenset({"task-1"})
    ledger.assert_event_coverage(
        expected_comment_phases=REGRESSION_COMMENT_PHASES,
        inline_finding_ids=("finding-1",),
    )


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


@pytest.mark.parametrize("missing_phase", REGRESSION_COMMENT_PHASES)
def test_ledger_coverage_rejects_each_missing_regression_comment_phase(missing_phase: str) -> None:
    phases = tuple(phase for phase in REGRESSION_COMMENT_PHASES if phase != missing_phase)
    ledger = parse_ledger(_ledger_text(phases=phases))

    with pytest.raises(AcceptanceError, match="comment phases"):
        ledger.assert_event_coverage(
            expected_comment_phases=REGRESSION_COMMENT_PHASES,
            inline_finding_ids=("finding-1",),
        )


def test_ledger_coverage_rejects_failed_comment_phase() -> None:
    ledger = parse_ledger(_ledger_text(comment_outcome="failed"))

    with pytest.raises(AcceptanceError, match="successful.*comment"):
        ledger.assert_event_coverage(
            expected_comment_phases=REGRESSION_COMMENT_PHASES,
            inline_finding_ids=("finding-1",),
        )


def test_parse_ledger_rejects_foreign_task_row() -> None:
    rows = [json.loads(line) for line in _ledger_text().splitlines()]
    rows[-1]["task_id"] = "foreign-task"

    with pytest.raises(AcceptanceError, match="one common.*task_id"):
        parse_ledger("\n".join(json.dumps(row) for row in rows))


def test_ledger_coverage_rejects_reproduced_foreign_candidate() -> None:
    ledger = parse_ledger(_ledger_text(verification_id="finding-2"))

    with pytest.raises(AcceptanceError, match="verification.*reviewed candidate"):
        ledger.assert_event_coverage(
            expected_comment_phases=REGRESSION_COMMENT_PHASES,
            inline_finding_ids=("finding-1",),
        )


def test_ledger_coverage_rejects_inline_finding_identity_mismatch() -> None:
    ledger = parse_ledger(_ledger_text())

    with pytest.raises(AcceptanceError, match="inline finding.*ledger"):
        ledger.assert_event_coverage(
            expected_comment_phases=REGRESSION_COMMENT_PHASES,
            inline_finding_ids=("finding-2",),
        )


def test_ledger_coverage_rejects_duplicate_inline_finding_count() -> None:
    ledger = parse_ledger(_ledger_text())

    with pytest.raises(AcceptanceError, match="inline finding.*ledger"):
        ledger.assert_event_coverage(
            expected_comment_phases=REGRESSION_COMMENT_PHASES,
            inline_finding_ids=("finding-1", "finding-1"),
        )


def test_ledger_coverage_allows_reproduced_overflow_without_inline_placement() -> None:
    rows = [json.loads(line) for line in _ledger_text().splitlines()]
    rows.insert(
        1,
        {
            "kind": "review",
            "task_id": "task-1",
            "finding_id": "finding-overflow",
            "spend": 0.001,
            "action": "drawer",
        },
    )
    rows.insert(
        3,
        {
            "kind": "verification",
            "task_id": "task-1",
            "finding_id": "finding-overflow",
            "outcome": "reproduced",
        },
    )
    ledger = parse_ledger("\n".join(json.dumps(row) for row in rows))

    ledger.assert_event_coverage(
        expected_comment_phases=REGRESSION_COMMENT_PHASES,
        inline_finding_ids=("finding-1",),
    )


def _control_ledger_text() -> str:
    return "\n".join(
        json.dumps(
            {
                "kind": "github_comment",
                "task_id": "task-control",
                "phase": phase,
                "outcome": "posted",
            }
        )
        for phase in CONTROL_COMMENT_PHASES
    )


def test_control_ledger_requires_exact_non_review_comment_phases() -> None:
    ledger = parse_ledger(_control_ledger_text())

    ledger.assert_event_coverage(
        expected_comment_phases=CONTROL_COMMENT_PHASES,
        inline_finding_ids=(),
    )


def _new_code_ledger_text(
    *,
    task_id: str = "task-new-code",
    finding_id: str = "finding-new",
    evidence_class: str = NEW_CODE_EVIDENCE_CLASS,
    outcome: str = "deferred",
    phases: tuple[str, ...] = NEW_CODE_COMMENT_PHASES,
) -> str:
    rows: list[dict[str, object]] = [
        {
            "kind": "review",
            "task_id": task_id,
            "finding_id": finding_id,
            "spend": 0.009,
            "action": "drawer",
        },
        {
            "kind": "verification",
            "task_id": task_id,
            "finding_id": finding_id,
            "outcome": outcome,
            "evidence_class": evidence_class,
            "reason": "new-code candidate: symbol absent on base; not priced",
        },
        *[
            {"kind": "github_comment", "task_id": task_id, "phase": phase, "outcome": "posted"}
            for phase in phases
        ],
        {
            "kind": "ci_final",
            "task_id": task_id,
            "decisions": [
                {"finding_id": finding_id, "action": "drawer", "placement": "drawer"}
            ],
            "spend_usd": 0.011,
        },
    ]
    return "\n".join(json.dumps(row) for row in rows)


def test_new_code_ledger_records_recognised_but_unpriced_candidate() -> None:
    ledger = parse_ledger(_new_code_ledger_text())

    ledger.assert_event_coverage(
        expected_comment_phases=NEW_CODE_COMMENT_PHASES, inline_finding_ids=()
    )
    ledger.assert_new_code_recorded()
    assert ledger.evidence_class_of("finding-new") == NEW_CODE_EVIDENCE_CLASS


def test_new_code_assertion_rejects_a_ledger_that_never_saw_the_defect() -> None:
    ledger = parse_ledger(_new_code_ledger_text(evidence_class="not_reproduced"))

    with pytest.raises(AcceptanceError, match="missed rather than deliberately"):
        ledger.assert_new_code_recorded()


def test_new_code_assertion_rejects_a_priced_new_code_row() -> None:
    ledger = parse_ledger(_new_code_ledger_text(outcome="reproduced"))

    with pytest.raises(AcceptanceError, match="deferred and unpriced"):
        ledger.assert_new_code_recorded()


def test_new_code_arm_requires_the_deferred_status_phase_sequence() -> None:
    ledger = parse_ledger(
        _new_code_ledger_text(phases=("running", "candidate_count", "complete"))
    )

    with pytest.raises(AcceptanceError, match="comment phases"):
        ledger.assert_event_coverage(
            expected_comment_phases=NEW_CODE_COMMENT_PHASES, inline_finding_ids=()
        )


def test_inline_finding_must_be_bought_by_regression_evidence() -> None:
    ledger = parse_ledger(_ledger_text())

    ledger.assert_regression_evidence(("finding-1",))
    assert ledger.evidence_class_of("finding-1") == REGRESSION_EVIDENCE_CLASS


@pytest.mark.parametrize("recorded", [NEW_CODE_EVIDENCE_CLASS, "unfaithful"])
def test_inline_finding_with_other_evidence_class_is_rejected(recorded: str) -> None:
    ledger = parse_ledger(_ledger_text(evidence_class=recorded))

    with pytest.raises(AcceptanceError, match="evidence class"):
        ledger.assert_regression_evidence(("finding-1",))


def test_inline_finding_without_any_evidence_class_is_rejected() -> None:
    rows = [json.loads(line) for line in _ledger_text().splitlines()]
    del rows[1]["evidence_class"]
    ledger = parse_ledger("\n".join(json.dumps(row) for row in rows))

    with pytest.raises(AcceptanceError, match="evidence class None"):
        ledger.assert_regression_evidence(("finding-1",))


def test_parse_ledger_rejects_non_string_evidence_class() -> None:
    rows = [json.loads(line) for line in _ledger_text().splitlines()]
    rows[1]["evidence_class"] = 7

    with pytest.raises(AcceptanceError, match="evidence_class"):
        parse_ledger("\n".join(json.dumps(row) for row in rows))


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


def _matrix_run(
    ledger_text: str,
    *,
    run_id: int,
    finding_ids: tuple[str, ...] = (),
    sticky_seconds: float = 1.0,
) -> _WorkflowRun:
    findings = tuple(
        {"id": index, "body": finding_id, "path": "sample/stats.py", "line": 3}
        for index, finding_id in enumerate(finding_ids, start=100)
    )
    return _WorkflowRun(
        run_id=run_id,
        url=f"https://github.invalid/actions/runs/{run_id}",
        created_at="2026-08-29T00:00:00Z",
        job_started_at="2026-08-29T00:00:01Z",
        queue_seconds=1.0,
        sticky_seconds=sticky_seconds,
        comments=CommentClassification(
            sticky=({"id": 1, "body": "<!-- attest:status -->"},),
            findings=findings,
            finding_ids=finding_ids,
        ),
        ledger=parse_ledger(ledger_text),
    )


def _matrix_arms() -> tuple[_WorkflowRun, _WorkflowRun, _WorkflowRun]:
    return (
        _matrix_run(
            _ledger_text(), run_id=101, finding_ids=("finding-1",), sticky_seconds=12.5
        ),
        _matrix_run(_control_ledger_text(), run_id=102, sticky_seconds=8.0),
        _matrix_run(_new_code_ledger_text(), run_id=103, sticky_seconds=5.25),
    )


def test_matrix_accepts_verified_regression_silent_control_and_recorded_new_code() -> None:
    AcceptanceService._assert_matrix(*_matrix_arms())


def test_matrix_requires_a_verified_inline_finding_on_the_regression_arm() -> None:
    regression, control, new_code = _matrix_arms()
    silent = _matrix_run(_ledger_text(phases=CONTROL_COMMENT_PHASES), run_id=101)

    with pytest.raises(AcceptanceError, match="regression PR has no verified inline finding"):
        AcceptanceService._assert_matrix(silent, control, new_code)


def test_matrix_rejects_a_speaking_negative_control() -> None:
    regression, _, new_code = _matrix_arms()
    noisy = _matrix_run(_ledger_text(), run_id=102, finding_ids=("finding-1",))

    with pytest.raises(AcceptanceError, match="negative-control PR unexpectedly"):
        AcceptanceService._assert_matrix(regression, noisy, new_code)


def test_matrix_rejects_a_priced_finding_on_the_new_code_arm() -> None:
    regression, control, _ = _matrix_arms()
    noisy = _matrix_run(
        _new_code_ledger_text(finding_id="finding-new"),
        run_id=103,
        finding_ids=("finding-new",),
    )

    with pytest.raises(AcceptanceError, match="new-code PR unexpectedly"):
        AcceptanceService._assert_matrix(regression, control, noisy)


def test_matrix_rejects_a_new_code_arm_that_never_recorded_the_class() -> None:
    regression, control, _ = _matrix_arms()
    unaware = _matrix_run(
        _new_code_ledger_text(evidence_class="not_reproduced"), run_id=103
    )

    with pytest.raises(AcceptanceError, match="missed rather than deliberately"):
        AcceptanceService._assert_matrix(regression, control, unaware)


def test_matrix_rejects_an_inline_finding_not_bought_by_regression_evidence() -> None:
    _, control, new_code = _matrix_arms()
    mispriced = _matrix_run(
        _ledger_text(evidence_class=NEW_CODE_EVIDENCE_CLASS),
        run_id=101,
        finding_ids=("finding-1",),
    )

    with pytest.raises(AcceptanceError, match="evidence class"):
        AcceptanceService._assert_matrix(mispriced, control, new_code)


@pytest.mark.parametrize(
    ("index", "label"), [(0, "regression"), (1, "negative-control"), (2, "new-code")]
)
def test_matrix_holds_every_arm_to_the_sixty_second_sticky_limit(
    index: int, label: str
) -> None:
    arms = list(_matrix_arms())
    slow = arms[index]
    arms[index] = _matrix_run(
        (_ledger_text(), _control_ledger_text(), _new_code_ledger_text())[index],
        run_id=slow.run_id,
        finding_ids=slow.comments.finding_ids,
        sticky_seconds=60.001,
    )

    with pytest.raises(AcceptanceError, match=f"{label} sticky status"):
        AcceptanceService._assert_matrix(*arms)


def _workflow_run(run_id: int, spend: float) -> _WorkflowRun:
    return _WorkflowRun(
        run_id=run_id,
        url=f"https://github.invalid/actions/runs/{run_id}",
        created_at="2026-08-29T00:00:00Z",
        job_started_at="2026-08-29T00:00:01Z",
        queue_seconds=1.0,
        sticky_seconds=1.0,
        comments=CommentClassification((), (), ()),
        ledger=LedgerArtifact(
            (
                {
                    "kind": "ci_final",
                    "task_id": f"task-{run_id}",
                    "decisions": [],
                    "spend_usd": spend,
                },
            )
        ),
    )


def _acceptance_orchestrator(
    monkeypatch: pytest.MonkeyPatch, runs: list[_WorkflowRun | Exception]
) -> AcceptanceService:
    spend_path = Path("/workspace/DEVSPEND.md")
    service = _service(
        FakeRunner([]),
        files={spend_path: "**Total API spend: $0.0000 of $10.00.**\n"},
    )
    monkeypatch.setattr(service, "preflight", lambda: None)
    monkeypatch.setattr(service, "_json_command", lambda *args: {"login": "octocat"})
    monkeypatch.setattr(service, "_checked", lambda *args, **kwargs: CommandResult(0))
    monkeypatch.setattr(service, "_seed_repository", lambda *args: None)
    monkeypatch.setattr(service, "_install_secrets", lambda *args: None)
    monkeypatch.setattr(
        service,
        "_create_regression_pr",
        lambda *args: _PullRequest(1, "https://github.invalid/pull/1", "regression"),
    )
    monkeypatch.setattr(
        service,
        "_create_control_pr",
        lambda *args: _PullRequest(2, "https://github.invalid/pull/2", "control"),
    )
    monkeypatch.setattr(
        service,
        "_create_new_code_pr",
        lambda *args: _PullRequest(3, "https://github.invalid/pull/3", "new-code"),
    )

    def inspect(*args: object) -> _WorkflowRun:
        value = runs.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(service, "_inspect_run", inspect)
    return service


def test_acceptance_records_first_artifact_spend_when_second_run_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _acceptance_orchestrator(
        monkeypatch, [_workflow_run(101, 0.03), AcceptanceError("second run failed")]
    )

    with pytest.raises(AcceptanceError, match="second run"):
        service.run_acceptance("local-ref")

    ledger = service.filesystem.read_text(Path("/workspace/DEVSPEND.md"))
    assert "phase-3 acceptance run 101" in ledger
    assert "phase-3 acceptance run 102" not in ledger


def test_acceptance_records_every_artifact_spend_before_matrix_assertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _acceptance_orchestrator(
        monkeypatch,
        [_workflow_run(101, 0.03), _workflow_run(102, 0.02), _workflow_run(103, 0.01)],
    )
    monkeypatch.setattr(
        service,
        "_assert_matrix",
        lambda *args: (_ for _ in ()).throw(AcceptanceError("matrix failed")),
    )

    with pytest.raises(AcceptanceError, match="matrix"):
        service.run_acceptance("local-ref")

    ledger = service.filesystem.read_text(Path("/workspace/DEVSPEND.md"))
    for run_id in (101, 102, 103):
        assert ledger.count(f"phase-3 acceptance run {run_id}") == 1


def test_acceptance_reports_all_three_arms_on_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _acceptance_orchestrator(monkeypatch, list(_matrix_arms()))

    result = service.run_acceptance("local-ref")

    assert result.regression_pr_url == "https://github.invalid/pull/1"
    assert result.control_pr_url == "https://github.invalid/pull/2"
    assert result.new_code_pr_url == "https://github.invalid/pull/3"
    assert set(result.queue_seconds) == {101, 102, 103}
    assert result.new_code_sticky_seconds == 5.25
    assert result.spend_usd == pytest.approx(0.023)
    report = service.filesystem.read_text(Path("/workspace/docs/acceptance/phase-3.md"))
    assert NEW_CODE_EVIDENCE_CLASS in report


def test_report_describes_three_arms_with_inspectable_urls() -> None:
    result = AcceptanceResult(
        repository_url="https://github.com/octocat/attest-phase3-20260829",
        regression_pr_url="https://github.com/octocat/attest-phase3-20260829/pull/1",
        control_pr_url="https://github.com/octocat/attest-phase3-20260829/pull/2",
        new_code_pr_url="https://github.com/octocat/attest-phase3-20260829/pull/3",
        regression_sticky_seconds=12.5,
        control_sticky_seconds=8.0,
        new_code_sticky_seconds=5.25,
        queue_seconds={101: 4.25, 102: 1.5, 103: 2.0},
        spend_usd=0.0345,
        run_urls={
            run_id: f"https://github.com/octocat/attest-phase3-20260829/actions/runs/{run_id}"
            for run_id in (101, 102, 103)
        },
    )

    report = render_report(result)

    assert "https://github.com/octocat/attest-phase3-20260829" in report
    assert result.regression_pr_url in report
    assert result.control_pr_url in report
    assert result.new_code_pr_url in report
    for run_id in (101, 102, 103):
        assert result.run_urls[run_id] in report
    assert "12.500s" in report
    assert "5.250s" in report
    assert "$0.0345" in report
    assert REGRESSION_EVIDENCE_CLASS in report
    assert NEW_CODE_EVIDENCE_CLASS in report
    assert "not priced" in report
    assert "recognised" in report
