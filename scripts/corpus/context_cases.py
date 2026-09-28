"""Declared reasonable changes with tests of a substituted callable, plus a real regression.

The six negative cases intentionally change the raw parse result while preserving tests of
the substituted callable. A claim that those tests specify the raw callable is false.
This is a synthetic certification-boundary experiment, not a product recall estimate.
Reuses binding_cases' product trace and fixture builder; no model service or remote writes.
Run the committed driver before and after the reader change, in fresh work directories.
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(os.environ.get("ATTEST_CONTEXT_SRC", ROOT / "src")).resolve()
if not SOURCE.is_relative_to(ROOT):
    raise ValueError("comparison source must be inside this working tree")
sys.path.insert(0, str(SOURCE))

importlib.import_module("attest")  # pin package path before binding_cases adds default src

from binding_cases import SCENARIOS, _git, trace  # noqa: E402

from attest.benchmark.artifacts import write_canonical_json  # noqa: E402
from attest.certification.intent import INTENT_POLICY_V61  # noqa: E402

TEST = '''from geo import Point, parse

def test_parse():
    assert parse("1,2") == Point(1, 2)
'''
PATCH = '''def install():
    globals()["parse"] = lambda text: Point(1, 2)
'''
FIXTURE = '''import pytest

@pytest.fixture(autouse=True)
def substitute(monkeypatch):
    monkeypatch.setitem(globals(), "parse", lambda text: Point(1, 2))
'''
CONFTEST = '''import pytest
from geo import Point

@pytest.fixture(autouse=True)
def substitute(request, monkeypatch):
    if hasattr(request.module, "parse"):
        monkeypatch.setattr(request.module, "parse", lambda text: Point(1, 2))
'''
CASES = {
    "module_autouse": (TEST + "\n" + FIXTURE, {}),
    "ancestor_conftest": (TEST, {"conftest.py": CONFTEST}),
    "module_setup": (TEST + "\n" + PATCH + "\ndef setup_module():\n    install()\n", {}),
    "class_setup": (
        'from geo import Point, parse\n\n' + PATCH + '\nclass TestParse:\n'
        '    def setup_method(self):\n        install()\n\n'
        '    def test_parse(self):\n        assert parse("1,2") == Point(1, 2)\n', {}),
    "import_effect": (TEST + "\n" + PATCH + "\ninstall()\n", {}),
    "declared_plugin": (TEST + '\npytest_plugins = ["context_plugin"]\n',
                        {"context_plugin.py": CONFTEST}),
    "parametrize_ids": (
        'import pytest\nfrom geo import Point, parse\n\n' + PATCH + '\n'
        '@pytest.mark.parametrize("unused", [0], ids=install())\n'
        'def test_parse(unused):\n    assert parse("1,2") == Point(1, 2)\n', {}),
}


def register() -> None:
    for name, (source, files) in CASES.items():
        SCENARIOS[name] = {
            "head": ("return Point(int(a), int(b))", "return Point(int(a), int(b) + 1)"),
            "tests": source, "files": files,
            "probe": {"imports": "from geo import parse", "setup": "",
                      "expression": 'parse("1,2")'},
        }


def measure(name: str, root: Path) -> dict[str, Any]:
    register()
    result = trace(name, policy=INTENT_POLICY_V61, contract_probes=True, root=root)
    repo = root / name
    outcomes = {}
    for revision in ("HEAD~1", "HEAD"):
        sha = _git(repo, "rev-parse", revision)
        tree = root / f"suite-{name}-{sha[:12]}"
        tree.mkdir()
        archive = subprocess.run(["git", "-C", str(repo), "archive", sha],
                                 capture_output=True, check=True).stdout
        subprocess.run(["tar", "-x", "-C", str(tree)], input=archive, check=True)
        run = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_geo.py", "-q", "-p", "no:cacheprovider"],
            cwd=tree, capture_output=True, text=True, timeout=30,
            env={"PATH": str(Path(sys.executable).parent), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        )
        outcomes[revision] = {"sha": sha, "exit": run.returncode,
                              "stdout": run.stdout, "stderr": run.stderr}
    result["original_suite"] = outcomes
    result["declared_truth"] = "regression" if name == "legal_contract" else "reasonable_change"
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--scenarios", default=",".join((*CASES, "legal_contract")))
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=False)
    results = []
    for name in args.scenarios.split(","):
        row = measure(name, args.work)
        results.append(row)
        print(json.dumps({k: row[k] for k in
                          ("scenario", "reader_admitted", "certification")}), flush=True)
    write_canonical_json(args.out, results)


if __name__ == "__main__":
    main()
