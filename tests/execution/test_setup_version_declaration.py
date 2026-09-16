"""Experimental metadata discovery never executes a setup module."""

from pathlib import Path

import pytest

from attest.execution.container_images import declared_version_file, discover_roots


@pytest.mark.parametrize(
    "body,expected",
    [
        ("setup(use_scm_version={'write_to': 'lib/pkg/_version.py'})", True),
        ("setup(use_scm_version={'write_to': '../outside.py'})", False),
        ("setup(use_scm_version={'write_to': '/outside.py'})", False),
        ("setup(use_scm_version={'write_to': value()})", False),
        ("setup(use_scm_version=options)", False),
        ("if False:\n    setup(use_scm_version={'write_to': 'lib/pkg/_version.py'})", False),
        ("setup = other\nsetup(use_scm_version={'write_to': 'lib/pkg/_version.py'})", False),
        ("setup(use_scm_version={'write_to': 'a.py', 'write_to': 'b.py'})", False),
        ("setup(use_scm_version={'write_to': 'a.py'})\nsetup()", False),
    ],
)
def test_literal_setup_metadata_is_opt_in(tmp_path: Path, body: str, expected: bool) -> None:
    (tmp_path / "setup.py").write_text("from setuptools import setup\n" + body + "\n")
    roots = discover_roots(tmp_path)
    assert declared_version_file(tmp_path, roots) is None
    assert declared_version_file(tmp_path, roots, allow_setup_py=True) == (
        tmp_path / "lib/pkg/_version.py" if expected else None
    )


def test_setup_module_is_not_executed(tmp_path: Path) -> None:
    (tmp_path / "setup.py").write_text(
        "from setuptools import setup\nraise RuntimeError('do not execute')\n"
        "setup(use_scm_version={'write_to':'lib/pkg/_version.py'})\n"
    )
    assert declared_version_file(tmp_path, discover_roots(tmp_path), allow_setup_py=True) is None


@pytest.mark.parametrize("imports", [
    "from setuptools import setup, find_packages as setup",
    "from setuptools import setup, setup",
    "from setuptools import setup\nfrom other import setup",
    "from setuptools import setup\nfrom other import *",
])
def test_ambiguous_imports_refuse(tmp_path: Path, imports: str) -> None:
    (tmp_path / "setup.py").write_text(
        imports + "\nsetup(use_scm_version={'write_to':'lib/pkg/_version.py'})\n"
    )
    assert declared_version_file(tmp_path, discover_roots(tmp_path), allow_setup_py=True) is None
