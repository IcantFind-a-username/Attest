"""V-03 (G-SEM-003): fresh writable state per run, sealed bundles, offline verifier."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from attest.certification.types import AcceptedReceipt
from attest.cli.main import main
from attest.execution.controller import Controller
from attest.execution.local_adapter import LocalDevelopmentAdapter
from attest.execution.provenance import KEY_RELATIVE, load_or_create_key, seal
from attest.execution.types import LOCAL_DEVELOPMENT_PROFILE, ResourceLimits
from attest.review.evidence import verify_bundle

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from attest.review.config import ReviewConfig  # noqa: E402
from attest.review.executor import ExecutorLimits  # noqa: E402
from attest.review.run import run_review  # noqa: E402
from test_review_run import PlantedProvider, _plant_regression  # noqa: E402

LIMITS = ResourceLimits(wall_timeout_s=20.0, cpu_timeout_s=10, memory_mb=512, output_bytes=4_096)


def _certified_bundle(tmp_path: Path) -> tuple[Path, Path]:
    repo, base_sha, _head = _plant_regression(tmp_path)
    review = run_review(
        repo,
        base_sha,
        ReviewConfig(probe_generation=False, k_samples=2, tier0_commands=[]),
        PlantedProvider(),
        verify=True,
        limits=ExecutorLimits(wall_timeout_s=20.0),
    )
    assert len(review.published) == 1, review.notes
    rows = [
        json.loads(line)
        for line in (repo / ".attest" / "ledger.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    row = next(
        r for r in rows if r.get("kind") == "certification" and r.get("outcome") == "accepted"
    )
    return repo, Path(str(row["bundle_path"]))


def test_a_run_started_on_stale_state_is_rejected_by_the_verifier(tmp_path: Path) -> None:
    """The V-03 RED: a receipt whose run record says the writable state was
    not fresh is rejected offline, whatever else the bundle proves."""
    repo, bundle = _certified_bundle(tmp_path)
    key = load_or_create_key(repo)
    assert isinstance(verify_bundle(bundle, key=key, require_seal=True), AcceptedReceipt)

    stale = tmp_path / "stale-bundle"
    shutil.copytree(bundle, stale)
    record_path = stale / "runs" / "head-1" / "run.json"
    record = json.loads(record_path.read_bytes())
    record["fresh_state"] = False
    record_path.write_bytes(
        json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    )
    verdict = verify_bundle(stale)
    assert not isinstance(verdict, AcceptedReceipt)
    assert any("fresh writable state" in reason for reason in verdict.reasons)


def test_the_controller_creates_an_empty_outputs_directory_and_names_stale_entries(
    tmp_path: Path,
) -> None:
    controller = Controller(tmp_path / "runs")
    leftover = tmp_path / "runs" / "head-1" / "outputs"
    leftover.mkdir(parents=True)
    (leftover / "junit.xml").write_text("<stale/>", encoding="utf-8")
    request = controller.issue(
        task_id="t",
        run_id="head-1",
        candidate_id="c",
        revision_sha="",
        profile=LOCAL_DEVELOPMENT_PROFILE,
        interpreter=sys.executable,
        argv_template=[sys.executable, "-c", "import os; print(os.listdir('{outputs}'))"],
        environment={"ATTEST_OUTPUTS": "{outputs}"},
        inputs={},
        limits=LIMITS,
        expected_artifacts=["stdout.txt"],
    )
    outcome = controller.dispatch(request, LocalDevelopmentAdapter(), tree=tmp_path, inputs={})
    assert outcome.accepted, outcome.reasons
    assert outcome.fresh_state is True
    assert outcome.stale_entries == ("junit.xml",)
    # the job saw an empty directory: the stale file was gone before it ran
    assert outcome.artifacts["stdout.txt"].strip() == b"[]"


def test_seal_copied_from_another_bundle_or_forged_is_rejected(tmp_path: Path) -> None:
    repo, bundle = _certified_bundle(tmp_path)
    key = load_or_create_key(repo)
    assert isinstance(verify_bundle(bundle, key=key, require_seal=True), AcceptedReceipt)
    # no key: the bundle still verifies structurally, but not when the seal is required
    unsealed = verify_bundle(bundle, require_seal=True)
    assert not isinstance(unsealed, AcceptedReceipt)
    assert any("no key supplied" in reason for reason in unsealed.reasons)
    # a seal made with another controller's key
    forged = tmp_path / "forged"
    shutil.copytree(bundle, forged)
    other = b"\x01" * 32
    manifest_digest = json.loads((forged / "seal.json").read_bytes())["manifest_digest"]
    receipt_digest = json.loads((forged / "receipt.json").read_bytes())["provenance_digest"]
    (forged / "seal.json").write_bytes(
        json.dumps(seal(manifest_digest, receipt_digest, other), sort_keys=True).encode()
    )
    verdict = verify_bundle(forged, key=key)
    assert not isinstance(verdict, AcceptedReceipt)
    assert any("different controller key" in reason for reason in verdict.reasons)
    # a seal that names another bundle
    replayed = tmp_path / "replayed"
    shutil.copytree(bundle, replayed)
    (replayed / "seal.json").write_bytes(
        json.dumps(seal("0" * 64, receipt_digest, key), sort_keys=True).encode()
    )
    verdict = verify_bundle(replayed, key=key)
    assert not isinstance(verdict, AcceptedReceipt)
    assert any("different bundle manifest" in reason for reason in verdict.reasons)


def test_attest_verify_checks_a_bundle_offline(tmp_path: Path, capsys) -> None:
    repo, bundle = _certified_bundle(tmp_path)
    assert (repo / KEY_RELATIVE).is_file()
    assert main(["--repo", str(repo), "verify", "--bundle", str(bundle), "--require-seal"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("accepted: receipt") and "seal verified" in out
    (bundle / "test_repro.py").write_bytes(b"def test_repro():\n    assert True\n")
    assert main(["--repo", str(repo), "verify", "--bundle", str(bundle)]) == 1
    assert "rejected:" in capsys.readouterr().out
    # the executor never receives the key: it is outside every mount
    assert not any(KEY_RELATIVE.name in str(p) for p in bundle.rglob("*"))


def test_key_file_is_private_and_stable(tmp_path: Path) -> None:
    first = load_or_create_key(tmp_path)
    second = load_or_create_key(tmp_path)
    assert first == second and len(first) == 32
    mode = (tmp_path / KEY_RELATIVE).stat().st_mode & 0o777
    assert mode == 0o600
    assert subprocess.run(["true"]).returncode == 0
