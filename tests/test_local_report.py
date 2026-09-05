"""`attest review`'s terminal output obeys the same contract as the comment (D-152).

Two properties, and both fail on the pre-D-152 report, which printed prose
paragraphs (`verified findings (each backed by one accepted receipt):`,
`unverified candidates (3; ranked by internal score...)`) and no level markers
at all:

1. every author-visible claim is one contract line with a level marker, and the
   run always ends with **one** accounting line naming units, candidates and the
   drawer's reason distribution;
2. `--explain` -- and only `--explain` -- prints the drawer, one line per silent
   candidate, with the reason class the ledger recorded.
"""

from __future__ import annotations

from types import SimpleNamespace

from attest.review.output_contract import LEVEL_MARKERS, SILENCE_MARKER
from attest.review.output_contract import check as contract_check
from attest.review.report import drawer_reason_class, render
from attest.review.status import RunStatus


def _result(finding_id: str, path: str, line: int, wealth: float) -> SimpleNamespace:
    return SimpleNamespace(
        finding=SimpleNamespace(finding_id=finding_id, file=path, line=line, claim="a claim"),
        wealth=wealth,
        action="drawer",
    )


def _outcome(*results: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(formal=[], drawer_overflow=[], drawer=list(results), discarded=[])


STATUS = RunStatus(
    task_id="t",
    units_read=3,
    candidates=2,
    eligible=2,
    attempts=2,
    certified=0,
    published=0,
    units_planned=9,
)
REASONS = {
    "aaaaaaaaaa": (
        "intent: intent stated in the change itself: the same change also updates a test"
    ),
    "bbbbbbbbbb": "generation failed: BudgetExceeded: call 'probe-x' estimated $0.07",
}


def test_a_silent_run_says_one_silence_line_and_one_accounting_line() -> None:
    body = render(
        _outcome(
            _result("aaaaaaaaaa", "pkg/a.py", 10, 2.0), _result("bbbbbbbbbb", "pkg/b.py", 20, 1.0)
        ),
        alpha=0.1,
        spend_usd=0.0125,
        budget_usd=1.0,
        elapsed_s=3.2,
        status=STATUS,
        reasons=REASONS,
    )
    lines = body.splitlines()

    assert lines[0].startswith(SILENCE_MARKER)
    # the accounting line is last, and it is the only place a count appears
    assert lines[-1].startswith("read 3/9 units, candidates 2, drawer 2")
    assert "intent-stated-in-diff 1" in lines[-1]
    assert "budget-exhausted 1" in lines[-1]
    # the drawer's contents are not printed without --explain
    assert "pkg/a.py:10" not in body


def test_explain_prints_one_line_per_silent_candidate_with_its_reason() -> None:
    body = render(
        _outcome(
            _result("aaaaaaaaaa", "pkg/a.py", 10, 2.0), _result("bbbbbbbbbb", "pkg/b.py", 20, 1.0)
        ),
        alpha=0.1,
        spend_usd=0.0125,
        budget_usd=1.0,
        elapsed_s=3.2,
        status=STATUS,
        reasons=REASONS,
        explain=True,
    )

    assert "[aaaaaaaaaa] pkg/a.py:10 — intent-stated-in-diff" in body
    assert "[bbbbbbbbbb] pkg/b.py:20 — budget-exhausted" in body
    # ranked by wealth, highest first, as the drawer has always been
    assert body.index("pkg/a.py:10") < body.index("pkg/b.py:20")


def test_every_drawer_reason_the_corpus_has_produced_has_a_class() -> None:
    """The distribution is only useful if it does not collapse into `other`."""
    corpus = {
        "intent: intent stated in the change itself: ...": "intent-stated-in-diff",
        "intent: behavior change confirmed, intent unknown: ...": "behavior-change-intent-unknown",
        "intent: value change confirmed, intent unknown: ...": "value-change-intent-unknown",
        "probe deferred on base: pytest collection failure": "probe-deferred",
        "probe reported no observation on base": "probe-no-observation",
        "generation failed: BudgetExceeded: call 'probe-x'": "budget-exhausted",
        "unfaithful generated test: fails on base as well": "unfaithful-reproduction",
        "isolation backend unavailable: bootstrap failed": "host-blocked",
        "pytest passed on head in 3/3 runs; base not executed": "not-reproduced-on-head",
        "": "unrecorded",
    }
    assert {reason: drawer_reason_class(reason) for reason in corpus} == corpus


def test_a_verified_finding_is_one_contract_line_naming_its_receipt() -> None:
    receipt = SimpleNamespace(
        candidate_id="cccccccccc",
        evidence_class="regression",
        provenance_digest="3253ada5eff4aaaa",
        head_runs=[1, 2, 3],
        base_runs=[1, 2, 3],
        test_node="t::test_attest_replay",
    )
    finding = SimpleNamespace(
        accepted_receipt=SimpleNamespace(receipt=receipt),
        anchors=[SimpleNamespace(path="pkg/a.py", line=10)],
        claim="the header is set unconditionally for GET",
    )

    body = render(
        _outcome(),
        alpha=0.1,
        spend_usd=0.0125,
        budget_usd=1.0,
        elapsed_s=3.2,
        certified=[finding],
        status=STATUS,
    )
    first = body.splitlines()[0]

    assert first.startswith(LEVEL_MARKERS["red"])
    assert contract_check(first).admitted is True
    assert "pkg/a.py:10" in first and "receipt 3253ada5eff4" in first
