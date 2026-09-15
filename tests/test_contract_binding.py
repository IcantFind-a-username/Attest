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
    return flow_refusal(point, func, call, owner=_owners(module).get(id(func)), module=module)


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
                other = [1]
                other.append(len(TEXT))
                assert parse(TEXT) == 1
            """, {}, "", id="read: unrelated statements, an immutable constant handed to a call"),
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
            """, {}, "calls a method of the module-level 'ROWS'",
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
