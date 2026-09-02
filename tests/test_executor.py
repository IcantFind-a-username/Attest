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
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

import attest.review.executor as executor
from attest.review.budget import Budget, BudgetExceeded
from attest.review.candidates import StoredCandidate
from attest.review.channels import ChannelPurchase
from attest.review.config import load_pricing
from attest.review.executor import (
    EvidenceClass,
    ExecutionOutcome,
    ExecutionResult,
    ExecutorLimits,
    FailureSignature,
    ReproSpec,
    VerificationRun,
    classify_failure_signature,
    execute_differential,
    execute_repro,
    generate_repro,
    verify_candidate,
)
from attest.review.gate import GateResult
from attest.review.ledger import Ledger
from attest.review.proposer import PROPOSER_MAX_OUTPUT_TOKENS, ProviderResult
from attest.review.schema import Finding

VerifyWithDefaults = Callable[..., VerificationRun]

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
# A pure rename refactor: the private helper changes name, its caller follows,
# and behaviour is identical on both trees. A reproduction still naming the old
# helper is a stale reference, not evidence of a defect.
RENAMED_BASE_MODULE = (
    "def _validate(s):\n"
    "    return bool(s)\n"
    "\n"
    "\n"
    "def describe(s):\n"
    '    return "filled" if _validate(s) else "empty"\n'
)
RENAMED_HEAD_MODULE = (
    "def _is_nonempty(s):\n"
    "    return bool(s)\n"
    "\n"
    "\n"
    "def describe(s):\n"
    '    return "filled" if _is_nonempty(s) else "empty"\n'
)
STALE_RENAME_BODY = (
    'import mypkg.calc as m\n\ndef test_x():\n    assert m._validate("") is False\n'
)
# A crash-shaped genuine regression: `mean` exists on both trees, base guards
# the empty list and head does not, so head fails with ZeroDivisionError rather
# than an assertion (the D-022 widening).
GUARDED_MEAN_MODULE = (
    "def mean(items):\n"
    "    if not items:\n"
    "        return 0.0\n"
    "    return sum(items) / len(items)\n"
)
UNGUARDED_MEAN_MODULE = "def mean(items):\n    return sum(items) / len(items)\n"
MEAN_CRASH_BODY = "import mod\n\ndef test_repro():\n    mod.mean([])\n"
# Two genuine regressions whose reproductions fail with KeyError. `threshold`
# and `settings` exist on BOTH trees; base honours the defaults and head drops
# them. The first raises its KeyError deep inside the code under test, the
# second at the reproduction's own assertion -- neither says anything about a
# symbol being absent.
DEFAULTED_LOOKUP_MODULE = (
    'DEFAULTS = {"threshold": 5}\n'
    "\n"
    "\n"
    "def threshold(config):\n"
    '    return config.get("threshold", DEFAULTS["threshold"])\n'
)
UNDEFAULTED_LOOKUP_MODULE = (
    'DEFAULTS = {"threshold": 5}\n'
    "\n"
    "\n"
    "def threshold(config):\n"
    '    return config["threshold"]\n'
)
DEEP_KEY_ERROR_BODY = "import mod\n\ndef test_repro():\n    assert mod.threshold({}) == 5\n"
MERGED_SETTINGS_MODULE = (
    'DEFAULTS = {"threshold": 5}\n'
    "\n"
    "\n"
    "def settings(overrides):\n"
    "    merged = dict(DEFAULTS)\n"
    "    merged.update(overrides)\n"
    "    return merged\n"
)
DROPPED_SETTINGS_MODULE = (
    'DEFAULTS = {"threshold": 5}\n'
    "\n"
    "\n"
    "def settings(overrides):\n"
    "    return dict(overrides)\n"
)
TEST_FRAME_KEY_ERROR_BODY = (
    'import mod\n\ndef test_repro():\n    assert mod.settings({})["threshold"] == 5\n'
)
# The rename refactor of D-029, but on a METHOD rather than a module-level
# helper: the reproduction still names the old attribute on an instance.
RENAMED_METHOD_BASE_MODULE = (
    "class Calculator:\n"
    "    def _validate(self, s):\n"
    "        return bool(s)\n"
    "\n"
    "    def describe(self, s):\n"
    '        return "filled" if self._validate(s) else "empty"\n'
)
RENAMED_METHOD_HEAD_MODULE = (
    "class Calculator:\n"
    "    def _is_nonempty(self, s):\n"
    "        return bool(s)\n"
    "\n"
    "    def describe(self, s):\n"
    '        return "filled" if self._is_nonempty(s) else "empty"\n'
)
STALE_METHOD_RENAME_BODY = (
    'import mod\n\ndef test_repro():\n    assert mod.Calculator()._validate("") is False\n'
)

# A root-level conftest.py is innocuous on its own, but pytest's prepend import
# mode inserts the directory holding it at the front of sys.path, ahead of
# anything PYTHONPATH contributes. Every fixture below therefore ships one.
ROOT_CONFTEST = "# the reviewed project's own root conftest\n"
# Any packaging config at the repository root anchors pytest's rootdir there,
# which in turn makes the root conftest.py above discoverable from a generated
# test written anywhere underneath it.
PYPROJECT = '[project]\nname = "mypkg"\nversion = "0.0.1"\n'
SRC_PATH_CONFTEST = (
    "import sys\n"
    "from pathlib import Path\n"
    "\n"
    'sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))\n'
)
GUARDED_CALC = (
    "def average(items):\n"
    "    if not items:\n"
    "        return 0.0\n"
    "    return sum(items) / len(items)\n"
)
UNGUARDED_CALC = "def average(items):\n    return sum(items) / len(items)\n"
CALC_CRASH_BODY = "import mypkg.calc\n\ndef test_repro():\n    mypkg.calc.average([])\n"
TOTAL_CALC = "def total(items):\n    return sum(items)\n"
FIXTURE_CONFTEST = (
    "import pytest\n"
    "\n"
    "\n"
    "@pytest.fixture\n"
    "def sample_items():\n"
    "    return {items}\n"
)
FIXTURE_BODY = (
    "import mypkg.calc\n"
    "\n"
    "def test_repro(sample_items):\n"
    "    assert mypkg.calc.total(sample_items) == 6\n"
)


@dataclass(frozen=True)
class DifferentialExpectation:
    head_outcomes: tuple[str, ...]
    head_signature: str | None
    base_outcomes: tuple[str, ...]
    base_signature: str | None
    evidence_class: str
    outcome: str
    reason: str
    wealth: float
    channels: tuple[str, ...]
    purchase_detail: str | None = None
    required_reason_fragments: tuple[str, ...] = ()
    forbidden_reason_fragment: str | None = None


class RecordingProvider:
    def __init__(
        self,
        result: ProviderResult | Exception | list[ProviderResult | Exception],
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
        result = self.result.pop(0) if isinstance(self.result, list) else self.result
        if isinstance(result, Exception):
            raise result
        return result


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


def write_layout(root: Path, files: dict[str, str]) -> None:
    """Materialise `files` (relative posix paths -> contents) under `root`."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def provenance_body(tree: Path, modules: tuple[str, ...], origin: str) -> str:
    """A generated reproduction that passes only when every named module was
    imported out of `tree`, and that names the offending file when it was not."""
    lines = [
        "from pathlib import Path",
        "",
        *[f"import {module}" for module in modules],
        "",
        f"TREE = Path({str(tree)!r}).resolve()",
        f"MODULES = ({', '.join(modules)},)",
        "",
        "",
        "def test_repro():",
        "    for module in MODULES:",
        "        resolved = Path(module.__file__).resolve()",
        '        detail = module.__name__ + " -> " + str(resolved)',
        '        detail += " origin=" + module.ORIGIN',
        "        assert TREE in resolved.parents, detail",
        f"        assert module.ORIGIN == {origin!r}, detail",
    ]
    return "\n".join(lines) + "\n"


def provenance_layout(origin: str, *, conftest: str = ROOT_CONFTEST) -> dict[str, str]:
    """A flat module plus a src/ module, both stamped with `origin`, under a
    root-level conftest.py."""
    return {
        "conftest.py": conftest,
        "mod.py": f"ORIGIN = {origin!r}\n",
        "src/nested.py": f"ORIGIN = {origin!r}\n",
    }


def two_commit_repo(
    tmp_path: Path, base_files: dict[str, str], head_files: dict[str, str]
) -> tuple[Path, str, str]:
    """Real repo whose base commit holds `base_files` and whose head commit
    holds exactly `head_files` (files absent from head are deleted)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "--initial-branch=main")
    write_layout(repo, base_files)
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", "base")
    base_sha = run_git(repo, "rev-parse", "HEAD")
    for name in base_files:
        if name not in head_files:
            (repo / name).unlink()
    write_layout(repo, head_files)
    run_git(repo, "add", "--all")
    run_git(repo, "commit", "-m", "head")
    head_sha = run_git(repo, "rev-parse", "HEAD")
    return repo, base_sha, head_sha


def assert_worktrees_cleaned(repo: Path, stored: StoredCandidate) -> None:
    trees = repo / ".attest" / "repro" / stored.task_id / stored.finding.finding_id / "trees"
    assert not trees.exists()
    assert len(run_git(repo, "worktree", "list").splitlines()) == 1


def test_generate_uses_literal_schema_and_candidate_details(tmp_path: Path) -> None:

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
            "label": f"verify-{candidate().finding.finding_id}-attempt-1",
            "input_tokens": 9,
            "output_tokens": 7,
            "cost_usd": pytest.approx(budget.spent_usd),
        }
    ]
    assert budget.reserved_usd == 0.0


def test_verify_passes_remaining_shared_deadline_to_repro_provider(tmp_path: Path) -> None:

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
    assert budget.calls[0]["label"] == f"verify-{candidate().finding.finding_id}-attempt-1"
    assert provider.requests[0][3] == executor.REPRO_MAX_OUTPUT_TOKENS
    assert executor.REPRO_MAX_OUTPUT_TOKENS > PROPOSER_MAX_OUTPUT_TOKENS


def test_generate_cancels_reservation_when_provider_raises(tmp_path: Path) -> None:

    write_anchor_file(tmp_path)
    budget = Budget(limit_usd=1.0, model=DEFAULT_MODEL)
    provider = RecordingProvider(RuntimeError("provider unavailable"))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        generate_repro(tmp_path, candidate(), provider, budget)

    assert budget.reserved_usd == 0.0
    assert budget.spent_usd == 0.0
    assert budget.calls == []


def test_generate_preflights_both_attempts_before_dispatch(tmp_path: Path) -> None:
    write_anchor_file(tmp_path)
    probe = Budget(limit_usd=1.0, model=DEFAULT_MODEL)
    estimate = probe.estimate_cost(10_000, executor.REPRO_MAX_OUTPUT_TOKENS)
    budget = Budget(limit_usd=estimate * 1.5, model=DEFAULT_MODEL)
    provider = RecordingProvider(
        ProviderResult(
            text='{"test_body":"def test_repro(): pass"}', input_tokens=1, output_tokens=1
        )
    )

    with pytest.raises(BudgetExceeded):
        generate_repro(tmp_path, candidate(), provider, budget)

    assert provider.requests == []
    assert budget.reserved_usd == 0.0


def test_generate_retries_schema_failure_once_and_accepts_json_fence(tmp_path: Path) -> None:
    write_anchor_file(tmp_path)
    provider = RecordingProvider(
        [
            ProviderResult(text="{}", input_tokens=2, output_tokens=3),
            ProviderResult(
                text='```json\n{"test_body":"def test_repro(): pass"}\n```',
                input_tokens=4,
                output_tokens=5,
            ),
        ]
    )
    budget = Budget(limit_usd=1.0, model=DEFAULT_MODEL)

    spec = generate_repro(tmp_path, candidate(), provider, budget)

    assert spec.test_body == "def test_repro(): pass"
    assert len(provider.requests) == executor.MAX_REPRO_ATTEMPTS
    assert len(budget.calls) == executor.MAX_REPRO_ATTEMPTS
    assert budget.reserved_usd == 0.0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"test_body": 17},
        {"test_body": "def test_repro(): pass", "extra": True},
        ["def test_repro(): pass"],
    ],
)
def test_generate_rejects_malformed_output_after_settling(tmp_path: Path, payload: object) -> None:

    write_anchor_file(tmp_path)
    budget = Budget(limit_usd=1.0, model=DEFAULT_MODEL)
    provider = RecordingProvider(
        ProviderResult(text=json.dumps(payload), input_tokens=2, output_tokens=3)
    )

    with pytest.raises(ValueError, match="generator output"):
        generate_repro(tmp_path, candidate(), provider, budget)

    assert budget.reserved_usd == 0.0
    assert len(budget.calls) == executor.MAX_REPRO_ATTEMPTS


def test_generate_schema_failure_includes_bounded_redacted_raw_fragment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_anchor_file(tmp_path)
    secret = "generator-secret-that-must-not-be-recorded"
    monkeypatch.setenv("ANTHROPIC_API_KEY", secret)
    provider = RecordingProvider(
        ProviderResult(text=secret + "x" * 600, input_tokens=2, output_tokens=3)
    )

    with pytest.raises(ValueError) as caught:
        generate_repro(
            tmp_path,
            candidate(),
            provider,
            Budget(limit_usd=1.0, model=DEFAULT_MODEL),
        )

    message = str(caught.value)
    assert secret not in message
    assert "[REDACTED]" in message
    assert "[truncated]" in message


def test_execute_assertion_failure_is_reproduced_and_uses_task_path(tmp_path: Path) -> None:

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
    assert "[process audit]" in result.stderr
    assert "event=subprocess.Popen" in result.stderr
    assert "test_repro" in result.stderr


@pytest.mark.skipif(os.name != "posix", reason="PID liveness assertion uses POSIX signals")
def test_execute_post_spawn_failure_cleans_up_owned_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

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
        repo / ".attest" / "repro" / stored.task_id / stored.finding.finding_id / "test_repro.py"
    ).is_file()


def test_execute_can_use_reviewed_project_python_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    marker = tmp_path / "project-python-used"
    wrapper = tmp_path / "project-python"
    wrapper.write_text(
        f'#!/bin/sh\nprintf used > {str(marker)!r}\nexec {sys.executable!r} "$@"\n',
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
    row = Ledger(repo).entries_strict()[-1]
    run_evidence = row["run_evidence"]
    assert [(run["side"], run["repeat"]) for run in run_evidence] == [
        ("collect", 1),  # V-01: the exact-node collection run is evidence too
        ("head", 1),
        ("head", 2),
        ("head", 3),
        ("base", 1),
    ]
    assert all(len(run["stdout"]) <= 2_000 for run in run_evidence)
    assert all(len(run["stderr"]) <= 2_000 for run in run_evidence)


def test_candidate_run_output_fragment_is_bounded_with_visible_marker() -> None:
    fragment = executor._bounded_run_output("A" * 2_500)

    assert len(fragment) == executor.MAX_RUN_OUTPUT_FRAGMENT_CHARS
    assert fragment.startswith("[...truncated...]\n")
    assert fragment.endswith("A" * 100)


def test_execute_high_volume_output_uses_bounded_parent_memory(tmp_path: Path) -> None:

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
    verify_with_defaults: VerifyWithDefaults,
    test_body: str,
    outcome: str,
    reason: str,
    wealth: float,
    detail: str,
    head_run_outcomes: list[str],
    base_run_outcomes: list[str],
    evidence_class: str,
) -> None:

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(text=json.dumps({"test_body": test_body}), input_tokens=2, output_tokens=3)
    )

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
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
    """Provenance, asserted directly: the reproduction must import the revision
    under test even when the reviewed project carries a root-level conftest.py
    whose directory pytest prepends to sys.path."""

    repo = tmp_path / "repo"
    write_layout(repo, provenance_layout("repo-root"))
    trees = {name: repo / "trees" / name for name in ("tree-one", "tree-two")}
    for name, tree in trees.items():
        write_layout(tree, provenance_layout(name))
    stored = candidate(line=1)

    def run(tree: Path, expected: Path, label: str) -> Any:
        return execute_repro(
            repo,
            stored,
            ReproSpec(provenance_body(expected, ("mod", "nested"), expected.name)),
            ExecutorLimits(),
            tree=tree,
            run_label=label,
        )

    one = run(trees["tree-one"], trees["tree-one"], "tree-one")
    two = run(trees["tree-two"], trees["tree-two"], "tree-two")
    # control: the provenance assertion really is able to fail
    mismatched = run(trees["tree-two"], trees["tree-one"], "mismatched")

    assert one.outcome is ExecutionOutcome.NOT_REPRODUCED, f"{one.reason}\n{one.stdout}"
    assert one.network_blocked is True
    assert two.outcome is ExecutionOutcome.NOT_REPRODUCED, f"{two.reason}\n{two.stdout}"
    assert mismatched.outcome is ExecutionOutcome.REPRODUCED
    # the generated source stays on disk under the repository for the audit trail
    work = repo / ".attest" / "repro" / stored.task_id / stored.finding.finding_id
    assert (work / "tree-one" / "test_repro.py").is_file()
    assert (work / "tree-two" / "test_repro.py").is_file()


def test_execute_repro_src_layout_with_root_conftest_imports_from_the_given_tree(
    tmp_path: Path,
) -> None:
    """src/ layout whose root conftest.py puts its own src/ on sys.path: the
    tree's conftest must win, not the one sitting in the repository root."""

    repo = tmp_path / "repo"
    decoy = {
        "conftest.py": SRC_PATH_CONFTEST,
        "src/mypkg/__init__.py": "",
        "src/mypkg/calc.py": 'ORIGIN = "repo-root"\n',
    }
    write_layout(repo, decoy)
    tree = repo / "trees" / "head"
    write_layout(
        tree,
        {
            "conftest.py": SRC_PATH_CONFTEST,
            "src/mypkg/__init__.py": "",
            "src/mypkg/calc.py": 'ORIGIN = "head"\n',
        },
    )
    stored = candidate(line=1)

    result = execute_repro(
        repo,
        stored,
        ReproSpec(provenance_body(tree, ("mypkg.calc",), "head")),
        ExecutorLimits(),
        tree=tree,
        run_label="head-1",
    )

    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED, f"{result.reason}\n{result.stdout}"


def test_execute_repro_honours_the_conftest_fixtures_of_the_tree_under_test(
    tmp_path: Path,
) -> None:
    """Projects legitimately need their own conftest fixtures, so the tree's
    conftest.py must still be loaded -- and it must be the tree's, not the
    repository working tree's."""

    repo = tmp_path / "repo"
    write_layout(
        repo,
        {
            "conftest.py": FIXTURE_CONFTEST.format(items="[9, 9, 9]"),
            "mypkg/__init__.py": "",
            "mypkg/calc.py": TOTAL_CALC,
        },
    )
    tree = repo / "trees" / "head"
    write_layout(
        tree,
        {
            "conftest.py": FIXTURE_CONFTEST.format(items="[1, 2, 3]"),
            "mypkg/__init__.py": "",
            "mypkg/calc.py": TOTAL_CALC,
        },
    )
    stored = candidate(line=1)

    result = execute_repro(
        repo,
        stored,
        ReproSpec(FIXTURE_BODY),
        ExecutorLimits(),
        tree=tree,
        run_label="head-1",
    )

    # a missing fixture would be a collection error and defer instead
    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED, f"{result.reason}\n{result.stdout}"


def test_execute_differential_root_conftest_does_not_leak_head_code_into_base(
    tmp_path: Path,
) -> None:
    """The reproduced defect: a flat package plus a root-level conftest.py made
    pytest prepend the repository root to sys.path, so the BASE run imported the
    head checkout in the working tree. A genuine regression then failed on both
    sides and was written off as unfaithful -- attest never spoke about it."""

    def project(calc: str) -> dict[str, str]:
        return {
            "pyproject.toml": PYPROJECT,
            "conftest.py": ROOT_CONFTEST,
            "mypkg/__init__.py": "",
            "mypkg/calc.py": calc,
        }

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path, project(GUARDED_CALC), project(UNGUARDED_CALC)
    )
    stored = candidate(line=1)

    result = execute_differential(
        repo,
        stored,
        ReproSpec(CALC_CRASH_BODY),
        ExecutorLimits(),
        base_sha=base_sha,
        head_sha=head_sha,
        repeats=2,
    )

    detail = f"{result.evidence_class}: {result.reason}"
    assert result.outcome is ExecutionOutcome.REPRODUCED, detail
    assert result.evidence_class is EvidenceClass.REGRESSION_REPRODUCED
    assert result.reason == "head FAIL 2/2, base PASS 2/2"
    assert result.network_blocked is True
    assert_worktrees_cleaned(repo, stored)


def test_execute_differential_syntax_error_defers_and_cleans_worktrees(tmp_path: Path) -> None:

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
    # V-01 collects before any behavioural repeat: the failing collection run is
    # the retained evidence and no head run is bought
    assert result.collection_run is not None
    assert result.collection_run.outcome is ExecutionOutcome.DEFERRED
    assert result.head_runs == ()
    assert result.base_runs == ()
    assert result.base_sha == base_sha
    assert result.head_sha == head_sha
    assert_worktrees_cleaned(repo, stored)


def test_execute_differential_expired_deadline_defers_before_any_run(tmp_path: Path) -> None:

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
    # one interpreter-version probe, one collect-only run, then 3 + 3 repeats
    assert log.read_text(encoding="utf-8").splitlines() == ["run"] * 8
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_unfaithful_test_failing_on_base_is_deferred(
    tmp_path: Path, verify_with_defaults: VerifyWithDefaults
) -> None:

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

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
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
    verify_with_defaults: VerifyWithDefaults,
) -> None:

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

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
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


# Verbatim pytest output for a KeyError raised inside the code under test.
DEEP_KEY_ERROR_OUTPUT = """\
=================================== FAILURES ===================================
__________________________________ test_repro __________________________________

    def test_repro():
>       assert mod.threshold({}) == 5
               ^^^^^^^^^^^^^^^^^

/tmp/repro/test_repro.py:5:
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

config = {}

    def threshold(config):
>       return config["threshold"]
               ^^^^^^^^^^^^^^^^^^^
E       KeyError: 'threshold'

/tmp/repro/mod.py:5: KeyError
"""

# The same defect asserted directly on the returned mapping: the KeyError is
# raised in the reproduction's own frame, and still says nothing about symbols.
TEST_FRAME_KEY_ERROR_OUTPUT = """\
=================================== FAILURES ===================================
__________________________________ test_repro __________________________________

    def test_repro():
>       assert mod.settings({})["threshold"] == 5
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       KeyError: 'threshold'

/tmp/repro/test_repro.py:5: KeyError
"""

# An AttributeError about a VALUE, not a definition: head returned None where
# the reproduction expected an object. The interpreter owns NoneType's
# namespace, so no diff can have removed `strip` from it.
NONETYPE_ATTRIBUTE_OUTPUT = """\
=================================== FAILURES ===================================
__________________________________ test_repro __________________________________

    def test_repro():
>       assert mod.normalize(" a ").strip() == "a"
               ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'NoneType' object has no attribute 'strip'

/tmp/repro/test_repro.py:5: AttributeError
"""

# An AttributeError about a DEFINITION reached through an instance: the
# renamed-method form of the D-029 refactor.
INSTANCE_ATTRIBUTE_OUTPUT = """\
=================================== FAILURES ===================================
__________________________________ test_repro __________________________________

    def test_repro():
>       assert mod.Calculator()._validate("") is False
               ^^^^^^^^^^^^^^^^^^^^^^^^^^
E       AttributeError: 'Calculator' object has no attribute '_validate'

/tmp/repro/test_repro.py:5: AttributeError
"""

NAME_ERROR_OUTPUT = """\
=================================== FAILURES ===================================
__________________________________ test_repro __________________________________

    def test_repro():
>       assert totally_absent_symbol(2) == 4
               ^^^^^^^^^^^^^^^^^^^^^^^
E       NameError: name 'totally_absent_symbol' is not defined

/tmp/repro/test_repro.py:2: NameError
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
        # a lookup that failed at runtime on data is NOT a missing symbol,
        # wherever the mapping access happened to sit
        (DEEP_KEY_ERROR_OUTPUT, "other"),
        (TEST_FRAME_KEY_ERROR_OUTPUT, "other"),
        (NONETYPE_ATTRIBUTE_OUTPUT, "other"),
        # ... but a name that could not be resolved still is
        (INSTANCE_ATTRIBUTE_OUTPUT, "symbol_absent"),
        (NAME_ERROR_OUTPUT, "symbol_absent"),
    ],
)
def test_classify_failure_signature_reads_the_failure_lines(stdout: str, signature: str) -> None:

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


def test_verify_candidate_new_function_on_head_is_a_new_code_candidate(
    tmp_path: Path, verify_with_defaults: VerifyWithDefaults
) -> None:
    """The reviewed diff ADDS parse(): the reproduction fails by assertion on
    head while the symbol is absent on base. Signal only -- no V is purchased."""

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

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
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


def test_verify_candidate_new_module_on_head_is_a_new_code_candidate(
    tmp_path: Path, verify_with_defaults: VerifyWithDefaults
) -> None:
    """Same evidence class when the added symbol lives in a file absent from
    base entirely: the base run is a ModuleNotFoundError collection error."""

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

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
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
    tmp_path: Path,
    verify_with_defaults: VerifyWithDefaults,
    head_module: str,
    test_body: str,
) -> None:
    """ZeroDivisionError, TypeError and IndexError are all *the code
    misbehaved*, not *the symbol was never there*; each pairs with a
    symbol-absent base into the same unpriced class."""

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path, {"mod.py": TOTAL_ONLY_MODULE}, {"mod.py": head_module}
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(text=json.dumps({"test_body": test_body}), input_tokens=2, output_tokens=3)
    )

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
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
    verify_with_defaults: VerifyWithDefaults,
) -> None:
    """`add` exists on head and base alike and the assertion is false on both:
    widening the head-side condition must not let this buy the new-code class."""

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

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
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
    verify_with_defaults: VerifyWithDefaults,
) -> None:
    """Fabrication guard: a test naming a symbol that exists on neither tree
    fails symbol-absent on HEAD, which the new-code rule excludes outright."""

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": FABRICATED_BODY}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
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


@pytest.mark.parametrize(
    ("base_files", "head_files", "test_body", "expected"),
    [
        pytest.param(
            {"mypkg/__init__.py": "", "mypkg/calc.py": RENAMED_BASE_MODULE},
            {"mypkg/__init__.py": "", "mypkg/calc.py": RENAMED_HEAD_MODULE},
            STALE_RENAME_BODY,
            DifferentialExpectation(
                head_outcomes=("reproduced",) * 3,
                head_signature="symbol_absent",
                base_outcomes=("not_reproduced",) * 3,
                base_signature=None,
                evidence_class="unfaithful",
                outcome="deferred",
                reason=(
                    "unfaithful generated test: it references a symbol absent from head, "
                    "so its head failure is a stale reference rather than a defect"
                ),
                wealth=8.0,
                channels=("S",),
                required_reason_fragments=("absent from head", "unfaithful"),
            ),
            id="head_symbol_absent__base_pass__unfaithful",
        ),
        pytest.param(
            {"mod.py": GOOD_MODULE},
            {"mod.py": BUGGY_MODULE},
            DIFFERENTIAL_BODY,
            DifferentialExpectation(
                head_outcomes=("reproduced",) * 3,
                head_signature="assertion",
                base_outcomes=("not_reproduced",) * 3,
                base_signature=None,
                evidence_class="regression_reproduced",
                outcome="reproduced",
                reason="head FAIL 3/3, base PASS 3/3",
                wealth=160.0,
                channels=("S", "V"),
                purchase_detail="reproduced",
            ),
            id="head_assertion__base_pass__certifies",
        ),
        pytest.param(
            {"mod.py": GUARDED_MEAN_MODULE},
            {"mod.py": UNGUARDED_MEAN_MODULE},
            MEAN_CRASH_BODY,
            DifferentialExpectation(
                head_outcomes=("reproduced",) * 3,
                head_signature="other",
                base_outcomes=("not_reproduced",) * 3,
                base_signature=None,
                evidence_class="regression_reproduced",
                outcome="reproduced",
                reason="head FAIL 3/3, base PASS 3/3",
                wealth=160.0,
                channels=("S", "V"),
                purchase_detail="reproduced",
            ),
            id="head_crash__base_pass__certifies",
        ),
        # Live-acceptance shape: the added average() crashes on head while its
        # symbol is absent from base. This is signal, but remains unpriced.
        pytest.param(
            {"mod.py": TOTAL_ONLY_MODULE},
            {"mod.py": AVERAGE_MODULE},
            AVERAGE_CRASH_BODY,
            DifferentialExpectation(
                head_outcomes=("reproduced",) * 3,
                head_signature="other",
                base_outcomes=("reproduced",),
                base_signature="symbol_absent",
                evidence_class="new_code_candidate",
                outcome="deferred",
                reason=(
                    "new-code candidate: reproduction fails on head and the symbol is absent "
                    "on base; not priced"
                ),
                wealth=8.0,
                channels=("S",),
                required_reason_fragments=("new-code",),
                forbidden_reason_fragment="unfaithful",
            ),
            id="head_crash__base_symbol_absent__new_code",
        ),
        pytest.param(
            {"mod.py": GOOD_MODULE},
            {"mod.py": GOOD_MODULE + "# head touches nothing the test names\n"},
            FABRICATED_BODY,
            DifferentialExpectation(
                head_outcomes=("reproduced",) * 3,
                head_signature="symbol_absent",
                base_outcomes=("reproduced",),
                base_signature="symbol_absent",
                evidence_class="unfaithful",
                outcome="deferred",
                reason="unfaithful generated test: fails on base as well",
                wealth=8.0,
                channels=("S",),
            ),
            id="head_symbol_absent__base_symbol_absent__unfaithful",
        ),
    ],
)
def test_differential_certification_requires_the_head_code_to_misbehave(
    tmp_path: Path,
    verify_with_defaults: VerifyWithDefaults,
    base_files: dict[str, str],
    head_files: dict[str, str],
    test_body: str,
    expected: DifferentialExpectation,
) -> None:
    """The full head-signature x base-outcome table. One invariant runs through
    every row: the head runs must show the code MISBEHAVING before anything is
    bought. A head that merely reports the symbol absent never certifies, no
    matter how cleanly base passes."""

    repo, base_sha, head_sha = two_commit_repo(tmp_path, base_files, head_files)
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(text=json.dumps({"test_body": test_body}), input_tokens=2, output_tokens=3)
    )

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert tuple(run.outcome.value for run in verification.execution.head_runs) == (
        expected.head_outcomes
    )
    if expected.head_signature is not None:
        assert {
            classify_failure_signature(run).value for run in verification.execution.head_runs
        } == {expected.head_signature}
    assert tuple(run.outcome.value for run in verification.execution.base_runs) == (
        expected.base_outcomes
    )
    if expected.base_signature is not None:
        assert {
            classify_failure_signature(run).value for run in verification.execution.base_runs
        } == {expected.base_signature}
    assert verification.execution.evidence_class is EvidenceClass(expected.evidence_class)
    assert verification.execution.outcome is ExecutionOutcome(expected.outcome)
    assert verification.execution.reason == expected.reason
    assert all(
        fragment in verification.execution.reason for fragment in expected.required_reason_fragments
    )
    if expected.forbidden_reason_fragment is not None:
        assert expected.forbidden_reason_fragment not in verification.execution.reason
    assert verification.gate_result.wealth == expected.wealth
    assert (
        tuple(purchase.channel for purchase in verification.gate_result.purchases)
        == expected.channels
    )
    if expected.purchase_detail is not None:
        assert verification.gate_result.purchases[-1].detail == expected.purchase_detail
    if expected.outcome == "deferred":
        # buys nothing at all: the caller's own gate result comes straight back,
        # so neither V nor V_FAILED can have been applied
        assert verification.gate_result is gate
    else:
        assert verification.gate_result is not gate
    row = Ledger(repo).entries()[-1]
    assert row["kind"] == "verification"
    assert row["outcome"] == expected.outcome
    assert row["evidence_class"] == expected.evidence_class
    assert row["reason"] == expected.reason
    if expected.forbidden_reason_fragment is not None:
        assert expected.forbidden_reason_fragment not in row["reason"]
    assert_worktrees_cleaned(repo, stored)


@pytest.mark.parametrize(
    ("base_module", "head_module", "test_body"),
    [
        (DEFAULTED_LOOKUP_MODULE, UNDEFAULTED_LOOKUP_MODULE, DEEP_KEY_ERROR_BODY),
        (MERGED_SETTINGS_MODULE, DROPPED_SETTINGS_MODULE, TEST_FRAME_KEY_ERROR_BODY),
    ],
    ids=["raised_inside_the_code_under_test", "raised_at_the_reproduction_assertion"],
)
def test_verify_candidate_key_error_regression_certifies(
    tmp_path: Path,
    verify_with_defaults: VerifyWithDefaults,
    base_module: str,
    head_module: str,
    test_body: str,
) -> None:
    """The reproduced defect. A genuine regression whose reproduction fails with
    KeyError: the symbol is present on BOTH trees, base honours the default and
    head genuinely misbehaves. Reading the exception NAME called this a missing
    symbol, and since certification now requires the head code to misbehave,
    that silently blocked a true finding from buying any evidence at all."""

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path, {"mod.py": base_module}, {"mod.py": head_module}
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(text=json.dumps({"test_body": test_body}), input_tokens=2, output_tokens=3)
    )

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
        base_sha=base_sha,
        head_sha=head_sha,
    )

    # head fails 3/3 with a KeyError, and that is the code misbehaving
    assert [run.outcome.value for run in verification.execution.head_runs] == ["reproduced"] * 3
    assert all(
        classify_failure_signature(run) is not FailureSignature.SYMBOL_ABSENT
        for run in verification.execution.head_runs
    )
    assert "KeyError" in verification.execution.head_runs[0].stdout
    assert [run.outcome.value for run in verification.execution.base_runs] == ["not_reproduced"] * 3

    assert verification.execution.evidence_class is EvidenceClass.REGRESSION_REPRODUCED
    assert verification.execution.outcome is ExecutionOutcome.REPRODUCED
    assert verification.execution.reason == "head FAIL 3/3, base PASS 3/3"
    # V is purchased: 8.0 * 20
    assert verification.gate_result is not gate
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S", "V"]
    assert verification.gate_result.wealth == 160.0
    row = Ledger(repo).entries()[-1]
    assert row["outcome"] == "reproduced"
    assert row["evidence_class"] == "regression_reproduced"
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_symbol_that_exists_nowhere_still_buys_nothing(
    tmp_path: Path,
    verify_with_defaults: VerifyWithDefaults,
) -> None:
    """Fabrication guard, stated against the loosened classifier: a reproduction
    naming a symbol present on NEITHER tree must still be classified
    symbol-absent on head, and must still buy nothing. Discriminating KeyError
    and data-shaped AttributeErrors must not touch this path."""

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path,
        {"mod.py": DEFAULTED_LOOKUP_MODULE},
        {"mod.py": UNDEFAULTED_LOOKUP_MODULE},
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": FABRICATED_BODY}), input_tokens=2, output_tokens=3
        )
    )

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
        base_sha=base_sha,
        head_sha=head_sha,
    )

    # the load-bearing mechanism: HEAD itself reports the symbol as absent,
    # even though this very diff is a real KeyError regression
    assert all(
        classify_failure_signature(run) is FailureSignature.SYMBOL_ABSENT
        for run in verification.execution.head_runs
    )
    assert verification.execution.evidence_class is not EvidenceClass.REGRESSION_REPRODUCED
    assert verification.execution.evidence_class is not EvidenceClass.NEW_CODE_CANDIDATE
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    # buys nothing: the caller's gate result comes back by identity
    assert verification.gate_result is gate
    assert verification.gate_result.wealth == stored.wealth
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S"]
    row = Ledger(repo).entries()[-1]
    assert row["outcome"] == "deferred"
    assert row["evidence_class"] != "regression_reproduced"
    assert_worktrees_cleaned(repo, stored)


def test_verify_candidate_renamed_method_never_buys_evidence(
    tmp_path: Path, verify_with_defaults: VerifyWithDefaults
) -> None:
    """Rename guard, extended to the instance case. D-029(a) reached head
    through a module-level helper; the same refactor on a METHOD produces
    `'Calculator' object has no attribute '_validate'`, which is still a name
    the reviewed revision does not have. Base passes 3/3, so anything short of
    symbol-absent on head certifies a behaviour-preserving refactor."""

    repo, base_sha, head_sha = two_commit_repo(
        tmp_path,
        {"mod.py": RENAMED_METHOD_BASE_MODULE},
        {"mod.py": RENAMED_METHOD_HEAD_MODULE},
    )
    stored = candidate(line=1)
    gate = original_gate(stored)
    provider = RecordingProvider(
        ProviderResult(
            text=json.dumps({"test_body": STALE_METHOD_RENAME_BODY}),
            input_tokens=2,
            output_tokens=3,
        )
    )

    verification = verify_with_defaults(
        repo,
        stored,
        gate,
        provider,
        base_sha=base_sha,
        head_sha=head_sha,
    )

    assert [run.outcome.value for run in verification.execution.head_runs] == ["reproduced"] * 3
    assert all(
        classify_failure_signature(run) is FailureSignature.SYMBOL_ABSENT
        for run in verification.execution.head_runs
    )
    assert [run.outcome.value for run in verification.execution.base_runs] == ["not_reproduced"] * 3
    assert verification.execution.evidence_class is EvidenceClass.UNFAITHFUL
    assert verification.execution.outcome is ExecutionOutcome.DEFERRED
    assert "absent from head" in verification.execution.reason
    assert verification.gate_result is gate
    assert verification.gate_result.wealth == stored.wealth
    assert [purchase.channel for purchase in verification.gate_result.purchases] == ["S"]
    assert Ledger(repo).entries()[-1]["evidence_class"] == "unfaithful"
    assert_worktrees_cleaned(repo, stored)


def test_generation_prompt_shows_both_sides_of_the_anchored_definition(tmp_path: Path) -> None:
    """The generator must see the merge-base version of the code it is asked to
    distinguish from, not only a window of the head file: a faithful test asserts
    the base behaviour and fails on head."""
    from attest.review.executor import _generation_prompt

    repo, base_sha, head_sha = differential_repo(tmp_path)
    stored = candidate(file="mod.py", line=2)

    prompt = _generation_prompt(repo, stored, base_sha)

    assert "return a - b" in prompt  # head definition, the defect
    assert "return a + b" in prompt  # merge-base definition, the behaviour to assert
    assert "merge-base" in prompt.lower()
