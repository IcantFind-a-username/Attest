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
from dataclasses import dataclass
from pathlib import Path

from attest.execution.container_adapter import ContainerImage, docker_executable, image_digest

AVAILABLE_PYTHONS = ("3.13", "3.12", "3.11", "3.10", "3.9")
FALLBACK_PYTHON = "3.9"
_CLASSIFIER_RE = re.compile(r"Programming Language :: Python :: 3\.(\d+)")
_MANIFESTS = ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt", "requirements-dev.txt")
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


def project_python(tree: Path) -> tuple[str, str]:
    """(python minor version, reason) by the project's own classifiers."""
    declared: list[int] = []
    for root in discover_roots(tree):
        for name in ("setup.py", "setup.cfg", "pyproject.toml"):
            path = tree / root.relative / name if root.relative else tree / name
            if path.is_file():
                try:
                    text = path.read_text(errors="replace")
                except OSError:
                    continue
                declared.extend(int(m) for m in _CLASSIFIER_RE.findall(text))
    if declared:
        newest = max(declared)
        for version in AVAILABLE_PYTHONS:
            if int(version.split(".")[1]) <= newest:
                return version, f"classifiers up to 3.{newest}"
        return FALLBACK_PYTHON, f"classifiers up to 3.{newest}; fallback"
    return FALLBACK_PYTHON, "no classifiers; era fallback"


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


def dockerfile(python_version: str, roots: list[ProjectRoot]) -> str:
    lines = [
        f"FROM python:{python_version}-slim",
        "ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1",
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
            lines.append(f"RUN pip install {directory}")
    lines.append("RUN rm -rf /attest/build")
    return "\n".join(lines) + "\n"


def ensure_image(tree: Path, *, docker: str | None = None, rebuild: bool = False) -> ContainerImage:
    """Build (or reuse) the image for ``tree``; raise BootstrapFailed with the
    build log's tail when the environment cannot be constructed."""
    binary = docker or docker_executable()
    if binary is None:
        raise BootstrapFailed("docker is not installed on this host")
    version, _reason = project_python(tree)
    roots = discover_roots(tree)
    tag = (
        "attest-repro:"
        + hashlib.sha256(
            f"{version}\n{manifest_digest(tree, roots)}\n{dockerfile(version, roots)}".encode()
        ).hexdigest()[:16]
    )
    existing = image_digest(tag, docker=binary)
    if existing and not rebuild:
        return ContainerImage(tag, existing)
    with tempfile.TemporaryDirectory(prefix="attest-image-") as context:
        context_dir = Path(context)
        (context_dir / "Dockerfile").write_text(dockerfile(version, roots), encoding="utf-8")
        shutil.copytree(
            tree,
            context_dir / "tree",
            ignore=shutil.ignore_patterns(*_SKIP),
            symlinks=False,
        )
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
            timeout=1800,
        )
    if build.returncode != 0:
        tail = (build.stderr or build.stdout)[-1200:]
        raise BootstrapFailed(
            f"environment bootstrap failed (python {version}, roots "
            f"{[root.relative or '.' for root in roots]}): {tail}"
        )
    digest = image_digest(tag, docker=binary)
    if not digest:
        raise BootstrapFailed(
            f"environment bootstrap failed: image {tag} has no digest after build"
        )
    return ContainerImage(tag, digest)
