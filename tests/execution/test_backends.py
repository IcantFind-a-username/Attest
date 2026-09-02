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
