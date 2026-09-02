from pathlib import Path

import pytest

from attest.review.config import ReviewConfig, load_config, load_pricing
from attest.review.gate import apply_gate, evaluate_finding
from attest.review.report import render
from attest.review.schema import Finding


def test_factory_defaults() -> None:
    c = ReviewConfig()
    assert c.alpha == 0.1
    assert c.budget_usd == 0.25
    assert c.k_samples == 5
    assert c.max_findings == 3
    assert c.model == load_pricing()["default_model"]


def test_config_validation() -> None:
    with pytest.raises(ValueError):
        ReviewConfig(alpha=1.5)
    with pytest.raises(ValueError):
        ReviewConfig(budget_usd=0)
    with pytest.raises(ValueError):
        ReviewConfig(k_samples=0)


@pytest.mark.parametrize("budget", (float("nan"), float("inf"), float("-inf"), True))
def test_review_config_rejects_nonfinite_or_boolean_budget(budget: object) -> None:
    with pytest.raises(ValueError, match="budget"):
        ReviewConfig(budget_usd=budget)  # type: ignore[arg-type]


@pytest.mark.parametrize("alpha", (float("nan"), float("inf"), True))
def test_review_config_rejects_nonfinite_or_boolean_alpha(alpha: object) -> None:
    with pytest.raises(ValueError, match="alpha"):
        ReviewConfig(alpha=alpha)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "kwargs",
    (
        {"k_samples": True},
        {"max_findings": True},
        {"max_findings": 0},
        {"auto_tighten_alpha": 1},
        {"tier0_commands": ("ruff",)},
        {"tier0_commands": [1]},
    ),
)
def test_review_config_rejects_ambiguous_policy_types(kwargs: object) -> None:
    with pytest.raises(ValueError):
        ReviewConfig(**kwargs)  # type: ignore[arg-type]


def test_load_config_merges_toml(tmp_path: Path) -> None:
    (tmp_path / ".attest.toml").write_text(
        'alpha = 0.05\nbudget_usd = 0.5\nunknown_key = "ignored"\n', encoding="utf-8"
    )
    c = load_config(tmp_path)
    assert c.alpha == 0.05
    assert c.budget_usd == 0.5
    assert c.k_samples == 5  # untouched default


def test_load_config_missing_file(tmp_path: Path) -> None:
    assert load_config(tmp_path).alpha == 0.1


def _result(votes: int, claim: str, verified: bool):
    f = Finding(
        claim=claim,
        file="a.py",
        line=5,
        failure_scenario="boom",
        falsification_plan="try it",
    )
    f.votes = votes
    return evaluate_finding(f, 0.1, [], verification=True if verified else None)


def test_render_certified_findings_and_drawer(certified_factory) -> None:
    ranked = [_result(3, f"Crash variant number {i} on empty input.", True) for i in range(4)]
    for i, r in enumerate(ranked):
        r.wealth += i  # stable ordering
    drawer = [_result(1, "Weak hunch about a possible leak.", False)]
    outcome = apply_gate(ranked + drawer, max_findings=3)
    # only the two candidates with an accepted receipt are findings; the other
    # two cleared the legacy wealth gate and are still just drawer candidates
    certified = [
        certified_factory(
            claim=r.finding.claim, path="a.py", line=5, candidate_id=r.finding.finding_id
        )
        for r in ranked[:2]
    ]
    text = render(outcome, 0.1, 0.12, 0.25, 42.0, notes=["hello"], certified=certified)
    assert "verified findings (each backed by one accepted receipt):" in text
    assert text.count("receipt:") == 2
    assert "unverified candidates (3; ranked by internal score, not evidence" in text
    assert "note: hello" in text
    assert "spend $0.1200 of $0.25" in text
    assert "5 candidate(s): 2 verified, 3 unverified, 0 discarded" in text
    assert "certified-false" not in text
    assert "surfaced" not in text


def test_render_defer() -> None:
    outcome = apply_gate([], max_findings=3)
    text = render(outcome, 0.1, 0.0, 0.25, 1.0, deferred_reason="budget: too big")
    assert "DEFER: budget: too big" in text
    assert "no findings cleared" not in text


def test_render_silence_reports_candidate_count_without_surfacing() -> None:
    # there was one candidate, it just never cleared the bar -- silence
    # should say how much was actually examined, not just go quiet.
    drawer_only = [_result(1, "Weak hunch about a possible leak.", False)]
    outcome = apply_gate(drawer_only, max_findings=3)
    text = render(outcome, 0.1, 0.0, 0.25, 3.0)
    assert "checked 1 candidate(s)" in text
    assert "none was verified by a reproduction" in text
    assert "certified-false" not in text
    assert "1 candidate(s): 0 verified, 1 unverified, 0 discarded" in text


def test_render_silence_zero_candidates_is_distinct() -> None:
    # zero candidates proposed is a different fact than "candidates proposed
    # but none surfaced" -- the reader shouldn't have to guess which happened.
    outcome = apply_gate([], max_findings=3)
    text = render(outcome, 0.1, 0.0, 0.25, 0.5)
    assert "no candidates proposed — saying nothing." in text
    assert "checked" not in text
    assert "0 candidate(s): 0 verified, 0 unverified, 0 discarded" in text
