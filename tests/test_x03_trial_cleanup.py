"""Synthetic trial failures retain evidence and clean up their named container."""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/corpus"))
import x03_supervisor_trial as trial  # noqa: E402


@pytest.mark.parametrize("failure", ["timeout", "launch", "none", "cleanup"])
def test_named_container_cleanup_and_checkpoint(tmp_path: Path, monkeypatch, failure: str) -> None:
    problem = subprocess.TimeoutExpired("docker", 30, output=b"partial")
    run = Mock(side_effect=[
        problem if failure == "timeout" else OSError("launch") if failure == "launch"
        else subprocess.CompletedProcess([], 0, b"ok", b""),
        subprocess.CompletedProcess([], 1 if failure == "cleanup" else 0, b"", b""),
    ])
    monkeypatch.setattr(trial.subprocess, "run", run)
    if failure == "none":
        assert trial.run_container(["image"], {}, tmp_path).stdout == b"ok"
    else:
        with pytest.raises((subprocess.TimeoutExpired, OSError, RuntimeError)):
            trial.run_container(["image"], {}, tmp_path)
    launch, cleanup = [call.args[0] for call in run.call_args_list]
    assert launch[:3] == ["docker", "run", "--name"]
    assert cleanup == ["docker", "rm", "-f", launch[3]]
    record = json.loads((tmp_path / "container.json").read_text())
    assert record["cleanup_exit_code"] == (1 if failure == "cleanup" else 0)
    assert record["status"] == {
        "timeout": "TimeoutExpired", "launch": "OSError", "none": "exited", "cleanup": "exited",
    }[failure]
    assert (tmp_path / "stdout.txt").read_bytes() == (
        b"partial" if failure == "timeout" else b"" if failure == "launch" else b"ok"
    )


def test_cleanup_timeout_is_recorded(tmp_path: Path, monkeypatch) -> None:
    run = Mock(side_effect=[
        subprocess.CompletedProcess([], 0, b"ok", b""),
        subprocess.TimeoutExpired("docker rm", 30),
    ])
    monkeypatch.setattr(trial.subprocess, "run", run)
    with pytest.raises(subprocess.TimeoutExpired):
        trial.run_container(["image"], {}, tmp_path)
    record = json.loads((tmp_path / "container.json").read_text())
    assert record["status"] == "exited"
    assert record["cleanup_error"] == "TimeoutExpired"
    assert "cleanup_exit_code" not in record


def test_output_write_failure_still_removes_container(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "stdout.txt").mkdir()
    run = Mock(return_value=subprocess.CompletedProcess([], 0, b"ok", b""))
    monkeypatch.setattr(trial.subprocess, "run", run)
    with pytest.raises(IsADirectoryError):
        trial.run_container(["image"], {}, tmp_path)
    assert run.call_args_list[-1].args[0][:3] == ["docker", "rm", "-f"]
    record = json.loads((tmp_path / "container.json").read_text())
    assert record["cleanup_exit_code"] == 0
