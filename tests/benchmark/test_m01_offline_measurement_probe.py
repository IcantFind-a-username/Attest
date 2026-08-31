"""Acceptance coverage for the versioned M-01 offline measurement probe."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest

from attest.benchmark.artifacts import canonical_json_bytes

ROOT = Path(__file__).parents[2]
PROBE = ROOT / "scripts" / "acceptance" / "m01_offline_measurement_probe.py"
CASSETTE = ROOT / "benchmarks" / "attest-v2" / "cassettes" / "m01-mixed-5-v1.json"
BASELINE = "0e58cd61a1a63c51a329d5c1a5509181be32adfa"
MARKER = "legacy_mixed_outcome_denominator"


def _command(source: Path, output: Path, repeat: int, cassette: Path = CASSETTE) -> list[str]:
    return [
        str(ROOT / ".venv" / "bin" / "python"),
        "-I",
        "-B",
        str(PROBE),
        "--source-root",
        str(source),
        "--cassette",
        str(cassette),
        "--output",
        str(output),
        "--repeat",
        str(repeat),
        "--repeats",
        "1",
    ]


def _environment(home: Path) -> dict[str, str]:
    home.mkdir(parents=True, exist_ok=True)
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "HOME": str(home),
        "PATH": os.environ["PATH"],
        "PYTHONDONTWRITEBYTECODE": "1",
    }


@pytest.fixture(scope="module")
def current_repeats(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict[str, object], ...]:
    root = tmp_path_factory.mktemp("m01-current")
    env = _environment(root / "home")
    payloads = []
    for repeat in range(20):
        output = root / f"repeat-{repeat}.json"
        completed = subprocess.run(
            _command(ROOT, output, repeat), capture_output=True, text=True, env=env
        )
        assert (completed.returncode, completed.stdout, completed.stderr) == (0, "", "")
        raw = output.read_bytes()
        payload = json.loads(raw)
        assert raw == canonical_json_bytes(payload)
        payloads.append(payload)
    return tuple(payloads)


@pytest.fixture(scope="module")
def baseline_result(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[tuple[subprocess.CompletedProcess[str], dict[str, object]]]:
    root = tmp_path_factory.mktemp("m01-baseline")
    source = root / "source"
    subprocess.run(
        ["git", "worktree", "add", "--detach", str(source), BASELINE],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    try:
        output = root / "baseline.json"
        completed = subprocess.run(
            _command(source, output, 0),
            capture_output=True,
            text=True,
            env=_environment(root / "home"),
        )
        yield completed, json.loads(output.read_bytes())
    finally:
        subprocess.run(
            ["git", "worktree", "remove", "--force", str(source)],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )


def test_current_probe_reports_the_author_visible_denominator(
    current_repeats: tuple[dict[str, object], ...],
) -> None:
    payload = current_repeats[0]
    assert payload["schema_version"] == "attest.m01-offline-probe.v1"
    assert payload["repeat"] == 0
    assert payload["repeats"] == 1
    assert payload["candidate_count"] == 5
    assert payload["published"] == 4
    assert payload["unresolved"] == 1
    assert payload["partially_deferred"] == 1
    assert payload["task_status"] == "partially_deferred"
    assert payload["semantic_n"] == 1
    assert payload["operational_repeats"] == 1
    assert payload["guards"] == {
        "credential_variables_removed": 0,
        "credentials_available": False,
        "external_network": False,
        "local_only_provider": True,
        "loopback_delivery": True,
        "paid_provider_calls": 0,
        "remote_writes": 0,
        "resume": False,
    }
    rendered = json.dumps(payload, sort_keys=True)
    assert "/private/" not in rendered
    assert not {"elapsed_s", "latency_s", "wall_clock"} & set(payload)


def test_twenty_processes_are_operational_repeats_of_one_semantic_unit(
    current_repeats: tuple[dict[str, object], ...],
) -> None:
    assert {payload["repeat"] for payload in current_repeats} == set(range(20))
    assert {payload["repeats"] for payload in current_repeats} == {1}
    assert len({payload["isolation_sha256"] for payload in current_repeats}) == 20
    assert len({payload["semantic_digest"] for payload in current_repeats}) == 1
    assert len({payload["cassette_sha256"] for payload in current_repeats}) == 1
    assert len({payload["probe_sha256"] for payload in current_repeats}) == 1
    assert len({payload["input_sha256"] for payload in current_repeats}) == 1
    assert sum(cast(int, payload["operational_repeats"]) for payload in current_repeats) == 20
    assert max(cast(int, payload["semantic_n"]) for payload in current_repeats) == 1


def test_baseline_has_only_the_named_legacy_denominator_red(
    baseline_result: tuple[subprocess.CompletedProcess[str], dict[str, object]],
) -> None:
    completed, payload = baseline_result
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == f"{MARKER}\n"
    assert payload["expected_failure"] == MARKER
    assert payload["source_sha"] == BASELINE
    assert (payload["candidate_count"], payload["published"], payload["unresolved"]) == (
        5,
        4,
        1,
    )


def test_fixture_integrity_failure_is_not_the_named_red(tmp_path: Path) -> None:
    cassette = tmp_path / CASSETTE.name
    cassette.write_bytes(
        CASSETTE.read_bytes().replace(b'"input_tokens": 23', b'"input_tokens": 24')
    )
    digest = hashlib.sha256(cassette.read_bytes()).hexdigest()
    (tmp_path / "SHA256SUMS").write_text(f"{digest}  {cassette.name}\n", encoding="ascii")
    completed = subprocess.run(
        _command(ROOT, tmp_path / "unexpected.json", 0, cassette),
        capture_output=True,
        text=True,
        env=_environment(tmp_path / "home"),
    )
    assert completed.returncode == 2
    assert MARKER not in completed.stderr
    assert "token count mismatch" in completed.stderr
