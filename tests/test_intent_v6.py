"""D-252: `attest.intent.v6` (experimental, never the default) -- a specification
may be a *contract*, admitted only when it binds the probe's concrete input, a
value the observer derives mechanically, and a call path that resolves to the
anchored module. Every contract found is recorded with the binding it lacks.

The positive cases are the three shapes the evidence-supply audit found unread
(object-valued expected sides, parametrize rows, an exception expected through a
caller), and one generic constant a bound assertion covers. The counterexamples
are the mis-associations the rule must refuse: a different input, an expected
side nobody can derive, a same-named symbol of another module, and a caller
contract the probe did not enter through.
"""

from __future__ import annotations

from pathlib import Path

from attest.certification.intent import (
    INTENT_POLICY_V6,
    INTENT_POLICY_VERSION,
    POLICY_FIELDS,
    IntentObservation,
    admitted_contract_values,
    intent_verdict,
)
from attest.review.intent import observe_intent

GEO_BASE = '''from typing import NamedTuple


class Point(NamedTuple):
    x: int
    y: int


def parse(text):
    if not text:
        raise ValueError("empty")
    a, b = text.split(",")
    return Point(int(a), int(b))


def public(text):
    return parse(text)


def count(text):
    return len(text.split(","))
'''
# head: parse returns y + 1, the empty guard is gone, count is off by one
GEO_HEAD = GEO_BASE.replace(
    '    if not text:\n        raise ValueError("empty")\n', ""
).replace("return Point(int(a), int(b))", "return Point(int(a), int(b) + 1)").replace(
    'return len(text.split(","))', 'return len(text.split(",")) + 1'
)
# head-side lines of the change, per touched definition (the guard of `parse`
# is deleted, so head's `parse` spans 9-11; `count` sits at 18-19 on head)
PARSE_LINES = (9, 10, 11)
COUNT_LINES = (18, 19)

TESTS_ROWS = '''import pytest

from pkg.geo import Point, parse


@pytest.mark.parametrize("text, expected", [("1,2", Point(1, 2)), ("3,4", Point(3, 4))])
def test_parse(text, expected):
    assert parse(text) == expected
'''
TESTS_ASSERT = '''from pkg.geo import Point, parse


def test_parse():
    assert parse("1,2") == Point(1, 2)
'''
TESTS_UNDERIVABLE = '''from pkg.geo import Point, parse


def test_parse():
    assert parse("1,2") == Point.from_text("1,2")
'''
TESTS_OTHER_MODULE = '''from other.geo import Point, parse


def test_parse():
    assert parse("1,2") == Point(1, 2)
'''
TESTS_CALLER = '''import pytest

from pkg.geo import public


def test_public_rejects_empty():
    with pytest.raises(ValueError):
        public("")
'''
TESTS_COUNT = '''from pkg.geo import count


def test_count():
    assert count("a") == 1
'''


def _replay(imports: str, expression: str, pinned_repr: str) -> tuple[str, str]:
    """A replay test in the shape `replay_test_body` writes, and pytest's
    longrepr for its failing assertion."""
    source = (
        "import re\n"
        f"{imports}\n\n\n"
        "def test_attest_replay():\n"
        f"    _attest_value = {expression}\n"
        "    # recorded\n"
        f"    assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == {pinned_repr!r}\n"
    )
    longrepr = (
        "    def test_attest_replay():\n"
        f">       assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == {pinned_repr!r}\n"
        "E       AssertionError\n\n"
        ".attest-repro/test_repro.py:8: AssertionError"
    )
    return source, longrepr


def _replay_raises(imports: str, expression: str, exception: str) -> tuple[str, str]:
    source = (
        "import re\n"
        f"{imports}\n\n\n"
        "def test_attest_replay():\n"
        "    try:\n"
        f"        _attest_value = {expression}\n"
        "    except BaseException as _attest_error:  # noqa: BLE001\n"
        "        _attest_raised = type(_attest_error).__name__\n"
        "    else:\n"
        "        _attest_raised = None\n"
        "    # recorded\n"
        f"    assert _attest_raised == {exception!r}\n"
    )
    longrepr = (
        "    def test_attest_replay():\n"
        f">       assert _attest_raised == {exception!r}\n"
        "E       AssertionError\n\n"
        ".attest-repro/test_repro.py:13: AssertionError"
    )
    return source, longrepr


def _tree(root: Path, files: dict[str, str]) -> Path:
    for relative, body in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return root


def _observe(
    tmp_path: Path, *, tests: str, test: str, longrepr: str, policy: str,
    changed: tuple[int, ...] = PARSE_LINES,
) -> IntentObservation:
    base = _tree(tmp_path / "base", {"pkg/__init__.py": "", "pkg/geo.py": GEO_BASE,
                                     "tests/test_geo.py": tests})
    head = _tree(tmp_path / "head", {"pkg/__init__.py": "", "pkg/geo.py": GEO_HEAD,
                                     "tests/test_geo.py": tests})
    observed = observe_intent(
        path="pkg/geo.py",
        changed_lines=changed,
        head_source=GEO_HEAD,
        base_source=GEO_BASE,
        test_source=test,
        head_origins=[() for _ in range(3)],
        head_failures=["AssertionError"] * 3,
        head_failure_details=[longrepr] * 3,
        base_tree=base,
        head_tree=head,
        changed_files=("pkg/geo.py",),
        policy_version=policy,
    )
    assert isinstance(observed, IntentObservation), observed
    return observed


# --- the positive cases ---------------------------------------------------------


def test_a_parametrize_row_with_the_probes_input_specifies_the_object(tmp_path: Path) -> None:
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    shipped = _observe(tmp_path / "a", tests=TESTS_ROWS, test=test, longrepr=longrepr,
                       policy=INTENT_POLICY_VERSION)
    assert shipped.contracts == ()
    assert intent_verdict(shipped) is not None  # the drawer, as today

    observed = _observe(tmp_path / "b", tests=TESTS_ROWS, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    admitted = [c for c in observed.contracts if c.admitted]
    assert len(admitted) == 1
    contract = admitted[0]
    assert contract.kind == "parametrize_row"
    assert contract.input == "'1,2'"
    assert contract.derived == "Point(x=1, y=2)"
    assert contract.pinned == "'Point(x=1, y=2)'"
    assert contract.source == "tests/test_geo.py:8"
    assert (contract.input_bound, contract.evaluated, contract.path_bound) == (True, True, True)
    assert ("'Point(x=1, y=2)'", "tests/test_geo.py") in observed.value_specified
    assert intent_verdict(observed) is None
    # the other row is recorded too, refused for its input
    other = [c for c in observed.contracts if not c.admitted]
    assert other and all(not c.input_bound for c in other)
    assert "is not the probe's" in other[0].reason


def test_a_bound_assertion_with_an_object_expected_side_specifies_it(tmp_path: Path) -> None:
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    observed = _observe(tmp_path, tests=TESTS_ASSERT, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    assert [c.kind for c in observed.contracts if c.admitted] == ["bound_assertion"]
    assert intent_verdict(observed) is None


def test_an_exception_expected_through_the_caller_the_probe_entered_specifies_it(
    tmp_path: Path,
) -> None:
    test, longrepr = _replay_raises("from pkg.geo import public", 'public("")', "ValueError")
    observed = _observe(tmp_path, tests=TESTS_CALLER, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    admitted = [c for c in observed.contracts if c.admitted]
    assert len(admitted) == 1
    assert admitted[0].kind == "caller_raises"
    assert admitted[0].call_path.startswith("parse <- public (pkg/geo.py:")
    assert admitted[0].pinned == "'ValueError'"
    assert intent_verdict(observed) is None


def test_a_generic_constant_a_bound_assertion_covers_is_a_specification(tmp_path: Path) -> None:
    test, longrepr = _replay("from pkg.geo import count", 'count("a")', "1")
    # the replay pins the literal itself, not its repr as a string
    test = test.replace("assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == '1'",
                        "assert _attest_value == 1")
    longrepr = longrepr.replace(
        "assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == '1'",
        "assert _attest_value == 1",
    )
    shipped = _observe(tmp_path / "a", tests=TESTS_COUNT, test=test, longrepr=longrepr,
                       policy=INTENT_POLICY_VERSION, changed=COUNT_LINES)
    verdict = intent_verdict(shipped)
    assert verdict is not None and "generic constant" in verdict
    observed = _observe(tmp_path / "b", tests=TESTS_COUNT, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6, changed=COUNT_LINES)
    assert admitted_contract_values(observed) == frozenset({"1"})
    assert intent_verdict(observed) is None


# --- the counterexamples: what must not associate ---------------------------------


def test_a_row_with_another_input_does_not_specify_even_the_same_object(tmp_path: Path) -> None:
    rows = TESTS_ROWS.replace('("1,2", Point(1, 2)), ("3,4", Point(3, 4))',
                              '("01,02", Point(1, 2)), ("3,4", Point(3, 4))')
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    observed = _observe(tmp_path, tests=rows, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    assert observed.contracts and not any(c.admitted for c in observed.contracts)
    row = next(c for c in observed.contracts if c.derived == "Point(x=1, y=2)")
    assert not row.input_bound and row.evaluated and row.path_bound
    assert "('01,02') is not the probe's ('1,2')" in row.reason
    verdict = intent_verdict(observed)
    assert verdict is not None and "does not specify" in verdict


def test_an_expected_side_nobody_can_derive_does_not_specify(tmp_path: Path) -> None:
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    observed = _observe(tmp_path, tests=TESTS_UNDERIVABLE, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    assert len(observed.contracts) == 1
    contract = observed.contracts[0]
    assert contract.input_bound and contract.path_bound and not contract.evaluated
    assert not contract.admitted and "not a value this reader can derive" in contract.reason
    assert intent_verdict(observed) is not None


def test_a_same_named_symbol_of_another_module_is_no_contract(tmp_path: Path) -> None:
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    observed = _observe(tmp_path, tests=TESTS_OTHER_MODULE, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    assert observed.contracts == ()
    assert intent_verdict(observed) is not None


def test_a_caller_contract_the_probe_did_not_enter_through_is_recorded_and_refused(
    tmp_path: Path,
) -> None:
    """The base test expects the exception from `public`; the probe called
    `parse` directly. The contract exists, names the path, and does not admit."""
    test, longrepr = _replay_raises("from pkg.geo import parse", 'parse("")', "ValueError")
    observed = _observe(tmp_path, tests=TESTS_CALLER, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    assert len(observed.contracts) == 1
    contract = observed.contracts[0]
    assert contract.kind == "caller_raises" and not contract.path_bound
    assert not contract.admitted
    assert "the probe entered through parse, the source calls public" in contract.reason
    verdict = intent_verdict(observed)
    assert verdict is not None and "does not specify" in verdict


# --- the record, the digest, and the default ------------------------------------------


def test_v6_records_its_contracts_and_v51_never_carries_the_field(tmp_path: Path) -> None:
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    observed = _observe(tmp_path, tests=TESTS_ROWS, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    record = observed.record()
    assert set(record) == set(POLICY_FIELDS[INTENT_POLICY_V6])
    assert record["contracts"] and isinstance(record["contracts"][0], dict)
    rebuilt = IntentObservation(**record)
    assert rebuilt.contracts == observed.contracts
    assert rebuilt.digest() == observed.digest()
    shipped = _observe(tmp_path / "s", tests=TESTS_ROWS, test=test, longrepr=longrepr,
                       policy=INTENT_POLICY_VERSION)
    assert "contracts" not in shipped.record()
    assert set(shipped.record()) == set(POLICY_FIELDS[INTENT_POLICY_VERSION])


def test_the_default_is_still_v51_and_records_no_contract(tmp_path: Path) -> None:
    assert INTENT_POLICY_VERSION == "attest.intent.v5.1"
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    base = _tree(tmp_path / "base", {"pkg/__init__.py": "", "pkg/geo.py": GEO_BASE,
                                     "tests/test_geo.py": TESTS_ROWS})
    observed = observe_intent(
        path="pkg/geo.py", changed_lines=PARSE_LINES, head_source=GEO_HEAD, base_source=GEO_BASE,
        test_source=test, head_origins=[(), (), ()], head_failures=["AssertionError"] * 3,
        head_failure_details=[longrepr] * 3, base_tree=base, head_tree=None,
    )
    assert isinstance(observed, IntentObservation)
    assert observed.policy_version == INTENT_POLICY_VERSION
    assert observed.contracts == ()


def test_a_name_assigned_from_itself_does_not_send_the_reader_in_circles(tmp_path: Path) -> None:
    """`s = s.get()` names itself; the reader follows a name through the test's
    assignments once and stops -- boltons' statistics tests did this and the
    first draft never came back."""
    tests = '''from pkg.geo import parse


def test_parse():
    s = parse("1,2")
    s = s.next()
    assert s.count() == 2
'''
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    observed = _observe(tmp_path, tests=tests, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    assert observed.contracts == ()


# --- D-253: a contract stands at head, or it is not admitted ------------------------


def test_a_change_that_removes_the_contract_at_head_is_not_specified_by_it(
    tmp_path: Path,
) -> None:
    """The caller contract of `public` is admitted while the test that states it
    stands. A head that removes that test -- which names `public`, not the touched
    `parse`, so D-132 (c) reads no intent in it -- has said what it meant: the
    contract is recorded as not standing and specifies nothing."""
    test, longrepr = _replay_raises("from pkg.geo import public", 'public("")', "ValueError")
    base = _tree(tmp_path / "base", {"pkg/__init__.py": "", "pkg/geo.py": GEO_BASE,
                                     "tests/test_geo.py": TESTS_CALLER})
    head = _tree(tmp_path / "head", {"pkg/__init__.py": "", "pkg/geo.py": GEO_HEAD,
                                     "tests/test_geo.py": "import pytest\n"})
    observed = observe_intent(
        path="pkg/geo.py", changed_lines=PARSE_LINES, head_source=GEO_HEAD,
        base_source=GEO_BASE, test_source=test, head_origins=[(), (), ()],
        head_failures=["AssertionError"] * 3, head_failure_details=[longrepr] * 3,
        base_tree=base, head_tree=head, changed_files=("pkg/geo.py", "tests/test_geo.py"),
        policy_version=INTENT_POLICY_V6,
    )
    assert isinstance(observed, IntentObservation)
    assert observed.intent_evidence == ()  # the removed test never names `parse`
    assert len(observed.contracts) == 1
    contract = observed.contracts[0]
    assert contract.input_bound and contract.evaluated and contract.path_bound
    assert not contract.standing_at_head and not contract.admitted
    assert "removes or rewrites this contract at head" in contract.reason
    verdict = intent_verdict(observed)
    assert verdict is not None and "does not specify" in verdict


def test_an_admitted_contract_records_that_it_stands_at_head(tmp_path: Path) -> None:
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    observed = _observe(tmp_path, tests=TESTS_ROWS, test=test, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    admitted = [c for c in observed.contracts if c.admitted]
    assert admitted and all(c.standing_at_head for c in admitted)


def test_without_a_head_tree_no_contract_is_admitted(tmp_path: Path) -> None:
    test, longrepr = _replay("from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)")
    base = _tree(tmp_path / "base", {"pkg/__init__.py": "", "pkg/geo.py": GEO_BASE,
                                     "tests/test_geo.py": TESTS_ROWS})
    observed = observe_intent(
        path="pkg/geo.py", changed_lines=PARSE_LINES, head_source=GEO_HEAD,
        base_source=GEO_BASE, test_source=test, head_origins=[(), (), ()],
        head_failures=["AssertionError"] * 3, head_failure_details=[longrepr] * 3,
        base_tree=base, head_tree=None, policy_version=INTENT_POLICY_V6,
    )
    assert isinstance(observed, IntentObservation)
    assert observed.contracts and not any(c.admitted for c in observed.contracts)
    assert intent_verdict(observed) is not None


# --- D-253: a constructed argument, a receiver, and a name chain are inputs too -------

GRID = '''

class Grid:
    def __init__(self, width=1):
        self.width = width

    def cell(self, point):
        return point.x * self.width + point.y
'''
GRID_HEAD = GRID.replace("return point.x * self.width + point.y",
                         "return point.x * self.width + point.y + 1")
GRID_BASE_FILE = GEO_BASE + GRID
GRID_HEAD_FILE = GEO_HEAD + GRID_HEAD
# the `cell` body on head, after GEO_HEAD's own lines
CELL_LINES = tuple(range(GEO_HEAD.count("\n") + 7, GEO_HEAD.count("\n") + 10))


def _observe_grid(tmp_path: Path, *, tests: str, setup: str, expression: str,
                  pinned: str) -> IntentObservation:
    source = (
        "from pkg.geo import Grid, Point\n\n\n"
        "def test_attest_replay():\n"
        f"    {setup}\n"
        f"    _attest_value = {expression}\n"
        "    # recorded\n"
        f"    assert _attest_value == {pinned}\n"
    )
    longrepr = (f"    def test_attest_replay():\n>       assert _attest_value == {pinned}\n"
                "E       AssertionError\n\n.attest-repro/test_repro.py:8: AssertionError")
    files = {"pkg/__init__.py": "", "tests/test_geo.py": tests}
    base = _tree(tmp_path / "base", {**files, "pkg/geo.py": GRID_BASE_FILE})
    head = _tree(tmp_path / "head", {**files, "pkg/geo.py": GRID_HEAD_FILE})
    observed = observe_intent(
        path="pkg/geo.py", changed_lines=CELL_LINES, head_source=GRID_HEAD_FILE,
        base_source=GRID_BASE_FILE, test_source=source, head_origins=[(), (), ()],
        head_failures=["AssertionError"] * 3, head_failure_details=[longrepr] * 3,
        base_tree=base, head_tree=head, changed_files=("pkg/geo.py",),
        policy_version=INTENT_POLICY_V6,
    )
    assert isinstance(observed, IntentObservation), observed
    return observed


def test_a_constructed_argument_and_receiver_bind_when_both_sides_build_them_alike(
    tmp_path: Path,
) -> None:
    tests = ("from pkg.geo import Grid, Point\n\n\ndef test_cell():\n"
             "    g = Grid(width=2)\n    assert g.cell(Point(1, 2)) == 4\n")
    observed = _observe_grid(tmp_path, tests=tests, setup="g = Grid(width=2)",
                             expression="g.cell(Point(1, 2))", pinned="4")
    admitted = [c for c in observed.contracts if c.admitted]
    assert len(admitted) == 1
    assert admitted[0].input == "pkg.geo.Grid(width=2) :: pkg.geo.Point(1, 2)"


def test_the_same_argument_and_value_on_a_receiver_built_otherwise_is_another_input(
    tmp_path: Path,
) -> None:
    """`Grid(width=5).cell(Point(0, 3))` and `Grid(width=2).cell(Point(0, 3))` both
    return 3: the value and the argument agree and the contract is still about
    another object. D-252 compared the arguments alone and would have admitted it."""
    tests = ("from pkg.geo import Grid, Point\n\n\ndef test_cell():\n"
             "    g = Grid(width=5)\n    assert g.cell(Point(0, 3)) == 3\n")
    observed = _observe_grid(tmp_path, tests=tests, setup="g = Grid(width=2)",
                             expression="g.cell(Point(0, 3))", pinned="3")
    assert len(observed.contracts) == 1
    contract = observed.contracts[0]
    assert contract.evaluated and contract.path_bound and not contract.input_bound
    assert not contract.admitted
    assert "pkg.geo.Grid(width=5)" in contract.reason
    assert "pkg.geo.Grid(width=2)" in contract.reason


def test_a_name_chain_binds_on_the_probe_side_as_on_the_source_side(tmp_path: Path) -> None:
    rows = TESTS_ROWS.replace('("1,2", Point(1, 2))', '(ONE_TWO, Point(1, 2))').replace(
        "from pkg.geo import Point, parse\n",
        'from pkg.geo import Point, parse\n\nONE_TWO = "1,2"\n',
    )
    source = (
        "import re\nfrom pkg.geo import parse\n\n\n"
        "def test_attest_replay():\n"
        "    ONE_TWO = '1,2'\n"
        "    text = ONE_TWO\n"
        "    _attest_value = parse(text)\n"
        "    # recorded\n"
        "    assert re.sub(' at 0x[0-9a-f]+', '', repr(_attest_value)) == 'Point(x=1, y=2)'\n"
    )
    longrepr = (">       assert ...\nE       AssertionError\n\n"
                ".attest-repro/test_repro.py:10: AssertionError")
    observed = _observe(tmp_path, tests=rows, test=source, longrepr=longrepr,
                        policy=INTENT_POLICY_V6)
    assert [c.input for c in observed.contracts if c.admitted] == ["'1,2'"]
