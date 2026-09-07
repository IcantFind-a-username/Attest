"""Owner item 6 (2026-09-03): a run status that is readable on a silent run."""

from __future__ import annotations

from attest.review.status import categorise_failure, status_from_rows


def _rows() -> list[dict[str, object]]:
    return [
        {"kind": "review_plan", "task_id": "t1", "units": [{"unit_id": "u1"}, {"unit_id": "u2"}]},
        {"kind": "eligibility", "task_id": "t1", "finding_id": "a", "eligibility": "regression"},
        {"kind": "eligibility", "task_id": "t1", "finding_id": "b", "eligibility": "regression"},
        {"kind": "eligibility", "task_id": "t1", "finding_id": "c", "eligibility": "new_code"},
        {
            "kind": "verification",
            "task_id": "t1",
            "finding_id": "a",
            "outcome": "deferred",
            "reason": (
                "generation failed: GenerationNoText: generation_no_text "
                "(stop_reason=max_tokens, blocks=thinking)"
            ),
        },
        {
            "kind": "verification",
            "task_id": "t1",
            "finding_id": "b",
            "outcome": "deferred",
            "reason": "unfaithful generated test: fails on base as well",
        },
        {"kind": "certification", "task_id": "t1", "finding_id": "a", "outcome": "not_attempted"},
        {"kind": "publication_policy", "task_id": "t1", "published": []},
        {"kind": "verification", "task_id": "other", "finding_id": "z", "outcome": "reproduced"},
    ]


def test_silent_run_status_names_counts_and_every_failure_reason() -> None:
    status = status_from_rows(_rows(), "t1")
    assert (status.units_read, status.candidates, status.eligible) == (2, 3, 2)
    assert (status.attempts, status.certified, status.published) == (2, 0, 0)
    assert [category for category, _ in status.failures] == ["no text returned", "unfaithful test"]
    text = status.render()
    assert "candidates: 3" in text
    assert "reproduction 1: no text returned" in text
    assert "reproduction 2: unfaithful test" in text
    collapsed = status.render_collapsed()
    assert collapsed.startswith("<details>") and "<summary>Run status</summary>" in collapsed
    # never the content or location of an uncertified candidate
    for forbidden in ("a", "b", "c"):
        assert f"finding {forbidden}" not in text


def test_failure_categories_cover_the_named_causes() -> None:
    assert categorise_failure("generation failed: generation_no_text (...)") == "no text returned"
    assert (
        categorise_failure("unfaithful generated test: fails on base as well") == "unfaithful test"
    )
    assert categorise_failure("head run 1/3 deferred: ModuleNotFoundError: x") == (
        "environment or import failure"
    )
    assert categorise_failure("reproduction timed out after 60s") == "timeout"
    assert categorise_failure("binding: the reproduction exercises none of the changed lines") == (
        "changed lines not executed"
    )
    assert categorise_failure("collection deferred: pytest collection failure") == (
        "collection failure"
    )


def test_status_reports_prompt_tokens_and_cache_reads() -> None:
    rows = [
        {
            "kind": "review_run",
            "task_id": "t1",
            "provider_samples": [
                {
                    "input_tokens": 100,
                    "cache_creation_input_tokens": 900,
                    "cache_read_input_tokens": 0,
                },
                {
                    "input_tokens": 100,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 900,
                },
            ],
        }
    ]
    status = status_from_rows(rows, "t1")
    assert (status.prompt_tokens, status.cache_read_input_tokens) == (2000, 900)
    assert "cache_read_input_tokens: 900" in status.render()


def test_a_budget_limited_run_says_how_many_units_it_read_of_how_many() -> None:
    """E-04 next stratum: a silence bought by the per-unit budget says so.

    Without the proposal's own coverage row the status reported the planned
    unit count as "change units read", so a 13-unit commit whose budget funded
    one unit read as if all thirteen had been reviewed.

    Owner instruction 5 of 2026-09-04: the "of M" is now unconditional. A
    silence covers exactly the units it read, and "read 1 of 13" and "read 13 of
    13" are different claims the reader cannot tell apart from a bare count;
    only the "budget-limited" suffix depends on what stopped the run.
    """
    rows = _rows() + [
        {
            "kind": "proposal_coverage",
            "task_id": "t1",
            "units_planned": 13,
            "units_read": 1,
            "budget_limited": True,
        }
    ]
    status = status_from_rows(rows, "t1")
    assert (status.units_read, status.units_planned, status.budget_limited) == (1, 13, True)
    assert "read 1 of 13 units, budget-limited" in status.render()
    # a run the budget did not stop still says how much of the change it read
    unlimited = status_from_rows(_rows(), "t1").render()
    assert "budget-limited" not in unlimited
    assert "read 2 of 2 units" in unlimited


def test_a_timed_out_image_build_is_categorised_as_a_bootstrap_failure() -> None:
    """The timeout reason contains both 'environment bootstrap failed' and
    'timed out'; only the order of the checks keeps it out of the 'timeout'
    bucket, which has no row in failure-modes.md and which the operator reads
    as 'the reproduction timed out' rather than 'the environment could not be
    built'. Reordering those two lines must fail here."""
    reason = (
        "isolation backend unavailable: environment bootstrap failed "
        "(python 3.10, roots ['.']): the image build timed out after 1800 s"
    )
    assert categorise_failure(reason) == "environment bootstrap failed"


def test_a_bootstrap_reason_keeps_the_build_log_tail_the_docs_promise() -> None:
    """`failure-modes.md` tells the operator to read the build log's tail in the
    run status. The 200-character bound, minus the 31-character
    `isolation backend unavailable: ` prefix, delivered about 9% of the
    1,200-character tail the bootstrap attaches -- so the code implied far more
    than it showed (2026-09-03 backlog, D-105 review finding 7)."""
    from attest.review.status import (
        BOOTSTRAP_REASON_LIMIT,
        REASON_LIMIT,
        _bounded,
    )

    tail = "ERROR: could not build wheels for numpy " * 40
    bootstrap = f"isolation backend unavailable: environment bootstrap failed (python 3.12): {tail}"
    ordinary = f"pytest passed on head: {tail}"

    kept = _bounded(bootstrap)
    assert len(kept) == BOOTSTRAP_REASON_LIMIT
    assert kept.count("could not build wheels") > 25, "the tail is still mostly gone"

    assert len(_bounded(ordinary)) == REASON_LIMIT
    assert REASON_LIMIT < BOOTSTRAP_REASON_LIMIT

    short = "isolation backend unavailable: docker not found"
    assert _bounded(short) == short


def test_a_host_that_cannot_run_the_executor_is_counted_and_named() -> None:
    """D-177. Every candidate was refused before generation because the host
    cannot run the declared executor profile, so none was judged. The status
    carries the count and the reason so the silence line can say which of the
    two silences this is."""
    rows: list[dict[str, object]] = [
        {"kind": "review_plan", "task_id": "t2", "units": [{"unit_id": "u1"}]},
        *(
            {
                "kind": "eligibility",
                "task_id": "t2",
                "finding_id": name,
                "eligibility": "unsupported_executor",
                "reason": "process containment unavailable: running as uid 0",
            }
            for name in ("a", "b", "c")
        ),
    ]

    status = status_from_rows(rows, "t2")

    assert status.unsupported_executor == 3
    assert status.executor_unavailable == "process containment unavailable: running as uid 0"
    assert status.eligible == 0


def test_a_healthy_run_claims_no_executor_problem() -> None:
    status = status_from_rows(_rows(), "t1")
    assert status.unsupported_executor == 0
    assert status.executor_unavailable == ""


def test_a_candidate_counted_once_however_many_rows_it_wrote() -> None:
    """Independent review of 2026-09-09, finding 5. `candidates` and `eligible`
    are sets of finding ids; the blocked count was a list of rows, so a task with
    a duplicated eligibility row would publish `4 candidate(s) not verified`
    beside a collapsed status saying `candidates: 2`. Two numbers about the same
    thing must not disagree."""
    row = {
        "kind": "eligibility",
        "task_id": "t3",
        "eligibility": "unsupported_executor",
        "reason": "process containment unavailable for privileged POSIX user",
    }
    rows: list[dict[str, object]] = [
        {"kind": "review_plan", "task_id": "t3", "units": [{"unit_id": "u1"}]},
        {**row, "finding_id": "a"},
        {**row, "finding_id": "b"},
        {**row, "finding_id": "a"},
        {**row, "finding_id": "b"},
    ]

    status = status_from_rows(rows, "t3")

    assert status.candidates == 2
    assert status.unsupported_executor == 2


def test_a_long_executor_reason_cannot_push_the_silence_line_past_the_contract() -> None:
    """Independent review of 2026-09-09, finding 6. `_bounded` allows 1,400
    characters when the text carries a bootstrap marker, and an executor reason
    is exactly the register that could grow one. The line the reader gets is
    bounded independently of that."""
    from attest.review.output_contract import MAX_LINE_CHARS, check, silence_line

    rows: list[dict[str, object]] = [
        {"kind": "review_plan", "task_id": "t4", "units": [{"unit_id": "u1"}]},
        {
            "kind": "eligibility",
            "task_id": "t4",
            "finding_id": "a",
            "eligibility": "unsupported_executor",
            "reason": "isolation backend unavailable: " + "x" * 2000,
        },
    ]

    status = status_from_rows(rows, "t4")
    line = silence_line(
        units_read=status.units_read,
        units_planned=status.units_planned,
        spend_usd=0.0,
        elapsed_s=1.0,
        executor_unavailable=status.executor_unavailable,
        unverified=status.unsupported_executor,
    )

    assert len(line) <= MAX_LINE_CHARS
    assert check(line), check(line).reason


# --- the trade a truncation cost, on the path an author reads (D-187) ------
# PR #14 of this repository is why this exists. Its own review read 3 of 16
# units and the status said `read 3 of 16 units, budget-limited` and nothing
# else -- on the very branch that recorded the owner's decision to *name* the
# trade when the ceiling actually bites. The clause was in the local report's
# notes and reached no author.


def _coverage(**over: object) -> dict[str, object]:
    row: dict[str, object] = {
        "kind": "proposal_coverage",
        "task_id": "t1",
        "units_planned": 16,
        "units_read": 3,
        "budget_limited": True,
    }
    row.update(over)
    return row


def test_a_truncated_run_says_which_unit_and_what_would_have_read_it() -> None:
    shortfall = (
        "unit u4 (src/attest/review/executor.py) was $0.0218 short of the discovery "
        "share; `budget-usd` $1.08 would have read it"
    )
    status = status_from_rows(_rows() + [_coverage(budget_shortfall=shortfall)], "t1")

    line = status.render()
    assert "read 3 of 16 units, budget-limited (" in line
    assert "src/attest/review/executor.py" in line  # which unit
    assert "$0.0218 short" in line  # how much
    assert "$1.08 would have read it" in line  # and the input that closes it


def test_a_run_the_ceiling_did_not_stop_carries_no_budget_clause() -> None:
    """No standing declaration: a review that fit says nothing about money."""
    status = status_from_rows(_rows(), "t1")

    assert status.budget_shortfall == ""
    assert "short of the discovery share" not in status.render()


def test_a_truncation_without_a_clause_still_renders_the_old_line() -> None:
    """A ledger written before D-187 carries no clause, and the status reads
    exactly as it did then rather than printing an empty bracket."""
    status = status_from_rows(_rows() + [_coverage()], "t1")

    assert "read 3 of 16 units, budget-limited;" in status.render()
    assert "()" not in status.render()


def test_a_long_unit_label_cannot_push_the_status_line_past_what_is_read() -> None:
    """The clause sits inside the first status line, which the silence contract
    bounds. A unit label long enough to overrun it is truncated."""
    from attest.review.status import BUDGET_SHORTFALL_LIMIT

    status = status_from_rows(_rows() + [_coverage(budget_shortfall="x" * 4000)], "t1")

    first_line = status.render().splitlines()[0]
    assert first_line.count("x") == BUDGET_SHORTFALL_LIMIT
    assert first_line.endswith(")") or "; candidates:" in first_line
