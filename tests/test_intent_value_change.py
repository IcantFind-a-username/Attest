"""D-127: a value mismatch publishes only against a base specification this change left standing.

The case that forced the rule is `G-NULL-001a` control `jinja ac3ac6c9` -- a
deliberate, commented, four-year-old change of a wrapper's ``__name__`` that the
product published as a defect. The first test is that control: the real generated
test body from the published bundle, the real base and head revisions of the
anchored file, and a base tree carrying the shape jinja's own tests have. The
full-tree replay over the clone is in
`scripts/corpus/intent_v3_replay.py` and reports the same verdict and the same
pinned set.
"""

from __future__ import annotations

from pathlib import Path

from attest.certification.intent import (
    EVIDENCE_CLASS_BEHAVIOR_CHANGE,
    EVIDENCE_CLASS_REGRESSION,
    INTENT_STATED_LABEL,
    INTENT_STATED_LABEL_ZH,
    IntentObservation,
    evidence_class_for,
    intent_verdict,
)
from attest.review.intent import observe_intent

ASSERTION = (
    "AssertionError: expected wrapper name to come from the sync function, got "
    "'async_func' assert 'async_func' == 'normal_func'"
)
# D-132 (a) reads the failing assertion's line out of pytest's longrepr; these
# tests state it explicitly rather than re-deriving it from the body.
def _longrepr(line: int) -> str:
    return f"E       {ASSERTION}\n\n.attest-repro/test_repro.py:{line}: AssertionError"

# --- the jinja control, verbatim where it matters -----------------------------

JINJA_BASE = (
    "from functools import wraps\n"
    "\n"
    "\n"
    "def async_variant(normal_func):\n"
    "    def decorator(async_func):\n"
    "        @wraps(normal_func)\n"
    "        def wrapper(*args, **kwargs):\n"
    "            return normal_func(*args, **kwargs)\n"
    "\n"
    "        wrapper.jinja_async_variant = True\n"
    "        return wrapper\n"
    "\n"
    "    return decorator\n"
)
# the commit: the name comes from the async function on purpose, and says so
JINJA_HEAD = (
    "from functools import WRAPPER_ASSIGNMENTS\n"
    "from functools import wraps\n"
    "\n"
    "\n"
    "def async_variant(normal_func):\n"
    "    def decorator(async_func):\n"
    "        # Take the doc and annotations from the sync function, but the\n"
    "        # name from the async function.\n"
    '        async_func_attrs = ("__module__", "__name__", "__qualname__")\n'
    "        normal_func_attrs = tuple(set(WRAPPER_ASSIGNMENTS).difference(async_func_attrs))\n"
    "\n"
    "        @wraps(normal_func, assigned=normal_func_attrs)\n"
    "        @wraps(async_func, assigned=async_func_attrs, updated=())\n"
    "        def wrapper(*args, **kwargs):\n"
    "            return normal_func(*args, **kwargs)\n"
    "\n"
    "        wrapper.jinja_async_variant = True\n"
    "        return wrapper\n"
    "\n"
    "    return decorator\n"
)
# the published reproduction, from
# .attest/evidence/20260904-054801-e2a48c5d/5d27c0905c/test_repro.py
JINJA_TEST = (
    "from jinja2.async_utils import async_variant\n"
    "\n"
    "\n"
    "def test_async_variant_does_not_copy_normal_func_dict():\n"
    "    def normal_func(eval_ctx, value):\n"
    "        return value\n"
    "\n"
    '    normal_func.marker = "from_normal"\n'
    "\n"
    "    @async_variant(normal_func)\n"
    "    async def async_func(eval_ctx, value):\n"
    "        return value\n"
    "\n"
    "    wrapper = async_func\n"
    '    assert wrapper.__name__ == "normal_func", (\n'
    '        f"expected wrapper name to come from the sync function, got "\n'
    '        f"{wrapper.__name__!r}"\n'
    "    )\n"
    '    assert getattr(wrapper, "__wrapped__", None) is normal_func\n'
    '    assert wrapper.marker == "from_normal"\n'
    "    assert wrapper.jinja_async_variant is True\n"
)
# what jinja's own tests say about async_variant: that it is one, not what it is
# called. `True` and `None` are asserted all over the tree; the names are not.
JINJA_BASE_TESTS = (
    "from jinja2.async_utils import async_variant\n"
    "\n"
    "\n"
    "def test_async_variant_marks_the_wrapper():\n"
    "    def sync(eval_ctx, value):\n"
    "        return value\n"
    "\n"
    "    @async_variant(sync)\n"
    "    async def other(eval_ctx, value):\n"
    "        return value\n"
    "\n"
    "    assert other.jinja_async_variant is True\n"
    "    assert getattr(other, 'missing', None) is None\n"
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _observe(tmp_path: Path, *, base: dict[str, str], head: dict[str, str], test: str,
             path: str, changed: tuple[int, ...], failing_line: int,
             changed_files: tuple[str, ...] = ()) -> IntentObservation:
    base_tree = _tree(tmp_path / "base", base)
    head_tree = _tree(tmp_path / "head", head)
    observed = observe_intent(
        path=path,
        changed_lines=changed,
        head_source=(head_tree / path).read_text(encoding="utf-8"),
        base_source=(base_tree / path).read_text(encoding="utf-8"),
        test_source=test,
        head_origins=[(), (), ()],
        head_failures=[ASSERTION] * 3,
        head_failure_details=[_longrepr(failing_line)] * 3,
        changed_files=changed_files or (path,),
        base_tree=base_tree,
        head_tree=head_tree,
    )
    assert isinstance(observed, IntentObservation), observed
    return observed


def test_the_jinja_control_goes_to_the_drawer(tmp_path: Path) -> None:
    """`G-NULL-001a` control `jinja ac3ac6c9`: the publication D-127 exists to stop."""
    anchored = "src/jinja2/async_utils.py"

    observed = _observe(
        tmp_path,
        base={anchored: JINJA_BASE, "tests/test_async.py": JINJA_BASE_TESTS},
        head={anchored: JINJA_HEAD, "tests/test_async.py": JINJA_BASE_TESTS},
        test=JINJA_TEST,
        path=anchored,
        changed=tuple(range(1, 21)),
        failing_line=15,
    )

    assert observed.value_mismatch
    # D-132 (a): only the assertion that failed. `wrapper.__name__ == "normal_func"`
    # is the one the head runs raised on; the marker and flag assertions below it
    # never ran and state nothing about this differential.
    assert observed.pinned_values == ("'normal_func'",)
    # the name is stated nowhere in jinja's own tests
    assert observed.value_specified == ()
    # D-132 (c), on its own: the commit adds an inline comment inside the very
    # function it changes, saying which name it now takes and why
    assert observed.anchored_symbols == ("async_variant", "decorator", "wrapper")
    assert observed.intent_evidence == (("decorator", anchored),)
    verdict = intent_verdict(observed)
    assert verdict is not None and verdict.startswith(INTENT_STATED_LABEL)
    assert INTENT_STATED_LABEL_ZH in verdict
    assert evidence_class_for(observed) == EVIDENCE_CLASS_BEHAVIOR_CHANGE
    # author-visible: the verdict names neither the file nor the value (D-091)
    assert anchored not in verdict and "normal_func" not in verdict


# --- a specified value, and a change that leaves the specification standing ---

SPEC_BASE = (
    "def slug(title):\n"
    '    """Return the URL slug: ``slug("Hello World")`` is ``"hello-world"``."""\n'
    '    return title.lower().replace(" ", "-")\n'
)
SPEC_HEAD_DEFECT = (
    "def slug(title):\n"
    '    """Return the URL slug: ``slug("Hello World")`` is ``"hello-world"``."""\n'
    '    return title.replace(" ", "-")\n'
)
SPEC_HEAD_RENAMED = (
    "def slug(title):\n"
    '    """Return the URL slug: ``slug("Hello World")`` is ``"Hello-World"``."""\n'
    '    return title.replace(" ", "-")\n'
)
SPEC_TEST = (
    "import mod\n"
    "\n"
    "\n"
    "def test_repro():\n"
    '    assert mod.slug("Hello World") == "hello-world"\n'
)
SPEC_BASE_TESTS = (
    "import mod\n"
    "\n"
    "\n"
    "def test_slug():\n"
    '    assert mod.slug("Hello World") == "hello-world"\n'
)


def test_a_value_the_base_specifies_and_the_change_leaves_alone_publishes(
    tmp_path: Path,
) -> None:
    """The defect case: the base tree states the old value in a test *and* in the
    docstring, and the change rewrites neither. That is a regression."""
    observed = _observe(
        tmp_path,
        base={"mod.py": SPEC_BASE, "tests/test_mod.py": SPEC_BASE_TESTS},
        head={"mod.py": SPEC_HEAD_DEFECT, "tests/test_mod.py": SPEC_BASE_TESTS},
        test=SPEC_TEST,
        path="mod.py",
        changed=(3,),
        failing_line=5,
    )

    assert observed.value_mismatch
    assert observed.pinned_values == ("'hello-world'",)  # the input is not pinned
    assert observed.value_respecified == ()
    assert intent_verdict(observed) is None
    assert evidence_class_for(observed) == EVIDENCE_CLASS_REGRESSION


def test_a_value_nothing_in_the_base_specifies_goes_to_the_drawer(tmp_path: Path) -> None:
    """The same change with no test and no docstring saying what ``slug`` returns:
    the reproduction invented the expected value, and nothing certifies it."""
    bare_base = 'def slug(title):\n    return title.lower().replace(" ", "-")\n'
    bare_head = 'def slug(title):\n    return title.replace(" ", "-")\n'

    observed = _observe(
        tmp_path,
        base={"mod.py": bare_base},
        head={"mod.py": bare_head},
        test=SPEC_TEST,
        path="mod.py",
        changed=(2,),
        failing_line=5,
    )

    assert observed.value_specified == ()
    verdict = intent_verdict(observed)
    assert verdict is not None and "does not specify the value" in verdict
    assert evidence_class_for(observed) == EVIDENCE_CLASS_BEHAVIOR_CHANGE


def test_a_specification_the_same_change_rewrites_goes_to_the_drawer(tmp_path: Path) -> None:
    """The author moved the value and updated the docstring that stated it. The
    generated test restates the old one; that is intent, not a defect."""
    observed = _observe(
        tmp_path,
        base={"mod.py": SPEC_BASE},
        head={"mod.py": SPEC_HEAD_RENAMED},
        test=SPEC_TEST,
        path="mod.py",
        changed=(2, 3),
        failing_line=5,
    )

    assert {value for value, _site in observed.value_specified} == {"'hello-world'"}
    assert [value for value, _site in observed.value_respecified] == ["'hello-world'"]
    verdict = intent_verdict(observed)
    assert verdict is not None and "rewrites the base tree's own specification" in verdict
    assert evidence_class_for(observed) == EVIDENCE_CLASS_BEHAVIOR_CHANGE


def test_a_crash_is_not_a_value_mismatch_and_still_publishes(tmp_path: Path) -> None:
    """The rule is scoped to value mismatches: a head run that fails because the
    code raised is a regression as before, with no specification required."""
    base_tree = _tree(tmp_path / "base", {"mod.py": SPEC_BASE})
    head_tree = _tree(tmp_path / "head", {"mod.py": SPEC_HEAD_DEFECT})

    observed = observe_intent(
        path="mod.py",
        changed_lines=(3,),
        head_source=(head_tree / "mod.py").read_text(encoding="utf-8"),
        base_source=(base_tree / "mod.py").read_text(encoding="utf-8"),
        test_source=SPEC_TEST,
        head_origins=[(), (), ()],
        head_failures=["AttributeError: 'NoneType' object has no attribute 'lower'"] * 3,
        head_failure_details=["src/mod.py:3: AttributeError"] * 3,
        changed_files=("mod.py",),
        base_tree=base_tree,
        head_tree=head_tree,
    )

    assert isinstance(observed, IntentObservation)
    assert not observed.value_mismatch and observed.pinned_values == ()
    assert intent_verdict(observed) is None
    assert evidence_class_for(observed) == EVIDENCE_CLASS_REGRESSION


def test_without_a_head_tree_nothing_can_be_shown_to_stand(tmp_path: Path) -> None:
    """Fail closed: a specification whose head revision could not be read is
    reported as rewritten, never as standing."""
    base_tree = _tree(tmp_path / "base", {"mod.py": SPEC_BASE, "tests/t.py": SPEC_BASE_TESTS})

    observed = observe_intent(
        path="mod.py",
        changed_lines=(3,),
        head_source=SPEC_HEAD_DEFECT,
        base_source=SPEC_BASE,
        test_source=SPEC_TEST,
        head_origins=[(), (), ()],
        head_failures=[ASSERTION] * 3,
        head_failure_details=[_longrepr(5)] * 3,
        changed_files=("mod.py",),
        base_tree=base_tree,
        head_tree=None,
    )

    assert isinstance(observed, IntentObservation)
    assert observed.value_specified and len(observed.value_respecified) == len(
        observed.value_specified
    )
    assert intent_verdict(observed) is not None
