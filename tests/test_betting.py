import pytest

from attest.core import Tables, decide, task_lr_canonical, task_lr_purchase_order


def _informative_tables() -> Tables:
    t = Tables()
    for _ in range(8):
        t.update(1, {"A": 1, "B": 1, "C": 1})
        t.update(0, {"A": 0, "B": 0, "C": 0})
    for _ in range(2):
        t.update(1, {"A": 0, "B": 0, "C": 0})
        t.update(0, {"A": 1, "B": 1, "C": 1})
    return t


def test_decide_thresholds() -> None:
    assert decide(10.0, 0.1) == 1  # boundary inclusive
    assert decide(10.1, 0.1) == 1
    assert decide(0.1, 0.1) == 0  # boundary inclusive
    assert decide(0.09, 0.1) == 0
    assert decide(9.99, 0.1) is None
    assert decide(1.0, 0.1) is None
    assert decide(0.11, 0.1) is None


def test_task_lr_orders_agree_on_full_purchase() -> None:
    t = _informative_tables()
    verdicts = {"A": 1, "B": 1, "C": 0}
    # chain rule: product over any order equals the same joint LR estimate only
    # when tables are consistent (built from full joint updates) — check the
    # canonical order equals explicit canonical purchase order.
    lr_canon = task_lr_canonical(t, verdicts)
    lr_po_same = task_lr_purchase_order(t, ["A", "B", "C"], verdicts)
    assert lr_canon == pytest.approx(lr_po_same)


def test_task_lr_canonical_skips_missing() -> None:
    t = _informative_tables()
    lr_ac = task_lr_canonical(t, {"A": 1, "C": 1})
    # manual: marginal A factor times C-given-A factor
    manual = t.lr_factor("A", {}, 1) * t.lr_factor("C", {"A": 1}, 1)
    assert lr_ac == pytest.approx(manual)


def test_task_lr_purchase_order_conditions_sequentially() -> None:
    t = _informative_tables()
    lr = task_lr_purchase_order(t, ["C", "A"], {"C": 1, "A": 1})
    manual = t.lr_factor("C", {}, 1) * t.lr_factor("A", {"C": 1}, 1)
    assert lr == pytest.approx(manual)


def test_unanimous_correct_verdicts_grow_wealth() -> None:
    t = _informative_tables()
    lr = task_lr_canonical(t, {"A": 1, "B": 1, "C": 1})
    assert lr > 1.0
    lr_wrong = task_lr_canonical(t, {"A": 0, "B": 0, "C": 0})
    assert lr_wrong < 1.0
