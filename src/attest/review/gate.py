"""Per-finding wealth process and the odds-threshold gate.

Each candidate finding is a wager. Evidence channels are purchased in order
S (proposer votes) -> T (static corroboration) -> V (reproduction, when
available); wealth is the product of purchased LRs. Only the threshold decides:
wealth >= 1/alpha surfaces, wealth <= alpha silently discards, otherwise the
finding waits in the drawer. The formal-findings cap manages layout, never
speech (a capped finding is still visible in the drawer).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from attest.core.betting import decide
from attest.review.channels import ChannelPurchase, tier0_lr, verification_lr, votes_lr
from attest.review.schema import Finding
from attest.review.tier0 import Tier0Signal


@dataclass
class GateResult:
    finding: Finding
    wealth: float
    purchases: list[ChannelPurchase] = field(default_factory=list)
    decision: int | None = None  # 1 surface, 0 discard, None drawer
    # Instrument only (D-063). Whether multiplying the purchased channels
    # together decided anything the strongest single purchased channel would
    # not have decided on its own. It changes no decision and is never read by
    # the gate; it exists so the pricing layer reports every round whether it
    # is load-bearing, the same way silence and abstention rates do.
    pricing_changed_decision: bool | None = None

    @property
    def action(self) -> str:
        return {1: "surface", 0: "discard", None: "drawer"}[self.decision]

    @property
    def strongest_purchased_lr(self) -> float:
        """The largest single purchased likelihood ratio, or 1.0 if none."""
        return max((purchase.lr for purchase in self.purchases), default=1.0)


def _pricing_changed_decision(
    wealth: float, purchases: list[ChannelPurchase], alpha: float
) -> bool:
    """Did the product of the purchased channels decide differently alone?

    Compares the real decision, taken on the full wealth, against the decision
    the strongest single purchased channel would have produced by itself. This
    records; it never decides.
    """
    strongest = max((purchase.lr for purchase in purchases), default=1.0)
    return decide(wealth, alpha) != decide(strongest, alpha)


def evaluate_finding(
    finding: Finding,
    alpha: float,
    tier0: list[Tier0Signal],
    verification: bool | None = None,
) -> GateResult:
    purchases: list[ChannelPurchase] = []
    wealth = 1.0

    lr_s = votes_lr(finding.votes)
    purchases.append(ChannelPurchase("S", lr_s, f"{finding.votes} of K samples assert"))
    wealth *= lr_s

    if decide(wealth, alpha) is None and tier0:
        lr_t = tier0_lr(len(tier0))
        detail = "; ".join(f"{s.tool} {s.file}:{s.line} {s.message}" for s in tier0[:3])
        purchases.append(ChannelPurchase("T", lr_t, detail))
        wealth *= lr_t

    if decide(wealth, alpha) is None and verification is not None:
        lr_v = verification_lr(verification)
        purchases.append(
            ChannelPurchase("V", lr_v, "reproduced" if verification else "reproduction failed")
        )
        wealth *= lr_v

    return GateResult(
        finding=finding,
        wealth=wealth,
        purchases=purchases,
        decision=decide(wealth, alpha),
        pricing_changed_decision=_pricing_changed_decision(wealth, purchases, alpha),
    )


def apply_verification(result: GateResult, alpha: float, reproduced: bool) -> GateResult:
    """Return a new result after purchasing one reproduction-evidence channel."""
    lr_v = verification_lr(reproduced)
    purchase = ChannelPurchase("V", lr_v, "reproduced" if reproduced else "reproduction failed")
    wealth = result.wealth * lr_v
    purchases = [*result.purchases, purchase]
    return GateResult(
        finding=result.finding,
        wealth=wealth,
        purchases=purchases,
        decision=decide(wealth, alpha),
        pricing_changed_decision=_pricing_changed_decision(wealth, purchases, alpha),
    )


@dataclass
class GateOutcome:
    formal: list[GateResult]  # top-N surfaced findings, wealth-sorted
    drawer_overflow: list[GateResult]  # surfaced beyond the cap (still visible)
    drawer: list[GateResult]  # deferred
    discarded: list[GateResult]  # certified false (silent; kept for the ledger)


def apply_gate(results: list[GateResult], max_findings: int) -> GateOutcome:
    surfaced = sorted((r for r in results if r.decision == 1), key=lambda r: r.wealth, reverse=True)
    return GateOutcome(
        formal=surfaced[:max_findings],
        drawer_overflow=surfaced[max_findings:],
        drawer=[r for r in results if r.decision is None],
        discarded=[r for r in results if r.decision == 0],
    )
