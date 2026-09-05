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
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from attest.execution.container_adapter import (
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


def scm_pretend_version(tree: Path, roots: list[ProjectRoot]) -> str | None:
    """For a project that versions itself with setuptools_scm: the version its
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
                if "setuptools_scm" in text or "setuptools-scm" in text:
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
        if found:
            return found.group(1)
    return "0.0.1"


def dockerfile(
    python_version: str, roots: list[ProjectRoot], scm_version: str | None = None
) -> str:
    lines = [
        f"FROM python:{python_version}-slim",
        "ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1",
    ]
    if scm_version:
        # setuptools_scm cannot see a repository inside the build context
        lines.append(f"ENV SETUPTOOLS_SCM_PRETEND_VERSION={scm_version}")
    lines += [
        "RUN pip install pytest",
        "COPY tree /attest/build",
    ]
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
            else:
                lines.append(f"RUN pip install {directory}")
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


def ensure_image(
    tree: Path,
    *,
    docker: str | None = None,
    rebuild: bool = False,
    remaining_s: float | None = None,
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
    text = dockerfile(version, roots, scm_version)
    tag = (
        "attest-repro:"
        + hashlib.sha256(f"{version}\n{manifest_digest(tree, roots)}\n{text}".encode()).hexdigest()[
            :16
        ]
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
