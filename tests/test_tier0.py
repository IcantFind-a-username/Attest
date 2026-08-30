import ast
import inspect
import json
import socket
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from attest.review import tier0
from attest.review.config import ReviewConfig
from attest.review.proposer import MockProvider
from attest.review.run import run_review
from attest.review.schema import Finding
from attest.review.tier0 import (
    Tier0Signal,
    _ident_defined_names,
    collect_signals,
    run_ruff,
    signals_near,
    unresolved_identifiers,
)


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


# --- identifier-existence veto (tier-0, zero cost, purely static) -----------

MODULE_SOURCE = '''"""Helpers for totals. See the legacy ``spreadsheet`` importer."""

import os.path


class Accumulator:
    def __init__(self, config):
        self.retry_limit = config.retry_limit
        self.total = 0

    def add(self, amount):
        self.total += amount
        return self.total


def average(items):
    # historical name: mean_of
    return sum(items) / len(items)
'''


def _finding(claim: str, scenario: str = "", file: str = "mod.py", line: int = 1) -> Finding:
    return Finding(
        claim=claim,
        file=file,
        line=line,
        failure_scenario=scenario,
        falsification_plan="re-run the anchored code path",
    )


@pytest.fixture
def module_repo(tmp_path: Path) -> Path:
    (tmp_path / "mod.py").write_text(MODULE_SOURCE, encoding="utf-8")
    return tmp_path


def test_unresolved_identifiers_accepts_names_defined_in_the_anchored_file(
    module_repo: Path,
) -> None:
    finding = _finding(
        "`average()` divides by zero for an empty sequence.",
        "`Accumulator.add()` is then called with the bad total.",
    )
    assert unresolved_identifiers(module_repo, finding) == []


def test_unresolved_identifiers_flags_a_name_that_exists_nowhere(module_repo: Path) -> None:
    finding = _finding(
        "The helper `frobnicate()` is called before the guard runs.",
        "frobnicate([]) raises before the total is accumulated.",
    )
    assert unresolved_identifiers(module_repo, finding) == ["frobnicate"]


def test_unresolved_identifiers_ignores_builtins_keywords_and_english(module_repo: Path) -> None:
    finding = _finding(
        "`len()` returns 0 and the `dict` lookup yields no `value`.",
        "The `return` statement then propagates an empty `result` to the caller.",
    )
    assert unresolved_identifiers(module_repo, finding) == []


def test_unresolved_identifiers_accepts_a_name_only_in_a_docstring_or_comment(
    module_repo: Path,
) -> None:
    finding = _finding(
        "The `spreadsheet` importer path is not covered by `mean_of`.",
        "Both names appear only in prose inside the file.",
    )
    assert unresolved_identifiers(module_repo, finding) == []


def test_unresolved_identifiers_fails_open_on_unparseable_or_missing_file(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def (((\n", encoding="utf-8")
    broken = _finding("`frobnicate()` explodes.", file="broken.py")
    assert unresolved_identifiers(tmp_path, broken) == []

    absent = _finding("`frobnicate()` explodes.", file="does_not_exist.py")
    assert unresolved_identifiers(tmp_path, absent) == []

    directory = _finding("`frobnicate()` explodes.", file=".")
    assert unresolved_identifiers(tmp_path, directory) == []


def test_unresolved_identifiers_ignores_file_paths_in_prose(module_repo: Path) -> None:
    # `app.py` names a file, not a symbol; treating "app" as an invented
    # identifier would veto a true finding for citing its own file
    finding = _finding("The loader in `app.py` never reads `data.json`.")
    assert unresolved_identifiers(module_repo, finding) == []


def test_defined_names_cover_imports_aliases_handlers_and_globals() -> None:
    tree = ast.parse(
        "import os.path as ospath\n"
        "from collections import abc\n"
        "\n"
        "TALLY = 0\n"
        "\n"
        "def bump():\n"
        "    global TALLY\n"
        "    def inner():\n"
        "        nonlocal held\n"
        "    held = 1\n"
        "    try:\n"
        "        TALLY += 1\n"
        "    except ValueError as caught:\n"
        "        raise caught\n"
    )
    names = _ident_defined_names(tree)
    assert {"ospath", "os", "path", "collections", "abc", "TALLY", "caught", "held"} <= names


def test_unresolved_identifiers_resolves_dotted_attribute_access(module_repo: Path) -> None:
    finding = _finding("`config.retry_limit` is read before it is validated.")
    assert unresolved_identifiers(module_repo, finding) == []


def test_unresolved_identifiers_makes_no_network_or_subprocess_calls(
    module_repo: Path, monkeypatch
) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("the identifier check must not shell out or open a socket")

    monkeypatch.setattr(tier0.subprocess, "run", forbidden)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)

    finding = _finding("`frobnicate()` is invented.", "`average()` is real.")
    assert unresolved_identifiers(module_repo, finding) == ["frobnicate"]

    # structural: the new code path names no process- or network-capable module
    sources = "\n".join(
        inspect.getsource(obj)
        for obj in vars(tier0).values()
        if inspect.isfunction(obj) and obj.__module__ == tier0.__name__ and _is_identifier_path(obj)
    )
    assert sources.strip()
    for banned in ("subprocess", "socket", "urllib", "requests", "http", "shutil", "open("):
        assert banned not in sources


def _is_identifier_path(obj) -> bool:
    """Functions reachable from unresolved_identifiers (name-prefixed by design)."""
    return obj.__name__ == "unresolved_identifiers" or obj.__name__.startswith("_ident")


# --- end-to-end: the signal is recorded and vetoes nothing ------------------


def _ledger_rows(repo: Path, kind: str) -> list[dict]:
    path = repo / ".attest" / "ledger.jsonl"
    if not path.is_file():
        return []
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return [row for row in rows if row.get("kind") == kind]


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    def git(*args: str) -> None:
        subprocess.run(["git", "-C", str(tmp_path), *args], check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "app.py").write_text("def total(items):\n    return sum(items)\n", encoding="utf-8")
    git("add", "-A")
    git("commit", "-m", "base")
    (tmp_path / "app.py").write_text(
        "def total(items):\n    return sum(items)\n\n\ndef average(items):\n"
        "    return sum(items) / len(items)\n",
        encoding="utf-8",
    )
    return tmp_path


def _payload(claim: str, scenario: str) -> str:
    return json.dumps(
        {
            "findings": [
                {
                    "claim": claim,
                    "anchor": {"file": "app.py", "line": 5},
                    "failure_scenario": scenario,
                    "falsification_plan": "call the function and observe the exception",
                }
            ]
        }
    )


def test_hallucinated_identifier_is_recorded_but_still_reaches_the_gate(git_repo: Path) -> None:
    run = run_review(
        git_repo,
        None,
        ReviewConfig(k_samples=1, tier0_commands=[]),
        MockProvider(
            [_payload("`frobnicate()` divides by zero.", "frobnicate([]) raises immediately.")]
        ),
        clock=lambda: 0.0,
    )

    # the signal vetoes nothing: the finding is wagered exactly as before
    assert len(run.results) == 1
    assert run.results[0].finding.file == "app.py"
    assert not any("voided" in note for note in run.notes)

    rows = _ledger_rows(git_repo, "identifier_check")
    assert len(rows) == 1
    assert rows[0]["unresolved"] == ["frobnicate"]
    assert rows[0]["task_id"] == run.task_id
    assert rows[0]["finding_id"] == run.results[0].finding.finding_id


def test_resolved_identifiers_record_no_ledger_row(git_repo: Path) -> None:
    run = run_review(
        git_repo,
        None,
        ReviewConfig(k_samples=1, tier0_commands=[]),
        MockProvider(
            [_payload("`average()` divides by zero.", "`average([])` raises ZeroDivisionError.")]
        ),
        clock=lambda: 0.0,
    )

    assert len(run.results) == 1
    assert _ledger_rows(git_repo, "identifier_check") == []
