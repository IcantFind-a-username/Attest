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
    CANARY_CONFIGURATION,
    DEFAULT_GAMMAS,
    DEFAULT_NULL_ASSUMPTIONS,
    DEFAULT_NULL_GAMMAS,
    DEFAULT_NULL_GRID_ALPHAS,
    DEFAULT_NULL_GRID_LENGTHS,
    DEFAULT_NULL_GRID_PANEL_GAMMAS,
    DEFAULT_NULL_GRID_SEEDS,
    DEFAULT_SEEDS,
    DEFAULT_TWO_LEDGER_ALPHAS,
    DEFAULT_TWO_LEDGER_ASSUMPTIONS,
    DEFAULT_VILLE_ALPHAS,
    DISCOUNTED_ARM,
    FACTORY_ALPHAS,
    FACTORY_LEDGER_ARM,
    FULL_CHANNELS,
    HEALTHY_CONFIGURATION,
    MONITOR_POLICIES,
    NAIVE_ARM,
    NULL_GRID_ACCURACIES,
    ORACLE_SCHEDULE,
    OUTCOME_NO_PURCHASE,
    OUTCOME_NOT_REPRODUCED,
    OUTCOME_REPRODUCED,
    POLICY_EXPLORATION_RECOVERY,
    POLICY_LEDGER_ONLY,
    POLICY_QUARANTINE,
    PRODUCTION_ARM,
    TWO_LEDGER_ARM,
    TWO_SIDED_ARM,
    VOTES_ONLY,
    CandidateRecord,
    NullAssumptions,
    TwoLedgerAssumptions,
    arm_decisions,
    calibrated_vote_accuracy,
    clone_rate_for_pairwise_correlation,
    discount_speech_window,
    factory_terminal_wealth,
    make_canary_stream,
    make_null_stream,
    mean_pairwise_correlation,
    measure_channel_e_validity,
    measure_ville_bound,
    measured_pairwise_correlation,
    naive_votes_lr,
    optimism_alarm_judges,
    oracle_panel_lr,
    panel_vote_distribution,
    run_e_validity_experiment,
    run_monitor_policy_experiment,
    run_null_grid,
    run_policy_stream,
    run_rho_ablation,
    run_two_ledger_experiment,
    schedule_oracle_mismatch,
    shared_speech_alpha,
    simulate_panel,
    st_priority,
    synthesize_candidate_records,
    two_ledger_certification_wealth,
    two_sided_votes_lr,
    verification_e_validity_ceiling,
)
from attest.core.engine import Engine, EngineConfig
from attest.core.monitor import WinnersCurseMonitor
from attest.core.stream import make_stream
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
        "paired_resamples": 300,
    }
    kwargs.update(overrides)
    return run_rho_ablation(**kwargs)


def _cell(report: Any, gamma: float, alpha: float) -> Any:
    for cell in report.cells:
        if cell.clone_rate == gamma and cell.alpha == alpha:
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


def test_at_factory_alpha_the_independence_control_cannot_test_the_discount() -> None:
    """The control the ablation used to rest on, and what it actually shows.

    At the factory alphas the capped schedule cannot reach the gate at any vote
    count (D-008), so 'the discounted arm is not anti-conservative here' is the
    cap arithmetic restated. The cell is marked uninformative for that reason;
    only the naive arm is genuinely under test at these gates.
    """
    report = _ablation(gammas=(0.0,), n_tasks=2000)

    for alpha in FACTORY_ALPHAS:
        cell = _cell(report, 0.0, alpha)
        assert cell.both_arms_can_certify is False
        assert cell.discounted_can_certify is False
        assert cell.discounted.certifications == 0
        naive = cell.naive.wrong_certification_rate_per_candidate
        assert naive is not None and naive <= alpha

    control = report.derived["independence_control"]
    assert control and all(row["informative"] is False for row in control)


def test_the_independence_control_at_a_gate_both_arms_can_reach() -> None:
    """Objection 3, adjudicated: run the gamma=0 control where the discounted
    arm is not shielded, and it stops saying what it used to say.

    Under *perfect independence* the naive product is already anti-conservative
    at a gate it can share with the discount — it certifies on two votes, which
    a null panel produces often — while the discounted arm stays inside alpha.
    So the discount's advantage is not attributable to correlation pricing
    alone: a capped one-sided schedule is simply more conservative at a loose
    gate, correlation or no correlation.
    """
    alpha = shared_speech_alpha()
    low, high = discount_speech_window()
    assert low < alpha < high

    report = _ablation(gammas=(0.0,), alphas=(alpha,), n_tasks=2000)
    cell = _cell(report, 0.0, alpha)
    naive = cell.naive
    discounted = cell.discounted

    assert cell.both_arms_can_certify is True
    assert naive.wrong_certification_rate_per_candidate > alpha
    assert naive.exceeds_alpha_per_candidate is True
    assert discounted.wrong_certification_rate_per_candidate < alpha
    assert discounted.exceeds_alpha_per_candidate is False
    assert report.derived["independence_control"][0]["informative"] is True


def test_correlated_panels_inflate_the_naive_wrong_certification_rate() -> None:
    """The claim under test, on the denominator nominal alpha bounds."""
    report = _ablation(gammas=(0.9,), n_tasks=2000, seeds=DEFAULT_SEEDS)

    for alpha in FACTORY_ALPHAS:
        cell = _cell(report, 0.9, alpha)
        naive = cell.naive.wrong_certification_rate_per_candidate
        discounted = cell.discounted.wrong_certification_rate_per_candidate
        assert naive is not None and discounted is not None
        assert naive > discounted
        assert naive > alpha
        assert cell.naive.exceeds_alpha_per_candidate is True


def test_wrong_certification_rate_rises_with_correlation() -> None:
    """Monotone pressure, not a single lucky clone rate.

    On the per-candidate denominator the rise is strictly monotone across the
    whole preregistered sweep, including the top two points. The apparent
    saturation between clone rates 0.9 and 0.99 was an artifact of the per-task
    denominator: a near-degenerate panel is more often unanimously silent, so
    dividing by every task hides the last and largest step.
    """
    report = _ablation(gammas=DEFAULT_GAMMAS, alphas=(0.1,), n_tasks=2000)
    arms = [_cell(report, gamma, 0.1).naive for gamma in DEFAULT_GAMMAS]
    per_candidate = [arm.wrong_certification_rate_per_candidate for arm in arms]
    per_task = [arm.wrong_certification_rate_per_task for arm in arms]

    assert all(rate is not None for rate in per_candidate)
    for lower, higher in zip(per_candidate[:-1], per_candidate[1:], strict=True):
        assert lower < higher

    saturated = arms[-2].wrong_certification_interval_per_task
    extreme = arms[-1].wrong_certification_interval_per_task
    assert saturated is not None and extreme is not None
    assert saturated[0] <= extreme[1] and extreme[0] <= saturated[1]
    assert per_task[-1] - per_task[-2] < per_candidate[-1] - per_candidate[-2]


# --- objection 1: the denominator ------------------------------------------


def test_wrong_certifications_are_divided_by_candidates_as_well_as_tasks() -> None:
    """Objection 1, adjudicated: one numerator, two named denominators.

    Nominal alpha bounds the error rate over the findings the gate judges, and
    the gate only ever judges a finding some sample proposed. A per-task rate
    counts silent panels in the denominator and is therefore diluted; both are
    reported and both are named, so neither can be quoted as 'the rate'.
    """
    report = _ablation(gammas=(0.9,), alphas=(0.1,), n_tasks=2000)
    arm = _cell(report, 0.9, 0.1).naive

    assert arm.negative_candidate_tasks < arm.negative_tasks
    assert arm.wrong_certification_rate_per_task == pytest.approx(
        arm.wrong_certifications / arm.negative_tasks
    )
    assert arm.wrong_certification_rate_per_candidate == pytest.approx(
        arm.wrong_certifications / arm.negative_candidate_tasks
    )
    assert (
        arm.wrong_certification_rate_per_candidate > arm.wrong_certification_rate_per_task
    )
    assert arm.alpha_excess_per_candidate > arm.alpha_excess_per_task


def test_the_per_task_denominator_dilutes_most_where_correlation_is_highest() -> None:
    """Why the wrong denominator is not a harmless relabelling.

    A cloned panel is more often unanimously silent, so the share of tasks that
    ever produce a candidate falls as the clone rate rises. The dilution factor
    therefore grows with exactly the quantity the ablation is measuring, and a
    per-task comparison against alpha understates the effect it exists to show.
    """
    report = _ablation(gammas=DEFAULT_GAMMAS, alphas=(0.1,), n_tasks=2000)
    arms = [_cell(report, gamma, 0.1).naive for gamma in DEFAULT_GAMMAS]
    candidate_rates = [arm.negative_candidate_rate for arm in arms]
    dilution = [
        arm.wrong_certification_rate_per_candidate / arm.wrong_certification_rate_per_task
        for arm in arms
    ]

    for higher, lower in zip(candidate_rates[:-1], candidate_rates[1:], strict=True):
        assert higher > lower
    for smaller, larger in zip(dilution[:-1], dilution[1:], strict=True):
        assert smaller < larger
    assert dilution[0] < 1.2 < dilution[-1]


# --- objection 2: the arms are paired --------------------------------------


def test_the_arms_are_nested_so_every_discordant_pair_runs_one_way() -> None:
    """The structural fact that makes an independent-sample test wrong.

    Both arms are applied to the same panel and depend on it only through the
    vote count, and the naive product dominates the capped discount at every
    count, so the discounted arm certifies a subset of what the naive arm
    certifies. There is no draw in which the discount wrongly certifies and the
    naive product does not.
    """
    report = _ablation(gammas=DEFAULT_GAMMAS, alphas=(0.1, shared_speech_alpha()))

    for cell in report.cells:
        assert cell.paired.arms_are_nested is True
        assert cell.paired.discounted_only == 0
        assert cell.paired.pairs == cell.naive.negative_candidate_tasks
        assert cell.paired.pairs == cell.discounted.negative_candidate_tasks


def test_paired_analysis_separates_the_arms_where_intervals_overlap() -> None:
    """Objection 2, adjudicated: the check that exposes the wrong test.

    At the shared-speech gate and a clone rate of 0.9 the two arms' independent
    Wilson intervals overlap, which is what 'statistically indistinguishable'
    was read from. The arms are paired and nested, so the correct analysis is
    the discordant pairs — and they run one way in every draw, giving an exact
    McNemar p-value far below any conventional threshold and a paired difference
    interval that excludes zero.
    """
    alpha = shared_speech_alpha()
    report = _ablation(gammas=(0.9,), alphas=(alpha,), n_tasks=2000, seeds=DEFAULT_SEEDS)
    cell = _cell(report, 0.9, alpha)
    paired = cell.paired

    assert paired.intervals_overlap is True
    assert paired.naive_only > 0 and paired.discounted_only == 0
    assert paired.mcnemar_exact_p < 1e-6
    assert paired.difference_per_candidate > 0.0
    assert paired.difference_interval_per_candidate[0] > 0.0
    assert cell.label in report.derived["paired_verdict_disagrees_with_interval_overlap"]


def test_the_paired_difference_collapses_on_a_degenerate_panel() -> None:
    """What actually vanishes at the top of the sweep: the size of the gap.

    At a clone rate of 0.99 the panel is one witness repeated, almost no draw
    lands between the two thresholds, and the discordant pairs nearly disappear.
    The honest statement is that the discount's advantage shrinks to nothing —
    not that the two arms were ever indistinguishable in a draw that separated
    them.
    """
    alpha = shared_speech_alpha()
    report = _ablation(
        gammas=(0.9, 0.99), alphas=(alpha,), n_tasks=2000, seeds=DEFAULT_SEEDS
    )
    saturated = _cell(report, 0.9, alpha).paired
    degenerate = _cell(report, 0.99, alpha).paired

    assert degenerate.naive_only < saturated.naive_only
    assert degenerate.difference_per_candidate < saturated.difference_per_candidate
    assert degenerate.mcnemar_exact_p > saturated.mcnemar_exact_p


def test_a_cell_with_no_discordant_pairs_reports_no_p_value() -> None:
    """A test statistic over zero discordant pairs is unknown, never one.

    At a gate loose enough that both thresholds land on the same vote count the
    arms make identical decisions on every task. That is a property of the
    lattice and the draw, not a finding of equivalence.
    """
    alpha = 0.4
    report = _ablation(gammas=(0.0,), alphas=(alpha,), n_tasks=400)
    cell = _cell(report, 0.0, alpha)
    paired = cell.paired

    assert cell.both_arms_can_certify is True
    assert paired.pairs > 0
    assert paired.naive_only == 0 and paired.discounted_only == 0
    assert paired.mcnemar_exact_p is None
    assert paired.difference_per_candidate == 0.0
    assert cell.label not in report.derived["paired_separations"]


# --- objection 4: the correlation axis -------------------------------------


def test_the_clone_rate_is_not_the_pairwise_correlation() -> None:
    """Objection 4, adjudicated by measurement rather than by argument.

    Only vote one is cloned, so the panel is not exchangeable: a later vote is
    correlated with vote one at the clone rate, but two later votes agree only
    when both cloned vote one, at the square of it. The mean over pairs is
    strictly below the nominal clone rate everywhere in (0, 1), so labelling the
    sweep axis 'correlation' overstates it at every interior point.
    """
    accuracy = calibrated_vote_accuracy()
    for gamma in (0.3, RHO, 0.9):
        # theta is fixed, so every column correlation below is panel structure
        # and not two votes agreeing because they saw the same ground truth.
        fixed = simulate_panel(
            gamma=gamma,
            theta_prior=0.0,
            judge_accuracy=accuracy,
            k=5,
            n_tasks=200000,
            seed=101,
        )
        columns = np.corrcoef(fixed.ballots.astype(float), rowvar=False)
        with_first = float(np.mean([columns[0, j] for j in range(1, 5)]))
        among_rest = float(
            np.mean([columns[i, j] for i in range(1, 5) for j in range(i + 1, 5)])
        )
        analytic = mean_pairwise_correlation(k=5, gamma=gamma)

        assert with_first == pytest.approx(gamma, abs=0.01)
        assert among_rest == pytest.approx(gamma * gamma, abs=0.01)
        assert with_first > among_rest
        assert analytic < gamma
        assert measured_pairwise_correlation(fixed) == pytest.approx(analytic, abs=0.01)

        # The same measurement on a mixed-truth stream, where the shared theta
        # has to be partialled out before any of that is visible.
        mixed = simulate_panel(
            gamma=gamma,
            theta_prior=0.5,
            judge_accuracy=accuracy,
            k=5,
            n_tasks=200000,
            seed=101,
        )
        raw = np.corrcoef(mixed.ballots.astype(float), rowvar=False)
        raw_mean = float(
            np.mean([raw[i, j] for i in range(5) for j in range(i + 1, 5)])
        )
        assert measured_pairwise_correlation(mixed) == pytest.approx(analytic, abs=0.01)
        assert raw_mean > analytic


def test_the_reported_correlation_axis_is_the_measured_one() -> None:
    """Each cell carries the correlation it truly generates, not its nominal."""
    report = _ablation(gammas=DEFAULT_GAMMAS, alphas=(0.1,), n_tasks=2000)

    for gamma in DEFAULT_GAMMAS:
        cell = _cell(report, gamma, 0.1)
        assert cell.clone_rate == gamma
        assert cell.mean_pairwise_correlation == mean_pairwise_correlation(
            k=5, gamma=gamma
        )
        assert cell.measured_pairwise_correlation == pytest.approx(
            cell.mean_pairwise_correlation, abs=0.02
        )
        if 0.0 < gamma < 1.0:
            assert cell.mean_pairwise_correlation < gamma

    matching = report.derived["clone_rate_matching_rho"]
    assert matching > RHO
    assert mean_pairwise_correlation(k=5, gamma=matching) == pytest.approx(RHO)


def test_clone_rate_and_correlation_invert_each_other() -> None:
    """The relabelling has to be reversible or it is not a relabelling."""
    for k in (2, 3, 5, 8):
        for correlation in (0.0, 0.25, RHO, 0.9, 1.0):
            rate = clone_rate_for_pairwise_correlation(k=k, correlation=correlation)
            assert 0.0 <= rate <= 1.0
            assert mean_pairwise_correlation(k=k, gamma=rate) == pytest.approx(
                correlation
            )

    assert mean_pairwise_correlation(k=1, gamma=0.5) is None
    assert clone_rate_for_pairwise_correlation(k=1, correlation=0.5) is None


def test_no_clone_rate_makes_the_production_schedule_exact() -> None:
    """The second half of objection 4: 'the one level where D-007's assumption
    is literally true' does not exist at any correlation.

    The schedule is monotone non-decreasing in the vote count by construction.
    The exact vote-count likelihood ratio is not, once the panel is correlated:
    a middling count is evidence *against* a clone panel, which is nearly
    unanimous either way. Scanning the whole clone-rate axis, the best
    achievable worst-case disagreement is still large.
    """
    accuracy = calibrated_vote_accuracy()
    mismatch = schedule_oracle_mismatch(k=5, judge_accuracy=accuracy)

    assert mismatch["schedule_is_monotone"] is True
    assert mismatch["oracle_is_monotone_at_best_clone_rate"] is False
    assert mismatch["max_ratio"] > 2.0

    exact = oracle_panel_lr(k=5, judge_accuracy=accuracy, gamma=RHO)
    assert any(exact[votes] < exact[votes - 1] for votes in range(2, 6))
    assert any(
        abs(math.log(exact[votes] / VOTE_LR[votes])) > 0.5 for votes in range(1, 6)
    )


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
    alpha = shared_speech_alpha()
    report = _ablation(gammas=(0.9,), alphas=(alpha,), n_tasks=2000)
    cell = _cell(report, 0.9, alpha)

    assert low == pytest.approx(1.0 / S_CAP)
    assert high == pytest.approx(1.0 / VOTE_LR[2])
    assert alpha == pytest.approx((low + high) / 2)
    assert cell.both_arms_can_certify is True
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
            assert sum(row.negative_tasks for row in arm.per_seed) == arm.negative_tasks
            assert sum(row.negative_candidate_tasks for row in arm.per_seed) == (
                arm.negative_candidate_tasks
            )
        assert cell.naive.aggregator == NAIVE_ARM
        assert cell.discounted.aggregator == DISCOUNTED_ARM


def test_wilson_intervals_are_present_and_finite() -> None:
    """Uncertainty must travel with every reported rate, on both denominators."""
    report = _ablation(gammas=(0.9,), alphas=(0.1,), n_tasks=1000)
    naive = _cell(report, 0.9, 0.1).naive
    pairs = (
        (naive.wrong_certification_rate_per_task, naive.wrong_certification_interval_per_task),
        (
            naive.wrong_certification_rate_per_candidate,
            naive.wrong_certification_interval_per_candidate,
        ),
    )

    for rate, interval in pairs:
        assert interval is not None
        low, high = interval
        assert math.isfinite(low) and math.isfinite(high)
        assert 0.0 <= low <= rate <= high <= 1.0


def test_empty_denominators_report_none_rather_than_zero() -> None:
    """A rate over zero observations is unknown, not zero."""
    report = _ablation(gammas=(0.9,), alphas=(0.1,), theta_prior=1.0, n_tasks=200)
    naive = _cell(report, 0.9, 0.1).naive

    assert naive.negative_tasks == 0
    assert naive.negative_candidate_tasks == 0
    assert naive.wrong_certification_rate_per_task is None
    assert naive.wrong_certification_interval_per_task is None
    assert naive.wrong_certification_rate_per_candidate is None
    assert naive.wrong_certification_interval_per_candidate is None
    assert naive.alpha_excess_per_candidate is None
    assert naive.exceeds_alpha_per_candidate is False

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
    assert "per_candidate" in notes
    assert "Overlapping independent Wilson intervals are NOT" in notes
    assert "clone_rate_is_not_correlation" in notes
    assert payload["constants"] == {
        "lr1": LR1,
        "rho": RHO,
        "s_cap": S_CAP,
        "vote_lr": list(VOTE_LR),
    }
    assert payload["status"] == report.status
    assert payload["config"]["gammas_are_clone_rates"] is True
    assert payload["cells"][0]["clone_rate"] == report.cells[0].clone_rate
    assert "mean_pairwise_correlation" in payload["cells"][0]
    assert "paired" in payload["cells"][0]
    assert "gamma" not in payload["cells"][0]


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
        {"paired_resamples": 0},
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


# ===========================================================================
# Task 8 remainder, experiment A: multi-seed null grids on the REAL core
# engine. These tests pin the protocol — the null stream construction, the
# use of the shipped Engine, determinism, and the reporting contract — never
# a hand-picked zero-error seed.
# ===========================================================================


_GRID_SEEDS = (11, 22)


def _null_grid(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "alphas": (0.1, 0.2),
        "stream_lengths": (300,),
        "panel_gammas": (0.0, 0.9),
        "seeds": _GRID_SEEDS,
    }
    kwargs.update(overrides)
    return run_null_grid(**kwargs)


def _grid_cell(report: Any, gamma: float, alpha: float, length: int) -> Any:
    for cell in report.cells:
        if (cell.clone_gamma, cell.alpha, cell.stream_length) == (gamma, alpha, length):
            return cell
    raise AssertionError("missing null-grid cell")


def test_null_stream_is_make_streams_draw_under_a_null_truth() -> None:
    """The null stream must be the REAL make_stream draw, re-expressed with a
    null ground truth: each judge's per-task agreement is preserved exactly, so
    the verdict is the original XOR the original truth, and the clone edge
    between B and C survives the transformation."""
    acc_a, acc_b, acc_c = NULL_GRID_ACCURACIES
    stream = make_stream(acc_a, acc_b, acc_c, 0.9, seed=11, n=300, warmup=0)
    null = make_null_stream(acc_a, acc_b, acc_c, 0.9, seed=11, n=300)

    assert (null.theta == 0).all()
    for judge in ("A", "B", "C"):
        assert (
            null.verdicts[judge] == np.bitwise_xor(stream.verdicts[judge], stream.theta)
        ).all()

    cloned = make_null_stream(acc_a, acc_b, acc_c, 1.0, seed=11, n=300)
    assert (cloned.verdicts["C"] == cloned.verdicts["B"]).all()


def test_null_grid_report_is_deterministic() -> None:
    first = _null_grid()
    second = _null_grid()
    shifted = _null_grid(seeds=(11, 23))

    assert first.digest == second.digest
    assert len(first.digest) == 64
    assert first.to_json_dict() == second.to_json_dict()
    assert first.digest != shifted.digest

    payload = first.to_json_dict()
    digest = payload.pop("digest")
    assert digest == first.digest
    assert json.dumps(payload, sort_keys=True)


def test_null_grid_runs_the_real_core_engine() -> None:
    """Protocol pin: a per-seed row must be exactly what the shipped Engine
    produces on the same null stream with the same engine seed. If the harness
    forked the engine, this equality would be the first thing to break."""
    report = _null_grid(alphas=(0.1,), panel_gammas=(0.0,), stream_lengths=(300,))
    cell = _grid_cell(report, 0.0, 0.1, 300)

    acc_a, acc_b, acc_c = NULL_GRID_ACCURACIES
    stream = make_null_stream(acc_a, acc_b, acc_c, 0.0, seed=11, n=300)
    engine = Engine(EngineConfig(alpha=0.1, seed=11))
    results = engine.run_stream(stream)
    surfaced = sum(1 for _, res in results if res.decision == 1)
    discarded = sum(1 for _, res in results if res.decision == 0)
    spend = sum(sum(res.spend.values()) for _, res in results)

    row = next(row for row in cell.per_seed if row.seed == 11)
    assert row.tasks == 300
    assert row.certifications == surfaced
    assert row.wrong_certifications == surfaced
    assert row.discards == discarded
    assert row.abstentions == 300 - surfaced - discarded
    assert row.total_spend == pytest.approx(spend)
    assert set(row.alarm_kinds) <= {"winners_curse_optimism", "spend_share_drift"}


def test_null_grid_covers_every_preregistered_axis_and_seed() -> None:
    report = _null_grid()

    assert len(report.cells) == 2 * 2 * 1
    labels = [cell.label for cell in report.cells]
    assert len(set(labels)) == len(labels)
    for cell in report.cells:
        assert tuple(row.seed for row in cell.per_seed) == _GRID_SEEDS
        assert sum(row.tasks for row in cell.per_seed) == cell.tasks
        assert sum(row.certifications for row in cell.per_seed) == cell.certifications
        assert (
            sum(row.wrong_certifications for row in cell.per_seed)
            == cell.wrong_certifications
        )
        assert sum(row.abstentions for row in cell.per_seed) == cell.abstentions
        assert cell.panel == ("independent" if cell.clone_gamma == 0.0 else "correlated")


def test_null_grid_reports_rates_intervals_and_alarm_kinds() -> None:
    report = _null_grid()

    for cell in report.cells:
        assert cell.wrong_certifications == cell.certifications
        assert cell.wrong_certification_rate_per_task == pytest.approx(
            cell.wrong_certifications / cell.tasks
        )
        interval = cell.wrong_certification_interval_per_task
        assert interval is not None
        low, high = interval
        assert 0.0 <= low <= cell.wrong_certification_rate_per_task <= high <= 1.0
        assert set(cell.alarm_kinds_fired) <= {
            "winners_curse_optimism",
            "spend_share_drift",
        }
        assert cell.runs == len(_GRID_SEEDS)
        assert 0 <= cell.runs_with_any_alarm <= cell.runs
        assert cell.abstention_rate == pytest.approx(cell.abstentions / cell.tasks)


def test_null_grid_defaults_match_the_preregistered_protocol() -> None:
    """The defaults are the preregistration: three alphas including both
    factory gates, independent and correlated panels, several lengths, and
    twenty seeds — not one favourable configuration."""
    assert DEFAULT_NULL_GRID_ALPHAS == (0.05, 0.1, 0.2)
    assert set(FACTORY_ALPHAS) <= set(DEFAULT_NULL_GRID_ALPHAS)
    assert 0.0 in DEFAULT_NULL_GRID_PANEL_GAMMAS
    assert any(gamma > 0.5 for gamma in DEFAULT_NULL_GRID_PANEL_GAMMAS)
    assert len(DEFAULT_NULL_GRID_LENGTHS) >= 2
    assert len(DEFAULT_NULL_GRID_SEEDS) == 20
    assert len(set(DEFAULT_NULL_GRID_SEEDS)) == 20


def test_null_grid_declares_its_honesty_and_provenance() -> None:
    report = _null_grid()
    payload = report.to_json_dict()
    notes = " ".join(report.honesty)

    assert report.status == "insufficient_labels/recommendation_only"
    assert report.offline is True
    assert "null-only" in notes
    assert "synthetic" in notes
    assert "500" in notes
    assert "no_seed_selection" in notes

    external = report.derived["prior_external_measurement"]
    assert external["independently_reproduced"] is False
    assert "owner-provided" in external["note"]

    monitor = WinnersCurseMonitor()
    constants = payload["constants"]
    assert constants["monitor"]["window"] == monitor.window
    assert constants["monitor"]["optimism_threshold"] == monitor.optimism_threshold
    assert constants["monitor"]["drift_threshold"] == monitor.drift_threshold
    engine_defaults = EngineConfig()
    assert constants["engine"]["variant"] == engine_defaults.variant
    assert constants["engine"]["tau"] == engine_defaults.tau
    assert constants["engine"]["cell_target"] == engine_defaults.cell_target


@pytest.mark.parametrize(
    "override",
    [
        {"alphas": ()},
        {"alphas": (0.0,)},
        {"alphas": (1.0,)},
        {"stream_lengths": ()},
        {"stream_lengths": (0,)},
        {"panel_gammas": ()},
        {"panel_gammas": (1.5,)},
        {"seeds": ()},
        {"seeds": (1, 1)},
        {"accuracies": (0.8, 0.75)},
        {"accuracies": (0.8, 0.75, 1.5)},
        {"alarm_poll_every": 0},
    ],
)
def test_null_grid_rejects_an_invalid_configuration(override: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _null_grid(**override)


def test_null_grid_cli_writes_deterministic_offline_json(tmp_path: Path) -> None:
    cli = _cli()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    argv = [
        "experiment-nullgrid",
        "--alphas",
        "0.1",
        "--lengths",
        "200",
        "--panel-gammas",
        "0.0",
        "0.9",
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
    assert payload["experiment"] == "core_engine_null_grid"
    assert len(payload["cells"]) == 2


def test_null_grid_cli_rejects_an_invalid_configuration(tmp_path: Path) -> None:
    cli = _cli()
    output = tmp_path / "out.json"
    code = cli.main(
        [
            "experiment-nullgrid",
            "--alphas",
            "1.5",
            "--lengths",
            "100",
            "--panel-gammas",
            "0.0",
            "--seeds",
            "11",
            "--output",
            str(output),
        ]
    )

    assert code == 2
    assert not output.exists()


# ===========================================================================
# Task 8 remainder, experiment B: monitor intervention policies. The policy
# driver must be the shipped engine loop with two reversible interventions
# added; its ledger-only mode is pinned equal to the real Engine, and drift
# alarms are never allowed to trigger a brake.
# ===========================================================================


_POLICY_SEEDS = (11, 22)


def _policy_report(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "alpha": 0.1,
        "n_tasks": 600,
        "seeds": _POLICY_SEEDS,
    }
    kwargs.update(overrides)
    return run_monitor_policy_experiment(**kwargs)


def _policy_cell(report: Any, configuration: str, policy: str) -> Any:
    for cell in report.cells:
        if (cell.configuration, cell.policy) == (configuration, policy):
            return cell
    raise AssertionError("missing policy cell")


def _canary_stream(seed: int = 11, n: int = 1200) -> Any:
    acc_a, acc_b, acc_c = NULL_GRID_ACCURACIES
    return make_canary_stream(
        acc_a,
        acc_b,
        acc_c,
        0.0,
        seed=seed,
        n=n,
        canary_accuracy=0.1,
        shift=n // 2,
    )


def test_ledger_only_policy_reproduces_the_shipped_engine_exactly() -> None:
    """Protocol pin, the experiment's licence to exist: with no intervention,
    the policy driver and the real Engine must produce identical decisions,
    wealth, exploration flags, and spend on the same stream and seed. The
    driver is a rebuild of Engine.review_task (the same approach the Ville
    section takes to gate.evaluate_finding), and this equality is what keeps
    the rebuild honest."""
    acc_a, acc_b, acc_c = NULL_GRID_ACCURACIES
    stream = make_stream(acc_a, acc_b, acc_c, 0.0, seed=5, n=400, warmup=0)
    engine = Engine(EngineConfig(alpha=0.1, seed=5))
    results = engine.run_stream(stream)

    run = run_policy_stream(stream, alpha=0.1, policy=POLICY_LEDGER_ONLY, engine_seed=5)

    assert run.policy == POLICY_LEDGER_ONLY
    assert list(run.decisions) == [res.decision for _, res in results]
    for ours, (_, theirs) in zip(run.wealth, results, strict=True):
        assert ours == pytest.approx(theirs.wealth)
    assert list(run.explored) == [res.explored for _, res in results]
    assert list(run.orders) == [tuple(res.order) for _, res in results]
    assert sum(run.spend) == pytest.approx(
        sum(sum(res.spend.values()) for _, res in results)
    )
    assert run.intervention_episodes == 0
    assert not any(run.intervention_active)
    assert not any(run.forced_exploration)


def test_optimism_alarm_judges_ignores_spend_share_drift() -> None:
    """D-004 separation: drift alone is never evidence of invalid evidence,
    so the intervention trigger reads only winners_curse_optimism alarms."""
    alarms = [
        {"kind": "spend_share_drift", "judge": "A", "drift": 0.4},
        {
            "kind": "winners_curse_optimism",
            "judge": "C",
            "mean_realized_minus_estimated": -0.3,
        },
        {
            "kind": "winners_curse_optimism",
            "judge": "B",
            "mean_realized_minus_estimated": -0.2,
        },
    ]

    assert optimism_alarm_judges(alarms) == ("B", "C")
    assert optimism_alarm_judges([alarms[0]]) == ()
    assert optimism_alarm_judges([]) == ()


def test_canary_stream_shifts_only_the_canary_judge_after_the_shift() -> None:
    acc_a, acc_b, acc_c = NULL_GRID_ACCURACIES
    healthy = make_stream(acc_a, acc_b, acc_c, 0.0, seed=11, n=1200, warmup=0)
    canary = _canary_stream(seed=11, n=1200)

    assert (canary.theta == healthy.theta).all()
    assert (canary.verdicts["B"] == healthy.verdicts["B"]).all()
    assert (canary.verdicts["C"] == healthy.verdicts["C"]).all()
    assert (canary.verdicts["A"][:600] == healthy.verdicts["A"][:600]).all()
    assert (canary.verdicts["A"][600:] != healthy.verdicts["A"][600:]).any()

    post = canary.verdicts["A"][600:]
    truth = canary.theta[600:]
    agreement = float((post == truth).mean())
    assert agreement < 0.2


def test_interventions_trigger_exactly_when_an_optimism_alarm_is_active() -> None:
    """Reversibility and the trigger, in one pin: the intervention is active on
    precisely the tasks where the rolling window shows a winners_curse_optimism
    alarm — it switches on with the alarm and off when the window clears, and
    drift alarms never activate it."""
    stream = _canary_stream()

    quarantine = run_policy_stream(
        stream, alpha=0.1, policy=POLICY_QUARANTINE, engine_seed=11
    )
    recovery = run_policy_stream(
        stream, alpha=0.1, policy=POLICY_EXPLORATION_RECOVERY, engine_seed=11
    )
    ledger = run_policy_stream(
        stream, alpha=0.1, policy=POLICY_LEDGER_ONLY, engine_seed=11
    )

    assert list(quarantine.intervention_active) == list(quarantine.optimism_active)
    assert list(recovery.forced_exploration) == list(recovery.optimism_active)
    assert list(recovery.intervention_active) == list(recovery.optimism_active)
    assert not any(ledger.intervention_active)
    assert any(quarantine.optimism_active)
    assert quarantine.intervention_episodes >= 1


def test_quarantine_removes_the_optimistic_judge_from_adaptive_purchases() -> None:
    """The quarantined judge is never bought adaptively while the alarm is
    active, but exploration tasks still buy every judge — that is what lets the
    tables recover and the alarm clear, which makes the policy reversible."""
    stream = _canary_stream()
    run = run_policy_stream(stream, alpha=0.1, policy=POLICY_QUARANTINE, engine_seed=11)

    quarantined_adaptive = [
        index
        for index in range(len(run.decisions))
        if run.quarantined[index] and not run.explored[index]
    ]
    assert quarantined_adaptive
    for index in quarantined_adaptive:
        assert not set(run.orders[index]) & set(run.quarantined[index])

    quarantined_explored = [
        index
        for index in range(len(run.decisions))
        if run.quarantined[index] and run.explored[index]
    ]
    for index in quarantined_explored:
        assert set(run.orders[index]) == {"A", "B", "C"}


def test_the_canary_produces_wrong_certifications_without_intervention() -> None:
    """A canary that never errs tests nothing. Under ledger-only monitoring the
    stale-table shift must actually produce wrong certifications, or the
    missed-unsafe-run metric would be vacuous."""
    report = _policy_report(seeds=(11, 22, 33), n_tasks=1500)
    cell = _policy_cell(report, CANARY_CONFIGURATION, POLICY_LEDGER_ONLY)

    assert cell.wrong_certifications > 0
    assert cell.wrong_certifications_post_shift > 0


def test_policy_cells_cover_every_configuration_and_seed() -> None:
    report = _policy_report()

    assert len(report.cells) == 2 * len(MONITOR_POLICIES)
    for cell in report.cells:
        assert cell.configuration in (HEALTHY_CONFIGURATION, CANARY_CONFIGURATION)
        assert cell.policy in MONITOR_POLICIES
        assert tuple(row.seed for row in cell.per_seed) == _POLICY_SEEDS
        assert sum(row.tasks for row in cell.per_seed) == cell.tasks
        assert (
            sum(row.wrong_certifications for row in cell.per_seed)
            == cell.wrong_certifications
        )
        assert sum(row.abstentions for row in cell.per_seed) == cell.abstentions
        assert cell.runs == len(_POLICY_SEEDS)
        rate = cell.wrong_certification_rate_per_task
        assert rate == pytest.approx(cell.wrong_certifications / cell.tasks)
        assert cell.wrong_certification_interval_per_task is not None


def test_false_brakes_and_missed_runs_live_on_the_right_cells() -> None:
    """False brakes are only measurable where nothing is wrong; missed unsafe
    runs only where something is. The ledger-only arm cannot brake at all, so
    its 'response' is the optimism alarm itself and its false-brake rate is
    unknown rather than zero."""
    report = _policy_report()

    for policy in MONITOR_POLICIES:
        healthy = _policy_cell(report, HEALTHY_CONFIGURATION, policy)
        canary = _policy_cell(report, CANARY_CONFIGURATION, policy)

        assert healthy.missed_unsafe_run_rate is None
        assert canary.false_brake_rate is None
        if policy == POLICY_LEDGER_ONLY:
            assert healthy.intervention_capable is False
            assert healthy.false_brake_rate is None
            assert canary.missed_unsafe_run_rate == pytest.approx(
                (canary.runs - canary.runs_with_optimism_alarm) / canary.runs
            )
        else:
            assert healthy.intervention_capable is True
            assert healthy.false_brake_rate == pytest.approx(
                healthy.runs_with_intervention / healthy.runs
            )
            assert canary.missed_unsafe_run_rate == pytest.approx(
                (canary.runs - canary.runs_with_intervention) / canary.runs
            )


def test_the_report_says_whether_any_policy_catches_the_canary() -> None:
    report = _policy_report()
    derived = report.derived

    catching = derived["policies_catching_canary"]
    assert isinstance(catching, list)
    assert derived["canary_caught_by_any_policy"] == bool(catching)
    for policy in catching:
        cell = _policy_cell(report, CANARY_CONFIGURATION, policy)
        assert cell.runs_with_response > 0
    assert set(derived["canary_wrong_certifications_by_policy"]) == set(MONITOR_POLICIES)


def test_policy_report_is_deterministic() -> None:
    first = _policy_report()
    second = _policy_report()
    shifted = _policy_report(seeds=(11, 23))

    assert first.digest == second.digest
    assert first.to_json_dict() == second.to_json_dict()
    assert first.digest != shifted.digest

    payload = first.to_json_dict()
    digest = payload.pop("digest")
    assert digest == first.digest
    assert json.dumps(payload, sort_keys=True)


def test_policy_report_declares_its_honesty() -> None:
    report = _policy_report()
    notes = " ".join(report.honesty)

    assert report.status == "insufficient_labels/recommendation_only"
    assert report.offline is True
    assert "synthetic" in notes
    assert "500" in notes
    assert "no_seed_selection" in notes
    assert "spend_share_drift" in notes
    assert "winners_curse_optimism" in notes
    assert "rebuild" in notes


@pytest.mark.parametrize(
    "override",
    [
        {"alpha": 0.0},
        {"alpha": 1.0},
        {"n_tasks": 0},
        {"seeds": ()},
        {"seeds": (1, 1)},
        {"gamma": 1.5},
        {"canary_accuracy": 1.5},
        {"canary_shift_fraction": 0.0},
        {"canary_shift_fraction": 1.0},
        {"policies": ()},
        {"policies": ("unknown_policy",)},
        {"accuracies": (0.8, 0.75, 1.5)},
    ],
)
def test_policy_report_rejects_an_invalid_configuration(
    override: dict[str, Any],
) -> None:
    with pytest.raises(ValueError):
        _policy_report(**override)


def test_policy_cli_writes_deterministic_offline_json(tmp_path: Path) -> None:
    cli = _cli()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    argv = [
        "experiment-monitor",
        "--alpha",
        "0.1",
        "--tasks",
        "400",
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
    assert payload["experiment"] == "monitor_intervention_policies"
    assert len(payload["cells"]) == 2 * len(MONITOR_POLICIES)


def test_policy_cli_rejects_an_invalid_configuration(tmp_path: Path) -> None:
    cli = _cli()
    output = tmp_path / "out.json"
    code = cli.main(
        [
            "experiment-monitor",
            "--alpha",
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


# ===========================================================================
# Task 8 remainder, experiment C: V-only speech with S/T as ranking — the
# two-ledger model. Speech stays exactly certification_wealth >= 1/alpha;
# S/T order the verification queue and buy nothing. The record shape accepts
# real labeled data later; nothing here is a patch.
# ===========================================================================


_LEDGER_SEEDS = (11, 22)


def _two_ledger(**overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "alphas": (0.05, 0.1, 0.4),
        "k": 5,
        "n_tasks": 400,
        "seeds": _LEDGER_SEEDS,
        "bootstrap_resamples": 200,
    }
    kwargs.update(overrides)
    return run_two_ledger_experiment(**kwargs)


def _ledger_cell(report: Any, alpha: float, rate: float) -> Any:
    for cell in report.cells:
        if (cell.alpha, cell.false_reproduce_rate) == (alpha, rate):
            return cell
    raise AssertionError("missing two-ledger cell")


def test_candidate_records_share_draws_across_the_rate_sweep() -> None:
    """Sweeping the assumed false-reproduction rate must re-threshold the same
    uniforms, not redraw the panel: truth, votes, signals, and every true
    finding's outcome are identical across rates, and only null outcomes move."""
    kwargs: dict[str, Any] = {
        "k": 5,
        "gamma": RHO,
        "judge_accuracy": 0.65,
        "n_tasks": 400,
        "seed": 11,
        "assumptions": DEFAULT_TWO_LEDGER_ASSUMPTIONS,
    }
    zero = synthesize_candidate_records(false_reproduce_rate=0.0, **kwargs)
    half = synthesize_candidate_records(false_reproduce_rate=0.5, **kwargs)
    again = synthesize_candidate_records(false_reproduce_rate=0.0, **kwargs)

    assert zero == again
    assert len(zero) == len(half)
    for low, high in zip(zero, half, strict=True):
        assert (low.candidate_id, low.theta, low.votes, low.tier0_signals) == (
            high.candidate_id,
            high.theta,
            high.votes,
            high.tier0_signals,
        )
        assert low.votes >= 1
        if low.theta == 1:
            assert low.verification_outcome == high.verification_outcome
        if low.theta == 0:
            assert low.verification_outcome != OUTCOME_REPRODUCED

    assert any(
        record.verification_outcome == OUTCOME_REPRODUCED
        for record in half
        if record.theta == 0
    )


def test_two_ledger_speech_is_exactly_the_certification_wealth_threshold() -> None:
    """certification_wealth is purchased by V and only V; speech remains
    wealth >= 1/alpha through the shipped decide()."""
    assert two_ledger_certification_wealth(OUTCOME_REPRODUCED, verified=True) == V_CAP
    assert (
        two_ledger_certification_wealth(OUTCOME_NOT_REPRODUCED, verified=True) == V_FAILED
    )
    assert two_ledger_certification_wealth(OUTCOME_NO_PURCHASE, verified=True) == 1.0
    assert two_ledger_certification_wealth(OUTCOME_REPRODUCED, verified=False) == 1.0
    with pytest.raises(ValueError):
        two_ledger_certification_wealth("unknown", verified=True)

    reproduced = CandidateRecord(
        candidate_id="external/1",
        seed=0,
        theta=0,
        votes=3,
        tier0_signals=1,
        verification_outcome=OUTCOME_REPRODUCED,
    )
    failed = CandidateRecord(
        candidate_id="external/2",
        seed=0,
        theta=0,
        votes=3,
        tier0_signals=1,
        verification_outcome=OUTCOME_NOT_REPRODUCED,
    )

    assert arm_decisions(reproduced, alpha=0.1) == (1, 1)
    assert arm_decisions(failed, alpha=0.1) == (None, None)
    assert arm_decisions(reproduced, alpha=0.04) == (1, None)
    assert arm_decisions(reproduced, alpha=0.1, verified=False) == (None, None)


def test_factory_arm_follows_the_gate_purchase_order() -> None:
    """The factory arm is the shipped purchase order with early stopping: at a
    loose gate two votes certify before V is ever bought, and at a factory gate
    the wealth is the full S*T*V product."""
    assert factory_terminal_wealth(
        votes=2, signals=1, outcome=OUTCOME_REPRODUCED, alpha=0.4, verified=True
    ) == pytest.approx(votes_lr(2))
    assert factory_terminal_wealth(
        votes=1, signals=1, outcome=OUTCOME_REPRODUCED, alpha=0.05, verified=True
    ) == pytest.approx(votes_lr(1) * tier0_lr(1) * V_CAP)
    assert factory_terminal_wealth(
        votes=1, signals=0, outcome=OUTCOME_NOT_REPRODUCED, alpha=0.05, verified=True
    ) == pytest.approx(votes_lr(1) * V_FAILED)
    assert factory_terminal_wealth(
        votes=1, signals=2, outcome=OUTCOME_NO_PURCHASE, alpha=0.05, verified=True
    ) == pytest.approx(votes_lr(1) * tier0_lr(2))


def test_the_arms_are_nested_and_analysed_as_paired_data() -> None:
    """Both arms see the same draws, and the two-ledger certification set is a
    subset of the factory's, so every discordant pair runs one way and the
    paired machinery — not interval overlap — is the comparison."""
    report = _two_ledger()

    for cell in report.cells:
        paired = cell.paired
        assert paired.arms_are_nested is True
        assert paired.two_ledger_only == 0
        assert paired.pairs == cell.factory.null_candidates
        assert paired.pairs == cell.two_ledger.null_candidates
        assert paired.denominator == "null_candidate_tasks"


def test_wrong_certifications_carry_both_denominators() -> None:
    report = _two_ledger()
    cell = _ledger_cell(report, 0.4, DEFAULT_TWO_LEDGER_ASSUMPTIONS.false_reproduce_rate)
    arm = cell.factory

    assert arm.null_candidates < arm.null_tasks
    assert arm.wrong_certification_rate_per_null_candidate == pytest.approx(
        arm.wrong_certifications / arm.null_candidates
    )
    assert arm.wrong_certification_rate_per_null_task == pytest.approx(
        arm.wrong_certifications / arm.null_tasks
    )
    assert (
        arm.wrong_certification_rate_per_null_candidate
        > arm.wrong_certification_rate_per_null_task
    )


def test_zero_false_reproduction_silences_both_arms_at_factory_alpha() -> None:
    """At the factory gates neither arm can speak without V (cap arithmetic),
    so with an assumed false-reproduction rate of zero the wrong-certification
    count is exactly zero in both arms — and the report must say that this is
    the assumption speaking, not a measurement."""
    report = _two_ledger()

    for alpha in (0.05, 0.1):
        cell = _ledger_cell(report, alpha, 0.0)
        assert cell.is_factory_alpha == (alpha in FACTORY_ALPHAS)
        assert cell.factory.wrong_certifications == 0
        assert cell.two_ledger.wrong_certifications == 0
        assert cell.paired.mcnemar_exact_p is None


def test_a_loose_gate_separates_the_arms() -> None:
    """At alpha 0.4 the factory arm certifies on votes alone, which the
    two-ledger arm never does; the discordant pairs all run one way and the
    paired difference excludes zero."""
    rate = DEFAULT_TWO_LEDGER_ASSUMPTIONS.false_reproduce_rate
    report = _two_ledger()
    cell = _ledger_cell(report, 0.4, rate)

    assert cell.factory.wrong_certifications > 0
    assert cell.paired.factory_only > 0
    assert cell.paired.mcnemar_exact_p is not None
    assert cell.paired.mcnemar_exact_p < 1e-3
    assert cell.paired.difference_per_null_candidate > 0.0
    assert cell.paired.difference_interval_per_null_candidate[0] > 0.0
    assert cell.label in report.derived["cells_where_arms_differ"]

    assert cell.two_ledger.wrong_certification_rate_per_null_candidate <= (
        cell.factory.wrong_certification_rate_per_null_candidate
    )
    assert cell.two_ledger.discards == 0
    assert cell.two_ledger.abstention_rate > cell.factory.abstention_rate


def test_speech_feasibility_is_reported_per_alpha() -> None:
    report = _two_ledger(alphas=(0.04, 0.1))
    feasibility = report.derived["speech_feasibility"]

    for alpha in (0.04, 0.1):
        entry = feasibility[str(alpha)]
        assert entry["two_ledger_v_only"] == (1.0 / alpha <= V_CAP)
        assert entry["factory_with_verification"] == (
            1.0 / alpha <= S_CAP * T_CAP * V_CAP
        )
        assert entry["factory_without_verification"] == (1.0 / alpha <= S_CAP * T_CAP)

    rate = DEFAULT_TWO_LEDGER_ASSUMPTIONS.false_reproduce_rate
    infeasible = _ledger_cell(report, 0.04, rate)
    assert infeasible.two_ledger.certifications == 0


def test_voi_ordering_saves_verification_budget_at_fixed_recall() -> None:
    """The owner's number: the budget the S/T priority queue needs to reach a
    fixed recall, against first-come-first-served, on the same draws."""
    report = _two_ledger(n_tasks=800)

    assert report.budget
    for row in report.budget:
        assert 0.0 < row.recall_target <= 1.0
        if row.budget_voi is not None and row.budget_fcfs is not None:
            assert row.budget_voi <= row.budget_fcfs
            assert row.cost_voi == pytest.approx(
                row.budget_voi * row.verification_cost_per_candidate
            )
            if row.budget_fcfs > 0:
                assert row.budget_saving_fraction == pytest.approx(
                    1.0 - row.budget_voi / row.budget_fcfs
                )
        assert tuple(entry.seed for entry in row.per_seed) == _LEDGER_SEEDS

    savings = [
        row.budget_saving_fraction
        for row in report.budget
        if row.budget_saving_fraction is not None
    ]
    assert savings
    assert any(saving > 0.0 for saving in savings)


def test_st_priority_is_the_st_wealth_and_buys_nothing() -> None:
    """The ranking score is the S*T wealth the factory would hold before V —
    used only to order the verification queue in the two-ledger arm."""
    assert st_priority(votes=3, tier0_signals=1) == pytest.approx(
        votes_lr(3) * tier0_lr(1)
    )
    assert st_priority(votes=1, tier0_signals=0) == pytest.approx(votes_lr(1))
    assert st_priority(votes=5, tier0_signals=2) > st_priority(votes=1, tier0_signals=0)


def test_two_ledger_report_is_deterministic() -> None:
    first = _two_ledger()
    second = _two_ledger()
    shifted = _two_ledger(seeds=(11, 23))

    assert first.digest == second.digest
    assert first.to_json_dict() == second.to_json_dict()
    assert first.digest != shifted.digest

    payload = first.to_json_dict()
    digest = payload.pop("digest")
    assert digest == first.digest
    assert json.dumps(payload, sort_keys=True)


def test_two_ledger_cells_report_every_seed() -> None:
    report = _two_ledger()

    assert len(report.cells) == 3 * len(
        DEFAULT_TWO_LEDGER_ASSUMPTIONS.false_reproduce_rates()
    )
    for cell in report.cells:
        for arm in (cell.factory, cell.two_ledger):
            assert tuple(row.seed for row in arm.per_seed) == _LEDGER_SEEDS
            assert sum(row.wrong_certifications for row in arm.per_seed) == (
                arm.wrong_certifications
            )
            assert sum(row.null_candidates for row in arm.per_seed) == arm.null_candidates
            assert sum(row.true_certifications for row in arm.per_seed) == (
                arm.true_certifications
            )
        assert cell.factory.arm == FACTORY_LEDGER_ARM
        assert cell.two_ledger.arm == TWO_LEDGER_ARM


def test_two_ledger_report_declares_its_honesty() -> None:
    report = _two_ledger()
    payload = report.to_json_dict()
    notes = " ".join(report.honesty)

    assert report.status == "insufficient_labels/recommendation_only"
    assert report.offline is True
    assert "synthetic" in notes
    assert "500" in notes
    assert "no_seed_selection" in notes
    assert "certification_wealth >= 1/alpha" in notes
    assert "NOT a proposed" in notes or "not a patch" in notes
    assert "ASSUMPTION" in notes
    assert payload["config"]["assumptions"]["measured"] is False
    assert "interfaces_a_two_ledger_model_would_change" in report.derived
    assert set(DEFAULT_TWO_LEDGER_ALPHAS) >= set(FACTORY_ALPHAS)


@pytest.mark.parametrize(
    "override",
    [
        {"alphas": ()},
        {"alphas": (0.0,)},
        {"alphas": (1.0,)},
        {"k": 0},
        {"n_tasks": 0},
        {"seeds": ()},
        {"seeds": (1, 1)},
        {"gamma": 1.5},
        {"judge_accuracy": 0.0},
        {"recall_targets": ()},
        {"recall_targets": (0.0,)},
        {"recall_targets": (1.5,)},
        {"verification_cost": 0.0},
        {"bootstrap_resamples": 0},
        {"assumptions": TwoLedgerAssumptions(true_reproduce_rate=1.5)},
        {"assumptions": TwoLedgerAssumptions(false_reproduce_rate=1.5)},
        {
            "assumptions": TwoLedgerAssumptions(
                false_reproduce_rate=0.6, verification_no_purchase_rate=0.5
            )
        },
        {"assumptions": TwoLedgerAssumptions(tier0_signal_slots=-1)},
    ],
)
def test_two_ledger_rejects_an_invalid_configuration(override: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        _two_ledger(**override)


def test_two_ledger_cli_writes_deterministic_offline_json(tmp_path: Path) -> None:
    cli = _cli()
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    argv = [
        "experiment-twoledger",
        "--alphas",
        "0.1",
        "0.4",
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
    assert payload["experiment"] == "v_only_speech_two_ledger"
    assert payload["cells"]
    assert payload["budget"]


def test_two_ledger_cli_rejects_an_invalid_configuration(tmp_path: Path) -> None:
    cli = _cli()
    output = tmp_path / "out.json"
    code = cli.main(
        [
            "experiment-twoledger",
            "--alphas",
            "0.1",
            "--false-reproduce-rate",
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
