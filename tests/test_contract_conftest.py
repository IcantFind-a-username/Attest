"""D-282: a conftest is read for what it can reach, not refused for existing.

D-257 admitted only an empty conftest, so every real repository refused every contract:
98 of 98 refusals in that round's rebuilt searches were `conftest execution is unexamined`.
The screen now reads the conftest chain and the test module's own fixtures, and refuses a
contract only when code that runs *before* the test can reach the module under review --
the anchored module, or a module it imports -- or when the rule cannot tell what that code
reaches. Teardown after a fixture's `yield` runs after the assertion and is not read.

The stated limit stays: a call is followed to the module its name resolves to, never into
that module's own body.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from attest.review.contract_context import read_context  # noqa: E402

ANCHORED = "pkg.geo"
RELATED = frozenset({"pkg.geo", "pkg.markers"})


def _context(tmp_path: Path, conftest: str, module: str = "pass\n", *, nested: bool = False):
    where = Path("tests/nested/test_x.py") if nested else Path("tests/test_x.py")
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    if nested:
        (tmp_path / "tests" / "nested").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "conftest.py").write_text(conftest, encoding="utf-8")
    return read_context(
        tmp_path, where, ast.parse(module), anchored_module=ANCHORED, related=RELATED,
    )


# --- the conftest chain ------------------------------------------------------------


@pytest.mark.parametrize(
    ("conftest", "refused"),
    [
        pytest.param("import pytest\n\n\n@pytest.fixture\ndef client():\n    return 1\n",
                     False, id="read: an ordinary fixture nobody in this test requests"),
        pytest.param("import gc\n\n\ndef pytest_collection() -> None:\n    gc.disable()\n",
                     False, id="read: a hook that touches an unrelated module"),
        pytest.param(
            "from pkg.markers import cache\n\n\ndef pytest_runtest_setup() -> None:\n"
            "    cache.cache_clear()\n",
            True, id="refused: a hook that touches a module the anchored one imports"),
        pytest.param(
            "from pkg.geo import parse\n\n\ndef pytest_runtest_setup() -> None:\n"
            "    parse.cache_clear()\n",
            True, id="refused: a hook that touches the anchored module"),
        pytest.param("def pytest_runtest_setup() -> None:\n    helper()\n",
                     True, id="refused: a hook whose call the rule cannot resolve"),
        pytest.param("pytest_plugins = ['helpers.fixtures']\n",
                     True, id="refused: a plugin declaration"),
        pytest.param(
            "import pytest\nfrom pkg.geo import parse\n\n\n"
            "@pytest.fixture(autouse=True)\ndef patched(monkeypatch):\n"
            "    monkeypatch.setattr(parse, 'inner', None)\n",
            True, id="refused: an autouse fixture that reaches the anchored module"),
        pytest.param(
            "import pytest\nimport gc\n\n\n@pytest.fixture(autouse=True)\ndef collected():\n"
            "    yield\n    gc.collect()\n",
            False, id="read: an autouse fixture that only tears down"),
        pytest.param(
            "import pytest\nfrom pkg.geo import parse\n\n\n"
            "@pytest.fixture(autouse=True)\ndef cleared():\n    yield\n    parse.cache_clear()\n",
            False, id="read: teardown reaching the anchored module runs after the assertion"),
        pytest.param("import pytest\nfrom pkg.geo import parse\n\nparse.cache = {}\n",
                     True, id="refused: module-level code that reaches the anchored module"),
        pytest.param("broken (\n", True, id="refused: a conftest that cannot be parsed"),
    ],
)
def test_the_conftest_chain_is_read(tmp_path: Path, conftest: str, refused: bool) -> None:
    context = _context(tmp_path, conftest)
    assert bool(context.reason) is refused, context.reason
    if refused:
        assert "conftest.py" in context.reason


def test_every_conftest_on_the_path_is_read(tmp_path: Path) -> None:
    (tmp_path / "tests" / "nested").mkdir(parents=True)
    (tmp_path / "conftest.py").write_text(
        "from pkg.geo import parse\n\n\ndef pytest_runtest_setup() -> None:\n"
        "    parse.cache_clear()\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "conftest.py").write_text("import pytest\n", encoding="utf-8")
    context = read_context(
        tmp_path, Path("tests/nested/test_x.py"), ast.parse("pass\n"),
        anchored_module=ANCHORED, related=RELATED,
    )
    assert context.reason and "conftest.py" in context.reason


# --- the fixtures a test asks for ---------------------------------------------------


def _function(source: str) -> ast.FunctionDef:
    node = ast.parse(source).body[0]
    assert isinstance(node, ast.FunctionDef)
    return node


def test_a_requested_fixture_is_refused_unless_it_is_read(tmp_path: Path) -> None:
    conftest = (
        "import pytest\nfrom pkg.geo import parse\n\n\n"
        "@pytest.fixture\ndef patched():\n    parse.cache = {}\n    yield\n\n\n"
        "@pytest.fixture\ndef plain():\n    return 3\n"
    )
    context = _context(tmp_path, conftest)
    assert context.reason == ""
    # requested and provably harmless
    assert context.function_refusal(_function("def test_x(plain):\n    pass\n")) == ""
    # requested, reaches the anchored module, and never mentioned in the body
    reason = context.function_refusal(_function("def test_x(patched):\n    pass\n"))
    assert "patched" in reason and "pkg.geo" in reason
    # a fixture no conftest on the path defines: the rule does not know what it does
    unknown = context.function_refusal(_function("def test_x(monkeypatch):\n    pass\n"))
    assert "monkeypatch" in unknown
    # a parametrize row is an input, not a fixture
    rows = _function(
        "@pytest.mark.parametrize('value', [1])\ndef test_x(value):\n    pass\n"
    )
    assert context.function_refusal(rows) == ""


def test_a_fixture_of_the_test_module_is_read_like_a_conftest_one(tmp_path: Path) -> None:
    module = (
        "import pytest\nfrom pkg.geo import parse\n\n\n"
        "@pytest.fixture\ndef local():\n    parse.cache = {}\n    return 1\n\n\n"
        "def test_x(local):\n    pass\n"
    )
    context = _context(tmp_path, "import pytest\n", module)
    assert context.reason == ""
    reason = context.function_refusal(_function(module.split("\n\n\n")[-1]))
    assert "local" in reason and "pkg.geo" in reason


def test_an_autouse_fixture_of_the_test_module_refuses_the_file(tmp_path: Path) -> None:
    module = (
        "import pytest\nfrom pkg.geo import parse\n\n\n"
        "@pytest.fixture(autouse=True)\ndef patch_it():\n    parse.cache = {}\n"
    )
    context = _context(tmp_path, "import pytest\n", module)
    assert context.reason and "patch_it" in context.reason
