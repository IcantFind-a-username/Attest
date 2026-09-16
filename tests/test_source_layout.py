"""Source layouts must import and receive build artifacts in the same tree."""

import sys
from pathlib import Path
from zipfile import ZipFile

import pytest

from attest.benchmark.artifacts import sha256_bytes
from attest.review.executor import project_roots

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/corpus"))
from heldout_v2 import stub_packages  # noqa: E402
from wheel_overlay import apply_wheel  # noqa: E402


@pytest.mark.parametrize("prefix", ["", "src", "lib", "services/worker/lib"])
def test_layout_import_roots(tmp_path: Path, prefix: str) -> None:
    package = tmp_path / prefix / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("VALUE = 7\n")
    (tmp_path / "pyproject.toml").write_text("")
    if prefix.startswith("services/"):
        (tmp_path / "services/worker/setup.py").write_text("")
    expected = "{tree}" + ("/" + prefix if prefix else "")
    assert expected in project_roots(tmp_path)
    assert stub_packages(tmp_path) == ["example"]


@pytest.mark.parametrize("prefix", ["", "src", "lib"])
def test_wheel_targets_source_layout(tmp_path: Path, prefix: str) -> None:
    source = tmp_path / "tree"
    package = source / prefix / "example"
    package.mkdir(parents=True)
    (package / "__init__.py").write_bytes(b"VALUE = 7\n")
    (source / prefix / "helper.py").write_bytes(b"VALUE = 8\n")
    wheel = tmp_path / "fixture.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("example/__init__.py", b"VALUE = 7\n")
        archive.writestr("example/native.so", b"native fixture")
        archive.writestr("helper.py", b"VALUE = 8\n")
    result = apply_wheel(
        source, wheel, revision="a", expected_revision="a",
        expected_digest=sha256_bytes(wheel.read_bytes()), packages=("example",),
        source_prefix=prefix,
    )
    assert (package / "native.so").read_bytes() == b"native fixture"
    assert (package / "__init__.py").read_bytes() == b"VALUE = 7\n"
    assert set(result["added"]) == {(Path(prefix) / "example/native.so").as_posix()}
    if prefix:
        assert not (source / "example").exists()


@pytest.mark.parametrize("prefix", ["../outside", "/tmp", "lib/../lib", "link", "lib/alias"])
def test_wheel_refuses_unsafe_source_prefix(tmp_path: Path, prefix: str) -> None:
    tree = tmp_path / "tree"
    (tree / "lib").mkdir(parents=True)
    (tree / "link").symlink_to("lib", target_is_directory=True)
    (tree / "lib/alias").symlink_to(".", target_is_directory=True)
    wheel = tmp_path / "fixture.whl"
    with ZipFile(wheel, "w") as archive:
        archive.writestr("example/native.so", b"native fixture")
    with pytest.raises(ValueError, match="unsafe source prefix"):
        apply_wheel(
            tree, wheel, revision="a", expected_revision="a",
            expected_digest=sha256_bytes(wheel.read_bytes()), packages=("example",),
            source_prefix=prefix, allow_source_links=True,
        )
    assert not list(tree.rglob("*.so"))
