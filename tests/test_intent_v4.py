"""D-132: `attest.intent.v4` -- three narrowings of D-127's value rule.

Each clause has its own failing case, and each of the two live wrong
publications this product made is drawered by clause (c) **on its own**, with
the other two clauses satisfied:

  (a) the pinned set is the assertion that *failed*, read from the head runs'
      JUnit longrepr, not every ``assert`` in the generated test;
  (b) a generic constant (``True``/``False``/``None``/``0``/``1``/``""``) is not
      a specification, so a receipt needs at least one distinctive value;
  (c) any test, docstring, docs, changelog or inline-comment change in the same
      diff that touches the anchored symbol is intent, and drawers the receipt.

The composite rule: **the base tree specifies it, head still specifies it, and
the diff carries no intent evidence** -- otherwise the drawer.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from attest.certification.intent import (
    EVIDENCE_CLASS_BEHAVIOR_CHANGE,
    EVIDENCE_CLASS_REGRESSION,
    INTENT_POLICY_V3,
    INTENT_POLICY_VERSION,
    INTENT_STATED_LABEL,
    IntentObservation,
    distinctive_pinned_values,
    evidence_class_for,
    intent_verdict,
)
from attest.review.intent import failing_assertion_line, observe_intent

# --- a defect with a specified value and a diff that says nothing about it ----

MOD_BASE = (
    "def slug(title):\n"
    '    """Return the URL slug: ``slug("Hello World")`` is ``"hello-world"``."""\n'
    '    return title.lower().replace(" ", "-")\n'
)
MOD_HEAD = (
    "def slug(title):\n"
    '    """Return the URL slug: ``slug("Hello World")`` is ``"hello-world"``."""\n'
    '    return title.replace(" ", "-")\n'
)
MOD_TESTS = (
    "import mod\n"
    "\n"
    "\n"
    "def test_slug():\n"
    '    assert mod.slug("Hello World") == "hello-world"\n'
)
# two assertions; the *second* is the one that fails
MOD_REPRO = (
    "import mod\n"
    "\n"
    "\n"
    "def test_repro():\n"
    "    assert mod.slug is not None\n"
    '    assert mod.slug("Hello World") == "hello-world"\n'
)
MOD_LONGREPR = (
    "    def test_repro():\n"
    "        assert mod.slug is not None\n"
    '>       assert mod.slug("Hello World") == "hello-world"\n'
    "E       AssertionError: assert 'Hello-World' == 'hello-world'\n"
    "\n"
    ".attest-repro/test_repro.py:6: AssertionError"
)
MESSAGE = "AssertionError: assert 'Hello-World' == 'hello-world'"


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
    test: str,
    path: str,
    changed: tuple[int, ...],
    changed_files: tuple[str, ...] = (),
    longrepr: str = MOD_LONGREPR,
    message: str = MESSAGE,
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
        head_failures=[message] * runs,
        head_failure_details=[longrepr] * runs,
        changed_files=changed_files or (path,),
        base_tree=base_tree,
        head_tree=head_tree,
    )
    assert isinstance(observed, IntentObservation), observed
    assert observed.policy_version == INTENT_POLICY_VERSION
    return observed


def test_a_specified_value_with_no_intent_evidence_in_the_diff_publishes(
    tmp_path: Path,
) -> None:
    """The composite rule's one publishing branch: the base tree states
    ``"hello-world"`` in a test and in the docstring, head still states it, and
    the diff touches no test, doc, changelog or comment about ``slug``."""
    observed = _observe(
        tmp_path,
        base={"mod.py": MOD_BASE, "tests/test_mod.py": MOD_TESTS},
        head={"mod.py": MOD_HEAD, "tests/test_mod.py": MOD_TESTS},
        test=MOD_REPRO,
        path="mod.py",
        changed=(3,),
    )

    assert observed.value_mismatch
    assert observed.failing_assertion_line == 6
    assert observed.anchored_symbols == ("slug",)
    assert observed.intent_evidence == ()
    assert observed.pinned_values == ("'hello-world'",)
    assert intent_verdict(observed) is None
    assert evidence_class_for(observed) == EVIDENCE_CLASS_REGRESSION


# --- (a) the pinned set is the failing assertion's -----------------------------


def test_only_the_failing_assertion_contributes_pinned_values(tmp_path: Path) -> None:
    """The reproduction pins ``'hello-world'`` on line 6 and a distinctive
    ``'Widget'`` on line 5. The failure is on 5; the pinned set is line 5's."""
    repro = (
        "import mod\n"
        "\n"
        "\n"
        "def test_repro():\n"
        '    assert mod.NAME == "Widget"\n'
        '    assert mod.slug("Hello World") == "hello-world"\n'
    )
    longrepr = (
        "    def test_repro():\n"
        '>       assert mod.NAME == "Widget"\n'
        "E       AssertionError: assert 'Gadget' == 'Widget'\n"
        "\n"
        ".attest-repro/test_repro.py:5: AssertionError"
    )

    observed = _observe(
        tmp_path,
        base={"mod.py": MOD_BASE, "tests/test_mod.py": MOD_TESTS},
        head={"mod.py": MOD_HEAD, "tests/test_mod.py": MOD_TESTS},
        test=repro,
        path="mod.py",
        changed=(3,),
        longrepr=longrepr,
        message="AssertionError: assert 'Gadget' == 'Widget'",
    )

    assert observed.failing_assertion_line == 5
    assert observed.pinned_values == ("'Widget'",)


def test_a_failure_raised_outside_any_assertion_pins_nothing(tmp_path: Path) -> None:
    """`G-NULL-001a` control `urllib3 c7b9adcb`, clause (a): the failure is a bare
    ``raise AssertionError`` in a stub the test defines, so the ``assert ... is
    False`` further down is not the failing assertion and pins nothing."""
    repro = (
        "import mod\n"
        "\n"
        "\n"
        "def test_repro():\n"
        "    class Stub:\n"
        "        def getresponse(self):\n"
        "            raise AssertionError('must not be reached')\n"
        "\n"
        "    called = mod.run(Stub())\n"
        "    assert called is False\n"
    )
    longrepr = (
        "    def getresponse(self):\n"
        ">       raise AssertionError('must not be reached')\n"
        "E       AssertionError: must not be reached\n"
        "\n"
        ".attest-repro/test_repro.py:7: AssertionError"
    )

    observed = _observe(
        tmp_path,
        base={"mod.py": MOD_BASE, "tests/test_mod.py": MOD_TESTS},
        head={"mod.py": MOD_HEAD, "tests/test_mod.py": MOD_TESTS},
        test=repro,
        path="mod.py",
        changed=(3,),
        longrepr=longrepr,
        message="AssertionError: must not be reached",
    )

    assert observed.failing_assertion_line == 7
    assert observed.pinned_values == ()
    verdict = intent_verdict(observed)
    assert verdict is not None and "pins no value" in verdict
    assert evidence_class_for(observed) == EVIDENCE_CLASS_BEHAVIOR_CHANGE


def test_head_runs_that_disagree_on_the_failing_line_pin_nothing(tmp_path: Path) -> None:
    """Fail closed: two head runs failing on different assertions cannot say
    which one the differential is about."""
    other = MOD_LONGREPR.replace("test_repro.py:6", "test_repro.py:5")
    base_tree = _tree(tmp_path / "base", {"mod.py": MOD_BASE, "tests/t.py": MOD_TESTS})
    head_tree = _tree(tmp_path / "head", {"mod.py": MOD_HEAD, "tests/t.py": MOD_TESTS})

    observed = observe_intent(
        path="mod.py",
        changed_lines=(3,),
        head_source=MOD_HEAD,
        base_source=MOD_BASE,
        test_source=MOD_REPRO,
        head_origins=[(), (), ()],
        head_failures=[MESSAGE] * 3,
        head_failure_details=[MOD_LONGREPR, other, MOD_LONGREPR],
        changed_files=("mod.py",),
        base_tree=base_tree,
        head_tree=head_tree,
    )

    assert isinstance(observed, IntentObservation)
    assert observed.failing_assertion_line == 0
    assert observed.pinned_values == ()
    assert intent_verdict(observed) is not None


def test_the_longrepr_parser_takes_the_innermost_test_frame() -> None:
    assert failing_assertion_line(MOD_LONGREPR) == 6
    chained = (
        ".attest-repro/test_repro.py:56: \n"
        "_ _ _ _ _ _ _\n"
        "src/urllib3/connectionpool.py:537: in _make_request\n"
        "    response = conn.getresponse()\n"
        "_ _ _ _ _ _ _\n"
        ".attest-repro/test_repro.py:43: AssertionError"
    )
    assert failing_assertion_line(chained) == 43
    assert failing_assertion_line("") == 0
    assert failing_assertion_line("src/urllib3/connectionpool.py:537: ValueError") == 0


# --- (b) a generic constant is not a specification -----------------------------


def test_a_pinned_set_of_only_generic_constants_goes_to_the_drawer(
    tmp_path: Path,
) -> None:
    """`G-NULL-001a` control `urllib3 c7b9adcb`, clause (b): ``False`` is asserted
    somewhere in almost any tree, so a receipt resting only on it rests on a
    coincidence of vocabulary."""
    repro = (
        "import mod\n"
        "\n"
        "\n"
        "def test_repro():\n"
        "    assert mod.tolerated() is False\n"
    )
    longrepr = (
        "    def test_repro():\n"
        ">       assert mod.tolerated() is False\n"
        "E       assert True is False\n"
        "\n"
        ".attest-repro/test_repro.py:5: AssertionError"
    )
    # the literal `False` survives the change, so this is not D-120's constant
    # substitution: what moved is the expression, and clause (b) is what stops it
    base = MOD_BASE + "\n\nTOLERATED = False\n\n\ndef tolerated():\n    return TOLERATED\n"
    head = MOD_HEAD + "\n\nTOLERATED = False\n\n\ndef tolerated():\n    return not TOLERATED\n"
    tests = MOD_TESTS + "\n\ndef test_tolerated():\n    assert mod.tolerated() is False\n"

    observed = _observe(
        tmp_path,
        base={"mod.py": base, "tests/test_mod.py": tests},
        head={"mod.py": head, "tests/test_mod.py": tests},
        test=repro,
        path="mod.py",
        changed=(9,),
        longrepr=longrepr,
        message="assert True is False",
    )

    assert observed.pinned_values == ("False",)
    # the base tree does assert `is False` -- and that is exactly the coincidence
    assert observed.value_specified == ()
    verdict = intent_verdict(observed)
    assert verdict is not None and "generic constant" in verdict
    assert evidence_class_for(observed) == EVIDENCE_CLASS_BEHAVIOR_CHANGE


def test_one_distinctive_value_among_generic_ones_still_publishes(
    tmp_path: Path,
) -> None:
    """(b) removes generic constants from the requirement rather than poisoning
    the receipt: a set of ``{'hello-world', None}`` still rests on a real
    specification."""
    repro = (
        "import mod\n"
        "\n"
        "\n"
        "def test_repro():\n"
        '    assert mod.slug("Hello World", None) == "hello-world"\n'
    )
    longrepr = (
        "    def test_repro():\n"
        '>       assert mod.slug("Hello World", None) == "hello-world"\n'
        "E       AssertionError\n"
        "\n"
        ".attest-repro/test_repro.py:5: AssertionError"
    )
    observed = _observe(
        tmp_path,
        base={"mod.py": MOD_BASE, "tests/test_mod.py": MOD_TESTS},
        head={"mod.py": MOD_HEAD, "tests/test_mod.py": MOD_TESTS},
        test=repro,
        path="mod.py",
        changed=(3,),
        longrepr=longrepr,
    )

    assert observed.pinned_values == ("'hello-world'",)  # a call's arguments are not pinned
    assert intent_verdict(observed) is None


# --- (c) intent evidence in the diff -------------------------------------------


def test_a_comment_added_inside_the_anchored_symbol_is_intent(tmp_path: Path) -> None:
    """`G-NULL-001a` control `urllib3 c7b9adcb`, clause (c), in the shape the real
    diff has: the tolerated-errno set is widened and the comment above it is
    rewritten in the same three lines. Clauses (a) and (b) are satisfied here --
    the failing assertion pins a distinctive value the base tree specifies -- so
    this drawers the receipt on its own."""
    head = (
        "def slug(title):\n"
        '    """Return the URL slug: ``slug("Hello World")`` is ``"hello-world"``."""\n'
        "    # Casing is now the caller's business; the slug keeps what it is given.\n"
        '    return title.replace(" ", "-")\n'
    )

    observed = _observe(
        tmp_path,
        base={"mod.py": MOD_BASE, "tests/test_mod.py": MOD_TESTS},
        head={"mod.py": head, "tests/test_mod.py": MOD_TESTS},
        test=MOD_REPRO,
        path="mod.py",
        changed=(3, 4),
    )

    assert observed.pinned_values == ("'hello-world'",)
    assert {value for value, _site in observed.value_specified} == {"'hello-world'"}
    assert observed.value_respecified == ()
    assert [site for _symbol, site in observed.intent_evidence] == ["mod.py"]
    verdict = intent_verdict(observed)
    assert verdict is not None and "the same change" in verdict
    assert evidence_class_for(observed) == EVIDENCE_CLASS_BEHAVIOR_CHANGE
    # author-visible: no file, no line, no value (D-091)
    assert "mod.py" not in verdict and "hello-world" not in verdict


def test_a_changelog_entry_naming_the_anchored_symbol_is_intent(tmp_path: Path) -> None:
    """`G-NULL-001a` control `jinja ac3ac6c9` in the shape a released project has
    it: the behaviour change is announced in the changelog, by name."""
    news_base = "Version 3.1.0\n-------------\n\n-   Nothing yet.\n"
    news_head = (
        "Version 3.1.0\n"
        "-------------\n"
        "\n"
        "-   ``slug`` no longer lower-cases its input.\n"
    )

    observed = _observe(
        tmp_path,
        base={"mod.py": MOD_BASE, "tests/test_mod.py": MOD_TESTS, "CHANGES.rst": news_base},
        head={"mod.py": MOD_HEAD, "tests/test_mod.py": MOD_TESTS, "CHANGES.rst": news_head},
        test=MOD_REPRO,
        path="mod.py",
        changed=(3,),
        changed_files=("mod.py", "CHANGES.rst"),
    )

    assert observed.intent_evidence == (("slug", "CHANGES.rst"),)
    assert intent_verdict(observed) is not None


def test_a_test_the_same_diff_updates_is_intent(tmp_path: Path) -> None:
    """The author changed the behaviour and moved their own test with it."""
    moved = (
        "import mod\n"
        "\n"
        "\n"
        "def test_slug():\n"
        '    assert mod.slug("Hello World") == "Hello-World"\n'
    )

    observed = _observe(
        tmp_path,
        base={"mod.py": MOD_BASE, "tests/test_mod.py": MOD_TESTS, "docs/api.md": "# API\n"},
        head={"mod.py": MOD_HEAD, "tests/test_mod.py": moved, "docs/api.md": "# API\n"},
        test=MOD_REPRO,
        path="mod.py",
        changed=(3,),
        changed_files=("mod.py", "tests/test_mod.py"),
    )

    assert ("slug", "tests/test_mod.py") in observed.intent_evidence
    assert intent_verdict(observed) is not None


def test_an_unrelated_comment_change_elsewhere_is_not_intent(tmp_path: Path) -> None:
    """The false-positive control for (c): a comment change in another file that
    never names the anchored symbol leaves the receipt publishing."""
    other_base = "# helper\ndef helper():\n    return 1\n"
    other_head = "# helper, rewritten for clarity\ndef helper():\n    return 1\n"

    observed = _observe(
        tmp_path,
        base={"mod.py": MOD_BASE, "tests/test_mod.py": MOD_TESTS, "other.py": other_base},
        head={"mod.py": MOD_HEAD, "tests/test_mod.py": MOD_TESTS, "other.py": other_head},
        test=MOD_REPRO,
        path="mod.py",
        changed=(3,),
        changed_files=("mod.py", "other.py"),
    )

    assert observed.intent_evidence == ()
    assert intent_verdict(observed) is None


def test_a_deleted_symbol_is_still_anchored_and_still_readable(tmp_path: Path) -> None:
    """The shadow finding's shape: the change *removes* the function, so head has
    no node to intersect. The symbol comes from the base revision, and a docs
    line naming it is still intent."""
    base = "def reading():\n    return 3\n\n\ndef other():\n    return 4\n"
    head = "def other():\n    return 4\n"
    docs_base = "# API\n\n`reading` returns the reading.\n"
    docs_head = "# API\n\nRemoved: `reading`.\n"

    observed = _observe(
        tmp_path,
        base={"mod.py": base, "docs/api.md": docs_base},
        head={"mod.py": head, "docs/api.md": docs_head},
        test=MOD_REPRO,
        path="mod.py",
        changed=(1, 2),
        changed_files=("mod.py", "docs/api.md"),
    )

    assert "reading" in observed.anchored_symbols
    assert ("reading", "docs/api.md") in observed.intent_evidence

# --- the two live wrong publications, each drawered by (c) on its own ----------

# `G-NULL-001a` control `urllib3 c7b9adcb` ("Fix TestBrokenPipe on macOS"), the
# three lines of `src/urllib3/connectionpool.py` it changes, verbatim.
URLLIB3_BASE = (
    "class HTTPConnectionPool:\n"
    "    def _make_request(self, conn, method, url):\n"
    "        try:\n"
    "            conn.request(method, url)\n"
    "        except BrokenPipeError:\n"
    "            pass\n"
    "        except OSError as e:\n"
    "            # MacOS/Linux\n"
    "            # EPROTOTYPE is needed on macOS\n"
    "            # https://erickt.github.io/blog/2014/11/19/adventures-in-debugging\n"
    "            if e.errno != errno.EPROTOTYPE:\n"
    "                raise\n"
    "        return conn.getresponse()\n"
)
URLLIB3_HEAD = (
    "class HTTPConnectionPool:\n"
    "    def _make_request(self, conn, method, url):\n"
    "        try:\n"
    "            conn.request(method, url)\n"
    "        except BrokenPipeError:\n"
    "            pass\n"
    "        except OSError as e:\n"
    "            # MacOS/Linux\n"
    "            # EPROTOTYPE and ECONNRESET are needed on macOS\n"
    "            # https://erickt.github.io/blog/2014/11/19/adventures-in-debugging\n"
    "            # Condition changed later to emit ECONNRESET instead of only EPROTOTYPE.\n"
    "            if e.errno != errno.EPROTOTYPE and e.errno != errno.ECONNRESET:\n"
    "                raise\n"
    "        return conn.getresponse()\n"
)
# the published reproduction's two assertions, and the stub that actually raised
URLLIB3_REPRO = (
    "import errno\n"
    "\n"
    "import mod\n"
    "\n"
    "\n"
    "def test_econnreset_during_request_not_swallowed_off_macos():\n"
    "    class ResetOnRequestConnection:\n"
    "        def getresponse(self):\n"
    "            raise AssertionError('getresponse() must not be reached')\n"
    "\n"
    "    conn = ResetOnRequestConnection()\n"
    "    pool = mod.HTTPConnectionPool()\n"
    "    with pytest.raises(OSError) as excinfo:\n"
    "        pool._make_request(conn, 'GET', '/')\n"
    "    assert excinfo.value.errno == errno.ECONNRESET\n"
    "    assert conn.getresponse_called is False\n"
)
# the real longrepr's two frames: the call that failed, then the stub that raised
URLLIB3_LONGREPR = (
    "        with pytest.raises(OSError) as excinfo:\n"
    ">           pool._make_request(conn, 'GET', '/')\n"
    "\n"
    ".attest-repro/test_repro.py:14: \n"
    "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _\n"
    "src/urllib3/connectionpool.py:537: in _make_request\n"
    "    response = conn.getresponse()\n"
    "_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _\n"
    "        def getresponse(self):\n"
    ">           raise AssertionError('getresponse() must not be reached')\n"
    "E           AssertionError: getresponse() must not be reached\n"
    "\n"
    ".attest-repro/test_repro.py:9: AssertionError"
)


def test_the_urllib3_control_is_drawered_by_the_comment_it_updated(
    tmp_path: Path,
) -> None:
    """`G-NULL-001a` control `urllib3 c7b9adcb`, the second wrong publication this
    product made (D-131). All three clauses catch it, and (c) catches it alone:
    the diff rewrites the comment sitting above the very condition it widens."""
    anchored = "src/urllib3/connectionpool.py"
    # a base tree that asserts `is False` somewhere, which is what carried the
    # publication under v3
    tests = "def test_pool():\n    assert pool.closed is False\n"

    observed = _observe(
        tmp_path,
        base={anchored: URLLIB3_BASE, "test/test_pool.py": tests},
        head={anchored: URLLIB3_HEAD, "test/test_pool.py": tests},
        test=URLLIB3_REPRO,
        path=anchored,
        changed=(9, 11, 12),
        longrepr=URLLIB3_LONGREPR,
        message="AssertionError: getresponse() must not be reached",
    )

    # (a): the innermost frame is the stub's `raise`, not the `is False` assertion
    assert observed.failing_assertion_line == 9
    assert observed.pinned_values == ()
    # (c), on its own: the comment above the widened condition, inside the method
    assert observed.anchored_symbols == ("HTTPConnectionPool", "_make_request")
    assert observed.intent_evidence == (("_make_request", anchored),)
    verdict = intent_verdict(observed)
    assert verdict is not None and verdict.startswith(INTENT_STATED_LABEL)
    assert evidence_class_for(observed) == EVIDENCE_CLASS_BEHAVIOR_CHANGE


def test_clause_c_stands_alone_when_a_and_b_are_satisfied() -> None:
    """(c) is not decoration on the other two: an observation whose failing
    assertion pins a distinctive value the base tree specifies and head still
    specifies is *still* drawered when the diff states its intent."""
    publishing = IntentObservation(
        policy_version=INTENT_POLICY_VERSION,
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
        failing_assertion_line=6,
        anchored_symbols=("slug",),
    )
    assert intent_verdict(publishing) is None

    stated = replace(publishing, intent_evidence=(("slug", "CHANGES.rst"),))
    verdict = intent_verdict(stated)
    assert verdict is not None and verdict.startswith(INTENT_STATED_LABEL)
    assert evidence_class_for(stated) == EVIDENCE_CLASS_BEHAVIOR_CHANGE


def test_a_v3_receipt_is_still_judged_by_v3(tmp_path: Path) -> None:
    """D-121: bumping the version does not re-judge a receipt already issued.
    The urllib3 observation, stamped v3, keeps v3's fields and v3's answer --
    which is what makes the corpus replay a comparison rather than a rewrite."""
    under_v4 = IntentObservation(
        policy_version=INTENT_POLICY_VERSION,
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
        pinned_values=("False",),
        value_specified=(("False", "test/test_pool.py"),),
        intent_evidence=(("_make_request", "src/urllib3/connectionpool.py"),),
    )
    under_v3 = replace(under_v4, policy_version=INTENT_POLICY_V3)

    # v3 published it: a generic constant satisfied its rule and it had no (c)
    assert intent_verdict(under_v3) is None
    assert distinctive_pinned_values(under_v3) == ("False",)
    # v4 does not
    assert intent_verdict(under_v4) is not None
    assert distinctive_pinned_values(under_v4) == ()
    # and the two digests are over different field sets, so neither moved
    assert under_v3.digest() != under_v4.digest()

