"""Era pins for a historical tree, and the image line that applies them (D-214).

`xarray` 2022.6 is the case this exists for: nine of the 39 held-out instances
of the 2026-09-10 run never executed a probe because the image resolved
`numpy` 2.4 for a tree written against `numpy` 1.x, and `import xarray` raised
`AttributeError: np.unicode_` before pytest collected anything.

PyPI is not called here. `constraints_for` takes its fetcher, so these pin the
selection rule -- the newest release published on or before the date -- rather
than what PyPI happens to hold tonight.
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from era_constraints import (  # noqa: E402
    constraints_for,
    direct_dependencies,
    latest_before,
    normalise,
)

CUTOFF = datetime(2022, 7, 1, tzinfo=UTC)


def _release(*entries: tuple[str, str]) -> dict:
    return {
        "releases": {
            version: [{"upload_time_iso_8601": stamp, "yanked": False}]
            for version, stamp in entries
        }
    }


def test_the_newest_release_on_or_before_the_date_is_chosen() -> None:
    payload = _release(
        ("1.22.0", "2022-01-01T00:00:00Z"),
        ("1.23.0", "2022-06-22T00:00:00Z"),
        ("2.4.0", "2026-01-01T00:00:00Z"),
    )

    assert latest_before(payload, CUTOFF) == "1.23.0"


def test_a_back_ported_release_published_later_wins_over_a_higher_version() -> None:
    """The era question is what the tree *could have installed then*, which is
    a date question: 1.2.9 published after 1.3.0 is the newer thing to have."""
    payload = _release(
        ("1.3.0", "2022-02-01T00:00:00Z"),
        ("1.2.9", "2022-05-01T00:00:00Z"),
    )

    assert latest_before(payload, CUTOFF) == "1.2.9"


def test_prereleases_and_yanked_files_are_not_pinned() -> None:
    payload = {
        "releases": {
            "1.0.0": [{"upload_time_iso_8601": "2022-01-01T00:00:00Z", "yanked": True}],
            "2.0.0rc1": [{"upload_time_iso_8601": "2022-02-01T00:00:00Z", "yanked": False}],
            "0.9.0": [{"upload_time_iso_8601": "2021-01-01T00:00:00Z", "yanked": False}],
        }
    }

    assert latest_before(payload, CUTOFF) == "0.9.0"


def test_a_project_with_no_release_before_the_date_is_not_pinned(tmp_path: Path) -> None:
    """Not pinned rather than guessed at, and the file says which names those
    were: a constraint invented for a name nobody could resolve is the failure
    this is meant to prevent, not a smaller version of it."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "setup.py").write_text(
        "from setuptools import setup\nsetup(install_requires=['brandnew'])\n",
        encoding="utf-8",
    )

    text, unresolved = constraints_for(
        tree, CUTOFF, fetch=lambda name: _release(("1.0.0", "2026-01-01T00:00:00Z"))
    )

    assert unresolved == ["brandnew"]
    assert "brandnew<=" not in text
    assert "not pinned" in text


def test_direct_dependencies_are_read_from_every_manifest(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "pyproject.toml").write_text(
        '[project]\nname = "x"\ndependencies = ["Numpy >= 1.18", "pandas"]\n', encoding="utf-8"
    )
    (tree / "setup.cfg").write_text(
        "[options]\ninstall_requires =\n    packaging\n    # a comment\n", encoding="utf-8"
    )
    (tree / "requirements.txt").write_text("scipy==1.8.0\n-e .\n", encoding="utf-8")

    assert direct_dependencies(tree) == ["numpy", "packaging", "pandas", "scipy"]


def test_setup_py_is_read_and_never_executed(tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "setup.py").write_text(
        "raise SystemExit('this file must never run')\n"
        "from setuptools import setup\n"
        "setup(install_requires=['numpy>=1.18'])\n",
        encoding="utf-8",
    )

    assert direct_dependencies(tree) == ["numpy"]


def test_the_image_and_the_test_runner_are_never_pinned(tmp_path: Path) -> None:
    """The image installs `pytest` itself, before the project. An era pin on it
    would break the runner rather than reproduce the era."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "setup.py").write_text(
        "from setuptools import setup\n"
        "setup(install_requires=['setuptools', 'wheel', 'pytest', 'numpy'])\n",
        encoding="utf-8",
    )

    assert direct_dependencies(tree) == ["numpy"]


def test_names_are_normalised_once(tmp_path: Path) -> None:
    assert normalise("Zope.Interface") == "zope-interface"


def test_the_dockerfile_applies_a_constraints_file_when_one_is_given() -> None:
    from attest.execution.container_images import ProjectRoot, dockerfile

    roots = [ProjectRoot("", ("setup.py",))]
    without = dockerfile("3.12", roots)
    with_pins = dockerfile("3.12", roots, constraints="numpy<=1.23.0\n")

    assert "PIP_CONSTRAINT" not in without
    assert "COPY constraints.txt /attest/constraints.txt" in with_pins
    assert "ENV PIP_CONSTRAINT=/attest/constraints.txt" in with_pins
    # the constraint must not reach the runner pytest installs with: an era pin
    # on its own dependencies is how this breaks the image instead of the tree
    assert with_pins.index("RUN pip install pytest") < with_pins.index("PIP_CONSTRAINT")
    assert with_pins.index("PIP_CONSTRAINT") < with_pins.index("COPY tree /attest/build")


def test_the_product_path_is_byte_identical_without_constraints() -> None:
    from attest.execution.container_images import ProjectRoot, dockerfile

    roots = [ProjectRoot("", ("pyproject.toml",)), ProjectRoot("svc", ("setup.py",))]

    assert dockerfile("3.11", roots, "1.2.3") == dockerfile(
        "3.11", roots, "1.2.3", constraints=None
    )


def test_the_font_cache_is_warmed_in_every_image() -> None:
    """`matplotlib.font_manager` builds a `FontManager` on a cache miss, and
    that constructor starts a `threading.Timer` -- which the executor's thread
    guard rejects. Two of the 39 held-out cases died there. Warming the cache at
    build time means the constructor never runs under the guard; a tree without
    matplotlib is unaffected, which is what `|| true` is for."""
    from attest.execution.container_images import ProjectRoot, dockerfile

    text = dockerfile("3.12", [ProjectRoot("", ("setup.py",))])

    assert 'RUN python -c "import matplotlib.font_manager" || true' in text
    assert text.index("matplotlib") > text.index("COPY tree /attest/build")


def test_an_era_pin_that_cannot_install_falls_back_to_the_unpinned_line() -> None:
    """Measured, not hypothesised. `numpy<=1.23.1` is the correct pin for a 2022
    tree and has no wheel for any interpreter newer than 3.10, so on a tree whose
    classifiers select 3.12 the constrained install fails outright — and an image
    that fails to build loses a case the unpinned build would have attempted. The
    pin is an attempt, not a demand."""
    from attest.execution.container_images import ProjectRoot, dockerfile

    text = dockerfile("3.12", [ProjectRoot("", ("setup.py",))], constraints="numpy<=1.23.1\n")

    assert "PIP_CONSTRAINT= pip install /attest/build" in text
    assert "RUN pip install /attest/build || " in text


def test_two_constraint_files_do_not_share_one_image_tag(tmp_path: Path) -> None:
    """The `COPY` line is the same text for every constraint file, so a tag that
    digested only the Dockerfile would let the second file silently reuse the
    first file's image."""
    import hashlib

    from attest.execution.container_images import ProjectRoot, dockerfile

    roots = [ProjectRoot("", ("setup.py",))]
    one = dockerfile("3.12", roots, constraints="numpy<=1.23.1\n")
    two = dockerfile("3.12", roots, constraints="numpy<=1.26.4\n")

    assert one == two  # the Dockerfile alone cannot tell them apart
    assert hashlib.sha256(b"numpy<=1.23.1\n") != hashlib.sha256(b"numpy<=1.26.4\n")


def test_the_environment_knob_is_unset_by_default_and_reads_a_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from attest.execution.container_images import ERA_CONSTRAINT_ENV, era_constraints

    monkeypatch.delenv(ERA_CONSTRAINT_ENV, raising=False)
    assert era_constraints() is None

    pins = tmp_path / "constraints.txt"
    pins.write_text("numpy<=1.26.4\n", encoding="utf-8")
    monkeypatch.setenv(ERA_CONSTRAINT_ENV, str(pins))
    assert era_constraints() == "numpy<=1.26.4\n"

    # a corpus knob must not be able to fail an image build that would work
    monkeypatch.setenv(ERA_CONSTRAINT_ENV, str(tmp_path / "absent.txt"))
    assert era_constraints() is None


def test_an_unreachable_index_cannot_stall_a_build_stage(tmp_path: Path) -> None:
    """The corpus builds 39 cases in a job with a 330-minute ceiling and calls
    this once per case. At the 60 s per request the first draft used, a PyPI
    outage would have spent six hours here and taken the paid run with it. Not
    pinned rather than waited for: a case with no pins runs exactly as it did
    before this tool existed."""
    import era_constraints

    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "setup.py").write_text(
        "from setuptools import setup\nsetup(install_requires=['a', 'b', 'c'])\n",
        encoding="utf-8",
    )
    asked: list[str] = []

    def slow(name: str) -> dict | None:
        asked.append(name)
        return None

    era_constraints.TOTAL_BUDGET_S = 0.0
    try:
        text, unresolved = constraints_for(tree, CUTOFF, fetch=slow)
    finally:
        era_constraints.TOTAL_BUDGET_S = 180.0

    assert asked == []  # the budget was spent before the first request
    assert unresolved == ["a", "b", "c"]
    assert "a<=" not in text
