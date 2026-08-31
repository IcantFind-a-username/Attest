"""Repository-wide pytest fixtures shared by every test subtree."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def local_ruff_executable() -> Path:
    """Return the ruff binary paired with the interpreter running the Gate."""

    executable = Path(sys.executable).with_name("ruff")
    if not executable.is_file():
        pytest.skip("requires ruff in the active test environment")
    return executable
