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


def test_render_formal_findings_and_drawer() -> None:
    surfaced = [_result(3, f"Crash variant number {i} on empty input.", True) for i in range(4)]
    for i, r in enumerate(surfaced):
        r.wealth += i  # stable ordering
    drawer = [_result(1, "Weak hunch about a possible leak.", False)]
    outcome = apply_gate(surfaced + drawer, max_findings=3)
    text = render(outcome, 0.1, 0.12, 0.25, 42.0, notes=["hello"])
    assert "findings (wealth >= 10" in text
    assert text.count("breaks when:") == 3  # cap-3 formal
    assert "drawer (2 candidate(s)" in text  # overflow + deferred, both visible
    assert "note: hello" in text
    assert "spend $0.1200 of $0.25" in text


def test_render_defer() -> None:
    outcome = apply_gate([], max_findings=3)
    text = render(outcome, 0.1, 0.0, 0.25, 1.0, deferred_reason="budget: too big")
    assert "DEFER: budget: too big" in text
    assert "no findings cleared" not in text
