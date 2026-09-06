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
    from requires-python, an upper bound from classifiers, and the **primary**
    (3.12) when nothing is declared. D-162 moved the supported range to
    3.10-3.13 and the no-declaration answer from the 3.9 era fallback to the
    primary; `tests/execution/test_python_matrix.py` pins the range itself."""
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
    assert project_python(tmp_path)[0] == "3.12"


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
    monkeypatch.setattr(container_images, "resolve_image", lambda *a, **k: "")
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
    monkeypatch.setattr(container_images, "resolve_image", lambda *a, **k: "")
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
    monkeypatch.setattr(container_images, "resolve_image", lambda *a, **k: "")
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


def test_an_image_build_cannot_outlast_the_verification_budget_it_runs_under(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`select_backend` runs before the first deadline check, so a build capped
    at 1800 s under a 600 s shared deadline could "succeed" at 601 s and leave
    every candidate DEFERring with `shared verification deadline exceeded` --
    the wrong category, after up to 30 minutes of runner time bought for
    nothing (owner decision 2 of 2026-09-03d). The cap is now
    min(1800, remaining), and no budget at all buys no build."""
    import subprocess

    from attest.execution import container_images

    real_run = subprocess.run
    seen: list[object] = []

    def recording(args: object, **kwargs: object) -> object:
        if isinstance(args, list) and args[1:2] == ["build"]:
            seen.append(kwargs.get("timeout"))
            raise subprocess.TimeoutExpired(cmd=args, timeout=float(kwargs["timeout"]))  # type: ignore[arg-type]
        return real_run(args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(container_images.subprocess, "run", recording)
    monkeypatch.setattr(container_images, "docker_executable", lambda: "/usr/bin/docker")
    monkeypatch.setattr(container_images, "resolve_image", lambda *a, **k: "")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    with pytest.raises(container_images.BootstrapFailed) as short:
        container_images.ensure_image(tmp_path, remaining_s=420.0)
    assert seen == [420.0]
    assert "timed out after 420 s" in str(short.value)

    # the 1800 s ceiling still binds when the budget is larger
    with pytest.raises(container_images.BootstrapFailed):
        container_images.ensure_image(tmp_path, remaining_s=9000.0)
    assert seen[-1] == float(container_images.IMAGE_BUILD_TIMEOUT_S)

    # an exhausted budget never reaches the daemon at all
    with pytest.raises(container_images.BootstrapFailed) as spent:
        container_images.ensure_image(tmp_path, remaining_s=0.0)
    assert len(seen) == 2, "a build was attempted with no budget left"
    assert "no verification budget remained" in str(spent.value)


def test_a_reusable_image_is_found_and_addressed_by_id_not_by_tag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`docker image inspect <name:tag>` answered *No such image* for tags the
    same daemon listed in `docker images` and resolved by id, so a warm image
    was rebuilt from scratch. The reuse decision now reads the list path, and
    what it returns -- the id -- is what the run is addressed by, so neither
    the lookup nor the run depends on the resolver that was wrong."""
    import subprocess

    from attest.execution import container_adapter, container_images

    identifier = "sha256:" + "d6" * 32
    calls: list[list[str]] = []

    def daemon(args: object, **kwargs: object) -> object:
        assert isinstance(args, list)
        calls.append(args)
        if args[1:3] == ["image", "inspect"]:  # the resolver that was wrong
            return subprocess.CompletedProcess(args, 1, "", "Error: No such image")
        if args[1:2] == ["images"]:
            return subprocess.CompletedProcess(args, 0, identifier + "\n", "")
        raise AssertionError(f"unexpected docker call: {args}")

    monkeypatch.setattr(container_adapter.subprocess, "run", daemon)
    monkeypatch.setattr(container_images, "docker_executable", lambda: "/usr/bin/docker")
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")

    image = container_images.ensure_image(tmp_path)
    assert image.reference == identifier
    assert image.digest == identifier
    assert image.tag.startswith("attest-repro:")
    assert not any(args[1:2] == ["build"] for args in calls), "a warm image was rebuilt"


def test_a_hatch_vcs_project_pretends_its_version_like_a_setuptools_scm_one(
    tmp_path: Path,
) -> None:
    """`hatch-vcs` is setuptools_scm behind a different name in `pyproject.toml`,
    and it fails identically when the tree is copied without `.git`:
    `LookupError: Error getting the version from source 'vcs'`. Measured on
    `tenacity` at `26f719d` (release-readiness acceptance, 2026-09-09), where the
    whole image build died at `pip install /attest/build` and the repository was
    reported unreviewable. The version file it names is gitignored, so the
    fallback is what has to carry it."""
    from attest.execution.container_images import (
        discover_roots,
        dockerfile,
        scm_pretend_version,
    )

    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling", "hatch-vcs"]\n'
        '[tool.hatch.version]\nsource = "vcs"\n',
        encoding="utf-8",
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    roots = discover_roots(tmp_path)

    scm = scm_pretend_version(tmp_path, roots)

    assert scm == "0.0.1"
    assert "ENV SETUPTOOLS_SCM_PRETEND_VERSION=0.0.1" in dockerfile("3.13", roots, scm)


def test_a_version_string_from_the_reviewed_tree_cannot_write_a_dockerfile_step(
    tmp_path: Path,
) -> None:
    """Independent review of 2026-09-09, finding 1. `_version.py` is **content
    from the tree under review**, and its captured value is interpolated into a
    generated Dockerfile that `docker build` runs with network access. The
    capture class `[^'"]+` matches newlines, so a crafted version file could
    append its own `RUN` step. Nothing about a version number needs a newline."""
    from attest.execution.container_images import (
        discover_roots,
        dockerfile,
        scm_pretend_version,
    )

    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools", "setuptools-scm"]\n', encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "_version.py").write_text(
        'version = "1.0.0\nRUN echo pwned > /tmp/pwned\n"\n', encoding="utf-8"
    )
    roots = discover_roots(tmp_path)

    scm = scm_pretend_version(tmp_path, roots)

    assert scm is not None
    assert "\n" not in scm
    assert "RUN" not in scm
    text = dockerfile("3.12", roots, scm)
    assert "pwned" not in text
    assert sum(1 for line in text.splitlines() if line.startswith("RUN")) == len(
        [line for line in text.splitlines() if line.startswith("RUN")]
    )
    assert all(
        line.startswith(("FROM ", "ENV ", "RUN ", "COPY "))
        for line in text.splitlines()
        if line.strip()
    )


def test_an_ordinary_version_string_is_still_used(tmp_path: Path) -> None:
    from attest.execution.container_images import discover_roots, scm_pretend_version

    (tmp_path / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["hatchling", "hatch-vcs"]\n', encoding="utf-8"
    )
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "_version.py").write_text(
        'version = "7.4.0.dev3+g1a2b3c4"\n', encoding="utf-8"
    )

    assert scm_pretend_version(tmp_path, discover_roots(tmp_path)) == "7.4.0.dev3+g1a2b3c4"
