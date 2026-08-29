"""Factory evidence channels: fixed conservative LR tables (cold start).

No per-repo learning; the ledger needs >= 500 labels before any recalibration,
and even then only global (spec red line 5). The K-sample panel is a CORRELATED
panel: naive independence would fabricate confidence, so the vote schedule
discounts votes 2..K with an assumed within-sample correlation rho = 0.6 and
caps the whole channel.

Vote schedule derivation (frozen; DECISIONS D-007): vote i contributes
LR1^((1-rho)^(i-1)) with LR1 = 2.0, i.e. cumulative exponent
1, 1.4, 1.56, 1.624, 1.650 -> LR 2.00, 2.64, 2.95, 3.09, 3.14, capped at 3.
"""

from __future__ import annotations

from dataclasses import dataclass

RHO = 0.6
LR1 = 2.0
S_CAP = 3.0
T_CAP = 3.0
V_CAP = 20.0
V_FAILED = 0.5  # failed reproduction: mild evidence against, never a discard alone

# votes 1..5 (index 0 unused)
VOTE_LR = [1.0] + [min(S_CAP, LR1 ** sum((1 - RHO) ** i for i in range(m))) for m in range(1, 6)]


def votes_lr(votes: int) -> float:
    """S channel: proposer votes, correlation-discounted, capped."""
    if votes < 1:
        return 1.0
    return VOTE_LR[min(votes, len(VOTE_LR) - 1)]


def tier0_lr(n_signals: int) -> float:
    """T channel: distinct static signals overlapping the anchor. Capped."""
    if n_signals <= 0:
        return 1.0
    return 2.0 if n_signals == 1 else T_CAP


def verification_lr(reproduced: bool) -> float:
    """V channel: reproduction evidence. A strong feature and a surfacing
    brake, never an unconditional pass (red line 3): capped at 20, and the
    gate threshold still decides."""
    return V_CAP if reproduced else V_FAILED


@dataclass
class ChannelPurchase:
    channel: str  # "S" | "T" | "V"
    lr: float
    detail: str


def max_reachable_wealth(with_verification: bool) -> float:
    """Oracle feasibility ceiling of the factory tables (red line 4: prove the
    gate reachable before adopting it)."""
    base = S_CAP * T_CAP
    return base * V_CAP if with_verification else base


def gate_feasibility(alpha: float) -> dict[str, bool]:
    return {
        "reachable_without_verification": max_reachable_wealth(False) >= 1.0 / alpha,
        "reachable_with_verification": max_reachable_wealth(True) >= 1.0 / alpha,
    }
