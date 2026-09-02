"""Behavior tests for the composite action's safe shell entrypoint."""

from __future__ import annotations

import json
import os
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "scripts" / "action-entrypoint.sh"
GATE = ROOT / "scripts" / "action-gate.sh"
ACTION = ROOT / "action.yml"


def _event(
    path: Path,
    *,
    repository: str = "maintainer/project",
    head_repository: str = "maintainer/project",
    repository_is_fork: bool = False,
    head_repository_is_fork: bool = False,
) -> None:
    path.write_text(
        json.dumps(
            {
                "repository": {"full_name": repository, "fork": repository_is_fork},
                "number": 17,
                "pull_request": {
                    "base": {"sha": "base-sha"},
                    "head": {
                        "sha": "head-sha",
                        "repo": {
                            "full_name": head_repository,
                            "fork": head_repository_is_fork,
                        },
                    },
                }
            }
        ),
        encoding="utf-8",
    )


def _fake_attest(tmp_path: Path) -> tuple[Path, Path]:
    venv = tmp_path / "venv"
    binary = venv / "bin" / "attest"
    binary.parent.mkdir(parents=True)
    args_path = tmp_path / "attest-args.json"
    binary.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$@\" > \"$ATTEST_ARGS_PATH\"\n",
        encoding="utf-8",
    )
    binary.chmod(0o755)
    return venv, args_path


def _run_entrypoint(
    tmp_path: Path, event_path: Path, venv: Path, args_path: Path, **overrides: str
) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir(exist_ok=True)
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"${ATTEST_FAKE_GIT_HEAD:-head-sha}\"\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    environment = os.environ | {
        "ATTEST_VENV": str(venv),
        "ATTEST_ARGS_PATH": str(args_path),
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_WORKSPACE": str(tmp_path / "workspace"),
        "INPUT_GITHUB_TOKEN": "github-secret-value",
        "INPUT_MODEL_API_KEY": "model-secret-value",
        "INPUT_BUDGET_USD": "0.25",
        "INPUT_SAMPLES": "5",
        "INPUT_VERIFICATION_TIMEOUT": "600",
        "PATH": str(fake_bin) + os.pathsep + os.environ["PATH"],
    }
    environment.update(overrides)
    return subprocess.run(
        ["sh", str(ENTRYPOINT)],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def _run_gate(tmp_path: Path, event_path: Path) -> tuple[subprocess.CompletedProcess[str], Path]:
    output_path = tmp_path / "github-output"
    environment = {
        "GITHUB_EVENT_PATH": str(event_path),
        "GITHUB_OUTPUT": str(output_path),
        "PATH": os.environ["PATH"],
    }
    credential_names = {
        "GITHUB_TOKEN",
        "ANTHROPIC_API_KEY",
        "INPUT_GITHUB_TOKEN",
        "INPUT_MODEL_API_KEY",
    }
    assert credential_names.isdisjoint(environment)
    result = subprocess.run(
        ["sh", str(GATE)],
        cwd=tmp_path,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, output_path


def _action_steps() -> list[dict[str, object]]:
    result = subprocess.run(
        [
            "ruby",
            "-e",
            'require "json"; require "yaml"; puts JSON.generate(YAML.load_file(ARGV[0]))',
            str(ACTION),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    action = json.loads(result.stdout)
    return action["runs"]["steps"]


def test_cross_repository_event_skips_before_the_attest_executable_runs(tmp_path: Path) -> None:
    """Catches a privileged cross-repository path that reaches head-code review."""
    event_path = tmp_path / "fork-event.json"
    _event(event_path, head_repository="contributor/project")
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(tmp_path, event_path, venv, args_path)

    assert result.returncode == 0
    assert not args_path.exists()
    assert "fork" in result.stdout.lower()


def test_same_repository_pr_is_trusted_when_repository_is_a_fork(tmp_path: Path) -> None:
    """Catches treating the destination repository's fork status as an untrusted PR."""
    event_path = tmp_path / "same-repository-fork-event.json"
    _event(event_path, repository_is_fork=True, head_repository_is_fork=True)
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(tmp_path, event_path, venv, args_path)

    assert result.returncode == 0, result.stderr
    assert args_path.exists()


def test_upstream_parent_pr_into_a_fork_is_skipped(tmp_path: Path) -> None:
    """Catches trusting an upstream PR merely because its head repository is not a fork."""
    event_path = tmp_path / "upstream-parent-event.json"
    _event(
        event_path,
        repository="maintainer/project-fork",
        head_repository="upstream/project",
        repository_is_fork=True,
    )
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(tmp_path, event_path, venv, args_path)

    assert result.returncode == 0
    assert not args_path.exists()
    assert "fork" in result.stdout.lower()


def test_trusted_event_forwards_only_ci_arguments_to_attest(tmp_path: Path) -> None:
    """Catches a launcher that omits or changes the CI contract arguments."""
    event_path = tmp_path / "trusted-event.json"
    _event(event_path)
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(tmp_path, event_path, venv, args_path)

    assert result.returncode == 0, result.stderr
    assert args_path.read_text(encoding="utf-8").splitlines() == [
        "--repo",
        str(tmp_path / "workspace"),
        "ci",
        "--event-path",
        str(event_path),
        "--budget",
        "0.25",
        "--k",
        "5",
        "--verification-timeout",
        "600",
    ]


def test_missing_event_file_fails_without_running_attest(tmp_path: Path) -> None:
    """Catches a launcher that invokes review with no GitHub event context."""
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(tmp_path, tmp_path / "missing-event.json", venv, args_path)

    assert result.returncode != 0
    assert not args_path.exists()
    assert "GITHUB_EVENT_PATH" in result.stderr


def test_entrypoint_never_emits_supplied_secrets(tmp_path: Path) -> None:
    """Catches accidental secret logging from the shell launch boundary."""
    event_path = tmp_path / "trusted-event.json"
    _event(event_path)
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(tmp_path, event_path, venv, args_path)

    output = result.stdout + result.stderr
    assert "github-secret-value" not in output
    assert "model-secret-value" not in output


def test_entrypoint_fails_closed_when_workspace_head_does_not_match_event(tmp_path: Path) -> None:
    event_path = tmp_path / "trusted-event.json"
    _event(event_path)
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(
        tmp_path,
        event_path,
        venv,
        args_path,
        ATTEST_FAKE_GIT_HEAD="different-head",
    )

    assert result.returncode != 0
    assert not args_path.exists()
    assert "HEAD" in result.stderr


def test_example_workflow_checks_out_exact_pull_request_head() -> None:
    example = (ROOT / "examples" / "pull-request.yml").read_text(encoding="utf-8")
    expected = "ref: ${{ github.event.pull_request.head.sha }}"
    assert expected in example


def test_example_workflow_pins_the_action_to_an_immutable_ref() -> None:
    """L-01 pilot wiring: the example an operator copies pinned the action to
    `@main`, so a repository following the quickstart would have installed a
    moving branch while `install-ref.md` promised an immutable ref, and no
    receipt could name the code that produced it."""
    example = (ROOT / "examples" / "pull-request.yml").read_text(encoding="utf-8")
    used = re.findall(r"uses:\s*IcantFind-a-username/Attest@(\S+)", example)
    assert used, "the example workflow must use the action"
    for ref in used:
        assert ref not in {"main", "master", "HEAD"}, f"mutable action ref in the example: {ref}"
        assert re.fullmatch(r"v\d+\.\d+\.\d+[-.\w]*|[0-9a-f]{40}", ref), ref


def test_credential_free_gate_marks_cross_repository_event_untrusted(tmp_path: Path) -> None:
    """Catches a gate that either needs credentials or trusts a cross-repository event."""
    event_path = tmp_path / "fork-event.json"
    _event(event_path, head_repository="contributor/project")

    result, output_path = _run_gate(tmp_path, event_path)

    assert result.returncode == 0, result.stderr
    assert output_path.read_text(encoding="utf-8") == "trusted=false\n"
    assert "fork" in result.stdout.lower()
    assert "::notice" in result.stdout


def test_action_gate_has_no_credentials_and_only_trusted_execution_receives_them() -> None:
    """Catches wiring credentials into the gate or an unconditional action step."""
    steps = _action_steps()
    gate = next(step for step in steps if step.get("id") == "trust")
    trusted_steps = [step for step in steps if step.get("id") != "trust"]

    assert gate.get("env") is None
    assert gate["run"] == 'sh "${{ github.action_path }}/scripts/action-gate.sh"'
    trusted_condition = "${{ steps.trust.outputs.trusted == 'true' }}"
    assert all(step["if"] == trusted_condition for step in trusted_steps)
    credential_steps = [
        step
        for step in trusted_steps
        if {"INPUT_GITHUB_TOKEN", "INPUT_MODEL_API_KEY"} <= set(step.get("env", {}))
    ]
    assert len(credential_steps) == 1
    assert set(credential_steps[0]["env"]) & {"INPUT_GITHUB_TOKEN", "INPUT_MODEL_API_KEY"} == {
        "INPUT_GITHUB_TOKEN",
        "INPUT_MODEL_API_KEY",
    }


def test_action_install_includes_the_pytest_runtime_used_by_executor() -> None:
    """Catches an action venv that cannot execute planted pytest reproductions."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = project["project"]["dependencies"]
    assert any(dependency.startswith("pytest") for dependency in runtime_dependencies)

    install = next(
        step
        for step in _action_steps()
        if step.get("name") == "Install attest from this action"
    )
    assert '"${{ github.action_path }}"' in install["run"]


def test_action_uses_primary_python_and_the_audited_lock() -> None:
    steps = _action_steps()
    setup = next(step for step in steps if step.get("name") == "Set up Python")
    assert setup["uses"] == "actions/setup-python@v6"
    assert setup["with"] == {"python-version": "3.12.8"}

    install = next(
        step for step in steps if step.get("name") == "Install attest from this action"
    )
    command = install["run"]
    assert 'requirements-toolchain.lock' in command
    assert '--no-deps' in command
    assert '--no-build-isolation' in command
