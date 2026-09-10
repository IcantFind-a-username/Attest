"""The reachability ladder must actually climb.

`probe_reach.py` exists to decide whether D-206's route is closed, and its
answer is a negative result if the relaxed columns stay near zero. A relaxation
that silently never fires would produce exactly that shape while measuring
nothing -- the most expensive possible bug in a measurement, because it looks
like evidence. Each test below drives one relaxation with the smallest source
that should satisfy it and pins that the column moves, and one that should not
satisfy it and pins that the column does not.

These test the *script's* arithmetic. The `current` column is
`derive_probes` itself and is pinned by `tests/test_derived_probes.py`.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from probe_reach import (  # noqa: E402
    R_CONSTRUCTED,
    R_FIXTURE,
    R_LOCAL,
    R_OTHER_EXPR,
    _admits,
    _argument_reason,
    _enclosing,
    _enclosing_function,
    _literal_locals,
    _parametrized_literals,
    _receiver_is_literal_construction,
)


def _call(source: str) -> tuple[ast.Call, ast.FunctionDef]:
    """The single call of the single function in ``source``."""
    module = ast.parse(source)
    fn = next(n for n in ast.walk(module) if isinstance(n, ast.FunctionDef))
    call = next(
        n
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and not isinstance(n.func, ast.Attribute | ast.Name)
        or (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name | ast.Attribute)
            and ast.unparse(n.func).split(".")[-1] in {"total", "run", "f"}
        )
    )
    return call, fn


ALL_OFF = {"method": False, "local": False, "parametrize": False}


def test_a_literal_call_is_admitted_by_every_rule() -> None:
    call, fn = _call("def test_x():\n    total([1, 2])\n")
    assert _admits(call, fn, **ALL_OFF)
    assert _admits(call, fn, method=True, local=True, parametrize=True)


def test_a_local_assigned_a_literal_is_refused_now_and_admitted_by_local() -> None:
    source = "def test_x():\n    rows = [1, 2]\n    total(rows)\n"
    call, fn = _call(source)
    assert _literal_locals(fn) == {"rows"}
    assert not _admits(call, fn, **ALL_OFF), "the current rule must refuse a variable"
    assert _admits(call, fn, method=False, local=True, parametrize=False)
    assert _argument_reason(call, fn) == R_LOCAL


def test_a_local_assigned_a_call_is_refused_even_by_local() -> None:
    """`+local` relaxes literals-through-a-name, not arbitrary values."""
    source = "def test_x():\n    rows = build()\n    total(rows)\n"
    call, fn = _call(source)
    assert _literal_locals(fn) == set()
    assert not _admits(call, fn, method=False, local=True, parametrize=False)


def test_a_parametrized_literal_is_refused_now_and_admitted_by_parametrize() -> None:
    source = (
        "@pytest.mark.parametrize('n', [1, 2, 3])\n"
        "def test_x(n):\n"
        "    total(n)\n"
    )
    call, fn = _call(source)
    assert _parametrized_literals(fn) == {"n"}
    assert not _admits(call, fn, **ALL_OFF)
    assert _admits(call, fn, method=False, local=False, parametrize=True)
    # it is a fixture parameter as far as the current rule can tell
    assert _argument_reason(call, fn) == R_FIXTURE


def test_a_parametrized_non_literal_is_refused_even_by_parametrize() -> None:
    source = (
        "@pytest.mark.parametrize('n', [build(), other()])\n"
        "def test_x(n):\n"
        "    total(n)\n"
    )
    call, fn = _call(source)
    assert _parametrized_literals(fn) == set()
    assert not _admits(call, fn, method=False, local=False, parametrize=True)


def test_two_argnames_parametrized_together_are_read_column_by_column() -> None:
    source = (
        "@pytest.mark.parametrize('a,b', [(1, build()), (2, other())])\n"
        "def test_x(a, b):\n"
        "    total(a)\n"
    )
    call, fn = _call(source)
    assert _parametrized_literals(fn) == {"a"}
    assert _admits(call, fn, method=False, local=False, parametrize=True)


def test_a_method_on_a_literal_receiver_is_refused_now_and_admitted_by_method() -> None:
    source = "def test_x():\n    Box().run(1)\n"
    call, fn = _call(source)
    assert _receiver_is_literal_construction(call, fn)
    assert not _admits(call, fn, **ALL_OFF), "the current rule derives no method"
    assert _admits(call, fn, method=True, local=False, parametrize=False)


def test_a_method_on_a_receiver_built_from_a_fixture_is_refused_by_method() -> None:
    source = "def test_x(tmp_path):\n    box = Box(tmp_path)\n    box.run(1)\n"
    call, fn = _call(source)
    assert not _receiver_is_literal_construction(call, fn)
    assert not _admits(call, fn, method=True, local=False, parametrize=False)


def test_a_receiver_assigned_a_literal_construction_is_admitted_by_method() -> None:
    source = "def test_x():\n    box = Box(1, 2)\n    box.run(0)\n"
    call, fn = _call(source)
    assert _receiver_is_literal_construction(call, fn)
    assert _admits(call, fn, method=True, local=False, parametrize=False)


def test_star_args_are_refused_by_every_relaxation() -> None:
    """`*args` can supply anything; no relaxation here claims to see it."""
    source = "def test_x():\n    rows = [1]\n    total(*rows)\n"
    call, fn = _call(source)
    assert not _admits(call, fn, method=True, local=True, parametrize=True)
    assert _argument_reason(call, fn) == R_OTHER_EXPR


def test_a_constructed_argument_is_named_as_such() -> None:
    call, fn = _call("def test_x():\n    total(Frame(1))\n")
    assert _argument_reason(call, fn) == R_CONSTRUCTED
    assert not _admits(call, fn, method=True, local=True, parametrize=True)


@pytest.mark.parametrize(
    ("source", "line", "expected"),
    [
        ("def f():\n    pass\n", 2, ("f", "module")),
        ("class C:\n    def m(self):\n        pass\n", 3, ("m", "method")),
        ("def outer():\n    def inner():\n        pass\n", 3, ("inner", "nested")),
        ("X = 1\n", 1, (None, "none")),
    ],
)
def test_the_anchor_kind_separates_what_derive_probes_collapses(
    source: str, line: int, expected: tuple[str | None, str]
) -> None:
    """`derive_probes` returns None for a method and for module-level code
    alike; sizing the method population is the point of this measurement."""
    assert _enclosing(ast.parse(source), line) == expected


def test_the_enclosing_function_of_a_call_is_the_innermost_one() -> None:
    source = "def outer():\n    def inner():\n        total(1)\n"
    fn = _enclosing_function(ast.parse(source), 3)
    assert fn is not None and fn.name == "inner"
