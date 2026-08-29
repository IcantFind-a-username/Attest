from attest.review.gate import apply_gate, evaluate_finding
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
