from __future__ import annotations

import json
import subprocess
import sys
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock, Thread

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.acceptance.phase3 import (  # noqa: E402
    BUG_COMMENT_PHASES,
    classify_comments,
    parse_ledger,
)

from attest.github.client import STATUS_MARKER, GitHubClient
from attest.github.context import PullRequestContext
from attest.review.config import ReviewConfig
from attest.review.executor import ExecutorLimits
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


def test_ci_does_not_verify_an_already_terminal_surface(
    planted_repo: tuple[Path, str, str],
    github_server: RecordingGitHub,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from attest.review import tier0
    from attest.review.ci import run_ci
    from attest.review.tier0 import Tier0Signal

    repo, base_sha, head_sha = planted_repo

    class SurfaceOnlyProvider:
        def __init__(self) -> None:
            self.proposal_calls = 0
            self.generator_calls = 0

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
                self.generator_calls += 1
                pytest.fail("terminal surface must not generate a reproduction")
            self.proposal_calls += 1
            return ProviderResult(text=_finding_payload(), input_tokens=10, output_tokens=10)

    monkeypatch.setattr(
        tier0,
        "run_ruff",
        lambda _repo, _files: [
            Tier0Signal("ruff", "app.py", 5, "F821: first corroborating signal"),
            Tier0Signal("ruff", "app.py", 6, "F821: second corroborating signal"),
        ],
    )
    provider = SurfaceOnlyProvider()

    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(alpha=0.15, k_samples=2, tier0_commands=["ruff"]),
        provider,
    )

    assert result.surfaced_count == 1
    assert provider.proposal_calls == 2
    assert provider.generator_calls == 0
    rows = _ledger_rows(repo)
    assert not [row for row in rows if row["kind"] == "verification"]
    review = next(row for row in rows if row["kind"] == "review")
    assert review["channels_bought"] == ["S", "T"]
    final = next(row for row in rows if row["kind"] == "ci_final")
    decisions = final["decisions"]
    assert isinstance(decisions, list)
    assert decisions == [
        {
            "finding_id": review["finding_id"],
            "action": "surface",
            "wealth_final": 7.917,
            "placement": "inline",
        }
    ]


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
    assert "S x2.64" in str(comments[0]["body"])
    assert "V x20.00" in str(comments[0]["body"])

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
    ledger = parse_ledger(
        (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8")
    )

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
    assert "No findings cleared the evidence bar." in github_server.status_bodies[-1]


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
        row["channels_bought"] == ["S"]
        for row in _ledger_rows(repo)
        if row["kind"] == "review"
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
    assert "review setup failed" in result.deferred_reason
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
    comment_rows = [
        row for row in _ledger_rows(repo) if row["kind"] == "github_comment"
    ]
    assert [row["phase"] for row in comment_rows] == ["running", "defer"]
    assert {row["task_id"] for row in comment_rows} == {result.task_id}


def test_post_provider_persistence_failure_retains_spend_phase_and_task_accounting(
    planted_repo: tuple[Path, str, str], github_server: RecordingGitHub, monkeypatch
) -> None:
    from attest.review.candidates import CandidateStore
    from attest.review.ci import run_ci

    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), '{"test_body":"assert False"}')

    def fail_candidate_persistence(self, task_id, alpha, results):  # noqa: ANN001
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
    assert result.surfaced_count == 4
    comments = github_server.review_bodies[0]["comments"]
    assert isinstance(comments, list)
    assert len(comments) == 3
    assert all(str(finding["claim"]) in github_server.status_bodies[-1] for finding in findings)
    rows = _ledger_rows(repo)
    final = next(row for row in rows if row["kind"] == "ci_final")
    assert float(final["spend_usd"]) == pytest.approx(result.spend_usd)
    decisions = final["decisions"]
    assert isinstance(decisions, list)
    assert len(decisions) == 4
    assert {decision["action"] for decision in decisions} == {"surface"}

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
    assert result.surfaced_count == 4
    assert result.deferred_reason is not None
    comments = github_server.review_bodies[0]["comments"]
    assert isinstance(comments, list)
    assert len(comments) == 3
    sticky = github_server.status_bodies[-1]
    assert "DEFER" in sticky
    assert all(str(finding["claim"]) in sticky for finding in surfaced)
    for private_detail in (
        deferred["claim"],
        deferred["failure_scenario"],
        deferred["falsification_plan"],
    ):
        assert str(private_detail) not in sticky
