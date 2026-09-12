"""X-02: backend selection fails closed for production and never hands the
host adapter to a production task."""

from __future__ import annotations

import os
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


# --- the three one-line fixes of 2026-09-11 -----------------------------------


def _launcher_argv(*job: str) -> list[str]:
    """The adapter's launcher, with this host's interpreter in the image's place."""
    import sys

    from attest.execution.container_adapter import NPROC_LAUNCHER_ARGV

    return [sys.executable if entry == "python3" else entry for entry in NPROC_LAUNCHER_ARGV] + [
        sys.executable if job[0] == "python3" else job[0],
        *job[1:],
    ]


@pytest.mark.skipif(os.name != "posix", reason="RLIMIT_NPROC is posix")
def test_the_launcher_imports_no_sitecustomize_but_the_job_still_does(tmp_path: Path) -> None:
    """The launcher sets RLIMIT_NPROC and execs the job. Until 2026-09-11 it was
    `python3 -c`, which imports `sitecustomize` from PYTHONPATH *before* the
    limit is set -- so the guard's own containment check raised inside the
    launcher, Python printed `kernel process containment is inactive` to every
    run's stderr, and the sentence was in every root-cause read of every run
    although nothing was ever inactive. The job, exec'd after the limit, imports
    the guard under RLIMIT_NPROC = (0, 0) and writes `process-contained`."""
    import subprocess

    (tmp_path / "sitecustomize.py").write_text(
        "import os, pathlib, resource\n"
        "if resource.getrlimit(resource.RLIMIT_NPROC) != (0, 0):\n"
        "    raise RuntimeError('kernel process containment is inactive')\n"
        "pathlib.Path(os.environ['ATTEST_TEST_MARK']).write_text('active')\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        _launcher_argv("python3", "-c", "pass"),
        env={
            "PATH": os.environ.get("PATH", ""),
            "PYTHONPATH": str(tmp_path),
            "ATTEST_TEST_MARK": str(tmp_path / "process-contained"),
        },
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert "containment is inactive" not in completed.stderr
    assert (tmp_path / "process-contained").read_text(encoding="utf-8") == "active"


@pytest.mark.skipif(os.name != "posix", reason="RLIMIT_NPROC is posix")
def test_the_launcher_seeds_the_font_cache_into_the_writable_cache_directory(
    tmp_path: Path,
) -> None:
    """matplotlib refuses a cache directory it cannot write (`os.access(W_OK)`
    in `_get_config_or_cache_dir`) and rebuilds the font list in a temp dir
    instead -- on a thread the guard rejects. The image's warmed cache sits on
    a read-only root, so the launcher copies it into the run's writable
    MPLCONFIGDIR before the job starts. No seed directory, no copy."""
    import subprocess

    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "fontlist-v330.json").write_text("{}", encoding="utf-8")
    target = tmp_path / "scratch" / "mpl"
    env = {
        "PATH": os.environ.get("PATH", ""),
        "ATTEST_MPL_SEED": str(seed),
        "MPLCONFIGDIR": str(target),
    }
    completed = subprocess.run(
        _launcher_argv("python3", "-c", "pass"),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    assert (target / "fontlist-v330.json").read_text(encoding="utf-8") == "{}"

    env["ATTEST_MPL_SEED"] = str(tmp_path / "absent")
    env["MPLCONFIGDIR"] = str(tmp_path / "scratch2" / "mpl")
    completed = subprocess.run(
        _launcher_argv("python3", "-c", "pass"), env=env, capture_output=True, text=True, timeout=60
    )
    assert completed.returncode == 0, completed.stderr
    assert not (tmp_path / "scratch2").exists()


def test_the_image_warms_the_font_cache_into_a_named_directory_the_job_can_read(
    tmp_path: Path,
) -> None:
    """D-214 warmed the cache as root into /root; the job runs as uid 65534
    with HOME on the scratch tmpfs, so it never found it. The warm now goes
    to MPLCONFIGDIR=/attest/mpl, set *before* the import, and the directory is
    made world-readable *after* it."""
    from attest.execution.container_adapter import MPL_SEED_DIR
    from attest.execution.container_images import discover_roots, dockerfile

    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'\nversion='1'\n", encoding="utf-8")
    text = dockerfile("3.11", discover_roots(tmp_path), None)
    lines = text.splitlines()
    env_at = lines.index(f"ENV MPLCONFIGDIR={MPL_SEED_DIR}")
    warm_at = next(i for i, line in enumerate(lines) if "import matplotlib.font_manager" in line)
    chmod_at = next(i for i, line in enumerate(lines) if f"chmod -R a+rX {MPL_SEED_DIR}" in line)
    assert env_at < warm_at < chmod_at


def test_the_container_job_is_told_where_its_font_cache_is(tmp_path: Path) -> None:
    from attest.execution.container_adapter import (
        MPL_SEED_DIR,
        SCRATCH_MOUNT,
        ContainerAdapter,
        ContainerImage,
    )
    from attest.execution.controller import Controller
    from attest.execution.types import ResourceLimits

    adapter = ContainerAdapter(ContainerImage("img", ""), docker="/nonexistent/docker")
    request = Controller(tmp_path / "runs").issue(
        task_id="t",
        run_id="head-1",
        candidate_id="c",
        revision_sha="",
        profile=adapter.profile,
        interpreter="python",
        argv_template=["python", "-c", "pass"],
        environment={},
        inputs={},
        limits=ResourceLimits(30.0, 10, 512, 4096),
        expected_artifacts=["stdout.txt"],
    )
    argv = adapter.command(request, tree=tmp_path, inputs=tmp_path, outputs=tmp_path)
    assert f"MPLCONFIGDIR={SCRATCH_MOUNT}/mpl" in argv
    assert f"ATTEST_MPL_SEED={MPL_SEED_DIR}" in argv
    assert argv[argv.index("-c") - 1 :][:2] == ["-I", "-c"]


# --- D-236: the generated version file of a repository-versioned tree -----------


def _scm_tree(tmp_path: Path, pyproject: str, *, version_file: str | None = None) -> Path:
    tree = tmp_path / "tree"
    (tree / "src" / "pkg").mkdir(parents=True)
    (tree / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (tree / "src" / "pkg" / "__init__.py").write_text(
        "from ._version import __version__\n", encoding="utf-8"
    )
    if version_file is not None:
        (tree / "src" / "pkg" / "_version.py").write_text(version_file, encoding="utf-8")
    return tree


HATCH_VCS = (
    '[build-system]\nrequires = ["hatchling", "hatch-vcs"]\n'
    '[project]\nname = "pkg"\ndynamic = ["version"]\n'
    '[tool.hatch.version]\nsource = "vcs"\n'
    '[tool.hatch.build.hooks.vcs]\nversion-file = "src/pkg/_version.py"\n'
)


def test_the_declared_version_file_is_written_once_with_the_pretend_version(
    tmp_path: Path,
) -> None:
    from attest.execution.container_images import provision_scm_version_file

    tree = _scm_tree(tmp_path, HATCH_VCS)

    written = provision_scm_version_file(tree)

    assert written == tree / "src" / "pkg" / "_version.py"
    text = written.read_text(encoding="utf-8")
    assert "__version__ = version = '0.0.1'" in text
    assert "__version_tuple__ = version_tuple = (0, 0, 1)" in text
    # a committed file is the tree's and is never overwritten
    (tree / "src" / "pkg" / "_version.py").write_text("__version__ = '9.9'\n", encoding="utf-8")
    assert provision_scm_version_file(tree) is None
    kept = (tree / "src" / "pkg" / "_version.py").read_text(encoding="utf-8")
    assert kept == "__version__ = '9.9'\n"


def test_a_version_file_path_that_leaves_the_tree_or_names_no_python_file_is_not_written(
    tmp_path: Path,
) -> None:
    from attest.execution.container_images import provision_scm_version_file

    bad = ("../outside.py", "src/pkg/_version.txt", "/etc/passwd.py", "src/pkg/../../x.py")
    for declared in bad:
        pyproject = HATCH_VCS.replace(
            'version-file = "src/pkg/_version.py"', f'version-file = "{declared}"'
        )
        tree = _scm_tree(tmp_path / declared.replace("/", "_").replace(".", "_"), pyproject)
        assert provision_scm_version_file(tree) is None
    # setuptools_scm's spelling, and a project that is not repository-versioned at all
    scm = _scm_tree(
        tmp_path / "scm",
        '[build-system]\nrequires = ["setuptools", "setuptools_scm"]\n'
        '[tool.setuptools_scm]\nwrite_to = "src/pkg/_version.py"\n',
    )
    assert provision_scm_version_file(scm) == scm / "src" / "pkg" / "_version.py"
    plain = _scm_tree(tmp_path / "plain", '[project]\nname = "pkg"\nversion = "1.0"\n')
    assert provision_scm_version_file(plain) is None
