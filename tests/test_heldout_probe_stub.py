"""The evaluability probe's stub must actually import the project (D-213).

The stub the held-out driver collects inside the base image was
``assert True``. It never imported the tree, so it answered *does pytest
collect here* and nothing else -- and a tree whose own package does not import
under the image's resolved dependencies collected that stub perfectly well and
was planned, bought and then lost, three container runs later, as
``probe deferred on base``.

Nine of the 39 cases of the 2026-09-10 run died that way on one project. The
stub now imports every top-level package the tree defines, so a tree that
cannot import is refused in the free stage, before any model is asked anything.
This is the fourth instance of D-177's pattern: a stage that reports a zero
without asserting that its own input was there.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from heldout_v2 import probe_stub_source, stub_packages  # noqa: E402


def _collect(tree: Path) -> subprocess.CompletedProcess[str]:
    run_dir = tree / ".attest-run"
    run_dir.mkdir(exist_ok=True)
    (run_dir / "test_repro.py").write_text(probe_stub_source(tree), encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            str(run_dir / "test_repro.py"),
            "--collect-only",
            "--rootdir",
            str(tree),
            "--confcutdir",
            str(tree),
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        cwd=tree,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(tree), "HOME": str(tree)},
    )


def _tree(tmp_path: Path, body: str) -> Path:
    tree = tmp_path / "tree"
    (tree / "widget").mkdir(parents=True)
    (tree / "widget" / "__init__.py").write_text(body, encoding="utf-8")
    (tree / "setup.py").write_text("from setuptools import setup\nsetup()\n", encoding="utf-8")
    return tree


def test_the_stub_names_the_packages_the_tree_defines(tmp_path: Path) -> None:
    tree = _tree(tmp_path, "VALUE = 1\n")

    assert stub_packages(tree) == ["widget"]
    assert "import widget" in probe_stub_source(tree)


def test_a_tree_whose_package_does_not_import_fails_the_stub(tmp_path: Path) -> None:
    """The xarray shape: the package itself raises on import under the
    dependencies the image resolved. The old stub collected; this one does not."""
    tree = _tree(tmp_path, "raise AttributeError('np.unicode_ was removed')\n")

    done = _collect(tree)

    assert done.returncode != 0, done.stdout
    assert "np.unicode_ was removed" in done.stdout + done.stderr


def test_a_tree_whose_package_imports_still_collects(tmp_path: Path) -> None:
    tree = _tree(tmp_path, "VALUE = 1\n")

    done = _collect(tree)

    assert done.returncode == 0, done.stdout + done.stderr
    assert "1 test" in done.stdout


def test_a_tree_that_defines_no_package_is_not_silently_reported_as_importable(
    tmp_path: Path,
) -> None:
    """D-177 on the harness itself: an empty package list is stated, not hidden
    behind a stub that passes for a tree it never touched."""
    tree = tmp_path / "bare"
    tree.mkdir()

    assert stub_packages(tree) == []
    assert "no top-level package" in probe_stub_source(tree)
