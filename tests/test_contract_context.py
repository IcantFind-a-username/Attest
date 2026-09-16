"""A test of a substituted callable cannot specify the original implementation."""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from binding_cases import SCENARIOS  # noqa: E402
from context_cases import CASES, PATCH, measure  # noqa: E402

from attest.benchmark.artifacts import write_canonical_json  # noqa: E402
from attest.review.contract_context import context_refusal  # noqa: E402
from attest.review.contracts import find_contracts  # noqa: E402

PROBE = 'from geo import parse\ndef test_probe():\n    _attest_value = parse("1,2")\n'


def test_parameter_row_callbacks_cannot_supply_a_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    name = "parameter_row_callback"
    monkeypatch.setitem(SCENARIOS, name, {
        "head": ("return Point(int(a), int(b))", "return Point(int(a), int(b) + 1)"),
        "tests": 'import pytest\nfrom geo import Point, parse\n\n' + PATCH + '\n'
        '@pytest.mark.parametrize("unused", [install()])\n'
        'def test_parse(unused):\n    assert parse("1,2") == Point(1, 2)\n',
        "probe": {"imports": "from geo import parse", "setup": "",
                  "expression": 'parse("1,2")'},
    })
    result = measure(name, tmp_path)
    write_canonical_json(tmp_path / "trace.json", result)
    assert all(run["exit"] == 0 for run in result["original_suite"].values())
    assert result["certification"] != "accepted"
    assert result["reader_admitted"] is False


@pytest.mark.parametrize("name", CASES)
def test_implicit_context_cannot_certify_a_declared_reasonable_change(
    tmp_path: Path, name: str,
) -> None:
    result = measure(name, tmp_path)

    assert all(run["exit"] == 0 for run in result["original_suite"].values())
    # Ancestor conftest also substitutes the generated probe, so execution refuses it
    # before intent observation. Exercise the reader independently in that case too.
    assert result["reader_admitted"] is (None if name == "ancestor_conftest" else False)
    assert result["certification"] != "accepted"
    assert result["contract_search"]["probes"] == []
    assert all("context" in reason for _, reason in result["contract_search"]["refused"])
    repo = tmp_path / name
    contracts = find_contracts(base_tree=repo, head_tree=repo, anchored="geo.py",
                              symbols=("parse",), pinned=("'Point(x=1, y=2)'",),
                              test_source=PROBE)
    assert contracts and not any(c.admitted for c in contracts)
    assert all(not c.flow_bound and "context" in c.flow_reason for c in contracts)


@pytest.mark.parametrize(("source", "refused"), [
    ('"doc"\nfrom geo import parse\nVALUE = (1, 2)\ndef test_x(): pass\n', False),
    ('from helpers import setup_module\n', True),
    ('if FLAG:\n    from helpers import setup_function\n', True),
    ('@pytest.fixture(autouse=True)\ndef test_fixture(): pass\n', False),
    ('def helper(x=install()): pass\n', True),
    ('def helper(x: install()): pass\n', True),
    ('class TestSomething(Base): pass\n', True),
    ('class TestSomething:\n    def setUp(self): pass\n', True),
    ('state.member = 1\n', True),
])
def test_context_screen_has_an_explicit_local_subset(
    tmp_path: Path, source: str, refused: bool,
) -> None:
    reason = context_refusal(tmp_path, Path("tests/test_x.py"), ast.parse(source))
    assert bool(reason) is refused
    if refused:
        assert "tests/test_x.py:" in reason


# D-282: a decorator, and a fixture a test asks for, are screened on the test that states
# the contract, not on every function of the file -- a real suite decorates other tests.
@pytest.mark.parametrize(("source", "refused"), [
    ('def test_x(): pass\n', False),
    ('@pytest.mark.slow\ndef test_x(): pass\n', False),
    ('@pytest.mark.parametrize("v", [0])\ndef test_x(v): pass\n', False),
    ('@wrapper\ndef test_x(): pass\n', True),
    ('@pytest.mark.usefixtures("thing")\ndef test_x(): pass\n', True),
    ('@pytest.mark.parametrize("unused", [0], ids=install())\ndef test_x(unused): pass\n', True),
    ('@pytest.mark.parametrize("unused", [0], ids=callback)\ndef test_x(unused): pass\n', True),
    ('def test_x(unknown_thing): pass\n', True),
])
def test_a_tests_own_decorators_and_fixtures_are_screened(
    tmp_path: Path, source: str, refused: bool,
) -> None:
    from attest.review.contract_context import read_context

    module = ast.parse('import pytest\n\n\n' + source)
    context = read_context(tmp_path, Path("tests/test_x.py"), module)
    function = next(n for n in module.body if getattr(n, "name", "") == "test_x")
    # a decorator the rule cannot read refuses the file; a mark it can read refuses the test
    assert bool(context.reason or context.function_refusal(function)) is refused


@pytest.mark.parametrize(("text", "refused"), [
    ('"documentation"\npass\n', False),
    # D-282: an import binds a name; what the imported module does is the stated limit,
    # and refusing every conftest that imports refused every real repository (98 of 98)
    ('import helper\n', False),
    ('broken (', True),
    ('helper.install()\n', True),
])
def test_an_ancestor_conftest_is_read_for_what_it_can_reach(
    tmp_path: Path, text: str, refused: bool,
) -> None:
    (tmp_path / "conftest.py").write_text(text)
    reason = context_refusal(tmp_path, Path("tests/nested/test_x.py"), ast.parse("pass"))
    assert bool(reason) is refused
    if reason:
        assert "conftest.py" in reason
