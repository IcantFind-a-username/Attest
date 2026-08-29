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

import numpy as np
import pytest

from attest.benchmark.experiments import (
    ASSUMED_SCHEDULE,
    DEFAULT_GAMMAS,
    DEFAULT_NULL_ASSUMPTIONS,
    DEFAULT_NULL_GAMMAS,
    DEFAULT_SEEDS,
    DEFAULT_VILLE_ALPHAS,
    DISCOUNTED_ARM,
    FACTORY_ALPHAS,
    FULL_CHANNELS,
    NAIVE_ARM,
    ORACLE_SCHEDULE,
    PRODUCTION_ARM,
    TWO_SIDED_ARM,
    VOTES_ONLY,
    NullAssumptions,
    calibrated_vote_accuracy,
    discount_speech_window,
    measure_channel_e_validity,
    measure_ville_bound,
    naive_votes_lr,
    oracle_panel_lr,
    panel_vote_distribution,
    run_e_validity_experiment,
    run_rho_ablation,
    simulate_panel,
    two_sided_votes_lr,
    verification_e_validity_ceiling,
)
from attest.review.channels import (
    LR1,
    RHO,
    S_CAP,
    T_CAP,
    V_CAP,
    V_FAILED,
    VOTE_LR,
    tier0_lr,
    verification_lr,
    votes_lr,
)

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


# ===========================================================================
# D-023 follow-up: is the wealth process an e-process at all?
#
# Ville's inequality only bounds the wrong-certification rate when every
# evidence purchase satisfies E[LR | H0] <= 1. These tests pin the measuring
# instrument for that question: the estimator is validated against a
# likelihood ratio that is a valid e-value by construction before it is used
# to judge the production schedule, both the unconditioned and the
# candidate-conditioned expectation are reported, and the two-sided
# counterfactual stays inside the harness.
# ===========================================================================


_EVALUE_SEEDS = (11, 22, 33)


def _evalue(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "gammas": (0.0, RHO),
        "alphas": (0.1, 0.4),
        "k": 5,
        "n_tasks": 1000,
        "seeds": _EVALUE_SEEDS,
        "bootstrap_resamples": 300,
    }
    kwargs.update(overrides)
    return run_e_validity_experiment(**kwargs)


def _expectation(
    report: Any,
    *,
    channel: str,
    schedule: str,
    gamma: float | None = None,
    rate: float | None = None,
) -> Any:
    for row in report.expectations:
        if row.channel != channel or row.schedule != schedule:
            continue
        if gamma is not None and row.gamma != gamma:
            continue
        if rate is not None and row.assumed_rate != rate:
            continue
        return row
    raise AssertionError(f"missing expectation row {channel}/{schedule}")


def _ville(report: Any, *, gamma: float, alpha: float, composition: str, arm: str) -> Any:
    for cell in report.ville:
        if (cell.gamma, cell.alpha, cell.composition, cell.arm) == (
            gamma,
            alpha,
            composition,
            arm,
        ):
            return cell
    raise AssertionError("missing ville cell")


# --- the exact panel model -------------------------------------------------


def test_panel_vote_distribution_matches_the_simulator() -> None:
    """The analytic null model must describe the generator it claims to describe.

    Every analytic cross-check in this section rests on this equality.
    """
    accuracy = calibrated_vote_accuracy()
    for gamma in (0.0, RHO, 0.9):
        exact = panel_vote_distribution(k=5, vote_rate=1.0 - accuracy, gamma=gamma)
        panel = simulate_panel(
            gamma=gamma,
            theta_prior=0.0,
            judge_accuracy=accuracy,
            k=5,
            n_tasks=40000,
            seed=101,
        )
        empirical = np.bincount(panel.votes, minlength=6) / panel.n_tasks

        assert exact.sum() == pytest.approx(1.0)
        assert np.abs(exact - empirical).max() < 0.01


def test_panel_vote_distribution_handles_degenerate_rates() -> None:
    """A vote rate of zero or one puts every panel at one end, and an
    impossible panel is rejected rather than silently clamped."""
    silent = panel_vote_distribution(k=5, vote_rate=0.0, gamma=RHO)
    unanimous = panel_vote_distribution(k=5, vote_rate=1.0, gamma=RHO)

    assert silent[0] == pytest.approx(1.0)
    assert unanimous[5] == pytest.approx(1.0)
    for bad in ({"k": 0}, {"vote_rate": 1.5}, {"gamma": -0.1}):
        kwargs: dict[str, Any] = {"k": 5, "vote_rate": 0.3, "gamma": 0.5}
        kwargs.update(bad)
        with pytest.raises(ValueError):
            panel_vote_distribution(**kwargs)


def test_two_sided_votes_lr_is_a_normalized_likelihood_ratio() -> None:
    """P(V=v | theta=1) / P(V=v | theta=0) on the independent panel, nothing else."""
    accuracy = 0.7
    null = panel_vote_distribution(k=5, vote_rate=1.0 - accuracy, gamma=0.0)
    alternative = panel_vote_distribution(k=5, vote_rate=accuracy, gamma=0.0)

    values = [two_sided_votes_lr(votes, 5, accuracy) for votes in range(6)]

    assert values == [pytest.approx(a / n) for a, n in zip(alternative, null, strict=True)]
    assert float(sum(p * lr for p, lr in zip(null, values, strict=True))) == pytest.approx(1.0)
    assert values[0] < 1.0 and values[1] < 1.0
    assert values[5] > 1.0


def test_two_sided_votes_lr_rejects_impossible_arguments() -> None:
    """A counterfactual with silent clamping would measure nothing."""
    for bad in ({"votes": -1}, {"votes": 6}, {"k": 0}, {"judge_accuracy": 1.0}):
        kwargs: dict[str, Any] = {"votes": 2, "k": 5, "judge_accuracy": 0.7}
        kwargs.update(bad)
        with pytest.raises(ValueError):
            two_sided_votes_lr(kwargs["votes"], kwargs["k"], kwargs["judge_accuracy"])


def test_oracle_panel_lr_is_a_valid_e_value_by_construction() -> None:
    """The estimator fixture: an exact LR from the generator's own densities."""
    accuracy = calibrated_vote_accuracy()
    for gamma in (0.0, RHO, 0.9):
        null = panel_vote_distribution(k=5, vote_rate=1.0 - accuracy, gamma=gamma)
        lrs = oracle_panel_lr(k=5, judge_accuracy=accuracy, gamma=gamma)

        assert len(lrs) == 6
        assert float(np.dot(null, lrs)) == pytest.approx(1.0)


# --- determinism -----------------------------------------------------------


def test_e_validity_report_is_deterministic_for_the_same_seeds() -> None:
    """Same seeds, same bootstrap seed, same digest — or nothing here is pinnable."""
    first = _evalue()
    second = _evalue()
    shifted = _evalue(seeds=(11, 22, 34))

    assert first.digest == second.digest
    assert len(first.digest) == 64
    assert first.to_json_dict() == second.to_json_dict()
    assert first.digest != shifted.digest


def test_e_validity_digest_covers_the_emitted_payload() -> None:
    report = _evalue()
    payload = report.to_json_dict()
    digest = payload.pop("digest")

    assert digest == report.digest
    assert json.dumps(payload, sort_keys=True)


# --- estimator validation (do this before judging production) --------------


def test_the_oracle_fixture_measures_a_unit_null_expectation() -> None:
    """A known-valid e-value must measure to one within its interval.

    If this fails, the estimator is broken and every other number in this
    section is meaningless; it is checked first for that reason.
    """
    report = _evalue()

    for gamma in (0.0, RHO):
        row = _expectation(report, channel="S", schedule=ORACLE_SCHEDULE, gamma=gamma)
        assert row.analytic_mean == pytest.approx(1.0, abs=1e-9)
        assert row.interval[0] <= 1.0 <= row.interval[1]
        assert row.lower_bound_exceeds_one is False
        assert row.label not in report.derived["e_value_violations"]


def test_assumed_channel_rows_agree_with_their_analytic_expectations() -> None:
    """The same estimator, checked against closed forms for T and V."""
    report = _evalue()
    rows = [
        row
        for row in report.expectations
        if row.schedule == ASSUMED_SCHEDULE and row.analytic_mean is not None
    ]

    assert len(rows) >= 6
    for row in rows:
        assert row.mean == pytest.approx(row.analytic_mean, abs=0.05)
        assert row.interval[0] <= row.mean <= row.interval[1]


# --- the question ----------------------------------------------------------


def test_the_production_vote_schedule_is_not_an_e_value_under_the_null() -> None:
    """One-sided pricing: every reachable factor is >= 1, so E[LR|H0] > 1.

    If this ever measures at or below one, the concern is refuted and the
    report says so through an empty violation list — which is why the derived
    list, not the sign of a difference, is what is asserted.
    """
    report = _evalue()
    row = _expectation(report, channel="S", schedule=PRODUCTION_ARM, gamma=RHO)

    assert min(votes_lr(votes) for votes in range(6)) >= 1.0
    assert row.mean > 1.0
    assert row.interval[0] > 1.0
    assert row.e_validity_ratio == pytest.approx(row.mean)
    assert row.lower_bound_exceeds_one is True
    assert row.label in report.derived["e_value_violations"]


def test_candidate_conditioning_makes_the_production_channel_worse() -> None:
    """The product only prices findings some sample proposed, so the V=0
    outcome — the only one worth exactly 1 — is never observed."""
    report = _evalue()

    for gamma in (0.0, RHO):
        row = _expectation(report, channel="S", schedule=PRODUCTION_ARM, gamma=gamma)
        assert row.condition.startswith("candidate_exists")
        assert row.conditioned_mean is not None
        assert row.conditioned_mean > row.mean
        assert row.conditioned_e_validity_ratio > row.e_validity_ratio
        assert row.analytic_conditioned_mean > row.analytic_mean
        assert row.label in report.derived["e_value_violations_candidate_conditioned"]


def test_the_tier0_channel_is_one_sided_too() -> None:
    """T prices corroboration only: 1.0 / 2.0 / cap, never below one."""
    report = _evalue()
    zero = _expectation(report, channel="T", schedule=ASSUMED_SCHEDULE, rate=0.0)
    positive = _expectation(report, channel="T", schedule=ASSUMED_SCHEDULE, rate=0.1)

    assert min(tier0_lr(n) for n in range(4)) >= 1.0
    assert zero.analytic_mean == pytest.approx(1.0)
    assert positive.analytic_mean > 1.0
    assert positive.interval[0] > 1.0
    assert report.derived["tier0_e_validity_ceiling"] == 0.0


def test_the_verification_channel_is_the_only_one_that_can_be_valid() -> None:
    """V has a factor below one (a failed reproduction), so a low enough null
    reproduction rate keeps its expectation under the bound."""
    report = _evalue()
    no_purchase = DEFAULT_NULL_ASSUMPTIONS.verification_no_purchase_rate
    ceiling = verification_e_validity_ceiling(no_purchase)

    assert verification_lr(False) < 1.0 < verification_lr(True)
    assert ceiling == pytest.approx(
        (1.0 - V_FAILED) * (1.0 - no_purchase) / (V_CAP - V_FAILED)
    )
    below = _expectation(report, channel="V", schedule=ASSUMED_SCHEDULE, rate=0.0)
    above = _expectation(report, channel="V", schedule=ASSUMED_SCHEDULE, rate=0.1)

    assert below.analytic_mean < 1.0
    assert above.analytic_mean > 1.0
    assert report.derived["verification_e_validity_ceiling"] == pytest.approx(ceiling)


# --- the two-sided counterfactual (diagnostic only) ------------------------


def test_the_two_sided_counterfactual_is_valid_on_independent_panels() -> None:
    """Built from the true densities, so its null expectation is exactly one."""
    report = _evalue()
    row = _expectation(report, channel="S", schedule=TWO_SIDED_ARM, gamma=0.0)

    assert row.analytic_mean == pytest.approx(1.0, abs=1e-9)
    assert row.interval[0] <= 1.0 <= row.interval[1]
    assert row.label not in report.derived["e_value_violations"]


def test_the_two_sided_counterfactual_breaks_under_correlation() -> None:
    """It is only valid under the model it assumes. Recorded so nobody reads
    this diagnostic as a patch for channels.py."""
    report = _evalue()
    row = _expectation(report, channel="S", schedule=TWO_SIDED_ARM, gamma=RHO)

    assert row.analytic_mean > 1.0
    assert row.interval[0] > 1.0
    assert row.label in report.derived["e_value_violations"]


def test_candidate_conditioning_also_breaks_the_two_sided_counterfactual() -> None:
    """Selection, not just the schedule, is part of the problem."""
    report = _evalue()
    row = _expectation(report, channel="S", schedule=TWO_SIDED_ARM, gamma=0.0)

    assert row.analytic_conditioned_mean > 1.0
    assert row.analytic_conditioned_mean > row.analytic_mean


def test_the_two_sided_counterfactual_is_never_written_into_production() -> None:
    """channels.py must not learn about the experiment."""
    channels = (
        Path(__file__).parents[2] / "src" / "attest" / "review" / "channels.py"
    ).read_text(encoding="utf-8")

    assert "two_sided" not in channels
    assert "benchmark" not in channels


# --- Ville comparison ------------------------------------------------------


def test_ville_holds_at_factory_alpha_only_because_the_gate_is_unreachable() -> None:
    """D-008 arithmetic, restated as a measurement: the discounted channel
    cannot reach 1/alpha at all, so its silence — not a martingale — is what
    keeps the realized rate under the bound."""
    report = _evalue(alphas=FACTORY_ALPHAS)

    for alpha in FACTORY_ALPHAS:
        cell = _ville(
            report, gamma=RHO, alpha=alpha, composition=VOTES_ONLY, arm=PRODUCTION_ARM
        )
        assert cell.gate_reachable is False
        assert cell.wrong_certifications == 0
        assert cell.ville_crossings == 0
        assert cell.exceeds_bound is False
        assert 1.0 / alpha > S_CAP


def test_the_realized_rate_breaches_the_ville_bound_at_a_reachable_gate() -> None:
    """Where the gate is reachable on votes alone the advertised guarantee is
    simply not there."""
    report = _evalue(alphas=(0.4,))

    for gamma in (0.0, RHO):
        cell = _ville(
            report, gamma=gamma, alpha=0.4, composition=VOTES_ONLY, arm=PRODUCTION_ARM
        )
        assert cell.gate_reachable is True
        assert cell.wrong_certification_rate > cell.bound
        assert cell.wrong_certification_interval[0] > cell.bound
        assert cell.exceeds_bound is True
        assert cell.excess_ratio > 1.0


def test_the_two_sided_arm_stays_inside_the_bound_where_production_does_not() -> None:
    """The comparison that isolates the schedule from the gate arithmetic."""
    report = _evalue(alphas=(0.4,))
    production = _ville(
        report, gamma=0.0, alpha=0.4, composition=VOTES_ONLY, arm=PRODUCTION_ARM
    )
    two_sided = _ville(
        report, gamma=0.0, alpha=0.4, composition=VOTES_ONLY, arm=TWO_SIDED_ARM
    )

    assert two_sided.wrong_certification_rate < production.wrong_certification_rate
    assert two_sided.wrong_certification_rate <= two_sided.bound
    assert two_sided.exceeds_bound is False
    assert two_sided.discards > 0
    assert production.discards == 0


def test_ville_crossing_and_wrong_certification_coincide_under_the_stopping_rule() -> None:
    """Production stops purchasing the moment the gate decides, so the running
    maximum of the wealth process crosses exactly when a finding is certified.
    That equivalence is what makes this a Ville comparison at all."""
    report = _evalue(alphas=DEFAULT_VILLE_ALPHAS)

    for cell in report.ville:
        assert cell.ville_crossings == cell.wrong_certifications


def test_the_full_channel_stream_certifies_only_through_verification() -> None:
    """At factory alpha, S*T cannot reach the gate, so the realized wrong
    certification rate is the assumed false-reproduction rate and nothing else."""
    report = _evalue(alphas=(0.05,))
    votes_only = _ville(
        report, gamma=RHO, alpha=0.05, composition=VOTES_ONLY, arm=PRODUCTION_ARM
    )
    full = _ville(
        report, gamma=RHO, alpha=0.05, composition=FULL_CHANNELS, arm=PRODUCTION_ARM
    )

    assert S_CAP * T_CAP < 1.0 / 0.05
    assert votes_only.wrong_certifications == 0
    assert full.wrong_certifications > 0
    assert full.wrong_certification_rate == pytest.approx(
        DEFAULT_NULL_ASSUMPTIONS.verification_reproduce_rate, abs=0.02
    )


# --- reporting contract ----------------------------------------------------


def test_every_seed_is_reported_in_both_sections() -> None:
    report = _evalue()

    for row in report.expectations:
        assert tuple(entry.seed for entry in row.per_seed) == _EVALUE_SEEDS
        assert sum(entry.samples for entry in row.per_seed) == row.samples
    for cell in report.ville:
        assert tuple(entry.seed for entry in cell.per_seed) == _EVALUE_SEEDS
        assert sum(entry.candidates for entry in cell.per_seed) == cell.candidates
        assert (
            sum(entry.wrong_certifications for entry in cell.per_seed)
            == cell.wrong_certifications
        )


def test_the_report_states_its_assumptions_and_its_status() -> None:
    """The T and V null rates are assumptions with no measurement behind them,
    and the artifact has to say so itself."""
    report = _evalue()
    payload = report.to_json_dict()
    notes = " ".join(report.honesty)

    assert report.status == "insufficient_labels/recommendation_only"
    assert report.offline is True
    assert "synthetic" in notes
    assert "500" in notes
    assert "ASSUMPTION" in notes
    assert "NOT a proposed change" in notes
    assert RHO in DEFAULT_NULL_GAMMAS
    assert set(FACTORY_ALPHAS) <= set(DEFAULT_VILLE_ALPHAS)
    assert payload["constants"] == {
        "lr1": LR1,
        "rho": RHO,
        "s_cap": S_CAP,
        "t_cap": T_CAP,
        "v_cap": V_CAP,
        "v_failed": V_FAILED,
        "vote_lr": list(VOTE_LR),
    }
    assert payload["config"]["assumptions"]["verification_no_purchase_rate"] == (
        DEFAULT_NULL_ASSUMPTIONS.verification_no_purchase_rate
    )
    assert payload["derived"]["e_value_bound"] == 1.0


def test_measure_functions_are_usable_on_their_own() -> None:
    """Both measurement primitives are public and independently callable."""
    rows = measure_channel_e_validity(
        k=5, gamma=RHO, n_tasks=400, seeds=_EVALUE_SEEDS, bootstrap_resamples=200
    )
    cells = measure_ville_bound(
        alphas=(0.4,), k=5, gamma=RHO, n_tasks=400, seeds=_EVALUE_SEEDS
    )

    assert {row.channel for row in rows} == {"S", "T", "V"}
    assert {cell.composition for cell in cells} == {VOTES_ONLY, FULL_CHANNELS}


@pytest.mark.parametrize(
    "override",
    [
        {"gammas": ()},
        {"gammas": (1.5,)},
        {"alphas": ()},
        {"alphas": (1.0,)},
        {"seeds": ()},
        {"seeds": (1, 1)},
        {"k": 0},
        {"n_tasks": 0},
        {"judge_accuracy": 1.0},
        {"bootstrap_resamples": 0},
        {"assumptions": NullAssumptions(tier0_signal_rate=1.5)},
        {"assumptions": NullAssumptions(verification_reproduce_rate=0.9)},
        {"assumptions": NullAssumptions(tier0_signal_slots=-1)},
    ],
)
def test_invalid_e_validity_configuration_is_rejected(override: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _evalue(**override)


# --- structural ------------------------------------------------------------


def test_the_diagnostic_reads_every_production_channel_constant() -> None:
    """No forked schedule, no hardcoded cap: the instrument must measure the
    shipped values.

    ``V_FAILED`` (0.5) is imported and asserted by name but deliberately left
    out of the forbidden-literal set: 0.5 is the neutral prior used elsewhere
    in this module, so its presence would prove nothing.
    """
    tree = ast.parse(_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "attest.review.channels":
            imported |= {alias.name for alias in node.names}

    assert {
        "LR1",
        "RHO",
        "S_CAP",
        "T_CAP",
        "V_CAP",
        "V_FAILED",
        "VOTE_LR",
        "tier0_lr",
        "verification_lr",
        "votes_lr",
    } <= imported

    forbidden = {LR1, RHO, S_CAP, T_CAP, V_CAP}
    literals = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, float)
        and node.value in forbidden
    ]
    assert literals == []


def test_the_factory_constants_the_diagnostic_reads_are_unchanged() -> None:
    """This is a diagnostic that reads production values. If it ever moves one,
    this test is the tripwire (ground rule 8: owner decision, D-007/D-008)."""
    assert (LR1, RHO, S_CAP, T_CAP, V_CAP, V_FAILED) == (2.0, 0.6, 3.0, 3.0, 20.0, 0.5)
    assert [round(value, 2) for value in VOTE_LR] == [1.0, 2.0, 2.64, 2.95, 3.0, 3.0]
    assert [tier0_lr(n) for n in range(4)] == [1.0, 2.0, 3.0, 3.0]
    assert (verification_lr(True), verification_lr(False)) == (20.0, 0.5)


def test_production_modules_do_not_depend_on_the_experiment() -> None:
    """The dependency runs one way only: experiment -> production."""
    root = Path(__file__).parents[2] / "src" / "attest"
    for relative in ("review/channels.py", "review/gate.py", "core/betting.py"):
        tree = ast.parse((root / relative).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("attest.benchmark")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("attest.benchmark")


# --- command line ----------------------------------------------------------


def test_evalue_cli_writes_deterministic_offline_json(tmp_path: Path) -> None:
    cli = _cli()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    argv = [
        "experiment-evalue",
        "--gammas",
        "0.0",
        "--alphas",
        "0.4",
        "--k",
        "5",
        "--tasks",
        "300",
        "--seeds",
        "11",
        "22",
        "--bootstrap-resamples",
        "100",
    ]

    assert cli.main([*argv, "--output", str(first)]) == 0
    assert cli.main([*argv, "--output", str(second)]) == 0

    assert first.read_bytes() == second.read_bytes()
    payload = json.loads(first.read_text(encoding="utf-8"))
    assert payload["offline"] is True
    assert payload["status"] == "insufficient_labels/recommendation_only"
    assert payload["experiment"] == "channel_e_value_validity"
    assert payload["expectations"]
    assert payload["ville"]


def test_evalue_cli_rejects_an_invalid_configuration(tmp_path: Path) -> None:
    cli = _cli()
    output = tmp_path / "out.json"
    code = cli.main(
        [
            "experiment-evalue",
            "--gammas",
            "0.0",
            "--alphas",
            "0.4",
            "--verification-reproduce-rate",
            "1.4",
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
