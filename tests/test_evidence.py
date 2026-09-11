"""V-01: an accepted receipt verifies offline from its bundle, and any flipped byte rejects."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

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
    _payload,
    github_server,
    planted_repo,
)

WORKING_REPRO = (
    "import runpy\n\n"
    "def test_average_handles_empty_input():\n"
    "    average = runpy.run_path('app.py')['average']\n"
    "    assert average([]) == 0\n"
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


# --- owner authorisation 2 of 2026-09-12: the receipt body is versioned -------


def _certification_bundle(repo: Path) -> Path:
    rows = [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    certification = next(row for row in rows if row["kind"] == "certification")
    return Path(str(certification["bundle_path"]))


def test_a_bundle_written_under_body_v1_still_verifies_offline(
    planted_repo: tuple[Path, str, str],  # noqa: F811 - fixture re-exported above
    github_server: RecordingGitHub,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED, owner authorisation 2 of 2026-09-12. Every bundle sealed before
    this change was digested over the v1 field set and its `receipt.json`
    carries neither `body_version` nor `contained_attempts`. Such a bundle is
    written here by the writer pinned to v1 -- byte-for-byte the pre-change
    shape -- and must verify under the versioned verifier, with the digest it
    was sealed with (INV-VERSION-001, the D-124 failure this exists to avoid)."""
    from attest.certification.types import RECEIPT_BODY_V1
    from attest.review import certify as certify_module
    from attest.review.evidence import canonical_digest

    monkeypatch.setattr(certify_module, "RECEIPT_BODY_VERSION", RECEIPT_BODY_V1)
    repo, base_sha, head_sha = planted_repo
    result = run_ci(
        repo,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(probe_generation=False, k_samples=2, tier0_commands=[]),
        RecordingProvider(_finding_payload(), json.dumps({"test_body": WORKING_REPRO})),
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert result.surfaced_count == 1
    bundle = _certification_bundle(repo)
    raw = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))

    # the pre-change file shape: no body version, no contained attempts
    assert "body_version" not in raw and "contained_attempts" not in raw
    # and the pre-change digest formula -- everything in the file but the digest
    expected = canonical_digest({k: v for k, v in raw.items() if k != "provenance_digest"})
    assert raw["provenance_digest"] == expected
    assert isinstance(verify_bundle(bundle), AcceptedReceipt)


SPAWNING_APP = (
    "import subprocess\n"
    "import sys\n"
    "try:\n"
    "    subprocess.run([sys.executable, '-c', 'pass'], capture_output=True)\n"
    "except Exception:  # noqa: BLE001 - the package under review does exactly this\n"
    "    pass\n"
    "\n"
    "\n"
    "def total(items):\n"
    "    return sum(items)\n"
    "\n"
    "\n"
    "def average(items):\n"
    "    if not items:\n"
    "        return 0\n"
    "    return sum(items) / len(items)\n"
)
SPAWNING_APP_REGRESSED = SPAWNING_APP.replace("    if not items:\n        return 0\n", "")


@pytest.mark.skipif(os.name != "posix", reason="kernel process containment is POSIX-only")
def test_a_v2_bundle_carries_the_contained_attempts_under_its_digest(
    github_server: RecordingGitHub,  # noqa: F811
    tmp_path: Path,
) -> None:
    """RED, the other half: a receipt written today records body v2 and the
    creations the kernel refused across its runs, the digest covers them, the
    bundle verifies offline -- and a flipped byte inside that field rejects,
    which is what "under the digest" means."""
    import subprocess

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(tmp_path), *args], check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-b", "main")
    git("config", "user.email", "test@example.com")
    git("config", "user.name", "Test")
    (tmp_path / "app.py").write_text(SPAWNING_APP, encoding="utf-8")
    git("add", "app.py")
    git("commit", "-m", "base")
    base_sha = git("rev-parse", "HEAD")
    (tmp_path / "app.py").write_text(SPAWNING_APP_REGRESSED, encoding="utf-8")
    git("add", "app.py")
    git("commit", "-m", "regress average to divide by zero")
    head_sha = git("rev-parse", "HEAD")

    result = run_ci(
        tmp_path,
        _context(base_sha, head_sha),
        GitHubClient("local-token", github_server.url),
        ReviewConfig(
            probe_generation=False,
            k_samples=2,
            tier0_commands=[],
            contained_attempt_voids=False,
        ),
        RecordingProvider(
            _payload(
                {
                    "claim": "average() divides by zero when items is empty.",
                    "anchor": {"file": "app.py", "line": 14},
                    "failure_scenario": "average([]) raises ZeroDivisionError",
                    "falsification_plan": "call average([]) and require a safe empty result",
                }
            ),
            json.dumps({"test_body": WORKING_REPRO}),
        ),
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert result.surfaced_count == 1, result.deferred_reason
    bundle = _certification_bundle(tmp_path)
    raw = json.loads((bundle / "receipt.json").read_text(encoding="utf-8"))

    assert raw["body_version"] == "attest.receipt-body.v2"
    assert raw["contained_attempts"] and "subprocess" in raw["contained_attempts"][0].lower()
    assert isinstance(verify_bundle(bundle), AcceptedReceipt)

    # the field is under the digest: a flipped byte inside it rejects
    text = (bundle / "receipt.json").read_text(encoding="utf-8")
    position = text.index(raw["contained_attempts"][0][:8]) + 2
    copy = tmp_path / "mutant"
    shutil.copytree(bundle, copy)
    _flip(copy / "receipt.json", position)
    verdict = verify_bundle(copy)
    assert not isinstance(verdict, AcceptedReceipt)
    assert any("provenance digest" in reason for reason in verdict.reasons)  # type: ignore[union-attr]
