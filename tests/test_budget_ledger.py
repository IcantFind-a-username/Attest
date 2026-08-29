import pytest

from attest.review.budget import Budget, BudgetExceeded
from attest.review.ledger import Ledger


def test_budget_estimate_and_reserve_settle() -> None:
    b = Budget(limit_usd=0.25, model="claude-sonnet-5")
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
    b = Budget(limit_usd=0.01, model="claude-sonnet-5")
    with pytest.raises(BudgetExceeded) as exc:
        b.reserve("big", 300000, 2000)
    assert "exceeds budget" in exc.value.reason


def test_budget_cancel_releases_reservation() -> None:
    b = Budget(limit_usd=0.25, model="claude-sonnet-5")
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


def test_tighten_floor(tmp_path) -> None:
    led = Ledger(tmp_path)
    for i in range(20):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "dismiss")
    alpha = 0.1
    for _ in range(6):
        alpha, _ = led.maybe_tighten_alpha(alpha, enabled=True)
    assert alpha == 0.01  # floored


def test_good_precision_no_tighten(tmp_path) -> None:
    led = Ledger(tmp_path)
    for i in range(20):
        fid = f"f{i}"
        led.record_review("t", fid, ["S"], 0.0, 12.0, "surface")
        led.record_feedback(fid, "good" if i < 19 else "dismiss")
    alpha, note = led.maybe_tighten_alpha(0.1, enabled=True)
    assert alpha == 0.1 and note is None
