import pytest

from attest.review.channels import (
    RHO,
    VOTE_LR,
    gate_feasibility,
    max_reachable_wealth,
    tier0_lr,
    verification_lr,
    votes_lr,
)


def test_vote_schedule_diminishing_and_capped() -> None:
    # frozen factory schedule: 2.0, 2.64, 2.95, 3.0 (cap), 3.0 (cap)
    assert votes_lr(1) == pytest.approx(2.0)
    assert votes_lr(2) == pytest.approx(2.6390, abs=1e-3)
    assert votes_lr(3) == pytest.approx(2.9485, abs=1e-3)
    assert votes_lr(4) == 3.0
    assert votes_lr(5) == 3.0
    # marginal gain shrinks (correlation discount, rho=0.6)
    gains = [VOTE_LR[m] / VOTE_LR[m - 1] for m in range(2, 6)]
    assert all(gains[i] >= gains[i + 1] for i in range(len(gains) - 1))
    assert RHO == 0.6


def test_votes_lr_edges() -> None:
    assert votes_lr(0) == 1.0
    assert votes_lr(99) == 3.0  # beyond K: stays at cap


def test_tier0_lr() -> None:
    assert tier0_lr(0) == 1.0
    assert tier0_lr(1) == 2.0
    assert tier0_lr(2) == 3.0
    assert tier0_lr(10) == 3.0


def test_verification_lr_capped_not_unconditional() -> None:
    assert verification_lr(True) == 20.0
    assert verification_lr(False) == 0.5
    # reproduced alone must NOT clear every alpha: at alpha=0.04 threshold is 25
    assert verification_lr(True) < 25


def test_gate_feasibility_at_default_alpha() -> None:
    # alpha=0.1 -> threshold 10: S*T = 9 cannot reach it; with V it can
    assert max_reachable_wealth(False) == pytest.approx(9.0)
    feas = gate_feasibility(0.1)
    assert feas["reachable_without_verification"] is False
    assert feas["reachable_with_verification"] is True
    # a looser alpha makes S+T sufficient
    feas_loose = gate_feasibility(0.15)
    assert feas_loose["reachable_without_verification"] is True
    # an absurdly tight alpha is unreachable outright
    feas_tight = gate_feasibility(0.001)
    assert feas_tight["reachable_with_verification"] is False
