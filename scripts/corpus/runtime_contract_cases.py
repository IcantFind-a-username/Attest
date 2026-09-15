"""Frozen development cases for the runtime-contract shadow experiment (D-258)."""

from __future__ import annotations

from pathlib import Path

from binding_cases import SCENARIOS, _git, build
from context_cases import CASES, PATCH, TEST, register

NEGATIVES = (
    *CASES,
    "parameter_row_callback",
    "unreachable_assert",
    "receiver_mutated",
    "withdrawn_expectation",
    "observer_name_collision",
)
POSITIVES = ("legal_contract", "cache_clear_fixture", "receiver_fixture")
NAMES = (*NEGATIVES, *POSITIVES)
PARAMETER_NAMES = (
    "parameter_regression",
    "parameter_reordered",
    "parameter_swapped_inputs",
    "parameter_changed_ids",
    "parameter_skipped",
    "parameter_expected_update",
)
PARAMETER_POSITIVES = PARAMETER_NAMES[:2]


def build_case(name: str, work: Path) -> tuple[Path, str, str, int]:
    register()
    change = ("return Point(int(a), int(b))", "return Point(int(a), int(b) + 1)")
    extra = {
        "parameter_row_callback": {
            "tests": "import pytest\nfrom geo import Point, parse\n\n" + PATCH + "\n"
            '@pytest.mark.parametrize("unused", [install()])\n'
            'def test_parse(unused):\n    assert parse("1,2") == Point(1, 2)\n',
        },
        "cache_clear_fixture": {
            "tests": TEST.replace(
                "def test_parse():",
                'CACHE = {"stale": 1}\n\ndef test_parse():\n    assert not CACHE',
            ),
            "files": {
                "conftest.py": "import pytest\n\n@pytest.fixture(autouse=True)\n"
                "def clear_cache(request):\n    request.module.CACHE.clear()\n"
            },
        },
        "receiver_fixture": {
            "head": (
                "return Point(point.x * self.width, point.y)",
                "return Point(point.x * self.width, point.y + 1)",
            ),
            "tests": "import pytest\nfrom geo import Grid, Point\n\n"
            "@pytest.fixture\ndef grid():\n    g = Grid(width=2)\n    g.cache = {}\n"
            "    return g\n\ndef test_cell(grid):\n"
            "    assert grid.cell(Point(1, 2)) == Point(2, 2)\n",
        },
        "withdrawn_expectation": {"tests": TEST},
        "observer_name_collision": {
            "tests": TEST + "\n_attest_contract_shadow = object()\n",
        },
    }
    for label, scenario in extra.items():
        SCENARIOS[label] = {"head": change, **scenario}
    parameter_test = (
        "import pytest\nfrom geo import Point, parse\n\n"
        '@pytest.mark.parametrize(("text", "expected"), '
        '[("1,2", Point(1, 2)), ("3,4", Point(3, 4))], ids=["first", "second"])\n'
        "def test_parse(text, expected):\n    assert parse(text) == expected\n"
    )
    for label in PARAMETER_NAMES:
        SCENARIOS[label] = {
            "head": (change[0], 'return Point(int(a), int(b) + (1 if a == "1" else 0))'),
            "tests": parameter_test,
        }
    repo, base, head, line = build(name, work)
    if name == "withdrawn_expectation":
        (repo / "tests/test_geo.py").write_text(TEST.replace("Point(1, 2)", "Point(1, 3)"))
        _git(repo, "commit", "-am", "update expected value with intended behaviour")
        head = _git(repo, "rev-parse", "HEAD")
    if name in PARAMETER_NAMES[1:]:
        test = parameter_test
        if name in ("parameter_reordered", "parameter_swapped_inputs"):
            test = test.replace(
                '[("1,2", Point(1, 2)), ("3,4", Point(3, 4))]',
                '[("3,4", Point(3, 4)), ("1,2", Point(1, 2))]',
            )
        if name == "parameter_reordered":
            test = test.replace('ids=["first", "second"]', 'ids=["second", "first"]')
        elif name == "parameter_changed_ids":
            test = test.replace('ids=["first", "second"]', 'ids=["changed", "second"]')
        elif name == "parameter_skipped":
            test = test.replace(
                "def test_parse", '@pytest.mark.skip(reason="withdrawn")\ndef test_parse'
            )
        elif name == "parameter_expected_update":
            test = test.replace("Point(1, 2)", "Point(1, 3)")
        (repo / "tests/test_geo.py").write_text(test)
        _git(repo, "commit", "-am", "record parameter context change")
        head = _git(repo, "rev-parse", "HEAD")
    return repo, base, head, line
