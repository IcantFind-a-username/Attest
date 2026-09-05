"""`G-NULL-001a`'s revised stop rule (D-141).

A control that publishes stops the run unless an **independent probe** -- no
product code, at least two Python versions -- has adjudicated it a real defect.
The rule is small and it decides whether paid runs continue, so it is tested
rather than trusted: three of these fail on the previous implementation, which
had no adjudication at all and stopped on every publication.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "scripts" / "corpus" / "null_study.py"

PUBLISHED = "f4f2cfec9d1af6780012a5021e46c191d14148e0"  # the adjudicated control
UNKNOWN = "0" * 40


@pytest.fixture(scope="module")
def null_study() -> ModuleType:
    """The driver, imported by path: `scripts/` is not an installed package."""

    sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
    spec = importlib.util.spec_from_file_location("null_study_under_test", DRIVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_unadjudicated_publication_stops_the_run(null_study: ModuleType) -> None:
    stop, line = null_study.stop_decision(UNKNOWN)
    assert stop is True
    assert "RISK-CERT-01" in line


def test_an_adjudicated_true_positive_continues_the_run(null_study: ModuleType) -> None:
    stop, line = null_study.stop_decision(PUBLISHED)
    assert stop is False
    assert "true_positive_on_control" in line
    assert "divide-probe" in line


def test_a_probe_on_one_interpreter_is_not_an_adjudication(
    null_study: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two interpreters is the rule's content, not decoration: this control's
    defect is invisible on 3.11 and present on 3.12."""

    thin = dict(null_study.ADJUDICATED[PUBLISHED])
    thin["interpreters"] = ["3.12.2"]
    monkeypatch.setitem(null_study.ADJUDICATED, PUBLISHED, thin)
    assert null_study.adjudication(PUBLISHED) is None
    assert null_study.stop_decision(PUBLISHED)[0] is True


def test_a_verdict_that_is_not_a_true_positive_is_not_a_pass(
    null_study: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    refuted = dict(null_study.ADJUDICATED[PUBLISHED])
    refuted["verdict"] = "probe_showed_no_defect"
    monkeypatch.setitem(null_study.ADJUDICATED, PUBLISHED, refuted)
    assert null_study.stop_decision(PUBLISHED)[0] is True


def _log(blocks: list[tuple[str, int]]) -> str:
    out = []
    for sha, published in blocks:
        out.append(f"=== gn {sha} more-itertools age=2441.5d subject\n")
        out.append(
            "  read 1 of 1 units; candidates: 4; eligible: 4; reproductions attempted: 4; "
            f"certified: {published}; published: {published}\n"
        )
        out.append("spend $0.2442 of $1.00 budget\n[rc 0]\n")
    return "".join(out)


def _manifest(tmp_path: Path, shas: list[str]) -> Path:
    path = tmp_path / "population.json"
    path.write_text(
        json.dumps(
            {
                "seed": "test",
                "controls": [
                    {"sha": sha, "qualified": True, "age_days": 2441.5, "base": "x"} for sha in shas
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def _table(
    null_study: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    blocks: list[tuple[str, int]],
) -> dict[str, Any]:
    manifest = _manifest(tmp_path, [sha for sha, _ in blocks])
    monkeypatch.setattr(null_study, "MANIFEST_INDEPENDENT", manifest)
    log = tmp_path / "run.log"
    log.write_text(_log(blocks), encoding="utf-8")
    out = tmp_path / "result.json"
    null_study.cmd_table(
        argparse.Namespace(independent=True, log=str(log), json=out),
    )
    return json.loads(out.read_text(encoding="utf-8"))


def test_the_table_counts_an_adjudicated_publication_apart_from_a_wrong_one(
    null_study: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    payload = _table(null_study, monkeypatch, tmp_path, [(PUBLISHED, 1), (UNKNOWN, 1)])
    assert payload["publications"] == 2
    assert payload["true_positive_on_control"] == 1
    assert payload["wrong_publications"] == 1
    # A wrong publication is observed, so there is no zero-error bound at all.
    assert payload["wrong_publication_bound_95"] is None


def test_a_run_whose_only_publication_is_adjudicated_still_has_a_bound(
    null_study: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    blocks = [(PUBLISHED, 1), (UNKNOWN, 0), ("1" * 40, 0)]
    payload = _table(null_study, monkeypatch, tmp_path, blocks)
    assert payload["wrong_publications"] == 0
    assert payload["answered_controls"] == 3
    assert payload["wrong_publication_bound_95"] == pytest.approx(1.0)
    assert payload["bound_denominator"] == "answered_controls"


def test_the_drivers_own_decision_lines_are_not_controls(
    null_study: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`STOP:`, `CONTINUE:` and `done` share the log's `=== gn ` prefix."""

    manifest = _manifest(tmp_path, [PUBLISHED])
    monkeypatch.setattr(null_study, "MANIFEST_INDEPENDENT", manifest)
    log = tmp_path / "run.log"
    log.write_text(
        _log([(PUBLISHED, 1)])
        + "=== gn CONTINUE: true_positive_on_control adjudicated\n"
        + "=== gn done\n",
        encoding="utf-8",
    )
    out = tmp_path / "result.json"
    null_study.cmd_table(argparse.Namespace(independent=True, log=str(log), json=out))
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert len(payload["rows"]) == 1
    assert payload["rows"][0]["sha"] == PUBLISHED[:10]
