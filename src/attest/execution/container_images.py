"""Images for ``linux-container-v1`` and the environment bootstrap (X-02, item 8).

An image is built from the tree under review: the interpreter is chosen by the
executor-side rule (the highest Python the project's declared classifiers
allow, else 3.9; owner item 3 of 2026-09-02), pytest is installed, and every
project root the tree declares (``pyproject.toml``, ``setup.py``,
``setup.cfg``, ``requirements*.txt``; ``services/*`` layouts included) is
installed at build time -- with network, before any head code runs. The tag is
a digest of the interpreter and of the dependency manifests, so an unchanged
project reuses its image. A bootstrap that fails is reported as exactly that
(``environment bootstrap failed: ...``), never as "no findings".
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from attest.execution.container_adapter import (
    MPL_SEED_DIR,
    ContainerImage,
    docker_executable,
    image_digest,
    image_id,
)

# D-162: the supported interpreter matrix. 3.9 was the era fallback when the
# corpus was old open-source Python; the declared range is now 3.10-3.13, and a
# tree that names nothing usable gets the **primary** -- the version this
# project itself is built and shipped on (`docs/operations/install-ref.md`).
AVAILABLE_PYTHONS = ("3.13", "3.12", "3.11", "3.10")
PRIMARY_PYTHON = "3.12"
FALLBACK_PYTHON = PRIMARY_PYTHON  # the name the older call sites use
_CLASSIFIER_RE = re.compile(r"Programming Language :: Python :: 3\.(\d+)")
# The dependency declaration of a tree, in the order the digest reads them.
# The lock files are here for the cache key, not for installation: two commits
# that changed only source code carry byte-identical locks and must reuse one
# image, and a commit that moved a pin must not (D-156).
_MANIFESTS = (
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "requirements.txt",
    "requirements-dev.txt",
    "poetry.lock",
    "uv.lock",
    "pdm.lock",
    "Pipfile",
    "Pipfile.lock",
    "requirements.lock",
    "constraints.txt",
)
LOCK_MANIFESTS = frozenset(
    {"poetry.lock", "uv.lock", "pdm.lock", "Pipfile", "Pipfile.lock", "requirements.lock"}
)
_SKIP = {
    ".git",
    ".attest",
    ".attest-repro",
    ".venv",
    "venv",
    "node_modules",
    "build",
    "dist",
    "__pycache__",
    ".tox",
    ".nox",
}
MAX_DEPTH = 4


class BootstrapFailed(RuntimeError):
    """The image could not be built for this tree; the reason is the message."""


@dataclass(frozen=True)
class ProjectRoot:
    relative: str  # "" for the tree root
    manifests: tuple[str, ...]


_REQUIRES_PYTHON_RE = re.compile(r"requires-python\s*=\s*[\"']\s*>=\s*3\.(\d+)")
# D-162: the same lower bound as a lock file states it. `uv.lock` writes
# `requires-python`, `poetry.lock` writes `python-versions` in its metadata, and
# `Pipfile` writes `python_version`; all three are read for the bound only.
_LOCK_LOWER_RES = (
    re.compile(r"requires-python\s*=\s*[\"']\s*>=\s*3\.(\d+)"),
    re.compile(r"python-versions\s*=\s*[\"'][^\"']*?>=\s*3\.(\d+)"),
    re.compile(r"python[-_]version\s*=\s*[\"']\s*3\.(\d+)\s*[\"']"),
)
_LOCK_SOURCES = ("uv.lock", "poetry.lock", "pdm.lock", "Pipfile")


def _lock_lower_bounds(tree: Path, roots: list[ProjectRoot]) -> list[int]:
    """Every `>= 3.X` a lock file in this tree states, as minor versions."""
    found: list[int] = []
    for root in roots:
        base = tree / root.relative if root.relative else tree
        for name in _LOCK_SOURCES:
            path = base / name
            if not path.is_file():
                continue
            try:
                text = path.read_text(errors="replace")
            except OSError:
                continue
            for pattern in _LOCK_LOWER_RES:
                found.extend(int(match) for match in pattern.findall(text))
    return found


def project_python(tree: Path) -> tuple[str, str]:
    """(python minor version, reason) by the project's own declaration.

    The highest **supported** interpreter (3.10-3.13) no newer than the newest
    ``Programming Language :: Python :: 3.X`` classifier and no older than the
    strictest lower bound the tree states -- in ``requires-python`` or in a lock
    file (``uv.lock``'s ``requires-python``, ``poetry.lock``'s
    ``python-versions``, ``Pipfile``'s ``python_version``). A tree that names
    nothing usable gets the **primary**, 3.12 (D-162).

    A declared floor below 3.10 does not select 3.9: the supported range is the
    supported range, and a project that cannot install on 3.10 is a bootstrap
    DEFER with its reason, never a finding.
    """
    declared: list[int] = []
    lower: list[int] = []
    roots = discover_roots(tree)
    lower.extend(_lock_lower_bounds(tree, roots))
    for root in roots:
        for name in ("setup.py", "setup.cfg", "pyproject.toml"):
            path = tree / root.relative / name if root.relative else tree / name
            if path.is_file():
                try:
                    text = path.read_text(errors="replace")
                except OSError:
                    continue
                declared.extend(int(m) for m in _CLASSIFIER_RE.findall(text))
                lower.extend(int(m) for m in _REQUIRES_PYTHON_RE.findall(text))
    floor = max(lower) if lower else None
    ceiling = max(declared) if declared else None
    for version in AVAILABLE_PYTHONS:
        minor = int(version.split(".")[1])
        if ceiling is not None and minor > ceiling:
            continue
        if floor is not None and minor < floor:
            continue
        if ceiling is None and floor is None:
            continue
        reason = []
        if ceiling is not None:
            reason.append(f"classifiers up to 3.{ceiling}")
        if floor is not None:
            reason.append(f"declared floor >= 3.{floor}")
        return version, "; ".join(reason)
    if floor is not None or ceiling is not None:
        return PRIMARY_PYTHON, "declared range outside 3.10-3.13; primary"
    return PRIMARY_PYTHON, "no declaration found; primary"


def discover_roots(tree: Path) -> list[ProjectRoot]:
    """Every directory (bounded depth) holding a dependency manifest, tree root first."""
    found: list[ProjectRoot] = []
    for current in sorted(tree.rglob("*")):
        if not current.is_dir():
            continue
        relative = current.relative_to(tree)
        if len(relative.parts) > MAX_DEPTH or any(part in _SKIP for part in relative.parts):
            continue
        manifests = tuple(name for name in _MANIFESTS if (current / name).is_file())
        if manifests:
            found.append(ProjectRoot(relative.as_posix(), manifests))
    root_manifests = tuple(name for name in _MANIFESTS if (tree / name).is_file())
    roots = [ProjectRoot("", root_manifests)] if root_manifests else []
    roots.extend(sorted(found, key=lambda item: item.relative))
    return roots


def manifest_digest(tree: Path, roots: list[ProjectRoot]) -> str:
    digest = hashlib.sha256()
    for root in roots:
        for name in root.manifests:
            path = tree / root.relative / name if root.relative else tree / name
            digest.update(f"{root.relative}/{name}\n".encode())
            try:
                digest.update(path.read_bytes())
            except OSError:
                digest.update(b"<unreadable>")
    return digest.hexdigest()


_VERSION_FILE_RE = re.compile(r"""^\s*(?:__version__|version)\s*=\s*['"]([^'"]+)['"]""", re.M)
# `_version.py` is **content from the tree under review**, and what this regex
# captures is interpolated into a Dockerfile that `docker build` executes with
# network access. `[^'"]` matches newlines, so an unvalidated capture is a
# Dockerfile injection. A version is a short run of version characters or it is
# not used (independent review of 2026-09-09, finding 1).
_SAFE_VERSION_RE = re.compile(r"\A[A-Za-z0-9][A-Za-z0-9._+!-]{0,63}\Z")


# Every spelling of "this project takes its version from the repository". They
# all end in setuptools_scm and all honour SETUPTOOLS_SCM_PRETEND_VERSION;
# `hatch-vcs` is the one that reaches it through hatchling, and missing it cost
# `tenacity` its whole image build (D-176).
_SCM_MARKERS = ("setuptools_scm", "setuptools-scm", "hatch_vcs", "hatch-vcs")


def scm_pretend_version(tree: Path, roots: list[ProjectRoot]) -> str | None:
    """For a project that versions itself from the repository: the version its
    committed ``_version.py`` carries (the tree is copied without ``.git``, so
    scm metadata is absent at build time); None when scm is not used."""
    uses_scm = False
    for root in roots:
        for name in ("pyproject.toml", "setup.py", "setup.cfg"):
            path = tree / root.relative / name if root.relative else tree / name
            if path.is_file():
                try:
                    text = path.read_text(errors="replace")
                except OSError:
                    continue
                if any(marker in text for marker in _SCM_MARKERS):
                    uses_scm = True
    if not uses_scm:
        return None
    for candidate in sorted(tree.rglob("_version.py")):
        if any(part in _SKIP for part in candidate.relative_to(tree).parts):
            continue
        try:
            found = _VERSION_FILE_RE.search(candidate.read_text(errors="replace"))
        except OSError:
            continue
        if found and _SAFE_VERSION_RE.match(found.group(1)):
            return found.group(1)
    return "0.0.1"


# D-236: the declared location of the generated version file, in the two
# spellings the scm backends use. Only a relative `.py` path inside the tree,
# whose directory already exists, is ever written.
_VERSION_FILE_KEYS = (
    (("tool", "hatch", "build", "hooks", "vcs"), "version-file"),
    (("tool", "setuptools_scm"), "version_file"),
    (("tool", "setuptools_scm"), "write_to"),
)
_SAFE_RELATIVE_RE = re.compile(r"\A[A-Za-z0-9_][A-Za-z0-9_./-]{0,255}\Z")


def declared_version_file(tree: Path, roots: list[ProjectRoot]) -> Path | None:
    """The version file a repository-versioned project's build would generate,
    as `pyproject.toml` declares it, or None when nothing is declared."""
    import tomllib

    for root in roots:
        base = tree / root.relative if root.relative else tree
        path = base / "pyproject.toml"
        if not path.is_file():
            continue
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8", errors="replace"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        for keys, leaf in _VERSION_FILE_KEYS:
            node: object = data
            for key in keys:
                node = node.get(key) if isinstance(node, dict) else None
            value = node.get(leaf) if isinstance(node, dict) else None
            if not isinstance(value, str) or not _SAFE_RELATIVE_RE.match(value):
                continue
            if value.endswith(".py") and ".." not in value.split("/") and not value.startswith("/"):
                return base / value
    return None


def provision_scm_version_file(tree: Path) -> Path | None:
    """Write the generated version file a repository-versioned tree lacks (D-236).

    `hatch-vcs` and `setuptools_scm` write it at build time and the project's
    own `__init__` imports it (`urllib3`: `from ._version import __version__`);
    a worktree at a commit has no build step, so the package could not be
    imported and every probe on such a tree recorded nothing. The content is a
    fixed template around the pretend version the image build already uses --
    nothing of it comes from the tree -- and it is written only when the file is
    absent and its directory exists. Returns the path written, else None.
    """
    roots = discover_roots(tree)
    version = scm_pretend_version(tree, roots)
    if version is None:
        return None
    target = declared_version_file(tree, roots)
    if target is None or target.exists() or not target.parent.is_dir():
        return None
    try:
        target.resolve().relative_to(tree.resolve())
    except ValueError:
        return None
    numbers = re.match(r"\d+(?:\.\d+)*", version)
    parts = tuple(int(x) for x in numbers.group(0).split(".")) if numbers else (0, 0, 1)
    text = (
        "# written by attest into the reviewed worktree: this project versions itself from\n"
        "# the repository and its build would generate this file (D-236)\n"
        f"__version__ = version = {version!r}\n"
        f"__version_tuple__ = version_tuple = {parts!r}\n"
    )
    try:
        target.write_text(text, encoding="utf-8")
    except OSError:
        return None
    return target


def dockerfile(
    python_version: str,
    roots: list[ProjectRoot],
    scm_version: str | None = None,
    *,
    constraints: str | None = None,
) -> str:
    """The image for one tree.

    ``constraints`` is a pip constraint file applied to the **project's** install
    and to nothing else. It is not a product path: nothing in a review supplies
    it, and without it this function's output is byte-identical to what it always
    was. It exists for a historical corpus, where "resolve today's dependencies"
    is the wrong answer -- `xarray` 2022.6 with `numpy` 2.4 raises at import and
    nine of the 2026-09-10 held-out cases died there (D-214).

    It is applied **after** `pip install pytest` on purpose: an era pin on the
    test runner's own dependencies would break the runner rather than reproduce
    the era, and the runner is not what is under review.
    """
    lines = [
        f"FROM python:{python_version}-slim",
        "ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1",
    ]
    if scm_version:
        # setuptools_scm cannot see a repository inside the build context
        lines.append(f"ENV SETUPTOOLS_SCM_PRETEND_VERSION={scm_version}")
    lines.append("RUN pip install pytest")
    if constraints is not None:
        lines += [
            "COPY constraints.txt /attest/constraints.txt",
            "ENV PIP_CONSTRAINT=/attest/constraints.txt",
        ]
    lines.append("COPY tree /attest/build")
    for root in roots:
        directory = "/attest/build" + (f"/{root.relative}" if root.relative else "")
        # the project itself must install (its import roots are what the
        # reproduction needs); requirements files are the project's own dev
        # pins and are best-effort, with the failure kept in the build log
        for name in root.manifests:
            if name.startswith("requirements"):
                lines.append(
                    f"RUN pip install -r {directory}/{name} || "
                    f'echo "attest: optional requirements {root.relative or "."}/{name} failed"'
                )
        if any(name in ("pyproject.toml", "setup.py", "setup.cfg") for name in root.manifests):
            if root.relative:
                lines.append(
                    f"RUN pip install {directory} || "
                    f'echo "attest: optional project {root.relative} failed to install"'
                )
            elif constraints is None:
                lines.append(f"RUN pip install {directory}")
            else:
                # D-214, measured: an era pin can be uninstallable. `numpy<=1.23.1`
                # is right for a 2022 tree and has no wheel for any interpreter
                # newer than 3.10, so on a tree whose classifiers select 3.12 the
                # constrained install fails outright -- and an image that fails to
                # build loses a case the unpinned build would at least have
                # attempted. The pin is therefore an attempt, not a demand: it
                # falls back to exactly the line above, and the build log says
                # which one ran.
                lines.append(
                    f"RUN pip install {directory} || "
                    '(echo "attest: era constraints refused this install; retrying unpinned" '
                    f"&& PIP_CONSTRAINT= pip install {directory})"
                )
    # D-214: `matplotlib.font_manager` builds a `FontManager` on a cache miss,
    # and that constructor starts a `threading.Timer` -- which the executor's
    # thread guard rejects, so the probe dies on a font cache rather than on
    # anything about the diff (two of the 2026-09-10 held-out cases). Warming
    # the cache at build time, with the network still on, means the constructor
    # never runs under the guard. A tree without matplotlib is unaffected: that
    # is what the `|| true` is for, and it costs one failed import.
    # The warm goes to a named directory, set *before* the import, and made
    # world-readable *after* it: as root into $HOME it landed in /root, where
    # the job -- uid 65534, HOME on the scratch tmpfs -- never looked, so the
    # cache missed at run time and `seaborn-3187` still died on the timer
    # thread. The launcher seeds this directory into the run's writable
    # MPLCONFIGDIR (`container_adapter.NPROC_LAUNCHER`).
    lines.append(f"ENV MPLCONFIGDIR={MPL_SEED_DIR}")
    lines.append('RUN python -c "import matplotlib.font_manager" || true')
    lines.append(f"RUN chmod -R a+rX {MPL_SEED_DIR} || true")
    lines.append("RUN rm -rf /attest/build")
    return "\n".join(lines) + "\n"


IMAGE_BUILD_TIMEOUT_S = 1800  # the ceiling; the caller's remaining budget may be lower


def build_timeout(remaining_s: float | None) -> float:
    """``min(IMAGE_BUILD_TIMEOUT_S, remaining_s)``.

    The build runs *before* the first verification deadline check, so a ceiling
    three times the 600 s shared deadline let a 601-1800 s build "succeed" and
    then DEFER every candidate with `shared verification deadline exceeded` --
    the wrong category, after 10-30 minutes of runner time bought for nothing
    (owner decision 2 of 2026-09-03d, D-105 review finding 3).
    """
    if remaining_s is None:
        return float(IMAGE_BUILD_TIMEOUT_S)
    return min(float(IMAGE_BUILD_TIMEOUT_S), float(remaining_s))


def _log_tail(raw: str | bytes | None) -> str:
    """The end of a build log, as text. ``capture_output=True`` leaves the
    attributes of a ``TimeoutExpired`` as bytes even under ``text=True``, so a
    tail taken straight from the exception would splice a ``b'...'`` repr into
    the operator's status line."""
    if raw is None:
        return ""
    text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
    return text[-1200:]


def _bootstrap_failure(version: str, roots: list[ProjectRoot], detail: str) -> BootstrapFailed:
    """Every way this module fails wears the one sentence `failure-modes.md`
    promises the operator, so no path out of here is a traceback."""
    return BootstrapFailed(
        f"environment bootstrap failed (python {version}, roots "
        f"{[root.relative or '.' for root in roots]}): {detail}"
    )


def resolve_image(tag: str, *, docker: str | None = None) -> str:
    """The id docker holds for ``tag``, by the list path first ('' if absent)."""
    return image_id(tag, docker=docker) or image_digest(tag, docker=docker)


# D-214. A measurement knob, in the shape this module already uses for
# `ATTEST_PROJECT_PYTHON` and `ATTEST_WRITABLE`: the path of a pip constraint
# file to apply to the project's install. **Unset in every product path**, and
# unset means the Dockerfile is byte-identical to what it always was.
ERA_CONSTRAINT_ENV = "ATTEST_PIP_CONSTRAINT"


def era_constraints() -> str | None:
    """The constraint file named by the environment, or None.

    Unreadable is None rather than an error: a corpus knob must not be able to
    fail an image build that would otherwise work.
    """
    named = os.environ.get(ERA_CONSTRAINT_ENV, "").strip()
    if not named:
        return None
    try:
        return Path(named).read_text(encoding="utf-8")
    except OSError:
        return None


def ensure_image(
    tree: Path,
    *,
    docker: str | None = None,
    rebuild: bool = False,
    remaining_s: float | None = None,
    constraints: str | None = None,
) -> ContainerImage:
    """Build (or reuse) the image for ``tree``; raise BootstrapFailed with the
    build log's tail when the environment cannot be constructed.

    ``remaining_s`` is the verification budget still unspent when the backend is
    selected; the build may not outlast it.
    """
    binary = docker or docker_executable()
    if binary is None:
        raise BootstrapFailed("docker is not installed on this host")
    version, _reason = project_python(tree)
    roots = discover_roots(tree)
    scm_version = scm_pretend_version(tree, roots)
    pins = constraints if constraints is not None else era_constraints()
    text = dockerfile(version, roots, scm_version, constraints=pins)
    # the pins are digested as well as the Dockerfile: the `COPY` line is the
    # same text for every constraint file, so two different files would
    # otherwise share one tag and the second would silently reuse the first
    tag = (
        "attest-repro:"
        + hashlib.sha256(
            f"{version}\n{manifest_digest(tree, roots)}\n{text}\n{pins or ''}".encode()
        ).hexdigest()[:16]
    )
    existing = resolve_image(tag, docker=binary)
    if existing and not rebuild:
        # addressed by id from here on: the tag was only ever the cache key
        return ContainerImage(existing, existing, tag, cached=True)
    build_started = time.monotonic()
    timeout_s = build_timeout(remaining_s)
    if timeout_s <= 0:
        raise _bootstrap_failure(
            version, roots, "no verification budget remained for an image build"
        )
    with tempfile.TemporaryDirectory(prefix="attest-image-") as context:
        context_dir = Path(context)
        try:
            # ``text`` is what the tag digests; writing it (rather than a
            # second ``dockerfile()`` call) keeps the two from ever diverging
            (context_dir / "Dockerfile").write_text(text, encoding="utf-8")
            if pins is not None:
                (context_dir / "constraints.txt").write_text(pins, encoding="utf-8")
            shutil.copytree(
                tree,
                context_dir / "tree",
                ignore=shutil.ignore_patterns(*_SKIP),
                symlinks=False,
            )
        except OSError as exc:
            # a dangling symlink raises shutil.Error (an OSError) at the end of
            # the copy, and a full or unwritable /tmp raises here too: assembling
            # the context is part of the bootstrap, so it fails like the rest of it
            raise _bootstrap_failure(
                version, roots, f"build context could not be assembled: {exc}"
            ) from exc
        try:
            build = subprocess.run(
                [
                    binary,
                    "build",
                    "--quiet",
                    "--tag",
                    tag,
                    "--file",
                    str(context_dir / "Dockerfile"),
                    str(context_dir),
                ],
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except subprocess.TimeoutExpired as exc:
            # a build that never returns is a bootstrap failure like any other:
            # the operator-facing contract is "environment bootstrap failed …"
            # in the run status, never a traceback out of backend selection.
            # The tail names the step that was still running, which is the
            # difference between "raise the cap" and "this will never install"
            raise _bootstrap_failure(
                version,
                roots,
                f"the image build timed out after {timeout_s:g} s: "
                f"{_log_tail(exc.stderr or exc.stdout)}",
            ) from exc
    if build.returncode != 0:
        raise _bootstrap_failure(version, roots, _log_tail(build.stderr or build.stdout))
    digest = resolve_image(tag, docker=binary)
    if not digest:
        raise BootstrapFailed(
            f"environment bootstrap failed: image {tag} has no digest after build"
        )
    return ContainerImage(
        digest, digest, tag, cached=False, build_elapsed_s=time.monotonic() - build_started
    )
