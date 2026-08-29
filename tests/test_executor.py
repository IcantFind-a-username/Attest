from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import tracemalloc
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.channels import ChannelPurchase
from attest.review.config import load_pricing
from attest.review.gate import GateResult
from attest.review.ledger import Ledger
from attest.review.proposer import ProviderResult
from attest.review.schema import Finding

DEFAULT_MODEL = str(load_pricing()["default_model"])
GOOD_MODULE = "def add(a, b):\n    return a + b\n"
BUGGY_MODULE = "def add(a, b):\n    return a - b\n"
DIFFERENTIAL_BODY = "import mod\n\ndef test_repro():\n    assert mod.add(2, 2) == 4"
NEW_FUNCTION_MODULE = GOOD_MODULE + '\n\ndef parse(text):\n    return text.split(",")[-1]\n'
NEW_FUNCTION_BODY = 'import mod\n\ndef test_repro():\n    assert mod.parse("a,b") == "a"\n'
NEW_MODULE = 'def parse(text):\n    return text.split(",")[-1]\n'
NEW_MODULE_BODY = 'import newmod\n\ndef test_repro():\n    assert newmod.parse("a,b") == "a"\n'
FABRICATED_BODY = (
    "import mod\n\ndef test_repro():\n    assert mod.totally_absent_symbol(2) == 4\n"
)
# The live acceptance case: base ships only total(); head adds average() with no
# empty-input guard, and the reproduction crashes rather than asserting.
TOTAL_ONLY_MODULE = "def total(items):\n    return sum(items)\n"
AVERAGE_MODULE = TOTAL_ONLY_MODULE + "\n\ndef average(items):\n    return sum(items) / len(items)\n"
AVERAGE_CRASH_BODY = "import mod\n\ndef test_repro():\n    mod.average([])\n"
LABEL_MODULE = TOTAL_ONLY_MODULE + '\n\ndef label(count):\n    return "n=" + count\n'
LABEL_CRASH_BODY = "import mod\n\ndef test_repro():\n    mod.label(3)\n"
FIRST_MODULE = TOTAL_ONLY_MODULE + "\n\ndef first(items):\n    return items[0]\n"
FIRST_CRASH_BODY = "import mod\n\ndef test_repro():\n    mod.first([])\n"
# Symbol present on BOTH trees and the assertion is false on both: genuinely
# unfaithful, and must stay that way.
BOTH_TREES_FALSE_BODY = "import mod\n\ndef test_repro():\n    assert mod.add(2, 2) == 5\n"


class RecordingProvider:
    def __init__(
        self,
        result: ProviderResult | Exception,
        on_sample: Callable[[], None] | None = None,
    ):
        self.result = result
        self.on_sample = on_sample
        self.requests: list[tuple[str, str, dict[str, Any], int]] = []
        self.timeouts: list[float | None] = []

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        self.requests.append((system, prompt, schema, max_tokens))
        self.timeouts.append(timeout_s)
        if self.on_sample is not None:
            self.on_sample()
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def candidate(
    file: str = "pkg/example.py", line: int = 150, task_id: str = "task-42"
) -> StoredCandidate:
    return StoredCandidate(
        task_id=task_id,
        finding=Finding(
            claim="The boundary check accepts an invalid value.",
            file=file,
            line=line,
            failure_scenario="Passing -1 reaches the unsafe branch.",
            falsification_plan="Call validate(-1) and assert that it is rejected.",
        ),
        wealth=8.0,
        action="drawer",
        alpha=0.1,
    )


def write_anchor_file(repo: Path, lines: int = 300) -> None:
    path = repo / "pkg" / "example.py"
    path.parent.mkdir(parents=True)
    path.write_text("".join(f"line_{number} = {number}\n" for number in range(1, lines + 1)))


def process_exists(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def original_gate(stored: StoredCandidate) -> GateResult:
    return GateResult(
        finding=stored.finding,
        wealth=stored.wealth,
        purchases=[ChannelPurchase("S", 2.0, "existing evidence")],
        decision=None,
    )


def run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.email=executor@example.test",
            "-c",
            "user.name=executor-tests",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def differential_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Real repo: base commit with a working module, head commit with the bug."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    (repo / "mod.py").write_text(GOOD_MODULE, encoding="utf-8")
    run_git(repo, "add", "mod.py")
    run_git(repo, "commit", "-m", "base: working module")
    base_sha = run_git(repo, "rev-parse", "HEAD")
    (repo / "mod.py").write_text(BUGGY_MODULE, encoding="utf-8")
    run_git(repo, "commit", "-am", "head: introduce the bug")
    head_sha = run_git(repo, "rev-parse", "HEAD")
    return repo, base_sha, head_sha


def two_commit_repo(
    tmp_path: Path, base_files: dict[str, str], head_files: dict[str, str]
) -> tuple[Path, str, str]:
    """Real repo whose base commit holds `base_files` and whose head commit
    holds exactly `head_files` (files absent from head are deleted)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    for name, text in base_files.items():
        (repo / name).write_text(text, encoding="utf-8")
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", "base")
    base_sha = run_git(repo, "rev-parse", "HEAD")
    for name in base_files:
        if name not in head_files:
            (repo / name).unlink()
    for name, text in head_files.items():
        (repo / name).write_text(text, encoding="utf-8")
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", "head")
    head_sha = run_git(repo, "rev-parse", "HEAD")
    return repo, base_sha, head_sha


def assert_worktrees_cleaned(repo: Path, stored: StoredCandidate) -> None:
    trees = repo / ".attest" / "repro" / stored.task_id / stored.finding.finding_id / "trees"
    assert not trees.exists()
    assert len(run_git(repo, "worktree", "list").splitlines()) == 1


def test_generate_uses_literal_schema_and_candidate_details(tmp_path: Path) -> None:
    from attest.review.executor import generate_repro

    write_anchor_file(tmp_path)
    provider = RecordingProvider(
        ProviderResult(
            text='{"test_body":"def test_repro():\\n    assert False"}',
            input_tokens=9,
            output_tokens=7,
        )
    )
    budget = Budget(limit_usd=1.0, model=DEFAULT_MODEL)

    spec = generate_repro(tmp_path, candidate(), provider, budget)

    assert spec.test_body == "def test_repro():\n    assert False"
    _, prompt, schema, _ = provider.requests[0]
    assert schema == {
        "type": "object",
        "properties": {"test_body": {"type": "string"}},
        "required": ["test_body"],
        "additionalProperties": False,
    }
    assert "The boundary check accepts an invalid value." in prompt
    assert "Passing -1 reaches the unsafe branch." in prompt
    assert "Call validate(-1) and assert that it is rejected." in prompt
    assert "pkg/example.py:150" in prompt
    assert budget.calls == [
        {
            "label": f"verify-{candidate().finding.finding_id}",
            "input_tokens": 9,
            "output_tokens": 7,
            "cost_usd": pytest.approx(budget.spent_usd),
        }
    ]
    assert budget.reserved_usd == 0.0


def test_verify_passes_remaining_shared_deadline_to_repro_provider(tmp_path: Path) -> None:
    from attest.review.executor import ExecutorLimits, verify_candidate

    repo, base_sha, head_sha = differential_repo(tmp_path)
    provider = RecordingProvider(
        ProviderResult(
            text='{"test_body":"def test_repro(): assert True"}',
            input_tokens=1,
            output_tokens=1,
        )
    )

    verify_candidate(
        repo,
        candidate(line=1),
        original_gate(candidate(line=1)),
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
        deadline=15.0,
        clock=lambda: 10.0,
    )

    assert provider.timeouts == [5.0]


def test_generate_limits_source_context_to_200_lines_around_anchor(tmp_path: Path) -> None:
    from attest.review.executor import generate_repro

    write_anchor_file(tmp_path)
    provider = RecordingProvider(
        ProviderResult(
            text='{"test_body":"def test_repro(): pass"}', input_tokens=1, output_tokens=1
        )
    )

    generate_repro(
        tmp_path,
        candidate(),
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
    )

    prompt = provider.requests[0][1]
    source_lines = [line for line in prompt.splitlines() if line.startswith("line_")]
    assert len(source_lines) == 200
    assert source_lines[0] == "line_50 = 50"
    assert source_lines[-1] == "line_249 = 249"
    assert "line_49 = 49" not in prompt
    assert "line_250 = 250" not in prompt


def test_generate_does_not_read_anchor_context_outside_repo(tmp_path: Path) -> None:
    from attest.review.executor import generate_repro

    repo = tmp_path / "repo"
    repo.mkdir()
    (tmp_path / "secret.py").write_text("outside_secret = 'must-not-leak'\n", encoding="utf-8")
    provider = RecordingProvider(
        ProviderResult(
            text='{"test_body":"def test_repro(): pass"}', input_tokens=1, output_tokens=1
        )
    )

    generate_repro(
        repo,
        candidate(file="../secret.py", line=1),
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
    )

    assert "must-not-leak" not in provider.requests[0][1]


def test_generate_reserves_budget_before_provider_and_settles_afterward(tmp_path: Path) -> None:
    from attest.review.executor import generate_repro

    write_anchor_file(tmp_path)
    budget = Budget(limit_usd=1.0, model=DEFAULT_MODEL)
    reserved_during_call: list[float] = []
    provider = RecordingProvider(
        ProviderResult(
            text='{"test_body":"def test_repro(): pass"}', input_tokens=2, output_tokens=3
        ),
        on_sample=lambda: reserved_during_call.append(budget.reserved_usd),
    )

    generate_repro(tmp_path, candidate(), provider, budget)

    assert reserved_during_call[0] > 0.0
    assert budget.reserved_usd == 0.0
    assert len(budget.calls) == 1
    assert budget.calls[0]["label"] == f"verify-{candidate().finding.finding_id}"


def test_generate_cancels_reservation_when_provider_raises(tmp_path: Path) -> None:
    from attest.review.executor import generate_repro

    write_anchor_file(tmp_path)
    budget = Budget(limit_usd=1.0, model=DEFAULT_MODEL)
    provider = RecordingProvider(RuntimeError("provider unavailable"))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        generate_repro(tmp_path, candidate(), provider, budget)

    assert budget.reserved_usd == 0.0
    assert budget.spent_usd == 0.0
    assert budget.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"test_body": 17},
        {"test_body": "def test_repro(): pass", "extra": True},
        ["def test_repro(): pass"],
    ],
)
def test_generate_rejects_malformed_output_after_settling(
    tmp_path: Path, payload: object
) -> None:
    from attest.review.executor import generate_repro

    write_anchor_file(tmp_path)
    budget = Budget(limit_usd=1.0, model=DEFAULT_MODEL)
    provider = RecordingProvider(
        ProviderResult(text=json.dumps(payload), input_tokens=2, output_tokens=3)
    )

    with pytest.raises(ValueError, match="generator output"):
        generate_repro(tmp_path, candidate(), provider, budget)

    assert budget.reserved_usd == 0.0
    assert len(budget.calls) == 1


def test_execute_assertion_failure_is_reproduced_and_uses_task_path(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    stored = candidate(line=1)
    result = execute_repro(
        tmp_path,
        stored,
        ReproSpec("def test_repro():\n    assert 2 + 2 == 5"),
        ExecutorLimits(),
    )

    expected = (
        tmp_path
        / ".attest"
        / "repro"
        / stored.task_id
        / stored.finding.finding_id
        / "test_repro.py"
    )
    assert expected.read_text(encoding="utf-8") == "def test_repro():\n    assert 2 + 2 == 5\n"
    assert result.outcome is ExecutionOutcome.REPRODUCED
    assert result.exit_code == 1
    assert result.reason == "pytest reported 1 failure(s) and 0 error(s)"
    assert result.elapsed_s > 0.0
    assert result.network_blocked is True


def test_execute_passing_test_is_not_reproduced(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec("def test_repro():\n    assert 2 + 2 == 4"),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert result.exit_code == 0
    assert result.reason == "pytest passed"


@pytest.mark.parametrize(
    ("test_body", "reason_fragment"),
    [
        ("import package_that_does_not_exist", "collection/import/syntax"),
        ("def test_repro(:\n    pass", "collection/import/syntax"),
    ],
)
def test_execute_collection_failures_are_deferred(
    tmp_path: Path, test_body: str, reason_fragment: str
) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(test_body),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.exit_code not in (0, 1)
    assert reason_fragment in result.reason


def test_execute_timeout_is_deferred(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec("import time\ndef test_repro():\n    time.sleep(5)"),
        ExecutorLimits(wall_timeout_s=0.2),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.exit_code is None
    assert "timed out" in result.reason
    assert result.elapsed_s < 2.0


@pytest.mark.skipif(os.name != "posix", reason="kernel process limit is POSIX-only")
def test_execute_defers_atexit_spawn_attempt_without_starting_child(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    child_started = tmp_path / "atexit-child-started"
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import atexit\n"
            "import subprocess\n"
            "import sys\n"
            "def spawn_at_exit():\n"
            "    subprocess.Popen(\n"
            "        [sys.executable, '-c', "
            "\"from pathlib import Path; Path('atexit-child-started').touch()\"],\n"
            "        stdin=subprocess.DEVNULL,\n"
            "        stdout=subprocess.DEVNULL,\n"
            "        stderr=subprocess.DEVNULL,\n"
            "        start_new_session=True,\n"
            "    )\n"
            "atexit.register(spawn_at_exit)\n"
            "def test_repro():\n"
            "    assert True\n"
        ),
        ExecutorLimits(),
    )

    observation_deadline = time.monotonic() + 1.0
    while not child_started.exists() and time.monotonic() < observation_deadline:
        time.sleep(0.02)
    assert not child_started.exists()
    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.reason == "reproduction attempted to create a child process"


@pytest.mark.skipif(os.name != "posix", reason="exec replacement is POSIX-only")
def test_execute_defers_atexit_exec_attempt_without_replacing_pytest(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    replacement_started = tmp_path / "exec-replacement-started"
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import atexit\n"
            "import os\n"
            "import sys\n"
            "def replace_at_exit():\n"
            "    os.execv(\n"
            "        sys.executable,\n"
            "        [sys.executable, '-c', "
            "\"from pathlib import Path; Path('exec-replacement-started').touch()\"],\n"
            "    )\n"
            "atexit.register(replace_at_exit)\n"
            "def test_repro():\n"
            "    assert True\n"
        ),
        ExecutorLimits(),
    )

    assert not replacement_started.exists()
    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.reason == "reproduction attempted to replace the pytest process"


@pytest.mark.skipif(os.name != "posix", reason="native fork is POSIX-only")
def test_execute_kernel_limit_defers_native_fork_without_starting_child(
    tmp_path: Path,
) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    child_started = tmp_path / "native-fork-child-started"
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import ctypes\n"
            "import errno\n"
            "import os\n"
            "from pathlib import Path\n"
            "def test_repro():\n"
            "    libc = ctypes.CDLL(None, use_errno=True)\n"
            "    pid = libc.fork()\n"
            "    if pid == 0:\n"
            "        Path('native-fork-child-started').touch()\n"
            "        os._exit(0)\n"
            "    if pid > 0:\n"
            "        os.waitpid(pid, 0)\n"
            "    assert pid == -1\n"
            "    assert ctypes.get_errno() == errno.EAGAIN\n"
        ),
        ExecutorLimits(),
    )

    assert not child_started.exists()
    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.reason == "reproduction attempted to create a child process"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process containment limits tasks")
def test_execute_defers_python_thread_attempt_without_starting_thread(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    thread_started = tmp_path / "thread-started"
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import threading\n"
            "from pathlib import Path\n"
            "def test_repro():\n"
            "    thread = threading.Thread("
            "target=lambda: Path('thread-started').touch())\n"
            "    thread.start()\n"
            "    thread.join()\n"
        ),
        ExecutorLimits(),
    )

    assert not thread_started.exists()
    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.reason == "reproduction attempted to create a thread"


@pytest.mark.skipif(os.name != "posix", reason="POSIX process containment limits tasks")
def test_generated_guard_blocks_joinable_thread_entrypoint(tmp_path: Path) -> None:
    import attest.review.executor as executor

    escaped_thread = tmp_path / "joinable-thread-escaped"
    guard_path = tmp_path / "generated_sitecustomize.py"
    guard_path.write_text(
        executor._sitecustomize(
            tmp_path / "network-blocked",
            tmp_path / "process-guarded",
            tmp_path / "process-contained",
            tmp_path / "process-attempted",
            tmp_path / "process-replacement-attempted",
            tmp_path / "thread-attempted",
        ),
        encoding="utf-8",
    )
    probe_path = tmp_path / "joinable_thread_probe.py"
    probe_path.write_text(
        "import _thread\n"
        "import resource\n"
        "import runpy\n"
        "import threading\n"
        "from pathlib import Path\n"
        f"escaped = Path({str(escaped_thread)!r})\n"
        "def unguarded(*args, **kwargs):\n"
        "    escaped.touch()\n"
        "_thread.start_joinable_thread = unguarded\n"
        "threading._start_joinable_thread = unguarded\n"
        "resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))\n"
        f"runpy.run_path({str(guard_path)!r})\n"
        "try:\n"
        "    threading._start_joinable_thread(None)\n"
        "except PermissionError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('joinable thread entrypoint was not guarded')\n",
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "-I", str(probe_path)],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        timeout=10.0,
    )

    assert completed.returncode == 0, completed.stderr.decode(errors="replace")
    assert not escaped_thread.exists()
    assert (tmp_path / "thread-attempted").is_file()


@pytest.mark.skipif(os.name != "posix", reason="POSIX privilege check")
def test_execute_privileged_posix_user_defers_before_running_generated_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.review.executor as executor

    monkeypatch.setattr(executor.os, "getuid", lambda: 0)

    result = executor.execute_repro(
        tmp_path,
        candidate(line=1),
        executor.ReproSpec("def test_repro(): assert False"),
        executor.ExecutorLimits(),
    )

    assert result.outcome is executor.ExecutionOutcome.DEFERRED
    assert result.reason == "process containment unavailable for privileged POSIX user"
    assert not (tmp_path / ".attest" / "repro").exists()


@pytest.mark.skipif(os.name != "posix", reason="POSIX privilege check")
@pytest.mark.parametrize(
    ("capability_state", "reason"),
    [
        (
            True,
            "process containment unavailable: Linux capabilities override RLIMIT_NPROC",
        ),
        (
            None,
            "process containment unavailable: Linux capabilities could not be verified",
        ),
    ],
)
def test_execute_linux_privilege_state_fails_closed_before_generated_code(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capability_state: bool | None,
    reason: str,
) -> None:
    import attest.review.executor as executor

    monkeypatch.setattr(executor.sys, "platform", "linux")
    monkeypatch.setattr(
        executor,
        "_linux_capabilities_override_process_limit",
        lambda: capability_state,
    )

    result = executor.execute_repro(
        tmp_path,
        candidate(line=1),
        executor.ReproSpec("def test_repro(): assert False"),
        executor.ExecutorLimits(),
    )

    assert result.outcome is executor.ExecutionOutcome.DEFERRED
    assert result.reason == reason
    assert not (tmp_path / ".attest" / "repro").exists()


@pytest.mark.skipif(os.name != "posix", reason="kernel process limit is POSIX-only")
def test_execute_defers_subprocess_attempt_without_starting_child(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    child_started = tmp_path / "subprocess-child-started"
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import subprocess\n"
            "import sys\n"
            "def test_repro():\n"
            "    try:\n"
            "        subprocess.Popen(\n"
            "            [sys.executable, '-c', "
            "\"from pathlib import Path; Path('subprocess-child-started').touch()\"],\n"
            "            stdin=subprocess.DEVNULL,\n"
            "            stdout=subprocess.DEVNULL,\n"
            "            stderr=subprocess.DEVNULL,\n"
            "        )\n"
            "    except OSError:\n"
            "        return\n"
            "    raise AssertionError('child process was created')\n"
        ),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.reason == "reproduction attempted to create a child process"
    assert not child_started.exists()


@pytest.mark.skipif(os.name != "posix", reason="PID liveness assertion uses POSIX signals")
def test_execute_post_spawn_failure_cleans_up_owned_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.review.executor as executor

    real_popen = subprocess.Popen
    spawned_pids: list[int] = []

    def recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = real_popen(*args, **kwargs)
        spawned_pids.append(process.pid)
        return process

    def fail_to_start_drainer(self: Any) -> None:
        raise RuntimeError("drainer startup failed")

    monkeypatch.setattr(executor.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(executor.threading.Thread, "start", fail_to_start_drainer)

    result = executor.execute_repro(
        tmp_path,
        candidate(line=1),
        executor.ReproSpec("import time\ndef test_repro(): time.sleep(30)"),
        executor.ExecutorLimits(wall_timeout_s=0.4),
    )

    pytest_pid = spawned_pids[0]
    alive = process_exists(pytest_pid)
    if alive:
        os.killpg(pytest_pid, signal.SIGKILL)
    assert result.outcome is executor.ExecutionOutcome.DEFERRED
    assert "drainer startup failed" in result.reason
    assert not alive


@pytest.mark.skipif(os.name != "posix", reason="PID liveness assertion uses POSIX signals")
def test_execute_owner_constructor_failure_cleans_up_raw_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import attest.review.executor as executor

    real_popen = subprocess.Popen
    spawned_pids: list[int] = []

    def recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen[bytes]:
        process = real_popen(*args, **kwargs)
        spawned_pids.append(process.pid)
        return process

    def fail_owner_construction(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("owner construction failed")

    monkeypatch.setattr(executor.subprocess, "Popen", recording_popen)
    monkeypatch.setattr(executor, "_OwnedProcess", fail_owner_construction)

    result = executor.execute_repro(
        tmp_path,
        candidate(line=1),
        executor.ReproSpec("import time\ndef test_repro(): time.sleep(30)"),
        executor.ExecutorLimits(wall_timeout_s=0.4),
    )

    pytest_pid = spawned_pids[0]
    alive = process_exists(pytest_pid)
    if alive:
        os.killpg(pytest_pid, signal.SIGKILL)
    assert result.outcome is executor.ExecutionOutcome.DEFERRED
    assert "owner construction failed" in result.reason
    assert not alive


def test_execute_non_python_anchor_is_deferred_without_artifacts(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    result = execute_repro(
        tmp_path,
        candidate(file="web/example.js", line=1),
        ReproSpec("def test_repro(): assert False"),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.exit_code is None
    assert result.reason == "unsupported anchor language: .js"
    assert not (tmp_path / ".attest" / "repro").exists()


def test_execute_unsafe_task_identity_is_deferred_without_path_escape(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    result = execute_repro(
        tmp_path,
        candidate(line=1, task_id="../../escaped"),
        ReproSpec("def test_repro(): assert False"),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.reason == "unsafe task identity"
    assert not (tmp_path / "escaped").exists()


def test_execute_resolves_relative_repository_before_building_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    repo = tmp_path / "relative-repo"
    repo.mkdir()
    monkeypatch.chdir(tmp_path)
    stored = candidate(line=1)

    result = execute_repro(
        Path("relative-repo"),
        stored,
        ReproSpec("def test_repro(): assert True"),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert (
        repo
        / ".attest"
        / "repro"
        / stored.task_id
        / stored.finding.finding_id
        / "test_repro.py"
    ).is_file()


def test_execute_can_use_reviewed_project_python_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from attest.review.executor import ExecutionOutcome, ExecutorLimits, ReproSpec, execute_repro

    marker = tmp_path / "project-python-used"
    wrapper = tmp_path / "project-python"
    wrapper.write_text(
        f"#!/bin/sh\nprintf used > {str(marker)!r}\nexec {sys.executable!r} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    monkeypatch.setenv("ATTEST_PROJECT_PYTHON", str(wrapper))

    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec("def test_repro(): assert True"),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert marker.read_text(encoding="utf-8") == "used"


def test_execute_truncates_each_output_stream_to_last_bytes(tmp_path: Path) -> None:
    from attest.review.executor import ExecutorLimits, ReproSpec, execute_repro

    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import sys\n"
            "def test_repro():\n"
            "    print('A' * 5000)\n"
            "    print('B' * 5000, file=sys.stderr)\n"
            "    assert False\n"
        ),
        ExecutorLimits(output_bytes=128),
    )

    assert 0 < len(result.stdout.encode("utf-8")) <= 128
    assert len(result.stderr.encode("utf-8")) <= 128
    assert not result.stdout.startswith("A" * 128)


def test_verification_subprocess_drops_credentials_and_redacts_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from attest.review.executor import ExecutorLimits, verify_candidate

    repo, base_sha, head_sha = differential_repo(tmp_path)
    secret = "credential-that-must-never-reach-artifacts"
    monkeypatch.setenv("GITHUB_TOKEN", secret)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "model-credential")
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps(
                {
                    "test_body": (
                        "import os\n"
                        "def test_secret_isolation():\n"
                        "    assert os.getenv('GITHUB_TOKEN') is None\n"
                        f"    raise AssertionError({secret!r})\n"
                    )
                }
            ),
            input_tokens=1,
            output_tokens=1,
        )
    )

    verification = verify_candidate(
        repo,
        candidate(line=1),
        original_gate(candidate(line=1)),
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(wall_timeout_s=10),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    # the version-independent failure reproduces on both trees: unfaithful
    assert verification.execution.outcome.value == "deferred"
    assert "unfaithful" in verification.execution.reason
    artifact = (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8")
    assert secret not in artifact
    assert "model-credential" not in artifact
    assert "[REDACTED]" in artifact


def test_execute_high_volume_output_uses_bounded_parent_memory(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    tracemalloc.start()
    tracemalloc.reset_peak()
    try:
        result = execute_repro(
            tmp_path,
            candidate(line=1),
            ReproSpec(
                "import os\n"
                "def test_repro():\n"
                "    for _ in range(128):\n"
                "        os.write(1, b'A' * 65536)\n"
                "        os.write(2, b'B' * 65536)\n"
                "    assert False\n"
            ),
            ExecutorLimits(wall_timeout_s=10.0, output_bytes=256),
        )
        _, peak_bytes = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result.outcome is ExecutionOutcome.REPRODUCED
    assert len(result.stdout.encode("utf-8")) <= 256
    assert len(result.stderr.encode("utf-8")) <= 256
    assert peak_bytes < 4_000_000


def test_execute_blocks_socket_connections_with_sitecustomize(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import socket\n"
            "import sys\n"
            "import pytest\n"
            "def test_repro():\n"
            "    assert sys.flags.safe_path\n"
            "    with pytest.raises(PermissionError, match='network disabled'):\n"
            "        socket.create_connection(('127.0.0.1', 9))\n"
        ),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert result.exit_code == 0
    assert result.network_blocked is True


def test_execute_blocks_socket_connections_after_socket_reload(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        result = execute_repro(
            tmp_path,
            candidate(line=1),
            ReproSpec(
                "import importlib\n"
                "import socket\n"
                "import pytest\n"
                "def test_repro():\n"
                "    importlib.reload(socket)\n"
                "    with pytest.raises(PermissionError, match='network disabled'):\n"
                f"        socket.create_connection(('127.0.0.1', {port}), timeout=1.0)\n"
            ),
            ExecutorLimits(),
        )
        listener.settimeout(0.1)
        with pytest.raises(TimeoutError):
            listener.accept()

    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert result.exit_code == 0
    assert result.network_blocked is True


def test_execute_repository_sitecustomize_cannot_shadow_network_guard(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    (tmp_path / "sitecustomize.py").write_text(
        "import socket\nsocket.create_connection = lambda *args, **kwargs: None\n",
        encoding="utf-8",
    )
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import socket\n"
            "import sys\n"
            "import pytest\n"
            "def test_repro():\n"
            "    assert sys.flags.safe_path\n"
            "    with pytest.raises(PermissionError, match='network disabled'):\n"
            "        socket.create_connection(('127.0.0.1', 9))\n"
        ),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert result.network_blocked is True


def test_execute_reports_network_unblocked_when_process_never_starts(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    repo_file = tmp_path / "not-a-repository"
    repo_file.write_text("not a directory", encoding="utf-8")
    result = execute_repro(
        repo_file,
        candidate(line=1),
        ReproSpec("def test_repro(): assert False"),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.network_blocked is False


@pytest.mark.parametrize(
    (
        "test_body",
        "outcome",
        "reason",
        "wealth",
        "detail",
        "head_run_outcomes",
        "base_run_outcomes",
        "evidence_class",
    ),
    [
        (
            DIFFERENTIAL_BODY,
            "reproduced",
            "head FAIL 3/3, base PASS 3/3",
            160.0,
            "reproduced",
            ["reproduced"] * 3,
            ["not_reproduced"] * 3,
            "regression_reproduced",
        ),
        (
            "def test_repro():\n    assert True",
            "not_reproduced",
            "pytest passed on head in 3/3 runs; base not executed",
            4.0,
            "reproduction failed",
            ["not_reproduced"] * 3,
            [],
            "not_reproduced",
        ),
    ],
)
def test_verify_candidate_applies_only_conclusive_evidence_and_records_it(
    tmp_path: Path,
    test_body: str,
    outcome: str,
    reason: str,
    wealth: float,
    detail: str,
    head_run_outcomes: list[str],
    base_run_outcomes: list[str],
    evidence_class: str,
) -> None:
    from attest.review.executor import ExecutorLimits, verify_candidate

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": test_body}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert verification.execution.outcome.value == outcome
    assert verification.execution.reason == reason
    assert verification.execution.evidence_class.value == evidence_class
    assert verification.gate_result is not gate
    assert verification.gate_result.wealth == wealth
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S", "V"]
    assert verification.gate_result.purchases[-1].detail == detail
    row = Ledger(repo).entries()[-1]
    assert row["kind"] == "verification"
    assert row["task_id"] == stored.task_id
    assert row["finding_id"] == stored.finding.finding_id
    assert row["outcome"] == outcome
    assert row["evidence"]
    assert row["mode"] == "differential"
    assert row["base_sha"] == base_sha
    assert row["head_sha"] == head_sha
    assert row["head_runs"] == head_run_outcomes
    assert row["base_runs"] == base_run_outcomes
    assert row["repeats"] == 3
    assert row["evidence_class"] == evidence_class
    assert_worktrees_cleaned(repo, stored)


@pytest.mark.parametrize(
    ("stored", "provider_result", "reason_fragment"),
    [
        (
            candidate(line=1),
            ProviderResult(text="{}", input_tokens=2, output_tokens=3),
            "generator output",
        ),
        (candidate(line=1), RuntimeError("provider down"), "provider down"),
        (
            candidate(file="pkg/example.js", line=1),
            ProviderResult(
                text='{"test_body":"def test_repro(): assert False"}',
                input_tokens=2,
                output_tokens=3,
            ),
            "unsupported anchor language",
        ),
    ],
)
def test_verify_candidate_defers_failures_without_buying_v_evidence(
    tmp_path: Path,
    stored: StoredCandidate,
    provider_result: ProviderResult | Exception,
    reason_fragment: str,
) -> None:
    from attest.review.executor import ExecutionOutcome, ExecutorLimits, verify_candidate

    repo, base_sha, head_sha = differential_repo(tmp_path)
    gate = original_gate(stored)
    verification = verify_candidate(
        repo,
        stored,
        gate,
        RecordingProvider(provider_result),
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert reason_fragment in verification.execution.reason
    assert verification.gate_result is gate
    assert [purchase.channel for purchase in gate.purchases] == ["S"]
    row = Ledger(repo).entries()[-1]
    assert row["kind"] == "verification"
    assert row["task_id"] == stored.task_id
    assert row["finding_id"] == stored.finding.finding_id
    assert row["outcome"] == "deferred"
    assert reason_fragment in row["reason"]


def test_execute_repro_imports_code_from_the_given_tree(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    for name, value in (("tree-one", 1), ("tree-two", 2)):
        tree = tmp_path / name
        (tree / "src").mkdir(parents=True)
        (tree / "mod.py").write_text(f"VALUE = {value}\n", encoding="utf-8")
        (tree / "src" / "nested.py").write_text(f"VALUE = {value}\n", encoding="utf-8")
    body = (
        "import mod\n"
        "import nested\n"
        "def test_repro():\n"
        "    assert (mod.VALUE, nested.VALUE) == (1, 1)\n"
    )
    stored = candidate(line=1)

    matching = execute_repro(
        tmp_path,
        stored,
        ReproSpec(body),
        ExecutorLimits(),
        tree=tmp_path / "tree-one",
        run_label="tree-one",
    )
    differing = execute_repro(
        tmp_path,
        stored,
        ReproSpec(body),
        ExecutorLimits(),
        tree=tmp_path / "tree-two",
        run_label="tree-two",
    )

    assert matching.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert matching.network_blocked is True
    assert differing.outcome is ExecutionOutcome.REPRODUCED
    work = tmp_path / ".attest" / "repro" / stored.task_id / stored.finding.finding_id
    assert (work / "tree-one" / "test_repro.py").is_file()
    assert (work / "tree-two" / "test_repro.py").is_file()


def test_execute_differential_syntax_error_defers_and_cleans_worktrees(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_differential,
    )

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)

    result = execute_differential(
        repo,
        stored,
        ReproSpec("def test_repro(:\n    pass"),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert "collection/import/syntax" in result.reason
    assert len(result.head_runs) == 1
    assert result.base_runs == ()
    assert result.base_sha == base_sha
    assert result.head_sha == head_sha
    assert_worktrees_cleaned(repo, stored)


def test_execute_differential_expired_deadline_defers_before_any_run(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_differential,
    )

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)

    result = execute_differential(
        repo,
        stored,
        ReproSpec(DIFFERENTIAL_BODY),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
        deadline=5.0,
        clock=lambda: 10.0,
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.reason == "shared verification deadline exceeded during differential execution"
    assert result.head_runs == ()
    assert result.base_runs == ()
    assert_worktrees_cleaned(repo, stored)


def test_execute_differential_runs_one_test_source_with_one_interpreter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_differential,
    )

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)
    log = tmp_path / "interpreter-invocations"
    wrapper = tmp_path / "project-python"
    wrapper.write_text(
        f"#!/bin/sh\nprintf 'run\\n' >> {str(log)!r}\nexec {sys.executable!r} \"$@\"\n",
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    monkeypatch.setenv("ATTEST_PROJECT_PYTHON", str(wrapper))

    result = execute_differential(
        repo,
        stored,
        ReproSpec(DIFFERENTIAL_BODY),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert result.outcome is ExecutionOutcome.REPRODUCED
    assert result.reason == "head FAIL 3/3, base PASS 3/3"
    assert result.network_blocked is True
    work = repo / ".attest" / "repro" / stored.task_id / stored.finding.finding_id
    labels = ["head-1", "head-2", "head-3", "base-1", "base-2", "base-3"]
    sources = {(work / label / "test_repro.py").read_bytes() for label in labels}
    assert len(sources) == 1
    assert log.read_text(encoding="utf-8").splitlines() == ["run"] * 6
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_unfaithful_test_failing_on_base_is_deferred(tmp_path: Path) -> None:
    from attest.review.executor import (
        EvidenceClass,
        ExecutionOutcome,
        ExecutorLimits,
        verify_candidate,
    )

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": "def test_repro():\n    assert False"}),
            input_tokens=2,
            output_tokens=3,
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert verification.execution.reason == "unfaithful generated test: fails on base as well"
    assert verification.execution.evidence_class is EvidenceClass.UNFAITHFUL
    assert verification.gate_result is gate
    assert [purchase.channel for purchase in gate.purchases] == ["S"]
    assert [run.outcome.value for run in verification.execution.head_runs] == ["reproduced"] * 3
    assert any(
        run.outcome is ExecutionOutcome.REPRODUCED for run in verification.execution.base_runs
    )
    row = Ledger(repo).entries()[-1]
    assert row["outcome"] == "deferred"
    assert "unfaithful" in row["reason"]
    assert row["evidence_class"] == "unfaithful"
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_flaky_head_reproduction_defers_without_buying_v(
    tmp_path: Path,
) -> None:
    from attest.review.executor import ExecutionOutcome, ExecutorLimits, verify_candidate

    repo, base_sha, head_sha = differential_repo(tmp_path)
    counter = tmp_path / "flaky-counter"
    body = (
        "from pathlib import Path\n"
        f"counter = Path({str(counter)!r})\n"
        "def test_repro():\n"
        "    n = int(counter.read_text()) if counter.exists() else 0\n"
        "    counter.write_text(str(n + 1))\n"
        "    assert n % 2 == 1\n"
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(text=json.dumps({"test_body": body}), input_tokens=2, output_tokens=3)
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert verification.execution.reason == "flaky reproduction on head (2/3 runs failed)"
    assert verification.gate_result is gate
    assert [run.outcome.value for run in verification.execution.head_runs] == [
        "reproduced",
        "not_reproduced",
        "reproduced",
    ]
    assert verification.execution.base_runs == ()
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_deadline_expiring_after_generation_defers_differential(
    tmp_path: Path,
) -> None:
    from attest.review.executor import ExecutionOutcome, ExecutorLimits, verify_candidate

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": DIFFERENTIAL_BODY}), input_tokens=1, output_tokens=1
        )
    )
    times = [10.0]

    def clock() -> float:
        return times.pop(0) if times else 100.0

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
        deadline=15.0,
        clock=clock,
    )

    assert len(provider.requests) == 1
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert (
        verification.execution.reason
        == "shared verification deadline exceeded during differential execution"
    )
    assert verification.execution.head_runs == ()
    assert verification.gate_result is gate
    assert_worktrees_cleaned(repo, stored)


@pytest.mark.parametrize(
    ("violation", "reason"),
    [
        ("dirty", "working tree is dirty; differential evidence requires immutable revisions"),
        ("head_mismatch", "workspace HEAD does not match the reviewed head"),
        ("unresolvable", "unresolvable base/head revision"),
    ],
)
def test_verify_candidate_validates_revisions_before_calling_provider(
    tmp_path: Path,
    violation: str,
    reason: str,
) -> None:
    from attest.review.executor import ExecutionOutcome, ExecutorLimits, verify_candidate

    repo, base_sha, head_sha = differential_repo(tmp_path)
    requested_base, requested_head = base_sha, head_sha
    if violation == "dirty":
        (repo / "mod.py").write_text("def add(a, b):\n    return 0\n", encoding="utf-8")
    elif violation == "head_mismatch":
        requested_head = base_sha
    elif violation == "unresolvable":
        requested_base = "0" * 40
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text='{"test_body":"def test_repro(): pass"}', input_tokens=1, output_tokens=1
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=requested_base,
        head_sha=requested_head,
    )

    assert provider.requests == []
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert verification.execution.reason == reason
    assert verification.gate_result is gate
    row = Ledger(repo).entries()[-1]
    assert row["outcome"] == "deferred"
    assert row["reason"] == reason


ASSERTION_OUTPUT = """\
=================================== FAILURES ===================================
__________________________________ test_repro __________________________________

    def test_repro():
>       assert mod.add(2, 2) == 4
E       assert 0 == 4
E        +  where 0 = <function add at 0x104>(2, 2)

/tmp/repro/test_repro.py:5: AssertionError
=========================== short test summary info ============================
FAILED /tmp/repro/test_repro.py::test_repro
"""

ATTRIBUTE_OUTPUT = """\
=================================== FAILURES ===================================
__________________________________ test_repro __________________________________

    def test_repro():
>       assert mod.parse("a,b") == "a"
E       AttributeError: module 'mod' has no attribute 'parse'

/tmp/repro/test_repro.py:5: AttributeError
"""

COLLECTION_OUTPUT = """\
==================================== ERRORS ====================================
_______________________ ERROR collecting test_repro.py _________________________
ImportError while importing test module '/tmp/repro/test_repro.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
/usr/lib/python3.12/importlib/__init__.py:90: in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
test_repro.py:1: in <module>
    import newmod
E   ModuleNotFoundError: No module named 'newmod'
"""

MIXED_OUTPUT = """\
=================================== FAILURES ===================================
_________________________________ test_lookup __________________________________
E   KeyError: 'threshold'

/tmp/repro/test_repro.py:5: KeyError
__________________________________ test_repro __________________________________
E   assert 3 == 4

/tmp/repro/test_repro.py:9: AssertionError
"""

ECHOED_SOURCE_OUTPUT = """\
=================================== FAILURES ===================================
__________________________________ test_repro __________________________________

    def test_repro():
>       with pytest.raises(NameError):
E       Failed: DID NOT RAISE

/tmp/repro/test_repro.py:5: Failed
"""


@pytest.mark.parametrize(
    ("stdout", "signature"),
    [
        (ASSERTION_OUTPUT, "assertion"),
        (ATTRIBUTE_OUTPUT, "symbol_absent"),
        (COLLECTION_OUTPUT, "symbol_absent"),
        (MIXED_OUTPUT, "assertion"),
        (ECHOED_SOURCE_OUTPUT, "other"),
        ("", "other"),
    ],
)
def test_classify_failure_signature_reads_the_failure_lines(stdout: str, signature: str) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutionResult,
        classify_failure_signature,
    )

    result = ExecutionResult(
        outcome=ExecutionOutcome.REPRODUCED,
        reason="pytest reported 1 failure(s) and 0 error(s)",
        exit_code=1,
        stdout=stdout,
        stderr="",
        elapsed_s=0.1,
        network_blocked=True,
    )

    assert classify_failure_signature(result).value == signature


def test_classify_failure_signature_reads_raw_stderr_tracebacks() -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutionResult,
        classify_failure_signature,
    )

    result = ExecutionResult(
        outcome=ExecutionOutcome.DEFERRED,
        reason="pytest collection/import/syntax or infrastructure failure",
        exit_code=2,
        stdout="",
        stderr=(
            "Traceback (most recent call last):\n"
            '  File "/tmp/repro/conftest.py", line 1, in <module>\n'
            "    import newmod\n"
            "ModuleNotFoundError: No module named 'newmod'\n"
        ),
        elapsed_s=0.1,
        network_blocked=True,
    )

    assert classify_failure_signature(result).value == "symbol_absent"


def test_verify_candidate_new_function_on_head_is_a_new_code_candidate(tmp_path: Path) -> None:
    """The reviewed diff ADDS parse(): the reproduction fails by assertion on
    head while the symbol is absent on base. Signal only -- no V is purchased."""
    from attest.review.executor import (
        EvidenceClass,
        ExecutionOutcome,
        ExecutorLimits,
        verify_candidate,
    )

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path, {"mod.py": GOOD_MODULE}, {"mod.py": NEW_FUNCTION_MODULE}
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": NEW_FUNCTION_BODY}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert verification.execution.evidence_class is EvidenceClass.NEW_CODE_CANDIDATE
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert verification.execution.reason == (
        "new-code candidate: reproduction fails on head and the symbol is absent "
        "on base; not priced"
    )
    assert verification.gate_result is gate
    assert verification.gate_result.wealth == stored.wealth
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S"]
    assert [run.outcome.value for run in verification.execution.head_runs] == ["reproduced"] * 3
    assert verification.execution.base_runs[0].outcome is ExecutionOutcome.REPRODUCED
    row = Ledger(repo).entries()[-1]
    assert row["outcome"] == "deferred"
    assert row["evidence_class"] == "new_code_candidate"
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_new_module_on_head_is_a_new_code_candidate(tmp_path: Path) -> None:
    """Same evidence class when the added symbol lives in a file absent from
    base entirely: the base run is a ModuleNotFoundError collection error."""
    from attest.review.executor import (
        EvidenceClass,
        ExecutionOutcome,
        ExecutorLimits,
        verify_candidate,
    )

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path,
        {"mod.py": GOOD_MODULE},
        {"mod.py": GOOD_MODULE, "newmod.py": NEW_MODULE},
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": NEW_MODULE_BODY}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert verification.execution.evidence_class is EvidenceClass.NEW_CODE_CANDIDATE
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert verification.gate_result is gate
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S"]
    assert verification.execution.base_runs[0].outcome is ExecutionOutcome.DEFERRED
    row = Ledger(repo).entries()[-1]
    assert row["evidence_class"] == "new_code_candidate"
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_crashing_reproduction_on_added_function_is_a_new_code_candidate(
    tmp_path: Path,
) -> None:
    """The live acceptance case. The reviewed diff ADDS `average(items)` with no
    empty-input guard; the generated reproduction calls `average([])` and lets
    ZeroDivisionError propagate -- a genuine crash, not an assertion -- while
    base fails symbol-absent because `average` does not exist there. Most real
    bug reproductions crash rather than assert, so this is the common case, and
    the DEFER copy that reaches the pull request must not call it unfaithful."""
    from attest.review.executor import (
        EvidenceClass,
        ExecutionOutcome,
        ExecutorLimits,
        FailureSignature,
        classify_failure_signature,
        verify_candidate,
    )

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path, {"mod.py": TOTAL_ONLY_MODULE}, {"mod.py": AVERAGE_MODULE}
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": AVERAGE_CRASH_BODY}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    # the head crash is genuinely not assertion-class: that is what used to
    # push this run into UNFAITHFUL
    assert [run.outcome.value for run in verification.execution.head_runs] == ["reproduced"] * 3
    assert all(
        classify_failure_signature(run) is FailureSignature.OTHER
        for run in verification.execution.head_runs
    )
    assert (
        classify_failure_signature(verification.execution.base_runs[0])
        is FailureSignature.SYMBOL_ABSENT
    )
    assert verification.execution.evidence_class is EvidenceClass.NEW_CODE_CANDIDATE
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert verification.execution.reason == (
        "new-code candidate: reproduction fails on head and the symbol is absent "
        "on base; not priced"
    )
    assert "new-code" in verification.execution.reason
    assert "unfaithful" not in verification.execution.reason
    # buys nothing: the caller's gate result comes back untouched
    assert verification.gate_result is gate
    assert verification.gate_result.wealth == stored.wealth
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S"]
    row = Ledger(repo).entries()[-1]
    assert row["outcome"] == "deferred"
    assert row["evidence_class"] == "new_code_candidate"
    assert "unfaithful" not in row["reason"]
    assert_worktrees_cleaned(repo, stored)


@pytest.mark.parametrize(
    ("head_module", "test_body"),
    [
        (AVERAGE_MODULE, AVERAGE_CRASH_BODY),
        (LABEL_MODULE, LABEL_CRASH_BODY),
        (FIRST_MODULE, FIRST_CRASH_BODY),
    ],
    ids=["zero_division", "type_error", "index_error"],
)
def test_verify_candidate_any_genuine_crash_on_added_code_is_a_new_code_candidate(
    tmp_path: Path, head_module: str, test_body: str
) -> None:
    """ZeroDivisionError, TypeError and IndexError are all *the code
    misbehaved*, not *the symbol was never there*; each pairs with a
    symbol-absent base into the same unpriced class."""
    from attest.review.executor import (
        EvidenceClass,
        ExecutionOutcome,
        ExecutorLimits,
        verify_candidate,
    )

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path, {"mod.py": TOTAL_ONLY_MODULE}, {"mod.py": head_module}
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": test_body}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert verification.execution.evidence_class is EvidenceClass.NEW_CODE_CANDIDATE
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert "unfaithful" not in verification.execution.reason
    assert verification.gate_result is gate
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S"]
    assert Ledger(repo).entries()[-1]["evidence_class"] == "new_code_candidate"
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_false_assertion_on_both_trees_is_still_unfaithful(
    tmp_path: Path,
) -> None:
    """`add` exists on head and base alike and the assertion is false on both:
    widening the head-side condition must not let this buy the new-code class."""
    from attest.review.executor import (
        EvidenceClass,
        ExecutionOutcome,
        ExecutorLimits,
        verify_candidate,
    )

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": BOTH_TREES_FALSE_BODY}),
            input_tokens=2,
            output_tokens=3,
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert verification.execution.evidence_class is EvidenceClass.UNFAITHFUL
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert verification.execution.reason == "unfaithful generated test: fails on base as well"
    assert verification.gate_result is gate
    assert Ledger(repo).entries()[-1]["evidence_class"] == "unfaithful"
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_fabricated_symbol_can_never_be_a_new_code_candidate(
    tmp_path: Path,
) -> None:
    """Fabrication guard: a test naming a symbol that exists on neither tree
    fails symbol-absent on HEAD, which the new-code rule excludes outright."""
    from attest.review.executor import (
        EvidenceClass,
        ExecutionOutcome,
        ExecutorLimits,
        FailureSignature,
        classify_failure_signature,
        verify_candidate,
    )

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": FABRICATED_BODY}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_candidate(
        repo,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    # the load-bearing mechanism: HEAD itself reports the symbol as absent
    assert all(
        classify_failure_signature(run) is FailureSignature.SYMBOL_ABSENT
        for run in verification.execution.head_runs
    )
    assert verification.execution.evidence_class is not EvidenceClass.NEW_CODE_CANDIDATE
    assert verification.execution.evidence_class in (
        EvidenceClass.UNFAITHFUL,
        EvidenceClass.INDETERMINATE,
    )
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert verification.gate_result is gate
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S"]
    row = Ledger(repo).entries()[-1]
    assert row["outcome"] == "deferred"
    assert row["evidence_class"] != "new_code_candidate"
    assert_worktrees_cleaned(repo, stored)


def test_execute_differential_flaky_head_is_indeterminate(tmp_path: Path) -> None:
    from attest.review.executor import (
        EvidenceClass,
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_differential,
    )

    repo, base_sha, head_sha = differential_repo(tmp_path)
    counter = tmp_path / "flaky-counter"
    body = (
        "from pathlib import Path\n"
        f"counter = Path({str(counter)!r})\n"
        "def test_repro():\n"
        "    n = int(counter.read_text()) if counter.exists() else 0\n"
        "    counter.write_text(str(n + 1))\n"
        "    assert n % 2 == 1\n"
    )
    stored = candidate(line=1)

    result = execute_differential(
        repo,
        stored,
        ReproSpec(body),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    assert result.evidence_class is EvidenceClass.INDETERMINATE
    assert_worktrees_cleaned(repo, stored)
