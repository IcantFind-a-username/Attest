"""The distribution is part of the gate, not an afterthought at tag time (7.1).

A metadata mistake that first shows up when someone tries to install the release
is the kind of failure a tag cannot take back. So the wheel and the sdist are
built in CI on every push, the built wheel's CLI is run from a clean
environment, and these tests pin the metadata a package index and a human both
read: what it is, who owns it, where the docs are, which interpreters it claims.

They read `pyproject.toml`, not the installed distribution, so they hold in a
source checkout that was never built.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

import attest

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
PROJECT = PYPROJECT["project"]


def test_the_version_in_the_package_and_in_the_metadata_are_one_number() -> None:
    """Two versions is a release nobody can identify."""
    assert attest.__version__ == PROJECT["version"]


@pytest.mark.parametrize(
    "field", ("name", "version", "description", "readme", "requires-python", "license")
)
def test_the_metadata_a_package_index_requires_is_present(field: str) -> None:
    assert PROJECT.get(field)


def test_the_description_says_what_the_product_does() -> None:
    description = PROJECT["description"]
    assert 20 < len(description) <= 120
    assert not description.endswith(".")


def test_the_urls_point_at_this_repository() -> None:
    urls = PROJECT["urls"]
    assert set(urls) >= {"Homepage", "Repository", "Documentation", "Changelog", "Issues"}
    for value in urls.values():
        assert value.startswith("https://github.com/IcantFind-a-username/Attest")


def test_the_classifiers_declare_the_licence_and_the_supported_interpreters() -> None:
    classifiers = PROJECT["classifiers"]
    assert "License :: OSI Approved :: Apache Software License" in classifiers
    declared = {
        line.rsplit(" :: ", 1)[-1]
        for line in classifiers
        if line.startswith("Programming Language :: Python :: 3.")
    }
    # what the package claims to run on, against what `requires-python` allows
    assert declared == {"3.11", "3.12", "3.13"}
    assert PROJECT["requires-python"] == ">=3.11"
    assert any(line.startswith("Development Status ::") for line in classifiers)


def test_the_licence_file_the_metadata_names_exists() -> None:
    assert PROJECT["license"] == "Apache-2.0"
    assert (ROOT / "LICENSE").is_file()
    assert "Apache License" in (ROOT / "LICENSE").read_text(encoding="utf-8")[:2000]


def test_the_console_script_points_at_a_callable_that_exists() -> None:
    target = PROJECT["scripts"]["attest"]
    module_name, _, attribute = target.partition(":")
    module = __import__(module_name, fromlist=[attribute])

    assert callable(getattr(module, attribute))


def test_the_sdist_carries_what_makes_the_claims_checkable() -> None:
    """A source distribution of an evidence-first product that ships without its
    decisions, its acceptance evidence or its spend ledger is a binary with a
    licence file."""
    include = PYPROJECT["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]

    assert {"src/attest", "tests", "docs", "DECISIONS.md", "DEVSPEND.md"} <= set(include)
    for entry in include:
        assert (ROOT / entry).exists(), f"the sdist names {entry}, which is not in the tree"
