"""Backend selection (X-02): which adapter runs untrusted head code.

``linux-container-v1`` is the production profile; ``local_development_best_effort``
is selectable only by the local ``attest review`` when the operator asks for it or
when the container backend is unavailable on a development host. ``attest ci``
never falls back: a missing container backend is a DEFER with the reason.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from attest.execution.container_adapter import (
    CONTAINER_PROFILE,
    ContainerAdapter,
    docker_executable,
)
from attest.execution.container_images import BootstrapFailed, ensure_image
from attest.execution.controller import ExecutorAdapter
from attest.execution.local_adapter import LocalDevelopmentAdapter
from attest.execution.types import LOCAL_DEVELOPMENT_PROFILE

EXECUTOR_ENV = "ATTEST_EXECUTOR"  # "container" | "local"; the operator's local override


@dataclass(frozen=True)
class BackendSelection:
    adapter: ExecutorAdapter | None
    profile: str
    reason: str  # why this backend, or why none


def requested_backend(default: str) -> str:
    value = os.environ.get(EXECUTOR_ENV, "").strip().lower()
    return value if value in {"container", "local"} else default


def select_backend(
    tree: Path, *, production: bool, remaining_s: float | None = None
) -> BackendSelection:
    """The adapter for one task's head tree.

    Production (``attest ci``) accepts only the container backend and DEFERs
    without it. A local review defaults to the container when docker is
    present and falls back to the development adapter otherwise, or when
    ``ATTEST_EXECUTOR=local`` asks for it explicitly.

    ``remaining_s`` is the caller's unspent verification budget: an image build
    may not outlast the deadline the candidates it serves run under.
    """
    wanted = "container" if production else requested_backend("container")
    if wanted == "local":
        if production:
            return BackendSelection(
                None, CONTAINER_PROFILE, "production never uses the host adapter"
            )
        return BackendSelection(
            LocalDevelopmentAdapter(),
            LOCAL_DEVELOPMENT_PROFILE,
            "operator requested the host adapter",
        )
    if docker_executable() is None:
        if production:
            return BackendSelection(
                None, CONTAINER_PROFILE, "isolation backend unavailable: docker not found"
            )
        return BackendSelection(
            LocalDevelopmentAdapter(),
            LOCAL_DEVELOPMENT_PROFILE,
            "docker not found; development host adapter (no OS boundary)",
        )
    try:
        image = ensure_image(tree, remaining_s=remaining_s)
    except BootstrapFailed as exc:
        return BackendSelection(None, CONTAINER_PROFILE, str(exc))
    return BackendSelection(
        ContainerAdapter(image), CONTAINER_PROFILE, f"image {image.tag or image.reference}"
    )
