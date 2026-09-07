from pathlib import Path
from types import SimpleNamespace

import pytest

from attest.review.budget import Budget, BudgetExceeded
from attest.review.config import load_pricing
from attest.review.ledger import Ledger

DEFAULT_MODEL = str(load_pricing()["default_model"])


def test_budget_estimate_and_reserve_settle() -> None:
    b = Budget(limit_usd=0.25, model=DEFAULT_MODEL)
    # 3000 chars -> 1000 tokens in at $2/M plus 2000 out at $10/M
    est = b.estimate_cost(3000, 2000)
    assert est == pytest.approx(1000 * 2e-6 + 2000 * 10e-6)
    r = b.reserve("s0", 3000, 2000)
    assert b.reserved_usd == pytest.approx(r)
    actual = b.settle("s0", r, input_tokens=900, output_tokens=300)
    assert actual == pytest.approx(900 * 2e-6 + 300 * 10e-6)
    assert b.reserved_usd == 0.0
    assert b.spent_usd == pytest.approx(actual)
    assert b.calls[0]["label"] == "s0"


def test_budget_defers_before_calling() -> None:
    b = Budget(limit_usd=0.01, model=DEFAULT_MODEL)
    with pytest.raises(BudgetExceeded) as exc:
        b.reserve("big", 300000, 2000)
    assert "exceeds budget" in exc.value.reason


# --- what a real truncation says (D-187) -----------------------------------
# The 2026-09-10 K=5 run lost the `click` receipt to the discovery ceiling:
# `projected total $0.3218 exceeds the discovery share $0.3000`. Both numbers
# were printed and nothing told the operator that the gap was two cents, or
# that raising one input would have bought the finding back. The owner kept
# `budget-usd` at $1.00 and the factory `samples` at 5 and asked for the trade
# to be *named* when the ceiling actually bites -- and only then.


def test_a_truncation_names_the_gap_and_the_budget_that_would_have_covered_it() -> None:
    from attest.review.budget import PROPOSAL_SHARE
    from attest.review.proposer import budget_shortfall_note

    b = Budget(limit_usd=1.00, model=DEFAULT_MODEL)
    b.spent_usd = 0.28
    with b.stage("discovery", PROPOSAL_SHARE), pytest.raises(BudgetExceeded) as caught:
        b.reserve("proposal sample 4", 60000, 2000)

    note = budget_shortfall_note(caught.value)
    assert "$0.0400 short" in note
    # $0.34 projected against a 30% share is $1.13 of budget, not $1.04: the
    # ceiling is a share, so the shortfall and the budget that covers it are
    # different numbers and quoting the first as the second is the mistake
    # this line exists to avoid
    assert "`budget-usd` $1.13 would have bought it" in note
    assert caught.value.shortfall_usd == pytest.approx(0.04)
    assert caught.value.budget_usd_needed == pytest.approx(0.34 / PROPOSAL_SHARE)


def test_a_run_that_fits_says_nothing_about_the_budget() -> None:
    """No standing declaration: the clause exists only on the raise, so a review
    the ceiling never touched carries no budget sentence at all."""
    from attest.review.budget import PROPOSAL_SHARE

    b = Budget(limit_usd=1.00, model=DEFAULT_MODEL)
    with b.stage("discovery", PROPOSAL_SHARE):
        b.reserve("proposal sample 0", 3000, 2000)

    assert b.calls == []  # a reservation is not a call, and nothing was said
    assert b.reserved_usd > 0.0


def test_a_shortfall_without_a_ceiling_keeps_the_bare_reason() -> None:
    """An exception built by a caller rather than by the ceiling comparison has
    no numbers to quote, and inventing them would be worse than silence."""
    from attest.review.proposer import budget_shortfall_note

    assert budget_shortfall_note(BudgetExceeded("driver stopped at the reservation")) == (
        "driver stopped at the reservation"
    )


def test_budget_cancel_releases_reservation() -> None:
    b = Budget(limit_usd=0.25, model=DEFAULT_MODEL)
    r = b.reserve("s0", 3000, 2000)
    b.cancel(r)
    assert b.reserved_usd == 0.0
    assert b.spent_usd == 0.0


def test_budget_unknown_model_rejected() -> None:
    with pytest.raises(ValueError):
        Budget(limit_usd=0.25, model="not-a-model")


@pytest.mark.parametrize("limit", (float("nan"), float("inf"), float("-inf"), True, 0.0))
def test_budget_rejects_nonfinite_boolean_or_nonpositive_limit(limit: object) -> None:
    with pytest.raises(ValueError, match="limit"):
        Budget(limit_usd=limit, model=DEFAULT_MODEL)  # type: ignore[arg-type]


def test_ledger_roundtrip(tmp_path) -> None:
    led = Ledger(tmp_path)
    led.record_review("t1", "f1", ["S", "T"], 0.05, 5.3, "drawer")
    led.record_feedback("f1", "good")
    entries = led.entries()
    assert len(entries) == 2
    assert entries[0]["kind"] == "review"
    assert entries[0]["channels_bought"] == ["S", "T"]
    assert entries[1]["feedback"] == "good"
    assert (tmp_path / ".attest" / "ledger.jsonl").is_file()


def test_ledger_bad_feedback_rejected(tmp_path) -> None:
    led = Ledger(tmp_path)
    with pytest.raises(ValueError):
        led.record_feedback("f1", "meh")


def test_feedback_label_polarity_recorded(tmp_path) -> None:
    """Every accepted label carries a derived polarity so downstream
    consumers never have to re-derive the fix/good/wrong/wontfix/dismiss
    mapping themselves."""
    led = Ledger(tmp_path)
    expected_polarity = {
        "fix": "true",
        "good": "true",
        "wontfix": "true",
        "wrong": "false",
        "dismiss": "ambiguous",  # legacy, ambiguous polarity
    }
    for label in expected_polarity:
        led.record_feedback(f"f-{label}", label)
    by_finding = {e["finding_id"]: e for e in led.entries()}
    for label, polarity in expected_polarity.items():
        entry = by_finding[f"f-{label}"]
        assert entry["feedback"] == label
        assert entry["label_polarity"] == polarity


@pytest.mark.parametrize(
    ("feedback", "recorded"), (("wrong", "true"), ("wrong", "unknown"))
)
def test_feedback_label_polarity_must_be_exact_and_consistent(
    tmp_path: Path, feedback: str, recorded: str
) -> None:
    led = Ledger(tmp_path)
    led.record_review("t", "f", ["S"], 0.0, 12.0, "surface")
    led.append(
        {
            "kind": "feedback",
            "finding_id": "f",
            "feedback": feedback,
            "label_polarity": recorded,
        }
    )

    with pytest.raises(ValueError, match="label_polarity"):
        led.surfaced_precision()


def test_unknown_legacy_feedback_cannot_erase_a_false_label(tmp_path: Path) -> None:
    led = Ledger(tmp_path)
    led.record_review("t", "f", ["S"], 0.0, 12.0, "surface")
    led.record_feedback("f", "wrong")
    led.append({"kind": "feedback", "finding_id": "f", "feedback": "wron"})

    with pytest.raises(ValueError, match="feedback label"):
        led.surfaced_precision()


def test_precision_excludes_legacy_dismiss_from_denominator(tmp_path) -> None:
    """Legacy `dismiss` rows are polarity-ambiguous and must be excluded from
    BOTH the numerator and the denominator of surfaced precision -- never
    silently counted as either a true or a false label."""
    led = Ledger(tmp_path)
    labels = ["fix", "good", "wontfix", "wrong", "dismiss"]
    for i, label in enumerate(labels):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, label)
    precision, n = led.surfaced_precision()
    # dismiss (ambiguous) excluded entirely: denominator is 4, not 5
    assert n == 4
    assert precision == pytest.approx(3 / 4)  # fix, good, wontfix true; wrong false


def test_surfaced_precision_and_tighten(tmp_path) -> None:
    led = Ledger(tmp_path)
    # 12 surfaced findings: 8 good, 4 genuinely wrong -> precision 0.667 < 0.9
    for i in range(12):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "good" if i < 8 else "wrong")
    precision, n = led.surfaced_precision()
    assert n == 12
    assert precision == pytest.approx(8 / 12)
    new_alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert new_alpha == 0.05
    assert note is not None
    # the tightening is recorded and current_alpha follows the chain
    assert led.current_alpha(0.1) == 0.05


def test_precision_state_changes_but_not_duplicate_polarity_advance_watermark(
    tmp_path: Path,
) -> None:
    led = Ledger(tmp_path)
    for index in range(12):
        finding_id = f"f{index}"
        led.record_review("t", finding_id, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(finding_id, "good" if index < 8 else "wrong")
    alpha, _note = led.maybe_tighten_alpha(0.1, enabled=True)
    led.record_feedback("f0", "good")
    assert led.maybe_tighten_alpha(alpha, enabled=True) == (0.05, None)

    led.record_feedback("f0", "wrong")
    tightened, note = led.maybe_tighten_alpha(alpha, enabled=True)
    assert tightened == 0.025 and note is not None


def test_wrong_ambiguous_wrong_each_changes_precision_state(tmp_path: Path) -> None:
    led = Ledger(tmp_path)
    for index in range(12):
        finding_id = f"f{index}"
        led.record_review("t", finding_id, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(finding_id, "wrong")
    alpha, _note = led.maybe_tighten_alpha(0.1, enabled=True)

    led.record_feedback("f0", "dismiss")
    alpha, note = led.maybe_tighten_alpha(alpha, enabled=True)
    assert alpha == 0.025 and note is not None
    led.record_feedback("f0", "wrong")
    alpha, note = led.maybe_tighten_alpha(alpha, enabled=True)
    assert alpha == 0.0125 and note is not None


def test_watermark_ignores_label_changes_outside_the_precision_window(
    tmp_path: Path,
) -> None:
    led = Ledger(tmp_path)
    for index in range(60):
        finding_id = f"f{index}"
        led.record_review("t", finding_id, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(finding_id, "good" if index < 50 else "wrong")
    alpha, _note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert led.surfaced_precision() == (pytest.approx(0.8), 50)

    led.record_feedback("f0", "wrong")

    assert led.surfaced_precision() == (pytest.approx(0.8), 50)
    assert led.maybe_tighten_alpha(alpha, enabled=True) == (0.05, None)


def test_watermark_tracks_surface_changes_to_the_precision_window(
    tmp_path: Path,
) -> None:
    led = Ledger(tmp_path)
    for index in range(60):
        finding_id = f"f{index}"
        led.record_review("t", finding_id, ["S"], 0.0, 12.0, "surface")
        label = "wrong" if index < 10 or index >= 50 else "good"
        led.record_feedback(finding_id, label)
    alpha, _note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert led.surfaced_precision() == (pytest.approx(0.8), 50)

    for index in range(10):
        led.record_review("repeat", f"f{index}", ["S"], 0.0, 12.0, "surface")

    assert led.surfaced_precision() == (pytest.approx(0.6), 50)
    tightened, note = led.maybe_tighten_alpha(alpha, enabled=True)
    assert tightened == 0.025 and note is not None


def test_feedback_before_first_surface_is_not_a_precision_label(tmp_path: Path) -> None:
    led = Ledger(tmp_path)
    for index in range(10):
        finding_id = f"f{index}"
        led.record_feedback(finding_id, "wrong")
        led.record_review("t", finding_id, ["S"], 0.0, 12.0, "surface")

    assert led.surfaced_precision() == (None, 0)
    assert led.maybe_tighten_alpha(0.1, enabled=True) == (0.1, None)


@pytest.mark.parametrize(
    "malformed",
    (
        {"kind": "review", "finding_id": "phantom", "action": "surface"},
        {"kind": "github_comment", "task_id": "legacy"},
        {
            "kind": "github_comment",
            "task_id": "task",
            "phase": "unknown",
            "outcome": "posted",
        },
        {
            "kind": "github_comment",
            "task_id": "task",
            "phase": "review",
            "outcome": "failed",
        },
        {
            "kind": "github_comment",
            "task_id": "task",
            "phase": "review",
            "outcome": "posted",
            "reason": "not allowed on success",
        },
        {
            "kind": "ci_final",
            "task_id": "task",
            "decisions": [None],
            "spend_usd": 0.0,
        },
        {
            "kind": "review",
            "task_id": "legacy",
            "finding_id": "phantom",
            "channels_bought": ["X"],
            "spend": 0.0,
            "wealth_final": 12.0,
            "action": "surface",
        },
        {
            "kind": "review",
            "task_id": "legacy",
            "finding_id": "phantom",
            "channels_bought": ["S", "S"],
            "spend": 0.0,
            "wealth_final": 12.0,
            "action": "surface",
        },
        {
            "kind": "review",
            "task_id": "legacy",
            "finding_id": "phantom",
            "channels_bought": [],
            "spend": 0.0,
            "wealth_final": 12.0,
            "action": "surface",
        },
    ),
)
def test_malformed_surface_authority_rows_fail_closed(
    tmp_path: Path, malformed: dict[str, object]
) -> None:
    led = Ledger(tmp_path)
    led.append(malformed)

    with pytest.raises(ValueError):
        led.surfaced_precision()


@pytest.mark.parametrize("window", (0, -1, True, False, 1.0))
def test_precision_window_must_be_an_exact_positive_integer(
    tmp_path: Path, window: object
) -> None:
    with pytest.raises(ValueError, match="precision window"):
        Ledger(tmp_path).surfaced_precision(window=window)  # type: ignore[arg-type]


def test_current_precision_rejects_a_truncated_ledger(tmp_path: Path) -> None:
    led = Ledger(tmp_path)
    led.record_review("t", "f", ["S"], 0.0, 12.0, "surface")
    with led.path.open("ab") as stream:
        stream.write(b'{"kind":"feedback"')

    with pytest.raises(ValueError, match="truncated"):
        led.surfaced_precision()


# --- a note is not a receipt, in the delivery journal either (D-189) -------
# Found by the 2026-09-11 held-out re-run: `pytest-dev__pytest-10356` could not
# be reviewed at all. `run_review` raised `ValueError: delivery member does not
# match its ci_final surface decision` before buying anything, because the
# 2026-09-10 review of the same case posted a **yellow (a) note and no receipt**
# and journalled the note as a delivery member -- `{"finding_id":
# "src/_pytest/mark/structures.py:358", "placement": "impact"}`. `ci_final`
# records candidate decisions and knows nothing about a coordinate, so the
# reconciliation refused the row on the *next* review of that repository.
#
# The guard is right and stays: a coordinate must never reach `surfaced_ids`,
# which is what the alpha auto-tighten's precision window reads (D-048). What
# was wrong is that a note member was reconciled at all.


def _note_member_ledger(tmp_path: Path) -> "Ledger":
    """A repository whose last review posted one yellow (a) note and no receipt."""
    led = Ledger(tmp_path)
    led.record_ci_final(
        task_id="notes",
        decisions=[
            {
                "finding_id": "5e019fccef",
                "action": "drawer",
                "wealth_final": 3.0,
                "placement": "drawer",
            }
        ],
        spend_usd=0.0,
    )
    led.append(
        {
            "kind": "delivery_attempt_settlement",
            "task_id": "notes",
            "attempt_id": "note-attempt",
            "outcome": "succeeded",
        }
    )
    return led


def test_a_note_member_does_not_make_the_next_review_of_that_repository_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    led = _note_member_ledger(tmp_path)
    event = SimpleNamespace(
        attempt_id="note-attempt",
        outcome="succeeded",
        members=(("src/_pytest/mark/structures.py:358", "impact"),),
    )
    monkeypatch.setattr(
        "attest.review.ci.reconcile_delivery_rows",
        lambda _entries, task_id: ((event,), ()) if task_id == "notes" else ((), ()),
    )

    # the review that reads this ledger must run, and the coordinate must not be
    # counted as something an author was shown a receipt for
    assert led.maybe_tighten_alpha(0.1, enabled=True) == (0.1, None)
    assert list(led.surfaced_finding_ids()) == []


def test_a_receipt_member_is_still_reconciled_against_its_ci_final_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The other side: excluding notes must not stop the guard from refusing an
    *inline* member the ci_final row never decided to surface."""
    led = _note_member_ledger(tmp_path)
    event = SimpleNamespace(
        attempt_id="note-attempt",
        outcome="succeeded",
        members=(("5e019fccef", "inline"),),  # ci_final drawered it
    )
    monkeypatch.setattr(
        "attest.review.ci.reconcile_delivery_rows",
        lambda _entries, task_id: ((event,), ()) if task_id == "notes" else ((), ()),
    )

    with pytest.raises(ValueError, match="ci_final surface decision"):
        led.maybe_tighten_alpha(0.1, enabled=True)


def test_a_delivery_member_placement_nobody_defines_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A placement that is neither a receipt's nor a note's is a shape this
    reader does not understand, and it refuses rather than guessing which."""
    led = _note_member_ledger(tmp_path)
    event = SimpleNamespace(
        attempt_id="note-attempt",
        outcome="succeeded",
        members=(("whatever", "a-placement-from-the-future"),),
    )
    monkeypatch.setattr(
        "attest.review.ci.reconcile_delivery_rows",
        lambda _entries, task_id: ((event,), ()) if task_id == "notes" else ((), ()),
    )

    with pytest.raises(ValueError, match="delivery member placement"):
        led.maybe_tighten_alpha(0.1, enabled=True)


def test_ci_surface_order_is_anchored_to_successful_settlement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    led = Ledger(tmp_path)
    ci_ids = tuple(f"ci-{index}" for index in range(6))
    led.record_ci_final(
        task_id="ci",
        decisions=[
            {
                "finding_id": finding_id,
                "action": "surface",
                "wealth_final": 12.0,
                "placement": "inline",
            }
            for finding_id in ci_ids
        ],
        spend_usd=0.0,
    )
    for index in range(50):
        finding_id = f"legacy-{index}"
        led.record_review("legacy", finding_id, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(finding_id, "good")
    led.append(
        {
            "kind": "delivery_attempt_settlement",
            "task_id": "ci",
            "attempt_id": "ci-attempt",
            "outcome": "succeeded",
        }
    )
    for finding_id in ci_ids:
        led.record_feedback(finding_id, "wrong")
    event = SimpleNamespace(
        attempt_id="ci-attempt",
        outcome="succeeded",
        members=tuple((finding_id, "inline") for finding_id in ci_ids),
    )
    monkeypatch.setattr(
        "attest.review.ci.reconcile_delivery_rows",
        lambda _entries, task_id: ((event,), ()) if task_id == "ci" else ((), ()),
    )

    assert led.surfaced_finding_ids()[-6:] == ci_ids
    assert led.surfaced_precision() == (pytest.approx(0.88), 50)
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert alpha == 0.05 and note is not None


def test_ci_surface_attempt_is_bound_to_its_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    led = Ledger(tmp_path)
    led.record_ci_final(
        task_id="task-a",
        decisions=[
            {
                "finding_id": "finding-a",
                "action": "surface",
                "wealth_final": 12.0,
                "placement": "inline",
            }
        ],
        spend_usd=0.0,
    )
    led.append(
        {
            "kind": "delivery_attempt_settlement",
            "task_id": "task-b",
            "attempt_id": "shared",
            "outcome": "succeeded",
        }
    )
    led.record_feedback("finding-a", "wrong")
    led.append(
        {
            "kind": "delivery_attempt_settlement",
            "task_id": "task-a",
            "attempt_id": "shared",
            "outcome": "succeeded",
        }
    )
    event = SimpleNamespace(
        attempt_id="shared",
        outcome="succeeded",
        members=(("finding-a", "inline"),),
    )
    monkeypatch.setattr(
        "attest.review.ci.reconcile_delivery_rows",
        lambda _entries, task_id: ((event,), ()) if task_id == "task-a" else ((), ()),
    )

    assert led.surfaced_finding_ids() == ("finding-a",)
    assert led.surfaced_precision() == (None, 0)


@pytest.mark.parametrize(
    "mutation",
    ("unknown_member", "wrong_placement", "duplicate_final", "late_final", "legacy_final"),
)
def test_delivery_must_match_one_prior_current_ci_final(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    led = Ledger(tmp_path)
    decision: dict[str, object] = {
        "finding_id": "expected",
        "action": "surface",
        "wealth_final": 12.0,
        "placement": "inline",
    }
    if mutation == "legacy_final":
        del decision["placement"]
    if mutation == "late_final":
        led.append({"kind": "delivery_attempt_intent", "task_id": "task"})
    led.record_ci_final(task_id="task", decisions=[decision], spend_usd=0.0)
    if mutation == "duplicate_final":
        led.record_ci_final(task_id="task", decisions=[decision], spend_usd=0.0)
    if mutation != "late_final":
        led.append({"kind": "delivery_attempt_intent", "task_id": "task"})
    member = (
        "unknown" if mutation == "unknown_member" else "expected",
        "overflow" if mutation == "wrong_placement" else "inline",
    )
    event = SimpleNamespace(
        attempt_id="attempt",
        outcome="succeeded",
        members=(member,),
    )
    monkeypatch.setattr(
        "attest.review.ci.reconcile_delivery_rows",
        lambda _entries, task_id: ((event,), ()) if task_id == "task" else ((), ()),
    )

    with pytest.raises(ValueError, match="ci_final|delivery member"):
        led.surfaced_finding_ids()


def test_wontfix_labels_do_not_tighten_alpha(tmp_path) -> None:
    """wontfix means the finding was CORRECT but not acted on: it must count
    as a true label for precision, not as a false positive."""
    led = Ledger(tmp_path)
    # same shape as test_surfaced_precision_and_tighten, but the 4 "bad"
    # labels are wontfix rather than wrong -> precision stays 1.0
    for i in range(12):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "good" if i < 8 else "wontfix")
    precision, n = led.surfaced_precision()
    assert n == 12
    assert precision == pytest.approx(1.0)
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert alpha == 0.1 and note is None


def test_tighten_disabled_or_insufficient(tmp_path) -> None:
    led = Ledger(tmp_path)
    for i in range(5):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "dismiss")
    # fewer than 10 labels: no tightening
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert alpha == 0.1 and note is None
    # disabled: no tightening regardless
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=False)
    assert alpha == 0.1 and note is None


def test_tighten_floor_with_fresh_labels_each_round(tmp_path) -> None:
    led = Ledger(tmp_path)
    for i in range(20):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "wrong")
    alpha = 0.1
    for round_ in range(6):
        alpha, _ = led.maybe_tighten_alpha(alpha, enabled=True)
        # fresh bad label between rounds keeps the watermark moving
        fid = f"extra{round_}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "wrong")
    assert alpha == 0.01  # floored


def test_tighten_watermark_blocks_stale_rehalving(tmp_path) -> None:
    """Regression: repeated review runs with ZERO new labels must not keep
    halving alpha on the same stale window."""
    led = Ledger(tmp_path)
    for i in range(12):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "wrong")
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert alpha == 0.05 and note is not None
    led.append(
        {
            "kind": "alpha_tightened",
            "from": 0.1,
            "to": 0.05,
            "label_count": 0,
            "note": "legacy row with semantically wrong label_count",
        }
    )
    # same stale window: no further tightening, run after run
    for _ in range(4):
        alpha, note = led.maybe_tighten_alpha(alpha, enabled=True)
        assert alpha == 0.05 and note is None

    stale = led.surfaced_precision()
    led.append(
        {
            "kind": "github_comment",
            "task_id": "current-ci",
            "phase": "running",
            "outcome": "posted",
        }
    )
    led.record_review("current-ci", "phantom", ["S"], 0.0, 12.0, "surface")
    led.record_feedback("phantom", "wrong")
    alpha, note = led.maybe_tighten_alpha(alpha, enabled=True)
    assert led.surfaced_precision() == stale
    assert alpha == 0.05 and note is None

    led.record_review("legacy", "fresh", ["S"], 0.0, 12.0, "surface")
    led.record_feedback("fresh", "wrong")
    alpha, note = led.maybe_tighten_alpha(alpha, enabled=True)
    assert alpha == 0.025 and note is not None


@pytest.mark.parametrize("bad_count", (True, -1, "12"))
def test_any_malformed_historical_label_count_fails_closed(
    tmp_path: Path, bad_count: object
) -> None:
    led = Ledger(tmp_path)
    for index in range(12):
        finding_id = f"f{index}"
        led.record_review("t", finding_id, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(finding_id, "wrong")
    led.append(
        {
            "kind": "alpha_tightened",
            "from": 0.1,
            "to": 0.05,
            "label_count": bad_count,
        }
    )
    led.append(
        {
            "kind": "alpha_tightened",
            "from": 0.05,
            "to": 0.025,
            "label_count": 12,
        }
    )
    led.record_review("t", "fresh", ["S"], 0.0, 12.0, "surface")
    led.record_feedback("fresh", "wrong")

    with pytest.raises(ValueError, match="label_count"):
        led.current_alpha(0.1)
    assert led.maybe_tighten_alpha(0.025, enabled=True) == (0.025, None)


def test_ambiguous_labels_do_not_advance_the_tighten_watermark(tmp_path) -> None:
    """Regression: legacy `dismiss` labels are excluded from surfaced precision,
    so they cannot move the figure that justifies a tightening. Counting them in
    the watermark let each one re-open the gate on an UNCHANGED precision
    figure, halving alpha again and again down to the floor on one stale window.
    """
    led = Ledger(tmp_path)
    # 12 labels, 8 good / 4 wrong -> precision 0.667 < 0.9
    for i in range(12):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "good" if i < 8 else "wrong")
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert alpha == 0.05 and note is not None
    stale = led.surfaced_precision()

    # ambiguous labels only: precision cannot move, so neither may alpha
    for i in range(3):
        fid = f"d{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "dismiss")
        alpha, note = led.maybe_tighten_alpha(alpha, enabled=True)
        assert led.surfaced_precision() == stale
        assert alpha == 0.05 and note is None

    # a label that CAN move precision still re-tightens, exactly as before
    led.record_review("t", "fresh", ["S"], 0.0, 12.0, "surface")
    led.record_feedback("fresh", "wrong")
    alpha, note = led.maybe_tighten_alpha(alpha, enabled=True)
    assert alpha == 0.025 and note is not None


def test_reverify_not_double_counted_in_precision(tmp_path) -> None:
    """Regression: repeated `attest verify` rows for one finding count once."""
    led = Ledger(tmp_path)
    led.record_review("t", "f1", ["S"], 0.0, 12.0, "surface")
    led.record_review("t", "f1", ["V"], 0.0, 60.0, "verified_surface")
    led.record_review("t", "f1", ["V"], 0.0, 60.0, "verified_surface")
    led.record_review("t", "f2", ["S"], 0.0, 12.0, "surface")
    led.record_feedback("f1", "wrong")
    led.record_feedback("f2", "good")
    precision, n = led.surfaced_precision()
    assert n == 2
    assert precision == pytest.approx(0.5)


def test_overflow_surface_counts_into_precision(tmp_path) -> None:
    """Regression: findings past the gate but beyond the cap-3 layout are
    spoken (drawer section) and must feed the precision loop."""
    led = Ledger(tmp_path)
    led.record_review("t", "f1", ["S"], 0.0, 12.0, "overflow_surface")
    led.record_feedback("f1", "good")
    precision, n = led.surfaced_precision()
    assert (precision, n) == (1.0, 1)


def test_good_precision_no_tighten(tmp_path) -> None:
    led = Ledger(tmp_path)
    for i in range(20):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "good" if i < 19 else "dismiss")
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert alpha == 0.1 and note is None


@pytest.mark.parametrize(
    ("outcome", "reason", "network_blocked", "evidence"),
    [
        (
            "reproduced",
            "pytest reported 1 failure(s) and 0 error(s)",
            True,
            "AssertionError: expected 4, got 5",
        ),
        ("not_reproduced", "pytest passed", True, "1 passed in 0.02s"),
        ("deferred", "reproduction timed out after 60s", True, "last output bytes"),
    ],
)
def test_record_verification_preserves_identity_and_evidence_without_changing_review(
    tmp_path,
    outcome: str,
    reason: str,
    network_blocked: bool,
    evidence: str,
) -> None:
    led = Ledger(tmp_path)
    led.record_review("task-9", "finding-a", ["S", "T"], 0.0123456, 8.12345, "drawer")

    led.record_verification(
        task_id="task-9",
        finding_id="finding-a",
        outcome=outcome,
        reason=reason,
        elapsed_s=1.23456789,
        network_blocked=network_blocked,
        evidence=evidence,
    )

    review, verification = led.entries()
    assert review == {
        "ts": review["ts"],
        "kind": "review",
        "task_id": "task-9",
        "finding_id": "finding-a",
        "channels_bought": ["S", "T"],
        "spend": 0.012346,
        "wealth_final": 8.1235,
        "action": "drawer",
    }
    assert verification == {
        "ts": verification["ts"],
        "kind": "verification",
        "task_id": "task-9",
        "finding_id": "finding-a",
        "outcome": outcome,
        "reason": reason,
        "elapsed_s": 1.234568,
        "network_blocked": network_blocked,
        "evidence": evidence,
    }


def test_ci_final_without_delivery_authority_is_not_surfaced_precision(
    tmp_path: Path,
) -> None:
    led = Ledger(tmp_path)
    led.record_review("task", "finding", [], 0.01, 4.0, "drawer")
    led.record_ci_final(
        task_id="task",
        decisions=[{"finding_id": "finding", "action": "surface", "wealth_final": 40.0}],
        spend_usd=0.02,
    )
    led.record_feedback("finding", "good")

    assert led.surfaced_precision() == (None, 0)


@pytest.mark.parametrize(
    ("current_ci", "surfaced_ids", "precision"),
    ((True, (), (None, 0)), (False, ("finding",), (1.0, 1))),
)
def test_only_current_ci_review_surface_requires_delivery_authority(
    tmp_path: Path,
    current_ci: bool,
    surfaced_ids: tuple[str, ...],
    precision: tuple[float | None, int],
) -> None:
    led = Ledger(tmp_path)
    if current_ci:
        led.append(
            {
                "kind": "github_comment",
                "task_id": "task",
                "phase": "running",
                "outcome": "posted",
            }
        )
    led.record_review("task", "finding", ["S"], 0.01, 40.0, "surface")
    led.record_feedback("finding", "good")

    assert led.surfaced_finding_ids() == surfaced_ids
    assert led.surfaced_precision() == precision


def test_surfaced_precision_discards_an_equal_tuple_subclass(tmp_path: Path) -> None:
    class ForgedPopulation(tuple[str, ...]):
        def __getitem__(self, key: object) -> object:
            if isinstance(key, slice):
                return ("f9",) * 10
            return super().__getitem__(key)  # type: ignore[index]

    led = Ledger(tmp_path)
    for index in range(10):
        finding_id = f"f{index}"
        led.record_review("t", finding_id, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(finding_id, "wrong" if index == 9 else "good")
    canonical = led.surfaced_finding_ids()
    forged = ForgedPopulation(canonical)
    assert forged == canonical

    assert led.surfaced_precision(surfaced_ids=forged) == (pytest.approx(0.9), 10)


@pytest.mark.parametrize("bad_to", (True, -1.0, float("nan")))
def test_current_alpha_rejects_malformed_transitions(
    tmp_path: Path, bad_to: object
) -> None:
    led = Ledger(tmp_path)
    led.append({"kind": "alpha_tightened", "from": 0.1, "to": bad_to})

    with pytest.raises(ValueError):
        led.current_alpha(0.1)


def test_current_alpha_accepts_exact_factory_chain(tmp_path: Path) -> None:
    led = Ledger(tmp_path)
    for start, end in ((0.1, 0.05), (0.05, 0.025), (0.025, 0.0125), (0.0125, 0.01)):
        led.append({"kind": "alpha_tightened", "from": start, "to": end})

    assert led.current_alpha(0.1) == 0.01


def test_current_alpha_ignores_a_valid_chain_for_another_configuration(
    tmp_path: Path,
) -> None:
    led = Ledger(tmp_path)
    led.append({"kind": "alpha_tightened", "from": 0.1, "to": 0.05})

    assert led.current_alpha(0.2) == 0.2


def test_auto_tighten_never_relaxes_alpha_below_the_floor(tmp_path: Path) -> None:
    led = Ledger(tmp_path)
    for index in range(12):
        finding_id = f"f{index}"
        led.record_review("t", finding_id, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(finding_id, "wrong")

    assert led.maybe_tighten_alpha(0.005, enabled=True) == (0.005, None)


def test_discovery_cannot_spend_more_than_its_share_of_the_review_budget() -> None:
    """D-111: on `d7be758` the proposal stage produced 12 candidates from a
    210-line change and left nine of eleven reproductions unable to afford a
    single generation attempt — the budget went to breadth, not to difficulty.
    Discovery is capped at PROPOSAL_SHARE of the limit, and what it does not
    spend stays available to verification.

    D-168 lowered the share from 0.6 to 0.3 on the 2026-09-07 measurement that
    four times the budget bought 3.2× the candidates and moved no verdict. The
    property is unchanged; the number is the owner's."""
    from attest.review.budget import PROPOSAL_SHARE

    b = Budget(limit_usd=1.00, model=DEFAULT_MODEL)
    assert PROPOSAL_SHARE == 0.3
    # 9 samples of 3,200 output tokens each: $0.032 apiece at $10/Mtok
    with b.stage("proposal", PROPOSAL_SHARE):
        for i in range(9):
            b.reserve(f"sample-{i}", 0, 3200)
        with pytest.raises(BudgetExceeded) as exc:
            b.reserve("sample-9", 0, 3200)
    assert "proposal share $0.3000" in exc.value.reason
    assert "budget $1.00" in exc.value.reason
    assert b.reserved_usd == pytest.approx(0.288)

    # outside the stage the rest of the budget is still reservable: the share
    # bounds discovery, it does not shrink the review
    for i in range(22):
        b.reserve(f"generation-{i}", 0, 3200)
    assert b.reserved_usd == pytest.approx(0.992)
    with pytest.raises(BudgetExceeded) as spent:
        b.reserve("generation-22", 0, 3200)
    assert "exceeds budget" in spent.value.reason
