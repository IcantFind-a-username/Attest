"""P-05: a repository's own declared types, checked while its own tests run, without touching it.

P-04 showed the idea works and that the instrument did not: wrapping module attributes changed
what it measured (jinja's suite went from 911 passed to 910 passed, 1 failed, because pickle
notices a replaced function object). This audit observes instead of rebinding, with
`sys.monitoring` (PEP 669): a return event is delivered for exactly the code objects registered,
the function objects stay the ones the repository created, and nothing in the tree is written.

For each library it runs the suite twice -- once clean, once observed -- and reports both the
contradictions and the proof that observing did not change the run.

    .venv/bin/python scripts/probe/contradiction_audit.py --out audit.json

A contradiction is a function whose own signature declares a return type that the value it
returned is not. Two exemptions, both properties of the language rather than of the repository:
a coroutine or generator function (the call returns an awaitable, not the value), and
`NotImplemented` from a rich comparison. No model, no spend, no product change.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "probe"))

from checkpoint_inventory import package_of  # noqa: E402

CORPUS = ROOT / ".attest/corpora/mutations-v1-recall"
TIMEOUT_S = 1800.0
_COUNTS = re.compile(r"(\d+) (passed|failed|error|errors|skipped|xfailed|xpassed)")

PLUGIN = '''"""Observe a package's declared return types with sys.monitoring; change nothing."""
from __future__ import annotations

import importlib
import inspect
import json
import os
import pkgutil
import sys
from pathlib import Path

_SIMPLE = {
    "str": str, "int": int, "float": float, "bool": bool, "bytes": bytes,
    "list": list, "dict": dict, "tuple": tuple, "set": set, "frozenset": frozenset,
    "None": type(None), "NoneType": type(None),
}
_STATE = {
    "registered": 0, "returns": 0, "exercised": set(), "violations": {},
    "idiomatic": 0, "import_errors": [], "skipped_lazy": 0, "deferred": 0, "current": "",
}
_EXPECTED = {}
TOOL = 2  # sys.monitoring.PROFILER_ID


def _expected(annotation):
    if annotation is inspect.Signature.empty or annotation is None:
        return None
    if isinstance(annotation, str):
        text = annotation.strip()
        if text.startswith("Optional[") and text.endswith("]"):
            text = text[len("Optional["):-1] + " | None"
        parts = [p.strip() for p in text.split("|")]
        types = tuple(_SIMPLE[p] for p in parts if p in _SIMPLE)
        return types if types and len(types) == len(parts) else None
    if annotation in _SIMPLE.values():
        return (annotation,)
    return None


_ONLY = {w for w in os.environ.get("ATTEST_ONLY", "").split(",") if w}


def _register(function, where):
    if _ONLY and where not in _ONLY:
        return
    # a generator or coroutine function returns an awaitable at call time, whatever its
    # annotation describes; its PY_RETURN carries the value handed to StopIteration, not
    # the value the caller receives
    if (inspect.isgeneratorfunction(function) or inspect.iscoroutinefunction(function)
            or inspect.isasyncgenfunction(function)):
        _STATE["skipped_lazy"] += 1
        return
    expected = _expected(function.__annotations__.get("return", inspect.Signature.empty))
    if expected is None:
        return
    code = function.__code__
    if code in _EXPECTED:
        return
    _EXPECTED[code] = (expected, where)
    sys.monitoring.set_local_events(TOOL, code, sys.monitoring.events.PY_RETURN)
    _STATE["registered"] += 1


def _on_return(code, offset, value):
    entry = _EXPECTED.get(code)
    if entry is None:
        return sys.monitoring.DISABLE
    expected, where = entry
    _STATE["returns"] += 1
    _STATE["exercised"].add(where)
    if value is NotImplemented:
        _STATE["idiomatic"] += 1  # the comparison protocol, not a contradiction
        return None
    if inspect.iscoroutine(value) or inspect.isgenerator(value) or inspect.isasyncgen(value):
        # the value is not produced yet: a sync function returning an awaitable is how a
        # library offers an async mode, and the annotation describes what the caller awaits
        _STATE["deferred"] += 1
        return None
    if not isinstance(value, expected):
        key = where
        record = _STATE["violations"].setdefault(key, {
            "where": where,
            "expected": "|".join(t.__name__ for t in expected),
            "got": {},
            "count": 0,
            "nodes": [],
        })
        record["count"] += 1
        got = type(value).__name__
        record["got"][got] = record["got"].get(got, 0) + 1
        # which test made this call: what a reader needs to reproduce the contradiction
        node = _STATE["current"]
        if node and node not in record["nodes"] and len(record["nodes"]) < 5:
            record["nodes"].append(node)
    return None


def pytest_runtest_logstart(nodeid, location):
    _STATE["current"] = nodeid


def pytest_configure(config):
    name = os.environ["ATTEST_PACKAGE"]
    sys.monitoring.use_tool_id(TOOL, "attest-contradiction-audit")
    sys.monitoring.register_callback(TOOL, sys.monitoring.events.PY_RETURN, _on_return)
    try:
        package = importlib.import_module(name)
    except Exception as exc:  # noqa: BLE001 - recorded, never raised into the suite
        _STATE["import_errors"].append(f"{name}: {exc}")
        return
    modules = [package]
    for info in pkgutil.walk_packages(getattr(package, "__path__", []), f"{name}."):
        try:
            modules.append(importlib.import_module(info.name))
        except Exception as exc:  # noqa: BLE001
            _STATE["import_errors"].append(f"{info.name}: {exc}")
    for module in modules:
        for attribute, value in list(vars(module).items()):
            if getattr(value, "__module__", None) != module.__name__:
                continue
            if inspect.isfunction(value):
                _register(value, f"{module.__name__}.{attribute}")
            elif inspect.isclass(value):
                for member_name, member in list(vars(value).items()):
                    if inspect.isfunction(member):
                        _register(member, f"{module.__name__}.{attribute}.{member_name}")


def pytest_sessionfinish(session, exitstatus):
    Path(os.environ["ATTEST_AUDIT_OUT"]).write_text(json.dumps({
        "registered": _STATE["registered"],
        "returns": _STATE["returns"],
        "exercised": len(_STATE["exercised"]),
        "idiomatic": _STATE["idiomatic"],
        "deferred": _STATE["deferred"],
        "skipped_lazy": _STATE["skipped_lazy"],
        "violations": sorted(_STATE["violations"].values(), key=lambda v: -v["count"]),
        "import_errors": _STATE["import_errors"][:10],
        "exit": int(exitstatus),
    }), encoding="utf-8")
'''


def counts_of(text: str) -> dict[str, int]:
    return {kind: int(n) for n, kind in _COUNTS.findall(text)}


def run_suite(
    venv: Path, repo: Path, tests: str, *, plugin_dir: Path | None = None,
    package: str = "", out: Path | None = None,
) -> dict[str, Any]:
    argv = [str(venv / "bin" / "python"), "-m", "pytest", "-q", "--no-header",
            "-p", "no:cacheprovider", "-o", "addopts=", "-W", "ignore"]
    environment = {"PATH": f"{venv / 'bin'}:/usr/bin:/bin", "HOME": str(plugin_dir or repo)}
    if plugin_dir is not None:
        argv += ["-p", "attest_audit"]
        environment |= {
            "PYTHONPATH": str(plugin_dir), "ATTEST_PACKAGE": package,
            "ATTEST_AUDIT_OUT": str(out),
        }
    try:
        completed = subprocess.run(
            [*argv, tests], cwd=repo, capture_output=True, text=True,
            timeout=TIMEOUT_S, env=environment,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "timeout"}
    text = (completed.stdout or "") + (completed.stderr or "")
    record: dict[str, Any] = {
        "outcome": "ran", "exit": completed.returncode, "counts": counts_of(text),
    }
    if out is not None and out.is_file():
        record |= json.loads(out.read_text(encoding="utf-8"))
    elif out is not None:
        record["outcome"] = "no record"
        record["tail"] = text[-300:]
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--libraries", default="")
    args = parser.parse_args(argv)
    wanted = {name for name in args.libraries.split(",") if name}

    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="contradiction-audit-") as tmp:
        plugin_dir = Path(tmp)
        (plugin_dir / "attest_audit.py").write_text(PLUGIN, encoding="utf-8")
        for library in sorted(p for p in CORPUS.glob("*") if (p / "repo").is_dir()):
            if wanted and library.name not in wanted:
                continue
            repo, venv = library / "repo", library / ".venv"
            package_path = package_of(repo)
            if package_path is None or not (venv / "bin" / "python").is_file():
                rows.append({"library": library.name, "outcome": "no package or environment"})
                continue
            tests = "tests" if (repo / "tests").is_dir() else "test"
            revision = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True,
            ).stdout.strip()
            clean = run_suite(venv, repo, tests)
            observed = run_suite(
                venv, repo, tests, plugin_dir=plugin_dir, package=package_path.name,
                out=plugin_dir / f"{library.name}.json",
            )
            row = {
                "library": library.name, "package": package_path.name, "revision": revision,
                "clean": {k: clean.get(k) for k in ("outcome", "exit", "counts")},
                "observed": {k: observed.get(k) for k in
                             ("outcome", "exit", "counts", "registered", "returns",
                              "exercised", "idiomatic", "skipped_lazy", "deferred")},
                "unperturbed": clean.get("counts") == observed.get("counts")
                and clean.get("exit") == observed.get("exit"),
                "contradictions": observed.get("violations", []),
                "import_errors": observed.get("import_errors", []),
            }
            rows.append(row)
            print(json.dumps({
                "library": row["library"], "registered": row["observed"].get("registered"),
                "exercised": row["observed"].get("exercised"),
                "contradictions": len(row["contradictions"]),
                "unperturbed": row["unperturbed"],
            }), flush=True)

    audited = [r for r in rows if "observed" in r]
    summary = {
        "probe": "P-05 contradiction audit",
        "libraries": len(rows),
        "registered": sum(int(r["observed"].get("registered") or 0) for r in audited),
        "exercised": sum(int(r["observed"].get("exercised") or 0) for r in audited),
        "contradictions": sum(len(r["contradictions"]) for r in audited),
        "unperturbed": sum(1 for r in audited if r["unperturbed"]),
        "perturbed": [r["library"] for r in audited if not r["unperturbed"]],
        "limits": [
            "a contradiction is a declared return type the returned value is not; the rule "
            "reads builtin shapes and optionals of them, not generics or protocols",
            "generator and coroutine functions are not observed: their return event carries "
            "the value handed to StopIteration, not the value the caller receives",
            "`NotImplemented` from a rich comparison is the language's protocol, not a "
            "contradiction, and is counted separately",
            "a returned coroutine or generator is counted as deferred, not as a contradiction: "
            "the value the annotation describes is the one the caller awaits",
            "the workload is each library's own test suite: a function no test calls is "
            "registered and never exercised",
        ],
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in
                      ("libraries", "registered", "exercised", "contradictions",
                       "unperturbed", "perturbed")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
