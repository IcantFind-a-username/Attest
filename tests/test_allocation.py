import numpy as np
import pytest

from attest.core import Tables, choose_next, expected_info, kl


def test_kl_hand_values() -> None:
    assert kl(0.5, 0.5) == pytest.approx(0.0)
    v = 0.75 * np.log(0.75 / 0.25) + 0.25 * np.log(0.25 / 0.75)
    assert kl(0.75, 0.25) == pytest.approx(v)
    # clipping keeps extreme inputs finite
    assert np.isfinite(kl(0.0, 1.0))


def test_expected_info_zero_when_uninformative() -> None:
    t = Tables()  # empty tables: p1 = 0.5 under both truths
    assert expected_info(t, "A", {}, 0.5) == pytest.approx(0.0)


def _symmetric_tables() -> Tables:
    t = Tables()
    for _ in range(20):
        t.update(1, {"A": 1, "B": 1, "C": 1})
        t.update(0, {"A": 0, "B": 0, "C": 0})
    for _ in range(5):
        t.update(1, {"A": 0, "B": 0, "C": 0})
        t.update(0, {"A": 1, "B": 1, "C": 1})
    return t


def test_choose_next_price_aware_vs_blind() -> None:
    t = _symmetric_tables()
    prices = {"A": 1.00, "B": 0.50, "C": 0.15}
    # identical info for all three: price-aware picks the cheapest (C),
    # price-blind falls back to first-candidate tie-break (A)
    best_aware, _ = choose_next(t, ["A", "B", "C"], {}, 1.0, prices, True, 0.0)
    assert best_aware == "C"
    best_blind, _ = choose_next(t, ["A", "B", "C"], {}, 1.0, prices, False, 0.0)
    assert best_blind == "A"


def test_choose_next_tau_cutoff() -> None:
    t = Tables()  # uninformative: info = 0 for everyone
    prices = {"A": 1.0, "B": 0.5, "C": 0.15}
    best, val = choose_next(t, ["A", "B", "C"], {}, 1.0, prices, True, 0.05)
    assert best is None
    assert val == pytest.approx(0.0)


def test_choose_next_tie_break_first_candidate() -> None:
    t = Tables()
    prices = {"A": 1.0, "B": 1.0, "C": 1.0}
    # all info equal (zero) and tau=-1 disables the cutoff: first candidate wins
    best, _ = choose_next(t, ["B", "A"], {}, 1.0, prices, True, -1.0)
    assert best == "B"
