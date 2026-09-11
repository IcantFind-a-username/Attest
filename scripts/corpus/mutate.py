"""mutations-v1: a crash-mutation corpus over the eight public clones ($0, no review).

Owner authorisation of 2026-09-12 (work order PR 3 e). For each of the eight
`G-NULL-001a` clones at its current default-branch tip, the library's **own**
test suite is run under `coverage` to find the lines its tests reach, and three
classes of crash mutation are injected on covered lines of the package's own
source, each one a separate commit off the original:

    guard_raise   an `if ...: raise ...` validation is deleted
    boundary      a `<=` becomes `<` (or `<` becomes `<=`, likewise `>=`/`>`)
    none_guard    an `if x is None: return ...` guard is deleted

Every mutation yields two cases in the `swebench_pilot` manifest shape: the
**forward** direction (base = the original, head = the mutation: the pull
request that introduces the defect) and the **fix** direction (base = the
mutation, head = the original: the pull request that repairs it). Nothing here
buys a review; the corpus sits under `.attest/corpora/mutations-v1/` and is
never committed.

A library whose tests cannot be installed or run inside the time cap is
skipped by name with the reason, never silently.

    .venv/bin/python scripts/corpus/mutate.py --clones .attest/corpora/gnull \\
        --out .attest/corpora/mutations-v1 [--only click,jinja] [--per-class 6]
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts" / "corpus"))

from e05_select import is_package_source  # noqa: E402

LIBRARIES = (
    "attrs",
    "click",
    "itsdangerous",
    "jinja",
    "more-itertools",
    "packaging",
    "python-dotenv",
    "urllib3",
)
INSTALL_TIMEOUT_S = 900.0
TEST_TIMEOUT_S = 1200.0
# what each library's own test suite needs beyond `pip install -e .`, read off
# its tox/pyproject at the tip; a wrong guess only means the suite fails and the
# library is recorded as skipped
EXTRA_TEST_DEPS = {
    "attrs": ["hypothesis", "pympler"],
    "itsdangerous": ["freezegun"],
    "python-dotenv": ["sh", "click"],
    # urllib3's `test` dependency group at the 2026-09 tip, plus `trustme`,
    # which its conftest imports
    "urllib3": ["anyio[trio]", "h2", "httpx", "hypercorn", "pysocks", "pytest-socket",
                "pytest-timeout", "quart", "quart-trio", "trio", "trustme"],
    "packaging": ["hypothesis", "pretend", "tomli_w", "pip"],
    "more-itertools": [],
    "click": [],
    "jinja": ["pytest-timeout", "trio"],
}
CLASSES = ("guard_raise", "boundary", "none_guard")
SWAP = {"<=": "<", "<": "<=", ">=": ">", ">": ">="}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def _run(args: list[str], *, cwd: Path, timeout: float, env: dict[str, str] | None = None
         ) -> tuple[int | None, str]:
    try:
        completed = subprocess.run(
            args, cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
            env=env or os.environ.copy(), check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return None, f"timed out after {timeout:.0f}s: {(exc.stdout or b'')[-2000:]!r}"
    return completed.returncode, (completed.stdout + completed.stderr)[-4000:]


@dataclass(frozen=True)
class Site:
    kind: str
    path: str  # relative, posix
    line: int  # first line of the statement / the compare's line
    end_line: int
    description: str
    replacement: str = ""  # boundary: the operator text after the swap
    span: tuple[int, int] = (0, 0)  # boundary: (start col, end col) on `line`


def _sites_in(source: str, path: str, executed: set[int]) -> list[Site]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = source.splitlines()
    found: list[Site] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and node.lineno in executed and not node.orelse:
            body = node.body
            if len(body) == 1 and isinstance(body[0], ast.Raise):
                found.append(
                    Site("guard_raise", path, node.lineno, node.end_lineno or node.lineno,
                         f"delete the guard at {path}:{node.lineno}: "
                         f"{lines[node.lineno - 1].strip()[:80]}")
                )
            test = node.test
            if (
                len(body) == 1
                and isinstance(body[0], ast.Return)
                and isinstance(test, ast.Compare)
                and len(test.ops) == 1
                and isinstance(test.ops[0], ast.Is)
                and isinstance(test.comparators[0], ast.Constant)
                and test.comparators[0].value is None
            ):
                found.append(
                    Site("none_guard", path, node.lineno, node.end_lineno or node.lineno,
                         f"delete the None guard at {path}:{node.lineno}: "
                         f"{lines[node.lineno - 1].strip()[:80]}")
                )
        if (
            isinstance(node, ast.Compare)
            and len(node.ops) == 1
            and isinstance(node.ops[0], (ast.Lt, ast.LtE, ast.Gt, ast.GtE))
            and node.lineno in executed
            and node.left.end_lineno == node.lineno
            and node.comparators[0].lineno == node.lineno
        ):
            start = node.left.end_col_offset or 0
            end = node.comparators[0].col_offset
            text = lines[node.lineno - 1]
            between = text[start:end]
            op = {ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}[type(node.ops[0])]
            if between.strip() != op:
                continue
            found.append(
                Site("boundary", path, node.lineno, node.lineno,
                     f"{op} -> {SWAP[op]} at {path}:{node.lineno}: {text.strip()[:80]}",
                     replacement=between.replace(op, SWAP[op], 1), span=(start, end))
            )
    return found


def _apply(worktree: Path, site: Site) -> bool:
    file = worktree / site.path
    lines = file.read_text(encoding="utf-8").splitlines(keepends=True)
    if site.kind == "boundary":
        text = lines[site.line - 1]
        start, end = site.span
        lines[site.line - 1] = text[:start] + site.replacement + text[end:]
    else:
        del lines[site.line - 1 : site.end_line]
    mutated = "".join(lines)
    try:
        ast.parse(mutated)
    except SyntaxError:
        return False
    file.write_text(mutated, encoding="utf-8")
    return True


def _package_dir(worktree: Path) -> str:
    """The directory `coverage` measures: `src/` when it exists, else the tree."""
    return "src" if (worktree / "src").is_dir() else "."


def prepare(clone: Path, out: Path, name: str, log: list[str]) -> tuple[Path, Path, str] | str:
    """Worktree at the tip, a venv with the library and its tests installed."""
    tip = _git(clone, "rev-parse", "origin/HEAD")
    # absolute: `git -C <clone> worktree add <path>` resolves a relative path
    # against the clone, not the caller
    worktree = (out / name / "repo").resolve()
    if not worktree.exists():
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _git(clone, "worktree", "add", "--detach", str(worktree), tip)
    else:
        _git(worktree, "checkout", "-q", "--detach", tip)
        _git(worktree, "checkout", "-q", "--", ".")
    venv = out / name / ".venv"
    python = venv / "bin" / "python"
    if not python.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
        code, text = _run([str(python), "-m", "pip", "install", "-q", "-U", "pip", "pytest",
                           "coverage"], cwd=worktree, timeout=INSTALL_TIMEOUT_S)
        if code != 0:
            return f"pip bootstrap failed: {text[-300:]}"
        installed = False
        for spec in ('.[tests]', '.[test]', '.[dev]', '.'):
            code, text = _run([str(python), "-m", "pip", "install", "-q", "-e", spec],
                              cwd=worktree, timeout=INSTALL_TIMEOUT_S)
            log.append(f"{name}: pip install -e {spec!r} -> {code}")
            if code == 0:
                installed = True
                break
        if not installed:
            return f"install failed: {text[-300:]}"
    # the extras every time, venv new or not: a re-run after a missing test
    # dependency was named must be able to add it. PEP 735 groups first (pip
    # >= 25.1 reads `[dependency-groups]`); a group that does not exist fails
    # quietly and the explicit list below covers it.
    for group in ("tests", "test"):
        code, _ = _run([str(python), "-m", "pip", "install", "-q", "--group", group],
                       cwd=worktree, timeout=INSTALL_TIMEOUT_S)
        log.append(f"{name}: pip install --group {group} -> {code}")
    extras = EXTRA_TEST_DEPS.get(name, [])
    if extras and (extras[0] != "-r" or (worktree / extras[1]).is_file()):
        code, text = _run([str(python), "-m", "pip", "install", "-q", *extras],
                          cwd=worktree, timeout=INSTALL_TIMEOUT_S)
        log.append(f"{name}: extras {extras} -> {code}")
    return worktree, python, tip


def measure(worktree: Path, python: Path, name: str, log: list[str]) -> dict[str, set[int]] | str:
    """The library's own tests under coverage; executed lines per package file."""
    for stale in ("coverage.json", ".coverage"):
        (worktree / stale).unlink(missing_ok=True)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CI": "1"}
    env.pop("PYTHONPATH", None)
    started = time.monotonic()
    # the whole suite, failures and all: coverage is the point, and `-x` would
    # stop measuring at the first failing test
    code, text = _run(
        [str(python), "-m", "coverage", "run", f"--source={_package_dir(worktree)}",
         "-m", "pytest", "-q", "--no-header", "-p", "no:cacheprovider",
         "-o", "addopts=", "-W", "ignore"],
        cwd=worktree, timeout=TEST_TIMEOUT_S, env=env,
    )
    log.append(f"{name}: pytest exit {code} in {time.monotonic() - started:.0f}s")
    if code is None:
        return f"tests {text[:200]}"
    if code not in (0, 1):
        return f"pytest exit {code}: {text[-400:]}"
    # `--fail-under=0`: a project's own `fail_under = 100` must not turn a
    # measurement into a refusal
    code, text = _run([str(python), "-m", "coverage", "json", "-q", "--fail-under=0",
                       "-o", "coverage.json"], cwd=worktree, timeout=300.0, env=env)
    if code != 0 or not (worktree / "coverage.json").is_file():
        return f"coverage json failed: {text[-300:]}"
    data = json.loads((worktree / "coverage.json").read_text(encoding="utf-8"))
    covered: dict[str, set[int]] = {}
    for filename, entry in data.get("files", {}).items():
        rel = os.path.relpath(filename, worktree) if os.path.isabs(filename) else filename
        rel = rel.replace(os.sep, "/")
        if is_package_source(rel):
            covered[rel] = set(int(n) for n in entry.get("executed_lines", []))
    return covered


def mutate_library(
    name: str, clone: Path, out: Path, per_class: int, log: list[str]
) -> dict[str, object]:
    prepared = prepare(clone, out, name, log)
    if isinstance(prepared, str):
        return {"library": name, "skipped": prepared}
    worktree, python, tip = prepared
    covered = measure(worktree, python, name, log)
    if isinstance(covered, str):
        return {"library": name, "tip": tip, "skipped": covered}
    sites: list[Site] = []
    for rel in sorted(covered):
        try:
            source = (worktree / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        sites.extend(_sites_in(source, rel, covered[rel]))
    chosen: list[Site] = []
    for kind in CLASSES:
        of_kind = sorted((s for s in sites if s.kind == kind), key=lambda s: (s.path, s.line))
        chosen.extend(of_kind[:per_class])
    # a re-run of one library replaces its cases rather than leaving stale ones
    for stale in (out / "cases").glob(f"{name}-*"):
        shutil.rmtree(stale, ignore_errors=True)
    cases: list[dict[str, object]] = []
    applied = 0
    for index, site in enumerate(chosen, start=1):
        _git(worktree, "checkout", "-q", "--detach", tip)
        _git(worktree, "checkout", "-q", "--", ".")
        if not _apply(worktree, site):
            log.append(f"{name}: mutation at {site.path}:{site.line} does not parse; skipped")
            continue
        _git(worktree, "-c", "user.email=corpus@attest.invalid", "-c", "user.name=attest corpus",
             "commit", "-q", "-am", f"mutation {site.kind} at {site.path}:{site.line}")
        mutated = _git(worktree, "rev-parse", "HEAD")
        applied += 1
        case_id = f"{name}-{site.kind}-{index:02d}"
        for direction, base, head, shape in (
            ("forward", tip, mutated, "forward: base = original, head = the mutation"),
            ("fix", mutated, tip, "fix: base = the mutation, head = the original"),
        ):
            manifest = {
                "instance_id": f"{case_id}--{direction}",
                "repo": name,
                "repo_path": str(worktree),
                "control": None,
                "base_sha": base,
                "head_sha": head,
                "shape": shape,
                "mutation": asdict(site),
                "project_python": str(python),
                "tip": tip,
            }
            case_dir = out / "cases" / manifest["instance_id"]
            case_dir.mkdir(parents=True, exist_ok=True)
            (case_dir / "manifest.json").write_text(
                json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
            )
            cases.append(manifest)
    _git(worktree, "checkout", "-q", "--detach", tip)
    _git(worktree, "checkout", "-q", "--", ".")
    return {
        "library": name,
        "tip": tip,
        "covered_files": len(covered),
        "covered_lines": sum(len(v) for v in covered.values()),
        "sites_found": {kind: sum(1 for s in sites if s.kind == kind) for kind in CLASSES},
        "mutations_applied": applied,
        "applied_by_class": {kind: sum(1 for s in chosen if s.kind == kind) for kind in CLASSES},
        "cases": len(cases),
        "case_ids": [c["instance_id"] for c in cases],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clones", default=str(ROOT / ".attest" / "corpora" / "gnull"))
    parser.add_argument("--out", default=str(ROOT / ".attest" / "corpora" / "mutations-v1"))
    parser.add_argument("--only", default="")
    parser.add_argument("--per-class", type=int, default=6)
    parser.add_argument("--fresh", action="store_true", help="discard an existing output tree")
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    if args.fresh and out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(LIBRARIES)
    # a partial re-run keeps the other libraries' rows of the report
    previous: dict[str, object] = {"libraries": [], "log": []}
    if (out / "report.json").is_file() and not args.fresh:
        previous = json.loads((out / "report.json").read_text(encoding="utf-8"))
    log: list[str] = list(previous.get("log", []))  # type: ignore[arg-type]
    results: list[dict[str, object]] = [
        row for row in previous.get("libraries", [])  # type: ignore[union-attr]
        if row.get("library") not in names
    ]
    for name in names:
        clone = (Path(args.clones) / name).resolve()
        if not (clone / ".git").is_dir():
            results.append({"library": name, "skipped": f"no clone at {clone}"})
            continue
        started = time.monotonic()
        try:
            result = mutate_library(name, clone, out, args.per_class, log)
        except Exception as exc:  # noqa: BLE001 - one library must not end the corpus
            result = {"library": name, "skipped": f"{type(exc).__name__}: {str(exc)[:300]}"}
        result["elapsed_s"] = round(time.monotonic() - started, 1)
        results.append(result)
        results.sort(key=lambda row: str(row.get("library")))
        print(json.dumps(result), flush=True)
        (out / "report.json").write_text(
            json.dumps({"libraries": results, "log": log}, indent=2) + "\n", encoding="utf-8"
        )
    manifests = sorted(out.glob("cases/*/manifest.json"))
    with (out / "manifest.jsonl").open("w", encoding="utf-8") as handle:
        for path in manifests:
            handle.write(json.dumps(json.loads(path.read_text(encoding="utf-8"))) + "\n")
    print(f"{len(manifests)} cases -> {out / 'manifest.jsonl'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
