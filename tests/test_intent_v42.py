"""D-174: `attest.intent.v4.2` -- a specification must be *about* the symbol.

v4.1 asked whether the base tree specifies the value the failing assertion pins.
It did not ask what the specification was **about**. So a tree holding
``assert len("weekday") == 7`` anywhere specified the value ``7`` for every
function in the repository that returns it, and a receipt about a function whose
result moved 7 -> 8 published against a sentence that was never about it.

v4.2 adds the association and nothing else. An assertion counts only when its own
scope -- the test function it sits in, or the module top level -- **references an
anchored symbol**; a docstring counts only when it *is* that symbol's docstring
or names it; a documentation paragraph counts only when the paragraph names it.
No anchored symbol at all means no specification is possible, and the receipt
goes to the drawer with that as its reason.
"""

from __future__ import annotations

from pathlib import Path

from attest.certification.intent import (
    INTENT_POLICY_VERSION,
    POLICY_FIELDS,
    IntentObservation,
    intent_verdict,
)
from attest.review.intent import observe_intent

CONV_BASE = 'def convert(n):\n    """Days."""\n    return n + 6\n'
CONV_HEAD = 'def convert(n):\n    """Days."""\n    return n + 7\n'
CONV_REPRO = "import convert\n\n\ndef test_repro():\n    assert convert.convert(1) == 7\n"
CONV_LONGREPR = (
    "    def test_repro():\n"
    ">       assert convert.convert(1) == 7\n"
    "E       AssertionError: assert 8 == 7\n"
    "\n"
    ".attest-repro/test_repro.py:5: AssertionError"
)
MESSAGE = "AssertionError: assert 8 == 7"

# the counterexample the owner named: a sentence about the word "weekday",
# which pins 7 and says nothing about any function
UNRELATED_SPEC = 'def test_word_length():\n    assert len("weekday") == 7\n'
ASSOCIATED_ATTRIBUTE = (
    "import convert\n\n\ndef test_convert():\n    assert convert.convert(1) == 7\n"
)
ASSOCIATED_IMPORT = (
    "from convert import convert\n\n\ndef test_convert():\n    assert convert(1) == 7\n"
)


def _tree(root: Path, files: dict[str, str]) -> Path:
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _observe(
    tmp_path: Path,
    *,
    base: dict[str, str],
    head: dict[str, str],
    test: str = CONV_REPRO,
    path: str = "convert.py",
    changed: tuple[int, ...] = (3,),
    longrepr: str = CONV_LONGREPR,
    runs: int = 3,
) -> IntentObservation:
    base_tree = _tree(tmp_path / "base", base)
    head_tree = _tree(tmp_path / "head", head)
    observed = observe_intent(
        path=path,
        changed_lines=changed,
        head_source=(head_tree / path).read_text(encoding="utf-8"),
        base_source=(base_tree / path).read_text(encoding="utf-8"),
        test_source=test,
        head_origins=[() for _ in range(runs)],
        head_failures=[MESSAGE] * runs,
        head_failure_details=[longrepr] * runs,
        base_tree=base_tree,
        head_tree=head_tree,
        changed_files=(path,),
    )
    assert isinstance(observed, IntentObservation), observed
    return observed


# --- the counterexample --------------------------------------------------------


def test_an_assertion_about_nothing_in_this_change_is_not_a_specification(
    tmp_path: Path,
) -> None:
    """RED. `assert len("weekday") == 7` pins 7 and is about the word "weekday".
    Reading it as the base tree's specification of `convert`'s result publishes a
    defect claim against a sentence that was never about `convert`."""
    observed = _observe(
        tmp_path,
        base={"convert.py": CONV_BASE, "tests/test_words.py": UNRELATED_SPEC},
        head={"convert.py": CONV_HEAD, "tests/test_words.py": UNRELATED_SPEC},
    )

    assert observed.pinned_values == ("7",)
    assert observed.anchored_symbols == ("convert",)
    assert observed.value_specified == ()
    verdict = intent_verdict(observed)
    assert verdict is not None
    assert "does not specify" in verdict


# --- the two retained positives ------------------------------------------------


def test_an_assertion_that_names_the_symbol_by_attribute_is_a_specification(
    tmp_path: Path,
) -> None:
    """`assert convert.convert(1) == 7`: the scope names the anchored symbol."""
    observed = _observe(
        tmp_path,
        base={"convert.py": CONV_BASE, "tests/test_convert.py": ASSOCIATED_ATTRIBUTE},
        head={"convert.py": CONV_HEAD, "tests/test_convert.py": ASSOCIATED_ATTRIBUTE},
    )

    assert {value for value, _site in observed.value_specified} == {"7"}
    assert intent_verdict(observed) is None


def test_an_assertion_that_names_the_imported_symbol_is_a_specification(
    tmp_path: Path,
) -> None:
    """`from convert import convert; assert convert(1) == 7`: the import binds the
    name and the assertion writes it."""
    observed = _observe(
        tmp_path,
        base={"convert.py": CONV_BASE, "tests/test_convert.py": ASSOCIATED_IMPORT},
        head={"convert.py": CONV_HEAD, "tests/test_convert.py": ASSOCIATED_IMPORT},
    )

    assert {value for value, _site in observed.value_specified} == {"7"}
    assert intent_verdict(observed) is None


# --- no anchored symbol at all --------------------------------------------------

MODULE_LEVEL_BASE = (
    "import re\n"
    "\n"
    "\n"
    "def slug(title):\n"
    '    """Return the URL slug."""\n'
    '    return title.lower().replace(" ", "-")\n'
)
MODULE_LEVEL_HEAD = MODULE_LEVEL_BASE.replace("import re\n", "import re as regex\n")
SLUG_TESTS = (
    "import mod\n\n\ndef test_slug():\n    assert mod.slug(\"Hello World\") == \"hello-world\"\n"
)
SLUG_REPRO = (
    "import mod\n\n\ndef test_repro():\n    assert mod.slug(\"Hello World\") == \"hello-world\"\n"
)
SLUG_LONGREPR = (
    "    def test_repro():\n"
    '>       assert mod.slug("Hello World") == "hello-world"\n'
    "E       AssertionError: assert 'Hello-World' == 'hello-world'\n"
    "\n"
    ".attest-repro/test_repro.py:5: AssertionError"
)


def test_a_change_that_touches_no_symbol_can_have_no_specification(
    tmp_path: Path,
) -> None:
    """A changed line at module level anchors no def or class. Nothing in the
    base tree can be a specification *of* it, so the receipt is drawered and the
    reason says which half is missing."""
    observed = _observe(
        tmp_path,
        base={"mod.py": MODULE_LEVEL_BASE, "tests/test_mod.py": SLUG_TESTS},
        head={"mod.py": MODULE_LEVEL_HEAD, "tests/test_mod.py": SLUG_TESTS},
        test=SLUG_REPRO,
        path="mod.py",
        changed=(1,),
        longrepr=SLUG_LONGREPR,
    )

    assert observed.anchored_symbols == ()
    assert observed.pinned_values == ("'hello-world'",)
    assert observed.value_specified == ()
    verdict = intent_verdict(observed)
    assert verdict is not None
    assert "no symbol" in verdict


# --- documentation is associated by paragraph -----------------------------------

DOC_ABOUT = (
    "Utilities\n"
    "=========\n"
    "\n"
    "The ``slug`` helper turns ``Hello World`` into ``hello-world``.\n"
)
DOC_ELSEWHERE = (
    "Utilities\n"
    "=========\n"
    "\n"
    "The ``slug`` helper normalises titles.\n"
    "\n"
    "Our canonical example everywhere in this project is ``hello-world``.\n"
)
SLUG_BASE = (
    "def slug(title):\n"
    '    """Return the URL slug."""\n'
    '    return title.lower().replace(" ", "-")\n'
)
SLUG_HEAD = (
    "def slug(title):\n"
    '    """Return the URL slug."""\n'
    '    return title.replace(" ", "-")\n'
)


def test_a_documentation_paragraph_that_names_the_symbol_specifies_the_value(
    tmp_path: Path,
) -> None:
    observed = _observe(
        tmp_path,
        base={"mod.py": SLUG_BASE, "docs/guide.rst": DOC_ABOUT},
        head={"mod.py": SLUG_HEAD, "docs/guide.rst": DOC_ABOUT},
        test=SLUG_REPRO,
        path="mod.py",
        changed=(3,),
        longrepr=SLUG_LONGREPR,
    )

    assert {value for value, _site in observed.value_specified} == {"'hello-world'"}
    assert intent_verdict(observed) is None


def test_a_value_quoted_in_another_paragraph_specifies_nothing(tmp_path: Path) -> None:
    """The same file, the same value, a different paragraph. Association is by
    paragraph because a document is a sequence of statements, not one statement."""
    observed = _observe(
        tmp_path,
        base={"mod.py": SLUG_BASE, "docs/guide.rst": DOC_ELSEWHERE},
        head={"mod.py": SLUG_HEAD, "docs/guide.rst": DOC_ELSEWHERE},
        test=SLUG_REPRO,
        path="mod.py",
        changed=(3,),
        longrepr=SLUG_LONGREPR,
    )

    assert observed.value_specified == ()
    assert intent_verdict(observed) is not None


# --- the version is recorded and replayed ---------------------------------------


def test_the_policy_version_is_v42_and_registered(tmp_path: Path) -> None:
    observed = _observe(
        tmp_path,
        base={"convert.py": CONV_BASE, "tests/test_convert.py": ASSOCIATED_IMPORT},
        head={"convert.py": CONV_HEAD, "tests/test_convert.py": ASSOCIATED_IMPORT},
    )

    assert observed.policy_version == INTENT_POLICY_VERSION == "attest.intent.v4.2"
    assert INTENT_POLICY_VERSION in POLICY_FIELDS


def test_a_v41_receipt_is_still_judged_under_v41() -> None:
    """D-121: a receipt is judged under the version it records. The association
    rule did not exist when a v4.1 observation was written, and applying it
    retroactively would void receipts nobody re-adjudicated."""
    older = IntentObservation(
        policy_version="attest.intent.v4.1",
        path="mod.py",
        changed_lines=(3,),
        origin_line=0,
        origin_statement="",
        exception_type="",
        new_rejection=False,
        rejected_inputs=(),
        witnesses=(),
        head_runs_observed=3,
        value_mismatch=True,
        pinned_values=("'hello-world'",),
        value_specified=(("'hello-world'", "tests/test_mod.py"),),
        failing_assertion_line=5,
        anchored_symbols=(),  # v4.2 would drawer this; v4.1 never asked
    )

    assert intent_verdict(older) is None
