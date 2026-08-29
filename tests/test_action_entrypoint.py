"""Behavior tests for the composite action's safe shell entrypoint."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "scripts" / "action-entrypoint.sh"


def _event(path: Path, *, fork: bool) -> None:
    path.write_text(
        json.dumps(
            {
                "pull_request": {
                    "base": {"sha": "base-sha"},
                    "head": {"repo": {"fork": fork}},
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


def test_fork_event_skips_before_the_attest_executable_runs(tmp_path: Path) -> None:
    """Catches a privileged fork path that reaches executable head-code review."""
    event_path = tmp_path / "fork-event.json"
    _event(event_path, fork=True)
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(tmp_path, event_path, venv, args_path)

    assert result.returncode == 0
    assert not args_path.exists()
    assert "fork" in result.stdout.lower()


def test_trusted_event_forwards_only_ci_arguments_to_attest(tmp_path: Path) -> None:
    """Catches a launcher that omits or changes the CI contract arguments."""
    event_path = tmp_path / "trusted-event.json"
    _event(event_path, fork=False)
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
    _event(event_path, fork=False)
    venv, args_path = _fake_attest(tmp_path)

    result = _run_entrypoint(tmp_path, event_path, venv, args_path)

    output = result.stdout + result.stderr
    assert "github-secret-value" not in output
    assert "model-secret-value" not in output
