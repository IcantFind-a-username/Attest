"""D-255: a contract binds its input at the assertion's program point, or it is not a contract.

Three shapes the D-254 reader bound wrongly, each traced to the intent verdict and to the kernel
(`scripts/corpus/binding_cases.py` builds and runs them): a name reassigned after the assertion,
a receiver whose state is changed after its construction, and an assertion no test run reaches.
Before D-255 the reader admitted the contract in all three and the kernel accepted a receipt.

Then the kernel's own half: the `admitted` flag an observer writes is not evidence -- the rule
recomputes admission from the binding fields and refuses a record whose flag disagrees -- and the
offline verifier re-judges the recorded observation without rebuilding it from contract source.

Finally the selection diagnostic, pinned as it is and not changed: a first contract probe whose
differential cannot certify is chosen, and the model probe that would have certified is never asked.
"""

from __future__ import annotations

import ast
import sys
import textwrap
from dataclasses import replace
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "corpus"))

from binding_cases import trace  # noqa: E402

import attest.certification.intent as intent_rules  # noqa: E402
from attest.certification.intent import (  # noqa: E402
    INTENT_POLICY_V6,
    ContractRecord,
    IntentObservation,
    intent_verdict,
)

# the policy these rules live under; before D-255 only v6 existed, and the REDs ran against it
POLICY = getattr(intent_rules, "INTENT_POLICY_V61", INTENT_POLICY_V6)


# --- the three shapes ------------------------------------------------------------------


def test_a_name_reassigned_after_the_assertion_is_bound_at_the_assertion(tmp_path: Path) -> None:
    """`text = "1,2"; assert norm(text) == Point(1, 2); text = "9,9"`. The model probe calls
    `norm("9,9")`, which the base happens to answer `Point(1, 2)` too. The contract is about
    "1,2": bound at the assertion, its input is not the probe's."""
    result = trace("reassigned_after_assert", policy=POLICY, contract_probes=True, root=tmp_path)

    assert result["probe"]["source"] == "model"
    assert result["reader_admitted"] is False
    contract = next(c for c in result["reader"] if c["source"].endswith(":6"))
    assert contract["input"] == "'1,2'" and contract["input_bound"] is False
    assert result["certification"] != "accepted"


def test_a_receiver_changed_after_its_construction_binds_no_contract(tmp_path: Path) -> None:
    """`g = Grid(width=2); g.cache = {}; assert g.cell(...) == Point(2, 2)`. The contract is about a
    grid whose cache was set; neither the search nor the reader may read it as one about any
    `Grid(width=2)`."""
    result = trace("receiver_mutated", policy=POLICY, contract_probes=True, root=tmp_path)

    refused = dict(result["contract_search"]["refused"])
    assert any("line 6" in reason for reason in refused.values()), refused
    assert result["probe"]["source"] == "model"
    assert result["reader_admitted"] is False
    contract = next(c for c in result["reader"] if c["source"].endswith(":7"))
    assert contract["flow_bound"] is False and "line 6" in contract["flow_reason"]
    assert result["certification"] != "accepted"


def test_an_assertion_after_a_return_is_no_contract(tmp_path: Path) -> None:
    result = trace("unreachable_assert", policy=POLICY, contract_probes=True, root=tmp_path)

    refused = dict(result["contract_search"]["refused"])
    assert any("line 5" in reason for reason in refused.values()), refused
    assert result["probe"]["source"] == "model"
    assert result["reader_admitted"] is False
    contract = next(c for c in result["reader"] if c["source"].endswith(":6"))
    assert contract["flow_bound"] is False
    assert result["certification"] != "accepted"


# --- the kernel does not take the observer's word ----------------------------------------------


def _admitted_observation(**contract_changes: object) -> IntentObservation:
    contract = ContractRecord(
        kind="bound_assertion", symbol="parse", input="'1,2'", expected="Point(1, 2)",
        derived="Point(x=1, y=2)", pinned="'Point(x=1, y=2)'", source="tests/test_geo.py:6",
        call_path="parse <- tests/test_geo.py::test_parse", input_bound=True, evaluated=True,
        path_bound=True, admitted=True, reason="admitted", standing_at_head=True,
    )
    if hasattr(contract, "flow_bound"):
        contract = replace(contract, flow_bound=True)
    contract = replace(contract, **contract_changes)  # type: ignore[arg-type]
    return IntentObservation(
        policy_version=POLICY, path="geo.py", changed_lines=(11,), origin_line=0,
        origin_statement="", exception_type="", new_rejection=False, rejected_inputs=(),
        witnesses=(), head_runs_observed=3, value_mismatch=True,
        pinned_values=("'Point(x=1, y=2)'",), failing_assertion_line=8,
        anchored_symbols=("parse",), added_lines=(11,), contracts=(contract,),
    )


def test_an_admitted_flag_without_its_bindings_is_refused_not_believed() -> None:
    consistent = _admitted_observation()
    assert intent_verdict(consistent) is None

    for field in ("input_bound", "evaluated", "path_bound", "standing_at_head", "flow_bound"):
        forged = _admitted_observation(**{field: False})
        verdict = intent_verdict(forged)
        assert verdict is not None and "inconsistent" in verdict, (field, verdict)
    unclaimed = _admitted_observation(admitted=False)
    verdict = intent_verdict(unclaimed)
    assert verdict is not None and "inconsistent" in verdict


def test_a_contract_pinned_value_the_assertion_does_not_pin_is_refused() -> None:
    forged = _admitted_observation(pinned="'Point(x=9, y=9)'")
    verdict = intent_verdict(forged)
    assert verdict is not None


def test_the_verifier_rejudges_the_record_and_does_not_rebuild_it_from_source() -> None:
    """What offline verification can and cannot say: it recomputes the verdict from the recorded
    observation -- so a forged flag fails -- but the bundle carries no contract source, so a
    consistent record whose bindings were wrongly computed verifies. Stated, not hidden."""
    from attest.certification.intent import EVIDENCE_CLASS_REGRESSION
    from attest.review.evidence import intent_reasons

    def reasons(observation: IntentObservation) -> tuple[str, ...]:
        record = observation.record()
        return intent_reasons(
            {k: (list(v) if isinstance(v, tuple) else v) for k, v in record.items()},
            receipt_policy_version=observation.policy_version,
            receipt_intent_digest=observation.digest(),
            receipt_evidence_class=EVIDENCE_CLASS_REGRESSION,
        )

    assert reasons(_admitted_observation()) == ()
    assert any("inconsistent" in r for r in reasons(_admitted_observation(input_bound=False)))
    # a record that is consistent with itself and says nothing about the source it came from
    assert reasons(_admitted_observation(input="'anything'")) == ()


# --- the selection diagnostic, pinned as it behaves -------------------------------------------


@pytest.mark.parametrize("contracts_on", [True, False])
def test_a_first_contract_differential_that_cannot_certify_masks_the_model_probe(
    tmp_path: Path, contracts_on: bool
) -> None:
    """Not a fix: the strategy is "the first probe whose revisions differ decides". With the
    contract search on, `describe(1) == Label("1")` differs and cannot certify (a plain class is
    not derivable), and the model probe `describe(9)`, which certifies, is never asked."""
    result = trace("first_contract_masks_model", policy=POLICY, contract_probes=contracts_on,
                   root=tmp_path)
    if contracts_on:
        assert result["model_calls"] == 0
        assert result["probe"]["source"] == "contract"
        assert result["certification"] != "accepted"
    else:
        assert result["model_calls"] == 1
        assert result["certification"] == "accepted"


# --- the legal contract still certifies ---------------------------------------------------


def test_a_contract_bound_at_its_assertion_is_admitted_and_certifies(tmp_path: Path) -> None:
    """The assignment after the assertion is not the contract's input; the one before it is.
    A change that breaks that input is caught by the contract probe and certified, without a
    model call, and the kernel -- not the observer -- adds the value the contract covers."""
    result = trace("legal_contract", policy=POLICY, contract_probes=True, root=tmp_path)

    assert result["model_calls"] == 0 and result["probe"]["source"] == "contract"
    assert result["probe"]["setup"] == "text = '1,2'"
    assert result["reader_admitted"] is True
    assert result["verdict"] == "publishes"
    assert result["certification"] == "accepted"


# --- the shapes the rule reads, and the ones it refuses ---------------------------------------


def _flow(source: str, *, callee: str = "parse", container: str = "", nth: int = 0) -> str:
    from attest.review.contracts import _owners, flow_refusal, program_point

    module = ast.parse(textwrap.dedent(source))
    func = next(
        n for n in ast.walk(module)
        if isinstance(n, ast.FunctionDef) and n.name.startswith("test")
    )
    calls = [
        n for n in ast.walk(func)
        if isinstance(n, ast.Call) and ast.unparse(n.func).endswith(callee)
    ]
    call = sorted(calls, key=lambda n: (n.lineno, n.col_offset))[nth]
    point = program_point(func, call, container=container)
    return flow_refusal(point, func, call, owners=_owners(module).get(id(func), ()), module=module)


@pytest.mark.parametrize(
    ("source", "kwargs", "expected"),
    [
        pytest.param(
            """
            def test_x():
                text = "a"
                text = "1,2"
                assert parse(text) == 1
                text = "9,9"
                for text in ["x"]:
                    pass
            """, {}, "", id="read: an earlier assignment replaced, later ones ignored"),
        pytest.param(
            """
            TEXT = "1,2"
            def test_x():
                \"\"\"A docstring.\"\"\"
                other = [1, TEXT]
                assert other
                assert parse(TEXT) == 1
            """, {}, "", id="read: inert statements that call nothing and change nothing"),
        pytest.param(
            """
            TEXT = "1,2"
            def test_x():
                other = [1]
                other.append(len(TEXT))
                assert parse(TEXT) == 1
            """, {}, "line 5 calls other.append before the assertion at line 6",
            id="refused: any call before the assertion, however unrelated it looks"),
        pytest.param(
            """
            def test_x():
                with pytest.raises(E):
                    Url.from_dict({"url": 1})
            """, {"callee": "from_dict", "container": "raises"}, "",
            id="read: the first statement of an expected-exception block"),
        pytest.param(
            """
            def test_x():
                text = "1,2"
                if FLAG:
                    text = "9,9"
                assert parse(text) == 1
            """, {}, "line 5 touches 'text'", id="refused: a rebinding inside a branch"),
        pytest.param(
            """
            def test_x():
                if FLAG:
                    text = "1,2"
                assert parse(text) == 1
            """, {}, "is assigned in test_x at line 4, not by a plain assignment",
            id="refused: bound only inside a branch"),
        pytest.param(
            """
            def test_x():
                g = Grid(width=2)
                h = g
                h.cache = {}
                assert g.cell(1) == 1
            """, {"callee": "cell"}, "line 4 touches 'g'", id="refused: an alias"),
        pytest.param(
            """
            def test_x():
                g = Grid(width=2)
                prime(g)
                assert g.cell(1) == 1
            """, {"callee": "cell"}, "line 4 touches 'g'",
            id="refused: handed to a call that may change it"),
        pytest.param(
            """
            def test_x():
                p = PoolManager()
                assert p.absolute(Url("http://a")) is False
                assert p.absolute(Url("https://a")) is False
            """, {"callee": "absolute", "nth": 1}, "line 4 touches 'p'",
            id="refused: an earlier call on the same receiver"),
        pytest.param(
            """
            def test_x(monkeypatch):
                monkeypatch.setenv("A", "1")
                assert parse("1,2") == 1
            """, {}, "uses the fixture 'monkeypatch'", id="refused: a fixture used first"),
        pytest.param(
            """
            ROWS = ["1,2"]
            def test_x():
                ROWS.append("9,9")
                assert parse(ROWS) == 1
            """, {}, "line 4 touches the module-level 'ROWS', a value a statement can change",
            id="refused: a module-level value changed first"),
        pytest.param(
            """
            @pytest.mark.skip(reason="later")
            def test_x():
                assert parse("1,2") == 1
            """, {}, "marked pytest.mark.skip", id="refused: skipped"),
        pytest.param(
            """
            @mock.patch("geo.parse")
            def test_x(fake):
                assert parse("1,2") == 1
            """, {}, "marked mock.patch", id="refused: patched"),
        pytest.param(
            """
            pytestmark = [pytest.mark.xfail]
            def test_x():
                assert parse("1,2") == 1
            """, {}, "marked pytest.mark.xfail", id="refused: a module expected to fail"),
        pytest.param(
            """
            @pytest.mark.usefixtures("reset")
            class TestX:
                def test_x(self):
                    assert parse("1,2") == 1
            """, {}, "marked pytest.mark.usefixtures", id="refused: a class that uses fixtures"),
        pytest.param(
            """
            def test_x():
                yield
                assert parse("1,2") == 1
            """, {}, "is a generator", id="refused: a generator test"),
        pytest.param(
            """
            def test_x():
                if sys.platform == "win32":
                    pytest.skip("no")
                assert parse("1,2") == 1
            """, {}, "line 4 inside the if at line 3 may leave the test",
            id="refused: a conditional skip"),
        pytest.param(
            """
            def test_x():
                pytest.importorskip("yaml")
                assert parse("1,2") == 1
            """, {}, "line 3 calls pytest.importorskip", id="refused: a skip call"),
        pytest.param(
            """
            def test_x():
                for text in ["1,2"]:
                    assert parse(text) == 1
            """, {}, "sits inside the for at line 3", id="refused: an assertion in a loop"),
        pytest.param(
            """
            def test_x():
                with pytest.raises(E):
                    prepare()
                    Url.from_dict({"url": 1})
            """, {"callee": "from_dict", "container": "raises"}, "is not the first statement",
            id="refused: a caller call after another statement of the block"),
    ],
)
def test_the_program_point_rule(source: str, kwargs: dict[str, object], expected: str) -> None:
    reason = _flow(source, **kwargs)  # type: ignore[arg-type]
    if expected:
        assert expected in reason, reason
    else:
        assert reason == ""


def test_a_probe_whose_own_setup_changes_its_receiver_binds_no_input() -> None:
    from attest.review.contracts import probe_call

    plain = probe_call(
        "from geo import Grid, Point\n\n\ndef test_attest_replay():\n"
        "    g = Grid(width=2)\n    _attest_value = g.cell(Point(1, 2))\n", "geo"
    )
    changed = probe_call(
        "from geo import Grid, Point\n\n\ndef test_attest_replay():\n"
        "    g = Grid(width=2)\n    g.cache = {}\n    _attest_value = g.cell(Point(1, 2))\n",
        "geo",
    )
    assert plain is not None and changed is not None
    assert plain.flow == "" and "line 6 touches 'g'" in changed.flow
    assert plain.same_input(plain) and not changed.same_input(plain)


# --- every earlier v6 case, under v6.1 -------------------------------------------------------

import test_intent_v6 as v6_cases  # noqa: E402

_V6_ONLY = {
    # record shape and the default: v6's own, asserted where they are defined
    "test_v6_records_its_contracts_and_v51_never_carries_the_field",
    "test_the_default_is_still_v51_and_records_no_contract",
    # asserts the observer merged the contract site into `value_specified`, which v6.1 does
    # not do; its v6.1 counterpart is the next test
    "test_a_parametrize_row_with_the_probes_input_specifies_the_object",
}


@pytest.mark.parametrize(
    "name", sorted(n for n in dir(v6_cases) if n.startswith("test_") and n not in _V6_ONLY)
)
def test_every_v6_contract_case_holds_under_v61(
    name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(v6_cases, "INTENT_POLICY_V6", intent_rules.INTENT_POLICY_V61)
    getattr(v6_cases, name)(tmp_path)


def test_under_v61_the_kernel_not_the_observer_adds_the_contract_value(tmp_path: Path) -> None:
    test, longrepr = v6_cases._replay(
        "from pkg.geo import parse", 'parse("1,2")', "Point(x=1, y=2)"
    )
    observed = v6_cases._observe(tmp_path, tests=v6_cases.TESTS_ROWS, test=test,
                                 longrepr=longrepr, policy=intent_rules.INTENT_POLICY_V61)
    admitted = [c for c in observed.contracts if c.admitted]
    assert len(admitted) == 1 and admitted[0].flow_bound and admitted[0].flow_reason == ""
    assert observed.value_specified == ()
    assert intent_verdict(observed) is None
    assert intent_rules.evidence_class_for(observed) == intent_rules.EVIDENCE_CLASS_REGRESSION
    record = observed.record()
    assert {"flow_bound", "flow_reason"} <= set(record["contracts"][0])
    assert IntentObservation(**record).digest() == observed.digest()


def test_v6_is_no_longer_selectable_and_v61_is() -> None:
    from attest.review.config import ReviewConfig, validate_review_config

    validate_review_config(ReviewConfig(intent_policy=intent_rules.INTENT_POLICY_V61))
    with pytest.raises(ValueError, match="intent_policy must be one of"):
        validate_review_config(ReviewConfig(intent_policy=INTENT_POLICY_V6))


def test_a_site_whose_receiver_is_bound_inside_a_block_is_refused_not_dropped(
    tmp_path: Path,
) -> None:
    """Recognised through D-254's function-wide reading, bound through D-255's: the site is
    reported with its reason by the search and recorded unbound by the reader."""
    from binding_cases import GEO_BASE

    from attest.review.contracts import contract_probes

    (tmp_path / "geo.py").write_text(GEO_BASE, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_geo.py").write_text(
        "from geo import Grid, Point\nimport contextlib\n\n\n"
        "def test_cell():\n"
        "    with contextlib.nullcontext():\n"
        "        g = Grid(width=2)\n"
        "    assert g.cell(Point(1, 2)) == Point(2, 2)\n",
        encoding="utf-8",
    )
    search = contract_probes(tmp_path, "geo.py", ["cell"])
    assert search.probes == ()
    reason = dict(search.refused)["tests/test_geo.py:8#0"]
    assert "'g' is assigned in test_cell at line 7" in reason


# --- the independent review's shapes (D-255), each refused ------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            """
            def test_x():
                text = "01,02"
                other = text
                text = "1,2"
                assert parse(other) == 1
            """, "line 5 rebinds 'text', which line 4 reads", id="a stale binding chain"),
        pytest.param(
            """
            from geo import parse, public
            def test_x():
                parse = public
                assert parse("1,2") == 1
            """, "'parse' is imported or defined at module level and rebound in test_x",
            id="the callee rebound in the test"),
        pytest.param(
            """
            from geo import parse
            def parse(t):
                return 1
            def test_x():
                assert parse("1,2") == 1
            """, "'parse' is bound more than once at module level (lines 2, 3)",
            id="the callee rebound at module level"),
        pytest.param(
            """
            def test_x():
                text = "1,2"
                match "01,02":
                    case text:
                        pass
                assert parse(text) == 1
            """, "line 5 rebinds 'text' in a match pattern", id="a match capture"),
        pytest.param(
            """
            @mock.patch.object(geo, "parse", fake)
            def test_x():
                assert parse("1,2") == 1
            """, "marked mock.patch", id="patch.object"),
        pytest.param(
            """
            @patch.dict("os.environ", {"A": "1"})
            def test_x():
                assert parse("1,2") == 1
            """, "marked patch", id="patch.dict"),
        pytest.param(
            """
            needs_x = pytest.mark.skipif(True, reason="x")
            @needs_x
            def test_x():
                assert parse("1,2") == 1
            """, "marked pytest.mark.skipif", id="a mark bound to a module name"),
        pytest.param(
            """
            @pytest.mark.parametrize("text", [pytest.param("1,2", marks=pytest.mark.skip)])
            def test_x(text):
                assert parse(text) == 1
            """, "marked pytest.mark.skip", id="a row marked skip"),
        pytest.param(
            """
            @pytest.mark.skip
            class TestOuter:
                class TestInner:
                    def test_x(self):
                        assert parse("1,2") == 1
            """, "marked pytest.mark.skip at line 2", id="an outer class marked skip"),
        pytest.param(
            """
            text = "1,2"
            def test_x(text):
                assert parse(text) == 1
            """, "the call depends on 'text', a fixture of test_x",
            id="a parameter that shadows a module constant"),
        pytest.param(
            """
            @pytest.mark.parametrize("text", ["1,2"], indirect=True)
            def test_x(text):
                assert parse(text) == 1
            """, "marked parametrize(indirect=...)", id="an indirect parametrization"),
        pytest.param(
            """
            import geo
            def test_x():
                geo.int = lambda s: 1
                assert parse("1,2") == 1
            """, "line 4 changes state through 'geo.int'",
            id="module state the call does not name"),
        pytest.param(
            """
            TEXT = "1,2"
            def test_x():
                globals()["TEXT"] = "01,02"
                assert parse(TEXT) == 1
            """, "line 4 changes state through", id="globals()"),
        pytest.param(
            """
            PARTS = ["1,2"]
            def test_x():
                alias = PARTS
                alias[0] = "01,02"
                assert parse(PARTS[0]) == 1
            """, "line 4 touches the module-level 'PARTS'", id="an alias of a mutable constant"),
    ],
)
def test_the_reviews_shapes_are_refused(source: str, expected: str) -> None:
    reason = _flow(source)
    assert expected in reason, reason


def test_a_path_nested_beyond_the_interpreters_depth_is_refused_not_raised() -> None:
    from attest.review.contracts import flow_refusal, program_point

    module = ast.parse("def test_x():\n    a" + ".b" * 600 + "()\n    assert parse('1,2') == 1\n")
    func = module.body[0]
    assert isinstance(func, ast.FunctionDef)
    statement = func.body[1]
    assert isinstance(statement, ast.Assert) and isinstance(statement.test, ast.Compare)
    call = statement.test.left
    reason = flow_refusal(program_point(func, call), func, call, module=module)
    assert "nested too deeply" in reason


def test_a_stale_chain_in_the_models_own_setup_binds_no_input() -> None:
    from attest.review.contracts import probe_call

    call = probe_call(
        "from geo import parse\n\n\ndef test_attest_replay():\n"
        "    s = '01,02'\n    u = s\n    s = '1,2'\n    _attest_value = parse(u)\n",
        "geo",
    )
    assert call is not None and "line 7 rebinds 's', which line 6 reads" in call.flow


def test_the_generator_writes_the_test_bodys_bindings_in_source_order(tmp_path: Path) -> None:
    from binding_cases import GEO_BASE

    from attest.review.contracts import contract_probes

    (tmp_path / "geo.py").write_text(GEO_BASE, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_geo.py").write_text(
        "from geo import Grid, Point\n\n\n"
        "def test_cell():\n"
        "    p = Point(1, 2)\n"
        "    g = Grid(width=2)\n"
        "    assert g.cell(p) == Point(2, 2)\n",
        encoding="utf-8",
    )
    search = contract_probes(tmp_path, "geo.py", ["cell"])
    assert [probe.spec.setup for probe in search.probes] == ["p = Point(1, 2)\ng = Grid(width=2)"]


def test_a_contract_covering_a_value_the_assertion_does_not_pin_is_inconsistent() -> None:
    forged = _admitted_observation(derived="Point(x=9, y=9)", pinned="'Point(x=9, y=9)'")
    verdict = intent_verdict(forged)
    assert verdict is not None and "covers a value the failing assertion does not pin" in verdict


def test_a_contract_about_a_symbol_the_change_did_not_touch_is_inconsistent() -> None:
    forged = _admitted_observation(symbol="Grid.cell")
    verdict = intent_verdict(forged)
    assert verdict is not None and "which this change did not touch" in verdict


# --- the second review's shapes (D-255) ----------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param(
            """
            X = "01,02"
            TEXT = X
            def test_x():
                X = "1,2"
                assert parse(TEXT) == 1
            """, "the module-level 'TEXT' reads 'X', which test_x binds itself",
            id="a module constant reading a name the test shadows"),
        pytest.param(
            """
            import atexit
            def test_x():
                @atexit.register
                def hook(): pass
                assert parse("1,2") == 1
            """, "line 4 reads 'atexit.register'", id="a bare decorator"),
        pytest.param(
            """
            def test_x():
                @register
                def hook(): pass
                assert parse("1,2") == 1
            """, "line 4 decorates 'hook'", id="a bare-name decorator"),
        pytest.param(
            """
            import os
            def test_x():
                def hook(x: os.putenv("A", "1")): pass
                assert parse("1,2") == 1
            """, "line 4 calls os.putenv", id="an annotation evaluated at definition"),
        pytest.param(
            """
            def test_x():
                class Sub(Base): pass
                assert parse("1,2") == 1
            """, "line 3 creates the class 'Sub' from a base", id="a class with a base"),
        pytest.param(
            """
            import os
            def test_x():
                _ = os.environ["HOME"]
                assert parse("1,2") == 1
            """, "line 4 reads", id="an item read"),
        pytest.param(
            """
            @unittest.skipIf(True, "no")
            def test_x():
                assert parse("1,2") == 1
            """, "marked unittest.skipIf", id="unittest.skipIf"),
        pytest.param(
            """
            @unittest.expectedFailure
            def test_x():
                assert parse("1,2") == 1
            """, "marked unittest.expectedFailure", id="unittest.expectedFailure"),
        pytest.param(
            """
            from unittest.mock import patch as p
            @p.object(geo, "int", fake)
            def test_x():
                assert parse("1,2") == 1
            """, "marked p", id="patch under an import alias"),
        pytest.param(
            """
            from geo import parse
            from helpers import *
            def test_x():
                assert parse("1,2") == 1
            """, "the star import at line 3", id="a star import"),
        pytest.param(
            """
            import pkg
            def test_x():
                items = ["a", "b"]
                n = pkg.push(items)
                assert first(items, n) == "a"
            """, "line 5 hands 'items' to pkg.push", id="a binding in force that changes a value"),
        pytest.param(
            """
            import pkg
            def test_x():
                items = ["a", "b"]
                assert first(items, pkg.push(items)) == "a"
            """, "hands 'items' to pkg.push", id="an argument that changes another"),
    ],
)
def test_the_second_reviews_shapes_are_refused(source: str, expected: str) -> None:
    reason = _flow(source, callee="parse" if "parse(" in source else "first")
    assert expected in reason, reason


def test_an_immutable_row_value_handed_to_a_binding_call_is_read() -> None:
    reason = _flow(
        """
        @pytest.mark.parametrize("value", ["", "a"])
        def test_x(value):
            result = parse_variables(value)
            assert list(result) == []
        """,
        callee="list",
    )
    assert reason == ""


def test_mark_aliases_are_read_once_each_however_wide_the_table() -> None:
    import time

    levels = ["L1 = [1, 2, 3, 4, 5, 6, 7, 8]"] + [
        f"L{n} = [{', '.join([f'L{n - 1}'] * 8)}]" for n in range(2, 10)
    ]
    source = "\n".join(levels) + (
        "\n@pytest.mark.parametrize('x', L9)\ndef test_x(x):\n    assert parse(x) == 1\n"
    )
    started = time.monotonic()
    _flow(source)
    assert time.monotonic() - started < 2.0


def test_the_contract_cap_stops_a_long_scan(tmp_path: Path) -> None:
    from binding_cases import GEO_BASE

    from attest.review.contracts import MAX_CONTRACTS, _contracts_in

    (tmp_path / "geo.py").write_text(GEO_BASE, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    body = "from geo import Point, parse\n\n" + "".join(
        f"\ndef test_{n}():\n    assert parse('{n},{n}') == Point({n}, {n})\n" for n in range(300)
    )
    (tmp_path / "tests" / "test_geo.py").write_text(body, encoding="utf-8")
    probe = (
        "import re\nfrom geo import parse\n\n\ndef test_attest_replay():\n"
        "    _attest_value = parse('1,1')\n"
    )
    found = _contracts_in(tmp_path, "geo.py", ["parse"], ["'Point(x=1, y=1)'"], probe)
    assert MAX_CONTRACTS * 4 <= len(found) < MAX_CONTRACTS * 4 + 4
