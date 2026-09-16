"""P-04c: do a repository's own return types hold at runtime, and do they localise a defect?

P-04b used the values a repository states (doctests). This one uses the types it states: the
1,359 return annotations P-04a found checkable. A checkpoint is one annotated function; it is
**exercised** when the workload calls it, and **broken** when the value it returns is not of the
type its own signature declares.

The workload is the library's own test suite. The plugin wraps every checkable function after
the package is imported, counts calls and violations, and writes a record. Two numbers decide
the idea: how many checkpoints break on the healthy revision (noise floor), and whether a
planted defect breaks one in the file it was planted in (localisation).

    .venv/bin/python scripts/probe/checkpoint_type_probe.py --out probe.json

No model, no spend. The plugin is written into a temporary directory, never into the corpus.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))
sys.path.insert(0, str(ROOT / "scripts" / "probe"))

from checkpoint_inventory import package_of  # noqa: E402
from mutation_recall import STUDY, WORK  # noqa: E402

TIMEOUT_S = 1200.0

PLUGIN = '''"""Wrap a package's annotated functions and record where its own types do not hold."""
from __future__ import annotations

import inspect
import json
import os
import pkgutil
import importlib
import functools
from pathlib import Path

_SIMPLE = {
    "str": str, "int": int, "float": float, "bool": bool, "bytes": bytes,
    "list": list, "dict": dict, "tuple": tuple, "set": set, "frozenset": frozenset,
    "None": type(None), "NoneType": type(None),
}
_STATE = {"calls": 0, "violations": [], "wrapped": 0, "exercised": set(),
          "import_errors": [], "deferred": 0, "idiomatic": 0}


def _expected(annotation):
    """The tuple of types this annotation admits, or None when the rule cannot decide."""
    if annotation is inspect.Signature.empty:
        return None
    if isinstance(annotation, str):
        parts = [p.strip() for p in annotation.replace("Optional[", "").rstrip("]").split("|")]
        types = tuple(_SIMPLE[p] for p in parts if p in _SIMPLE)
        return types if types and len(types) == len(parts) else None
    if annotation in _SIMPLE.values():
        return (annotation,)
    if annotation is None:
        return (type(None),)
    return None


def _wrap(function, where):
    # an async or generator function returns a coroutine or a generator at call time, whatever
    # its annotation says about the value it eventually produces: not a checkpoint this rule
    # can decide without driving the loop, so it is skipped rather than counted as broken
    if (inspect.iscoroutinefunction(function) or inspect.isasyncgenfunction(function)
            or inspect.isgeneratorfunction(function)):
        return None
    expected = _expected(function.__annotations__.get("return", inspect.Signature.empty))
    if expected is None:
        return None

    @functools.wraps(function)
    def checked(*args, **kwargs):
        _STATE["calls"] += 1
        _STATE["exercised"].add(where)
        value = function(*args, **kwargs)
        if inspect.iscoroutine(value) or inspect.isgenerator(value):
            _STATE["deferred"] += 1  # the value is produced later; this rule does not drive it
            return value
        if value is NotImplemented:
            # the comparison protocol: a rich comparison returns NotImplemented to hand the
            # question to the other operand, and `-> bool` is the shorthand every library
            # writes. The language contradicts the annotation here, not the repository
            _STATE["idiomatic"] += 1
            return value
        if not isinstance(value, expected):
            record = {
                "where": where,
                "expected": "|".join(t.__name__ for t in expected),
                "got": type(value).__name__,
            }
            if record not in _STATE["violations"]:
                _STATE["violations"].append(record)
        return value

    return checked


def pytest_configure(config):
    package_name = os.environ["ATTEST_PACKAGE"]
    try:
        package = importlib.import_module(package_name)
    except Exception as exc:  # noqa: BLE001 - recorded, never raised into the suite
        _STATE["import_errors"].append(f"{package_name}: {exc}")
        return
    modules = [package]
    for info in pkgutil.walk_packages(getattr(package, "__path__", []), f"{package_name}."):
        try:
            modules.append(importlib.import_module(info.name))
        except Exception as exc:  # noqa: BLE001
            _STATE["import_errors"].append(f"{info.name}: {exc}")
    for module in modules:
        for name, value in list(vars(module).items()):
            if getattr(value, "__module__", None) != module.__name__:
                continue
            if inspect.isfunction(value):
                wrapped = _wrap(value, f"{module.__name__}.{name}")
                if wrapped is not None:
                    setattr(module, name, wrapped)
                    _STATE["wrapped"] += 1
            elif inspect.isclass(value):
                for attribute, member in list(vars(value).items()):
                    if not inspect.isfunction(member):
                        continue
                    wrapped = _wrap(member, f"{module.__name__}.{name}.{attribute}")
                    if wrapped is not None:
                        try:
                            setattr(value, attribute, wrapped)
                        except (AttributeError, TypeError):
                            continue
                        _STATE["wrapped"] += 1


def pytest_sessionfinish(session, exitstatus):
    Path(os.environ["ATTEST_CHECKPOINT_OUT"]).write_text(json.dumps({
        "wrapped": _STATE["wrapped"],
        "calls": _STATE["calls"],
        "deferred": _STATE["deferred"],
        "idiomatic": _STATE["idiomatic"],
        "exercised": len(_STATE["exercised"]),
        "violations": _STATE["violations"][:50],
        "violation_count": len(_STATE["violations"]),
        "import_errors": _STATE["import_errors"][:10],
        "exit": int(exitstatus),
    }), encoding="utf-8")
'''


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def run_suite(venv: Path, repo: Path, package: str, plugin_dir: Path, out: Path) -> dict[str, Any]:
    tests = "tests" if (repo / "tests").is_dir() else "test"
    environment = {
        **dict(PATH=str(venv / "bin") + ":/usr/bin:/bin"),
        "ATTEST_PACKAGE": package,
        "ATTEST_CHECKPOINT_OUT": str(out),
        "PYTHONPATH": str(plugin_dir),
        "HOME": str(plugin_dir),
    }
    try:
        completed = subprocess.run(
            [str(venv / "bin" / "python"), "-m", "pytest", "-q", "--no-header",
             "-p", "no:cacheprovider", "-p", "attest_checkpoints", "-o", "addopts=",
             "-W", "ignore", "-x", "--timeout=120" if False else "-q", tests],
            cwd=repo, capture_output=True, text=True, timeout=TIMEOUT_S, env=environment,
        )
    except subprocess.TimeoutExpired:
        return {"outcome": "timeout"}
    record: dict[str, Any] = {"outcome": "ran", "exit": completed.returncode}
    if out.is_file():
        record.update(json.loads(out.read_text(encoding="utf-8")))
    else:
        record["outcome"] = "no record"
        record["tail"] = ((completed.stdout or "") + (completed.stderr or ""))[-300:]
    return record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    parser.add_argument("--libraries", default="jinja,urllib3,packaging,click")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args(argv)
    wanted = {name for name in args.libraries.split(",") if name}
    sample = [
        row for row in (
            json.loads(line) for line in
            (STUDY / "sample.jsonl").read_text(encoding="utf-8").splitlines() if line
        )
        if row["library"] in wanted
    ]
    seen: set[str] = set()
    cases = []
    for row in sample:  # one case per library is enough to measure a noise floor
        if row["library"] in seen:
            continue
        seen.add(row["library"])
        cases.append(row)
    cases.extend(row for row in sample if row not in cases)
    if args.limit:
        cases = cases[: args.limit]

    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="checkpoint-plugin-") as tmp:
        plugin_dir = Path(tmp)
        (plugin_dir / "attest_checkpoints.py").write_text(PLUGIN, encoding="utf-8")
        for case in cases:
            unit = case["unit_id"]
            manifest = json.loads((WORK / "cases" / unit / "manifest.json").read_text())
            repo = Path(manifest["repo_path"])
            venv = repo.parent / ".venv"
            package_path = package_of(repo)
            if package_path is None:
                continue
            package = package_path.name
            mutation = manifest["mutation"]
            restore = git(repo, "rev-parse", "HEAD")
            try:
                git(repo, "checkout", "--quiet", "--force", manifest["base_sha"])
                base = run_suite(venv, repo, package, plugin_dir, plugin_dir / "base.json")
                git(repo, "checkout", "--quiet", "--force", manifest["head_sha"])
                head = run_suite(venv, repo, package, plugin_dir, plugin_dir / "head.json")
            finally:
                git(repo, "checkout", "--quiet", "--force", restore)
            base_violations = {v["where"] for v in base.get("violations", [])}
            head_violations = {v["where"] for v in head.get("violations", [])}
            new = sorted(head_violations - base_violations)
            module_of_planted = mutation["path"].split("/")[-1].removesuffix(".py")
            row = {
                "unit_id": unit, "library": case["library"], "package": package,
                "planted": f"{mutation['path']}:{mutation['line']}",
                "base": {k: base.get(k) for k in
                         ("outcome", "wrapped", "calls", "exercised", "violation_count", "exit")},
                "head": {k: head.get(k) for k in
                         ("outcome", "wrapped", "calls", "exercised", "violation_count", "exit")},
                "noise_floor_violations": sorted(base_violations)[:20],
                "new_violations": new,
                "new_in_planted_module": [w for w in new if module_of_planted in w],
                "import_errors": base.get("import_errors", [])[:3],
            }
            rows.append(row)
            print(json.dumps({
                "unit_id": unit, "wrapped": base.get("wrapped"), "calls": base.get("calls"),
                "exercised": base.get("exercised"), "noise": base.get("violation_count"),
                "new": len(new), "localised": bool(row["new_in_planted_module"]),
            }), flush=True)

    summary = {
        "probe": "P-04c type checkpoints",
        "cases": len(rows),
        "detected": sum(1 for r in rows if r["new_violations"]),
        "localised": sum(1 for r in rows if r["new_in_planted_module"]),
        "limits": [
            "only the annotations a runtime check can decide (builtin shapes and optionals "
            "of them) are checkpoints; a generic, a protocol or a forward reference is not",
            "wrapping is by module attribute: a function a library re-exports or calls "
            "through a private reference is not wrapped, and is not counted as exercised",
            "a suite that a wrapped function breaks reports its own failure; the record keeps "
            "the exit code so such a run is visible rather than silently empty",
        ],
        "rows": rows,
    }
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("cases", "detected", "localised")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
