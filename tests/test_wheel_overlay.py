"""Generated artifacts cannot overwrite source or cross revision identities."""

import sys
from pathlib import Path
from zipfile import ZipFile, ZipInfo

import pytest

from attest.benchmark.artifacts import sha256_bytes

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/corpus"))
from wheel_overlay import apply_wheel  # noqa: E402


@pytest.fixture
def wheel_tree(tmp_path: Path) -> tuple[Path, Path]:
    tree = tmp_path / "tree"
    (tree / "pkg").mkdir(parents=True)
    (tree / "pkg/__init__.py").write_bytes(b"VALUE = 1\n")
    return tree, tmp_path / "fixture.whl"


@pytest.mark.parametrize(
    "kind", ["revision", "digest", "overwrite", "traversal", "symlink", "python", "collision"]
)
def test_refuses_before_any_transfer(wheel_tree: tuple[Path, Path], kind: str) -> None:
    tree, wheel = wheel_tree
    with ZipFile(wheel, "w") as z:
        z.writestr("pkg/native.so", b"fixture native bytes")
        if kind == "overwrite":
            z.writestr("pkg/__init__.py", b"VALUE = 2\n")
        elif kind == "traversal":
            z.writestr("../escape.so", b"escape")
        elif kind == "symlink":
            info = ZipInfo("pkg/link.so")
            info.external_attr = 0o120777 << 16
            z.writestr(info, "../escape")
        elif kind == "python":
            z.writestr("pkg/injected.py", b"VALUE = 2\n")
        elif kind == "collision":
            z.writestr("pkg/native.so/other.so", b"nested native bytes")
    with pytest.raises(ValueError):
        apply_wheel(
            tree, wheel, revision="a" * 40,
            expected_revision=("b" if kind == "revision" else "a") * 40,
            expected_digest="wrong" if kind == "digest" else sha256_bytes(wheel.read_bytes()),
            packages=("pkg",),
        )
    assert not (tree / "pkg/native.so").exists()
    assert (tree / "pkg/__init__.py").read_bytes() == b"VALUE = 1\n"


def test_generated_additions_preserve_source(wheel_tree: tuple[Path, Path]) -> None:
    tree, wheel = wheel_tree
    with ZipFile(wheel, "w") as z:
        z.writestr("pkg/__init__.py", b"VALUE = 1\n")
        z.writestr("pkg/native.so", b"fixture native bytes")
        z.writestr("pkg/_version.py", b"version = '0.1'\n")
        z.writestr("fixture-0.1.dist-info/METADATA", b"Name: fixture\n")
    result = apply_wheel(
        tree, wheel, revision="a" * 40, expected_revision="a" * 40,
        expected_digest=sha256_bytes(wheel.read_bytes()), packages=("pkg",),
        version_path="pkg/_version.py",
    )
    assert set(result["added"]) == {"pkg/native.so", "pkg/_version.py"}
    assert (tree / "pkg/__init__.py").read_bytes() == b"VALUE = 1\n"
