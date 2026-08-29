#!/usr/bin/env python3
"""Drive and verify Phase 3 acceptance in an owner-controlled scratch repository.

The acceptance policy is kept in :class:`AcceptanceService`; subprocess and
filesystem effects are adapters so local tests never contact GitHub or expose a
credential.  The executable path is intentionally opt-in and retains the
private repository whenever an assertion fails.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

STATUS_MARKER = "<!-- attest:status -->"
SPEND_CAP_USD = 10.0
MODEL_KEY_ENV = "ANTHROPIC_API_KEY"
SOURCE_TOKEN_SECRET = "ATTEST_SOURCE_TOKEN"
MODEL_KEY_PREFIX = "sk-ant-"
MIN_MODEL_KEY_LENGTH = 24
SCRATCH_PREFIX = "attest-phase3-"
SOURCE_REPOSITORY = "IcantFind-a-username/Attest"
BUG_COMMENT_PHASES = ("running", "candidate_count", "review", "complete")
CONTROL_COMMENT_PHASES = ("running", "candidate_count", "complete")


class AcceptanceError(RuntimeError):
    """A sanitized local or remote acceptance failure."""


class PreflightError(AcceptanceError):
    """A sanitized missing-prerequisite failure."""


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str | None = None,
        cwd: Path | None = None,
    ) -> CommandResult: ...


class FileSystem(Protocol):
    def read_text(self, path: Path) -> str: ...

    def write_text(self, path: Path, text: str) -> None: ...

    def exists(self, path: Path) -> bool: ...

    def mkdir(self, path: Path) -> None: ...


class SubprocessRunner:
    """Subprocess adapter that never invokes a shell or logs command input."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = dict(os.environ if environ is None else environ)
        self._environ["GIT_TERMINAL_PROMPT"] = "0"

    def run(
        self,
        args: tuple[str, ...],
        *,
        input_text: str | None = None,
        cwd: Path | None = None,
    ) -> CommandResult:
        completed = subprocess.run(
            list(args),
            cwd=cwd,
            input=input_text,
            text=True,
            capture_output=True,
            check=False,
            env=self._environ,
        )
        return CommandResult(completed.returncode, completed.stdout, completed.stderr)


class LocalFileSystem:
    def read_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def write_text(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def exists(self, path: Path) -> bool:
        return path.exists()

    def mkdir(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AcceptanceResult:
    repository_url: str
    bug_pr_url: str
    control_pr_url: str
    bug_sticky_seconds: float
    control_sticky_seconds: float
    queue_seconds: dict[int, float]
    spend_usd: float
    run_urls: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CommentClassification:
    sticky: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    finding_ids: tuple[str, ...]


@dataclass(frozen=True)
class LedgerArtifact:
    rows: tuple[dict[str, Any], ...]

    @property
    def task_ids(self) -> frozenset[str]:
        return frozenset(
            str(row["task_id"])
            for row in self.rows
            if isinstance(row.get("task_id"), str) and row["task_id"]
        )

    @property
    def spend_usd(self) -> float:
        review_runs = [
            float(row["spend_usd"])
            for row in self.rows
            if row.get("kind") == "review_run" and _is_number(row.get("spend_usd"))
        ]
        if review_runs:
            return round(sum(review_runs), 6)
        return round(
            sum(
                float(row["spend"])
                for row in self.rows
                if row.get("kind") == "review" and _is_number(row.get("spend"))
            ),
            6,
        )

    def assert_event_coverage(
        self,
        *,
        expected_comment_phases: tuple[str, ...],
        inline_finding_ids: Sequence[str],
    ) -> None:
        review_rows = [row for row in self.rows if row.get("kind") == "review"]
        verification_rows = [row for row in self.rows if row.get("kind") == "verification"]
        comment_rows = [row for row in self.rows if row.get("kind") == "github_comment"]
        if any(row.get("outcome") != "posted" for row in comment_rows):
            raise AcceptanceError("ledger requires successful GitHub comment rows")
        phases = tuple(str(row["phase"]) for row in comment_rows)
        if phases != expected_comment_phases:
            raise AcceptanceError(
                f"ledger comment phases {phases!r} do not match {expected_comment_phases!r}"
            )

        reviewed_ids = {str(row["finding_id"]) for row in review_rows}
        reproduced_ids = {
            str(row["finding_id"])
            for row in verification_rows
            if row.get("outcome") == "reproduced"
        }
        if not reproduced_ids.issubset(reviewed_ids):
            raise AcceptanceError("ledger verification references an unreviewed candidate")

        surfaced_ids = {
            str(row["finding_id"])
            for row in review_rows
            if str(row.get("action", "")).endswith("surface")
        }
        inline_ids = tuple(inline_finding_ids)
        if len(inline_ids) != len(set(inline_ids)) or set(inline_ids) != surfaced_ids:
            raise AcceptanceError("inline finding identities do not match surfaced ledger rows")
        if not set(inline_ids).issubset(reproduced_ids):
            raise AcceptanceError("inline finding lacks reproduced verification evidence")


@dataclass(frozen=True)
class _PullRequest:
    number: int
    url: str
    branch: str


@dataclass(frozen=True)
class _WorkflowRun:
    run_id: int
    url: str
    created_at: str
    job_started_at: str
    queue_seconds: float
    sticky_seconds: float
    comments: CommentClassification
    ledger: LedgerArtifact


@dataclass
class AcceptanceService:
    runner: CommandRunner
    filesystem: FileSystem
    environ: Mapping[str, str]
    workspace: Path
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    sleeper: Callable[[float], None] = time.sleep

    def preflight(self) -> None:
        try:
            auth = self.runner.run(("gh", "auth", "status"))
        except FileNotFoundError:
            raise PreflightError("GitHub CLI is not installed or is not on PATH") from None
        if auth.returncode != 0:
            raise PreflightError("GitHub CLI is not authenticated")
        auth_summary = f"{auth.stdout}\n{auth.stderr}".lower()
        if "repo" not in auth_summary or "workflow" not in auth_summary:
            raise PreflightError("GitHub authentication requires repo and workflow scopes")

        key = self.environ.get(MODEL_KEY_ENV, "")
        if len(key) < MIN_MODEL_KEY_LENGTH or not key.startswith(MODEL_KEY_PREFIX):
            raise PreflightError(
                "model API key is missing or fails the required length/prefix check"
            )

    def record_spend(self, run_id: str, spend_usd: float, repository_url: str) -> None:
        if spend_usd < 0:
            raise AcceptanceError("acceptance spend cannot be negative")
        path = self.workspace / "DEVSPEND.md"
        if not self.filesystem.exists(path):
            raise AcceptanceError("DEVSPEND.md is missing")
        original = self.filesystem.read_text(path)
        marker = f"phase-3 acceptance run {run_id}"
        if marker in original:
            return
        match = _spend_total_match(original)
        current = float(match.group(1))
        updated_total = current + spend_usd
        if updated_total > SPEND_CAP_USD + 1e-9:
            raise AcceptanceError(
                f"$10.00 development spend cap would be exceeded (${updated_total:.4f})"
            )
        row = (
            f"| {self.clock().date().isoformat()} | {marker} ({repository_url}) "
            f"| ${spend_usd:.4f} |\n"
        )
        total_line_start = match.start()
        prefix = original[:total_line_start]
        if not prefix.endswith("\n\n"):
            prefix = prefix.rstrip("\n") + "\n\n"
        updated = (
            prefix
            + row
            + "\n"
            + f"**Total API spend: ${updated_total:.4f} of $10.00.**"
            + original[match.end() :]
        )
        self.filesystem.write_text(path, updated)

    def ensure_spend_headroom(self, reserved_usd: float) -> None:
        if reserved_usd < 0:
            raise AcceptanceError("reserved acceptance spend cannot be negative")
        path = self.workspace / "DEVSPEND.md"
        if not self.filesystem.exists(path):
            raise AcceptanceError("DEVSPEND.md is missing")
        current = float(_spend_total_match(self.filesystem.read_text(path)).group(1))
        if current + reserved_usd > SPEND_CAP_USD + 1e-9:
            raise AcceptanceError(
                f"$10.00 development spend cap lacks ${reserved_usd:.2f} acceptance headroom"
            )

    def run_acceptance(self, action_ref: str, *, keep_repo: bool = True) -> AcceptanceResult:
        self.preflight()
        self.ensure_spend_headroom(0.50)
        if not action_ref.strip():
            raise AcceptanceError("action ref must not be empty")
        owner = self._json_command(("gh", "api", "user"), "authenticated owner").get("login")
        if not isinstance(owner, str) or not owner:
            raise AcceptanceError("GitHub API returned an invalid authenticated owner")

        stamp = self.clock().strftime("%Y%m%d-%H%M%S")
        repository = f"{owner}/{SCRATCH_PREFIX}{stamp}-{uuid.uuid4().hex[:6]}"
        repository_url = f"https://github.com/{repository}"
        created = False
        try:
            self._checked(build_private_repo_command(owner, repository.split("/", 1)[1]))
            created = True
            with tempfile.TemporaryDirectory(prefix="attest-phase3-") as raw_checkout:
                checkout = Path(raw_checkout)
                self._seed_repository(checkout, repository, action_ref)
                self._install_secrets(repository)
                bug_pr = self._create_bug_pr(checkout, repository)
                control_pr = self._create_control_pr(checkout, repository)
                bug_run = self._inspect_run(repository, bug_pr, checkout / "artifacts")
                control_run = self._inspect_run(repository, control_pr, checkout / "artifacts")
                self._assert_matrix(bug_run, control_run)

                result = AcceptanceResult(
                    repository_url=repository_url,
                    bug_pr_url=bug_pr.url,
                    control_pr_url=control_pr.url,
                    bug_sticky_seconds=bug_run.sticky_seconds,
                    control_sticky_seconds=control_run.sticky_seconds,
                    queue_seconds={
                        bug_run.run_id: bug_run.queue_seconds,
                        control_run.run_id: control_run.queue_seconds,
                    },
                    spend_usd=round(
                        bug_run.ledger.spend_usd + control_run.ledger.spend_usd, 6
                    ),
                    run_urls={bug_run.run_id: bug_run.url, control_run.run_id: control_run.url},
                )
                self._record_live_success(
                    result,
                    {
                        bug_run.run_id: bug_run.ledger.spend_usd,
                        control_run.run_id: control_run.ledger.spend_usd,
                    },
                )
                if not keep_repo:
                    self._checked(("gh", "repo", "delete", repository, "--yes"))
                return result
        except Exception:
            if created:
                print(
                    f"Acceptance failed; retained private repository: {repository_url}",
                    file=sys.stderr,
                )
            raise

    def _record_live_success(
        self, result: AcceptanceResult, spend_by_run: Mapping[int, float]
    ) -> None:
        existing = self.filesystem.read_text(self.workspace / "DEVSPEND.md")
        current_match = _spend_total_match(existing)
        unrecorded = sum(
            spend
            for run_id, spend in spend_by_run.items()
            if f"phase-3 acceptance run {run_id}" not in existing
        )
        if float(current_match.group(1)) + unrecorded > SPEND_CAP_USD + 1e-9:
            raise AcceptanceError("$10.00 development spend cap would be exceeded")
        for run_id, spend in spend_by_run.items():
            self.record_spend(str(run_id), spend, result.repository_url)
        self.filesystem.write_text(
            self.workspace / "docs" / "acceptance" / "phase-3.md", render_report(result)
        )

    def _seed_repository(self, checkout: Path, repository: str, action_ref: str) -> None:
        self.filesystem.mkdir(checkout / ".github" / "workflows")
        self.filesystem.mkdir(checkout / "sample")
        self.filesystem.mkdir(checkout / "tests")
        self.filesystem.write_text(
            checkout / "sample" / "stats.py",
            "def total(items: list[int]) -> int:\n    return sum(items)\n",
        )
        self.filesystem.write_text(checkout / "sample" / "__init__.py", "")
        self.filesystem.write_text(
            checkout / "tests" / "test_stats.py",
            "from sample.stats import total\n\n\n"
            "def test_total() -> None:\n"
            "    assert total([1, 2]) == 3\n",
        )
        self.filesystem.write_text(
            checkout / "pyproject.toml",
            "[project]\nname = \"attest-acceptance-sample\"\nversion = \"0.0.1\"\n"
            "requires-python = \">=3.11\"\n\n[tool.pytest.ini_options]\ntestpaths = [\"tests\"]\n",
        )
        self.filesystem.write_text(
            checkout / ".github" / "workflows" / "attest.yml",
            _workflow_text(action_ref),
        )
        for command in (
            ("git", "init", "-b", "main"),
            ("git", "config", "--local", "credential.https://github.com.helper", ""),
            (
                "git",
                "config",
                "--local",
                "--add",
                "credential.https://github.com.helper",
                "!gh auth git-credential",
            ),
            ("git", "config", "user.email", "attest-acceptance@example.invalid"),
            ("git", "config", "user.name", "Attest Acceptance"),
            ("git", "add", "."),
            ("git", "commit", "-m", "chore: seed acceptance repository"),
            ("git", "remote", "add", "origin", f"https://github.com/{repository}.git"),
            ("git", "push", "-u", "origin", "main"),
        ):
            self._checked(command, cwd=checkout)

    def _install_secrets(self, repository: str) -> None:
        self._checked(
            ("gh", "secret", "set", MODEL_KEY_ENV, "--repo", repository),
            input_text=self.environ[MODEL_KEY_ENV],
        )
        self._checked(
            ("gh", "secret", "set", SOURCE_TOKEN_SECRET, "--repo", repository),
            input_text=self._source_token(),
        )

    def _source_token(self) -> str:
        token = self.environ.get("GH_TOKEN", "").strip()
        if not token:
            token = self._checked(("gh", "auth", "token")).stdout.strip()
        if not token:
            raise AcceptanceError("GitHub source-repository token is unavailable")
        return token

    def _create_bug_pr(self, checkout: Path, repository: str) -> _PullRequest:
        branch = "acceptance/planted-empty-input-crash"
        self._checked(("git", "switch", "-c", branch, "main"), cwd=checkout)
        self.filesystem.write_text(
            checkout / "sample" / "stats.py",
            "def total(items: list[int]) -> int:\n    return sum(items)\n\n\n"
            "def average(items: list[int]) -> float:\n    return sum(items) / len(items)\n",
        )
        self._checked(("git", "add", "sample/stats.py"), cwd=checkout)
        self._checked(("git", "commit", "-m", "test: plant empty input crash"), cwd=checkout)
        self._checked(("git", "push", "-u", "origin", branch), cwd=checkout)
        return self._open_pr(repository, branch, "Plant deterministic empty-input crash")

    def _create_control_pr(self, checkout: Path, repository: str) -> _PullRequest:
        branch = "acceptance/clean-refactor"
        self._checked(("git", "switch", "main"), cwd=checkout)
        self._checked(("git", "switch", "-c", branch), cwd=checkout)
        self.filesystem.write_text(
            checkout / "sample" / "stats.py",
            "def total(items: list[int]) -> int:\n"
            "    values = tuple(items)\n"
            "    return sum(values)\n",
        )
        self._checked(("git", "add", "sample/stats.py"), cwd=checkout)
        self._checked(("git", "commit", "-m", "refactor: name materialized values"), cwd=checkout)
        self._checked(("git", "push", "-u", "origin", branch), cwd=checkout)
        return self._open_pr(repository, branch, "Clean refactor control")

    def _open_pr(self, repository: str, branch: str, title: str) -> _PullRequest:
        self._checked(
            (
                "gh",
                "pr",
                "create",
                "--repo",
                repository,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                title,
                "--body",
                "Automated Phase 3 acceptance fixture.",
            )
        )
        payload = self._json_command(
            ("gh", "pr", "view", branch, "--repo", repository, "--json", "number,url"),
            "pull request",
        )
        number = payload.get("number")
        url = payload.get("url")
        if not isinstance(number, int) or not isinstance(url, str):
            raise AcceptanceError("GitHub CLI returned invalid pull-request metadata")
        return _PullRequest(number, url, branch)

    def _inspect_run(
        self, repository: str, pull_request: _PullRequest, artifact_root: Path
    ) -> _WorkflowRun:
        run = self._wait_for_run(repository, pull_request.branch)
        run_id = run.get("databaseId")
        if not isinstance(run_id, int):
            raise AcceptanceError("workflow run metadata is missing databaseId")
        self._checked(("gh", "run", "watch", str(run_id), "--repo", repository, "--exit-status"))

        jobs = self._json_command(
            ("gh", "api", f"repos/{repository}/actions/runs/{run_id}/jobs"),
            "workflow jobs",
        ).get("jobs")
        if not isinstance(jobs, list) or not jobs or not isinstance(jobs[0], dict):
            raise AcceptanceError("workflow run has no job metadata")
        job_started_at = jobs[0].get("started_at")
        created_at = run.get("createdAt")
        run_url = run.get("url")
        if not all(isinstance(value, str) for value in (job_started_at, created_at, run_url)):
            raise AcceptanceError("workflow run timestamps or URL are invalid")

        issue_comments = self._json_list_command(
            ("gh", "api", f"repos/{repository}/issues/{pull_request.number}/comments"),
            "issue comments",
        )
        review_comments = self._json_list_command(
            ("gh", "api", f"repos/{repository}/pulls/{pull_request.number}/comments"),
            "review comments",
        )
        comments = classify_comments(issue_comments, review_comments)
        if not comments.sticky:
            raise AcceptanceError(f"PR {pull_request.number} has no sticky status comment")
        first_sticky_at = min(str(comment["created_at"]) for comment in comments.sticky)

        destination = artifact_root / str(run_id)
        self.filesystem.mkdir(destination)
        artifact_name = f"attest-ledger-pr-{pull_request.number}-run-{run_id}"
        self._checked(
            (
                "gh",
                "run",
                "download",
                str(run_id),
                "--repo",
                repository,
                "--name",
                artifact_name,
                "--dir",
                str(destination),
            )
        )
        ledger_path = destination / "ledger.jsonl"
        if not self.filesystem.exists(ledger_path):
            nested = destination / ".attest" / "ledger.jsonl"
            ledger_path = nested if self.filesystem.exists(nested) else ledger_path
        if not self.filesystem.exists(ledger_path):
            raise AcceptanceError(f"workflow run {run_id} ledger artifact is missing")
        return _WorkflowRun(
            run_id=run_id,
            url=str(run_url),
            created_at=str(created_at),
            job_started_at=str(job_started_at),
            queue_seconds=sticky_seconds(str(created_at), str(job_started_at)),
            sticky_seconds=sticky_seconds(str(job_started_at), first_sticky_at),
            comments=comments,
            ledger=parse_ledger(self.filesystem.read_text(ledger_path)),
        )

    def _wait_for_run(self, repository: str, branch: str) -> dict[str, Any]:
        for _ in range(60):
            result = self._checked(
                (
                    "gh",
                    "run",
                    "list",
                    "--repo",
                    repository,
                    "--branch",
                    branch,
                    "--workflow",
                    "attest.yml",
                    "--limit",
                    "1",
                    "--json",
                    "databaseId,createdAt,url",
                )
            )
            try:
                payload = json.loads(result.stdout)
            except json.JSONDecodeError:
                raise AcceptanceError("GitHub CLI returned invalid workflow-run JSON") from None
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                return payload[0]
            self.sleeper(2.0)
        raise AcceptanceError(f"workflow run did not appear for branch {branch}")

    @staticmethod
    def _assert_matrix(bug_run: _WorkflowRun, control_run: _WorkflowRun) -> None:
        if bug_run.sticky_seconds > 60:
            raise AcceptanceError(
                f"planted-bug sticky status took {bug_run.sticky_seconds:.3f}s (limit 60s)"
            )
        if control_run.sticky_seconds > 60:
            raise AcceptanceError(
                f"control sticky status took {control_run.sticky_seconds:.3f}s (limit 60s)"
            )
        if not bug_run.comments.findings:
            raise AcceptanceError("planted-bug PR has no verified inline finding")
        if control_run.comments.findings:
            raise AcceptanceError("negative-control PR unexpectedly has finding comments")
        bug_run.ledger.assert_event_coverage(
            expected_comment_phases=BUG_COMMENT_PHASES,
            inline_finding_ids=bug_run.comments.finding_ids,
        )
        control_run.ledger.assert_event_coverage(
            expected_comment_phases=CONTROL_COMMENT_PHASES,
            inline_finding_ids=control_run.comments.finding_ids,
        )

    def _checked(
        self,
        args: tuple[str, ...],
        *,
        input_text: str | None = None,
        cwd: Path | None = None,
    ) -> CommandResult:
        try:
            result = self.runner.run(args, input_text=input_text, cwd=cwd)
        except FileNotFoundError:
            raise AcceptanceError(f"required executable is unavailable: {args[0]}") from None
        if result.returncode != 0:
            raise AcceptanceError(f"command failed: {' '.join(args[:3])}")
        return result

    def _json_command(self, args: tuple[str, ...], description: str) -> dict[str, Any]:
        result = self._checked(args)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise AcceptanceError(f"GitHub CLI returned invalid {description} JSON") from None
        if not isinstance(payload, dict):
            raise AcceptanceError(f"GitHub CLI returned invalid {description} JSON")
        return payload

    def _json_list_command(self, args: tuple[str, ...], description: str) -> list[Any]:
        result = self._checked(args)
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            raise AcceptanceError(f"GitHub CLI returned invalid {description} JSON") from None
        if not isinstance(payload, list):
            raise AcceptanceError(f"GitHub CLI returned invalid {description} JSON")
        return payload


def build_private_repo_command(owner: str, name: str) -> tuple[str, ...]:
    """Return the exact no-shell command used to create the retained scratch repo."""
    component = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})\Z")
    if component.fullmatch(owner) is None or component.fullmatch(name) is None:
        raise AcceptanceError("invalid GitHub owner or repository name")
    return ("gh", "repo", "create", f"{owner}/{name}", "--private", "--confirm")


def sticky_seconds(job_started_at: str, comment_created_at: str) -> float:
    """Measure status latency from job start, deliberately excluding runner queue time."""
    started = _parse_timestamp(job_started_at)
    commented = _parse_timestamp(comment_created_at)
    elapsed = (commented - started).total_seconds()
    if elapsed < 0:
        raise AcceptanceError("sticky comment timestamp precedes job start")
    return elapsed


def classify_comments(
    issue_comments: Sequence[object], review_comments: Sequence[object]
) -> CommentClassification:
    sticky: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    finding_ids: list[str] = []
    for raw in issue_comments:
        comment = _comment_object(raw, "issue comment")
        if STATUS_MARKER in comment["body"]:
            if not isinstance(comment.get("created_at"), str):
                raise AcceptanceError("issue comment has invalid created_at")
            sticky.append(comment)
    for raw in review_comments:
        comment = _comment_object(raw, "review comment")
        body = comment["body"]
        if "Evidence purchases:" in body and re.search(r"\bV\s+x20(?:\.0+)?\b", body):
            if not isinstance(comment.get("path"), str) or not isinstance(
                comment.get("line"), int
            ):
                raise AcceptanceError("finding review comment has invalid anchor")
            match = re.search(r"(?:^|\n)Finding ID: ([0-9a-f]{10})(?:\n|$)", body)
            if match is None:
                raise AcceptanceError("verified review comment is missing a stable finding ID")
            findings.append(comment)
            finding_ids.append(match.group(1))
    return CommentClassification(tuple(sticky), tuple(findings), tuple(finding_ids))


def parse_ledger(text: str) -> LedgerArtifact:
    rows: list[dict[str, Any]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            raise AcceptanceError(f"ledger line {number} is invalid JSON") from None
        if not isinstance(raw, dict):
            raise AcceptanceError(f"ledger line {number} is not a JSON object")
        _validate_ledger_row(raw, number)
        rows.append(raw)
    if not rows:
        raise AcceptanceError("ledger artifact is empty")
    artifact = LedgerArtifact(tuple(rows))
    if len(artifact.task_ids) != 1:
        raise AcceptanceError("ledger rows must share one common nonempty task_id")
    return artifact


def render_report(result: AcceptanceResult) -> str:
    lines = [
        "# Phase 3 acceptance",
        "",
        "Acceptance passed against a retained private scratch repository.",
        "",
        f"- Repository: {result.repository_url}",
        f"- Planted-bug PR: {result.bug_pr_url}",
        f"- Negative-control PR: {result.control_pr_url}",
        f"- Planted-bug sticky latency (job start to comment): {result.bug_sticky_seconds:.3f}s",
        f"- Control sticky latency (job start to comment): {result.control_sticky_seconds:.3f}s",
        f"- Development API spend: ${result.spend_usd:.4f}",
        "",
        "## Workflow runs",
        "",
    ]
    for run_id, queue_seconds in sorted(result.queue_seconds.items()):
        url = result.run_urls.get(run_id, f"{result.repository_url}/actions/runs/{run_id}")
        lines.append(f"- Run {run_id}: {url} (runner queue {queue_seconds:.3f}s)")
    lines.extend(
        [
            "",
            "The planted bug produced verified inline evidence, the control produced no finding "
            "comments, both sticky comments met the 60-second job-start limit, and downloaded "
            "ledger artifacts accounted for review, verification, and comment events.",
            "",
        ]
    )
    return "\n".join(lines)


def preflight() -> None:
    _default_service().preflight()


def run_acceptance(action_ref: str, *, keep_repo: bool = True) -> AcceptanceResult:
    return _default_service().run_acceptance(action_ref, keep_repo=keep_repo)


def _default_service() -> AcceptanceService:
    environment = dict(os.environ)
    command_environment = dict(environment)
    command_environment.pop(MODEL_KEY_ENV, None)
    return AcceptanceService(
        runner=SubprocessRunner(command_environment),
        filesystem=LocalFileSystem(),
        environ=environment,
        workspace=Path(__file__).resolve().parents[2],
    )


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AcceptanceError("GitHub API returned an invalid timestamp") from None
    if parsed.tzinfo is None:
        raise AcceptanceError("GitHub API timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _comment_object(raw: object, description: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not isinstance(raw.get("id"), int) or not isinstance(
        raw.get("body"), str
    ):
        raise AcceptanceError(f"{description} payload is malformed")
    return raw


def _validate_ledger_row(row: dict[str, Any], number: int) -> None:
    kind = row.get("kind")
    if not isinstance(kind, str) or not kind:
        raise AcceptanceError(f"ledger line {number} is missing kind")
    event_required = {
        "review": ("task_id", "finding_id", "action"),
        "review_run": ("task_id", "spend_usd"),
        "verification": ("task_id", "finding_id", "outcome"),
        "github_comment": ("task_id", "phase", "outcome"),
    }
    for field_name in event_required.get(kind, ("task_id",)):
        if field_name not in row or row[field_name] in (None, ""):
            raise AcceptanceError(f"ledger line {number} is missing {field_name}")
    if kind == "review" and "spend" in row and not _is_number(row["spend"]):
        raise AcceptanceError(f"ledger line {number} has invalid spend")
    if kind == "review_run" and not _is_number(row["spend_usd"]):
        raise AcceptanceError(f"ledger line {number} has invalid spend_usd")


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _spend_total_match(text: str) -> re.Match[str]:
    match = re.search(
        r"\*\*Total API spend: \$([0-9]+(?:\.[0-9]+)?) of \$10\.00\.\*\*",
        text,
    )
    if match is None:
        raise AcceptanceError("DEVSPEND.md total API spend line is missing")
    return match


def _workflow_text(action_ref: str) -> str:
    if "\n" in action_ref or "\r" in action_ref:
        raise AcceptanceError("action ref must be a single line")
    artifact_name = (
        "attest-ledger-pr-${{ github.event.pull_request.number }}"
        "-run-${{ github.run_id }}"
    )
    return f"""name: attest acceptance

on:
  pull_request:
    types: [opened, reopened, synchronize]

permissions:
  contents: read
  pull-requests: write

concurrency:
  group: attest-${{{{ github.event.pull_request.number }}}}
  cancel-in-progress: true

jobs:
  attest:
    runs-on: ubuntu-latest
    steps:
      - name: Check out pull request
        uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Check out action
        uses: actions/checkout@v4
        with:
          repository: {SOURCE_REPOSITORY}
          ref: {action_ref}
          token: ${{{{ secrets.{SOURCE_TOKEN_SECRET} }}}}
          path: _attest_action
      - name: Review pull request
        uses: ./_attest_action
        with:
          github-token: ${{{{ secrets.GITHUB_TOKEN }}}}
          model-api-key: ${{{{ secrets.{MODEL_KEY_ENV} }}}}
      - name: Upload attest ledger
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: {artifact_name}
          path: .attest/ledger.jsonl
          if-no-files-found: error
"""


def _main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--action-ref", required=True)
    parser.add_argument(
        "--delete-repo",
        action="store_true",
        help="delete the scratch repository after a successful acceptance run",
    )
    args = parser.parse_args(argv)
    try:
        result = run_acceptance(args.action_ref, keep_repo=not args.delete_repo)
    except AcceptanceError as exc:
        print(f"acceptance failed: {exc}", file=sys.stderr)
        return 1
    print(render_report(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
