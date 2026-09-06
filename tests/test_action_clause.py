"""Every author-visible comment says what to do next (D-178).

Release-readiness acceptance, 2026-09-09. D-142 gave the comment a claim line,
a coordinate and evidence, and stopped there. A reader who agrees with the
finding still has to work out what the product wants of them, and the four
levels want four different things:

    red     reproduce it -- the command, then the bundle to verify offline
    gate    the reachable path and the input that triggers it
    yellow  the affected caller, and the two things that close it
    green   the two coordinates, and where the surviving copy should live

The clause is adjudicated by `output_contract.check_comment`, which calls no
model, and it is assembled from coordinates the level already holds -- so it can
never be the thing that suppresses a certified finding.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from attest.github.presentation import (
    impact_comments,
    inline_comments,
    nullability_comments,
    propagation_comments,
    structural_comments,
)
from attest.review.finding_evidence import FindingEvidence, RunSummary
from attest.review.impact import build_call_graph, changed_functions, notes_for_change
from attest.review.output_contract import ACTION_PREFIX, action_clause, check_comment, has_action
from attest.review.structural import (
    STRUCTURAL_POLICY_VERSION,
    DuplicateImplementation,
    structural_note,
)


def _duplicate(**fields: object) -> DuplicateImplementation:
    return DuplicateImplementation(
        policy_version=STRUCTURAL_POLICY_VERSION,
        category="duplicate implementation",
        **fields,  # type: ignore[arg-type]
    )


# --- the adjudicator itself -----------------------------------------------


def test_a_comment_without_an_action_clause_is_refused() -> None:
    body = "[green] a.py:2 — the same implementation as b.py:9 — b.py:9"
    verdict = check_comment(body)
    assert not verdict
    assert verdict.category == "actionless"


def test_two_action_clauses_are_no_action_clause() -> None:
    body = (
        "[green] a.py:2 — the same implementation as b.py:9 — b.py:9\n"
        f"{ACTION_PREFIX} keep `a.py:2`.\n"
        f"{ACTION_PREFIX} keep `b.py:9`."
    )
    assert not check_comment(body)


def test_an_action_clause_that_names_nothing_is_refused() -> None:
    body = (
        "[green] a.py:2 — the same implementation as b.py:9 — b.py:9\n"
        f"{ACTION_PREFIX} clean this up."
    )
    verdict = check_comment(body)
    assert not verdict
    assert verdict.category == "actionless"
    assert not has_action(body)


def test_a_claim_line_that_fails_the_contract_fails_the_comment() -> None:
    """The action clause is added to the contract, not substituted for it."""
    body = f"[green] this might be duplicated\n{ACTION_PREFIX} open `a.py:2`."
    assert not check_comment(body)


# --- the four levels' own comments ----------------------------------------


def _evidence(candidate_id: str) -> FindingEvidence:
    run = RunSummary(run_id="r1", outcome="failed", exit_code=1, log="")
    return FindingEvidence(
        candidate_id=candidate_id,
        test_source="def test_case():\n    assert False\n",
        test_node="test_repro.py::test_case",
        command="python -m pytest .attest-repro/test_repro.py::test_case",
        head_runs=(run,),
        base_runs=(RunSummary(run_id="r2", outcome="passed", exit_code=0, log=""),),
        bundle_path=".attest/evidence/task-1/abc",
        verify_command="attest verify --bundle .attest/evidence/task-1/abc --require-seal",
    )


def test_a_red_comment_tells_the_reader_how_to_reproduce_it(certified_factory) -> None:
    finding = certified_factory()
    candidate_id = finding.accepted_receipt.receipt.candidate_id

    comment = inline_comments([finding], {candidate_id: _evidence(candidate_id)})[0]
    body = str(comment["body"])

    assert check_comment(body), check_comment(body).reason
    clause = action_clause(body) or ""
    assert "pytest" in clause
    assert ".attest/evidence/task-1/abc" in clause


def test_a_red_comment_without_its_evidence_still_says_what_to_do(certified_factory) -> None:
    """Evidence is attached by the caller and may be absent; the receipt digest
    and the finding id are always there, and `attest verify` takes both."""
    finding = certified_factory()

    body = str(inline_comments([finding])[0]["body"])

    assert check_comment(body), check_comment(body).reason
    assert "attest verify" in (action_clause(body) or "")


def _impact_notes() -> list[object]:
    base = "def widen(a):\n    return a\n"
    head = "def widen(a, b):\n    return a\n"
    callers = "from lib import widen\n\n\ndef call():\n    return widen(1, 2)\n"
    graph = build_call_graph({"lib.py": head, "app.py": callers})
    changed = changed_functions(
        path="lib.py", head_source=head, base_source=base, changed_lines={1}
    )
    return list(notes_for_change(graph, changed))


def test_a_yellow_a_comment_offers_the_two_things_that_close_it() -> None:
    notes = _impact_notes()
    assert notes

    body = str(impact_comments(notes)[0]["body"])

    assert check_comment(body), check_comment(body).reason
    clause = action_clause(body) or ""
    assert "app.py:5" in clause  # the untested caller, by coordinate
    assert "test" in clause and "caller" in clause


def test_a_yellow_a_comment_states_its_call_sites_as_resolved_not_as_names() -> None:
    """D-174 made a call site the thing a name *resolves to*; the comment copy
    still said "by name" and "static reachability over names", which describes
    the rule the product no longer runs. The honesty clause stays."""
    body = str(impact_comments(_impact_notes())[0]["body"])

    assert "by name" not in body
    assert "over names" not in body
    assert "resolve" in body.lower()
    assert "named by no test" in body
    assert "never *not covered*" in body


def test_a_green_comment_names_where_the_surviving_copy_goes() -> None:
    finding = _duplicate(
        path_a="billing/invoices.py",
        line_a=2,
        end_line_a=8,
        name_a="summarise_orders",
        path_b="reports/summary.py",
        line_b=11,
        end_line_b=17,
        name_b="tally_invoices",
        similarity=0.97,
        tokens_a=40,
        tokens_b=40,
        changed_side="a",
    )

    body = str(structural_comments([structural_note(finding)])[0]["body"])

    assert check_comment(body), check_comment(body).reason
    clause = action_clause(body) or ""
    assert "billing/invoices.py:2" in clause
    assert "reports/summary.py:11" in clause


@pytest.mark.parametrize("builder", (nullability_comments, propagation_comments))
def test_the_yellow_b_builders_publish_nothing_without_an_action_clause(builder) -> None:
    """Both classes are off or in shadow, so this pins the seam rather than a
    live surface: an empty input publishes nothing, and the builders are the
    only path to a comment."""
    assert builder([]) == []


def test_no_live_comment_builder_can_publish_an_actionless_comment(
    certified_factory, tmp_path: Path
) -> None:
    """The property, over every builder that has an author-visible path today."""
    finding = certified_factory()
    candidate_id = finding.accepted_receipt.receipt.candidate_id
    duplicate = _duplicate(
        path_a="a/one.py",
        line_a=3,
        end_line_a=9,
        name_a="one",
        path_b="b/two.py",
        line_b=4,
        end_line_b=10,
        name_b="two",
        similarity=0.95,
        tokens_a=30,
        tokens_b=30,
        changed_side="b",
    )
    comments = [
        *inline_comments([finding], {candidate_id: _evidence(candidate_id)}),
        *impact_comments(_impact_notes()),
        *structural_comments([structural_note(duplicate)]),
    ]
    assert len(comments) == 3

    for comment in comments:
        body = str(comment["body"])
        verdict = check_comment(body)
        assert verdict, f"{body!r} -> {verdict.reason}"


def test_a_model_paragraph_that_writes_action_cannot_suppress_a_green_note() -> None:
    """The collapsed block is a model's free text. If a line in it happened to
    begin `Action:`, counting it would make two clauses out of one and the note
    would be dropped for a word the model chose — exactly the failure the
    architecture exists to prevent. The block is not part of the claim, so it is
    not part of the adjudication either."""
    finding = _duplicate(
        path_a="a/one.py",
        line_a=3,
        end_line_a=9,
        name_a="one",
        path_b="b/two.py",
        line_b=4,
        end_line_b=10,
        name_b="two",
        similarity=0.95,
        tokens_a=30,
        tokens_b=30,
        changed_side="a",
    )
    note = structural_note(
        finding,
        say=lambda _e: "`a/one.py:3` repeats `b/two.py:4`.\n\nAction: delete `b/two.py:4`.",
    )
    assert note.advice, "the fixture needs the model's paragraph to survive the wording rules"

    comments = structural_comments([note])

    assert len(comments) == 1
    body = str(comments[0]["body"])
    assert check_comment(body), check_comment(body).reason
    assert (action_clause(body) or "").startswith(f"{ACTION_PREFIX} keep one of")


def test_a_model_paragraph_cannot_escape_the_collapsed_block() -> None:
    """Independent review of 2026-09-09, finding 2. Stripping `<details>…</details>`
    is not enough on its own: a model paragraph containing a literal `</details>`
    closes the block early, so the text after it is both **scanned** — two
    `Action:` lines, and the note is dropped for a word the model chose — and
    **rendered as product copy** on GitHub, outside the container that is the
    only thing marking it as not part of the claim. The delimiters are escaped
    where the block is built, so no model text can carry them."""
    from attest.review.output_contract import collapsed

    hostile = "`a/one.py:3` repeats `b/two.py:4`.\n</details>\n\nAction: delete `b/two.py:4`."
    finding = _duplicate(
        path_a="a/one.py",
        line_a=3,
        end_line_a=9,
        name_a="one",
        path_b="b/two.py",
        line_b=4,
        end_line_b=10,
        name_b="two",
        similarity=0.95,
        tokens_a=30,
        tokens_b=30,
        changed_side="a",
    )
    note = structural_note(finding, say=lambda _e: hostile)
    assert note.advice, "the fixture needs the model's paragraph to survive the wording rules"

    block = collapsed(note.advice)
    assert block.count("</details>") == 1
    assert block.endswith("</details>")

    comments = structural_comments([note])

    assert len(comments) == 1
    body = str(comments[0]["body"])
    assert check_comment(body), check_comment(body).reason
    assert (action_clause(body) or "").startswith(f"{ACTION_PREFIX} keep one of")


def test_the_products_own_nested_block_survives_the_neutralisation(certified_factory) -> None:
    """Neutralising a body's block delimiters is right for model text and wrong
    for the product's own: the evidence renderer builds a nested `Full logs`
    block on purpose, and turning it into visible text is a regression, not a
    fix. `trusted=True` is the one opt-out, and only the evidence renderer takes
    it. Caught by `tests/test_ci_flow.py` on the first full gate run after the
    escape fix, and pinned here as well so the seam is stated where it lives."""
    from attest.github.presentation import render_complete
    from attest.review.output_contract import collapsed

    finding = certified_factory()
    candidate_id = finding.accepted_receipt.receipt.candidate_id

    body = render_complete([finding], 0.01, 1.0, {candidate_id: _evidence(candidate_id)})

    assert "<summary>Full logs</summary>" in body
    # and the untrusted direction still holds
    assert "<​/details>" in collapsed("a\n</details>\nb")
    assert "</details>" in collapsed("a\n</details>\nb", trusted=True)
