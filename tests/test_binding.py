"""The shared binding layer: a written name, resolved to one definition or none.

Every abstention here is a claim the product will not make. The negatives are
therefore as load-bearing as the positives and are written first.
"""

from __future__ import annotations

import ast

from attest.review.binding import BindingIndex, Reference, Target, dotted_name


def index(**sources: str) -> BindingIndex:
    """`__` in a keyword stands for `/`, so a path can be written as a keyword."""
    return BindingIndex.from_sources(
        {path.replace("__", "/"): text for path, text in sources.items()}
    )


def resolve(idx: BindingIndex, path: str, dotted: str, scope: str | None = None) -> Target | None:
    return idx.resolve(Reference(path=path, dotted=dotted, scope=scope))


# -- module-level defs of the referring file


def test_a_module_level_def_of_the_same_file_binds() -> None:
    idx = index(**{"app.py": "def f(x):\n    return x\n\ndef g():\n    return f(1)\n"})
    assert resolve(idx, "app.py", "f", "g") == Target("app.py", "f")


def test_a_name_defined_twice_in_one_file_binds_to_nothing() -> None:
    idx = index(**{"app.py": "def f():\n    pass\n\ndef f():\n    pass\n\ndef g():\n    f()\n"})
    assert resolve(idx, "app.py", "f", "g") is None


def test_a_module_level_assignment_over_a_def_binds_to_nothing() -> None:
    idx = index(**{"app.py": "def f():\n    pass\n\nf = None\n\ndef g():\n    f()\n"})
    assert resolve(idx, "app.py", "f", "g") is None


def test_a_parameter_of_the_enclosing_function_is_not_the_module_level_def() -> None:
    idx = index(**{"app.py": "def f():\n    pass\n\ndef g(f):\n    return f()\n"})
    assert resolve(idx, "app.py", "f", "g") is None


def test_a_nested_def_does_not_bind_to_the_module_level_name() -> None:
    src = "def f():\n    return 1\n\ndef g():\n    def f():\n        return 2\n    return f()\n"
    idx = index(**{"app.py": src})
    assert resolve(idx, "app.py", "f", "g") is None


# -- imports


def test_from_import_binds_across_files() -> None:
    idx = index(
        **{
            "lib.py": "def sqrt(x):\n    return x\n",
            "app.py": "from lib import sqrt\n\ndef go(v):\n    return sqrt(v)\n",
        }
    )
    assert resolve(idx, "app.py", "sqrt", "go") == Target("lib.py", "sqrt")


def test_an_alias_binds_to_the_name_it_aliases() -> None:
    idx = index(
        **{
            "mathlib.py": "def sqrt(x):\n    return x\n",
            "app.py": "from mathlib import sqrt as root\n\ndef go(v):\n    return root(v)\n",
        }
    )
    assert resolve(idx, "app.py", "root", "go") == Target("mathlib.py", "sqrt")


def test_a_stdlib_module_attribute_binds_to_nothing() -> None:
    idx = index(
        **{
            "mathlib.py": "def sqrt(x):\n    return x\n",
            "app.py": "import math\n\ndef go():\n    return math.sqrt(9)\n",
        }
    )
    assert resolve(idx, "app.py", "math.sqrt", "go") is None


def test_a_project_module_attribute_binds() -> None:
    idx = index(
        **{
            "mathlib.py": "def sqrt(x):\n    return x\n",
            "app.py": "import mathlib\n\ndef go():\n    return mathlib.sqrt(9)\n",
        }
    )
    assert resolve(idx, "app.py", "mathlib.sqrt", "go") == Target("mathlib.py", "sqrt")


def test_an_aliased_module_binds() -> None:
    idx = index(
        **{
            "pkg__mathlib.py": "def sqrt(x):\n    return x\n",
            "app.py": "import pkg.mathlib as m\n\ndef go():\n    return m.sqrt(9)\n",
        }
    )
    assert resolve(idx, "app.py", "m.sqrt", "go") == Target("pkg/mathlib.py", "sqrt")


def test_a_layout_prefix_is_not_part_of_the_module_name() -> None:
    idx = index(
        **{
            "src__pkg__mathlib.py": "def sqrt(x):\n    return x\n",
            "src__pkg__app.py": "from pkg.mathlib import sqrt\n\ndef go(v):\n    return sqrt(v)\n",
        }
    )
    assert resolve(idx, "src/pkg/app.py", "sqrt", "go") == Target("src/pkg/mathlib.py", "sqrt")


def test_two_files_matching_one_dotted_suffix_are_ambiguous() -> None:
    idx = index(
        **{
            "src__pkg__mathlib.py": "def sqrt(x):\n    return x\n",
            "vendor__pkg__mathlib.py": "def sqrt(x):\n    return x\n",
            "app.py": "from pkg.mathlib import sqrt\n\ndef go(v):\n    return sqrt(v)\n",
        }
    )
    assert resolve(idx, "app.py", "sqrt", "go") is None


def test_a_relative_import_binds_from_the_referring_directory() -> None:
    idx = index(
        **{
            "pkg__mathlib.py": "def sqrt(x):\n    return x\n",
            "pkg__app.py": "from .mathlib import sqrt\n\ndef go(v):\n    return sqrt(v)\n",
        }
    )
    assert resolve(idx, "pkg/app.py", "sqrt", "go") == Target("pkg/mathlib.py", "sqrt")


def test_a_two_level_relative_import_walks_up_one_package() -> None:
    idx = index(
        **{
            "pkg__mathlib.py": "def sqrt(x):\n    return x\n",
            "pkg__sub__app.py": "from ..mathlib import sqrt\n\ndef go(v):\n    return sqrt(v)\n",
        }
    )
    assert resolve(idx, "pkg/sub/app.py", "sqrt", "go") == Target("pkg/mathlib.py", "sqrt")


def test_a_reexport_the_package_init_does_not_define_binds_to_nothing() -> None:
    idx = index(
        **{
            "pkg____init__.py": "from .mathlib import sqrt\n",
            "pkg__mathlib.py": "def sqrt(x):\n    return x\n",
            "app.py": "from pkg import sqrt\n\ndef go(v):\n    return sqrt(v)\n",
        }
    )
    assert resolve(idx, "app.py", "sqrt", "go") is None


# -- star imports


def test_a_star_import_makes_every_bare_name_of_that_file_unresolvable() -> None:
    idx = index(
        **{
            "lib.py": "def f():\n    pass\n",
            "app.py": "from lib import *\n\ndef f():\n    pass\n\ndef g():\n    return f()\n",
        }
    )
    assert resolve(idx, "app.py", "f", "g") is None


def test_a_star_import_does_not_void_an_explicit_module_attribute() -> None:
    idx = index(
        **{
            "lib.py": "def f():\n    pass\n",
            "other.py": "def f():\n    pass\n",
            "app.py": "from other import *\nimport lib\n\ndef g():\n    return lib.f()\n",
        }
    )
    assert resolve(idx, "app.py", "lib.f", "g") == Target("lib.py", "f")


# -- receivers


def test_self_binds_to_the_innermost_enclosing_class() -> None:
    src = (
        "class A:\n"
        "    def save(self):\n"
        "        pass\n"
        "    def go(self):\n"
        "        return self.save()\n"
    )
    idx = index(**{"app.py": src})
    assert resolve(idx, "app.py", "self.save", "A.go") == Target("app.py", "A.save")


def test_cls_binds_the_same_way() -> None:
    src = (
        "class A:\n"
        "    def save(cls):\n"
        "        pass\n"
        "    def go(cls):\n"
        "        return cls.save()\n"
    )
    idx = index(**{"app.py": src})
    assert resolve(idx, "app.py", "cls.save", "A.go") == Target("app.py", "A.save")


def test_self_does_not_reach_an_inherited_method() -> None:
    src = (
        "class B:\n"
        "    def save(self):\n"
        "        pass\n"
        "\n"
        "class A(B):\n"
        "    def go(self):\n"
        "        return self.save()\n"
    )
    idx = index(**{"app.py": src})
    assert resolve(idx, "app.py", "self.save", "A.go") is None


def test_two_classes_with_the_same_method_name_do_not_collide() -> None:
    src = (
        "class A:\n"
        "    def save(self):\n"
        "        pass\n"
        "    def go(self):\n"
        "        return self.save()\n"
        "\n"
        "class B:\n"
        "    def save(self):\n"
        "        pass\n"
    )
    idx = index(**{"app.py": src})
    assert resolve(idx, "app.py", "self.save", "A.go") == Target("app.py", "A.save")


# -- refusals


def test_a_call_through_a_variable_binds_to_nothing() -> None:
    idx = index(**{"app.py": "def f():\n    pass\n\ndef g():\n    h = f\n    return h()\n"})
    assert resolve(idx, "app.py", "h", "g") is None


def test_a_deeper_attribute_chain_binds_to_nothing() -> None:
    idx = index(
        **{
            "pkg__mathlib.py": "def sqrt(x):\n    return x\n",
            "app.py": "import pkg\n\ndef go():\n    return pkg.mathlib.sqrt(9)\n",
        }
    )
    assert resolve(idx, "app.py", "pkg.mathlib.sqrt", "go") is None


def test_an_unparsable_file_binds_nothing() -> None:
    idx = index(**{"app.py": "def f(:\n"})
    assert resolve(idx, "app.py", "f", None) is None


def test_a_missing_file_binds_nothing() -> None:
    idx = BindingIndex(["app.py"], lambda path: None)
    assert resolve(idx, "app.py", "f", None) is None


# -- the expression reader


def test_dotted_name_reads_a_plain_chain_and_refuses_anything_else() -> None:
    assert dotted_name(ast.parse("a.b.c()").body[0].value.func) == "a.b.c"
    assert dotted_name(ast.parse("f()").body[0].value.func) == "f"
    assert dotted_name(ast.parse("d['k']()").body[0].value.func) is None
    assert dotted_name(ast.parse("g()()").body[0].value.func) is None
