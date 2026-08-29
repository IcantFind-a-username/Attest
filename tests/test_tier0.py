import json
from pathlib import Path
from types import SimpleNamespace

from attest.review import tier0
from attest.review.tier0 import Tier0Signal, collect_signals, run_ruff, signals_near


def _fake_run(stdout: str):
    def fake(cmd, **kwargs):
        return SimpleNamespace(stdout=stdout, returncode=0)

    return fake


def test_run_ruff_parses_diagnostics(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(tier0.shutil, "which", lambda name: "ruff")
    diags = [
        {"filename": "a.py", "location": {"row": 3}, "code": "F821", "message": "undefined name"},
        {"filename": "a.py", "location": {"row": 9}, "code": "E999", "message": "syntax error"},
        {"bogus": True},
    ]
    monkeypatch.setattr(tier0.subprocess, "run", _fake_run(json.dumps(diags)))
    signals = run_ruff(tmp_path, ["a.py"])
    assert len(signals) == 2
    assert signals[0].tool == "ruff" and signals[0].line == 3
    assert "F821" in signals[0].message


def test_run_ruff_no_tool_or_no_python_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(tier0.shutil, "which", lambda name: None)
    assert run_ruff(tmp_path, ["a.py"]) == []
    monkeypatch.setattr(tier0.shutil, "which", lambda name: "ruff")
    assert run_ruff(tmp_path, ["notes.txt"]) == []


def test_run_ruff_bad_json(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(tier0.shutil, "which", lambda name: "ruff")
    monkeypatch.setattr(tier0.subprocess, "run", _fake_run("not json"))
    assert run_ruff(tmp_path, ["a.py"]) == []


def test_collect_signals_respects_commands(tmp_path: Path, monkeypatch) -> None:
    called = []
    monkeypatch.setattr(tier0, "run_ruff", lambda repo, files: called.append(1) or [])
    collect_signals(tmp_path, ["a.py"], commands=[])
    assert called == []
    collect_signals(tmp_path, ["a.py"], commands=["ruff"])
    assert called == [1]


def test_signals_near_slack_and_path_matching() -> None:
    sigs = [
        Tier0Signal("ruff", "pkg/a.py", 10, "E1"),
        Tier0Signal("ruff", "pkg/a.py", 13, "E2"),
        Tier0Signal("ruff", "pkg/b.py", 10, "E3"),
    ]
    near = signals_near(sigs, "pkg/a.py", 11)
    assert [s.message for s in near] == ["E1", "E2"]
    assert signals_near(sigs, "pkg\\a.py", 10)  # backslash normalization
    assert signals_near(sigs, "b.py", 10)  # suffix match tolerates repo prefixes
