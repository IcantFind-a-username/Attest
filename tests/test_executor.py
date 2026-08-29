from __future__ import annotations

import json
import os
import signal
import subprocess
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


class RecordingProvider:
    def __init__(
        self,
        result: ProviderResult | Exception,
        on_sample: Callable[[], None] | None = None,
    ):
        self.result = result
        self.on_sample = on_sample
        self.requests: list[tuple[str, str, dict[str, Any], int]] = []

    def sample(
        self, system: str, prompt: str, schema: dict[str, Any], max_tokens: int
    ) -> ProviderResult:
        self.requests.append((system, prompt, schema, max_tokens))
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


@pytest.mark.skipif(os.name != "posix", reason="PID liveness assertion uses POSIX signals")
def test_execute_timeout_terminates_spawned_child_process(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    pid_path = tmp_path / "spawned-child.pid"
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import subprocess\n"
            "import sys\n"
            "import time\n"
            "from pathlib import Path\n"
            "def test_repro():\n"
            "    child = subprocess.Popen(\n"
            "        [sys.executable, '-c', 'import time; time.sleep(30)'],\n"
            "        stdin=subprocess.DEVNULL,\n"
            "        stdout=subprocess.DEVNULL,\n"
            "        stderr=subprocess.DEVNULL,\n"
            "    )\n"
            "    Path('spawned-child.pid').write_text(str(child.pid))\n"
            "    time.sleep(30)\n"
        ),
        ExecutorLimits(wall_timeout_s=0.8),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    child_pid = int(pid_path.read_text(encoding="utf-8"))
    alive = process_exists(child_pid)
    deadline = time.monotonic() + 2.0
    while alive and time.monotonic() < deadline:
        time.sleep(0.02)
        alive = process_exists(child_pid)
    if alive:
        os.kill(child_pid, signal.SIGKILL)
    assert not alive


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX sessions and file descriptors")
def test_execute_timeout_kills_detached_child_that_retains_pipe(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    pid_path = tmp_path / "detached-child.pid"
    completed_path = tmp_path / "detached-child-completed"
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import os\n"
            "import stat\n"
            "import subprocess\n"
            "import sys\n"
            "import time\n"
            "def test_repro():\n"
            "    pipe_fds = []\n"
            "    for fd in range(3, 256):\n"
            "        try:\n"
            "            if stat.S_ISFIFO(os.fstat(fd).st_mode):\n"
            "                pipe_fds.append(fd)\n"
            "        except OSError:\n"
            "            pass\n"
            "    assert pipe_fds\n"
            "    code = (\n"
            "        \"import os, time; from pathlib import Path; \"\n"
            "        \"Path('detached-child.pid').write_text(str(os.getpid())); \"\n"
            "        \"time.sleep(4); Path('detached-child-completed').touch()\"\n"
            "    )\n"
            "    subprocess.Popen(\n"
            "        [sys.executable, '-c', code],\n"
            "        stdin=subprocess.DEVNULL,\n"
            "        stdout=subprocess.DEVNULL,\n"
            "        stderr=subprocess.DEVNULL,\n"
            "        pass_fds=tuple(pipe_fds),\n"
            "        start_new_session=True,\n"
            "    )\n"
            "    time.sleep(30)\n"
        ),
        ExecutorLimits(wall_timeout_s=0.4),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    child_pid = int(pid_path.read_text(encoding="utf-8"))
    alive = process_exists(child_pid)
    observation_deadline = time.monotonic() + 1.0
    while alive and time.monotonic() < observation_deadline:
        time.sleep(0.02)
        alive = process_exists(child_pid)
    if alive:
        os.kill(child_pid, signal.SIGKILL)
    assert result.elapsed_s < 2.0
    assert not alive
    assert not completed_path.exists()


@pytest.mark.skipif(os.name != "posix", reason="requires POSIX sessions and file descriptors")
def test_execute_tracks_detached_pipe_holder_before_pytest_exits(tmp_path: Path) -> None:
    from attest.review.executor import (
        ExecutionOutcome,
        ExecutorLimits,
        ReproSpec,
        execute_repro,
    )

    pid_path = tmp_path / "normal-exit-child.pid"
    completed_path = tmp_path / "normal-exit-child-completed"
    result = execute_repro(
        tmp_path,
        candidate(line=1),
        ReproSpec(
            "import os\n"
            "import stat\n"
            "import subprocess\n"
            "import sys\n"
            "import time\n"
            "def test_repro():\n"
            "    pipe_fds = []\n"
            "    for fd in range(3, 256):\n"
            "        try:\n"
            "            if stat.S_ISFIFO(os.fstat(fd).st_mode):\n"
            "                pipe_fds.append(fd)\n"
            "        except OSError:\n"
            "            pass\n"
            "    assert pipe_fds\n"
            "    code = (\n"
            "        \"import os, time; from pathlib import Path; \"\n"
            "        \"Path('normal-exit-child.pid').write_text(str(os.getpid())); \"\n"
            "        \"time.sleep(4); Path('normal-exit-child-completed').touch()\"\n"
            "    )\n"
            "    subprocess.Popen(\n"
            "        [sys.executable, '-c', code],\n"
            "        stdin=subprocess.DEVNULL,\n"
            "        stdout=subprocess.DEVNULL,\n"
            "        stderr=subprocess.DEVNULL,\n"
            "        pass_fds=tuple(pipe_fds),\n"
            "        start_new_session=True,\n"
            "    )\n"
            "    time.sleep(0.3)\n"
        ),
        ExecutorLimits(wall_timeout_s=0.8),
    )

    assert result.outcome is ExecutionOutcome.DEFERRED
    child_pid = int(pid_path.read_text(encoding="utf-8"))
    alive = process_exists(child_pid)
    observation_deadline = time.monotonic() + 1.0
    while alive and time.monotonic() < observation_deadline:
        time.sleep(0.02)
        alive = process_exists(child_pid)
    if alive:
        os.kill(child_pid, signal.SIGKILL)
    assert result.elapsed_s < 2.0
    assert not alive
    assert not completed_path.exists()


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
    ("test_body", "outcome", "wealth", "detail"),
    [
        (
            "def test_repro():\n    assert False",
            "reproduced",
            160.0,
            "reproduced",
        ),
        (
            "def test_repro():\n    assert True",
            "not_reproduced",
            4.0,
            "reproduction failed",
        ),
    ],
)
def test_verify_candidate_applies_only_conclusive_evidence_and_records_it(
    tmp_path: Path,
    test_body: str,
    outcome: str,
    wealth: float,
    detail: str,
) -> None:
    from attest.review.executor import ExecutorLimits, verify_candidate

    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": test_body}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_candidate(
        tmp_path,
        stored,
        gate,
        provider,
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
    )

    assert verification.execution.outcome.value == outcome
    assert verification.gate_result is not gate
    assert verification.gate_result.wealth == wealth
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S", "V"]
    assert verification.gate_result.purchases[-1].detail == detail
    row = Ledger(tmp_path).entries()[-1]
    assert row["kind"] == "verification"
    assert row["task_id"] == stored.task_id
    assert row["finding_id"] == stored.finding.finding_id
    assert row["outcome"] == outcome
    assert row["evidence"]


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

    gate = original_gate(stored)
    verification = verify_candidate(
        tmp_path,
        stored,
        gate,
        RecordingProvider(provider_result),
        Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        ExecutorLimits(),
    )

    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert reason_fragment in verification.execution.reason
    assert verification.gate_result is gate
    assert [purchase.channel for purchase in gate.purchases] == ["S"]
    row = Ledger(tmp_path).entries()[-1]
    assert row["kind"] == "verification"
    assert row["task_id"] == stored.task_id
    assert row["finding_id"] == stored.finding.finding_id
    assert row["outcome"] == "deferred"
    assert reason_fragment in row["reason"]
