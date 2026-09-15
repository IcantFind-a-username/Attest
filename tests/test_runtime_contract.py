"""Exercise original pytest fixtures and the shadow interpreter, including damaged records."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/corpus"))

import runtime_contract_shadow as shadow  # noqa: E402
from binding_cases import _git  # noqa: E402
from runtime_contract_cases import PARAMETER_NAMES, build_case  # noqa: E402

from attest.execution.backends import BackendSelection  # noqa: E402
from attest.execution.local_adapter import LocalDevelopmentAdapter  # noqa: E402
from attest.review.contract_runtime import (  # noqa: E402
    PREFIX,
    RuntimeSite,
    interpret_pair,
    read_observation,
)
from attest.review.executor import ExecutionResult  # noqa: E402


@pytest.fixture(scope="module")
def observations(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    # Test-owned inputs on the existing development adapter; the acceptance driver
    # separately uses the real container boundary without this adapter override.
    work = tmp_path_factory.mktemp("runtime-contract")
    adapter = LocalDevelopmentAdapter()
    rows = {}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            shadow,
            "select_backend",
            lambda *_a, **_k: BackendSelection(adapter, adapter.profile, "test-owned fixture"),
        )
        for name in ("cache_clear_fixture", "module_autouse", "receiver_fixture", *PARAMETER_NAMES):
            repo, base, head, _ = build_case(name, work / "fixtures")
            rows[name] = shadow.measure(name, repo, base, head, work / name)
        for before, after, expected in (("True", "1", "bool"), ("1", "1.0", "int")):
            name = "type-" + expected
            repo, _, _, _ = build_case("legal_contract", work / name)
            (repo / "geo.py").write_text("def parse(value):\n    return type(value).__name__\n")
            test = "from geo import parse\nVALUE = {}\ndef test_parse():\n"
            test += '    assert parse(VALUE) == "' + expected + '"\n'
            (repo / "tests/test_geo.py").write_text(test.format(before))
            _git(repo, "add", "--all")
            _git(repo, "commit", "-m", "type-sensitive base")
            base = _git(repo, "rev-parse", "HEAD")
            (repo / "geo.py").write_text(
                'def parse(value):\n    return type(value).__name__ + ""\n'
            )
            (repo / "tests/test_geo.py").write_text(test.format(after))
            _git(repo, "commit", "-am", "change test input with equivalent implementation")
            head = _git(repo, "rev-parse", "HEAD")
            rows[name] = shadow.measure(name, repo, base, head, work / (name + "-runs"))
    return rows


@pytest.mark.parametrize(
    ("name", "status"),
    [
        ("cache_clear_fixture", "binding_observed"),
        ("receiver_fixture", "binding_observed"),
        ("module_autouse", "defer"),
    ],
)
def test_original_fixture_context_and_actual_callable_are_observed(
    observations: dict[str, Any],
    name: str,
    status: str,
) -> None:
    sites = observations[name]["sites"]
    assert len(sites) == 1
    site = sites[0]
    assert site["verdict"]["status"] == status, site["verdict"]
    assert site["verdict"]["receipt_eligible"] is False
    assert all(run["collected_count"] == 1 for run in site["runs"].values())
    if name == "module_autouse":
        assert "actual callable" in site["verdict"]["reason"]
    elif name == "receiver_fixture":
        event = site["verdict"]["observations"][0]
        assert event["receiver"]["state"] == {
            "kind": "dict",
            "items": [
                ["width", {"kind": "int", "value": 2}],
                ["cache", {"kind": "dict", "items": []}],
            ],
        }
        assert event["callee"]["qualname"] == "Grid.cell"
    else:
        event = site["verdict"]["observations"][0]
        assert event["args"]["items"] == [{"kind": "str", "value": "1,2"}]
        assert event["expected"]["items"] == [
            {"kind": "int", "value": 1},
            {"kind": "int", "value": 2},
        ]


@pytest.mark.parametrize(
    "damage",
    ["missing", "duplicate", "site", "authority", "callee", "fields", "null_fields"],
)
def test_damaged_runtime_packets_do_not_supply_binding(
    observations: dict[str, Any],
    damage: str,
) -> None:
    row = observations["cache_clear_fixture"]["sites"][0]
    site = RuntimeSite(**row["base_site"])
    run = ExecutionResult(**row["runs"]["base-observed"])
    raw = next(line[len(PREFIX) :] for line in run.stdout.splitlines() if line.startswith(PREFIX))
    packet = json.loads(raw)
    if damage == "site":
        packet["events"][0]["site"] = "another site"
    elif damage == "authority":
        packet["receipt_eligible"] = True
    elif damage == "callee":
        packet["events"][0]["callee"]["file"] = "substitute.py"
    elif damage == "fields":
        del packet["events"][0]["args"]
    elif damage == "null_fields":
        for field in ("args", "kwargs", "receiver", "expected", "returned", "left"):
            packet["events"][0][field] = None
    stdout = PREFIX + json.dumps(packet)
    if damage == "missing":
        stdout = ""
    elif damage == "duplicate":
        stdout += "\n" + stdout
    event, reason = read_observation(replace(run, stdout=stdout), site)
    assert event is None and reason


@pytest.mark.parametrize(
    "damage", ["test_bytes", "node_identity", "overlay_outcome", "environment"]
)
def test_pair_consistency_is_checked_outside_the_recorder(
    observations: dict[str, Any],
    damage: str,
) -> None:
    row = observations["cache_clear_fixture"]["sites"][0]
    base, head = RuntimeSite(**row["base_site"]), RuntimeSite(**row["head_site"])
    runs = {label: ExecutionResult(**run) for label, run in row["runs"].items()}
    digests = {label: run.test_file_digest for label, run in runs.items()}
    run = runs["head-observed"]
    if damage == "test_bytes":
        run = replace(run, test_file_digest="0" * 64)
    elif damage == "node_identity":
        run = replace(run, junit_xml=run.junit_xml.replace("tests.test_geo", "different.test_geo"))
    elif damage == "overlay_outcome":
        run = replace(run, exit_code=0)
    else:
        run = replace(run, environment_digest="0" * 64)
    runs["head-observed"] = run
    result = interpret_pair(base, head, runs, digests=digests)
    assert result["status"] == "defer", result
    assert result["receipt_eligible"] is False


@pytest.mark.parametrize("name", PARAMETER_NAMES)
def test_parameter_rows_bind_by_identity_and_keep_all_outcomes(
    observations: dict[str, Any], name: str,
) -> None:
    result = observations[name]["sites"][0]["verdict"]
    positive = name in ("parameter_regression", "parameter_reordered")
    assert result["status"] == ("binding_observed" if positive else "defer"), result
    assert result["receipt_eligible"] is False
    if positive:
        nodes = result["nodes"]
        assert len(nodes) == 2
        assert [n["node"].split("[")[-1] for n in nodes] == ["first]", "second]"]
        assert [n["status"] for n in nodes] == ["binding_observed", "defer"]
        assert all(n["receipt_eligible"] is False for n in nodes)


@pytest.mark.parametrize("name", ["type-bool", "type-int"])
def test_changed_input_types_do_not_look_like_implementation_regressions(
    observations: dict[str, Any],
    name: str,
) -> None:
    result = observations[name]["sites"][0]["verdict"]
    assert result["status"] == "defer", result
    assert "input" in result["reason"]
    assert result["receipt_eligible"] is False
