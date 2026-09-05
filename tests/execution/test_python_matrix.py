"""Which interpreter a reproduction runs on, and why (D-162).

The declared range is **3.10-3.13**. The version is the highest supported one
the tree's own declaration allows: the newest `Programming Language :: Python
:: 3.X` classifier is a ceiling, and the strictest lower bound is a floor --
taken from `requires-python` **or from a lock file**, because a project that
pins its interpreter in `uv.lock`, `poetry.lock` or `Pipfile` and nowhere else
has still said what it needs.

A tree that names nothing usable gets the **primary**, 3.12 -- the version this
project is itself built and shipped on. A floor below 3.10 does not reach back
for 3.9: the supported range is the supported range, and a project that cannot
install on 3.10 is a bootstrap DEFER with its reason, never a finding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attest.execution.container_images import (
    AVAILABLE_PYTHONS,
    PRIMARY_PYTHON,
    project_python,
)


def _tree(path: Path, **files: str) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    for name, body in files.items():
        (path / name.replace("__", ".")).write_text(body, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("floor", "expected"),
    (("3.13", "3.13"), ("3.12", "3.13"), ("3.10", "3.13")),
)
def test_requires_python_selects_within_the_supported_range(
    tmp_path: Path, floor: str, expected: str
) -> None:
    tree = _tree(
        tmp_path / floor.replace(".", "_"),
        pyproject__toml=f'[project]\nname = "x"\nrequires-python = ">={floor}"\n',
    )

    version, reason = project_python(tree)

    assert version == expected
    assert f"declared floor >= {floor}" in reason


@pytest.mark.parametrize(
    ("ceiling", "expected"),
    (("3.10", "3.10"), ("3.11", "3.11"), ("3.12", "3.12")),
)
def test_a_classifier_ceiling_picks_that_interpreter(
    tmp_path: Path, ceiling: str, expected: str
) -> None:
    """Three synthetic trees with three different declarations select three
    different interpreters -- the owner's RED for this item."""
    tree = _tree(
        tmp_path / ceiling.replace(".", "_"),
        setup__py=(
            "from setuptools import setup\nsetup(classifiers=["
            f'"Programming Language :: Python :: {ceiling}"])\n'
        ),
    )

    version, reason = project_python(tree)

    assert version == expected
    assert f"classifiers up to {ceiling}" in reason


@pytest.mark.parametrize(
    ("name", "body"),
    (
        ("uv.lock", 'requires-python = ">=3.13"\n'),
        ("poetry.lock", '[metadata]\npython-versions = ">=3.13,<4.0"\n'),
        ("Pipfile", '[requires]\npython_version = "3.13"\n'),
    ),
)
def test_a_lock_file_alone_states_the_floor(tmp_path: Path, name: str, body: str) -> None:
    tree = tmp_path / name.replace(".", "_")
    tree.mkdir(parents=True)
    (tree / "pyproject.toml").write_text('[project]\nname = "x"\n', encoding="utf-8")
    (tree / name).write_text(body, encoding="utf-8")

    version, reason = project_python(tree)

    assert version == "3.13"
    assert "declared floor >= 3.13" in reason


def test_a_tree_that_says_nothing_gets_the_primary(tmp_path: Path) -> None:
    tree = _tree(tmp_path / "silent", app__py="x = 1\n")

    version, reason = project_python(tree)

    assert version == PRIMARY_PYTHON == "3.12"
    assert "primary" in reason


def test_a_declaration_below_the_supported_range_does_not_reach_back_for_39(
    tmp_path: Path,
) -> None:
    tree = _tree(
        tmp_path / "old",
        setup__py=(
            "from setuptools import setup\nsetup(classifiers=["
            '"Programming Language :: Python :: 3.7"])\n'
        ),
    )

    version, reason = project_python(tree)

    assert version == PRIMARY_PYTHON
    assert "outside 3.10-3.13" in reason
    assert "3.9" not in AVAILABLE_PYTHONS


def test_the_supported_matrix_is_exactly_310_to_313() -> None:
    assert AVAILABLE_PYTHONS == ("3.13", "3.12", "3.11", "3.10")
