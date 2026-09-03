"""G-RELEASE-001 operational drills, minimal set: kill switch and rollback.

Offline and free. No model call, no credential, no network beyond a git
repository this script creates in a temporary directory. Every drill drives
the product's own code path -- `resolve_review_policy`, `run_review`,
`verify_bundle` -- rather than restating what those functions are supposed to
do, and every drill carries a negative control, because a drill that cannot
fail proves nothing.

    python scripts/release/drill.py --all
    python scripts/release/drill.py --all --record docs/acceptance/<date>-drills.md

The remaining seven drills named by G-RELEASE-001 (revoked credential, GitHub
outage, executor unavailable, budget exhaustion, superseded pull request,
malicious same-repository change, verifier failure) are not implemented here.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from attest.certification.types import AcceptedReceipt  # noqa: E402
from attest.execution.backends import select_backend  # noqa: E402
from attest.execution.container_adapter import CONTAINER_PROFILE  # noqa: E402
from attest.execution.types import LOCAL_DEVELOPMENT_PROFILE  # noqa: E402
from attest.github.client import GitHubClient  # noqa: E402
from attest.github.context import PullRequestContext  # noqa: E402
from attest.review.budget import Budget  # noqa: E402
from attest.review.candidates import StoredCandidate  # noqa: E402
from attest.review.ci import run_ci  # noqa: E402
from attest.review.config import (  # noqa: E402
    DISABLED_REASON,
    ReviewConfig,
    resolve_review_policy,
)
from attest.review.evidence import verify_bundle  # noqa: E402
from attest.review.executor import (  # noqa: E402
    ExecutionOutcome,
    ExecutorLimits,
    verify_candidate,
)
from attest.review.gate import GateResult  # noqa: E402
from attest.review.proposer import ProviderResult  # noqa: E402
from attest.review.run import run_review  # noqa: E402
from attest.review.schema import Finding  # noqa: E402


@dataclass
class Drill:
    name: str
    checks: list[tuple[str, bool, str]] = field(default_factory=list)

    def check(self, what: str, passed: bool, detail: str = "") -> None:
        self.checks.append((what, bool(passed), detail))

    @property
    def passed(self) -> bool:
        return all(passed for _, passed, _ in self.checks)


class ScriptedProvider:
    """Replays one proposal and one reproduction; counts every call so a drill
    can assert that nothing was bought."""

    def __init__(self) -> None:
        self.calls = 0

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
            payload = json.dumps(
                {
                    "test_body": "import runpy\n\n"
                    "def test_average_handles_empty_input():\n"
                    "    average = runpy.run_path('app.py')['average']\n"
                    "    assert average([]) == 0\n"
                }
            )
        else:
            payload = json.dumps(
                {
                    "findings": [
                        {
                            "claim": "average() divides by zero when items is empty.",
                            "anchor": {"file": "app.py", "line": 6},
                            "failure_scenario": "average([]) raises ZeroDivisionError",
                            "falsification_plan": (
                                "call average([]) and require a safe empty result"
                            ),
                        }
                    ]
                }
            )
        return ProviderResult(text=payload, input_tokens=10, output_tokens=10)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _planted_repo(
    root: Path, *, base_policy: str | None, head_policy: str | None
) -> tuple[str, str]:
    """A regression a reproduction can certify: `average` is correct on base and
    divides by zero on head. `base_policy`/`head_policy` write `.attest.toml`
    on each side, so a drill can put a different answer on each."""
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "drill@example.com")
    _git(root, "config", "user.name", "Release drill")
    (root / "app.py").write_text(
        "def total(items):\n"
        "    return sum(items)\n\n\n"
        "def average(items):\n"
        "    if not items:\n"
        "        return 0\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    if base_policy is not None:
        (root / ".attest.toml").write_text(base_policy, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "base")
    base_sha = _git(root, "rev-parse", "HEAD")
    (root / "app.py").write_text(
        "def total(items):\n"
        "    return sum(items)\n\n\n"
        "def average(items):\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    if head_policy is not None:
        (root / ".attest.toml").write_text(head_policy, encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "regress average to divide by zero")
    return base_sha, _git(root, "rev-parse", "HEAD")


def drill_kill_switch(workspace: Path) -> Drill:
    """`.attest.toml` on the base branch stops every review of a pull request
    into it, and the head of that pull request cannot flip it back on."""
    drill = Drill("kill switch")

    repo = workspace / "kill-switch"
    repo.mkdir()
    base_sha, _head_sha = _planted_repo(
        repo, base_policy="enabled = false\n", head_policy="enabled = true\n"
    )

    # 1. the trust root: CI resolves the policy at the merge base, and the head
    #    checkout's file -- which says `true` -- is never consulted
    resolved = resolve_review_policy(repo, base_sha, None)
    drill.check(
        "base policy owns the switch; the head cannot flip it",
        resolved.config.enabled is False,
        f"resolved enabled={resolved.config.enabled} from {resolved.source}",
    )

    # 2. the review itself stops before any model call and buys nothing
    provider = ScriptedProvider()
    run = run_review(repo, base_sha, resolved.config, provider, verify=True)
    drill.check("review defers", run.deferred_reason == DISABLED_REASON, str(run.deferred_reason))
    drill.check("no model call", provider.calls == 0, f"{provider.calls} call(s)")
    drill.check("nothing spent", run.budget.spent_usd == 0.0, f"${run.budget.spent_usd:.6f}")
    drill.check("no candidate reached ranking", not run.results, f"{len(run.results)} result(s)")
    drill.check(
        "no evidence bundle written",
        not list((repo / ".attest" / "evidence").glob("*")),
        ".attest/evidence is empty",
    )

    # negative control: the same repository with the switch on must proceed,
    # otherwise the checks above would pass for the wrong reason
    control = workspace / "kill-switch-control"
    control.mkdir()
    control_base, _ = _planted_repo(control, base_policy="enabled = true\n", head_policy=None)
    control_policy = resolve_review_policy(control, control_base, None)
    control_provider = ScriptedProvider()
    control_run = run_review(control, control_base, control_policy.config, control_provider)
    drill.check(
        "negative control: the switch on lets the review run",
        control_provider.calls > 0 and control_run.deferred_reason != DISABLED_REASON,
        f"{control_provider.calls} call(s), deferred={control_run.deferred_reason!r}",
    )
    return drill


def drill_rollback(workspace: Path) -> Drill:
    """A bundle written by this version verifies offline; a bundle whose schema
    version an older verifier would not know is *rejected*, never misread. That
    is what makes rolling the action ref back safe."""
    drill = Drill("rollback")

    repo = workspace / "rollback"
    repo.mkdir()
    base_sha, _head_sha = _planted_repo(repo, base_policy=None, head_policy=None)
    provider = ScriptedProvider()
    run = run_review(
        repo,
        base_sha,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        provider,
        verify=True,
        verification_timeout_s=180.0,
    )
    evidence = repo / ".attest" / "evidence"
    bundles = sorted(p for p in evidence.glob("*/*") if p.is_dir()) if evidence.is_dir() else []
    drill.check(
        "a review of a real regression writes an evidence bundle",
        bool(bundles),
        f"{len(bundles)} bundle(s); deferred={run.deferred_reason!r}",
    )
    if not bundles:
        return drill
    bundle = bundles[0]

    drill.check(
        "the bundle verifies offline as written",
        isinstance(verify_bundle(bundle), AcceptedReceipt),
        str(type(verify_bundle(bundle)).__name__),
    )

    # a version this verifier does not know must be refused, not read anyway:
    # that is the property a rollback to an earlier action ref relies on
    unknown = workspace / "bundle-unknown-version"
    shutil.copytree(bundle, unknown)
    manifest_path = unknown / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema_version"] = "attest.evidence-bundle.v999"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    drill.check(
        "an unknown bundle schema version is rejected, not misread",
        not isinstance(verify_bundle(unknown), AcceptedReceipt),
        str(type(verify_bundle(unknown)).__name__),
    )

    # negative control for the verifier itself: a flipped byte must also reject,
    # otherwise "rejected" above would say nothing about the verifier's teeth
    tampered = workspace / "bundle-tampered"
    shutil.copytree(bundle, tampered)
    target = tampered / "test_repro.py"
    data = bytearray(target.read_bytes())
    data[0] = (data[0] + 1) % 256
    target.write_bytes(bytes(data))
    drill.check(
        "negative control: a flipped byte is rejected",
        not isinstance(verify_bundle(tampered), AcceptedReceipt),
        str(type(verify_bundle(tampered)).__name__),
    )

    # the documented rollback target must exist in this repository
    doc = (ROOT / "docs" / "operations" / "install-ref.md").read_text(encoding="utf-8")
    named = [line for line in doc.splitlines() if "oldest ref" in line]
    ref = ""
    for line in named:
        for token in line.replace("`", " ").split():
            if token.startswith("v0.") or token.startswith("v1."):
                ref = token
                break
    resolved_ref = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--verify", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
    )
    drill.check(
        "the documented oldest rollback target resolves",
        bool(ref) and resolved_ref.returncode == 0,
        f"{ref or '(none named)'} -> {resolved_ref.stdout.strip() or resolved_ref.stderr.strip()}",
    )
    return drill



class FailingProvider:
    """A provider that always raises, with the message a real outage returns."""

    def __init__(self, message: str) -> None:
        self.message = message
        self.calls = 0

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
        raise RuntimeError(self.message)


def _bundles(repo: Path) -> list[Path]:
    evidence = repo / ".attest" / "evidence"
    return sorted(p for p in evidence.glob("*/*") if p.is_dir()) if evidence.is_dir() else []


def _ledger_text(repo: Path) -> str:
    path = repo / ".attest" / "ledger.jsonl"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def drill_revoked_credential(workspace: Path) -> Drill:
    """The model credential is revoked mid-flight. The review must defer with a
    stated reason rather than raise, publish nothing, execute no head code, and
    never write the credential's value anywhere a human or a log can read it."""
    drill = Drill("revoked credential")

    secret = "sk-ant-drill-0000000000000000000000000000"
    repo = workspace / "revoked-credential"
    repo.mkdir()
    base_sha, _head_sha = _planted_repo(repo, base_policy=None, head_policy=None)
    provider = FailingProvider(f"401 authentication_error: invalid x-api-key {secret}")

    previous = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = secret
    try:
        run = run_review(
            repo, base_sha, ReviewConfig(k_samples=2, tier0_commands=[]), provider, verify=True
        )
    finally:
        if previous is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = previous

    drill.check(
        "the review defers with a stated reason, it does not raise",
        run.deferred_reason is not None,
        str(run.deferred_reason),
    )
    drill.check("the credential was actually used", provider.calls > 0, f"{provider.calls} call(s)")
    drill.check("nothing is published", not run.published, f"{len(run.published)} published")
    drill.check("no evidence bundle is written", not _bundles(repo), f"{len(_bundles(repo))}")
    drill.check(
        "no head code is executed",
        not (repo / ".attest" / "repro").exists(),
        ".attest/repro does not exist",
    )
    rendered = str(run.deferred_reason) + " ".join(run.notes)
    drill.check(
        "the credential value is in neither the ledger nor the author-visible text",
        secret not in _ledger_text(repo) and secret not in rendered,
        "redacted",
    )

    # negative control: the same repository with a working provider must reach a
    # receipt, or every check above would pass for the wrong reason
    control = workspace / "revoked-credential-control"
    control.mkdir()
    control_base, _ = _planted_repo(control, base_policy=None, head_policy=None)
    control_run = run_review(
        control,
        control_base,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        ScriptedProvider(),
        verify=True,
        verification_timeout_s=180.0,
    )
    drill.check(
        "negative control: a working credential reaches a receipt",
        bool(control_run.certified) and bool(_bundles(control)),
        f"{len(control_run.certified)} certified, {len(_bundles(control))} bundle(s)",
    )
    return drill


class _StubGitHub:
    """A GitHub API on localhost that either answers or is down. Offline: the
    socket never leaves the loopback interface."""

    def __init__(self, status: int = 200, fail_after: int | None = None) -> None:
        self.status = status
        self.fail_after = fail_after  # writes succeed until this many have been made
        self.writes: list[str] = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    def close(self) -> None:
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: object) -> None:
                return

            def do_GET(self) -> None:  # noqa: N802
                self._respond([])

            def do_POST(self) -> None:  # noqa: N802
                self._respond({"id": 1, "body": ""})

            def do_PATCH(self) -> None:  # noqa: N802
                self._respond({"id": 1, "body": ""})

            def _respond(self, payload: object) -> None:
                length = int(self.headers.get("Content-Length", "0"))
                self.rfile.read(length)
                status = 200
                if self.command != "GET":
                    stub.writes.append(f"{self.command} {self.path}")
                    if stub.fail_after is None or len(stub.writes) > stub.fail_after:
                        status = stub.status
                elif stub.fail_after is None:
                    status = stub.status
                body = json.dumps(payload if status < 400 else {"message": "unavailable"})
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body.encode("utf-8"))

        return Handler


def _ci_context(base_sha: str, head_sha: str) -> PullRequestContext:
    return PullRequestContext(
        repository="owner/drill",
        number=1,
        base_sha=base_sha,
        head_sha=head_sha,
        is_fork=False,
    )


def drill_github_outage(workspace: Path) -> Drill:
    """GitHub is unreachable while a review is publishing. The run must not
    raise, must not record a delivery it did not make, and must keep the
    evidence it earned: the receipt is local, the comment is not."""
    drill = Drill("GitHub outage")

    # the interesting outage is the one that arrives *after* the review has
    # earned its receipt. run_ci writes the running comment, then the
    # discovery-progress comment, then verifies, then publishes: letting the
    # first two writes through and failing every later one puts the 503 exactly
    # on publication. (This branch runs a container, so it needs the same docker
    # the isolation tests need; without one it fails, which is the honest
    # answer for a host that cannot run the production backend.)
    repo = workspace / "github-outage"
    repo.mkdir()
    base_sha, head_sha = _planted_repo(repo, base_policy=None, head_policy=None)
    down = _StubGitHub(status=503, fail_after=2)
    try:
        run = run_ci(
            repo,
            _ci_context(base_sha, head_sha),
            GitHubClient("drill-token", down.url),
            ReviewConfig(k_samples=2, tier0_commands=[]),
            ScriptedProvider(),
            verification_timeout_s=180.0,
        )
    except Exception as exc:  # noqa: BLE001 - the drill's whole point
        drill.check("the run does not raise on an outage", False, f"{type(exc).__name__}: {exc}")
        down.close()
        return drill
    finally:
        with suppress(Exception):
            down.close()

    drill.check("the run does not raise on an outage", True, f"task {run.task_id}")
    settled = [e for e in run.publication_events if e.outcome == "settled"]
    drill.check(
        "no delivery is recorded as settled",
        not settled,
        f"{len(run.publication_events)} event(s), {len(settled)} settled",
    )
    drill.check(
        "the receipt it earned is still on disk",
        bool(_bundles(repo)),
        f"{len(_bundles(repo))} bundle(s)",
    )
    drill.check(
        "the ledger names the outage",
        "503" in _ledger_text(repo) or "unavailable" in _ledger_text(repo).lower(),
        "delivery failure recorded",
    )

    # an outage that is already there when the run starts must stop it before it
    # buys anything at all
    cold = workspace / "github-outage-cold"
    cold.mkdir()
    cold_base, cold_head = _planted_repo(cold, base_policy=None, head_policy=None)
    dead = _StubGitHub(status=503)
    cold_provider = ScriptedProvider()
    try:
        cold_run = run_ci(
            cold,
            _ci_context(cold_base, cold_head),
            GitHubClient("drill-token", dead.url),
            ReviewConfig(k_samples=2, tier0_commands=[]),
            cold_provider,
            verification_timeout_s=180.0,
        )
        cold_raised = ""
    except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
        cold_run = None
        cold_raised = f"{type(exc).__name__}: {exc}"
    finally:
        dead.close()
    drill.check(
        "an outage present at the start buys nothing",
        cold_provider.calls == 0,
        f"{cold_provider.calls} model call(s); "
        + (cold_raised or f"deferred={cold_run.deferred_reason!r}"),
    )

    # negative control: the same run against a GitHub that answers must deliver,
    # or "no delivery recorded" above would pass for the wrong reason
    control = workspace / "github-outage-control"
    control.mkdir()
    control_base, control_head = _planted_repo(control, base_policy=None, head_policy=None)
    up = _StubGitHub(status=200)
    try:
        control_run = run_ci(
            control,
            _ci_context(control_base, control_head),
            GitHubClient("drill-token", up.url),
            ReviewConfig(k_samples=2, tier0_commands=[]),
            ScriptedProvider(),
            verification_timeout_s=180.0,
        )
        writes = list(up.writes)
    finally:
        up.close()
    drill.check(
        "negative control: a reachable GitHub is written to",
        bool(writes) and control_run.task_id is not None,
        f"{len(writes)} write(s)",
    )
    return drill


def drill_executor_unavailable(workspace: Path) -> Drill:
    """No isolation backend. Production must refuse to run head code at all
    rather than fall back to the host, and every candidate must be deferred with
    the reason — never certified, never published."""
    drill = Drill("executor unavailable")

    repo = workspace / "executor-unavailable"
    repo.mkdir()
    base_sha, head_sha = _planted_repo(repo, base_policy=None, head_policy=None)
    up = _StubGitHub(status=200)
    # the outage: no container runtime on this host. The seam is the one
    # function that looks for it, so the rest of the run is the product's own
    # (emptying PATH would also take git away from the review itself)
    import attest.execution.backends as backends_module

    found = backends_module.docker_executable
    backends_module.docker_executable = lambda: None
    try:
        production = select_backend(workspace, production=True)
        drill.check(
            "production has no backend and does not invent one",
            production.adapter is None and production.profile == CONTAINER_PROFILE,
            f"profile={production.profile}; {production.reason}",
        )
        local = select_backend(workspace, production=False)
        drill.check(
            "a local review says in as many words that there is no OS boundary",
            local.profile == LOCAL_DEVELOPMENT_PROFILE and "no OS boundary" in local.reason,
            local.reason,
        )
        run = run_ci(
            repo,
            _ci_context(base_sha, head_sha),
            GitHubClient("drill-token", up.url),
            ReviewConfig(k_samples=2, tier0_commands=[]),
            ScriptedProvider(),
            verification_timeout_s=180.0,
        )
    finally:
        backends_module.docker_executable = found
        up.close()

    ledger = _ledger_text(repo)
    drill.check("the run does not raise", run.task_id is not None, f"task {run.task_id}")
    drill.check("nothing is surfaced", run.surfaced_count == 0, f"{run.surfaced_count} surfaced")
    drill.check("no evidence bundle is written", not _bundles(repo), f"{len(_bundles(repo))}")
    drill.check(
        "the deferral names the executor, not the finding",
        "isolation backend unavailable" in ledger,
        "isolation backend unavailable: docker not found",
    )

    # negative control: with a backend the same repository certifies
    control = workspace / "executor-unavailable-control"
    control.mkdir()
    control_base, _ = _planted_repo(control, base_policy=None, head_policy=None)
    control_run = run_review(
        control,
        control_base,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        ScriptedProvider(),
        verify=True,
        verification_timeout_s=180.0,
    )
    drill.check(
        "negative control: with an executor the same change certifies",
        bool(control_run.certified),
        f"{len(control_run.certified)} certified",
    )
    return drill


def drill_budget_exhaustion(workspace: Path) -> Drill:
    """The per-review budget is spent. The review must stop with an explicit
    budget reason before the call it cannot afford, publish nothing, and never
    truncate an answer to fit."""
    drill = Drill("budget exhaustion")

    repo = workspace / "budget-exhaustion"
    repo.mkdir()
    base_sha, _head_sha = _planted_repo(repo, base_policy=None, head_policy=None)
    provider = ScriptedProvider()
    # small enough that the first proposal sample cannot be reserved
    run = run_review(
        repo,
        base_sha,
        ReviewConfig(k_samples=2, tier0_commands=[], budget_usd=0.000001),
        provider,
        verify=True,
    )

    reason = str(run.deferred_reason)
    drill.check("the review defers on budget", reason.startswith("budget:"), reason)
    drill.check("no call was made", provider.calls == 0, f"{provider.calls} call(s)")
    drill.check("nothing was spent", run.budget.spent_usd == 0.0, f"${run.budget.spent_usd:.6f}")
    drill.check("nothing is published", not run.published, f"{len(run.published)} published")
    drill.check("no evidence bundle is written", not _bundles(repo), f"{len(_bundles(repo))}")
    drill.check(
        "the reason names the limit it hit",
        "exceeds budget" in reason or "share" in reason,
        reason,
    )

    # negative control: the product default funds the same review to a receipt
    control = workspace / "budget-exhaustion-control"
    control.mkdir()
    control_base, _ = _planted_repo(control, base_policy=None, head_policy=None)
    control_run = run_review(
        control,
        control_base,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        ScriptedProvider(),
        verify=True,
        verification_timeout_s=180.0,
    )
    drill.check(
        "negative control: the default budget reaches a receipt",
        bool(control_run.certified),
        f"{len(control_run.certified)} certified at ${control_run.budget.spent_usd:.6f}",
    )
    return drill


def drill_superseded_pull_request(workspace: Path) -> Drill:
    """The head moves while the review is running. Differential evidence is only
    meaningful against the revision it was collected on, so the verification must
    refuse rather than attribute the old evidence to the new head."""
    drill = Drill("superseded pull request")

    repo = workspace / "superseded"
    repo.mkdir()
    base_sha, head_sha = _planted_repo(repo, base_policy=None, head_policy=None)

    # the review is asked for evidence about a head that is no longer checked out
    stored = _stored_candidate(repo)
    superseded = verify_candidate(
        repo,
        stored,
        _gate(stored),
        ScriptedProvider(),
        Budget(limit_usd=1.0, model=ReviewConfig().model),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=base_sha,  # not the checked-out head: the pull request moved
    )
    drill.check(
        "evidence is refused when the workspace head is not the reviewed head",
        superseded.execution.outcome is ExecutionOutcome.DEFERRED,
        str(superseded.execution.reason),
    )
    drill.check(
        "the reason names the mismatch",
        "HEAD does not match" in superseded.execution.reason,
        superseded.execution.reason,
    )

    # a dirty tree is the same failure by another route: the revision under
    # review is no longer immutable
    (repo / "app.py").write_text("# superseded\n", encoding="utf-8")
    dirty = verify_candidate(
        repo,
        stored,
        _gate(stored),
        ScriptedProvider(),
        Budget(limit_usd=1.0, model=ReviewConfig().model),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )
    drill.check(
        "a dirty working tree buys no evidence either",
        dirty.execution.outcome is ExecutionOutcome.DEFERRED
        and "dirty" in dirty.execution.reason,
        dirty.execution.reason,
    )
    _git(repo, "checkout", "--", "app.py")

    # negative control: the same candidate against the head actually checked out
    control_provider = ScriptedProvider()
    control = verify_candidate(
        repo,
        stored,
        _gate(stored),
        control_provider,
        Budget(limit_usd=1.0, model=ReviewConfig().model),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )
    drill.check(
        "negative control: the reviewed head reproduces",
        control.execution.outcome is ExecutionOutcome.REPRODUCED,
        control.execution.reason,
    )
    return drill


def _stored_candidate(repo: Path) -> StoredCandidate:
    return StoredCandidate(
        task_id="drill-superseded",
        finding=Finding(
            claim="average() divides by zero when items is empty.",
            file="app.py",
            line=6,
            failure_scenario="average([]) raises ZeroDivisionError",
            falsification_plan="call average([]) and require a safe empty result",
        ),
        wealth=8.0,
        action="drawer",
        alpha=0.1,
    )


def _gate(stored: StoredCandidate) -> GateResult:
    return GateResult(finding=stored.finding, wealth=stored.wealth, purchases=[], decision=None)



MALICIOUS_MODULE = (
    "import os\n"
    "import socket\n"
    "from pathlib import Path\n\n\n"
    "def total(items):\n"
    "    return sum(items)\n\n\n"
    "def average(items):\n"
    "    # the same-repository change the drill is about: head code that reads a\n"
    "    # secret, opens a socket and writes outside its work directory before it\n"
    "    # answers at all\n"
    "    os.environ.get('ANTHROPIC_API_KEY', '')\n"
    "    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:\n"
    "        s.settimeout(0.2)\n"
    "        s.connect(('127.0.0.1', 9))\n"
    "    Path(os.path.expanduser('~/.attest-drill-escape')).write_text('escaped')\n"
    "    return sum(items) / len(items)\n"
)


def drill_malicious_change(workspace: Path) -> Drill:
    """A same-repository pull request whose head code reads a secret, opens a
    socket and writes outside its work directory. The reproduction must be
    *marked and deferred*, never certified, and the escape must not happen."""
    drill = Drill("malicious same-repository change")

    repo = workspace / "malicious"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "drill@example.com")
    _git(repo, "config", "user.name", "Release drill")
    (repo / "app.py").write_text(
        "def total(items):\n"
        "    return sum(items)\n\n\n"
        "def average(items):\n"
        "    if not items:\n"
        "        return 0\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base_sha = _git(repo, "rev-parse", "HEAD")
    (repo / "app.py").write_text(MALICIOUS_MODULE, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "head: reach for the secret, the network and the home directory")

    escape = Path(os.path.expanduser("~/.attest-drill-escape"))
    existed = escape.exists()
    run = run_review(
        repo,
        base_sha,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        ScriptedProvider(),
        verify=True,
        verification_timeout_s=180.0,
    )

    reasons = list(run.verification_reasons.values())
    drill.check("nothing is certified", not run.certified, f"{len(run.certified)} certified")
    drill.check("nothing is published", not run.published, f"{len(run.published)} published")
    drill.check("no evidence bundle is written", not _bundles(repo), f"{len(_bundles(repo))}")
    drill.check(
        "the run is marked, and the mark names what head code reached for",
        bool(reasons)
        and any(
            word in reason
            for reason in reasons
            for word in ("network", "socket", "wrote", "write", "outside", "attempted")
        ),
        "; ".join(reasons) or "(no verification reason recorded)",
    )
    drill.check(
        "head code did not write outside its work directory",
        escape.exists() == existed,
        f"{escape} {'pre-existing' if existed else 'absent'}",
    )
    if not existed and escape.exists():
        escape.unlink()

    # negative control: the same shape of change without the escape attempts
    # must still certify, or "nothing is certified" would pass for the wrong
    # reason on any planted repository at all
    control = workspace / "malicious-control"
    control.mkdir()
    control_base, _ = _planted_repo(control, base_policy=None, head_policy=None)
    control_run = run_review(
        control,
        control_base,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        ScriptedProvider(),
        verify=True,
        verification_timeout_s=180.0,
    )
    drill.check(
        "negative control: the benign version of the same change certifies",
        bool(control_run.certified),
        f"{len(control_run.certified)} certified",
    )
    return drill



def drill_verifier_failure(workspace: Path) -> Drill:
    """The offline verifier is the last line: a receipt is only worth what an
    independent reader can recompute. Every way a bundle can be wrong must be a
    rejection with a reason, never a quiet acceptance."""
    drill = Drill("verifier failure")

    repo = workspace / "verifier-failure"
    repo.mkdir()
    base_sha, _head_sha = _planted_repo(repo, base_policy=None, head_policy=None)
    run = run_review(
        repo,
        base_sha,
        ReviewConfig(k_samples=2, tier0_commands=[]),
        ScriptedProvider(),
        verify=True,
        verification_timeout_s=180.0,
    )
    bundles = _bundles(repo)
    drill.check(
        "a review of a real regression writes a bundle to verify",
        bool(bundles),
        f"{len(bundles)} bundle(s); deferred={run.deferred_reason!r}",
    )
    if not bundles:
        return drill
    bundle = bundles[0]
    drill.check(
        "the intact bundle is accepted",
        isinstance(verify_bundle(bundle), AcceptedReceipt),
        type(verify_bundle(bundle)).__name__,
    )

    def rejected(name: str, mutate: Callable[[Path], None]) -> None:
        copy = workspace / f"verifier-{name}"
        shutil.rmtree(copy, ignore_errors=True)
        shutil.copytree(bundle, copy)
        mutate(copy)
        verdict = verify_bundle(copy)
        drill.check(
            f"rejected: {name}",
            not isinstance(verdict, AcceptedReceipt),
            type(verdict).__name__,
        )

    def drop_manifest(copy: Path) -> None:
        (copy / "manifest.json").unlink()

    def drop_runs(copy: Path) -> None:
        shutil.rmtree(copy / "runs")

    def rewrite_outcome(copy: Path) -> None:
        path = copy / "receipt.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        for side in ("base_runs", "head_runs"):
            runs = receipt.get(side)
            if isinstance(runs, list) and runs:
                receipt[side] = list(reversed(runs))
        path.write_text(json.dumps(receipt), encoding="utf-8")

    def swap_test(copy: Path) -> None:
        (copy / "test_repro.py").write_text(
            "def test_repro():\n    assert True\n", encoding="utf-8"
        )

    rejected("a bundle with no manifest", drop_manifest)
    rejected("a bundle whose run records were removed", drop_runs)
    rejected("a receipt whose run outcomes were rewritten", rewrite_outcome)
    rejected("a bundle whose test was swapped for a passing one", swap_test)

    # the seal: a bundle verified without the controller key must not be
    # reported as sealed, and --require-seal must refuse it outright
    unsealed = workspace / "verifier-unsealed"
    shutil.rmtree(unsealed, ignore_errors=True)
    shutil.copytree(bundle, unsealed)
    verdict = verify_bundle(unsealed, require_seal=True)
    drill.check(
        "a copied bundle is refused when the seal is required and no key is present",
        not isinstance(verdict, AcceptedReceipt),
        type(verdict).__name__,
    )
    return drill


DRILLS = {
    "kill-switch": drill_kill_switch,
    "rollback": drill_rollback,
    "revoked-credential": drill_revoked_credential,
    "github-outage": drill_github_outage,
    "executor-unavailable": drill_executor_unavailable,
    "budget-exhaustion": drill_budget_exhaustion,
    "superseded-pull-request": drill_superseded_pull_request,
    "malicious-change": drill_malicious_change,
    "verifier-failure": drill_verifier_failure,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--all", action="store_true", help="run every implemented drill")
    parser.add_argument("--only", default=None, help=f"one of {', '.join(DRILLS)}")
    parser.add_argument(
        "--offline", action="store_true", help="accepted and ignored: every drill is offline"
    )
    parser.add_argument("--record", default=None, help="write the result table to this path")
    args = parser.parse_args(argv)

    names = [args.only] if args.only else list(DRILLS)
    if args.only and args.only not in DRILLS:
        parser.error(f"unknown drill {args.only!r}")

    results: list[Drill] = []
    with tempfile.TemporaryDirectory(prefix="attest-drill-") as workspace:
        # the strict ledger refuses a path with a symlinked ancestor, and on
        # macOS the system temporary directory is one
        root = Path(workspace).resolve()
        for name in names:
            drill = DRILLS[name](root)
            results.append(drill)
            print(f"\n== {drill.name}: {'PASS' if drill.passed else 'FAIL'}")
            for what, passed, detail in drill.checks:
                mark = "ok  " if passed else "FAIL"
                print(f"   {mark} {what}" + (f"  [{detail}]" if detail else ""))

    if args.record:
        stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        head = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True, text=True
        ).stdout.strip()
        lines = [
            "# G-RELEASE-001 operational drills (kill switch, rollback)",
            "",
            f"Run {stamp} at `{head[:7]}` by `scripts/release/drill.py`. Offline: no model call,",
            "no credential, no network. Seven of the nine named drills are not implemented.",
            "",
            "| drill | check | result | detail |",
            "|---|---|---|---|",
        ]
        for drill in results:
            for what, passed, detail in drill.checks:
                verdict = "pass" if passed else "**fail**"
                lines.append(f"| {drill.name} | {what} | {verdict} | {detail} |")
        lines.append("")
        Path(args.record).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nrecorded -> {args.record}")

    return 0 if all(drill.passed for drill in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
