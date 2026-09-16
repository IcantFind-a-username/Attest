"""An oracle overlay must not modify source through an in-tree link."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/corpus"))
from natural_pair_original_tests import overlay_original_test  # noqa: E402


@pytest.mark.parametrize("kind", ["file_link", "directory_link", "parent_path", "regular"])
def test_original_test_overlay_preserves_other_source(tmp_path: Path, kind: str) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b"SOURCE = 1\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    target = tests / "test_original.py"
    target.write_bytes(b"def test_original(): pass\n")
    path = "tests/test_original.py"
    if kind == "file_link":
        target.unlink()
        target.symlink_to("../source.py")
    elif kind == "directory_link":
        (tmp_path / "alias").symlink_to("tests", target_is_directory=True)
        path = "alias/test_original.py"
    elif kind == "parent_path":
        path = "tests/../source.py"
    if kind == "regular":
        overlay_original_test(tmp_path, path, b"ORACLE = 1\n")
        assert target.read_bytes() == b"ORACLE = 1\n"
    else:
        with pytest.raises(ValueError, match="unsafe original-test"):
            overlay_original_test(tmp_path, path, b"ORACLE = 1\n")
    assert source.read_bytes() == b"SOURCE = 1\n"
