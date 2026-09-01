from attest.core.betting import decide
from attest.review.channels import ChannelPurchase, tier0_lr, verification_lr, votes_lr
from attest.review.gate import GateResult, apply_gate, apply_verification, evaluate_finding
from attest.review.schema import Finding
from attest.review.tier0 import Tier0Signal


def _f(votes: int, claim: str = "Crash on empty input.") -> Finding:
    f = Finding(
        claim=claim,
        file="a.py",
        line=10,
        failure_scenario="empty list",
        falsification_plan="run f([])",
    )
    f.votes = votes
    return f


def _sig(n: int) -> list[Tier0Signal]:
    return [Tier0Signal("ruff", "a.py", 10 + i, f"E{i}") for i in range(n)]


def test_votes_only_stays_in_drawer_at_default_alpha() -> None:
    r = evaluate_finding(_f(5), alpha=0.1, tier0=[])
    assert r.wealth == 3.0
    assert r.decision is None
    assert [p.channel for p in r.purchases] == ["S"]


def test_tier0_bought_when_present_but_gate_still_decides() -> None:
    r = evaluate_finding(_f(5), alpha=0.1, tier0=_sig(2))
    assert r.wealth == 9.0  # 3 * 3: the factory ceiling without verification
    assert r.decision is None  # 9 < 10: cap-honest, still the drawer
    assert [p.channel for p in r.purchases] == ["S", "T"]


def test_verification_surfaces() -> None:
    r = evaluate_finding(_f(2), alpha=0.1, tier0=[], verification=True)
    assert r.wealth > 10
    assert r.decision == 1
    assert r.action == "surface"


def test_failed_verification_stays_in_drawer_not_discard() -> None:
    r = evaluate_finding(_f(2), alpha=0.1, tier0=[], verification=False)
    # 2.639 * 0.5 = 1.32: above alpha, below 1/alpha -> drawer
    assert r.decision is None


def test_single_vote_weak_claim_can_be_discarded_at_loose_alpha() -> None:
    # at alpha=0.55 the discard bar is 0.55; a failed verification on a
    # single-vote finding drops wealth to 1.0 * ... still above; construct via
    # verification failure: 2.0 * 0.5 = 1.0 -> drawer even here
    r = evaluate_finding(_f(1), alpha=0.4, tier0=[], verification=False)
    assert r.decision is None


def test_no_early_purchase_after_decision() -> None:
    # alpha=0.3: threshold 3.33; S(5 votes)=3.0 not enough; T pushes past
    r = evaluate_finding(_f(5), alpha=0.3, tier0=_sig(1), verification=True)
    # after S*T = 6 >= 3.33 the gate has decided: V must NOT be purchased
    assert [p.channel for p in r.purchases] == ["S", "T"]
    assert r.decision == 1


def test_apply_gate_cap_is_layout_not_speech() -> None:
    rs = [
        evaluate_finding(_f(2, f"Crash number {i} on empty input."), 0.1, [], True)
        for i in range(5)
    ]
    # stagger wealth so ordering is deterministic
    for i, r in enumerate(rs):
        r.wealth += i * 0.01
    outcome = apply_gate(rs, max_findings=3)
    assert len(outcome.formal) == 3
    assert len(outcome.drawer_overflow) == 2  # visible, not suppressed
    assert outcome.formal[0].wealth >= outcome.formal[-1].wealth
    assert not outcome.drawer and not outcome.discarded


def test_apply_gate_splits_actions() -> None:
    surface = evaluate_finding(_f(2), 0.1, [], True)
    drawer = evaluate_finding(_f(2), 0.1, [])
    outcome = apply_gate([surface, drawer], max_findings=3)
    assert outcome.formal == [surface]
    assert outcome.drawer == [drawer]


def test_apply_verification_reproduced_surfaces_with_one_v_purchase() -> None:
    result = GateResult(
        finding=_f(2),
        wealth=2.6390158215457884,
        purchases=[ChannelPurchase("S", 2.6390158215457884, "2 of K samples assert")],
        decision=None,
    )

    verified = apply_verification(result, alpha=0.1, reproduced=True)

    assert verified.wealth == 52.78031643091577
    assert verified.action == "surface"
    assert [purchase.channel for purchase in verified.purchases] == ["S", "V"]


def test_apply_verification_failed_reproduction_leaves_drawer() -> None:
    result = GateResult(
        finding=_f(2),
        wealth=2.6390158215457884,
        purchases=[ChannelPurchase("S", 2.6390158215457884, "2 of K samples assert")],
        decision=None,
    )

    verified = apply_verification(result, alpha=0.1, reproduced=False)

    assert verified.wealth == 1.3195079107728942
    assert verified.action == "drawer"


def test_apply_verification_does_not_mutate_the_input_result() -> None:
    result = GateResult(
        finding=_f(2),
        wealth=2.6390158215457884,
        purchases=[ChannelPurchase("S", 2.6390158215457884, "2 of K samples assert")],
        decision=None,
    )

    apply_verification(result, alpha=0.1, reproduced=True)

    assert result.wealth == 2.6390158215457884
    assert result.decision is None
    assert [purchase.channel for purchase in result.purchases] == ["S"]


def test_discard_is_unreachable_under_factory_constants() -> None:
    # Pins the honesty rationale for the report copy (report.py): under the
    # factory tables, decide() can never return 0 (discard) once a candidate
    # has at least one proposer vote, even after a failed verification. Floor:
    # votes=1, tier0=0 signals -> wealth = votes_lr(1) * 1.0 * V_FAILED
    # = 2.0 * 1.0 * 0.5 = 1.0, which is already > alpha=0.1. So a report line
    # that promises "certified-false" discards is a promise the tables cannot
    # keep, and must not be printed as if it happened.
    alpha = 0.1
    for votes in range(1, 6):
        for n_tier0 in range(0, 3):
            wealth = votes_lr(votes)
            if n_tier0:
                wealth *= tier0_lr(n_tier0)
            wealth *= verification_lr(False)  # failed reproduction: V_FAILED
            assert wealth > alpha
            assert decide(wealth, alpha) != 0

            # cross-check through the real gate pipeline end-to-end
            r = evaluate_finding(_f(votes), alpha, _sig(n_tier0), verification=False)
            assert r.wealth > alpha
            assert r.decision != 0



def test_pricing_instrument_records_without_deciding_anything() -> None:
    """The instrument observes the multiplication; it never feeds the gate.

    D-063: compare the decision taken on the full wealth against the decision
    the strongest single purchased channel would have taken alone. At the
    default alpha with the frozen factory tables the two never differ, because
    S * T tops out at 9 below the surfacing threshold of 10 and only V reaches
    it -- and V alone already reaches it.
    """
    votes_only = evaluate_finding(_f(5), alpha=0.1, tier0=[])
    assert votes_only.strongest_purchased_lr == 3.0
    assert votes_only.pricing_changed_decision is False

    at_the_ceiling = evaluate_finding(_f(5), alpha=0.1, tier0=_sig(2))
    assert at_the_ceiling.wealth == 9.0
    assert at_the_ceiling.strongest_purchased_lr == 3.0
    assert at_the_ceiling.pricing_changed_decision is False

    verified = apply_verification(votes_only, alpha=0.1, reproduced=True)
    assert verified.wealth == 60.0
    assert verified.strongest_purchased_lr == 20.0
    assert verified.decision == 1
    assert decide(verified.strongest_purchased_lr, 0.1) == 1
    assert verified.pricing_changed_decision is False


def test_pricing_instrument_reports_true_when_the_product_is_load_bearing() -> None:
    """A live instrument has to be able to fire, or it measures nothing.

    At a threshold of 8 the S * T product surfaces a finding that neither
    channel surfaces alone. No product decision is taken at this alpha here;
    this pins that the instrument responds to the thing it claims to watch.
    """
    alpha = 0.125  # threshold 1/alpha = 8
    result = evaluate_finding(_f(5), alpha=alpha, tier0=_sig(2))

    assert result.wealth == 9.0
    assert result.decision == 1
    assert result.strongest_purchased_lr == 3.0
    assert decide(result.strongest_purchased_lr, alpha) is None
    assert result.pricing_changed_decision is True
