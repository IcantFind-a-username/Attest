"""Pin a tree's direct dependencies to the era of its own base commit (D-214).

The image the product builds runs `pip install /attest/build` with no
constraint on anything, so a 2022 tree resolves today's dependencies. Nine of
the 39 cases of the 2026-09-10 held-out run died of exactly that: `xarray`
2022.6 with `numpy` 2.4 raises `AttributeError: np.unicode_` at import, pytest
exits 2 at collection, and the probe never reaches the code under review. The
same tree with `numpy` 1.26 collects normally under every guard.

This writes a `constraints.txt` for a tree and a date: for each **direct**
dependency the tree declares, the last version published on or before that
date. Transitive dependencies are left alone -- pip resolves those against the
pins, which is the whole point of a constraint file -- and a name that cannot
be resolved on PyPI is not pinned rather than guessed at.

**It is a corpus tool, not a product path.** The product reviews a pull request
against today's dependencies because that is what the repository's own CI does;
a historical corpus is the case where "today" is the wrong answer, and this is
what makes that case measurable.
"""

from __future__ import annotations

import argparse
import ast
import configparser
import json
import re
import sys
import tomllib
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from datetime import datetime
from pathlib import Path

PYPI = "https://pypi.org/pypi/{name}/json"
# PEP 508 far enough for a distribution name: everything before the first
# version specifier, extra, marker or comment.
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")
# never pinned: the build backend and the test runner the image installs itself,
# whose era pin would break the image rather than the project
EXCLUDED = frozenset({"setuptools", "wheel", "pip", "pytest"})


def normalise(name: str) -> str:
    """PEP 503 normalisation, so `Pillow` and `pillow` are one name."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _names(requirements: Iterable[str]) -> list[str]:
    found = []
    for line in requirements:
        text = line.split("#", 1)[0].strip()
        if not text or text.startswith("-"):
            continue
        match = _NAME.match(text)
        if match:
            found.append(normalise(match.group(1)))
    return found


def _from_pyproject(text: str) -> list[str]:
    try:
        data = tomllib.loads(text)
    except (tomllib.TOMLDecodeError, ValueError):
        return []
    found = _names(data.get("project", {}).get("dependencies", []) or [])
    poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry, dict):
        found += [normalise(name) for name in poetry if name.lower() != "python"]
    return found


def _from_setup_py(text: str) -> list[str]:
    """`install_requires` read from the source, never by executing it."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "install_requires":
            with_literals = node.value
            try:
                value = ast.literal_eval(with_literals)
            except (ValueError, SyntaxError):
                continue
            if isinstance(value, str):
                value = value.splitlines()
            if isinstance(value, list | tuple):
                found += _names(str(item) for item in value)
    return found


def _from_setup_cfg(text: str) -> list[str]:
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text)
    except configparser.Error:
        return []
    if not parser.has_option("options", "install_requires"):
        return []
    return _names(parser.get("options", "install_requires").splitlines())


def direct_dependencies(tree: Path) -> list[str]:
    """Every distribution the tree names as its own runtime dependency."""
    found: list[str] = []
    readers: tuple[tuple[str, Callable[[str], list[str]]], ...] = (
        ("pyproject.toml", _from_pyproject),
        ("setup.py", _from_setup_py),
        ("setup.cfg", _from_setup_cfg),
    )
    for name, reader in readers:
        path = tree / name
        if path.is_file():
            found += reader(path.read_text(errors="replace"))
    for path in sorted(tree.glob("requirements*.txt")):
        found += _names(path.read_text(errors="replace").splitlines())
    return sorted({name for name in found if name not in EXCLUDED})


def _fetch(name: str) -> dict | None:
    try:
        with urllib.request.urlopen(PYPI.format(name=name), timeout=60) as response:
            return json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None


def latest_before(payload: dict, cutoff: datetime) -> str | None:
    """The newest release of `payload` first published on or before `cutoff`.

    Ordered by release date, not by version: a project that back-ports to an
    older series publishes 1.2.9 after 1.3.0, and the era question is *what
    could this tree have installed then*, which is a date question.
    """
    from packaging.version import InvalidVersion, Version

    best: tuple[datetime, Version] | None = None
    for version, files in (payload.get("releases") or {}).items():
        stamps = [
            datetime.fromisoformat(entry["upload_time_iso_8601"].replace("Z", "+00:00"))
            for entry in files or []
            if not entry.get("yanked") and entry.get("upload_time_iso_8601")
        ]
        if not stamps:
            continue
        published = min(stamps)
        if published > cutoff:
            continue
        try:
            parsed = Version(version)
        except InvalidVersion:
            continue
        if parsed.is_prerelease or parsed.is_devrelease:
            continue
        if best is None or published > best[0]:
            best = (published, parsed)
    return None if best is None else str(best[1])


def constraints_for(
    tree: Path, cutoff: datetime, *, fetch: Callable[[str], dict | None] = _fetch
) -> tuple[str, list[str]]:
    """(the constraints file's text, the names that could not be pinned)."""
    lines: list[str] = []
    unresolved: list[str] = []
    for name in direct_dependencies(tree):
        payload = fetch(name)
        version = None if payload is None else latest_before(payload, cutoff)
        if version is None:
            unresolved.append(name)
            continue
        lines.append(f"{name}<={version}")
    header = [
        f"# direct dependencies as of {cutoff.date().isoformat()}, from PyPI release dates",
        "# generated by scripts/corpus/era_constraints.py; a corpus tool, not a product path",
    ]
    if unresolved:
        header.append(
            "# not pinned (no release found on or before the date): "
            + ", ".join(unresolved)
        )
    return "\n".join([*header, *lines]) + "\n", unresolved


def _cutoff(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        from datetime import UTC

        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tree", type=Path)
    parser.add_argument("date", help="the base commit's date, ISO 8601")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    text, unresolved = constraints_for(args.tree, _cutoff(args.date))
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
        print(f"wrote {args.output} ({len(text.splitlines())} lines)")
    if unresolved:
        print(f"not pinned: {', '.join(unresolved)}", file=sys.stderr)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI
    raise SystemExit(main())
