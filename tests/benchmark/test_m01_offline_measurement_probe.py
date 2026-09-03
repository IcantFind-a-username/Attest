"""Acceptance coverage for the versioned M-01 offline measurement probe."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from attest.benchmark.artifacts import canonical_json_bytes, sha256_bytes

ROOT = Path(__file__).parents[2]
# the interpreter running the gate, whatever it is: a hardcoded `.venv/bin/python`
# is a host assumption (AGENTS.md §13) and does not exist on a CI runner
PYTHON = Path(sys.executable)
PROBE = ROOT / "scripts" / "acceptance" / "m01_offline_measurement_probe.py"
CASSETTE = ROOT / "benchmarks" / "attest-v2" / "cassettes" / "m01-mixed-5-v1.json"
BASELINE = "0e58cd61a1a63c51a329d5c1a5509181be32adfa"
MARKER = "legacy_mixed_outcome_denominator"


def _run_command(
    source: Path, output: Path, repeat: int, cassette: Path = CASSETTE
) -> list[str]:
    return [
        str(PYTHON),
        "-I",
        "-B",
        str(PROBE),
        "run",
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


def _aggregate_command(source: Path, inputs: Path, output: Path) -> list[str]:
    return [
        str(PYTHON),
        "-I",
        "-B",
        str(PROBE),
        "aggregate",
        "--source-root",
        str(source),
        "--input-root",
        str(inputs),
        "--output",
        str(output),
        "--expected-repeats",
        "20",
    ]


def _environment(home: Path, **extra: str) -> dict[str, str]:
    home.mkdir(parents=True, exist_ok=True)
    return {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(home),
        "LC_ALL": "C",
        "PATH": os.environ["PATH"],
        "PYTHONDONTWRITEBYTECODE": "1",
        "TMPDIR": "/private/tmp",
        **extra,
    }


@pytest.fixture(scope="module")
def current_bundle(
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[Path, dict[str, str], tuple[dict[str, object], ...], dict[str, object]]:
    root = tmp_path_factory.mktemp("m01-current")
    env = _environment(root.parent / "home")
    payloads = []
    for repeat in range(20):
        output = root / f"current-{repeat}.json"
        completed = subprocess.run(
            _run_command(ROOT, output, repeat), capture_output=True, text=True, env=env
        )
        assert (completed.returncode, completed.stdout, completed.stderr) == (0, "", "")
        raw = output.read_bytes()
        payload = json.loads(raw)
        assert raw == canonical_json_bytes(payload)
        payloads.append(payload)
    aggregate_output = root.parent / "aggregate.json"
    completed = subprocess.run(
        _aggregate_command(ROOT, root, aggregate_output),
        capture_output=True,
        text=True,
        env=env,
    )
    assert (completed.returncode, completed.stdout, completed.stderr) == (0, "", "")
    aggregate = json.loads(aggregate_output.read_bytes())
    return root, env, tuple(payloads), aggregate


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
            _run_command(source, output, 0),
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


def test_current_run_embeds_the_exact_unnormalized_measurement(
    current_bundle: tuple[
        Path, dict[str, str], tuple[dict[str, object], ...], dict[str, object]
    ],
) -> None:
    _, _, payloads, _ = current_bundle
    for repeat, payload in enumerate(payloads):
        measurement = payload["measurement"]
        assert isinstance(measurement, dict)
        assert "report" not in payload
        assert measurement["repeat"] == repeat
        assert payload["repeat"] == repeat
        assert measurement["candidate_count"] == 5
        # since C-05 the four same-defect findings publish once; the other three
        # and the deferred candidate are unresolved
        assert measurement["published_count"] == 1
        assert measurement["unresolved_count"] == 4
    guards = payloads[0]["guards"]
    assert isinstance(guards, dict)
    assert isinstance(guards["platform_environment_removed"], bool)
    assert guards == {
        "delivery_transport": "loopback_http",
        "environment_allowlist": True,
        "entry_environment_variable_names": sorted(
            {
                "GIT_CONFIG_GLOBAL",
                "GIT_CONFIG_NOSYSTEM",
                "HOME",
                "LC_ALL",
                "PATH",
                "PYTHONDONTWRITEBYTECODE",
                "TMPDIR",
            }
        ),
        "paid_provider_calls": 0,
        "platform_environment_removed": guards["platform_environment_removed"],
        "provider_transport": "in_process_frozen_cassette",
        "python_external_connect_attempts": 0,
    }


def test_aggregate_uses_twenty_real_measurements_and_authoritative_reducer(
    current_bundle: tuple[
        Path, dict[str, str], tuple[dict[str, object], ...], dict[str, object]
    ],
) -> None:
    _, _, payloads, aggregate = current_bundle
    assert aggregate["schema_version"] == "attest.m01-offline-aggregate.v1"
    assert aggregate["expected_repeats"] == 20
    assert aggregate["semantic_n"] == 1
    assert aggregate["operational_repeats"] == 20
    assert aggregate["candidate_count"] == 5
    assert aggregate["published"] == 1
    assert aggregate["unresolved"] == 4
    assert aggregate["partially_deferred"] == 1
    assert aggregate["isolation_count"] == 20
    assert {payload["repeat"] for payload in payloads} == set(range(20))
    assert len({payload["semantic_digest"] for payload in payloads}) == 1
    assert aggregate["semantic_digest"] == payloads[0]["semantic_digest"]
    assert aggregate["run_outputs_sha256"] == {
        f"current-{repeat}.json": sha256_bytes(
            (current_bundle[0] / f"current-{repeat}.json").read_bytes()
        )
        for repeat in range(20)
    }


def test_baseline_has_only_the_named_legacy_denominator_red(
    baseline_result: tuple[subprocess.CompletedProcess[str], dict[str, object]],
) -> None:
    completed, payload = baseline_result
    assert completed.returncode == 1
    assert completed.stdout == ""
    assert completed.stderr == f"{MARKER}\n"
    assert payload["expected_failure"] == MARKER
    assert payload["source_sha"] == BASELINE
    observed = payload["observed"]
    assert isinstance(observed, dict)
    assert (observed["candidate_count"], observed["published"], observed["unresolved"]) == (
        5,
        4,
        1,
    )


@pytest.mark.parametrize("name", ("AWS_ACCESS_KEY_ID", "SSH_AUTH_SOCK"))
def test_unexpected_environment_is_rc2_without_output(tmp_path: Path, name: str) -> None:
    output = tmp_path / "rejected.json"
    completed = subprocess.run(
        _run_command(ROOT, output, 0),
        capture_output=True,
        text=True,
        env=_environment(tmp_path / "home", **{name: "not-read"}),
    )
    assert completed.returncode == 2
    assert MARKER not in completed.stderr
    assert name in completed.stderr
    assert not output.exists()


def test_fixture_integrity_failure_is_not_the_named_red(tmp_path: Path) -> None:
    cassette = tmp_path / CASSETTE.name
    cassette.write_bytes(
        CASSETTE.read_bytes().replace(b'"input_tokens": 23', b'"input_tokens": 24')
    )
    digest = sha256_bytes(cassette.read_bytes())
    (tmp_path / "SHA256SUMS").write_text(f"{digest}  {cassette.name}\n", encoding="ascii")
    completed = subprocess.run(
        _run_command(ROOT, tmp_path / "unexpected.json", 0, cassette),
        capture_output=True,
        text=True,
        env=_environment(tmp_path / "home"),
    )
    assert completed.returncode == 2
    assert MARKER not in completed.stderr
    assert "token count mismatch" in completed.stderr


def test_run_refuses_to_replace_an_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "occupied.json"
    original = b'{"occupied":true}\n'
    output.write_bytes(original)
    completed = subprocess.run(
        _run_command(ROOT, output, 0),
        capture_output=True,
        text=True,
        env=_environment(tmp_path / "home"),
    )
    assert completed.returncode == 2
    assert output.read_bytes() == original


def test_aggregate_refuses_to_replace_an_existing_output(
    tmp_path: Path,
    current_bundle: tuple[
        Path, dict[str, str], tuple[dict[str, object], ...], dict[str, object]
    ],
) -> None:
    inputs, env, _, _ = current_bundle
    output = tmp_path / "occupied.json"
    original = b'{"occupied":true}\n'
    output.write_bytes(original)
    completed = subprocess.run(
        _aggregate_command(ROOT, inputs, output), capture_output=True, text=True, env=env
    )
    assert completed.returncode == 2
    assert output.read_bytes() == original
