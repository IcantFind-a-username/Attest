"""X-02: backend selection fails closed for production and never hands the
host adapter to a production task."""

from __future__ import annotations

from pathlib import Path

import pytest

from attest.execution import backends
from attest.execution.container_adapter import CONTAINER_PROFILE
from attest.execution.types import LOCAL_DEVELOPMENT_PROFILE


@pytest.mark.real_backend
def test_production_without_docker_defers_and_never_uses_the_host_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backends, "docker_executable", lambda: None)
    monkeypatch.delenv(backends.EXECUTOR_ENV, raising=False)
    selection = backends.select_backend(tmp_path, production=True)
    assert selection.adapter is None
    assert selection.profile == CONTAINER_PROFILE
    assert "isolation backend unavailable" in selection.reason

    # the operator's local override is ignored by a production task
    monkeypatch.setenv(backends.EXECUTOR_ENV, "local")
    forced = backends.select_backend(tmp_path, production=True)
    assert forced.adapter is None
    assert forced.profile == CONTAINER_PROFILE
    assert "isolation backend unavailable" in forced.reason


@pytest.mark.real_backend
def test_local_review_falls_back_to_the_host_adapter_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backends, "docker_executable", lambda: None)
    monkeypatch.delenv(backends.EXECUTOR_ENV, raising=False)
    selection = backends.select_backend(tmp_path, production=False)
    assert selection.adapter is not None
    assert selection.profile == LOCAL_DEVELOPMENT_PROFILE
    assert "no OS boundary" in selection.reason


@pytest.mark.real_backend
def test_bootstrap_failure_is_the_reason_not_silence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(backends, "docker_executable", lambda: "/usr/bin/docker")

    def failing(tree: Path, **kwargs: object) -> object:
        raise backends.BootstrapFailed("environment bootstrap failed (python 3.9): pip failed")

    monkeypatch.setattr(backends, "ensure_image", failing)
    selection = backends.select_backend(tmp_path, production=True)
    assert selection.adapter is None
    assert selection.reason.startswith("environment bootstrap failed")


def test_project_python_honours_requires_python_and_classifiers(tmp_path: Path) -> None:
    """The image interpreter follows the project's declaration: a lower bound
    from requires-python, an upper bound from classifiers, the era fallback
    only when nothing is declared (2026-09-03)."""
    from attest.execution.container_images import project_python

    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nrequires-python = ">=3.11"\n', encoding="utf-8"
    )
    assert project_python(tmp_path)[0] == "3.13"
    (tmp_path / "setup.py").write_text(
        'classifiers=["Programming Language :: Python :: 3.12"]\n', encoding="utf-8"
    )
    assert project_python(tmp_path)[0] == "3.12"
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    assert project_python(tmp_path)[0] == "3.12"
    (tmp_path / "setup.py").unlink()
    assert project_python(tmp_path)[0] == "3.9"


def test_dockerfile_pretends_the_scm_version_and_keeps_nested_projects_best_effort(
    tmp_path: Path,
) -> None:
    """Held-out bootstrap (2026-09-03): a setuptools_scm project builds with the
    version its committed _version.py carries, the tree root's own install is
    required, and nested example/docs projects cannot fail the image."""
    from attest.execution.container_images import (
        discover_roots,
        dockerfile,
        scm_pretend_version,
    )

    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools", "setuptools-scm"]\n', encoding="utf-8"
    )
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    (tmp_path / "src" / "pkg" / "_version.py").write_text('version = "7.4.0"\n', encoding="utf-8")
    (tmp_path / "examples").mkdir()
    (tmp_path / "examples" / "setup.py").write_text("raise SystemExit(1)\n", encoding="utf-8")
    roots = discover_roots(tmp_path)
    scm = scm_pretend_version(tmp_path, roots)
    assert scm == "7.4.0"
    text = dockerfile("3.11", roots, scm)
    assert "ENV SETUPTOOLS_SCM_PRETEND_VERSION=7.4.0" in text
    assert "RUN pip install /attest/build\n" in text
    assert (
        'RUN pip install /attest/build/examples || echo "attest: optional project examples' in text
    )


def test_an_image_build_that_times_out_is_a_bootstrap_failure_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A 30-minute `docker build` on pytest's own tree raised TimeoutExpired
    straight out of select_backend, crashing the run instead of DEFERring with
    the reason `failure-modes.md` promises the operator."""
    import subprocess

    from attest.execution import container_images

    real_run = subprocess.run

    def timing_out(args: object, **kwargs: object) -> object:
        # only the build: `container_images.subprocess` *is* the stdlib module,
        # so an unconditional stub would refuse every other subprocess in the
        # process for the duration of this test
        if isinstance(args, list) and args[1:2] == ["build"]:
            raise subprocess.TimeoutExpired(
                cmd=args, timeout=container_images.IMAGE_BUILD_TIMEOUT_S
            )
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(container_images.subprocess, "run", timing_out)
    monkeypatch.setattr(container_images, "docker_executable", lambda: "/usr/bin/docker")
    monkeypatch.setattr(container_images, "image_digest", lambda *a, **k: "")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    with pytest.raises(container_images.BootstrapFailed) as caught:
        container_images.ensure_image(tmp_path)
    assert str(caught.value).startswith("environment bootstrap failed (python 3.")
    assert "roots ['.']" in str(caught.value)
    assert "timed out" in str(caught.value)


def test_a_build_context_that_cannot_be_assembled_is_a_bootstrap_failure_not_a_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A dangling symlink anywhere in the tree makes `shutil.copytree` raise
    `shutil.Error` out of `ensure_image`, so the same crash the timeout fix
    removed comes back through the line above it: the operator gets a
    traceback where `failure-modes.md` promises a bootstrap failure."""
    from attest.execution import container_images

    monkeypatch.setattr(container_images, "docker_executable", lambda: "/usr/bin/docker")
    monkeypatch.setattr(container_images, "image_digest", lambda *a, **k: "")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (tmp_path / "broken-link").symlink_to(tmp_path / "no-such-target")

    with pytest.raises(container_images.BootstrapFailed) as caught:
        container_images.ensure_image(tmp_path)
    assert str(caught.value).startswith("environment bootstrap failed")
    assert "build context" in str(caught.value)


def test_a_timed_out_build_reports_the_tail_of_its_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`TimeoutExpired` carries what the build printed before it was killed --
    the only signal naming which step was still running after 30 minutes.
    The message dropped it, and `capture_output=True` leaves those attributes
    as *bytes*, so copying the sibling branch would splice a b'...' repr into
    the operator's status line."""
    import subprocess

    from attest.execution import container_images

    real_run = subprocess.run

    def timing_out(args: object, **kwargs: object) -> object:
        if isinstance(args, list) and args[1:2] == ["build"]:
            raise subprocess.TimeoutExpired(
                cmd=args,
                timeout=container_images.IMAGE_BUILD_TIMEOUT_S,
                output=b"#8 [4/6] RUN pip install -r requirements.txt\n",
                stderr=b"#8 12.3 Collecting numpy\n",
            )
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(container_images.subprocess, "run", timing_out)
    monkeypatch.setattr(container_images, "docker_executable", lambda: "/usr/bin/docker")
    monkeypatch.setattr(container_images, "image_digest", lambda *a, **k: "")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    with pytest.raises(container_images.BootstrapFailed) as caught:
        container_images.ensure_image(tmp_path)
    message = str(caught.value)
    assert "Collecting numpy" in message
    assert "b'" not in message and "b\"" not in message


def test_the_image_probe_is_bounded_and_answers_unknown_when_docker_will_not(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`image_digest` is the only other subprocess on the `select_backend`
    path and it had no timeout at all: a wedged daemon -- the same condition
    that makes a build time out -- hung the review forever with no DEFER, no
    status line and no traceback, which is worse than the crash that was
    fixed. Unknown is this function's existing contract ('' at both call
    sites), so a probe that cannot answer must return it."""
    import subprocess

    from attest.execution import container_adapter

    seen: dict[str, object] = {}

    def refusing(args: object, **kwargs: object) -> object:
        seen.update(kwargs)
        raise subprocess.TimeoutExpired(cmd=args, timeout=1.0)

    monkeypatch.setattr(container_adapter.subprocess, "run", refusing)
    assert container_adapter.image_digest("attest-repro:deadbeef", docker="/usr/bin/docker") == ""
    assert seen.get("timeout"), "the probe must carry a timeout"

    def missing(args: object, **kwargs: object) -> object:
        raise OSError(13, "permission denied")

    monkeypatch.setattr(container_adapter.subprocess, "run", missing)
    assert container_adapter.image_digest("attest-repro:deadbeef", docker="/usr/bin/docker") == ""
