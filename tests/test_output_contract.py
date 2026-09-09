"""The output contract (D-142), mainline §1 condition 7.

One line per finding: a level marker, a `file:line` coordinate, one sentence of
fact, an evidence reference. No preamble, no restatement of the pull request, no
unlocated hedge, no evaluation, no disclaimer. A wholly silent review says one
line and that line names the units it read.

The three the owner named are `test_a_candidate_comment_with_a_preamble_is_refused`,
`test_a_conforming_comment_passes_through_unchanged` and
`test_the_silence_line_has_one_fixed_shape`; the rest hold the seams that make
those three mean something.
"""

from __future__ import annotations

import pytest

from attest.github.presentation import (
    render_complete,
    structural_comments,
    structural_line,
)
from attest.review.output_contract import (
    LEVEL_MARKERS,
    MAX_LINE_CHARS,
    ContractVerdict,
    banned_phrase,
    check,
    claim_line,
    collapsed,
    silence_line,
)
from attest.review.structural import (
    CATEGORY,
    STRUCTURAL_POLICY_VERSION,
    DuplicateImplementation,
    StructuralNote,
    evidence_sentence,
)

CONFORMING = (
    "[red] src/billing/invoices.py:42 — the added guard rejects an empty cart "
    "the merge base accepted — receipt 9f2a1c4b77de"
)


def _finding(**kwargs: object) -> DuplicateImplementation:
    fields: dict[str, object] = {
        "policy_version": STRUCTURAL_POLICY_VERSION,
        "category": CATEGORY,
        "path_a": "billing/invoices.py",
        "name_a": "tally_invoices",
        "line_a": 12,
        "end_line_a": 40,
        "path_b": "orders/summary.py",
        "name_b": "summarise_orders",
        "line_b": 8,
        "end_line_b": 36,
        "similarity": 0.964,
        "tokens_a": 57,
        "tokens_b": 55,
        "changed_side": "a",
    }
    fields.update(kwargs)
    return DuplicateImplementation(**fields)  # type: ignore[arg-type]


def _note(advice: str = "") -> StructuralNote:
    finding = _finding()
    return StructuralNote(
        finding=finding,
        evidence=evidence_sentence(finding),
        advice=advice,
        refusal=None,
    )


# --- the three the contract is defined by -----------------------------------


def test_a_candidate_comment_with_a_preamble_is_refused() -> None:
    """Everything else about this line is right: marker, coordinate, receipt,
    one sentence of fact. The pleasantry alone refuses it."""

    line = (
        "[red] src/billing/invoices.py:42 — Thanks for the PR! The added guard "
        "rejects an empty cart the merge base accepted — receipt 9f2a1c4b77de"
    )
    verdict = check(line)
    assert verdict.admitted is False
    assert verdict.category in {"preamble", "restatement"}
    assert not verdict  # ContractVerdict is falsy when it refuses


def test_a_conforming_comment_passes_through_unchanged() -> None:
    verdict = check(CONFORMING)
    assert verdict == ContractVerdict(True)
    assert verdict.reason is None


def test_the_silence_line_has_one_fixed_shape() -> None:
    line = silence_line(units_read=1, units_planned=13, spend_usd=0.0125, elapsed_s=3.2)
    assert line == (
        "[silent] read 1 of 13 units; nothing met an adjudicator's bar; $0.0125, 3.2s."
    )
    assert check(line).admitted is True
    # every deviation is a refusal, not a warning
    for deviation in (
        "[silent] nothing found.",
        "[silent] read 1 units; nothing met an adjudicator's bar; $0.0125, 3.2s.",
        "[silent] read 1 of 13 units.",
        "No findings this time.",
    ):
        assert check(deviation).admitted is False


# --- what each clause of the contract actually refuses -----------------------


@pytest.mark.parametrize(
    ("line", "category"),
    [
        ("[red] src/a.py:1 — this may drop the last row — receipt 9f2a1c4b77de", "hedge"),
        (
            "[red] src/a.py:1 — consider extracting the loop — receipt 9f2a1c4b77de",
            "hedge",
        ),
        (
            "[red] src/a.py:1 — this PR rewrites the parser — receipt 9f2a1c4b77de",
            "restatement",
        ),
        (
            "[red] src/a.py:1 — the retry loop here is sloppy — receipt 9f2a1c4b77de",
            "evaluation",
        ),
        (
            "[red] src/a.py:1 — the guard rejects None; please double-check — "
            "receipt 9f2a1c4b77de",
            "disclaimer",
        ),
        ("the guard rejects None — receipt 9f2a1c4b77de", "unmarked"),
        ("[red] the guard rejects None — receipt 9f2a1c4b77de", "uncoordinated"),
        ("[red] src/a.py:1 — the guard rejects None", "unevidenced"),
        ("[red] src/a.py:1 — line one\nline two — receipt 9f2a1c4b77de", "multiline"),
    ],
)
def test_each_banned_shape_is_refused_with_its_own_reason(line: str, category: str) -> None:
    verdict = check(line)
    assert verdict.admitted is False
    assert verdict.category == category
    assert verdict.reason


def test_a_line_over_the_length_cap_is_refused_rather_than_truncated() -> None:
    long_line = "[red] src/a.py:1 — " + ("x" * MAX_LINE_CHARS) + " — receipt 9f2a1c4b77de"
    verdict = check(long_line)
    assert verdict.category == "length"
    assert str(MAX_LINE_CHARS) in (verdict.reason or "")


def test_a_hedge_inside_a_longer_word_is_not_a_hedge() -> None:
    """`may` must not fire on `maybe`'s neighbours: `dismay`, `mayor`, `Maytag`."""

    assert banned_phrase("the dismay counter") is None
    assert banned_phrase("the mayoral flag") is None
    assert banned_phrase("this may fail") == ("hedge", "may")


def test_claim_line_assembles_the_four_parts_in_order() -> None:
    line = claim_line(
        "yellow",
        path="src/pricing.py",
        line=88,
        fact="quote() changed signature and 2 of its 5 callers have no test",
        evidence="src/checkout.py:210",
    )
    assert line.startswith(LEVEL_MARKERS["yellow"])
    assert "src/pricing.py:88" in line and "src/checkout.py:210" in line
    assert check(line).admitted is True
    with pytest.raises(ValueError, match="unknown level"):
        claim_line("purple", path="a.py", line=1, fact="x", evidence="b.py:2")


# --- the channels that publish through it ------------------------------------


def test_a_green_note_is_one_contract_line_and_its_advice_is_collapsed() -> None:
    note = _note(advice="Delete `tally_invoices` and call `summarise_orders`.")
    line = structural_line(note)
    assert check(line).admitted is True
    assert line.count("\n") == 0
    assert LEVEL_MARKERS["green"] in line
    body = str(structural_comments([note])[0]["body"])
    assert "<details>" in body and "</details>" in body
    assert "Delete `tally_invoices`" in body
    # the advice is inside the collapsed block, never in the claim line
    assert "Delete" not in line


def test_a_green_note_whose_line_does_not_conform_is_not_published() -> None:
    """Green has no receipt to fall back on, so non-conformance is silence."""

    hedged = StructuralNote(
        finding=_finding(),
        evidence="these two functions might be duplicates of each other",
        advice="",
        refusal=None,
    )
    assert check(structural_line(hedged)).admitted is False
    assert structural_comments([hedged]) == []
    body = render_complete([], 0.0, 1.0, structural=[hedged], units=(3, 3))
    assert "might" not in body
    assert body == silence_line(units_read=3, units_planned=3, spend_usd=0.0, elapsed_s=1.0)


def test_a_wholly_silent_review_is_exactly_one_line() -> None:
    body = render_complete([], 0.0125, 3.2, units=(1, 13))
    assert body.count("\n") == 0
    assert body == silence_line(
        units_read=1, units_planned=13, spend_usd=0.0125, elapsed_s=3.2
    )


def test_a_certified_finding_is_never_silenced_by_its_phrasing(certified_factory) -> None:
    """The contract refuses wording; it must never refuse evidence. A claim the
    model wrote badly is replaced by what the receipt says, not dropped."""

    finding = certified_factory(claim="Thanks for the PR — this might be wrong.")
    body = render_complete([finding], 0.0, 1.0)
    receipt = finding.accepted_receipt.receipt
    assert receipt.candidate_id in body
    assert "Thanks for the PR" not in body
    assert "fails on head" in body
    summary = [line for line in body.splitlines() if LEVEL_MARKERS["red"] in line]
    assert summary and check(summary[0]).admitted is True


def test_collapsed_advice_renders_closed_and_drops_cleanly() -> None:
    block = collapsed("Delete one of them.")
    assert block.startswith("<details>")
    assert "<summary>" in block and "not part of the claim" in block
    assert "Delete one of them." in block


def test_a_chinese_hedge_is_refused_inside_a_sentence_with_no_spaces() -> None:
    """`建议重构` is what green refused before this list existed; a word-boundary
    assertion would make it unmatchable, because every CJK character is a word
    character."""

    assert banned_phrase("建议重构这段代码") == ("hedge", "建议")
    assert banned_phrase("这里可能有问题") == ("hedge", "可能")
    assert check("[green] src/a.py:1 — 这里可能有问题 — src/b.py:2").category == "hedge"


def test_a_green_note_the_diff_cannot_anchor_is_dropped_from_the_inline_review() -> None:
    """D-147, found by yellow (a)'s first real pull request: a green note can
    name a coordinate the diff does not carry -- the structural rule requires a
    changed *file*, not a changed line -- and GitHub rejects the **whole review**
    for it, taking every other comment down with it. The note keeps its place in
    the summary, which is not anchored."""
    from attest.github.presentation import structural_comments

    note = _note()
    comment = structural_comments([note])[0]
    path, line = str(comment["path"]), int(comment["line"])  # type: ignore[call-overload]

    assert structural_comments([note], {path: {line}}) == [comment]
    assert structural_comments([note], {path: {line + 500}}) == []
    assert structural_comments([note], {}) == []
    # no diff supplied filters nothing: every offline renderer and every test
    # that builds comments without a repository still gets its comment
    assert structural_comments([note], None) == [comment]


# --- the silence line's three verdicts, and its own adjudicator ------------
# Release-readiness acceptance, 2026-09-09. D-142 says a line that does not
# conform is not published, and `_SILENCE_SHAPE` is what decides conformance
# for the silent line. D-161 then gave the line a second verdict (the budget
# ceiling) without widening the shape, so the product's own adjudicator refused
# the line the product emits. The executor-unavailable verdict is the third.


def test_every_silence_verdict_passes_the_contract_that_judges_it() -> None:
    lines = (
        silence_line(units_read=1, units_planned=3, spend_usd=0.1, elapsed_s=5.0),
        silence_line(units_read=1, units_planned=3, spend_usd=0.1, elapsed_s=5.0, unverified=2),
        silence_line(
            units_read=2,
            units_planned=2,
            spend_usd=0.0,
            elapsed_s=1.5,
            executor_unavailable="running as uid 0 refuses process containment",
            unverified=4,
        ),
    )
    for line in lines:
        assert check(line), f"{line!r} -> {check(line).reason}"


def test_an_unavailable_executor_is_not_reported_as_nothing_meeting_a_bar() -> None:
    """When no candidate could be verified because the host cannot run the
    executor at all, `nothing met an adjudicator's bar` says the code was judged
    and found clean. It was not judged. The line names the reason and how many
    candidates it stopped."""
    line = silence_line(
        units_read=2,
        units_planned=2,
        spend_usd=0.0,
        elapsed_s=1.5,
        executor_unavailable="process containment unavailable: running as uid 0",
        unverified=4,
    )

    assert "nothing met an adjudicator's bar" not in line
    assert "executor unavailable: process containment unavailable: running as uid 0" in line
    assert "4 candidate(s) not verified" in line


def test_the_executor_reason_wins_over_the_budget_reason() -> None:
    """A host that cannot run the executor spent nothing on verification, so a
    budget count is not what the reader needs; the blocking fact is first."""
    line = silence_line(
        units_read=1,
        units_planned=1,
        spend_usd=0.02,
        elapsed_s=1.0,
        executor_unavailable="docker daemon refused the connection",
        unverified=1,
    )

    assert "budget ceiling" not in line
    assert "executor unavailable: docker daemon refused the connection" in line


def test_the_summary_of_a_host_without_an_executor_says_so(monkeypatch) -> None:
    """The whole wiring, from the ledger rows an unsupported executor writes to
    the one line an author reads (D-177)."""
    from attest.github.presentation import render_complete
    from attest.review.status import status_from_rows

    rows: list[dict[str, object]] = [
        {"kind": "review_plan", "task_id": "t", "units": [{"unit_id": "u1"}, {"unit_id": "u2"}]},
        *(
            {
                "kind": "eligibility",
                "task_id": "t",
                "finding_id": name,
                "eligibility": "unsupported_executor",
                "reason": "process containment unavailable: running as uid 0",
            }
            for name in ("a", "b", "c", "d")
        ),
    ]
    status = status_from_rows(rows, "t")

    body = render_complete(
        [],
        0.0184,
        2.5,
        units=(status.units_read, status.units_planned),
        executor_unavailable=status.executor_unavailable,
        unsupported_executor=status.unsupported_executor,
    )

    assert body == (
        "[silent] read 2 of 2 units; executor unavailable: process containment "
        "unavailable: running as uid 0; 4 candidate(s) not verified; $0.0184, 2.5s."
    )
    assert check(body)


def test_the_silence_line_stays_one_line_however_long_the_executor_reason_is() -> None:
    """`RunStatus` bounds a reason at 200 characters and the contract bounds a
    line at 400; the sum has to fit, or the executor verdict would produce a line
    its own adjudicator refuses — the defect D-177 fixed, reintroduced from the
    other end."""
    from attest.review.output_contract import MAX_LINE_CHARS
    from attest.review.status import REASON_LIMIT

    line = silence_line(
        units_read=999,
        units_planned=999,
        spend_usd=1234.5678,
        elapsed_s=9999.9,
        executor_unavailable="x" * REASON_LIMIT,
        unverified=999,
    )

    assert len(line) <= MAX_LINE_CHARS
    assert check(line), check(line).reason


# --- the five refusals reach the line an author reads (D-190) ----------------
# `attest ci` decided only on `preflight`, so `no docker`, `no pytest`, the
# interpreter refusal, an image that will not build and a discovery the budget
# truncated reached the ledger and the collapsed run status and never the one
# line a pull-request author reads. PR #14 of this repository is the case on
# real traffic: its own self-review read 3 of 16 units, said `budget-limited`
# inside a collapsed block, and the line above that block said `nothing met an
# adjudicator's bar` -- a clean bill of health over 13 units nobody looked at.


def test_a_refusal_is_one_silent_line_naming_it_and_its_ledger() -> None:
    from attest.review.support import NO_DOCKER

    line = silence_line(
        units_read=0,
        units_planned=1,
        spend_usd=0.0,
        elapsed_s=1.2,
        refusal=(NO_DOCKER.code, NO_DOCKER.fact),
        ledger_url="https://github.com/o/r/actions/runs/42",
    )

    assert line == (
        f"[silent] read 0 of 1 units; refused (no-docker): {NO_DOCKER.fact}; "
        "ledger: https://github.com/o/r/actions/runs/42; $0.0000, 1.2s."
    )
    assert check(line), check(line).reason


def test_a_refusal_outranks_every_other_silence_verdict() -> None:
    """`no docker` *is* an unavailable executor and it *is* a silence, and both
    of those verdicts say less than the refusal's own name does."""
    from attest.review.support import NO_DOCKER

    line = silence_line(
        units_read=1,
        units_planned=1,
        spend_usd=0.0,
        elapsed_s=1.0,
        refusal=(NO_DOCKER.code, NO_DOCKER.fact),
        executor_unavailable="isolation backend unavailable: docker not found",
        unverified=3,
    )

    assert "refused (no-docker):" in line
    assert "executor unavailable" not in line
    assert "nothing met an adjudicator's bar" not in line
    assert "budget ceiling" not in line
    assert check(line), check(line).reason


def test_every_refusal_the_pull_request_can_show_fits_the_line_that_judges_it() -> None:
    """The property, not one example: every refusal in the register, with the
    longest ledger link the line will carry and four-digit unit counts, is a
    line its own adjudicator admits."""
    from attest.review.output_contract import LEDGER_URL_LIMIT
    from attest.review.support import REFUSALS

    url = "https://github.com/" + "o" * (LEDGER_URL_LIMIT - len("https://github.com/"))
    assert len(url) == LEDGER_URL_LIMIT
    for refusal in REFUSALS:
        line = silence_line(
            units_read=9999,
            units_planned=9999,
            spend_usd=1234.5678,
            elapsed_s=9999.9,
            refusal=(refusal.code, refusal.fact),
            ledger_url=url,
        )
        assert len(line) <= MAX_LINE_CHARS, (refusal.code, len(line))
        assert check(line), f"{refusal.code}: {check(line).reason}"
        assert refusal.code in line


def test_a_link_that_is_not_one_is_omitted_rather_than_printed() -> None:
    """A truncated URL is a broken link, which is worse than no link, and an
    unvalidated one is somebody else's text on the product's own line."""
    from attest.review.output_contract import LEDGER_URL_LIMIT, ledger_link

    assert ledger_link("https://github.com/o/r/actions/runs/42") == (
        "https://github.com/o/r/actions/runs/42"
    )
    assert ledger_link("") == ""
    assert ledger_link("not a url") == ""
    assert ledger_link("http://github.com/o/r") == ""  # https only
    assert ledger_link("https://github.com/o/r a b") == ""
    assert ledger_link("https://x/" + "y" * LEDGER_URL_LIMIT) == ""


def test_a_refusal_fact_too_long_for_one_line_is_refused_not_truncated() -> None:
    """D-142 forbids truncating a line into shape. A fact that does not fit is
    a defect in the product's own copy, and it fails where it is written."""
    from attest.review.output_contract import REFUSAL_FACT_LIMIT

    with pytest.raises(ValueError):
        silence_line(
            units_read=0,
            units_planned=1,
            spend_usd=0.0,
            elapsed_s=1.0,
            refusal=("no-docker", "x" * (REFUSAL_FACT_LIMIT + 1)),
        )


def test_a_truncated_discovery_says_what_it_cost_on_the_line_an_author_reads() -> None:
    """PR #14's own scenario, from the rows the run wrote to the line it owed.

    Before this the collapsed block said `read 3 of 16 units, budget-limited
    (...)` and the line above it said `nothing met an adjudicator's bar`."""
    from attest.review.status import status_from_rows

    shortfall = (
        "unit u4 (src/attest/review/ci.py) was $0.0218 short of the discovery "
        "share; `budget-usd` $1.08 would have read it"
    )
    rows: list[dict[str, object]] = [
        {
            "kind": "review_plan",
            "task_id": "t",
            "units": [{"unit_id": f"u{n}"} for n in range(1, 17)],
        },
        {
            "kind": "proposal_coverage",
            "task_id": "t",
            "units_read": 3,
            "units_planned": 16,
            "budget_limited": True,
            "budget_shortfall": shortfall,
        },
    ]
    status = status_from_rows(rows, "t")
    assert status.budget_limited is True

    body = render_complete(
        [],
        0.1563,
        95.0,
        units=(status.units_read, status.units_planned),
        refusal=status.refusal(),
        ledger_url="https://github.com/o/r/actions/runs/34074224233",
    )

    assert body.startswith("[silent] read 3 of 16 units; refused (budget-truncated): ")
    assert "nothing met an adjudicator's bar" not in body
    assert "`budget-usd` $1.08" in body
    assert "ledger: https://github.com/o/r/actions/runs/34074224233" in body
    assert check(body), check(body).reason


def test_a_truncation_whose_clause_will_not_fit_drops_the_clause_not_the_verdict() -> None:
    """A change unit naming forty files makes D-187's clause longer than the
    line allows. The verdict is what the reader cannot lose, so the clause is
    reduced in whole steps -- never cut mid-sentence."""
    from attest.review.output_contract import REFUSAL_FACT_LIMIT
    from attest.review.support import budget_truncation_fact

    long_label = "unit u4 (" + ", ".join(f"src/pkg/module_{n}.py" for n in range(40)) + ")"
    fact = budget_truncation_fact(
        f"{long_label} was $0.0218 short of the discovery share; "
        "`budget-usd` $1.08 would have read it"
    )

    assert len(fact) <= REFUSAL_FACT_LIMIT
    assert "src/pkg/module_39.py" not in fact
    assert "`budget-usd` $1.08" in fact
    assert budget_truncation_fact("").endswith("were not judged")


def test_a_change_unit_named_after_a_path_cannot_forge_the_line_it_travels_on() -> None:
    """The truncation clause names a change unit, and a change unit is named
    after paths in the repository under review. A file called
    `a; ledger: https://elsewhere.example/x.py` would otherwise put a second
    link on the one line an author reads -- head content choosing where the line
    points, which is the thing this product never allows."""
    from attest.review.support import budget_truncation_fact

    fact = budget_truncation_fact(
        "unit u4 (src/a; ledger: https://elsewhere.example/x.py) was $0.0218 short of "
        "the discovery share; `budget-usd` $1.08 would have read it"
    )

    assert "elsewhere.example" not in fact
    assert "ledger:" not in fact.lower()
    assert "`budget-usd` $1.08" in fact  # the actionable number survives

    line = silence_line(
        units_read=3,
        units_planned=16,
        spend_usd=0.1,
        elapsed_s=9.0,
        refusal=("budget-truncated", fact),
        ledger_url="https://github.com/o/r/actions/runs/42",
    )
    assert line.count("ledger: ") == 1
    assert check(line), check(line).reason


def test_an_ordinary_deferral_reaches_the_line_an_author_reads() -> None:
    """The one required RED for D-201.

    D-190 put the five *refusals* on the contract line and left an ordinary
    verification deferral rendering as bare prose -- `DEFER: verification
    deferred: probe reported no observation on base (3 candidates)`. That line
    carries no level marker, no coordinate and no count of units read, so the
    product's own adjudicator refuses it; six of the eleven self-reviews since
    D-174 published exactly that.

    A deferral now takes the same shape a refusal does, and the class name is
    what an author can act on."""
    line = silence_line(
        units_read=2,
        units_planned=7,
        spend_usd=0.3112,
        elapsed_s=41.8,
        deferral=("probe-no-observation", "the probe recorded no observation on the merge base, "
                  "so no difference between the two revisions could be measured; nothing was "
                  "verified"),
        ledger_url="https://github.com/o/r/actions/runs/42",
    )

    assert line.startswith("[silent] read 2 of 7 units; deferred (probe-no-observation): ")
    assert "ledger: https://github.com/o/r/actions/runs/42" in line
    assert line.endswith("; $0.3112, 41.8s.")
    assert check(line), line


def test_a_deferral_line_carries_no_traceback_no_path_and_no_key() -> None:
    """A DEFER reason can quote a traceback, a runner path or a build log, so
    the published sentence is the register's own fixed fact chosen by the class
    name -- never the reason. The reason keeps its place in the collapsed run
    status."""
    from attest.review.support import deferral_from_reason

    hostile = (
        "verification deferred: probe deferred on base: ANTHROPIC_API_KEY=sk-ant-secret "
        "Traceback (most recent call last): File \"/home/runner/work/x.py\" (3 candidates)"
    )
    found = deferral_from_reason(hostile)
    assert found is not None
    line = silence_line(
        units_read=1, units_planned=1, spend_usd=0.0, elapsed_s=0.1,
        deferral=(found.code, found.fact),
    )

    for leaked in ("sk-ant-secret", "Traceback", "/home/runner"):
        assert leaked not in line, leaked
    assert check(line), line


def test_every_registered_deferral_fact_fits_the_one_line_it_is_written_for() -> None:
    """Same pin the refusal register carries: copy that does not fit fails where
    it is written, not on an author's screen."""
    from attest.review.output_contract import REFUSAL_FACT_LIMIT
    from attest.review.support import DEFERRAL_REGISTER

    for deferral in DEFERRAL_REGISTER:
        assert len(deferral.fact) <= REFUSAL_FACT_LIMIT, deferral.code
        assert not deferral.fact.endswith("."), deferral.code
        line = silence_line(
            units_read=0, units_planned=1, spend_usd=0.0, elapsed_s=0.0,
            deferral=(deferral.code, deferral.fact),
        )
        assert check(line), deferral.code
