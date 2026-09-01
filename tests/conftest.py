"""Fixtures for isolated test-owned benchmark authority roots."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import pytest

from attest.review.budget import Budget
from attest.review.candidates import StoredCandidate
from attest.review.config import load_pricing
from attest.review.executor import ExecutorLimits, VerificationRun, verify_candidate
from attest.review.gate import GateResult
from attest.review.proposer import Provider

VerifyWithDefaults = Callable[..., VerificationRun]


@pytest.fixture
def verify_with_defaults() -> VerifyWithDefaults:
    """Verify a candidate with the production defaults used by executor tests."""

    def run(
        repo: Path,
        stored: StoredCandidate,
        gate: GateResult,
        provider: Provider,
        *,
        base_sha: str,
        head_sha: str,
    ) -> VerificationRun:
        pricing = load_pricing()
        return verify_candidate(
            repo,
            stored,
            gate,
            provider,
            Budget(limit_usd=1.0, model=str(pricing["default_model"])),
            ExecutorLimits(),
            base_sha=base_sha,
            head_sha=head_sha,
        )

    return run


@pytest.fixture
def comparison_cli_authority(tmp_path: Path) -> tuple[Path, str]:
    """Create stable owner inputs outside a compare command's output tree."""

    authority_root = tmp_path / "comparison-owner"
    run_identity = hashlib.sha256(str(authority_root).encode("utf-8")).hexdigest()
    return authority_root, run_identity
