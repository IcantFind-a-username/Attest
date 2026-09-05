"""D-124: the evidence bundle is about the test that actually ran, and
certification refuses anything it cannot itself verify offline.

Two REDs, one per half of the defect the 2026-09-04 handoff reported as a
published receipt whose bundle does not verify:

1. the D-114 collection loop may replace the generated test before any
   behavioural run is bought, and the bundle must carry *that* test's bytes;
2. whatever the reason, a bundle whose bytes disagree with the receipt buys no
   author-visible finding -- certification verifies its own output once and
   abstains when the pass fails.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from attest.certification.types import AcceptedReceipt
from attest.github.client import GitHubClient
from attest.review import certify as certify_module
from attest.review.ci import run_ci
from attest.review.config import ReviewConfig

# D-146: every `ReviewConfig` here pins `probe_generation=False`. These tests supply
# the exact reproduction they want executed; the product's default path, probe +
# record/replay, is exercised in `tests/test_probe_generation.py` and rehearsed by the
# release drills.
from attest.review.evidence import verify_bundle
from attest.review.executor import ExecutorLimits
from attest.review.proposer import ProviderResult
from test_ci_flow import (  # noqa: F401 - fixtures are re-exported into this module
    RecordingGitHub,
    RecordingProvider,
    _context,
    _finding_payload,
    github_server,
    planted_repo,
)

WORKING_REPRO = (
    "import runpy\n\n"
    "def test_average_handles_empty_input():\n"
    "    average = runpy.run_path('app.py')['average']\n"
    "    assert average([]) == 0\n"
)


class RegeneratingProvider:
    """One proposal, then a first reproduction that collects nothing and a
    second that works -- the shape that produced the unverifiable bundles."""

    def __init__(self, proposal: str, first_repro: str, second_repro: str) -> None:
        self.proposal = proposal
        self.repros = [first_repro, second_repro]
        self.repro_calls = 0

    def sample(
        self,
        system: str,
        prompt: str,
        schema: dict[str, object],
        max_tokens: int,
        *,
        timeout_s: float | None = None,
    ) -> ProviderResult:
        if "focused pytest reproduction" not in system:
            return ProviderResult(text=self.proposal, input_tokens=10, output_tokens=10)
        index = min(self.repro_calls, len(self.repros) - 1)
        self.repro_calls += 1
        return ProviderResult(text=self.repros[index], input_tokens=10, output_tokens=10)


def _certification_rows(repo: Path) -> list[dict[str, object]]:
    lines = (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    return [row for row in (json.loads(line) for line in lines) if row["kind"] == "certification"]


def test_a_regenerated_reproduction_puts_its_own_bytes_in_the_bundle(
    planted_repo: tuple[Path, str, str],  # noqa: F811 - fixture re-exported above
    github_server: RecordingGitHub,  # noqa: F811
) -> None:
    """RED 1(a): the first generated test never collects, the second does; the
    bundle's ``test_repro.py`` must be the second one's bytes, byte for byte,
    and therefore must equal ``receipt.test_digest``."""
    repo, base_sha, head_sha = planted_repo
    provider = RegeneratingProvider(
        _finding_payload(),
        json.dumps({"test_body": ""}),  # collects zero nodes -- the observed shape
        json.dumps({"test_body": WORKING_REPRO}),
    )
    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(probe_generation=False, k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert provider.repro_calls >= 2, "the collection loop did not regenerate"
    assert result.surfaced_count == 1
    row = next(row for row in _certification_rows(repo) if row["outcome"] == "accepted")
    bundle = Path(str(row["bundle_path"]))
    receipt = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))
    test_bytes = (bundle / "test_repro.py").read_bytes()
    assert test_bytes == WORKING_REPRO.encode("utf-8")
    assert hashlib.sha256(test_bytes).hexdigest() == receipt["test_digest"]
    assert isinstance(verify_bundle(bundle), AcceptedReceipt)


def test_a_bundle_that_does_not_verify_publishes_nothing(
    planted_repo: tuple[Path, str, str],  # noqa: F811
    github_server: RecordingGitHub,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED 1(b): with the wrong bytes forced into the bundle, the run abstains --
    no accepted certification, no author-visible finding, and the ledger says
    which self-check refused it."""
    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(_finding_payload(), json.dumps({"test_body": WORKING_REPRO}))

    real_write = certify_module.write_bundle

    def corrupting_write(root, **kwargs):  # type: ignore[no-untyped-def]
        return real_write(root, **{**kwargs, "test_bytes": b"# not the test that ran\n"})

    monkeypatch.setattr(certify_module, "write_bundle", corrupting_write)
    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(probe_generation=False, k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert result.surfaced_count == 0
    rows = _certification_rows(repo)
    assert not [row for row in rows if row["outcome"] == "accepted"]
    refused = next(row for row in rows if row["outcome"] == "rejected")
    assert refused["rejection_codes"] == ["bundle_self_verification_failed"]
    assert "test bytes do not match receipt.test_digest" in str(refused["reason"])
