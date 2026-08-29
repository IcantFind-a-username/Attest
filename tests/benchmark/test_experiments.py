"""Correlated-panel ablation: the naive independent product versus the D-007 discount.

These tests pin the experiment protocol — determinism, fairness under true
independence, honesty disclosures, and the D-008 arithmetic — never a
hand-picked seed or a favourable magnitude.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import math
from pathlib import Path
from typing import Any

import pytest

from attest.benchmark.experiments import (
    DEFAULT_GAMMAS,
    DEFAULT_SEEDS,
    DISCOUNTED_ARM,
    FACTORY_ALPHAS,
    NAIVE_ARM,
    calibrated_vote_accuracy,
    discount_speech_window,
    naive_votes_lr,
    run_rho_ablation,
    simulate_panel,
)
from attest.review.channels import LR1, RHO, S_CAP, VOTE_LR, votes_lr

_MODULE = Path(__file__).parents[2] / "src" / "attest" / "benchmark" / "experiments.py"
_SCRIPT = Path(__file__).parents[2] / "scripts" / "benchmark.py"

_SEEDS = (11, 22, 33)


def _ablation(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "gammas": (0.0, 0.9),
        "alphas": FACTORY_ALPHAS,
        "k": 5,
        "n_tasks": 400,
        "seeds": _SEEDS,
    }
    kwargs.update(overrides)
    return run_rho_ablation(**kwargs)


def _cell(report: Any, gamma: float, alpha: float) -> Any:
    for cell in report.cells:
        if cell.gamma == gamma and cell.alpha == alpha:
            return cell
    raise AssertionError("missing cell")


def _arm(cell: Any, aggregator: str) -> Any:
    return cell.naive if aggregator == NAIVE_ARM else cell.discounted


# --- determinism -----------------------------------------------------------


def test_simulate_panel_is_deterministic_for_a_seed() -> None:
    """Same seed must reproduce ballots exactly; a different seed must not."""
    first = simulate_panel(
        gamma=0.6, theta_prior=0.5, judge_accuracy=0.7, k=5, n_tasks=200, seed=7
    )
    second = simulate_panel(
        gamma=0.6, theta_prior=0.5, judge_accuracy=0.7, k=5, n_tasks=200, seed=7
    )
    other = simulate_panel(
        gamma=0.6, theta_prior=0.5, judge_accuracy=0.7, k=5, n_tasks=200, seed=8
    )

    assert (first.ballots == second.ballots).all()
    assert (first.theta == second.theta).all()
    assert (first.votes == second.votes).all()
    assert not (first.ballots == other.ballots).all()


def test_same_seeds_yield_identical_digest() -> None:
    """The whole report must be content-addressable for pinning."""
    first = _ablation()
    second = _ablation()
    shifted = _ablation(seeds=(11, 22, 34))

    assert first.digest == second.digest
    assert len(first.digest) == 64
    assert first.to_json_dict() == second.to_json_dict()
    assert first.digest != shifted.digest


def test_digest_covers_the_emitted_payload() -> None:
    """A digest that does not bind the payload cannot pin anything."""
    report = _ablation()
    payload = report.to_json_dict()
    digest = payload.pop("digest")

    assert digest == report.digest
    assert json.dumps(payload, sort_keys=True)


# --- panel generation ------------------------------------------------------


def test_gamma_one_makes_the_panel_a_single_witness() -> None:
    """gamma=1 clones vote one everywhere: k samples carry one draw of evidence."""
    panel = simulate_panel(
        gamma=1.0, theta_prior=0.5, judge_accuracy=0.7, k=5, n_tasks=300, seed=3
    )

    assert set(panel.votes.tolist()) <= {0, 5}
    assert (panel.ballots == panel.ballots[:, :1]).all()


def test_gamma_zero_gives_independent_votes() -> None:
    """gamma=0 must reproduce the binomial panel the naive aggregator assumes."""
    accuracy = 0.75
    panel = simulate_panel(
        gamma=0.0, theta_prior=1.0, judge_accuracy=accuracy, k=5, n_tasks=8000, seed=5
    )

    observed = float(panel.ballots.mean())
    assert abs(observed - accuracy) < 0.02
    variance = float(panel.votes.var())
    assert abs(variance - 5 * accuracy * (1 - accuracy)) < 0.15


def test_calibrated_accuracy_makes_one_positive_vote_worth_lr1() -> None:
    """The fair setting for the naive arm: its per-vote factor is exactly right."""
    accuracy = calibrated_vote_accuracy()

    assert accuracy == pytest.approx(LR1 / (1.0 + LR1))
    assert accuracy / (1.0 - accuracy) == pytest.approx(LR1)


# --- aggregators -----------------------------------------------------------


def test_naive_aggregator_is_the_uncapped_independent_product() -> None:
    """The counterfactual arm multiplies LR1 once per vote, with no cap."""
    assert naive_votes_lr(0) == 1.0
    for votes in range(1, 8):
        assert naive_votes_lr(votes) == pytest.approx(LR1**votes)
    assert naive_votes_lr(8) > S_CAP


def test_discounted_aggregator_is_the_production_function() -> None:
    """The experiment must compare against the shipped schedule, not a copy."""
    for votes in range(0, 8):
        assert votes_lr(votes) <= S_CAP
        if votes >= 2:
            assert votes_lr(votes) < naive_votes_lr(votes)


# --- the scientific claim --------------------------------------------------


def test_independent_panels_do_not_indict_the_naive_arm() -> None:
    """Fairness check: when independence truly holds the naive product is not
    anti-conservative at the factory gates, so the discount buys nothing."""
    report = _ablation(gammas=(0.0,), n_tasks=2000)

    for alpha in FACTORY_ALPHAS:
        cell = _cell(report, 0.0, alpha)
        for arm in (cell.naive, cell.discounted):
            assert arm.wrong_certification_rate is not None
            assert arm.wrong_certification_rate <= alpha


def test_correlated_panels_inflate_the_naive_wrong_certification_rate() -> None:
    """The claim under test, across the preregistered seed set."""
    report = _ablation(gammas=(0.9,), n_tasks=2000, seeds=DEFAULT_SEEDS)

    for alpha in FACTORY_ALPHAS:
        cell = _cell(report, 0.9, alpha)
        naive = cell.naive.wrong_certification_rate
        discounted = cell.discounted.wrong_certification_rate
        assert naive is not None and discounted is not None
        assert naive > discounted
        assert naive > alpha


def test_wrong_certification_rate_rises_with_correlation() -> None:
    """Monotone pressure, not a single lucky gamma.

    The rise is asserted only over the levels the design can separate. By
    gamma=0.9 the panel is effectively one witness repeated, so gamma=0.9 and
    gamma=0.99 saturate: their intervals overlap and no ordering is claimed.
    """
    report = _ablation(gammas=DEFAULT_GAMMAS, alphas=(0.1,), n_tasks=2000)
    arms = [_cell(report, gamma, 0.1).naive for gamma in DEFAULT_GAMMAS]
    rates = [arm.wrong_certification_rate for arm in arms]

    assert all(rate is not None for rate in rates)
    for lower, higher in zip(rates[:3], rates[1:4], strict=True):
        assert lower < higher

    saturated = arms[-2].wrong_certification_interval
    extreme = arms[-1].wrong_certification_interval
    assert saturated is not None and extreme is not None
    assert saturated[0] <= extreme[1] and extreme[0] <= saturated[1]


def test_discounted_arm_never_certifies_on_votes_alone_at_factory_alpha() -> None:
    """D-008 arithmetic: the capped S channel is 3 < 10 = 1/alpha."""
    assert S_CAP < 1.0 / 0.1
    report = _ablation(gammas=DEFAULT_GAMMAS, alphas=(0.1,), n_tasks=1000)

    for gamma in DEFAULT_GAMMAS:
        cell = _cell(report, gamma, 0.1)
        assert cell.discounted.certifications == 0
        assert cell.discounted.wrong_certifications == 0
        assert cell.discounted.abstention_rate == 1.0
        assert cell.discounted_can_certify is False


def test_loosened_gate_shows_the_discount_is_not_vacuously_silent() -> None:
    """Inside the derived window the discounted arm speaks, so the comparison
    is a real one rather than 'the safe arm never says anything'."""
    low, high = discount_speech_window()
    alpha = 0.5 * (low + high)
    report = _ablation(gammas=(0.9,), alphas=(alpha,), n_tasks=2000)
    cell = _cell(report, 0.9, alpha)

    assert low == pytest.approx(1.0 / S_CAP)
    assert high == pytest.approx(1.0 / VOTE_LR[2])
    assert cell.discounted_can_certify is True
    assert cell.discounted.certifications > 0
    assert cell.naive.certifications > cell.discounted.certifications


# --- reporting contract ----------------------------------------------------


def test_every_configuration_and_seed_is_reported() -> None:
    """No configuration and no seed may be dropped from the record."""
    report = _ablation(gammas=DEFAULT_GAMMAS, alphas=FACTORY_ALPHAS, n_tasks=200)

    assert len(report.cells) == len(DEFAULT_GAMMAS) * len(FACTORY_ALPHAS)
    for cell in report.cells:
        for arm in (cell.naive, cell.discounted):
            assert tuple(row.seed for row in arm.per_seed) == _SEEDS
            assert sum(row.wrong_certifications for row in arm.per_seed) == (
                arm.wrong_certifications
            )
            assert sum(row.certifications for row in arm.per_seed) == arm.certifications
        assert cell.naive.aggregator == NAIVE_ARM
        assert cell.discounted.aggregator == DISCOUNTED_ARM


def test_wilson_intervals_are_present_and_finite() -> None:
    """Uncertainty must travel with every reported rate."""
    report = _ablation(gammas=(0.9,), alphas=(0.1,), n_tasks=1000)
    naive = _cell(report, 0.9, 0.1).naive
    interval = naive.wrong_certification_interval

    assert interval is not None
    low, high = interval
    assert math.isfinite(low) and math.isfinite(high)
    assert 0.0 <= low <= naive.wrong_certification_rate <= high <= 1.0


def test_empty_denominators_report_none_rather_than_zero() -> None:
    """A rate over zero observations is unknown, not zero."""
    report = _ablation(gammas=(0.9,), alphas=(0.1,), theta_prior=1.0, n_tasks=200)
    naive = _cell(report, 0.9, 0.1).naive

    assert naive.negative_tasks == 0
    assert naive.wrong_certification_rate is None
    assert naive.wrong_certification_interval is None

    silent = _ablation(gammas=(0.9,), alphas=(0.1,), n_tasks=200).cells[0].discounted
    assert silent.certifications == 0
    assert silent.certification_precision is None
    assert silent.certification_precision_interval is None


def test_report_declares_synthetic_data_and_recommendation_only_status() -> None:
    """Honesty constraints are part of the artifact, not the prose around it."""
    report = _ablation(n_tasks=200)
    payload = report.to_json_dict()
    notes = " ".join(report.honesty)

    assert report.status == "insufficient_labels/recommendation_only"
    assert report.offline is True
    assert "synthetic" in notes
    assert "500" in notes
    assert payload["constants"] == {
        "lr1": LR1,
        "rho": RHO,
        "s_cap": S_CAP,
        "vote_lr": list(VOTE_LR),
    }
    assert payload["status"] == report.status


@pytest.mark.parametrize(
    "override",
    [
        {"gammas": ()},
        {"gammas": (1.5,)},
        {"gammas": (-0.1,)},
        {"alphas": ()},
        {"alphas": (0.0,)},
        {"alphas": (1.0,)},
        {"seeds": ()},
        {"seeds": (1, 1)},
        {"k": 0},
        {"n_tasks": 0},
        {"theta_prior": 1.5},
        {"judge_accuracy": 0.0},
    ],
)
def test_invalid_configuration_is_rejected(override: dict[str, Any]) -> None:
    """A silently clamped parameter would corrupt the record."""
    with pytest.raises(ValueError):
        _ablation(**override)


@pytest.mark.parametrize("override", [{"k": 0}, {"n_tasks": 0}, {"gamma": 1.1}])
def test_simulate_panel_rejects_an_impossible_panel(override: dict[str, Any]) -> None:
    """The generator guards itself; it is public and callable on its own."""
    kwargs: dict[str, Any] = {
        "gamma": 0.5,
        "theta_prior": 0.5,
        "judge_accuracy": 0.7,
        "k": 3,
        "n_tasks": 10,
        "seed": 1,
    }
    kwargs.update(override)
    with pytest.raises(ValueError):
        simulate_panel(**kwargs)


# --- structural ------------------------------------------------------------


def test_experiments_module_reads_production_constants() -> None:
    """The harness must not fork the schedule it claims to be measuring."""
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "attest.review.channels":
            imported |= {alias.name for alias in node.names}

    assert {"LR1", "RHO", "S_CAP", "votes_lr"} <= imported

    forbidden = {LR1, RHO, S_CAP}
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, float)
        and node.value in forbidden
    ]
    assert literals == []


# --- command line ----------------------------------------------------------


def _cli() -> Any:
    spec = importlib.util.spec_from_file_location("attest_benchmark_cli", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_cli_writes_deterministic_offline_json(tmp_path: Path) -> None:
    """The subcommand is offline by construction and byte-stable."""
    cli = _cli()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    argv = [
        "experiment-rho",
        "--gammas",
        "0.0",
        "0.9",
        "--alphas",
        "0.1",
        "--k",
        "5",
        "--tasks",
        "300",
        "--seeds",
        "11",
        "22",
    ]

    assert cli.main([*argv, "--output", str(first)]) == 0
    assert cli.main([*argv, "--output", str(second)]) == 0

    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["offline"] is True
    assert payload["status"] == "insufficient_labels/recommendation_only"
    assert len(payload["cells"]) == 2


def test_cli_rejects_an_invalid_experiment_configuration(tmp_path: Path) -> None:
    """Bad parameters must fail closed with the shared error contract."""
    cli = _cli()
    output = tmp_path / "out.json"
    code = cli.main(
        [
            "experiment-rho",
            "--gammas",
            "1.4",
            "--alphas",
            "0.1",
            "--k",
            "5",
            "--tasks",
            "100",
            "--seeds",
            "11",
            "--output",
            str(output),
        ]
    )

    assert code == 2
    assert not output.exists()
