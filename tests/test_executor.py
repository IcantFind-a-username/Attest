from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.config import load_pricing
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
            "import pytest\n"
            "def test_repro():\n"
            "    with pytest.raises(PermissionError, match='network disabled'):\n"
            "        socket.create_connection(('127.0.0.1', 9))\n"
        ),
        ExecutorLimits(),
    )

    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED
    assert result.exit_code == 0
    assert result.network_blocked is True
