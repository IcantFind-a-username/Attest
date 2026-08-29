from pathlib import Path

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


def test_budget_cancel_releases_reservation() -> None:
    b = Budget(limit_usd=0.25, model=DEFAULT_MODEL)
    r = b.reserve("s0", 3000, 2000)
    b.cancel(r)
    assert b.reserved_usd == 0.0
    assert b.spent_usd == 0.0


def test_budget_unknown_model_rejected() -> None:
    with pytest.raises(ValueError):
        Budget(limit_usd=0.25, model="not-a-model")


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


def test_surfaced_precision_and_tighten(tmp_path) -> None:
    led = Ledger(tmp_path)
    # 12 surfaced findings: 8 good, 4 dismissed -> precision 0.667 < 0.9
    for i in range(12):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "good" if i < 8 else "dismiss")
    precision, n = led.surfaced_precision()
    assert n == 12
    assert precision == pytest.approx(8 / 12)
    new_alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert new_alpha == 0.05
    assert note is not None
    # the tightening is recorded and current_alpha follows the chain
    assert led.current_alpha(0.1) == 0.05


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
        led.record_feedback(fid, "dismiss")
    alpha = 0.1
    for round_ in range(6):
        alpha, _ = led.maybe_tighten_alpha(alpha, enabled=True)
        # fresh bad label between rounds keeps the watermark moving
        fid = f"extra{round_}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "dismiss")
    assert alpha == 0.01  # floored


def test_tighten_watermark_blocks_stale_rehalving(tmp_path) -> None:
    """Regression: repeated review runs with ZERO new labels must not keep
    halving alpha on the same stale window."""
    led = Ledger(tmp_path)
    for i in range(12):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "dismiss")
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert alpha == 0.05 and note is not None
    # same stale window: no further tightening, run after run
    for _ in range(4):
        alpha, note = led.maybe_tighten_alpha(alpha, enabled=True)
        assert alpha == 0.05 and note is None


def test_reverify_not_double_counted_in_precision(tmp_path) -> None:
    """Regression: repeated `attest verify` rows for one finding count once."""
    led = Ledger(tmp_path)
    led.record_review("t", "f1", ["S"], 0.0, 12.0, "surface")
    led.record_review("t", "f1", ["V"], 0.0, 60.0, "verified_surface")
    led.record_review("t", "f1", ["V"], 0.0, 60.0, "verified_surface")
    led.record_review("t", "f2", ["S"], 0.0, 12.0, "surface")
    led.record_feedback("f1", "dismiss")
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


def test_final_ci_decisions_drive_surfaced_precision(tmp_path: Path) -> None:
    led = Ledger(tmp_path)
    led.record_review("task", "finding", [], 0.01, 4.0, "drawer")
    led.record_ci_final(
        task_id="task",
        decisions=[{"finding_id": "finding", "action": "surface", "wealth_final": 40.0}],
        spend_usd=0.02,
    )
    led.record_feedback("finding", "good")

    assert led.surfaced_precision() == (1.0, 1)
