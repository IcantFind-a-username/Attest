"""P-04a: what does a repository already state about itself, and how much of it is checkable?

The direction under test: instead of asking a model what should be true, read what the
repository already says, turn those statements into runtime checkpoints, run the project's own
workload, and treat a violated checkpoint as a contradiction between what the code says and
what it does. This first step counts the statements, by kind, without running anything.

Three kinds, in increasing value and decreasing volume:

    type        a function whose return annotation the rule can check at runtime
    value       a doctest example: a call and the value it is stated to produce
    assertion   an `assert` in the library's own source: a statement the interpreter checks

    .venv/bin/python scripts/probe/checkpoint_inventory.py --out inventory.json

Counts only; no execution, no model, no spend.
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / ".attest/corpora/mutations-v1-recall"

# annotations this rule can check against a value at runtime, without importing typing
# machinery: the builtin shapes, and `None`
_CHECKABLE = {
    "str", "int", "float", "bool", "bytes", "list", "dict", "tuple", "set", "frozenset",
    "None", "NoneType",
}


def checkable_annotation(node: ast.expr | None) -> bool:
    """Is this return annotation one a runtime check can decide?

    A bare builtin, or an optional of one. A generic (`list[int]`), a protocol, a type
    variable or a string forward reference is counted as stated but not checkable: the
    check would need the typing machinery, and a wrong answer there is noise, not signal.
    """
    if node is None:
        return False
    if isinstance(node, ast.Name):
        return node.id in _CHECKABLE
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return checkable_annotation(node.left) and checkable_annotation(node.right)
    if isinstance(node, ast.Subscript):
        base = node.value
        if isinstance(base, ast.Name) and base.id == "Optional":
            return checkable_annotation(node.slice)
    return False


def source_files(package: Path) -> list[Path]:
    return [
        p for p in sorted(package.rglob("*.py"))
        if "test" not in p.parts and not p.name.startswith("test_")
    ]


def count_file(path: Path) -> dict[str, Any]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError, ValueError):
        return {}
    annotated = checkable = doctests = asserts = functions = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            functions += 1
            if node.returns is not None:
                annotated += 1
                checkable += int(checkable_annotation(node.returns))
            doc = ast.get_docstring(node) or ""
            doctests += doc.count(">>>")
        elif isinstance(node, ast.Assert):
            asserts += 1
    doc = ast.get_docstring(tree) or ""
    doctests += doc.count(">>>")
    return {
        "functions": functions, "annotated_returns": annotated,
        "checkable_returns": checkable, "doctest_lines": doctests, "asserts": asserts,
    }


def package_of(repo: Path) -> Path | None:
    """The library's own source: `src/<name>` or `<name>`, whichever holds packages."""
    source = repo / "src"
    candidates = [p for p in source.glob("*") if p.is_dir()] if source.is_dir() else []
    candidates += [
        p for p in repo.glob("*")
        if p.is_dir() and (p / "__init__.py").is_file() and not p.name.startswith(("test", "."))
    ]
    # a project may ship a thin re-export beside the real package (`attrs` next to `attr`):
    # the one with the most modules is the one that holds the statements
    return max(candidates, key=lambda p: len(list(p.rglob("*.py"))), default=None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    rows: list[dict[str, Any]] = []
    for library in sorted(p for p in CORPUS.glob("*") if (p / "repo").is_dir()):
        repo = library / "repo"
        package = package_of(repo)
        if package is None:
            rows.append({"library": library.name, "error": "no package found"})
            continue
        totals: dict[str, int] = {}
        files = 0
        for path in source_files(package):
            counted = count_file(path)
            if not counted:
                continue
            files += 1
            for key, value in counted.items():
                totals[key] = totals.get(key, 0) + value
        rows.append({"library": library.name, "package": package.name, "files": files, **totals})
    summary = {
        "probe": "P-04a checkpoint inventory",
        "libraries": rows,
        "totals": {
            key: sum(int(r.get(key, 0)) for r in rows)
            for key in ("functions", "annotated_returns", "checkable_returns",
                        "doctest_lines", "asserts")
        },
    }
    Path(args.out).write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    width = max(len(r["library"]) for r in rows)
    print(f"{'library':<{width}}  funcs  annot  check  doctest  assert")
    for r in rows:
        print(f"{r['library']:<{width}}  {r.get('functions', 0):5}"
              f"  {r.get('annotated_returns', 0):5}"
              f"  {r.get('checkable_returns', 0):5}  {r.get('doctest_lines', 0):7}"
              f"  {r.get('asserts', 0):6}")
    print("totals:", json.dumps(summary["totals"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
