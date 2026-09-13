"""D-245: the tree index resolves calls through imports, orders files by import
distance, and lists the literals the tree passes to a symbol."""

from __future__ import annotations

import json
import os
from pathlib import Path

from attest.review.index import (
    ATTRIBUTE,
    EXACT,
    INDEX_DIR,
    build_index,
    module_name,
    tree_index,
    tree_key,
)


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _fixture(root: Path) -> None:
    _write(root, "src/pkg/__init__.py", "")
    _write(
        root,
        "src/pkg/reader.py",
        "class Reader:\n"
        "    def parse(self, text):\n"
        "        return self.clean(text)\n\n"
        "    def clean(self, text):\n"
        "        return text.strip()\n\n\n"
        "def limit(n, strict=False):\n"
        "    return n\n\n\n"
        "def twice(n):\n"
        "    return limit(n) * 2\n",
    )
    _write(
        root,
        "src/pkg/app.py",
        "from pkg.reader import Reader, limit\n\n\n"
        "def load(text):\n"
        "    limit(0)\n"
        "    limit(-1, strict=True)\n"
        "    return Reader().parse(text)\n",
    )
    _write(
        root,
        "src/pkg/alias.py",
        "import pkg.reader as reader\n\n\n"
        "def run():\n"
        "    return reader.limit(0)\n",
    )
    _write(
        root,
        "src/pkg/relative.py",
        "from .reader import limit\n\n\ndef go(r):\n    limit([])\n    return r.parse('x')\n",
    )
    _write(
        root,
        "src/pkg/other.py",
        "import json\n\n\ndef decode(text):\n    return json.JSONDecoder().parse(text)\n",
    )
    _write(root, "src/pkg/broken.py", "def (:\n")
    _write(
        root,
        "tests/test_reader.py",
        "from pkg.reader import limit\n\n\ndef test_limit():\n    assert limit(0) == 0\n",
    )
    _write(root, "script.py", "print('hi')\n")


def test_module_names_follow_the_package_root_and_skip_layout_directories(tmp_path: Path) -> None:
    _fixture(tmp_path)
    _write(tmp_path, "services/svc/src/deep/__init__.py", "")
    _write(tmp_path, "services/svc/src/deep/sub/__init__.py", "")
    _write(tmp_path, "services/svc/src/deep/sub/leaf.py", "X = 1\n")

    assert module_name(tmp_path, tmp_path / "src/pkg/reader.py") == "pkg.reader"
    assert module_name(tmp_path, tmp_path / "src/pkg/__init__.py") == "pkg"
    assert module_name(tmp_path, tmp_path / "script.py") == "script"
    assert module_name(tmp_path, tmp_path / "tests/test_reader.py") == "test_reader"
    assert module_name(tmp_path, tmp_path / "services/svc/src/deep/sub/leaf.py") == "deep.sub.leaf"


def test_calls_resolve_through_the_import_that_bound_the_name(tmp_path: Path) -> None:
    _fixture(tmp_path)
    index = build_index(tmp_path)

    sites = {(c.path, c.line, c.callee, c.resolution) for c in index.calls}
    # `from pkg.reader import limit` then `limit(0)`
    assert ("src/pkg/app.py", 5, "pkg.reader:limit", EXACT) in sites
    # `import pkg.reader as reader` then `reader.limit(0)`
    assert ("src/pkg/alias.py", 5, "pkg.reader:limit", EXACT) in sites
    # `from .reader import limit` in the same package
    assert ("src/pkg/relative.py", 5, "pkg.reader:limit", EXACT) in sites
    # `Reader().parse(text)`: the constructor and the method on a fresh instance
    assert ("src/pkg/app.py", 7, "pkg.reader:Reader", EXACT) in sites
    assert ("src/pkg/app.py", 7, "pkg.reader:Reader.parse", EXACT) in sites
    # `self.clean(text)` inside the class resolves through the enclosing class
    assert ("src/pkg/reader.py", 3, "pkg.reader:Reader.clean", EXACT) in sites
    # a same-module call of a local definition
    assert ("src/pkg/reader.py", 14, "pkg.reader:limit", EXACT) in sites
    # a receiver whose type the index does not know is an attribute match
    assert ("src/pkg/relative.py", 6, "", ATTRIBUTE) in sites
    # the unparsable file contributes nothing and breaks nothing
    assert "src/pkg/broken.py" in index.modules
    assert all(c.path != "src/pkg/broken.py" for c in index.calls)


def test_callers_of_a_generic_name_are_exact_first_then_importers_only(tmp_path: Path) -> None:
    _fixture(tmp_path)
    index = build_index(tmp_path)

    callers = index.callers_of("pkg.reader", "parse")

    assert [(c.path, c.line, c.resolution) for c in callers] == [
        ("src/pkg/app.py", 7, EXACT),
        ("src/pkg/relative.py", 6, ATTRIBUTE),  # imports pkg.reader; r.parse could be a Reader
    ]
    # json.JSONDecoder().parse in a file that never imports pkg.reader is not a caller
    assert all(c.path != "src/pkg/other.py" for c in callers)
    assert index.callers_of("pkg.reader", "nonexistent") == []


def test_import_distance_walks_the_graph_both_ways(tmp_path: Path) -> None:
    _fixture(tmp_path)
    _write(tmp_path, "src/pkg/far.py", "from pkg.app import load\n")
    index = build_index(tmp_path)

    distance = index.import_distance("src/pkg/reader.py")

    assert distance["src/pkg/reader.py"] == 0
    assert distance["src/pkg/app.py"] == 1
    assert distance["tests/test_reader.py"] == 1
    assert distance["src/pkg/far.py"] == 2
    assert "src/pkg/other.py" not in distance


def test_literal_arguments_are_counted_across_code_and_tests(tmp_path: Path) -> None:
    _fixture(tmp_path)
    index = build_index(tmp_path)

    literals = index.literal_arguments("pkg.reader", "limit")

    # `0` is passed three times (app, alias, the test); the rest once
    assert literals[0] == "0"
    assert set(literals) == {"0", "-1", "strict=True", "[]"}


def test_the_index_is_cached_under_attest_index_and_invalidated_by_a_change(
    tmp_path: Path,
) -> None:
    _fixture(tmp_path)

    first = tree_index(tmp_path)
    cached = tmp_path / INDEX_DIR / f"{first.key}.json"
    assert cached.is_file()
    payload = json.loads(cached.read_text(encoding="utf-8"))
    assert payload["key"] == first.key

    again = tree_index(tmp_path)
    assert again.key == first.key
    assert again.calls == first.calls

    # a change to any indexed file is a new key; the old cache file is not read
    path = tmp_path / "src/pkg/app.py"
    path.write_text(path.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
    assert tree_key(tmp_path) != first.key
    assert tree_index(tmp_path).key != first.key
