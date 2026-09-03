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
