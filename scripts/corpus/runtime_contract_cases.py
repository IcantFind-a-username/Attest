"""Frozen development cases for the runtime-contract shadow experiment (D-258)."""
from __future__ import annotations

from pathlib import Path

from binding_cases import SCENARIOS, _git, build
from context_cases import CASES, PATCH, TEST, register

NEGATIVES = (*CASES, "parameter_row_callback", "unreachable_assert", "receiver_mutated",
             "withdrawn_expectation", "observer_name_collision")
POSITIVES = ("legal_contract", "cache_clear_fixture", "receiver_fixture")
NAMES = (*NEGATIVES, *POSITIVES)


def build_case(name: str, work: Path) -> tuple[Path, str, str, int]:
    register()
    change = ("return Point(int(a), int(b))", "return Point(int(a), int(b) + 1)")
    extra = {
        "parameter_row_callback": {
            "tests": 'import pytest\nfrom geo import Point, parse\n\n' + PATCH + '\n'
            '@pytest.mark.parametrize("unused", [install()])\n'
            'def test_parse(unused):\n    assert parse("1,2") == Point(1, 2)\n',
        },
        "cache_clear_fixture": {
            "tests": TEST.replace('def test_parse():', 'CACHE = {"stale": 1}\n\n'
                                  'def test_parse():\n    assert not CACHE'),
            "files": {"conftest.py": 'import pytest\n\n@pytest.fixture(autouse=True)\n'
                      'def clear_cache(request):\n    request.module.CACHE.clear()\n'},
        },
        "receiver_fixture": {
            "head": ("return Point(point.x * self.width, point.y)",
                     "return Point(point.x * self.width, point.y + 1)"),
            "tests": 'import pytest\nfrom geo import Grid, Point\n\n'
            '@pytest.fixture\ndef grid():\n    g = Grid(width=2)\n    g.cache = {}\n'
            '    return g\n\ndef test_cell(grid):\n'
            '    assert grid.cell(Point(1, 2)) == Point(2, 2)\n',
        },
        "withdrawn_expectation": {"tests": TEST},
        "observer_name_collision": {
            "tests": TEST + '\n_attest_contract_shadow = object()\n',
        },
    }
    for label, scenario in extra.items():
        SCENARIOS[label] = {"head": change, **scenario}
    repo, base, head, line = build(name, work)
    if name == "withdrawn_expectation":
        (repo / "tests/test_geo.py").write_text(TEST.replace('Point(1, 2)', 'Point(1, 3)'))
        _git(repo, "commit", "-am", "update expected value with intended behaviour")
        head = _git(repo, "rev-parse", "HEAD")
    return repo, base, head, line
