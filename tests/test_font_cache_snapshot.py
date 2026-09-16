"""An image cache cannot hide filesystem objects outside its digest manifest."""

import os
import sys
from pathlib import Path

import pytest

from attest.benchmark.artifacts import sha256_bytes

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/corpus"))
from swebench_source_runtime import font_cache_digests  # noqa: E402


@pytest.fixture
def cache(tmp_path: Path) -> Path:
    (tmp_path / "font.json").write_bytes(b"{}")
    return tmp_path


@pytest.mark.parametrize("kind", ["fifo", "link", "excessive"])
def test_unrecorded_or_oversized_cache_refuses(cache: Path, kind: str) -> None:
    path = cache / "extra"
    if kind == "fifo":
        os.mkfifo(path)
    elif kind == "link":
        path.symlink_to("font.json")
    else:
        with path.open("wb") as stream:
            stream.truncate(8 * 1024 * 1024 + 1)
    with pytest.raises(ValueError):
        font_cache_digests(cache)
    assert (cache / "font.json").read_bytes() == b"{}"


def test_regular_cache_is_completely_bound(cache: Path) -> None:
    assert font_cache_digests(cache) == {"font.json": sha256_bytes(b"{}")}
