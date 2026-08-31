"""Fixtures for isolated test-owned benchmark authority roots."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


@pytest.fixture
def comparison_cli_authority(tmp_path: Path) -> tuple[Path, str]:
    """Create stable owner inputs outside a compare command's output tree."""

    authority_root = tmp_path / "comparison-owner"
    run_identity = hashlib.sha256(str(authority_root).encode("utf-8")).hexdigest()
    return authority_root, run_identity
