"""X-02 (G-SEC-001..003 RED): head code inside the production Linux backend.

Every case here runs in a real container (skipped, never faked, when docker or
the image is missing on this host): a reproduction that reads an environment
secret, opens a socket or writes outside its work directory fails and the run
is marked, never certified; a genuine regression still fails 3/3 on head and
passes 3/3 on base; the image digest is bound into every run record.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from attest.execution.container_adapter import (  # noqa: E402
    CONTAINER_PROFILE,
    ContainerAdapter,
    ContainerImage,
)
from attest.execution.container_images import ensure_image  # noqa: E402
from attest.review.executor import (  # noqa: E402
    EvidenceClass,
    ExecutionOutcome,
    ExecutorLimits,
    ReproSpec,
    execute_differential,
)
from test_executor import (  # noqa: E402
    DIFFERENTIAL_BODY,
    candidate,
    differential_repo,
)


def _docker_ready() -> bool:
    binary = shutil.which("docker")
    if binary is None:
        return False
    probe = subprocess.run([binary, "info"], capture_output=True, timeout=30)
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(not _docker_ready(), reason="docker daemon")


@pytest.fixture
def adapter(tmp_path: Path) -> ContainerAdapter:
    """The image for a manifest-less tree: python:3.9-slim plus pytest, built
    once and reused by tag (the build needs network; the runs have none)."""
    scratch = tmp_path / "image-source"
    scratch.mkdir()
    return ContainerAdapter(ensure_image(scratch))


def _differential(repo: Path, body: str, adapter: ContainerAdapter, base: str, head: str):
    return execute_differential(
        repo,
        candidate(file="mod.py", line=2),
        ReproSpec(body),
        ExecutorLimits(wall_timeout_s=120.0),
        base_sha=base,
        head_sha=head,
        adapter=adapter,
    )


def test_a_real_regression_certifies_inside_the_container(
    tmp_path: Path, adapter: ContainerAdapter
) -> None:
    repo, base_sha, head_sha = differential_repo(tmp_path)
    result = _differential(repo, DIFFERENTIAL_BODY, adapter, base_sha, head_sha)
    assert result.outcome is ExecutionOutcome.REPRODUCED, result.reason
    assert [run.outcome.value for run in result.head_runs] == ["reproduced"] * 3
    assert [run.outcome.value for run in result.base_runs] == ["not_reproduced"] * 3
    assert all(run.executor_profile == CONTAINER_PROFILE for run in result.head_runs)
    assert all(run.executor_digest == adapter.backend_digest() for run in result.head_runs)
    assert result.binding is not None and result.binding.executed_changed_lines == (2,)
    assert adapter.image.digest
    other = ContainerAdapter(ContainerImage(adapter.image.reference, "x"))
    assert adapter.backend_digest() != other.backend_digest()


def test_head_code_cannot_read_the_controllers_secret(
    tmp_path: Path, adapter: ContainerAdapter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATTEST_CANARY_TOKEN", "canary-must-not-leak")
    monkeypatch.setenv("CANARY_PLAIN", "plain-must-not-leak")
    repo, base_sha, head_sha = differential_repo(tmp_path)
    body = (
        "import os\n\n"
        "def test_repro():\n"
        "    leaked = {k: v for k, v in os.environ.items() if 'CANARY' in k}\n"
        "    assert leaked == {}, leaked\n"
        "    assert os.environ.get('ATTEST_CANARY_TOKEN') is None\n"
        "    assert 'must-not-leak' not in ''.join(os.environ.values())\n"
    )
    result = _differential(repo, body, adapter, base_sha, head_sha)
    # the canary is absent on both trees, so the test passes on head: not a
    # regression, and nothing about the secret reached the job
    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED, result.reason
    for run in result.head_runs:
        assert "must-not-leak" not in run.stdout + run.stderr


def test_a_socket_connection_fails_and_marks_the_run(
    tmp_path: Path, adapter: ContainerAdapter
) -> None:
    repo, base_sha, head_sha = differential_repo(tmp_path)
    body = (
        "import socket\n\n"
        "def test_repro():\n"
        "    s = socket.socket()\n"
        "    s.settimeout(3)\n"
        "    try:\n"
        "        s.connect(('1.1.1.1', 80))\n"
        "    except OSError:\n"
        "        return  # denied: the test itself passes\n"
        "    raise AssertionError('connected')\n"
    )
    result = _differential(repo, body, adapter, base_sha, head_sha)
    assert result.outcome is ExecutionOutcome.DEFERRED
    assert "network connection" in result.reason
    assert result.evidence_class is not EvidenceClass.REGRESSION_REPRODUCED


def test_a_write_outside_the_work_directory_fails_and_marks_the_run(
    tmp_path: Path, adapter: ContainerAdapter
) -> None:
    repo, base_sha, head_sha = differential_repo(tmp_path)
    body = (
        "import os\n\n"
        "def test_repro():\n"
        "    failures = 0\n"
        "    for target in ('/attest/tree/escaped.txt', '/etc/escaped.txt', '/attest/inputs/x'):\n"
        "        try:\n"
        "            with open(target, 'w') as handle:\n"
        "                handle.write('escaped')\n"
        "        except OSError:\n"
        "            failures += 1\n"
        "    assert failures == 3, failures\n"
    )
    result = _differential(repo, body, adapter, base_sha, head_sha)
    assert result.outcome is ExecutionOutcome.DEFERRED
    assert "write outside its work directory" in result.reason
    assert not (repo / "escaped.txt").exists()
    assert not any(repo.rglob("escaped.txt"))


def test_the_container_runs_as_an_unprivileged_user_without_capabilities(
    tmp_path: Path, adapter: ContainerAdapter
) -> None:
    repo, base_sha, head_sha = differential_repo(tmp_path)
    body = (
        "import os, resource\n\n"
        "def test_repro():\n"
        "    assert os.getuid() != 0\n"
        "    caps = [l for l in open('/proc/self/status') if l.startswith('CapEff')]\n"
        "    assert caps and caps[0].split()[1].strip('0') == '', caps\n"
        "    assert resource.getrlimit(resource.RLIMIT_NPROC) == (0, 0)\n"
    )
    result = _differential(repo, body, adapter, base_sha, head_sha)
    assert result.outcome is ExecutionOutcome.NOT_REPRODUCED, result.reason


@pytest.mark.skipif(os.name != "posix", reason="posix")
def test_docker_argv_is_the_declared_profile(tmp_path: Path, adapter: ContainerAdapter) -> None:
    from attest.execution.controller import Controller
    from attest.execution.types import ResourceLimits

    controller = Controller(tmp_path / "runs")
    request = controller.issue(
        task_id="t",
        run_id="head-1",
        candidate_id="c",
        revision_sha="",
        profile=CONTAINER_PROFILE,
        interpreter="python",
        argv_template=["python", "-c", "pass"],
        environment={"ATTEST_OUTPUTS": "{outputs}"},
        inputs={},
        limits=ResourceLimits(30.0, 10, 512, 4096),
        expected_artifacts=["stdout.txt"],
    )
    argv = adapter.command(request, tree=tmp_path, inputs=tmp_path, outputs=tmp_path)
    joined = " ".join(argv)
    for flag in (
        "--network none",
        "--read-only",
        "--user 65534:65534",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        "RLIMIT_NPROC, (0, 0)",
        "--pids-limit",
        "--entrypoint /usr/bin/env",
        "-i PATH=",
    ):
        assert flag in joined, flag
    assert "ATTEST_OUTPUTS=/attest/outputs" in argv


# numpy is on both sides of the import and inside the assertion, so the OpenBLAS
# thread question is still asked; the assertion pins the literal the base tree's
# own test states, so D-127's value rule does not stand in front of this one.
NUMPY_BODY = (
    "import numpy\nimport mod\n\n"
    "def test_repro():\n"
    "    assert int(numpy.array([mod.add(2, 2)]).sum()) == 4\n"
)


NUMPY_MANIFEST = (
    "[project]\n"
    'name = "numpy-fixture"\n'
    'version = "0"\n'
    'requires-python = ">=3.12"\n'
    "classifiers = [\"Programming Language :: Python :: 3.12\"]\n"
)


@pytest.fixture
def numpy_adapter(tmp_path: Path) -> ContainerAdapter:
    """The image for a tree that declares numpy: the smallest project whose
    import spawns OpenBLAS threads the run is not allowed to create. The
    interpreter is pinned to one numpy ships a wheel for, so the fixture is an
    image pull and not a source build."""
    scratch = tmp_path / "numpy-image-source"
    scratch.mkdir()
    (scratch / "pyproject.toml").write_text(NUMPY_MANIFEST, encoding="utf-8")
    (scratch / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    return ContainerAdapter(ensure_image(scratch))


def test_a_project_that_imports_numpy_runs_inside_the_container(
    tmp_path: Path, numpy_adapter: ContainerAdapter
) -> None:
    """RLIMIT_NPROC = 0 is the containment the backend is built on, so OpenBLAS
    cannot have its twelve threads. It has to be told to want one instead, or
    every candidate in a numpy project DEFERs before any evidence is bought."""
    repo, base_sha, head_sha = differential_repo(tmp_path)
    (repo / "pyproject.toml").write_text(NUMPY_MANIFEST, encoding="utf-8")
    (repo / "requirements.txt").write_text("numpy\n", encoding="utf-8")

    result = _differential(repo, NUMPY_BODY, numpy_adapter, base_sha, head_sha)

    assert result.outcome is ExecutionOutcome.REPRODUCED, result.reason
    joined = "".join(run.stdout + run.stderr for run in result.head_runs + result.base_runs)
    assert "blas_thread_init" not in joined, joined[:2000]
