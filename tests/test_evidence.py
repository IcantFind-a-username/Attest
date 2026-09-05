"""V-01: an accepted receipt verifies offline from its bundle, and any flipped byte rejects."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from attest.certification.types import AcceptedReceipt
from attest.github.client import GitHubClient
from attest.review.ci import run_ci
from attest.review.config import ReviewConfig

# D-146: every `ReviewConfig` here pins `probe_generation=False`. These tests
# supply the exact reproduction they want executed, because what they test is the
# differential, the certification kernel and the publication policy -- not how the
# test was written. The product's default path, probe + record/replay, is exercised
# end to end in `tests/test_probe_generation.py`.
from attest.review.evidence import verify_bundle
from attest.review.executor import ExecutorLimits
from test_ci_flow import (  # noqa: F401 - fixtures are re-exported into this module
    RecordingGitHub,
    RecordingProvider,
    _context,
    _finding_payload,
    github_server,
    planted_repo,
)


def _flip(path: Path, position: int) -> None:
    data = bytearray(path.read_bytes())
    data[position] = (data[position] + 1) % 256
    path.write_bytes(bytes(data))


def test_accepted_receipt_verifies_offline_and_any_flipped_byte_rejects(
    planted_repo: tuple[Path, str, str],  # noqa: F811 - fixture re-exported above
    github_server: RecordingGitHub,  # noqa: F811
    tmp_path: Path,
) -> None:
    repo, base_sha, head_sha = planted_repo
    provider = RecordingProvider(
        _finding_payload(),
        json.dumps(
            {
                "test_body": "import runpy\n\n"
                "def test_average_handles_empty_input():\n"
                "    average = runpy.run_path('app.py')['average']\n"
                "    assert average([]) == 0\n"
            }
        ),
    )
    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(probe_generation=False, k_samples=2, tier0_commands=[]),
        provider,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert result.surfaced_count == 1
    rows = [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    certification = next(row for row in rows if row["kind"] == "certification")
    bundle = Path(str(certification["bundle_path"]))
    assert bundle.is_dir()
    assert isinstance(verify_bundle(bundle), AcceptedReceipt)
    receipt = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))
    assert receipt["test_node"] == "test_repro.py::test_average_handles_empty_input"
    assert all(run["collected_count"] == 1 for run in receipt["head_runs"] + receipt["base_runs"])

    # flip bytes across the receipt, the test source, and a run artifact: each
    # mutated copy of the bundle must be rejected by the offline verifier
    targets = [
        ("receipt.json", range(0, len((bundle / "receipt.json").read_bytes()), 53)),
        ("test_repro.py", [0, 20]),
        ("runs/head-1/stdout.txt", [0]),
        ("runs/base-1/run.json", [40]),
    ]
    mutations = 0
    for relative, positions in targets:
        for position in positions:
            copy = tmp_path / f"mutant-{mutations}"
            shutil.copytree(bundle, copy)
            _flip(copy / relative, position)
            verdict = verify_bundle(copy)
            assert not isinstance(verdict, AcceptedReceipt), (relative, position, verdict)
            mutations += 1
    assert mutations >= 10
