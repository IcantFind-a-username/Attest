from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread

import pytest

from attest.github.client import STATUS_MARKER, GitHubClient
from attest.github.context import PullRequestContext
from attest.review.acceptance import (
    BUG_COMMENT_PHASES,
    classify_comments,
    parse_ledger,
)
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits
from attest.review.ledger import Ledger
from attest.review.proposer import ProviderResult


class RecordingProvider:
    def __init__(self, proposal: str, repro: str) -> None:
        self.proposal = proposal
        self.repro = repro
        self.calls: list[dict[str, object]] = []
        self._lock = Lock()

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        with self._lock:
            self.calls.append({"at": time.monotonic(), "system": system, "prompt": prompt})
        payload = self.repro if "focused pytest reproduction" in system else self.proposal
        return ProviderResult(text=payload, input_tokens=10, output_tokens=10)


class RecordingGitHub:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []
        self.status_bodies: list[str] = []
        self.review_bodies: list[dict[str, object]] = []
        self.fail_status_write_number: int | None = None
        self.status_write_attempts = 0
        self._status_comment: dict[str, object] | None = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                self._respond()

            def do_POST(self) -> None:  # noqa: N802
                self._respond()

            def do_PATCH(self) -> None:  # noqa: N802
                self._respond()

            def _respond(self) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8")
                body = json.loads(raw) if raw else None
                event = {
                    "at": time.monotonic(),
                    "method": self.command,
                    "path": self.path,
                    "body": body,
                }
                recorder.events.append(event)

                if self.command == "GET":
                    response: object = (
                        [] if recorder._status_comment is None else [recorder._status_comment]
                    )
                elif self.path.endswith("/comments") or "/issues/comments/" in self.path:
                    assert isinstance(body, dict)
                    recorder.status_write_attempts += 1
                    if recorder.status_write_attempts == recorder.fail_status_write_number:
                        response = {"message": "injected comment failure"}
                        encoded = json.dumps(response).encode("utf-8")
                        self.send_response(500)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(encoded)))
                        self.end_headers()
                        self.wfile.write(encoded)
                        return
                    text = str(body["body"])
                    recorder.status_bodies.append(text)
                    recorder._status_comment = {
                        "id": 101,
                        "body": text,
                        "user": {"type": "Bot"},
                    }
                    response = {"id": 101}
                else:
                    assert isinstance(body, dict)
                    recorder.review_bodies.append(body)
                    response = {"id": 202}

                encoded = json.dumps(response).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def log_message(self, format: str, *args: object) -> None:
                return

        return Handler


@pytest.fixture
def github_server() -> Iterator[RecordingGitHub]:
    server = RecordingGitHub()
    server.start()
    yield server
    server.close()


@pytest.fixture
def planted_repo(tmp_path: Path) -> tuple[Path, str, str]:
    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    # Differential evidence certifies a REGRESSION: the same function exists on
    # both sides, correct on base and broken on head. A generated reproduction
    # can then fail on head and pass on base, which is the only pattern that
    # buys V.
    (tmp_path / "app.py").write_text(
        "def total(items):\n"
        "    return sum(items)\n\n\n"
        "def average(items):\n"
        "    if not items:\n"
        "        return 0\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    git("add", "app.py")
    git("commit", "-m", "base")
    base_sha = git("rev-parse", "HEAD")
    (tmp_path / "app.py").write_text(
        "def total(items):\n"
        "    return sum(items)\n\n\n"
        "def average(items):\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    git("add", "app.py")
    git("commit", "-m", "regress average to divide by zero")
    return tmp_path, base_sha, git("rev-parse", "HEAD")


def _finding_payload() -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "claim": "average() divides by zero when items is empty.",
                    "anchor": {"file": "app.py", "line": 6},
                    "failure_scenario": "average([]) raises ZeroDivisionError",
                    "falsification_plan": "call average([]) and require a safe empty result",
                }
            ]
        }
    )


def _payload(*findings: dict[str, object]) -> str:
    return json.dumps({"findings": list(findings)})


def _context(base_sha: str, head_sha: str, *, is_fork: bool = False) -> PullRequestContext:
    return PullRequestContext(
        repository="octo/widgets",
        number=9,
        base_sha=base_sha,
        head_sha=head_sha,
        is_fork=is_fork,
    )


def _ledger_rows(repo: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]


@pytest.mark.parametrize(
    ("alpha", "auto_tighten", "max_findings"),
    [(0.15, False, 3), (0.4, False, 1), (0.15, True, 3), (0.4, True, 3)],
)
def test_st_cap_without_accepted_receipt_never_reaches_the_author(
    planted_repo: tuple[Path, str, str],
    github_server: RecordingGitHub,
    monkeypatch: pytest.MonkeyPatch,
    alpha: float,
    auto_tighten: bool,
    max_findings: int,
) -> None:
    """G-CERT-001 negative regression: S and T alone never publish.

    At a relaxed alpha the S x T wealth clears the legacy threshold before any
    reproduction. The candidate must still be sent through differential
    execution, and when no receipt is accepted (here the generated test passes
    on head) it must be invisible on every author-facing surface, whatever the
    alpha, auto-tighten, or cap configuration says.
    """
    from attest.review import tier0
    from attest.review.ci import run_ci
    from attest.review.tier0 import Tier0Signal

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(
        _finding_payload(),
        json.dumps({"test_body": "def test_passes_everywhere():\n    assert True\n"}),
    )
    monkeypatch.setattr(
        tier0,
        "run_ruff",
        lambda _repo, _files: [
            Tier0Signal("ruff", "app.py", 5, "F821: first corroborating signal"),
            Tier0Signal("ruff", "app.py", 6, "F821: second corroborating signal"),
        ],
    )

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(
            alpha=alpha,
            k_samples=2,
            tier0_commands=["ruff"],
            auto_tighten_alpha=auto_tighten,
            max_findings=max_findings,
        ),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    rows = _ledger_rows(repo)
    review = next(row for row in rows if row["kind"] == "review")
    # the legacy S/T wealth is recorded for analysis and did clear the bar ...
    assert review["channels_bought"] in (["S"], ["S", "T"])
    assert review["action"] == "surface"
    # ... but it is not speech authority: V was still attempted and no receipt
    # was accepted, so nothing author-visible exists on any surface
    assert [row for row in rows if row["kind"] == "verification"]
    assert result.surfaced_count == 0
    assert github_server.review_bodies == []
    for body in github_server.status_bodies:
        assert "average" not in body
        assert "app.py" not in body
    final = next(row for row in rows if row["kind"] == "ci_final")
    assert all(
        decision["placement"] not in {"inline", "overflow"} for decision in final["decisions"]
    )
    assert Ledger(repo).surfaced_finding_ids() == ()


def test_planted_bug_waits_for_failing_repro_before_speaking(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(
        _finding_payload(),
        json.dumps(
            {
                "test_body": "import runpy\n\n"
                "def test_average_handles_empty_input():\n"
                "    average = runpy.run_path('app.py')['average']\n"
                "    assert average([]) == 0\n"
            }
        ),
    )
    context = _context(base_sha, head_sha)

    result = run_ci(
        repo,
        context,
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    first_status_post = next(
        event
        for event in github_server.events
        if event["method"] == "POST" and str(event["path"]).endswith("/comments")
    )
    assert float(first_status_post["at"]) < min(float(call["at"]) for call in provider.calls)
    intermediate = github_server.status_bodies[1]
    assert "1" in intermediate
    assert "average" not in intermediate
    assert "app.py" not in intermediate

    assert result.candidate_count == 1
    assert result.surfaced_count == 1
    assert result.deferred_reason is None
    assert len(github_server.review_bodies) == 1
    comments = github_server.review_bodies[0]["comments"]
    assert isinstance(comments, list)
    assert len(comments) == 1
    assert "average() divides by zero" in str(comments[0]["body"])
    assert "Verified: the generated test failed on head in 3/3 runs" in str(comments[0]["body"])
    assert "Test: test_repro.py::test_average_handles_empty_input" in str(comments[0]["body"])
    assert "Receipt: " in str(comments[0]["body"])
    certification = next(row for row in _ledger_rows(repo) if row["kind"] == "certification")
    assert certification["outcome"] == "accepted"
    assert str(certification["receipt_digest"]) in str(comments[0]["body"])

    intermediate_event_index = next(
        index
        for index, event in enumerate(github_server.events)
        if event["method"] == "PATCH" and "1 candidates" in str(event["body"])
    )
    review_event_index = next(
        index
        for index, event in enumerate(github_server.events)
        if str(event["path"]).endswith("/reviews")
    )
    assert intermediate_event_index < review_event_index

    rows = _ledger_rows(repo)
    scoped = [row for row in rows if row["kind"] in {"review", "verification", "github_comment"}]
    assert {row["task_id"] for row in scoped} == {result.task_id}
    assert [row["kind"] for row in scoped].count("verification") == 1
    assert [row["kind"] for row in scoped].count("github_comment") == 4
    assert all(STATUS_MARKER not in str(row.get("body", "")) for row in scoped)


def test_real_ci_drawer_reproduction_inline_ledger_is_accepted(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(
        _finding_payload(),
        json.dumps(
            {
                "test_body": "import runpy\n\n"
                "def test_average_handles_empty_input():\n"
                "    average = runpy.run_path('app.py')['average']\n"
                "    assert average([]) == 0\n"
            }
        ),
    )

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    assert result.surfaced_count == 1
    rows = _ledger_rows(repo)
    review = next(row for row in rows if row["kind"] == "review")
    assert review["action"] == "drawer"
    inline_payload = github_server.review_bodies[0]["comments"]
    assert isinstance(inline_payload, list)
    api_comments = [
        {
            "id": index,
            "body": comment["body"],
            "path": comment["path"],
            "line": comment["line"],
        }
        for index, comment in enumerate(inline_payload, start=1)
        if isinstance(comment, dict)
    ]
    comments = classify_comments([], api_comments)
    ledger = parse_ledger((repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8"))

    ledger.assert_event_coverage(
        expected_comment_phases=BUG_COMMENT_PHASES,
        inline_finding_ids=comments.finding_ids,
    )


def test_clean_negative_control_posts_no_inline_review(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_payload(), '{"test_body":"assert False"}')

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=1, tier0_commands=[]),
        provider,
    )

    assert result.candidate_count == 0
    assert result.surfaced_count == 0
    assert result.deferred_reason is None
    assert len(provider.calls) == 1
    assert github_server.review_bodies == []
    final_body = github_server.status_bodies[-1]
    assert "No finding was verified by a reproduction; abstained." in final_body


def test_fork_is_skipped_before_provider_or_executor_use(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), '{"test_body":"assert False"}')

    result = run_ci(
        repo,
        _context(base_sha, head_sha, is_fork=True),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=1, tier0_commands=[]),
        provider,
    )

    assert result.task_id is not None
    assert result.deferred_reason is not None
    assert "fork" in result.deferred_reason.lower()
    assert provider.calls == []
    assert not (repo / ".attest" / "repro").exists()
    assert len(github_server.status_bodies) == 1
    assert "DEFER" in github_server.status_bodies[0]
    assert "fork" in github_server.status_bodies[0].lower()
    comment = next(row for row in _ledger_rows(repo) if row["kind"] == "github_comment")
    assert comment["task_id"] == result.task_id


def test_review_budget_defer_is_explicit_and_does_not_verify(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), '{"test_body":"assert False"}')

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(budget_usd=0.000001, k_samples=1, tier0_commands=[]),
        provider,
    )

    assert result.deferred_reason is not None
    assert result.deferred_reason.startswith("budget:")
    assert provider.calls == []
    assert github_server.review_bodies == []
    assert "DEFER" in github_server.status_bodies[-1]
    assert "budget" in github_server.status_bodies[-1]


def test_executor_timeout_defers_without_buying_verification_evidence(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(
        _finding_payload(),
        json.dumps({"test_body": "def test_never_finishes():\n    while True:\n        pass\n"}),
    )

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=1, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=0.05),
    )

    assert result.deferred_reason is not None
    assert "timed out" in result.deferred_reason
    assert result.surfaced_count == 0
    assert github_server.review_bodies == []
    verification = next(row for row in _ledger_rows(repo) if row["kind"] == "verification")
    assert verification["outcome"] == "deferred"
    review = next(row for row in _ledger_rows(repo) if row["kind"] == "review")
    assert review["channels_bought"] == ["S"]


def test_expired_shared_deadline_defers_every_unprocessed_candidate_without_v(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    first = {
        "claim": "Empty input divides the batch total by zero.",
        "anchor": {"file": "app.py", "line": 6},
        "failure_scenario": "An empty batch reaches a zero divisor.",
        "falsification_plan": "Run the helper with an empty batch.",
    }
    second = {
        "claim": "A missing numeric result aborts availability checks.",
        "anchor": {"file": "app.py", "line": 5},
        "failure_scenario": "The service passes no measurements to the helper.",
        "falsification_plan": "Exercise the no-measurements service path.",
    }
    provider = RecordingProvider(_payload(first, second), '{"test_body":"assert False"}')

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=1, tier0_commands=[]),
        provider,
        verification_timeout_s=0.0,
    )

    assert result.candidate_count == 2
    assert result.deferred_reason is not None
    assert "deadline" in result.deferred_reason
    assert len(provider.calls) == 1
    verification_rows = [row for row in _ledger_rows(repo) if row["kind"] == "verification"]
    assert len(verification_rows) == 2
    assert {row["outcome"] for row in verification_rows} == {"deferred"}
    assert all("deadline" in str(row["reason"]) for row in verification_rows)
    assert all(
        row["channels_bought"] == ["S"] for row in _ledger_rows(repo) if row["kind"] == "review"
    )


def test_generation_latency_exhausts_deadline_before_executor_starts(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo

    class MutableClock:
        now = 0.0

        def __call__(self) -> float:
            return self.now

    clock = MutableClock()

    class SlowGeneratorProvider:
        calls = 0

        def sample(
            self,
            system: str,
            prompt: str,
            schema: dict[str, object],
            max_tokens: int,
            *,
            timeout_s: float | None = None,
        ) -> ProviderResult:
            self.calls += 1
            if "focused pytest reproduction" in system:
                clock.now += 2.0
                payload = json.dumps({"test_body": "def test_repro():\n    assert False\n"})
            else:
                payload = _finding_payload()
            return ProviderResult(text=payload, input_tokens=10, output_tokens=10)

    provider = SlowGeneratorProvider()
    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=1, tier0_commands=[]),
        provider,
        verification_timeout_s=1.0,
        clock=clock,
    )

    assert provider.calls == 2
    assert result.deferred_reason is not None
    assert "deadline" in result.deferred_reason
    assert result.surfaced_count == 0
    assert not (repo / ".attest" / "repro").exists()
    verification = next(row for row in _ledger_rows(repo) if row["kind"] == "verification")
    assert verification["outcome"] == "deferred"
    assert "deadline" in str(verification["reason"])


def test_intermediate_github_failure_is_explicit_without_second_model_call(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), '{"test_body":"assert False"}')
    github_server.fail_status_write_number = 2

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=1, tier0_commands=[]),
        provider,
    )

    assert result.deferred_reason is not None
    assert "GitHub" in result.deferred_reason
    assert len(provider.calls) == 1
    assert github_server.review_bodies == []
    comment_rows = [row for row in _ledger_rows(repo) if row["kind"] == "github_comment"]
    assert comment_rows[-1]["outcome"] == "failed"
    assert {row["task_id"] for row in comment_rows} == {result.task_id}


def test_invalid_base_defers_with_immediate_comment_events_under_one_task(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, _, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), '{"test_body":"assert False"}')
    try:
        result = run_ci(
            repo,
            _context("missing-base-ref", head_sha),
            GitHubClient("local-token", github_server.url),
            ReviewConfig(k_samples=1, tier0_commands=[]),
            provider,
        )
    except (RuntimeError, subprocess.CalledProcessError):
        pytest.fail("review setup failure escaped instead of returning an explicit DEFER")

    assert result.task_id is not None
    assert result.deferred_reason is not None
    assert "merge-base unavailable" in result.deferred_reason
    assert provider.calls == []
    assert len(github_server.status_bodies) == 2
    assert "Review running" in github_server.status_bodies[0]
    assert "DEFER" in github_server.status_bodies[1]
    comment_rows = [row for row in _ledger_rows(repo) if row["kind"] == "github_comment"]
    assert [row["phase"] for row in comment_rows] == ["running", "defer"]
    assert {row["task_id"] for row in comment_rows} == {result.task_id}
    defer = next(row for row in _ledger_rows(repo) if row["kind"] == "defer")
    assert defer["task_id"] == result.task_id


def test_pre_provider_ledger_preparation_failure_is_zero_spend_setup_defer(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub, monkeypatch
) -> None:
    from attest.review.ci import run_ci
    from attest.review.ledger import Ledger

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), '{"test_body":"assert False"}')

    def fail_alpha_preparation(self, configured):  # noqa: ANN001
        raise OSError("private ledger preparation failure detail")

    monkeypatch.setattr(Ledger, "current_alpha", fail_alpha_preparation)
    try:
        result = run_ci(
            repo,
            _context(base_sha, head_sha),
            GitHubClient("local-token", github_server.url),
            ReviewConfig(k_samples=1, tier0_commands=[]),
            provider,
        )
    except OSError:
        pytest.fail("pre-provider ledger failure escaped instead of becoming setup DEFER")

    assert provider.calls == []
    assert result.task_id is not None
    assert result.candidate_count == 0
    assert result.spend_usd == 0.0
    assert result.deferred_reason == "review setup failed: ReviewSetupError"
    assert "private ledger preparation failure detail" not in result.deferred_reason
    comment_rows = [row for row in _ledger_rows(repo) if row["kind"] == "github_comment"]
    assert [row["phase"] for row in comment_rows] == ["running", "defer"]
    assert {row["task_id"] for row in comment_rows} == {result.task_id}


def test_post_provider_persistence_failure_retains_spend_phase_and_task_accounting(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub, monkeypatch
) -> None:
    from attest.review.candidates import CandidateStore
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), '{"test_body":"assert False"}')

    def fail_candidate_persistence(self, task_id, alpha, results, eligibility=None):  # noqa: ANN001
        raise OSError("private persistence failure detail")

    monkeypatch.setattr(CandidateStore, "append", fail_candidate_persistence)

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=1, tier0_commands=[]),
        provider,
    )

    assert len(provider.calls) == 1
    assert result.task_id is not None
    assert result.candidate_count == 1
    assert result.spend_usd > 0
    assert result.deferred_reason == "review execution failed during candidate persistence"
    assert "private persistence failure detail" not in result.deferred_reason
    assert len(github_server.status_bodies) == 2
    assert "DEFER" in github_server.status_bodies[-1]
    rows = _ledger_rows(repo)
    comment_rows = [row for row in rows if row["kind"] == "github_comment"]
    assert [row["phase"] for row in comment_rows] == ["running", "defer"]
    assert {row["task_id"] for row in comment_rows} == {result.task_id}
    defer = next(row for row in rows if row["kind"] == "defer")
    assert defer["task_id"] == result.task_id
    assert defer["phase"] == "candidate_persistence"
    review_run = next(row for row in rows if row["kind"] == "review_run")
    assert review_run["task_id"] == result.task_id
    assert float(review_run["spend_usd"]) == pytest.approx(result.spend_usd)
    assert review_run["phase"] == "candidate_persistence"


def test_final_review_run_accounting_failure_becomes_post_provider_defer(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub, monkeypatch
) -> None:
    from attest.review.ci import run_ci
    from attest.review.ledger import Ledger

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), '{"test_body":"assert False"}')
    original_append = Ledger.append

    def fail_unphased_review_run(self, entry):  # noqa: ANN001
        if entry.get("kind") == "review_run" and "phase" not in entry:
            raise OSError("private final accounting failure detail")
        original_append(self, entry)

    monkeypatch.setattr(Ledger, "append", fail_unphased_review_run)
    try:
        result = run_ci(
            repo,
            _context(base_sha, head_sha),
            GitHubClient("local-token", github_server.url),
            ReviewConfig(k_samples=1, tier0_commands=[]),
            provider,
        )
    except OSError:
        pytest.fail("final review-run accounting failure escaped the typed execution boundary")

    assert len(provider.calls) == 1
    assert result.task_id is not None
    assert result.candidate_count == 1
    assert result.spend_usd > 0
    assert result.deferred_reason == "review execution failed during review run accounting"
    assert "private final accounting failure detail" not in result.deferred_reason
    rows = _ledger_rows(repo)
    comment_rows = [row for row in rows if row["kind"] == "github_comment"]
    assert [row["phase"] for row in comment_rows] == ["running", "defer"]
    assert {row["task_id"] for row in comment_rows} == {result.task_id}
    defer = next(row for row in rows if row["kind"] == "defer")
    assert defer["phase"] == "review_run_accounting"
    review_runs = [row for row in rows if row["kind"] == "review_run"]
    assert len(review_runs) == 1
    assert review_runs[0]["task_id"] == result.task_id
    assert review_runs[0]["phase"] == "review_run_accounting"
    assert float(review_runs[0]["spend_usd"]) == pytest.approx(result.spend_usd)


def test_surface_overflow_stays_visible_without_extra_inline_placement(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    findings = [
        {
            "claim": "Empty batch division crashes request processing.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "A request submits an empty batch.",
            "falsification_plan": "Call the helper with no batch entries.",
        },
        {
            "claim": "Missing measurements abort the scheduled aggregation.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "A scheduled job receives no measurements.",
            "falsification_plan": "Run the scheduled job without measurements.",
        },
        {
            "claim": "Vacant samples terminate the health calculation.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "A health window contains vacant samples.",
            "falsification_plan": "Evaluate a health window containing no samples.",
        },
        {
            "claim": "Zero observations make the reporting endpoint unavailable.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "The endpoint handles a period with zero observations.",
            "falsification_plan": "Request a report for an observation-free period.",
        },
    ]
    provider = RecordingProvider(
        _payload(*findings),
        json.dumps(
            {
                "test_body": "import runpy\n\n"
                "def test_empty_input_is_safe():\n"
                "    average = runpy.run_path('app.py')['average']\n"
                "    assert average([]) == 0\n"
            }
        ),
    )

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, max_findings=3, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    assert result.candidate_count == 4
    # four certified candidates for one defect (same anchor, same reproduction)
    # are one publication cluster: the author sees it once (C-05)
    assert result.surfaced_count == 1
    comments = github_server.review_bodies[0]["comments"]
    assert isinstance(comments, list)
    assert len(comments) == 1
    visible = sum(str(finding["claim"]) in github_server.status_bodies[-1] for finding in findings)
    assert visible == 1
    rows = _ledger_rows(repo)
    final = next(row for row in rows if row["kind"] == "ci_final")
    assert float(final["spend_usd"]) == pytest.approx(result.spend_usd)
    decisions = final["decisions"]
    assert isinstance(decisions, list)
    assert len(decisions) == 4
    assert sorted(decision["action"] for decision in decisions) == ["drawer"] * 3 + ["surface"]
    policy = next(row for row in rows if row["kind"] == "publication_policy")
    assert [s["reason"] for s in policy["suppressed"]] == ["same defect as a published finding"] * 3

    classified = classify_comments(
        [],
        [
            {"id": index, "created_at": "2026-08-29T00:00:01Z", **comment}
            for index, comment in enumerate(comments, start=1)
        ],
    )
    parse_ledger(
        (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8")
    ).assert_event_coverage(
        expected_comment_phases=BUG_COMMENT_PHASES,
        inline_finding_ids=classified.finding_ids,
    )


def test_mixed_defer_summary_keeps_all_surfaced_overflow_and_hides_deferred_details(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    surfaced = [
        {
            "claim": "Empty batch division crashes request processing.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "A request submits an empty batch.",
            "falsification_plan": "Call the helper with no batch entries.",
        },
        {
            "claim": "Missing measurements abort the scheduled aggregation.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "A scheduled job receives no measurements.",
            "falsification_plan": "Run the scheduled job without measurements.",
        },
        {
            "claim": "Vacant samples terminate the health calculation.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "A health window contains vacant samples.",
            "falsification_plan": "Evaluate a health window containing no samples.",
        },
        {
            "claim": "Zero observations make the reporting endpoint unavailable.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "The endpoint handles a period with zero observations.",
            "falsification_plan": "Request a report for an observation-free period.",
        },
    ]
    deferred = {
        "claim": "Absent telemetry corrupts the archival checkpoint.",
        "anchor": {"file": "app.py", "line": 5},
        "failure_scenario": "An archival checkpoint receives absent telemetry.",
        "falsification_plan": "Inspect the private archival checkpoint path.",
    }
    proposal = _payload(*surfaced, deferred)
    failing_repro = json.dumps(
        {
            "test_body": "import runpy\n\n"
            "def test_empty_input_is_safe():\n"
            "    average = runpy.run_path('app.py')['average']\n"
            "    assert average([]) == 0\n"
        }
    )

    class MixedProvider:
        def sample(
            self,
            system: str,
            prompt: str,
            schema: dict[str, object],
            max_tokens: int,
            *,
            timeout_s: float | None = None,
        ) -> ProviderResult:
            if "focused pytest reproduction" not in system:
                return ProviderResult(text=proposal, input_tokens=10, output_tokens=10)
            payload = "{}" if str(deferred["claim"]) in prompt else failing_repro
            return ProviderResult(text=payload, input_tokens=10, output_tokens=10)

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, max_findings=3, tier0_commands=[]),
        MixedProvider(),
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    assert result.candidate_count == 5
    assert result.surfaced_count == 1  # one defect, published once (C-05)
    assert result.deferred_reason is not None
    comments = github_server.review_bodies[0]["comments"]
    assert isinstance(comments, list)
    assert len(comments) == 1
    sticky = github_server.status_bodies[-1]
    assert "DEFER" in sticky
    assert sum(str(finding["claim"]) in sticky for finding in surfaced) == 1
    for private_detail in (
        deferred["claim"],
        deferred["failure_scenario"],
        deferred["falsification_plan"],
    ):
        assert str(private_detail) not in sticky


def test_head_policy_is_ignored_and_the_diff_is_merge_base_to_head(
    planted_repo: tuple[Path, str, str],
    github_server: RecordingGitHub,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """G-CERT-002: policy is base-owned and the counterfactual is the merge-base.

    The head commit adds an ``.attest.toml`` that sets alpha to 1.0 (an invalid,
    maximally relaxed value); the base branch then advances with an unrelated
    file. The review must run under the base policy (factory alpha 0.1), must
    review only the pull request's own change (one file, not the base advance),
    and must verify against the merge-base rather than the advanced base tip.
    """
    from attest.cli.main import main

    repo, base_sha, head_sha = planted_repo

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    (repo / ".attest.toml").write_text(
        "alpha = 1.0\nmax_findings = 50\nbudget_usd = 1000.0\n", encoding="utf-8"
    )
    git("add", ".attest.toml")
    git("commit", "-m", "head relaxes policy")
    relaxed_head = git("rev-parse", "HEAD")
    git("checkout", "-q", "--detach", base_sha)
    (repo / "other.py").write_text("VALUE = 1\n", encoding="utf-8")
    git("add", "other.py")
    git("commit", "-m", "base advances after the fork")
    advanced_base = git("rev-parse", "HEAD")
    git("checkout", "-q", "--detach", relaxed_head)

    event = tmp_path / "event.json"
    event.write_text(
        json.dumps(
            {
                "number": 9,
                "repository": {"full_name": "octo/widgets"},
                "pull_request": {
                    "base": {"sha": advanced_base},
                    "head": {"sha": relaxed_head, "repo": {"full_name": "octo/widgets"}},
                },
            }
        ),
        encoding="utf-8",
    )
    mock = tmp_path / "proposal.json"
    mock.write_text(_finding_payload(), encoding="utf-8")
    monkeypatch.setenv("GITHUB_TOKEN", "local-token")
    monkeypatch.setenv("GITHUB_API_URL", github_server.url)

    rc = main(
        ["--repo", str(repo), "ci", "--event-path", str(event), "--k", "2", "--mock", str(mock)]
    )

    assert rc == 0
    rows = _ledger_rows(repo)
    run = next(row for row in rows if row["kind"] == "review_run")
    assert run["alpha"] == 0.1
    # merge-base..head touches app.py and the head's own .attest.toml; base-tip
    # two-dot semantics would also show other.py (as a deletion) -> 3 files
    assert run["files"] == 2
    verification = next(row for row in rows if row["kind"] == "verification")
    assert verification["base_sha"] == base_sha
    assert verification["head_sha"] == relaxed_head
    task = next(row for row in rows if row["kind"] == "certification_task")
    assert task["merge_base_sha"] == base_sha
    assert task["policy_source_sha"] == base_sha
    assert task["policy_source"] == "factory-defaults"


def test_pr_family_policy_caps_publication_and_counts_a_defect_once(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    """G-CERT-004: with m eligible candidates in one PR, nothing below m/alpha is
    published, two certified candidates for the same defect count once, and the
    author sees at most the hard cap.

    Five candidates; two are asserted by both samples (votes 2), three by one
    (votes 1). Every candidate is certified by the same reproduction, so all
    five hold accepted receipts. At alpha 0.1 with m = 5 the family threshold is
    50: wealth 2.64 x 20 = 52.8 clears it, 2.0 x 20 = 40 does not. The two
    clearing candidates share one test digest and adjacent anchors: one defect.
    """
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    # a second regression in another file so the singles form their own cluster
    git("checkout", "-q", "--detach", base_sha)
    (repo / "util.py").write_text(
        "def ratio(a, b):\n    if b == 0:\n        return 0\n    return a / b\n",
        encoding="utf-8",
    )
    git("add", "util.py")
    git("commit", "-qm", "guarded ratio")
    base_sha = git("rev-parse", "HEAD")
    (repo / "app.py").write_text(
        "def total(items):\n    return sum(items)\n\n\n"
        "def average(items):\n    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    (repo / "util.py").write_text("def ratio(a, b):\n    return a / b\n", encoding="utf-8")
    git("add", "app.py", "util.py")
    git("commit", "-qm", "drop both guards")
    head_sha = git("rev-parse", "HEAD")
    shared = [
        {
            "claim": "Empty batches crash the averaging helper.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "A request submits an empty batch.",
            "falsification_plan": "Call the helper with no batch entries.",
        },
        {
            "claim": "Vacant windows terminate the health computation.",
            "anchor": {"file": "app.py", "line": 6},
            "failure_scenario": "A health window contains nothing.",
            "falsification_plan": "Evaluate a window with no samples.",
        },
    ]
    singles = [
        {
            "claim": "Missing measurements abort the scheduled aggregation.",
            "anchor": {"file": "util.py", "line": 2},
            "failure_scenario": "A scheduled job receives no measurements.",
            "falsification_plan": "Run the scheduled job without measurements.",
        },
        {
            "claim": "Zero observations make the reporting endpoint unavailable.",
            "anchor": {"file": "util.py", "line": 2},
            "failure_scenario": "The endpoint handles a period with zero observations.",
            "falsification_plan": "Request a report for an observation-free period.",
        },
        {
            "claim": "Absent telemetry corrupts the archival checkpoint.",
            "anchor": {"file": "util.py", "line": 2},
            "failure_scenario": "An archival checkpoint receives absent telemetry.",
            "falsification_plan": "Inspect the archival checkpoint path.",
        },
    ]

    def repro_for(prompt: str) -> str:
        # the singles reproduce the util.py regression, each with its own bytes
        for index, finding in enumerate(singles):
            if str(finding["claim"]) in prompt:
                return json.dumps(
                    {
                        "test_body": "import runpy\n\n"
                        f"def test_single_{index}_zero_divisor():\n"
                        "    ratio = runpy.run_path('util.py')['ratio']\n"
                        "    assert ratio(1, 0) == 0\n"
                    }
                )
        return json.dumps(
            {
                "test_body": "import runpy\n\n"
                "def test_empty_input_is_safe():\n"
                "    average = runpy.run_path('app.py')['average']\n"
                "    assert average([]) == 0\n"
            }
        )

    class TwoSampleProvider:
        def __init__(self) -> None:
            self.proposals = 0

        def sample(
            self,
            system: str,
            prompt: str,
            schema: dict[str, object],
            max_tokens: int,
            *,
            timeout_s: float | None = None,
        ) -> ProviderResult:
            if "focused pytest reproduction" in system:
                return ProviderResult(text=repro_for(prompt), input_tokens=10, output_tokens=10)
            self.proposals += 1
            payload = _payload(*shared, *singles) if self.proposals == 1 else _payload(*shared)
            return ProviderResult(text=payload, input_tokens=10, output_tokens=10)

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(alpha=0.1, k_samples=2, max_findings=3, tier0_commands=[]),
        TwoSampleProvider(),
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    assert result.candidate_count == 5
    rows = _ledger_rows(repo)
    accepted = [
        row for row in rows if row["kind"] == "certification" and row["outcome"] == "accepted"
    ]
    assert len(accepted) == 5  # every candidate holds a receipt ...
    policy = next(row for row in rows if row["kind"] == "publication_policy")
    assert policy["eligible_count"] == 5
    assert policy["family_threshold"] == 50.0
    # ... but publication is family-controlled: one defect, once, above m/alpha
    assert result.surfaced_count == 1
    comments = github_server.review_bodies[0]["comments"]
    assert isinstance(comments, list) and len(comments) == 1
    body = str(comments[0]["body"])
    # equal e-values: the deterministic tie-break on candidate id picks one of the two
    assert ("Empty batches crash" in body) != ("Vacant windows" in body)
    final = next(row for row in rows if row["kind"] == "ci_final")
    published = [d for d in final["decisions"] if d["placement"] in {"inline", "overflow"}]
    assert len(published) == 1
    assert all(d["wealth_final"] >= 50.0 for d in published)
    suppressed = {s["finding_id"]: s["reason"] for s in policy["suppressed"]}
    assert sorted(suppressed.values()) == [
        "below family threshold",
        "below family threshold",
        "below family threshold",
        "same defect as a published finding",
    ]
    sticky = github_server.status_bodies[-1]
    assert ("Empty batches crash" in sticky) != ("Vacant windows" in sticky)
    assert "Missing measurements" not in sticky


def test_silent_run_status_comment_names_counts_and_every_failure_reason(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    """Owner item 6 (2026-09-03): a run that publishes nothing still reports
    its status in a collapsed section -- change units, candidates, eligible,
    reproduction attempts and each attempt's failure category -- without the
    content or location of any uncertified candidate."""
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    # a test that fails on both trees: unfaithful, so nothing is published
    provider = RecordingProvider(
        _finding_payload(),
        json.dumps({"test_body": "def test_repro():\n    assert False\n"}),
    )
    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert result.surfaced_count == 0
    final = github_server.status_bodies[-1]
    assert "<summary>Run status</summary>" in final
    assert "change units read: 1; candidates: 1; eligible: 1; reproductions attempted: 1" in final
    assert "reproduction 1: unfaithful test" in final
    assert "app.py" not in final.split("<details>")[1]
    assert "divides by zero" not in final


def test_verified_finding_comment_carries_a_test_and_command_that_reproduce_on_both_trees(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    """Owner item 7 (2026-09-03): the test and command copied out of the PR
    comment fail on the head tree and pass on the base tree."""
    import re

    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(
        _finding_payload(),
        json.dumps(
            {
                "test_body": "import runpy\n\n"
                "def test_average_handles_empty_input():\n"
                "    average = runpy.run_path('app.py')['average']\n"
                "    assert average([]) == 0\n"
            }
        ),
    )
    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert result.surfaced_count == 1
    inline = str(github_server.review_bodies[-1]["comments"][0]["body"])
    final = github_server.status_bodies[-1]
    for body in (inline, final):
        assert "Run it yourself" in body
        assert "attest verify --bundle" in body
        assert "<summary>Full logs</summary>" in body
        assert "head FAIL 3/3, base PASS 3/3" in body
    test_source = re.search(r"```python\n(.*?)\n```", inline, re.DOTALL).group(1)
    command = re.search(r"```bash\n(.*?)\n```", inline, re.DOTALL).group(1).strip()
    assert command.startswith("pytest -q test_repro.py::test_average_handles_empty_input")

    def run_on(sha: str) -> int:
        tree = repo.parent / f"tree-{sha[:7]}"
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", "--detach", str(tree), sha],
            check=True,
            capture_output=True,
        )
        (tree / "test_repro.py").write_text(test_source + "\n", encoding="utf-8")
        completed = subprocess.run(
            [sys.executable, "-m", *command.split()], cwd=tree, capture_output=True, text=True
        )
        subprocess.run(
            ["git", "-C", str(repo), "worktree", "remove", "--force", str(tree)],
            check=False,
            capture_output=True,
        )
        return completed.returncode

    assert run_on(head_sha) != 0
    assert run_on(base_sha) == 0


def test_base_branch_kill_switch_stops_the_review_before_any_model_call(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    """L-01 kill switch: `enabled = false` committed on the base branch defers
    the review before any provider call or head-code execution, and the head's
    own .attest.toml saying `enabled = true` changes nothing."""
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    # base: disabled; head: a change plus a policy file that tries to re-enable
    git("checkout", "-q", base_sha)
    (repo / ".attest.toml").write_text("enabled = false\n", encoding="utf-8")
    git("add", ".attest.toml")
    git("commit", "-q", "-m", "base: switch attest off")
    disabled_base = git("rev-parse", "HEAD")
    git("checkout", "-q", head_sha)
    (repo / ".attest.toml").write_text("enabled = true\n", encoding="utf-8")
    git("add", ".attest.toml")
    git("commit", "-q", "-m", "head: try to switch attest on")
    enabled_head = git("rev-parse", "HEAD")

    provider = RecordingProvider(
        _finding_payload(), json.dumps({"test_body": "def test_repro(): assert False"})
    )
    result = run_ci(
        repo,
        _context(disabled_base, enabled_head),
        GitHubClient("local-token", github_server.url),
        None,
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
        merge_base_sha=disabled_base,
    )
    assert result.surfaced_count == 0
    assert "disabled by the base policy" in str(result.deferred_reason)
    assert provider.calls == []
    assert "disabled by the base policy" in github_server.status_bodies[-1]
    assert result.spend_usd == 0.0


# --------------------------------------------------------------------------- D-102
GUARD_APP_BASE = (
    "BANNED = ('buy', 'sell')\n"
    "\n"
    "\n"
    "class Signal:\n"
    "    def __init__(self, summary):\n"
    "        if not summary.strip():\n"
    "            raise ValueError('summary is required')\n"
    "        self.summary = summary\n"
)
GUARD_APP_HEAD = (
    "BANNED = ('buy', 'sell')\n"
    "\n"
    "\n"
    "class Signal:\n"
    "    def __init__(self, summary):\n"
    "        if not summary.strip():\n"
    "            raise ValueError('summary is required')\n"
    "        for verb in BANNED:\n"
    "            if verb in summary:\n"
    "                raise ValueError(\n"
    "                    f'summary must never contain {verb!r}: {summary!r}'\n"
    "                )\n"
    "        self.summary = summary\n"
)
GUARD_WITNESS_TEST = (
    "from app import Signal\n"
    "\n"
    "\n"
    "def test_buyback_copy_is_accepted():\n"
    "    assert Signal('the buyback plan raises the floor').summary\n"
)
GUARD_REPRO = json.dumps(
    {
        "test_body": "import app\n\n\n"
        "def test_buyback_copy_constructs():\n"
        "    signal = app.Signal('the buyback plan raises the floor')\n"
        "    assert 'buyback' in signal.summary\n"
    }
)


def _guard_finding_payload() -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "claim": (
                        "The banned-verb guard uses substring containment and rejects "
                        "legitimate copy that merely contains a banned verb inside a "
                        "longer word."
                    ),
                    "anchor": {"file": "app.py", "line": 10},
                    "failure_scenario": "Signal('the buyback plan') raises ValueError",
                    "falsification_plan": "construct a signal whose summary contains buyback",
                }
            ]
        }
    )


def _guarded_repo(tmp_path: Path, *, witness: bool) -> tuple[Path, str, str]:
    """A base whose existing constructor accepts every phrase and a head that
    newly rejects phrases containing a banned verb; with ``witness`` the base
    tree's own test constructs the phrase the reproduction will feed."""

    def git(*args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        )
        return result.stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (tmp_path / "app.py").write_text(GUARD_APP_BASE, encoding="utf-8")
    if witness:
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_app.py").write_text(GUARD_WITNESS_TEST, encoding="utf-8")
    git("add", "--all")
    git("commit", "-m", "base")
    base_sha = git("rev-parse", "HEAD")
    (tmp_path / "app.py").write_text(GUARD_APP_HEAD, encoding="utf-8")
    git("add", "--all")
    git("commit", "-m", "feat: guard summaries against action verbs")
    return tmp_path, base_sha, git("rev-parse", "HEAD")


def test_a_new_rejection_without_a_base_witness_publishes_nothing_and_is_labelled(
    tmp_path: Path, github_server: RecordingGitHub
) -> None:
    """D-102 RED: the E-01 shape -- a valid head-fail/base-pass differential on a
    validation-tightening commit whose rejected input the generator invented --
    reaches no author. The run status and the ledger carry the label."""
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = _guarded_repo(tmp_path, witness=False)
    provider = RecordingProvider(_guard_finding_payload(), GUARD_REPRO)

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    assert result.candidate_count == 1
    assert result.surfaced_count == 0
    assert github_server.review_bodies == []
    final = github_server.status_bodies[-1]
    assert "behavior change, intent unknown" in final
    assert "buyback" not in final and "app.py" not in final
    rows = _ledger_rows(repo)
    verification = next(row for row in rows if row["kind"] == "verification")
    assert verification["outcome"] == "deferred"
    assert verification["evidence_class"] == "behavior_change"
    assert "behavior change confirmed, intent unknown" in str(verification["reason"])
    assert "行为变化已证实，意图未知" in str(verification["reason"])
    certification = next(row for row in rows if row["kind"] == "certification")
    assert certification["outcome"] == "not_attempted"
    assert "behavior_change" in str(certification["reason"])


def test_a_new_rejection_the_base_tests_attest_publishes_as_a_behavior_change(
    tmp_path: Path, github_server: RecordingGitHub
) -> None:
    """The same commit when the base tree's own test builds the rejected phrase:
    a behavior-change receipt, published in words that say exactly what it
    proves, with an intent observation the offline verifier re-judges."""
    from attest.certification.types import AcceptedReceipt
    from attest.review.ci import run_ci
    from attest.review.evidence import BundleRejection, canonical_digest, verify_bundle

    repo, base_sha, head_sha = _guarded_repo(tmp_path, witness=True)
    provider = RecordingProvider(_guard_finding_payload(), GUARD_REPRO)

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    assert result.surfaced_count == 1
    body = str(github_server.review_bodies[0]["comments"][0]["body"])  # type: ignore[index]
    assert "Behavior change (intent to confirm):" in body
    assert "Verified behavior change:" in body
    assert "rejects an input the merge base accepted" in body
    assert "head raises ValueError at app.py:10 on 'the buyback plan raises the floor'" in body
    assert "tests/test_app.py" in body
    assert "If the rejection is intended, dismiss this finding." in body
    final = github_server.status_bodies[-1]
    assert "behavior changes verified: 1" in final
    rows = _ledger_rows(repo)
    certification = next(row for row in rows if row["kind"] == "certification")
    assert certification["outcome"] == "accepted"
    assert certification["evidence_class"] == "behavior_change"
    bundle = Path(str(certification["bundle_path"]))
    intent = json.loads((bundle / "intent.json").read_text(encoding="utf-8"))
    assert intent["new_rejection"] is True
    assert intent["witnesses"] == [["the buyback plan raises the floor", "tests/test_app.py"]]
    receipt = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["evidence_class"] == "behavior_change"
    assert receipt["intent_policy_version"] == "attest.intent.new-rejection.v1"
    assert isinstance(verify_bundle(bundle), AcceptedReceipt)

    # the verifier re-judges the observation: a bundle whose every digest is
    # consistent but whose intent observation lost its witnesses is rejected
    mutant = tmp_path / "mutant"
    shutil.copytree(bundle, mutant)
    intent["witnesses"] = []
    intent_bytes = json.dumps(
        intent, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    (mutant / "intent.json").write_bytes(intent_bytes)
    receipt["intent_digest"] = hashlib.sha256(intent_bytes).hexdigest()
    unsigned = {key: value for key, value in receipt.items() if key != "provenance_digest"}
    receipt["provenance_digest"] = canonical_digest(unsigned)
    receipt_bytes = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    (mutant / "receipt.json").write_bytes(receipt_bytes)
    manifest = json.loads((mutant / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"]["intent.json"] = hashlib.sha256(intent_bytes).hexdigest()
    manifest["files"]["receipt.json"] = hashlib.sha256(receipt_bytes).hexdigest()
    (mutant / "manifest.json").write_bytes(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
            "utf-8"
        )
    )
    verdict = verify_bundle(mutant)
    assert isinstance(verdict, BundleRejection)
    assert any("intent observation forbids publication" in reason for reason in verdict.reasons)


def test_an_unattempted_certification_names_the_profile_that_actually_ran(
    tmp_path: Path, github_server: RecordingGitHub, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Found on the first GitHub-hosted runner review (PR #8): the runs executed
    under `linux-container-v1` and the `executor_backend` ledger row said so,
    but the `certification` row for the same task reported
    `local_development_best_effort` -- the dataclass default, because the
    not-attempted path is the one construction that never passes the profile.
    It buys nothing, so nothing is overclaimed; it is still a ledger row that
    names the wrong isolation boundary to anyone auditing the run."""
    from attest.execution.backends import BackendSelection
    from attest.execution.container_adapter import CONTAINER_PROFILE
    from attest.execution.local_adapter import LocalDevelopmentAdapter
    from attest.review import verification as verification_module
    from attest.review.ci import run_ci

    # the runner's condition without a docker daemon: the runs record the
    # container profile, so the certification row must not answer with the host
    class ContainerProfileAdapter(LocalDevelopmentAdapter):
        profile = CONTAINER_PROFILE

    monkeypatch.setattr(
        verification_module,
        "select_backend",
        lambda tree, *, production, remaining_s=None: BackendSelection(
            ContainerProfileAdapter(), CONTAINER_PROFILE, "image attest-repro:testdouble"
        ),
    )

    repo, base_sha, head_sha = _guarded_repo(tmp_path, witness=False)
    provider = RecordingProvider(_guard_finding_payload(), GUARD_REPRO)

    run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )

    rows = _ledger_rows(repo)
    backend = next(row for row in rows if row["kind"] == "executor_backend")
    certification = next(row for row in rows if row["kind"] == "certification")
    assert certification["outcome"] == "not_attempted"
    assert certification["executor_profile"] == backend["profile"]


def test_reproductions_are_bought_in_ranking_order(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub
) -> None:
    """D-111: verification walked the candidate store in storage order, which
    is the dedup clustering's (file, line, claim) order and carries no ranking.
    A shared deadline or an exhausted budget therefore stopped at whichever
    candidate happened to be last in the file rather than at the weakest one.
    Reproductions are now attempted best-first, by the same key C-05 already
    uses to publish: score first, candidate id to break ties."""
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    weaker = {
        "claim": "A missing numeric result aborts availability checks.",
        "anchor": {"file": "app.py", "line": 5},
        "failure_scenario": "The service passes no measurements to the helper.",
        "falsification_plan": "Exercise the no-measurements service path.",
    }
    stronger = {
        "claim": "Empty input divides the batch total by zero.",
        "anchor": {"file": "app.py", "line": 6},
        "failure_scenario": "An empty batch reaches a zero divisor.",
        "falsification_plan": "Run the helper with an empty batch.",
    }

    class TwoSampleProvider(RecordingProvider):
        """One sample sees both findings, the other only the stronger one, so
        the two candidates differ in votes and therefore in wealth. The store
        order is the opposite of the ranking: line 5 sorts before line 6."""

        def __init__(self) -> None:
            super().__init__("", '{"test_body":"assert False"}')
            self._remaining = [_payload(weaker, stronger), _payload(stronger)]

        def sample(
            self,
            system: str,
            prompt: str,
            schema: dict[str, object],
            max_tokens: int,
            *,
            timeout_s: float | None = None,
        ) -> ProviderResult:
            with self._lock:
                self.calls.append({"system": system, "prompt": prompt})
                if "focused pytest reproduction" in system:
                    return ProviderResult(text=self.repro, input_tokens=10, output_tokens=10)
                payload = self._remaining.pop(0)
            return ProviderResult(text=payload, input_tokens=10, output_tokens=10)

    provider = TwoSampleProvider()
    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
    )

    assert result.candidate_count == 2
    generations = [
        str(call["prompt"])
        for call in provider.calls
        if "focused pytest reproduction" in str(call["system"])
    ]
    assert len(generations) == 2, "both eligible candidates should have been attempted"
    assert str(stronger["claim"]) in generations[0]
    assert str(weaker["claim"]) in generations[1]
