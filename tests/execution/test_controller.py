"""X-01: the controller accepts only results that answer the nonce it issued."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from attest.execution.controller import Controller, JobState, read_bounded
from attest.execution.local_adapter import LocalDevelopmentAdapter
from attest.execution.protocol import ProtocolError, request_digest, sha256_hex
from attest.execution.types import (
    EXECUTION_PROTOCOL_VERSION,
    LOCAL_DEVELOPMENT_PROFILE,
    MAX_ARTIFACT_BYTES,
    Artifact,
    ExecutionRequest,
    ExecutionResultEnvelope,
    ResourceLimits,
)

LIMITS = ResourceLimits(wall_timeout_s=20.0, cpu_timeout_s=10, memory_mb=512, output_bytes=4_096)


def issue(controller: Controller, run_id: str = "head-1", **overrides: object) -> ExecutionRequest:
    fields: dict[str, object] = {
        "task_id": "task-1",
        "run_id": run_id,
        "candidate_id": "cand1",
        "revision_sha": "",
        "profile": LOCAL_DEVELOPMENT_PROFILE,
        "interpreter": sys.executable,
        "argv_template": [sys.executable, "-c", "open('{outputs}/out.txt', 'w').write('ok')"],
        "environment": {"ATTEST_OUTPUTS": "{outputs}"},
        "inputs": {"note.txt": b"input"},
        "limits": LIMITS,
        "expected_artifacts": ["out.txt", "stdout.txt", "stderr.txt"],
    }
    fields.update(overrides)
    return controller.issue(**fields)  # type: ignore[arg-type]


class Forging:
    """An executor that runs nothing and answers with whatever nonce it likes."""

    profile = LOCAL_DEVELOPMENT_PROFILE

    def __init__(self, nonce: str, *, artifact_bytes: bytes = b"ok", declared: bytes = b"ok"):
        self.nonce = nonce
        self.artifact_bytes = artifact_bytes
        self.declared = declared

    def backend_digest(self) -> str:
        return "f" * 64

    def execute(
        self, request: ExecutionRequest, *, tree: Path, inputs: Path, outputs: Path
    ) -> ExecutionResultEnvelope:
        (outputs / "out.txt").write_bytes(self.artifact_bytes)
        return ExecutionResultEnvelope(
            protocol_version=EXECUTION_PROTOCOL_VERSION,
            nonce=self.nonce,
            request_digest=request_digest(request),
            run_id=request.run_id,
            profile=self.profile,
            backend_digest=self.backend_digest(),
            exit_code=0,
            timed_out=False,
            elapsed_s=0.0,
            artifacts=(Artifact("out.txt", sha256_hex(self.declared), len(self.declared)),),
            error="",
        )


def test_result_answering_another_nonce_is_rejected(tmp_path: Path) -> None:
    """The X-01 RED: an executor result whose artifact digest is bound to a
    different request nonce (a replayed or forged envelope) buys nothing."""
    controller = Controller(tmp_path / "runs", nonce_source=iter(["1" * 32, "2" * 32]).__next__)
    first = issue(controller, "head-1")
    second = issue(controller, "head-2")
    outcome = controller.dispatch(
        first, Forging(second.nonce), tree=tmp_path, inputs={"note.txt": b"input"}
    )
    assert not outcome.accepted
    assert any("nonce mismatch" in reason for reason in outcome.reasons), outcome.reasons
    assert outcome.artifacts == {}
    assert controller.state(first.nonce) is JobState.REJECTED
    assert not (tmp_path / "runs" / "head-1" / "result.json").exists()


def test_artifact_bytes_that_disagree_with_their_digest_are_rejected(tmp_path: Path) -> None:
    controller = Controller(tmp_path / "runs")
    request = issue(controller)
    outcome = controller.dispatch(
        request,
        Forging(request.nonce, artifact_bytes=b"tampered", declared=b"ok"),
        tree=tmp_path,
        inputs={"note.txt": b"input"},
    )
    assert not outcome.accepted
    assert any("digest mismatch" in reason for reason in outcome.reasons)


def test_local_adapter_result_is_accepted_and_persisted_atomically(tmp_path: Path) -> None:
    controller = Controller(tmp_path / "runs")
    request = issue(controller)
    outcome = controller.dispatch(
        request, LocalDevelopmentAdapter(), tree=tmp_path, inputs={"note.txt": b"input"}
    )
    assert outcome.accepted, outcome.reasons
    assert outcome.artifacts["out.txt"] == b"ok"
    run_dir = tmp_path / "runs" / "head-1"
    assert (run_dir / "request.json").is_file()
    assert (run_dir / "result.json").is_file()
    assert (run_dir / "artifacts" / "out.txt").read_bytes() == b"ok"
    assert not list(run_dir.glob("*.tmp"))
    assert controller.state(request.nonce) is JobState.COMPLETED


def test_duplicate_stale_and_unissued_results_are_rejected(tmp_path: Path) -> None:
    controller = Controller(tmp_path / "runs")
    request = issue(controller)
    adapter = LocalDevelopmentAdapter()
    inputs = {"note.txt": b"input"}
    assert controller.dispatch(request, adapter, tree=tmp_path, inputs=inputs).accepted
    duplicate = controller.dispatch(request, adapter, tree=tmp_path, inputs=inputs)
    assert not duplicate.accepted
    assert "stale request" in duplicate.reason
    foreign = Controller(tmp_path / "other")
    never_issued = foreign.dispatch(request, adapter, tree=tmp_path, inputs=inputs)
    assert not never_issued.accepted
    assert "result before dispatch" in never_issued.reason


def test_controller_restart_makes_dispatched_jobs_ambiguous(tmp_path: Path) -> None:
    controller = Controller(tmp_path / "runs")
    request = issue(controller)

    class Crashing(Forging):
        def execute(self, request: ExecutionRequest, **kwargs: object) -> ExecutionResultEnvelope:
            raise RuntimeError("executor died")

    outcome = controller.dispatch(
        request, Crashing(request.nonce), tree=tmp_path, inputs={"note.txt": b"input"}
    )
    assert not outcome.accepted
    assert "executor crash" in outcome.reason
    # simulate a crash between dispatch and result: the persisted state says dispatched
    (tmp_path / "runs" / "head-1" / "state.json").write_text(
        f'{{"nonce":"{request.nonce}","state":"dispatched"}}', encoding="utf-8"
    )
    resumed = Controller.resume(tmp_path / "runs")
    assert resumed.state(request.nonce) is JobState.AMBIGUOUS
    late = resumed.dispatch(
        request, LocalDevelopmentAdapter(), tree=tmp_path, inputs={"note.txt": b"input"}
    )
    assert not late.accepted
    assert "ambiguous" in late.reason


def test_issue_refuses_credentials_and_unsafe_names(tmp_path: Path) -> None:
    controller = Controller(tmp_path / "runs")
    with pytest.raises(ProtocolError, match="credential"):
        issue(controller, environment={"GITHUB_TOKEN": "x"})
    with pytest.raises(ProtocolError, match="unsafe name"):
        issue(controller, run_id="../head-1")
    with pytest.raises(ProtocolError, match="unsafe name"):
        issue(controller, inputs={"../sitecustomize.py": b"x"})


def test_mismatched_input_bytes_never_reach_the_executor(tmp_path: Path) -> None:
    controller = Controller(tmp_path / "runs")
    request = issue(controller)
    outcome = controller.dispatch(
        request, LocalDevelopmentAdapter(), tree=tmp_path, inputs={"note.txt": b"changed"}
    )
    assert not outcome.accepted
    assert "does not match its declaration" in outcome.reason
    assert not (tmp_path / "runs" / "head-1" / "outputs" / "out.txt").exists()


@pytest.mark.skipif(os.name != "posix", reason="symlinks")
def test_symlinked_and_oversized_artifacts_are_not_read(tmp_path: Path) -> None:
    secret = tmp_path / "secret"
    secret.write_text("hidden", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(secret)
    assert read_bounded(link, MAX_ARTIFACT_BYTES) is None
    big = tmp_path / "big"
    big.write_bytes(b"x" * 11)
    assert read_bounded(big, 10) is None
    assert read_bounded(secret, 10) == b"hidden"


def test_local_adapter_passes_only_the_explicit_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "must-not-leak")
    monkeypatch.setenv("ATTEST_UNRELATED", "must-not-leak-either")
    controller = Controller(tmp_path / "runs")
    request = issue(
        controller,
        argv_template=[
            sys.executable,
            "-c",
            "import os, json; open('{outputs}/out.txt', 'w').write(json.dumps(sorted(os.environ)))",
        ],
    )
    outcome = controller.dispatch(
        request, LocalDevelopmentAdapter(), tree=tmp_path, inputs={"note.txt": b"input"}
    )
    assert outcome.accepted, outcome.reasons
    names = outcome.artifacts["out.txt"].decode("utf-8")
    assert "GITHUB_TOKEN" not in names
    assert "ATTEST_UNRELATED" not in names
    assert "ATTEST_OUTPUTS" in names
