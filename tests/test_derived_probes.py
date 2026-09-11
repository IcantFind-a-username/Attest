"""Probes derived from the repository's own tests: no model, no expectation.

D-146 made the model choose one call and the merge base record what it does.
The largest remaining loss of receipts is that the model's one call does not
collect, or is not the input the change is about. The repository's tests
already call the changed function, the way the project imports it, with inputs
that are real -- so those calls are probes that cost nothing to choose, and a
boundary variant of a real input (the empty list, zero, the empty string) is
the input a regression is most often about.

Everything here is `ast` and the binding layer. A call is derived only when it
**resolves** to the changed definition (`attest.review.binding`), and only when
every argument is a literal: a fixture, a variable, an object built two lines
up is not something a probe can carry into a file that runs outside the test
tree. Nothing derived here asserts anything; the recording on base does that.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from derived_probes import (  # noqa: E402
    DERIVED_PROBE_POLICY_VERSION,
    MAX_DERIVED_PROBES,
    DerivedProbe,
    derive_probes,
)

MODULE = "def total(items, scale=1):\n    return sum(items) * scale\n"


def _derive(tests: dict[str, str], module: str = MODULE, path: str = "mod.py", line: int = 2):
    return derive_probes({path: module, **tests}, path=path, line=line)


# --- the shapes that derive -------------------------------------------------


def test_a_from_import_call_with_literal_arguments_is_a_probe() -> None:
    body = "from mod import total\n\n\ndef test_it():\n    assert total([1, 2, 3]) == 6\n"
    tests = {"tests/test_mod.py": body}
    probes = _derive(tests)
    exact = [p for p in probes if p.kind == "exact"]
    assert len(exact) == 1
    assert exact[0].spec.imports == "from mod import total"
    assert exact[0].spec.setup == ""
    assert exact[0].spec.expression == "total([1, 2, 3])"
    assert exact[0].origin == "tests/test_mod.py:5"
    assert exact[0].policy_version == DERIVED_PROBE_POLICY_VERSION


def test_a_module_import_and_attribute_call_keeps_the_written_shape() -> None:
    body = "import mod\n\n\ndef test_it():\n    assert mod.total([1, 2]) == 3\n"
    tests = {"tests/test_mod.py": body}
    (exact,) = [p for p in _derive(tests) if p.kind == "exact"]
    assert exact.spec.imports == "import mod"
    assert exact.spec.expression == "mod.total([1, 2])"


def test_an_aliased_import_is_reproduced_as_written() -> None:
    tests = {
        "tests/test_mod.py": "from mod import total as add_up\n\n\ndef test_it():\n"
        "    assert add_up([4]) == 4\n"
    }
    (exact,) = [p for p in _derive(tests) if p.kind == "exact"]
    assert exact.spec.imports == "from mod import total as add_up"
    assert exact.spec.expression == "add_up([4])"


def test_keyword_literals_are_carried_and_ordered_as_written() -> None:
    tests = {
        "tests/test_mod.py": "from mod import total\n\n\ndef test_it():\n"
        "    assert total([1, 2], scale=2) == 6\n"
    }
    (exact,) = [p for p in _derive(tests) if p.kind == "exact"]
    assert exact.spec.expression == "total([1, 2], scale=2)"


# --- boundary variants ----------------------------------------------------------


def test_a_boundary_variant_of_each_literal_follows_the_exact_call() -> None:
    body = "from mod import total\n\n\ndef test_it():\n    total([1, 2, 3], scale=2)\n"
    tests = {"tests/test_mod.py": body}
    probes = _derive(tests)
    expressions = [p.spec.expression for p in probes]
    assert expressions[0] == "total([1, 2, 3], scale=2)"
    assert "total([], scale=2)" in expressions
    assert "total([1, 2, 3], scale=0)" in expressions
    assert all(p.kind == "variant" for p in probes[1:])
    assert all(p.spec.imports == "from mod import total" for p in probes)


def test_variants_of_strings_none_and_negative_numbers() -> None:
    module = "def label(text, count):\n    return text * count\n"
    tests = {"tests/test_l.py": "from lab import label\n\n\ndef test_it():\n    label('ab', 3)\n"}
    probes = derive_probes({"lab.py": module, **tests}, path="lab.py", line=2)
    expressions = {p.spec.expression for p in probes}
    assert "label('', 3)" in expressions
    assert "label('ab', 0)" in expressions
    assert "label('ab', -1)" in expressions


# --- what is refused ------------------------------------------------------------


def test_a_call_whose_argument_is_not_a_literal_derives_nothing() -> None:
    tests = {
        "tests/test_mod.py": "from mod import total\n\n\ndef test_it(items):\n"
        "    assert total(items) == 6\n"
    }
    assert _derive(tests) == ()


def test_a_call_the_binding_layer_cannot_resolve_derives_nothing() -> None:
    unbound = "def test_it():\n    assert total([1]) == 1\n"  # no import at all
    star = "from mod import *\n\n\ndef test_it():\n    assert total([1]) == 1\n"
    variable = "import mod\n\n\ndef test_it():\n    m = mod\n    assert m.total([1]) == 1\n"
    for body in (unbound, star, variable):
        assert _derive({"tests/test_mod.py": body}) == (), body


def test_a_relative_import_in_a_test_derives_nothing() -> None:
    tests = {"tests/test_mod.py": "from ..mod import total\n\n\ndef test_it():\n    total([1])\n"}
    assert _derive(tests) == ()


def test_a_call_from_outside_the_test_tree_is_not_a_probe() -> None:
    """A caller in application code is a caller, not a test input."""
    sources = {"mod.py": MODULE, "app.py": "from mod import total\n\nTOTAL = total([1, 2])\n"}
    assert derive_probes(sources, path="mod.py", line=2) == ()


def test_a_method_is_not_derived_in_this_version() -> None:
    module = "class Box:\n    def total(self, items):\n        return sum(items)\n"
    tests = {"tests/test_b.py": "from box import Box\n\n\ndef test_it():\n    Box().total([1])\n"}
    assert derive_probes({"box.py": module, **tests}, path="box.py", line=3) == ()


def test_a_line_outside_any_definition_derives_nothing() -> None:
    tests = {"tests/test_mod.py": "from mod import total\n\n\ndef test_it():\n    total([1])\n"}
    assert _derive(tests, module="X = 1\n" + MODULE, line=1) == ()


# --- bounds and order ---------------------------------------------------------------


def test_exact_calls_come_first_then_variants_and_the_whole_is_capped() -> None:
    calls = "\n".join(f"    total([{n}])" for n in range(1, 12))
    tests = {"tests/test_mod.py": f"from mod import total\n\n\ndef test_it():\n{calls}\n"}
    probes = _derive(tests)
    assert 0 < len(probes) <= MAX_DERIVED_PROBES
    kinds = [p.kind for p in probes]
    assert kinds == sorted(kinds, key=lambda k: 0 if k == "exact" else 1)
    assert len({p.spec.expression for p in probes}) == len(probes)


def test_the_same_expression_written_twice_is_one_probe() -> None:
    tests = {
        "tests/test_a.py": "from mod import total\n\n\ndef test_a():\n    total([1])\n",
        "tests/test_b.py": "from mod import total\n\n\ndef test_b():\n    total([1])\n",
    }
    expressions = [p.spec.expression for p in _derive(tests)]
    assert expressions.count("total([1])") == 1


def test_a_derived_probe_is_a_plain_record() -> None:
    probe = DerivedProbe.__dataclass_fields__
    assert set(probe) >= {"spec", "origin", "kind", "policy_version"}


# --- the import check the model path gets (D-206) --------------------------------


def test_a_probe_that_imports_nothing_the_tree_defines_cannot_reach_it(tmp_path) -> None:
    """The refusal the recorder used to make after three container runs on base."""
    from attest.review.probe import ProbeSpec, reaches_the_tree, tree_roots

    def probe(imports: str) -> ProbeSpec:
        return ProbeSpec(imports=imports, setup="", expression="f()")

    (tmp_path / "mod.py").write_text("def total(items):\n    return sum(items)\n")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("")
    roots = tree_roots(tmp_path)

    assert roots >= {"mod", "pkg"}
    assert reaches_the_tree(probe("import mod"), roots) is True
    assert reaches_the_tree(probe("from pkg.thing import f"), roots) is True
    # one-sided on purpose: a dependency the image provides is not this check's
    assert reaches_the_tree(probe("import numpy\nimport mod"), roots) is True
    assert reaches_the_tree(probe("import numpy"), roots) is False
    assert reaches_the_tree(probe("import json"), roots) is False
    assert reaches_the_tree(probe("from . import mod"), roots) is False
    # a shape `parse_probe` owns is not refused here
    assert reaches_the_tree(probe("import ("), roots) is True


def test_a_probe_that_loads_the_tree_by_path_reaches_it(tmp_path) -> None:
    """An import statement is not the only route into the tree.

    The release drills replay a probe that imports `runpy` and reaches the code
    under review with `runpy.run_path('app.py')`. Reading the import block alone
    calls that unreachable and refuses it -- which is what broke `gates` on
    `main` at 516b924, and which would silence the same shape on any real
    repository. The whole probe is what reaches, not its first three lines.
    """
    from attest.review.probe import ProbeSpec, reaches_the_tree, tree_roots

    (tmp_path / "app.py").write_text("def average(items):\n    return sum(items) / len(items)\n")
    roots = tree_roots(tmp_path)

    drill = ProbeSpec(
        imports="import runpy",
        setup="average = runpy.run_path('app.py')['average']",
        expression="average([])",
    )
    assert reaches_the_tree(drill, roots) is True
    # still refused: nothing in the whole probe names anything of the tree
    unreachable = ProbeSpec(imports="import json", setup="x = json.dumps({})", expression="len(x)")
    assert reaches_the_tree(unreachable, roots) is False


def test_a_src_layout_package_is_a_tree_root(tmp_path) -> None:
    from attest.review.probe import tree_roots

    (tmp_path / "src" / "proj").mkdir(parents=True)
    (tmp_path / "src" / "proj" / "__init__.py").write_text("")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "hidden.py").write_text("")

    roots = tree_roots(tmp_path)
    assert "proj" in roots
    assert "hidden" not in roots and "src" not in roots
