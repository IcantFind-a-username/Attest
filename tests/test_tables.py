import numpy as np
import pytest

from attest.core import Tables


def test_marginal_laplace_smoothing_from_empty() -> None:
    t = Tables()
    # no data: (0 + 1) / (0 + 2) = 0.5
    assert t.p1("A", {}, 1) == 0.5
    assert t.p1("A", {}, 0) == 0.5


def test_marginal_update_and_p1() -> None:
    t = Tables()
    t.update(1, {"A": 1})
    t.update(1, {"A": 1})
    t.update(1, {"A": 0})
    # theta=1: counts v=1:2, v=0:1 -> (2+1)/(3+2) = 0.6
    assert t.p1("A", {}, 1) == pytest.approx(0.6)
    # theta=0 untouched -> 0.5
    assert t.p1("A", {}, 0) == 0.5


def test_pair_conditioning_orientation() -> None:
    t = Tables()
    # A=1 with B=1 under theta=1, twice; A=1 with B=0 once
    t.update(1, {"A": 1, "B": 1})
    t.update(1, {"A": 1, "B": 1})
    t.update(1, {"A": 0, "B": 1})
    # P(vA=1 | vB=1, theta=1) = (2+1)/(3+2) = 0.6
    assert t.p1("A", {"B": 1}, 1) == pytest.approx(0.6)
    # P(vB=1 | vA=1, theta=1) = (2+1)/(2+2) = 0.75
    assert t.p1("B", {"A": 1}, 1) == pytest.approx(0.75)


def test_triple_conditioning() -> None:
    t = Tables()
    t.update(1, {"A": 1, "B": 1, "C": 1})
    t.update(1, {"A": 1, "B": 1, "C": 0})
    t.update(1, {"A": 0, "B": 1, "C": 1})
    # P(vC=1 | vA=1, vB=1, theta=1) = (1+1)/(2+2) = 0.5
    assert t.p1("C", {"A": 1, "B": 1}, 1) == pytest.approx(0.5)
    # P(vA=1 | vB=1, vC=1, theta=1) = (1+1)/(2+2) = 0.5
    assert t.p1("A", {"B": 1, "C": 1}, 1) == pytest.approx(0.5)


def test_lr_factor() -> None:
    t = Tables()
    for _ in range(8):
        t.update(1, {"A": 1})
        t.update(0, {"A": 0})
    for _ in range(2):
        t.update(1, {"A": 0})
        t.update(0, {"A": 1})
    # P(vA=1|theta=1) = (8+1)/(10+2) = 0.75; P(vA=1|theta=0) = (2+1)/12 = 0.25
    assert t.lr_factor("A", {}, 1) == pytest.approx(3.0)
    assert t.lr_factor("A", {}, 0) == pytest.approx(1 / 3)


def test_update_po_only_touches_used_tables() -> None:
    t = Tables()
    t.update_po(1, ["C", "A"], {"C": 1, "A": 0})
    # C first purchase -> marginal only
    assert t.marg["C"][1, 1] == 1
    assert t.marg["A"].sum() == 0  # A was second: pair table only
    assert t.pair[("A", "C")][1, 0, 1] == 1
    assert t.pair[("A", "B")].sum() == 0
    assert t.trip is not None and t.trip.sum() == 0


def test_update_po_third_purchase_hits_triple() -> None:
    t = Tables()
    t.update_po(0, ["B", "C", "A"], {"A": 1, "B": 0, "C": 1})
    assert t.trip is not None
    assert t.trip[0, 1, 0, 1] == 1


def test_agree() -> None:
    t = Tables()
    t.update(1, {"B": 1, "C": 1})
    t.update(0, {"B": 0, "C": 0})
    # per theta row: tot = 1+4, agree = 1+2 -> 0.6 each; prior-weighted = 0.6
    assert t.agree("B", "C") == pytest.approx(0.6)
    assert t.agree("C", "B") == pytest.approx(0.6)


def test_min_cell_count_excludes_triple() -> None:
    t = Tables()
    assert t.min_cell_count() == 0
    for th in (0, 1):
        for va in (0, 1):
            for vb in (0, 1):
                for vc in (0, 1):
                    t.update(th, {"A": va, "B": vb, "C": vc})
    # every marg cell has 4, every pair cell has 2, trip cells have 1 (excluded)
    assert t.min_cell_count() == 2
    # marginal-only trigger for the exploration schedule
    assert t.min_marginal_count() == 4


def test_two_judges_supported_no_triple() -> None:
    t = Tables(judges=("X", "Y"))
    t.update(1, {"X": 1, "Y": 0})
    assert t.trip is None
    assert t.p1("X", {"Y": 0}, 1) == pytest.approx((1 + 1) / (1 + 2))
    with pytest.raises(NotImplementedError):
        t.p1("X", {"Y": 0, "Z": 1}, 1)


def test_update_po_beyond_three_judges_rejected() -> None:
    t = Tables(judges=("A", "B", "C", "D"))
    with pytest.raises(NotImplementedError):
        t.update_po(1, ["A", "B", "C", "D"], {"A": 1, "B": 1, "C": 1, "D": 1})


def test_duplicate_judges_rejected() -> None:
    with pytest.raises(ValueError):
        Tables(judges=("A", "A", "B"))


def test_smoothing_parameter() -> None:
    t = Tables(smoothing=0.5)
    t.update(1, {"A": 1})
    assert t.p1("A", {}, 1) == pytest.approx((1 + 0.5) / (1 + 1.0))


def test_zero_smoothing_rejected() -> None:
    # dogfood finding: smoothing=0 made empty cells silently NaN
    with pytest.raises(ValueError):
        Tables(smoothing=0.0)
    with pytest.raises(ValueError):
        Tables(smoothing=-1.0)


def test_update_ignores_missing_judges() -> None:
    t = Tables()
    t.update(1, {"A": 1, "C": 0})
    assert t.pair[("A", "C")][1, 1, 0] == 1
    assert t.pair[("A", "B")].sum() == 0
    assert t.pair[("B", "C")].sum() == 0
    assert t.trip is not None and t.trip.sum() == 0
    assert isinstance(t.marg["A"], np.ndarray)
