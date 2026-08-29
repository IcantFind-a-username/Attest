"""Experiment-only diagnostics for the factory evidence channels (D-007, D-023).

Two independent measurements live here, sharing one synthetic panel generator:

1. :func:`run_rho_ablation` — the correlated-panel ablation (D-023): the naive
   independent product ``LR1 ** votes`` against the production discount.
2. :func:`run_e_validity_experiment` — the follow-up D-023 left open. attest's
   stated core is a sequential betting engine whose wealth threshold is supposed
   to control type-I error through Ville's inequality, and Ville's guarantee
   requires every purchase to satisfy ``E[LR | theta=0] <= 1``. The S channel
   prices only *positive* votes and the T channel only *positive* corroboration,
   so no factor below one is ever applied to a false finding. This module
   measures the resulting null expectations instead of arguing about them, and
   compares the realized wrong-certification rate against the bound ``alpha``.

Neither measurement is a policy and neither is a patch. Both **read** the
factory constants from :mod:`attest.review.channels`; nothing here redefines a
constant, imports a mutable copy, or writes back. Below 500 global ledger labels
no recalibration is permissible at all (architecture red line 5), and a channel
schedule is an owner decision under ground rule 8, so every number produced here
is a recommendation for the owner, never an authorisation.

The ablation's scientific claim: **K samples drawn from one model are a
correlated panel, not K independent witnesses.** Aggregating them as independent
evidence — the naive product ``LR1 ** votes`` — manufactures confidence that is
not in the data. The production schedule prices the correlation instead: vote
``m`` contributes ``LR1 ** ((1 - RHO) ** (m - 1))``, capped at ``S_CAP``.

Three measurement rules this module had to be corrected on, each of which
changes reported numbers rather than prose:

* **the denominator is candidates, not tasks.** Nominal ``alpha`` bounds the
  error rate of the things the gate actually judges, and the product only judges
  a finding some sample proposed. Dividing by every task in the stream — silent
  panels included — dilutes every rate, and dilutes it *hardest* exactly where
  correlation is highest, because a cloned panel is more often unanimously
  silent. Both denominators are reported and both are named in full;
  ``per_candidate`` is the one comparable to ``alpha``.
* **the arms are nested and paired.** Both aggregators see identical vote counts
  from the same draw, so their decisions are a deterministic function of one
  sample and the difference between them is not a difference between two
  independent samples. Overlapping independent Wilson intervals establish
  nothing about a paired difference; :class:`PairedDifference` reports the
  discordant-pair counts, an exact McNemar p-value, and a bootstrap interval on
  the difference itself.
* **the swept parameter is a clone rate, not a correlation.**
  :func:`simulate_panel` clones vote one, so the realized mean pairwise
  correlation is :func:`mean_pairwise_correlation`, strictly below the nominal
  ``gamma`` everywhere in ``(0, 1)``, and the panel is not exchangeable. Every
  cell carries the correlation it truly generates, analytically and as measured
  from the drawn ballots.

Honesty boundaries, restated in every emitted report:

* the panels are **synthetic** Bernoulli draws with a clone-mixing parameter,
  not samples from any real model — nothing here was measured on a
  live system, and no network, subprocess, or API call is involved;
* the vote channel prices only *positive* votes (a candidate exists because some
  sample proposed it), so neither aggregator is a martingale-valid e-value; the
  cap, not a Ville bound, is what holds the discounted arm;
* the T and V channels have no simulator in this project at all: their null
  behaviour is an explicit, swept **assumption**, never a measurement;
* every preregistered seed and every configuration is reported, including the
  ones where the discount loses power and the ones where a concern is refuted.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import NamedTuple

import numpy as np

from attest.benchmark.metrics import wilson_interval
from attest.core.betting import decide
from attest.review.channels import (
    LR1,
    RHO,
    S_CAP,
    T_CAP,
    V_CAP,
    V_FAILED,
    VOTE_LR,
    gate_feasibility,
    max_reachable_wealth,
    tier0_lr,
    verification_lr,
    votes_lr,
)

NAIVE_ARM = "naive_independent"
DISCOUNTED_ARM = "correlation_discounted"

#: Alphas that the product actually ships or documents.
FACTORY_ALPHAS: tuple[float, ...] = (0.05, 0.1)

#: Preregistered sweep. Fixed before any result was looked at, and deliberately
#: NOT re-chosen after the axis was corrected: the swept quantity is the
#: generator's **clone rate**, and the correlation each point truly produces is
#: reported beside it by :func:`mean_pairwise_correlation`.
#:
#: ``RHO`` appears as a sweep point because the production discount names that
#: number, and for no stronger reason. It is *not* a level at which the
#: schedule's assumption becomes true: at a clone rate of ``RHO`` the realized
#: mean pairwise correlation is lower than ``RHO``
#: (:func:`clone_rate_for_pairwise_correlation` gives the rate that would hit
#: it), and no clone rate whatsoever makes the schedule the panel's likelihood
#: ratio (:func:`schedule_oracle_mismatch`).
DEFAULT_GAMMAS: tuple[float, ...] = (0.0, 0.3, RHO, 0.9, 0.99)
DEFAULT_SEEDS: tuple[int, ...] = (11, 22, 33, 44, 55)

#: Shared resampling settings. Used by the ablation's paired difference and by
#: the e-validity section's null expectations, so a single change moves both.
DEFAULT_BOOTSTRAP_RESAMPLES = 2000
DEFAULT_BOOTSTRAP_SEED = 90210
_BOOTSTRAP_CONFIDENCE = 0.95
#: Resampling proceeds in fixed blocks so a large sweep stays inside memory.
#: The block size is part of the determinism contract: changing it changes the
#: random stream and therefore the digest.
_BOOTSTRAP_BLOCK = 250

HONESTY_NOTES: tuple[str, ...] = (
    "synthetic_panels: votes are simulated Bernoulli draws with a clone "
    "mixing parameter, not samples from any real model. No model, network, "
    "or subprocess call was made; nothing here is a measurement of the product.",
    "two_denominators: every wrong-certification rate is reported per_task and "
    "per_candidate, never as an unqualified 'rate'. Nominal alpha bounds the "
    "error rate of the findings the gate judges, and the product judges only "
    "findings some sample proposed, so per_candidate is the quantity comparable "
    "to alpha. per_task is strictly smaller wherever a panel is silent, and the "
    "gap widens with correlation, so a per_task comparison against alpha "
    "understates the very effect it is measuring.",
    "paired_arms: the two aggregators are nested and share every draw — they "
    "see identical vote counts, so the discounted arm certifies a subset of "
    "what the naive arm certifies and the difference is deterministic given the "
    "panel. Overlapping independent Wilson intervals are NOT a test of "
    "equivalence here; the discordant-pair counts, the exact McNemar p-value, "
    "and a bootstrap interval on the paired difference are.",
    "clone_rate_is_not_correlation: the swept parameter gamma is the rate at "
    "which a vote is replaced by a copy of vote one, not the pairwise ballot "
    "correlation. Because only vote one is cloned the panel is not "
    "exchangeable: corr(v1, vj) = gamma while corr(vi, vj) = gamma^2 for later "
    "pairs, so the realized mean pairwise correlation is below gamma everywhere "
    "in (0, 1). Each cell reports that correlation analytically and as measured "
    "from the drawn ballots.",
    "schedule_is_not_a_likelihood_ratio: the D-007 discount is a heuristic, not "
    "the vote count's likelihood ratio under any clone rate. It is monotone in "
    "the vote count by construction while the exact ratio is not once the panel "
    "is correlated, so there is no correlation level at which the schedule's "
    "assumption is literally true; the best achievable mismatch is reported.",
    "independence_control_needs_a_shared_gate: a fairness check run only at the "
    "factory alphas measures nothing about the discount, because the capped "
    "schedule cannot reach those gates at all (D-008). The control is reported "
    "at every swept gate together with whether BOTH arms could certify there.",
    "recommendation_only: this harness reads the production constants and never "
    "writes them. Fewer than 500 global ledger labels exist, and architecture "
    "red line 5 forbids recalibration below that threshold, so no number here "
    "can move a factory constant. Owner decision required.",
    "no_seed_selection: every preregistered seed is reported per cell and per "
    "arm, including configurations in which the discounted arm loses power or "
    "certifies nothing at all.",
    "one_sided_channel: the vote channel prices positive votes only, so neither "
    "aggregator is a martingale-valid e-value. The discounted arm is bounded by "
    "its cap, not by a Ville inequality; do not read its silence as a proof.",
)


class PanelResult(NamedTuple):
    """One simulated correlated panel.

    RNG draw order is part of the contract (same seed must reproduce byte for
    byte): theta, per-vote agreement, clone mask — one generator, three draws.
    """

    gamma: float
    theta_prior: float
    judge_accuracy: float
    k: int
    n_tasks: int
    seed: int
    theta: np.ndarray
    ballots: np.ndarray
    votes: np.ndarray


@dataclass(frozen=True)
class SeedCounts:
    """Per-seed counts, published so no seed can be selected after the fact.

    Both denominators are carried per seed as well, so a reader can rebuild
    either rate from the rows rather than trusting the pooled figure.
    """

    seed: int
    negative_tasks: int
    negative_candidate_tasks: int
    certifications: int
    wrong_certifications: int
    true_certifications: int
    abstentions: int


@dataclass(frozen=True)
class ArmOutcome:
    """Pooled outcome for one aggregator at one (clone rate, alpha) cell.

    **Two denominators, both named in full, neither called "the" rate.**
    ``per_task`` divides by every null task in the stream, including those where
    no sample proposed anything and no candidate ever existed. ``per_candidate``
    divides by the null tasks that actually produced a candidate — the findings
    the gate judges, and therefore the only population nominal ``alpha`` says
    anything about. ``per_task`` is strictly the smaller of the two whenever any
    panel is silent, and silence rises with correlation, so a ``per_task``
    comparison against ``alpha`` understates the effect under study.
    """

    aggregator: str
    tasks: int
    positive_tasks: int
    negative_tasks: int
    candidate_tasks: int
    positive_candidate_tasks: int
    negative_candidate_tasks: int
    candidate_rate: float | None
    negative_candidate_rate: float | None
    certifications: int
    wrong_certifications: int
    true_certifications: int
    discards: int
    abstentions: int
    wrong_certification_rate_per_task: float | None
    wrong_certification_interval_per_task: tuple[float, float] | None
    wrong_certification_rate_per_candidate: float | None
    wrong_certification_interval_per_candidate: tuple[float, float] | None
    alpha_excess_per_task: float | None
    alpha_excess_per_candidate: float | None
    exceeds_alpha_per_task: bool
    exceeds_alpha_per_candidate: bool
    true_certification_rate_per_task: float | None
    true_certification_rate_per_candidate: float | None
    certification_precision: float | None
    certification_precision_interval: tuple[float, float] | None
    abstention_rate: float | None
    per_seed: tuple[SeedCounts, ...]


@dataclass(frozen=True)
class PairedDifference:
    """Naive minus discounted wrong certifications, analysed as paired data.

    The arms are **nested and share every draw**: both aggregators are applied
    to the same simulated panel and both depend on it only through the vote
    count, so the discounted arm's certification set is a subset of the naive
    arm's and the difference between them is a deterministic function of one
    sample. Two consequences the original analysis missed:

    * comparing the arms' separate Wilson intervals treats one sample as two
      independent ones. It discards the pairing, is strictly conservative, and
      can report "overlapping, therefore indistinguishable" for a difference
      that is present in every single draw. ``intervals_overlap`` records what
      that reading would have concluded, so the two verdicts can be seen to
      disagree;
    * the whole of the evidence is the discordant pairs — the tasks where
      exactly one arm wrongly certified. ``mcnemar_exact_p`` is the exact
      two-sided binomial test on them, and ``difference_interval_per_candidate``
      bootstraps the paired difference itself rather than either arm's rate.

    A cell with no discordant pairs at all reports ``mcnemar_exact_p = None``:
    the arms made identical decisions on every task, which is a statement about
    the draw, not a p-value.
    """

    denominator: str
    pairs: int
    both_wrong: int
    naive_only: int
    discounted_only: int
    neither_wrong: int
    arms_are_nested: bool
    difference_per_candidate: float | None
    difference_interval_per_candidate: tuple[float, float] | None
    difference_per_task: float | None
    mcnemar_exact_p: float | None
    intervals_overlap: bool


@dataclass(frozen=True)
class AblationCell:
    """Both arms at one clone rate and one gate.

    ``clone_rate`` is the generator's mixing parameter. The correlation axis is
    ``mean_pairwise_correlation`` — derived from the clone rate — and
    ``measured_pairwise_correlation``, taken from the ballots that were actually
    drawn, so the axis is a measurement rather than a restatement of the
    arithmetic that produced it.

    ``both_arms_can_certify`` marks the cells in which a comparison between the
    arms means anything. Where it is false the discounted arm cannot reach the
    gate at any vote count, so its silence is the D-008 cap arithmetic and not a
    result about correlation.
    """

    label: str
    clone_rate: float
    mean_pairwise_correlation: float | None
    measured_pairwise_correlation: float | None
    alpha: float
    discounted_can_certify: bool
    naive_can_certify: bool
    both_arms_can_certify: bool
    naive: ArmOutcome
    discounted: ArmOutcome
    paired: PairedDifference


@dataclass(frozen=True)
class AblationReport:
    """The whole ablation, content-addressed for pinning."""

    experiment: str
    status: str
    offline: bool
    config: dict[str, object]
    constants: dict[str, object]
    derived: dict[str, object]
    honesty: tuple[str, ...]
    cells: tuple[AblationCell, ...]
    digest: str

    def to_json_dict(self) -> dict[str, object]:
        """Canonical, deterministic JSON payload including its own digest."""
        payload = self._payload()
        payload["digest"] = self.digest
        return payload

    def _payload(self) -> dict[str, object]:
        return {
            "experiment": self.experiment,
            "status": self.status,
            "offline": self.offline,
            "config": self.config,
            "constants": self.constants,
            "derived": self.derived,
            "honesty": list(self.honesty),
            "cells": [_cell_json(cell) for cell in self.cells],
        }


def calibrated_vote_accuracy() -> float:
    """Per-vote accuracy at which ``LR1`` is exactly the likelihood ratio of one
    positive vote: ``a / (1 - a) == LR1``.

    This is the fair default for the ablation. At any other accuracy a critic
    could say the naive arm failed because ``LR1`` was mispriced; here the only
    thing wrong with the naive arm is its independence assumption.
    """
    return LR1 / (1.0 + LR1)


def discount_speech_window() -> tuple[float, float]:
    """Alpha interval in which the discounted schedule can certify on votes
    alone while still being strictly stricter than the naive product.

    Derived, never chosen by hand: the gate ``1 / alpha`` must sit above the
    two-vote step of the production schedule (so the discount still demands more
    votes than the naive product) and at or below the cap (so the discount can
    reach the gate at all).
    """
    return 1.0 / S_CAP, 1.0 / VOTE_LR[2]


def shared_speech_alpha() -> float:
    """The one gate at which both arms can certify, used for every comparison
    that claims to be about the *schedules* rather than about the caps.

    Derived, never chosen by hand: the midpoint of
    :func:`discount_speech_window`. A control or a comparison run only at the
    factory alphas is uninformative about the discount, because the capped
    schedule cannot reach those gates at any vote count (D-008), so the
    discounted arm is shielded rather than tested there.
    """
    low, high = discount_speech_window()
    return (low + high) / 2


def mean_pairwise_correlation(*, k: int, gamma: float) -> float | None:
    """Mean pairwise ballot correlation the generator actually produces.

    :func:`simulate_panel` clones **vote one**, so the panel is not
    exchangeable. Conditional on the truth, ``corr(b_1, b_j) = gamma`` for each
    later vote, because vote ``j`` either is vote one or is drawn independently
    of it. Two later votes are correlated only through the event that both
    cloned vote one, giving ``corr(b_i, b_j) = gamma ** 2``. Averaging over the
    ``C(k, 2)`` pairs::

        ((k - 1) * gamma + C(k - 1, 2) * gamma ** 2) / C(k, 2)

    which is strictly below ``gamma`` for every ``0 < gamma < 1``. The sweep
    parameter is therefore a clone rate and this is the correlation axis;
    labelling the sweep with ``gamma`` overstates the correlation at every
    interior point. A panel of fewer than two votes has no pair and no
    correlation, which is unknown rather than zero.
    """
    if k < 1:
        raise ValueError("k must be at least one")
    _check_unit("gamma", gamma, closed=True)
    if k < 2:
        return None
    pairs = math.comb(k, 2)
    with_first = (k - 1) * gamma
    among_rest = math.comb(k - 1, 2) * gamma * gamma
    return (with_first + among_rest) / pairs


def clone_rate_for_pairwise_correlation(*, k: int, correlation: float) -> float | None:
    """Invert :func:`mean_pairwise_correlation`: the clone rate that really
    delivers ``correlation``.

    Reported beside the sweep so the gap between a nominal ``gamma`` and the
    correlation it produces is a number rather than a caveat.
    """
    if k < 1:
        raise ValueError("k must be at least one")
    _check_unit("correlation", correlation, closed=True)
    if k < 2:
        return None
    quadratic = math.comb(k - 1, 2)
    linear = k - 1
    constant = -correlation * math.comb(k, 2)
    if quadratic == 0:
        return -constant / linear
    root = math.sqrt(linear * linear - 4 * quadratic * constant)
    return (-linear + root) / (2 * quadratic)


def measured_pairwise_correlation(panel: PanelResult) -> float | None:
    """Mean pairwise ballot correlation of the draw that actually happened.

    Measured, not derived, so the reported correlation axis is evidence rather
    than a second copy of the arithmetic that generated it. Ballots are centred
    **inside each ground-truth group** first: two votes agree partly because
    they saw the same ``theta``, and that shared truth is not panel correlation.

    Returns ``None`` when no correlation is defined — fewer than two votes,
    fewer than two tasks, or a column with no variation to correlate.
    """
    if panel.k < 2 or panel.n_tasks < 2:
        return None
    ballots = panel.ballots.astype(float)
    centred = np.zeros_like(ballots)
    for value in (0, 1):
        mask = panel.theta == value
        if not mask.any():
            continue
        centred[mask] = ballots[mask] - ballots[mask].mean(axis=0)
    variance = (centred * centred).mean(axis=0)
    if float(variance.min()) <= 0.0:
        return None
    covariance = centred.T @ centred / centred.shape[0]
    correlation = covariance / np.sqrt(np.outer(variance, variance))
    upper = correlation[np.triu_indices(panel.k, k=1)]
    return float(upper.mean())


def schedule_oracle_mismatch(
    *, k: int, judge_accuracy: float, grid: int = 401
) -> dict[str, object]:
    """How close the D-007 schedule can get to the panel's true likelihood
    ratio, minimised over the entire clone-rate axis.

    The claim under test is that some correlation level makes the production
    discount exact. It cannot: the schedule is monotone non-decreasing in the
    vote count by construction, while the exact ratio
    :func:`oracle_panel_lr` is **not** monotone once the panel is correlated —
    on a clone panel a middling vote count is evidence *against* the finding,
    because a real clone panel is nearly unanimous either way. Scanning every
    clone rate and reporting the smallest achievable worst-case log ratio
    settles the question with a number instead of an argument.
    """
    if k < 1:
        raise ValueError("k must be at least one")
    if grid < 1:
        raise ValueError("grid must be at least one")
    _check_unit("judge_accuracy", judge_accuracy, closed=False)

    schedule = [votes_lr(votes) for votes in range(k + 1)]
    best_rate = 0.0
    best_error = math.inf
    best_oracle: tuple[float, ...] = ()
    for step in range(grid):
        rate = step * 0.999 / max(1, grid - 1)
        oracle = oracle_panel_lr(k=k, judge_accuracy=judge_accuracy, gamma=rate)
        error = max(
            abs(math.log(oracle[votes] / schedule[votes])) for votes in range(1, k + 1)
        )
        if error < best_error:
            best_rate, best_error, best_oracle = rate, error, oracle
    return {
        "best_clone_rate": _num(best_rate),
        "max_log_ratio": _num(best_error),
        "max_ratio": _num(math.exp(best_error)),
        "schedule_is_monotone": _is_monotone(schedule),
        "oracle_is_monotone_at_best_clone_rate": _is_monotone(list(best_oracle)),
        "note": (
            "no clone rate makes the production schedule the vote count's "
            "likelihood ratio; the schedule is monotone by construction and the "
            "exact ratio is not once the panel is correlated"
        ),
    }


def _is_monotone(table: Sequence[float]) -> bool:
    return all(
        later >= earlier
        for earlier, later in zip(table[:-1], table[1:], strict=True)
    )


def naive_votes_lr(votes: int) -> float:
    """Counterfactual S channel: treat the K panel samples as independent
    witnesses and multiply. Uncapped by construction — this is the aggregator
    the project rejects, reproduced faithfully so it can be measured.
    """
    if votes < 1:
        return 1.0
    return float(LR1**votes)


def simulate_panel(
    *,
    gamma: float,
    theta_prior: float,
    judge_accuracy: float,
    k: int,
    n_tasks: int,
    seed: int,
) -> PanelResult:
    """Draw ``n_tasks`` correlated K-sample panels.

    Ground truth ``theta ~ Bernoulli(theta_prior)``. Every vote would agree with
    the truth at ``judge_accuracy`` on its own; with probability ``gamma`` a vote
    is instead a clone of the first vote of the same panel. ``gamma = 0`` gives
    genuinely independent votes, ``gamma = 1`` a single witness repeated ``k``
    times.

    ``gamma`` is a **clone rate and not the pairwise correlation it produces**.
    Only vote one is copied, so the panel is not exchangeable and the realized
    mean pairwise correlation is :func:`mean_pairwise_correlation`, strictly
    below ``gamma`` at every interior point. Anything that reports a correlation
    axis must report that function of ``gamma``, not ``gamma`` itself.

    :func:`attest.core.stream.make_stream` is deliberately not reused: it models
    three *heterogeneous named* judges with one clone edge and an exploration
    mask, which is a different object from a homogeneous K-sample panel. Its
    regression pins would also be at risk from any shared-code change, and those
    pins must never move.
    """
    _check_unit("gamma", gamma, closed=True)
    _check_unit("theta_prior", theta_prior, closed=True)
    _check_unit("judge_accuracy", judge_accuracy, closed=False)
    if k < 1:
        raise ValueError("k must be at least one")
    if n_tasks < 1:
        raise ValueError("n_tasks must be at least one")

    rng = np.random.default_rng(seed)
    theta = (rng.random(n_tasks) < theta_prior).astype(np.int64)
    agrees = rng.random((n_tasks, k)) < judge_accuracy
    clones = rng.random((n_tasks, k)) < gamma

    truth = theta[:, None]
    independent = np.where(agrees, truth, 1 - truth)
    ballots = independent.copy()
    for column in range(1, k):
        ballots[:, column] = np.where(
            clones[:, column], ballots[:, 0], independent[:, column]
        )
    votes = ballots.sum(axis=1).astype(np.int64)
    return PanelResult(
        gamma=gamma,
        theta_prior=theta_prior,
        judge_accuracy=judge_accuracy,
        k=k,
        n_tasks=n_tasks,
        seed=seed,
        theta=theta,
        ballots=ballots,
        votes=votes,
    )


def run_rho_ablation(
    *,
    gammas: Sequence[float],
    alphas: Sequence[float],
    k: int,
    n_tasks: int,
    seeds: Sequence[int],
    theta_prior: float = 0.5,
    judge_accuracy: float | None = None,
    paired_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    paired_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> AblationReport:
    """Run both aggregators through the production gate over the whole grid.

    For every ``(gamma, alpha, seed)`` the naive and the discounted vote
    aggregator are each pushed through :func:`attest.core.betting.decide`. Counts
    are pooled across seeds; per-seed rows are retained so no favourable seed can
    be selected afterwards.

    Both arms run on the *same* panels, which is what makes the comparison sharp
    and also what makes an independent-sample comparison between them invalid.
    Each cell therefore carries a :class:`PairedDifference` alongside the two
    :class:`ArmOutcome` rows, and every rate is reported on both the per-task and
    the per-candidate denominator.
    """
    if not gammas:
        raise ValueError("at least one gamma is required")
    if not alphas:
        raise ValueError("at least one alpha is required")
    if not seeds:
        raise ValueError("at least one seed is required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be unique")
    if k < 1:
        raise ValueError("k must be at least one")
    if n_tasks < 1:
        raise ValueError("n_tasks must be at least one")
    for gamma in gammas:
        _check_unit("gamma", gamma, closed=True)
    for alpha in alphas:
        _check_unit("alpha", alpha, closed=False)
    _check_unit("theta_prior", theta_prior, closed=True)
    if paired_resamples < 1:
        raise ValueError("paired_resamples must be at least one")
    accuracy = calibrated_vote_accuracy() if judge_accuracy is None else judge_accuracy
    _check_unit("judge_accuracy", accuracy, closed=False)

    panels = {
        (gamma, seed): simulate_panel(
            gamma=gamma,
            theta_prior=theta_prior,
            judge_accuracy=accuracy,
            k=k,
            n_tasks=n_tasks,
            seed=seed,
        )
        for gamma in gammas
        for seed in seeds
    }

    cells: list[AblationCell] = []
    for gamma in gammas:
        runs = [panels[(gamma, seed)] for seed in seeds]
        correlation = _pooled_measured_correlation(runs)
        for alpha in alphas:
            naive_map = _decision_map(naive_votes_lr, k, alpha)
            discounted_map = _decision_map(votes_lr, k, alpha)
            label = f"clone_rate={_num(gamma)}/alpha={_num(alpha)}"
            naive_can = any(code == 1 for code in naive_map)
            discounted_can = any(code == 1 for code in discounted_map)
            cells.append(
                AblationCell(
                    label=label,
                    clone_rate=gamma,
                    mean_pairwise_correlation=mean_pairwise_correlation(k=k, gamma=gamma),
                    measured_pairwise_correlation=correlation,
                    alpha=alpha,
                    discounted_can_certify=discounted_can,
                    naive_can_certify=naive_can,
                    both_arms_can_certify=naive_can and discounted_can,
                    naive=_arm_outcome(NAIVE_ARM, naive_map, runs, alpha),
                    discounted=_arm_outcome(DISCOUNTED_ARM, discounted_map, runs, alpha),
                    paired=_paired_difference(
                        naive_map=naive_map,
                        discounted_map=discounted_map,
                        runs=runs,
                        seed=_row_seed(paired_seed, label, "paired"),
                        resamples=paired_resamples,
                    ),
                )
            )

    low, high = discount_speech_window()
    report = AblationReport(
        experiment="correlated_panel_rho_ablation",
        status="insufficient_labels/recommendation_only",
        offline=True,
        config={
            "gammas": [_num(gamma) for gamma in gammas],
            "alphas": [_num(alpha) for alpha in alphas],
            "k": k,
            "n_tasks": n_tasks,
            "seeds": list(seeds),
            "theta_prior": _num(theta_prior),
            "judge_accuracy": _num(accuracy),
            "judge_accuracy_is_lr1_calibrated": accuracy == calibrated_vote_accuracy(),
            "paired_resamples": paired_resamples,
            "paired_seed": paired_seed,
            "paired_confidence": _BOOTSTRAP_CONFIDENCE,
            "gammas_are_clone_rates": True,
        },
        constants={
            "lr1": LR1,
            "rho": RHO,
            "s_cap": S_CAP,
            "vote_lr": list(VOTE_LR),
        },
        derived={
            "discount_speech_window": [_num(low), _num(high)],
            "shared_speech_alpha": _num(shared_speech_alpha()),
            "factory_alphas": list(FACTORY_ALPHAS),
            "factory_gate_reachable_on_votes_alone": {
                str(_num(alpha)): bool(1.0 / alpha <= S_CAP) for alpha in FACTORY_ALPHAS
            },
            "mean_pairwise_correlation_by_clone_rate": {
                str(_num(gamma)): _optional(mean_pairwise_correlation(k=k, gamma=gamma))
                for gamma in gammas
            },
            "clone_rate_matching_rho": _optional(
                clone_rate_for_pairwise_correlation(k=k, correlation=RHO)
            ),
            "clone_rate_axis_note": (
                "the swept parameter is a clone rate, not a correlation; the "
                "correlation each point produces is reported per cell, "
                "analytically and as measured from the drawn ballots"
            ),
            "schedule_oracle_mismatch": schedule_oracle_mismatch(
                k=k, judge_accuracy=accuracy
            ),
            "cells_where_both_arms_can_certify": [
                cell.label for cell in cells if cell.both_arms_can_certify
            ],
            "cells_where_the_discounted_arm_is_shielded": [
                cell.label for cell in cells if not cell.discounted_can_certify
            ],
            "independence_control": [
                _independence_control_json(cell)
                for cell in cells
                if cell.clone_rate == 0.0
            ],
            "alpha_breaches_per_candidate": [
                f"{cell.label}/{arm.aggregator}"
                for cell in cells
                for arm in (cell.naive, cell.discounted)
                if arm.exceeds_alpha_per_candidate
            ],
            "alpha_breaches_per_task": [
                f"{cell.label}/{arm.aggregator}"
                for cell in cells
                for arm in (cell.naive, cell.discounted)
                if arm.exceeds_alpha_per_task
            ],
            "paired_separations": [
                cell.label
                for cell in cells
                if cell.paired.mcnemar_exact_p is not None
                and cell.paired.mcnemar_exact_p < 1.0 - _BOOTSTRAP_CONFIDENCE
            ],
            "paired_verdict_disagrees_with_interval_overlap": [
                cell.label
                for cell in cells
                if cell.paired.intervals_overlap
                and cell.paired.mcnemar_exact_p is not None
                and cell.paired.mcnemar_exact_p < 1.0 - _BOOTSTRAP_CONFIDENCE
            ],
        },
        honesty=HONESTY_NOTES,
        cells=tuple(cells),
        digest="",
    )
    return replace(report, digest=_digest(report._payload()))


def _decision_map(
    aggregator: Callable[[int], float], k: int, alpha: float
) -> tuple[int | None, ...]:
    """Production ``decide()`` evaluated once per reachable evidence state.

    Wealth depends on the vote count and nothing else, so calling the real gate
    once per reachable count is exactly equivalent to calling it per task.
    """
    return tuple(decide(aggregator(votes), alpha) for votes in range(k + 1))


def _arm_outcome(
    aggregator: str,
    decision_map: Sequence[int | None],
    runs: Sequence[PanelResult],
    alpha: float,
) -> ArmOutcome:
    """Pool one aggregator's decisions on **both** denominators.

    A candidate exists exactly when at least one of the K samples asserted the
    finding, which is the condition under which the product ever reaches the
    gate. Wrong certifications are counted once and divided twice: by every null
    task, and by the null tasks that produced a candidate. Only the second is
    comparable to ``alpha``.
    """
    certify = np.array([code == 1 for code in decision_map])
    discard = np.array([code == 0 for code in decision_map])

    per_seed: list[SeedCounts] = []
    tasks = positives = negatives = 0
    candidates = positive_candidates = negative_candidates = 0
    certifications = wrong = true = discards = abstentions = 0
    for panel in runs:
        certified = certify[panel.votes]
        discarded = discard[panel.votes]
        proposed = panel.votes >= 1
        seed_certified = int(certified.sum())
        seed_wrong = int((certified & (panel.theta == 0)).sum())
        seed_true = int((certified & (panel.theta == 1)).sum())
        seed_discards = int(discarded.sum())
        seed_abstentions = panel.n_tasks - seed_certified - seed_discards
        seed_negatives = int((panel.theta == 0).sum())
        seed_negative_candidates = int((proposed & (panel.theta == 0)).sum())
        per_seed.append(
            SeedCounts(
                seed=panel.seed,
                negative_tasks=seed_negatives,
                negative_candidate_tasks=seed_negative_candidates,
                certifications=seed_certified,
                wrong_certifications=seed_wrong,
                true_certifications=seed_true,
                abstentions=seed_abstentions,
            )
        )
        tasks += panel.n_tasks
        positives += int((panel.theta == 1).sum())
        negatives += seed_negatives
        candidates += int(proposed.sum())
        positive_candidates += int((proposed & (panel.theta == 1)).sum())
        negative_candidates += seed_negative_candidates
        certifications += seed_certified
        wrong += seed_wrong
        true += seed_true
        discards += seed_discards
        abstentions += seed_abstentions

    per_task = _rate(wrong, negatives)
    per_candidate = _rate(wrong, negative_candidates)
    task_interval = _interval(wrong, negatives)
    candidate_interval = _interval(wrong, negative_candidates)
    return ArmOutcome(
        aggregator=aggregator,
        tasks=tasks,
        positive_tasks=positives,
        negative_tasks=negatives,
        candidate_tasks=candidates,
        positive_candidate_tasks=positive_candidates,
        negative_candidate_tasks=negative_candidates,
        candidate_rate=_rate(candidates, tasks),
        negative_candidate_rate=_rate(negative_candidates, negatives),
        certifications=certifications,
        wrong_certifications=wrong,
        true_certifications=true,
        discards=discards,
        abstentions=abstentions,
        wrong_certification_rate_per_task=per_task,
        wrong_certification_interval_per_task=task_interval,
        wrong_certification_rate_per_candidate=per_candidate,
        wrong_certification_interval_per_candidate=candidate_interval,
        alpha_excess_per_task=None if per_task is None else per_task / alpha,
        alpha_excess_per_candidate=(
            None if per_candidate is None else per_candidate / alpha
        ),
        exceeds_alpha_per_task=task_interval is not None and task_interval[0] > alpha,
        exceeds_alpha_per_candidate=(
            candidate_interval is not None and candidate_interval[0] > alpha
        ),
        true_certification_rate_per_task=_rate(true, positives),
        true_certification_rate_per_candidate=_rate(true, positive_candidates),
        certification_precision=_rate(true, certifications),
        certification_precision_interval=_interval(true, certifications),
        abstention_rate=_rate(abstentions, tasks),
        per_seed=tuple(per_seed),
    )


def _paired_difference(
    *,
    naive_map: Sequence[int | None],
    discounted_map: Sequence[int | None],
    runs: Sequence[PanelResult],
    seed: int,
    resamples: int,
) -> PairedDifference:
    """Discordant-pair analysis of the two arms on the null tasks they share.

    Both arms are evaluated on the same panels, so every null candidate task
    contributes one *pair* of decisions. The difference in wrong-certification
    rates is the mean of the per-task difference, which is why a bootstrap over
    that single vector — not over either arm separately — is the interval that
    belongs to it.
    """
    naive_certify = np.array([code == 1 for code in naive_map])
    discounted_certify = np.array([code == 1 for code in discounted_map])
    nested = bool((discounted_certify <= naive_certify).all())

    naive_flags: list[np.ndarray] = []
    discounted_flags: list[np.ndarray] = []
    negatives = 0
    for panel in runs:
        selected = (panel.theta == 0) & (panel.votes >= 1)
        votes = panel.votes[selected]
        naive_flags.append(naive_certify[votes])
        discounted_flags.append(discounted_certify[votes])
        negatives += int((panel.theta == 0).sum())

    naive_wrong = np.concatenate(naive_flags) if naive_flags else np.array([], dtype=bool)
    discounted_wrong = (
        np.concatenate(discounted_flags) if discounted_flags else np.array([], dtype=bool)
    )
    pairs = int(naive_wrong.size)
    naive_only = int((naive_wrong & ~discounted_wrong).sum())
    discounted_only = int((discounted_wrong & ~naive_wrong).sum())
    both = int((naive_wrong & discounted_wrong).sum())

    difference: float | None = None
    interval: tuple[float, float] | None = None
    if pairs:
        deltas = naive_wrong.astype(float) - discounted_wrong.astype(float)
        difference = float(deltas.mean())
        interval = _bootstrap_interval(deltas, seed=seed, resamples=resamples)

    naive_interval = _interval(both + naive_only, pairs)
    discounted_interval = _interval(both + discounted_only, pairs)
    overlap = (
        naive_interval is not None
        and discounted_interval is not None
        and naive_interval[0] <= discounted_interval[1]
        and discounted_interval[0] <= naive_interval[1]
    )
    return PairedDifference(
        denominator="negative_candidate_tasks",
        pairs=pairs,
        both_wrong=both,
        naive_only=naive_only,
        discounted_only=discounted_only,
        neither_wrong=pairs - both - naive_only - discounted_only,
        arms_are_nested=nested,
        difference_per_candidate=difference,
        difference_interval_per_candidate=interval,
        difference_per_task=_rate(naive_only - discounted_only, negatives),
        mcnemar_exact_p=_mcnemar_exact_p(naive_only, discounted_only),
        intervals_overlap=overlap,
    )


def _mcnemar_exact_p(naive_only: int, discounted_only: int) -> float | None:
    """Exact two-sided McNemar p-value from the discordant counts.

    Under the null that the two arms are equally likely to be the one that
    wrongly certifies, the discordant pairs split Binomial(b + c, 1/2). Computed
    in log space because the counts here reach the thousands.

    ``None`` when there are no discordant pairs at all: the arms decided
    identically on every task, which is a property of the draw and not a test
    result.
    """
    total = naive_only + discounted_only
    if total == 0:
        return None
    smaller = min(naive_only, discounted_only)
    log_half = -total * math.log(2)
    tail = math.fsum(
        math.exp(_log_comb(total, index) + log_half) for index in range(smaller + 1)
    )
    return min(1.0, 2 * tail)


def _log_comb(total: int, chosen: int) -> float:
    return (
        math.lgamma(total + 1) - math.lgamma(chosen + 1) - math.lgamma(total - chosen + 1)
    )


def _pooled_measured_correlation(runs: Sequence[PanelResult]) -> float | None:
    """Mean of the per-seed measured correlations; unknown if none is defined."""
    measured = [
        value
        for value in (measured_pairwise_correlation(panel) for panel in runs)
        if value is not None
    ]
    return sum(measured) / len(measured) if measured else None


def _independence_control_json(cell: AblationCell) -> dict[str, object]:
    """The fairness control, reported per gate rather than asserted once.

    The control only means something where both arms can reach the gate. Where
    the discounted arm is shielded by the cap it cannot be anti-conservative at
    any vote count, so 'the discount is not anti-conservative here' is the D-008
    arithmetic restated and carries no information about correlation pricing.
    """
    return {
        "label": cell.label,
        "alpha": _num(cell.alpha),
        "both_arms_can_certify": cell.both_arms_can_certify,
        "naive_exceeds_alpha_per_candidate": cell.naive.exceeds_alpha_per_candidate,
        "discounted_exceeds_alpha_per_candidate": (
            cell.discounted.exceeds_alpha_per_candidate
        ),
        "naive_alpha_excess_per_candidate": _optional(
            cell.naive.alpha_excess_per_candidate
        ),
        "discounted_alpha_excess_per_candidate": _optional(
            cell.discounted.alpha_excess_per_candidate
        ),
        "informative": cell.both_arms_can_certify,
    }


def _rate(numerator: int, denominator: int) -> float | None:
    """A rate over zero observations is unknown, never zero."""
    return numerator / denominator if denominator else None


def _interval(successes: int, total: int) -> tuple[float, float] | None:
    return wilson_interval(successes, total) if total else None


def _check_unit(name: str, value: float, *, closed: bool) -> None:
    if closed and not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must lie in [0, 1]")
    if not closed and not 0.0 < value < 1.0:
        raise ValueError(f"{name} must lie in (0, 1)")


def _num(value: float) -> float:
    """Round to a stable width so the digest does not carry float noise."""
    return round(float(value), 12)


def _pair(interval: tuple[float, float] | None) -> list[float] | None:
    return None if interval is None else [_num(interval[0]), _num(interval[1])]


def _optional(value: float | None) -> float | None:
    return None if value is None else _num(value)


def _arm_json(arm: ArmOutcome) -> dict[str, object]:
    return {
        "aggregator": arm.aggregator,
        "tasks": arm.tasks,
        "positive_tasks": arm.positive_tasks,
        "negative_tasks": arm.negative_tasks,
        "candidate_tasks": arm.candidate_tasks,
        "positive_candidate_tasks": arm.positive_candidate_tasks,
        "negative_candidate_tasks": arm.negative_candidate_tasks,
        "candidate_rate": _optional(arm.candidate_rate),
        "negative_candidate_rate": _optional(arm.negative_candidate_rate),
        "certifications": arm.certifications,
        "wrong_certifications": arm.wrong_certifications,
        "true_certifications": arm.true_certifications,
        "discards": arm.discards,
        "abstentions": arm.abstentions,
        "wrong_certification_rate_per_task": _optional(
            arm.wrong_certification_rate_per_task
        ),
        "wrong_certification_interval_per_task": _pair(
            arm.wrong_certification_interval_per_task
        ),
        "wrong_certification_rate_per_candidate": _optional(
            arm.wrong_certification_rate_per_candidate
        ),
        "wrong_certification_interval_per_candidate": _pair(
            arm.wrong_certification_interval_per_candidate
        ),
        "alpha_excess_per_task": _optional(arm.alpha_excess_per_task),
        "alpha_excess_per_candidate": _optional(arm.alpha_excess_per_candidate),
        "exceeds_alpha_per_task": arm.exceeds_alpha_per_task,
        "exceeds_alpha_per_candidate": arm.exceeds_alpha_per_candidate,
        "true_certification_rate_per_task": _optional(
            arm.true_certification_rate_per_task
        ),
        "true_certification_rate_per_candidate": _optional(
            arm.true_certification_rate_per_candidate
        ),
        "certification_precision": _optional(arm.certification_precision),
        "certification_precision_interval": _pair(arm.certification_precision_interval),
        "abstention_rate": _optional(arm.abstention_rate),
        "per_seed": [
            {
                "seed": row.seed,
                "negative_tasks": row.negative_tasks,
                "negative_candidate_tasks": row.negative_candidate_tasks,
                "certifications": row.certifications,
                "wrong_certifications": row.wrong_certifications,
                "true_certifications": row.true_certifications,
                "abstentions": row.abstentions,
            }
            for row in arm.per_seed
        ],
    }


def _paired_json(paired: PairedDifference) -> dict[str, object]:
    return {
        "denominator": paired.denominator,
        "pairs": paired.pairs,
        "both_wrong": paired.both_wrong,
        "naive_only": paired.naive_only,
        "discounted_only": paired.discounted_only,
        "neither_wrong": paired.neither_wrong,
        "arms_are_nested": paired.arms_are_nested,
        "difference_per_candidate": _optional(paired.difference_per_candidate),
        "difference_interval_per_candidate": _pair(
            paired.difference_interval_per_candidate
        ),
        "difference_per_task": _optional(paired.difference_per_task),
        "mcnemar_exact_p": _optional(paired.mcnemar_exact_p),
        "intervals_overlap": paired.intervals_overlap,
    }


def _cell_json(cell: AblationCell) -> dict[str, object]:
    return {
        "label": cell.label,
        "clone_rate": _num(cell.clone_rate),
        "mean_pairwise_correlation": _optional(cell.mean_pairwise_correlation),
        "measured_pairwise_correlation": _optional(cell.measured_pairwise_correlation),
        "alpha": _num(cell.alpha),
        "discounted_can_certify": cell.discounted_can_certify,
        "naive_can_certify": cell.naive_can_certify,
        "both_arms_can_certify": cell.both_arms_can_certify,
        "naive": _arm_json(cell.naive),
        "discounted": _arm_json(cell.discounted),
        "paired": _paired_json(cell.paired),
    }


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


# ===========================================================================
# D-023 follow-up: is the wealth process an e-process as implemented?
#
# Ville's inequality bounds P(sup_t wealth_t >= 1/alpha) by alpha only when
# every purchased factor is an e-value under the null: E[LR | theta=0] <= 1.
# The S and T channels price corroboration only — every reachable factor is
# at least 1 — so no compensating factor below 1 can ever be applied to a
# false finding. Nothing below tries to fix that. It measures it.
# ===========================================================================

#: The bound an e-value has to satisfy. Named so the ratio has a denominator.
E_VALUE_BOUND = 1.0

PRODUCTION_ARM = "production_one_sided"
TWO_SIDED_ARM = "two_sided_counterfactual"
ORACLE_SCHEDULE = "oracle_panel_likelihood_ratio"
ASSUMED_SCHEDULE = "production_assumed_null"

VOTES_ONLY = "votes_only"
FULL_CHANNELS = "full_channels"

#: Preregistered correlation levels for the null measurement: genuinely
#: independent votes, the correlation the production discount assumes, and a
#: near-degenerate panel.
DEFAULT_NULL_GAMMAS: tuple[float, ...] = (0.0, RHO, 0.9)

#: Preregistered gates. The first two are what the product ships; the rest are
#: loosened on purpose, because at the factory alphas the capped S channel
#: cannot reach the gate at all and a bound that is never tested is not
#: evidence of a bound (D-008).
DEFAULT_VILLE_ALPHAS: tuple[float, ...] = (0.05, 0.1, 0.25, 0.4, 0.5)

#: Resampling settings are shared with the ablation and defined beside the
#: preregistered sweep; they are preregistered for this section too.

#: Second generator per seed, so the T and V draws cannot perturb the panel
#: draws and a stream is byte-identical to the ablation's panel at the same seed.
_EVIDENCE_STREAM_TAG = 20260830

_V_NOT_REPRODUCED = 0
_V_NO_PURCHASE = 1
_V_REPRODUCED = 2
_V_OUTCOMES = 3

#: Indexed by the codes above; read from production, never restated.
_VERIFICATION_LR: tuple[float, ...] = (
    verification_lr(False),
    E_VALUE_BOUND,
    verification_lr(True),
)

_CANDIDATE_CONDITION = (
    "candidate_exists: at least one of the K samples asserted the finding. A "
    "finding nobody proposed is never priced, so the V=0 outcome — the only one "
    "worth exactly 1 — is never observed by the product."
)
_TIER0_CONDITION = (
    "channel_purchased: at least one static signal overlaps the anchor "
    "(attest.review.gate buys T only when the signal list is non-empty)."
)
_VERIFICATION_CONDITION = (
    "channel_purchased: a reproduction verdict was recorded (attest.review.gate "
    "buys V only when a verification result exists)."
)

E_VALIDITY_HONESTY_NOTES: tuple[str, ...] = (
    "synthetic_panels: votes are simulated Bernoulli draws with a clone "
    "correlation parameter, not samples from any real model. No model, network, "
    "or subprocess call was made; nothing here is a measurement of the product.",
    "recommendation_only: this harness reads the production constants and never "
    "writes them. Fewer than 500 global ledger labels exist, architecture red "
    "line 5 forbids recalibration below that threshold, and a channel schedule "
    "is an owner decision under ground rule 8. Owner decision required.",
    "no_seed_selection: every preregistered seed is reported per row and per "
    "cell, including configurations where a stated concern is refuted.",
    "estimator_validated_in_band: the oracle row is a likelihood ratio built "
    "from the simulator's own null and alternative vote distributions, so it is "
    "a valid e-value by construction. If its measured expectation is not ~1 the "
    "estimator is broken and every other row in this report must be discarded.",
    "assumed_null_behaviour: the T and V channels have no simulator in this "
    "project. Their null rates are an ASSUMPTION stated as parameters and swept "
    "rather than fitted; no false-corroboration or false-reproduction rate has "
    "ever been measured on real data. The V channel's verdict flips at the "
    "derived ceiling reported beside it, so the assumption, not the evidence, "
    "decides that row.",
    "candidate_conditioning: the unconditioned expectation is the generous "
    "reading of each channel. The candidate-conditioned expectation is what the "
    "product actually experiences, because only findings some sample proposed "
    "ever reach the gate. Both are reported; the conditioned one is worse.",
    "counterfactual_not_a_patch: two_sided_votes_lr exists only inside this "
    "harness, to give the measurement a comparator that is valid by "
    "construction. It is NOT a proposed change to attest.review.channels: it is "
    "exactly valid only under the independent-panel model it assumes, it is "
    "measured here to break under correlation, and candidate conditioning "
    "breaks it too.",
    "one_sided_channels: the S and T schedules have no factor below one, so "
    "their null expectation exceeds the e-value bound for any null in which a "
    "purchase can happen at all. That is arithmetic, not a simulation artifact; "
    "the simulation only says by how much.",
)


@dataclass(frozen=True)
class NullAssumptions:
    """Assumed null behaviour of the two channels this project cannot simulate.

    **These are assumptions, not measurements.** attest has never measured how
    often a static analyser spuriously corroborates a false finding, nor how
    often a generated differential reproduction fails on head and passes on base
    for a finding that is wrong. Both numbers would need real ledger labels.
    They are parameters here so that the reader can see exactly what the verdict
    rests on, and both are swept rather than fitted.

    The vote channel needs no assumption of this kind: its null distribution
    comes from the panel generator itself.
    """

    #: Independent chances for a spurious static signal to overlap the anchor.
    #: Two is enough to reach every branch of ``tier0_lr`` (1.0 / 2.0 / cap).
    tier0_signal_slots: int = 2
    tier0_signal_rate: float = 0.1
    tier0_signal_rate_sweep: tuple[float, ...] = (0.0, 0.05, 0.1, 0.25)
    #: Chance that a false finding's generated reproduction is nonetheless
    #: classified as a reproduced regression.
    verification_reproduce_rate: float = 0.05
    #: Chance that no V purchase happens at all: deferral (D-022's unpriced
    #: classes) or no verification attempt. Both leave wealth untouched.
    verification_no_purchase_rate: float = 0.5
    verification_reproduce_rate_sweep: tuple[float, ...] = (0.0, 0.01, 0.025, 0.05, 0.1)

    def to_json_dict(self) -> dict[str, object]:
        """Emitted verbatim in the artifact: the assumption is never buried."""
        return {
            "tier0_signal_slots": self.tier0_signal_slots,
            "tier0_signal_rate": _num(self.tier0_signal_rate),
            "tier0_signal_rate_sweep": [_num(rate) for rate in self.tier0_signal_rates()],
            "verification_reproduce_rate": _num(self.verification_reproduce_rate),
            "verification_no_purchase_rate": _num(self.verification_no_purchase_rate),
            "verification_reproduce_rate_sweep": [
                _num(rate) for rate in self.verification_reproduce_rates()
            ],
            "measured": False,
            "note": "assumed null behaviour of the T and V channels; never measured",
        }

    def tier0_signal_rates(self) -> tuple[float, ...]:
        """Sweep points, always including the one the Ville section uses."""
        return tuple(sorted({*self.tier0_signal_rate_sweep, self.tier0_signal_rate}))

    def verification_reproduce_rates(self) -> tuple[float, ...]:
        return tuple(
            sorted({*self.verification_reproduce_rate_sweep, self.verification_reproduce_rate})
        )


DEFAULT_NULL_ASSUMPTIONS = NullAssumptions()


class NullStream(NamedTuple):
    """One null-only evidence stream: every task's ground truth is theta=0.

    RNG draw order is part of the contract. Votes come from
    :func:`simulate_panel` at ``theta_prior=0``, so a stream is byte-identical
    to the ablation's panel at the same seed. The T and V uniforms come from a
    second generator, drawn signals-then-verification, so that sweeping an
    assumed rate re-thresholds the same draws instead of redrawing them.
    """

    seed: int
    k: int
    gamma: float
    judge_accuracy: float
    n_tasks: int
    votes: np.ndarray
    signal_uniforms: np.ndarray
    verification_uniforms: np.ndarray


@dataclass(frozen=True)
class SeedMean:
    """Per-seed expectation, published so no seed can be selected afterwards."""

    seed: int
    samples: int
    mean: float
    conditioned_samples: int
    conditioned_mean: float | None


@dataclass(frozen=True)
class NullExpectation:
    """``E[LR | theta=0]`` for one channel schedule, with its own denominator."""

    channel: str
    schedule: str
    label: str
    gamma: float | None
    assumed_rate: float | None
    assumption: dict[str, object] | None
    condition: str
    samples: int
    mean: float
    interval: tuple[float, float]
    e_validity_ratio: float
    lower_bound_exceeds_one: bool
    conditioned_samples: int
    conditioned_mean: float | None
    conditioned_interval: tuple[float, float] | None
    conditioned_e_validity_ratio: float | None
    conditioned_lower_bound_exceeds_one: bool | None
    analytic_mean: float | None
    analytic_conditioned_mean: float | None
    per_seed: tuple[SeedMean, ...]


@dataclass(frozen=True)
class VilleSeedCounts:
    seed: int
    null_tasks: int
    candidates: int
    wrong_certifications: int
    ville_crossings: int
    discards: int


@dataclass(frozen=True)
class VilleCell:
    """Realized wrong-certification rate against the bound at one gate."""

    label: str
    gamma: float
    alpha: float
    composition: str
    arm: str
    bound: float
    is_factory_alpha: bool
    gate_reachable: bool
    null_tasks: int
    candidates: int
    candidate_rate: float | None
    wrong_certifications: int
    wrong_certification_rate: float | None
    wrong_certification_interval: tuple[float, float] | None
    wrong_certification_rate_all_null_tasks: float | None
    excess_ratio: float | None
    exceeds_bound: bool
    ville_crossings: int
    ville_crossing_rate: float | None
    discards: int
    per_seed: tuple[VilleSeedCounts, ...]


@dataclass(frozen=True)
class EProcessReport:
    """The whole diagnostic, content-addressed for pinning."""

    experiment: str
    status: str
    offline: bool
    config: dict[str, object]
    constants: dict[str, object]
    derived: dict[str, object]
    honesty: tuple[str, ...]
    expectations: tuple[NullExpectation, ...]
    ville: tuple[VilleCell, ...]
    digest: str

    def to_json_dict(self) -> dict[str, object]:
        payload = self._payload()
        payload["digest"] = self.digest
        return payload

    def _payload(self) -> dict[str, object]:
        return {
            "experiment": self.experiment,
            "status": self.status,
            "offline": self.offline,
            "config": self.config,
            "constants": self.constants,
            "derived": self.derived,
            "honesty": list(self.honesty),
            "expectations": [_expectation_json(row) for row in self.expectations],
            "ville": [_ville_json(cell) for cell in self.ville],
        }


def panel_vote_distribution(*, k: int, vote_rate: float, gamma: float) -> np.ndarray:
    """Exact distribution of the vote count under :func:`simulate_panel`.

    ``vote_rate`` is the chance that any one *independent* ballot asserts the
    finding: ``1 - judge_accuracy`` under the null, ``judge_accuracy`` under the
    alternative. Vote one is such a ballot; each later vote is a clone of it
    with probability ``gamma`` and an independent ballot otherwise, so with
    ``c`` clones the count is ``b * (1 + c) + Binomial(k - 1 - c, vote_rate)``.

    Written out rather than estimated because every analytic cross-check in this
    section — and the oracle e-value fixture that validates the estimator —
    rests on it. A test pins it against the generator it claims to describe.
    """
    if k < 1:
        raise ValueError("k must be at least one")
    _check_unit("vote_rate", vote_rate, closed=True)
    _check_unit("gamma", gamma, closed=True)

    distribution = np.zeros(k + 1)
    for first in (0, 1):
        first_probability = vote_rate if first else 1.0 - vote_rate
        if first_probability == 0.0:
            continue
        for clones in range(k):
            clone_probability = (
                math.comb(k - 1, clones) * gamma**clones * (1.0 - gamma) ** (k - 1 - clones)
            )
            if clone_probability == 0.0:
                continue
            free = k - 1 - clones
            base = first * (1 + clones)
            for hits in range(free + 1):
                hit_probability = (
                    math.comb(free, hits)
                    * vote_rate**hits
                    * (1.0 - vote_rate) ** (free - hits)
                )
                distribution[base + hits] += (
                    first_probability * clone_probability * hit_probability
                )
    return distribution


def oracle_panel_lr(*, k: int, judge_accuracy: float, gamma: float) -> tuple[float, ...]:
    """``P(V=v | theta=1) / P(V=v | theta=0)`` under the *actual* panel model.

    A valid e-value by construction: summing it against the null distribution
    recovers the alternative's total mass, which is one. It exists so the
    estimator can be validated on a quantity whose answer is known before the
    same estimator is pointed at the production schedule.

    Vote counts the null cannot produce (``gamma = 1`` leaves the interior
    empty) are given a ratio of one. They carry no null mass, so they cannot
    affect the null expectation either way.
    """
    _check_unit("judge_accuracy", judge_accuracy, closed=False)
    null = panel_vote_distribution(k=k, vote_rate=1.0 - judge_accuracy, gamma=gamma)
    alternative = panel_vote_distribution(k=k, vote_rate=judge_accuracy, gamma=gamma)
    ratio = np.ones(k + 1)
    np.divide(alternative, null, out=ratio, where=null > 0.0)
    return tuple(float(value) for value in ratio)


def two_sided_votes_lr(votes: int, k: int, judge_accuracy: float) -> float:
    """Counterfactual S channel: the normalized likelihood ratio of the vote count.

    ``P(V=v | theta=1) / P(V=v | theta=0)`` on the *independent* panel, which is
    the model the naive aggregator assumes. Being a normalized likelihood ratio
    it satisfies ``E[LR | theta=0] = 1`` exactly under that model, which the
    production schedule cannot: low vote counts are priced *below* one here, and
    ``votes = 0`` is priced lowest of all.

    **This is a diagnostic comparator, not a proposed patch.** It is not
    imported by, referenced by, or reachable from
    :mod:`attest.review.channels`, and it must not be: it is exactly valid only
    under the independence it assumes, this harness measures it breaking once
    the panel is correlated, and candidate conditioning breaks it as well.
    Replacing a factory schedule is an owner decision (ground rule 8) that
    cannot be justified on synthetic evidence.
    """
    if k < 1:
        raise ValueError("k must be at least one")
    if not 0 <= votes <= k:
        raise ValueError("votes must lie between zero and k")
    _check_unit("judge_accuracy", judge_accuracy, closed=False)
    return oracle_panel_lr(k=k, judge_accuracy=judge_accuracy, gamma=0.0)[votes]


def verification_e_validity_ceiling(no_purchase_rate: float) -> float:
    """Largest null reproduction rate at which the V channel stays an e-value.

    V is the only factory channel with a factor below one, so it is the only one
    that can satisfy the bound at all. Solving
    ``V_CAP * p + 1 * q + V_FAILED * (1 - p - q) <= 1`` for ``p`` gives
    ``(1 - V_FAILED) * (1 - q) / (V_CAP - V_FAILED)``. Derived from the shipped
    constants; nothing here chooses it.
    """
    _check_unit("no_purchase_rate", no_purchase_rate, closed=True)
    return (E_VALUE_BOUND - V_FAILED) * (1.0 - no_purchase_rate) / (V_CAP - V_FAILED)


def measure_channel_e_validity(
    *,
    judge_accuracy: float | None = None,
    k: int = 5,
    gamma: float = RHO,
    n_tasks: int = 2000,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    assumptions: NullAssumptions = DEFAULT_NULL_ASSUMPTIONS,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
    include_assumed_channels: bool = True,
) -> tuple[NullExpectation, ...]:
    """Estimate ``E[LR | theta=0]`` for every channel, both denominators.

    Every task in the stream is a false finding. The vote channel's null
    distribution — including the ``V = 0`` outcome at its true probability — is
    produced by the panel generator; the T and V channels have no generator and
    use :class:`NullAssumptions`, swept and reported.

    Four vote schedules are measured at the given correlation: the production
    one-sided schedule, the two-sided counterfactual, and the oracle likelihood
    ratio that validates the estimator. Each row carries both the unconditioned
    expectation and the expectation conditioned on the channel actually being
    purchased, which for votes is exactly the condition that a candidate exists.
    """
    accuracy = calibrated_vote_accuracy() if judge_accuracy is None else judge_accuracy
    _validate_null_design(
        k=k,
        n_tasks=n_tasks,
        seeds=seeds,
        gamma=gamma,
        accuracy=accuracy,
        bootstrap_resamples=bootstrap_resamples,
    )
    _check_assumptions(assumptions)

    streams = [
        _null_stream(
            gamma=gamma,
            judge_accuracy=accuracy,
            k=k,
            n_tasks=n_tasks,
            seed=seed,
            slots=assumptions.tier0_signal_slots,
        )
        for seed in seeds
    ]
    null_votes = panel_vote_distribution(k=k, vote_rate=1.0 - accuracy, gamma=gamma)

    rows: list[NullExpectation] = []
    schedules: tuple[tuple[str, tuple[float, ...]], ...] = (
        (PRODUCTION_ARM, tuple(votes_lr(votes) for votes in range(k + 1))),
        (TWO_SIDED_ARM, tuple(two_sided_votes_lr(votes, k, accuracy) for votes in range(k + 1))),
        (ORACLE_SCHEDULE, oracle_panel_lr(k=k, judge_accuracy=accuracy, gamma=gamma)),
    )
    for schedule, table in schedules:
        lrs = np.asarray(table, dtype=float)
        rows.append(
            _null_expectation(
                channel="S",
                schedule=schedule,
                label=f"S/{schedule}/gamma={_num(gamma)}",
                gamma=gamma,
                assumed_rate=None,
                assumption=None,
                condition=_CANDIDATE_CONDITION,
                samples=[
                    (stream.seed, lrs[stream.votes], stream.votes >= 1) for stream in streams
                ],
                analytic=_analytic_pair(null_votes, lrs, np.arange(k + 1) >= 1),
                bootstrap_seed=bootstrap_seed,
                resamples=bootstrap_resamples,
            )
        )

    if not include_assumed_channels:
        return tuple(rows)

    slots = assumptions.tier0_signal_slots
    tier0_table = np.asarray([tier0_lr(count) for count in range(slots + 1)], dtype=float)
    for rate in assumptions.tier0_signal_rates():
        counts = np.arange(slots + 1)
        null_signals = np.asarray(
            [math.comb(slots, n) * rate**n * (1.0 - rate) ** (slots - n) for n in counts],
            dtype=float,
        )
        rows.append(
            _null_expectation(
                channel="T",
                schedule=ASSUMED_SCHEDULE,
                label=f"T/{ASSUMED_SCHEDULE}/rate={_num(rate)}",
                gamma=None,
                assumed_rate=rate,
                assumption={
                    "tier0_signal_slots": slots,
                    "tier0_signal_rate": _num(rate),
                    "measured": False,
                },
                condition=_TIER0_CONDITION,
                samples=[
                    (
                        stream.seed,
                        tier0_table[_tier0_signals(stream, rate)],
                        _tier0_signals(stream, rate) >= 1,
                    )
                    for stream in streams
                ],
                analytic=_analytic_pair(null_signals, tier0_table, counts >= 1),
                bootstrap_seed=bootstrap_seed,
                resamples=bootstrap_resamples,
            )
        )

    no_purchase = assumptions.verification_no_purchase_rate
    verification_table = np.asarray(_VERIFICATION_LR, dtype=float)
    for rate in assumptions.verification_reproduce_rates():
        null_outcomes = np.zeros(_V_OUTCOMES)
        null_outcomes[_V_REPRODUCED] = rate
        null_outcomes[_V_NO_PURCHASE] = no_purchase
        null_outcomes[_V_NOT_REPRODUCED] = 1.0 - rate - no_purchase
        codes = [_verification_codes(stream, rate, no_purchase) for stream in streams]
        rows.append(
            _null_expectation(
                channel="V",
                schedule=ASSUMED_SCHEDULE,
                label=f"V/{ASSUMED_SCHEDULE}/rate={_num(rate)}",
                gamma=None,
                assumed_rate=rate,
                assumption={
                    "verification_reproduce_rate": _num(rate),
                    "verification_no_purchase_rate": _num(no_purchase),
                    "e_validity_ceiling": _num(verification_e_validity_ceiling(no_purchase)),
                    "measured": False,
                },
                condition=_VERIFICATION_CONDITION,
                samples=[
                    (stream.seed, verification_table[code], code != _V_NO_PURCHASE)
                    for stream, code in zip(streams, codes, strict=True)
                ],
                analytic=_analytic_pair(
                    null_outcomes,
                    verification_table,
                    np.arange(_V_OUTCOMES) != _V_NO_PURCHASE,
                ),
                bootstrap_seed=bootstrap_seed,
                resamples=bootstrap_resamples,
            )
        )
    return tuple(rows)


def measure_ville_bound(
    *,
    alphas: Sequence[float] = DEFAULT_VILLE_ALPHAS,
    judge_accuracy: float | None = None,
    k: int = 5,
    gamma: float = RHO,
    n_tasks: int = 2000,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    assumptions: NullAssumptions = DEFAULT_NULL_ASSUMPTIONS,
) -> tuple[VilleCell, ...]:
    """Compare the realized wrong-certification rate against the bound ``alpha``.

    Null-only streams: every finding is false, so *any* certification is wrong.
    The wealth process is rebuilt exactly as :func:`attest.review.gate.
    evaluate_finding` builds it — S, then T only if a signal exists, then V only
    if a verdict exists, each purchase skipped once the gate has already decided
    — and both the terminal decision and the running maximum are recorded.

    Two compositions are reported. ``votes_only`` isolates the S channel, which
    is the one whose e-validity is in question. ``full_channels`` multiplies in
    the assumed T and V behaviour, which is what can actually reach a factory
    gate at all (D-008: ``S_CAP * T_CAP = 9 < 10``).

    Where the realized rate exceeds ``alpha``, the process is not providing the
    advertised guarantee at that configuration.
    """
    accuracy = calibrated_vote_accuracy() if judge_accuracy is None else judge_accuracy
    _validate_null_design(
        k=k, n_tasks=n_tasks, seeds=seeds, gamma=gamma, accuracy=accuracy
    )
    _check_assumptions(assumptions)
    if not alphas:
        raise ValueError("at least one alpha is required")
    for alpha in alphas:
        _check_unit("alpha", alpha, closed=False)

    slots = assumptions.tier0_signal_slots
    streams = [
        _null_stream(
            gamma=gamma,
            judge_accuracy=accuracy,
            k=k,
            n_tasks=n_tasks,
            seed=seed,
            slots=slots,
        )
        for seed in seeds
    ]
    states = [
        (
            stream,
            _state_index(
                stream,
                slots=slots,
                signals=_tier0_signals(stream, assumptions.tier0_signal_rate),
                codes=_verification_codes(
                    stream,
                    assumptions.verification_reproduce_rate,
                    assumptions.verification_no_purchase_rate,
                ),
            ),
        )
        for stream in streams
    ]
    arms: tuple[tuple[str, tuple[float, ...]], ...] = (
        (PRODUCTION_ARM, tuple(votes_lr(votes) for votes in range(k + 1))),
        (TWO_SIDED_ARM, tuple(two_sided_votes_lr(votes, k, accuracy) for votes in range(k + 1))),
    )

    cells: list[VilleCell] = []
    for alpha in alphas:
        for composition in (VOTES_ONLY, FULL_CHANNELS):
            for arm, table in arms:
                cells.append(
                    _ville_cell(
                        gamma=gamma,
                        alpha=alpha,
                        composition=composition,
                        arm=arm,
                        vote_lrs=table,
                        slots=slots,
                        k=k,
                        states=states,
                    )
                )
    return tuple(cells)


def run_e_validity_experiment(
    *,
    gammas: Sequence[float] = DEFAULT_NULL_GAMMAS,
    alphas: Sequence[float] = DEFAULT_VILLE_ALPHAS,
    k: int = 5,
    n_tasks: int = 2000,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    judge_accuracy: float | None = None,
    assumptions: NullAssumptions = DEFAULT_NULL_ASSUMPTIONS,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> EProcessReport:
    """Both measurements over the preregistered grid, in one pinnable report."""
    if not gammas:
        raise ValueError("at least one gamma is required")
    for gamma in gammas:
        _check_unit("gamma", gamma, closed=True)
    accuracy = calibrated_vote_accuracy() if judge_accuracy is None else judge_accuracy

    expectations: list[NullExpectation] = []
    ville: list[VilleCell] = []
    for index, gamma in enumerate(gammas):
        expectations.extend(
            measure_channel_e_validity(
                judge_accuracy=accuracy,
                k=k,
                gamma=gamma,
                n_tasks=n_tasks,
                seeds=seeds,
                assumptions=assumptions,
                bootstrap_resamples=bootstrap_resamples,
                bootstrap_seed=bootstrap_seed,
                # The assumed channels do not depend on the panel correlation;
                # measuring them once keeps the artifact free of copies.
                include_assumed_channels=index == 0,
            )
        )
        ville.extend(
            measure_ville_bound(
                alphas=alphas,
                judge_accuracy=accuracy,
                k=k,
                gamma=gamma,
                n_tasks=n_tasks,
                seeds=seeds,
                assumptions=assumptions,
            )
        )

    report = EProcessReport(
        experiment="channel_e_value_validity",
        status="insufficient_labels/recommendation_only",
        offline=True,
        config={
            "gammas": [_num(gamma) for gamma in gammas],
            "alphas": [_num(alpha) for alpha in alphas],
            "k": k,
            "n_tasks": n_tasks,
            "seeds": list(seeds),
            "theta_prior": 0.0,
            "theta_prior_note": "null-only streams: every simulated finding is false",
            "judge_accuracy": _num(accuracy),
            "judge_accuracy_is_lr1_calibrated": accuracy == calibrated_vote_accuracy(),
            "bootstrap_resamples": bootstrap_resamples,
            "bootstrap_seed": bootstrap_seed,
            "bootstrap_confidence": _BOOTSTRAP_CONFIDENCE,
            "assumptions": assumptions.to_json_dict(),
        },
        constants={
            "lr1": LR1,
            "rho": RHO,
            "s_cap": S_CAP,
            "t_cap": T_CAP,
            "v_cap": V_CAP,
            "v_failed": V_FAILED,
            "vote_lr": list(VOTE_LR),
        },
        derived=_e_validity_derived(
            expectations=expectations,
            ville=ville,
            assumptions=assumptions,
            k=k,
        ),
        honesty=E_VALIDITY_HONESTY_NOTES,
        expectations=tuple(expectations),
        ville=tuple(ville),
        digest="",
    )
    return replace(report, digest=_digest(report._payload()))


def _e_validity_derived(
    *,
    expectations: Sequence[NullExpectation],
    ville: Sequence[VilleCell],
    assumptions: NullAssumptions,
    k: int,
) -> dict[str, object]:
    """Everything that follows from the shipped constants alone.

    The violation lists are the honest reporting surface: a refuted concern
    shows up as an empty list rather than as an absent claim.
    """
    slots = assumptions.tier0_signal_slots
    return {
        "e_value_bound": E_VALUE_BOUND,
        "e_value_violations": [
            row.label for row in expectations if row.lower_bound_exceeds_one
        ],
        "e_value_violations_candidate_conditioned": [
            row.label for row in expectations if row.conditioned_lower_bound_exceeds_one
        ],
        "ville_bound_breaches": [cell.label for cell in ville if cell.exceeds_bound],
        "channel_sign_structure": {
            "S": _sign_structure([votes_lr(votes) for votes in range(k + 1)]),
            "T": _sign_structure([tier0_lr(count) for count in range(slots + 1)]),
            "V": _sign_structure(list(_VERIFICATION_LR)),
        },
        "s_channel_e_validity_ceiling": 0.0,
        "tier0_e_validity_ceiling": 0.0,
        "one_sided_ceiling_note": (
            "S and T have no factor below one, so no positive purchase rate "
            "keeps their null expectation at or under the bound: the ceiling is "
            "zero by arithmetic, not by measurement."
        ),
        "verification_e_validity_ceiling": _num(
            verification_e_validity_ceiling(assumptions.verification_no_purchase_rate)
        ),
        "factory_alphas": list(FACTORY_ALPHAS),
        "factory_gate_reachable_on_votes_alone": {
            str(_num(alpha)): bool(1.0 / alpha <= S_CAP) for alpha in FACTORY_ALPHAS
        },
        "factory_gate_reachable_on_votes_and_tier0": {
            str(_num(alpha)): bool(1.0 / alpha <= S_CAP * T_CAP) for alpha in FACTORY_ALPHAS
        },
        "gate_feasibility": {
            str(_num(alpha)): gate_feasibility(alpha) for alpha in FACTORY_ALPHAS
        },
        "max_reachable_wealth": {
            "without_verification": max_reachable_wealth(False),
            "with_verification": max_reachable_wealth(True),
        },
    }


def _sign_structure(table: Sequence[float]) -> dict[str, object]:
    return {
        "min_lr": _num(min(table)),
        "max_lr": _num(max(table)),
        "has_factor_below_one": any(value < E_VALUE_BOUND for value in table),
        "one_sided": all(value >= E_VALUE_BOUND for value in table),
    }


def _null_stream(
    *,
    gamma: float,
    judge_accuracy: float,
    k: int,
    n_tasks: int,
    seed: int,
    slots: int,
) -> NullStream:
    """One null-only stream; see :class:`NullStream` for the draw-order contract."""
    panel = simulate_panel(
        gamma=gamma,
        theta_prior=0.0,
        judge_accuracy=judge_accuracy,
        k=k,
        n_tasks=n_tasks,
        seed=seed,
    )
    rng = np.random.default_rng([seed, _EVIDENCE_STREAM_TAG])
    signal_uniforms = rng.random((n_tasks, slots))
    verification_uniforms = rng.random(n_tasks)
    return NullStream(
        seed=seed,
        k=k,
        gamma=gamma,
        judge_accuracy=judge_accuracy,
        n_tasks=n_tasks,
        votes=panel.votes,
        signal_uniforms=signal_uniforms,
        verification_uniforms=verification_uniforms,
    )


def _tier0_signals(stream: NullStream, rate: float) -> np.ndarray:
    return (stream.signal_uniforms < rate).sum(axis=1).astype(np.int64)


def _verification_codes(
    stream: NullStream, reproduce_rate: float, no_purchase_rate: float
) -> np.ndarray:
    """Thresholds on one uniform draw, so a sweep re-cuts the same stream."""
    codes = np.full(stream.n_tasks, _V_NOT_REPRODUCED, dtype=np.int64)
    codes[stream.verification_uniforms < reproduce_rate + no_purchase_rate] = _V_NO_PURCHASE
    codes[stream.verification_uniforms < reproduce_rate] = _V_REPRODUCED
    return codes


def _state_index(
    stream: NullStream, *, slots: int, signals: np.ndarray, codes: np.ndarray
) -> np.ndarray:
    """Flatten (votes, signals, verification outcome) into one reachable state."""
    return (stream.votes * (slots + 1) + signals) * _V_OUTCOMES + codes


def _wealth_trace(
    *, vote_lr: float, tier0: float | None, verification: float | None, alpha: float
) -> tuple[float, float]:
    """Rebuild of :func:`attest.review.gate.evaluate_finding`'s purchase order.

    Production stops buying the moment the gate decides, so the running maximum
    of the wealth process crosses ``1 / alpha`` exactly when the terminal
    decision is a certification. That equivalence is what makes the realized
    wrong-certification rate the empirical left-hand side of Ville's inequality;
    a test asserts the two counts agree in every cell.
    """
    wealth = vote_lr
    peak = max(E_VALUE_BOUND, wealth)
    if tier0 is not None and decide(wealth, alpha) is None:
        wealth *= tier0
        peak = max(peak, wealth)
    if verification is not None and decide(wealth, alpha) is None:
        wealth *= verification
        peak = max(peak, wealth)
    return wealth, peak


def _state_decisions(
    *, k: int, slots: int, vote_lrs: Sequence[float], composition: str, alpha: float
) -> tuple[np.ndarray, np.ndarray]:
    """Production ``decide()`` evaluated once per reachable evidence state."""
    size = (k + 1) * (slots + 1) * _V_OUTCOMES
    decisions = np.full(size, -1, dtype=np.int64)
    crossings = np.zeros(size, dtype=bool)
    full = composition == FULL_CHANNELS
    for votes in range(k + 1):
        for signals in range(slots + 1):
            for code in range(_V_OUTCOMES):
                terminal, peak = _wealth_trace(
                    vote_lr=vote_lrs[votes],
                    tier0=tier0_lr(signals) if full and signals >= 1 else None,
                    verification=(
                        _VERIFICATION_LR[code] if full and code != _V_NO_PURCHASE else None
                    ),
                    alpha=alpha,
                )
                index = (votes * (slots + 1) + signals) * _V_OUTCOMES + code
                verdict = decide(terminal, alpha)
                decisions[index] = -1 if verdict is None else verdict
                crossings[index] = peak >= 1.0 / alpha
    return decisions, crossings


def _ville_cell(
    *,
    gamma: float,
    alpha: float,
    composition: str,
    arm: str,
    vote_lrs: Sequence[float],
    slots: int,
    k: int,
    states: Sequence[tuple[NullStream, np.ndarray]],
) -> VilleCell:
    decisions, crossings = _state_decisions(
        k=k, slots=slots, vote_lrs=vote_lrs, composition=composition, alpha=alpha
    )
    reachable = np.zeros(decisions.size, dtype=bool)
    for votes in range(1, k + 1):
        low = (votes * (slots + 1)) * _V_OUTCOMES
        reachable[low : low + (slots + 1) * _V_OUTCOMES] = True

    per_seed: list[VilleSeedCounts] = []
    tasks = candidates = wrong = crossed = discards = 0
    for stream, state in states:
        candidate_states = state[stream.votes >= 1]
        verdicts = decisions[candidate_states]
        seed_candidates = int(candidate_states.size)
        seed_wrong = int((verdicts == 1).sum())
        seed_crossed = int(crossings[candidate_states].sum())
        seed_discards = int((verdicts == 0).sum())
        per_seed.append(
            VilleSeedCounts(
                seed=stream.seed,
                null_tasks=stream.n_tasks,
                candidates=seed_candidates,
                wrong_certifications=seed_wrong,
                ville_crossings=seed_crossed,
                discards=seed_discards,
            )
        )
        tasks += stream.n_tasks
        candidates += seed_candidates
        wrong += seed_wrong
        crossed += seed_crossed
        discards += seed_discards

    rate = _rate(wrong, candidates)
    interval = _interval(wrong, candidates)
    return VilleCell(
        label=f"{arm}/{composition}/gamma={_num(gamma)}/alpha={_num(alpha)}",
        gamma=gamma,
        alpha=alpha,
        composition=composition,
        arm=arm,
        bound=alpha,
        is_factory_alpha=alpha in FACTORY_ALPHAS,
        gate_reachable=bool((decisions[reachable] == 1).any()),
        null_tasks=tasks,
        candidates=candidates,
        candidate_rate=_rate(candidates, tasks),
        wrong_certifications=wrong,
        wrong_certification_rate=rate,
        wrong_certification_interval=interval,
        wrong_certification_rate_all_null_tasks=_rate(wrong, tasks),
        excess_ratio=None if rate is None else rate / alpha,
        exceeds_bound=interval is not None and interval[0] > alpha,
        ville_crossings=crossed,
        ville_crossing_rate=_rate(crossed, candidates),
        discards=discards,
        per_seed=tuple(per_seed),
    )


def _analytic_pair(
    distribution: np.ndarray, table: np.ndarray, condition: np.ndarray
) -> tuple[float, float | None]:
    """Exact ``(E[LR], E[LR | purchased])`` from a closed-form null distribution.

    Reported beside every Monte Carlo estimate so the estimator can be checked
    against arithmetic rather than against itself.
    """
    unconditioned = float(np.dot(distribution, table))
    mass = float(distribution[condition].sum())
    if mass == 0.0:
        return unconditioned, None
    conditioned = float(np.dot(distribution[condition], table[condition]) / mass)
    return unconditioned, conditioned


def _null_expectation(
    *,
    channel: str,
    schedule: str,
    label: str,
    gamma: float | None,
    assumed_rate: float | None,
    assumption: dict[str, object] | None,
    condition: str,
    samples: Sequence[tuple[int, np.ndarray, np.ndarray]],
    analytic: tuple[float, float | None],
    bootstrap_seed: int,
    resamples: int,
) -> NullExpectation:
    per_seed: list[SeedMean] = []
    for seed, values, mask in samples:
        selected = values[mask]
        per_seed.append(
            SeedMean(
                seed=seed,
                samples=int(values.size),
                mean=float(values.mean()),
                conditioned_samples=int(selected.size),
                conditioned_mean=float(selected.mean()) if selected.size else None,
            )
        )

    pooled = np.concatenate([values for _, values, _ in samples])
    pooled_mask = np.concatenate([mask for _, _, mask in samples])
    mean = float(pooled.mean())
    interval = _bootstrap_interval(
        pooled, seed=_row_seed(bootstrap_seed, label, "all"), resamples=resamples
    )

    conditioned = pooled[pooled_mask]
    conditioned_mean: float | None = None
    conditioned_interval: tuple[float, float] | None = None
    conditioned_exceeds: bool | None = None
    if conditioned.size:
        conditioned_mean = float(conditioned.mean())
        conditioned_interval = _bootstrap_interval(
            conditioned,
            seed=_row_seed(bootstrap_seed, label, "conditioned"),
            resamples=resamples,
        )
        conditioned_exceeds = conditioned_interval[0] > E_VALUE_BOUND

    return NullExpectation(
        channel=channel,
        schedule=schedule,
        label=label,
        gamma=gamma,
        assumed_rate=assumed_rate,
        assumption=assumption,
        condition=condition,
        samples=int(pooled.size),
        mean=mean,
        interval=interval,
        e_validity_ratio=mean / E_VALUE_BOUND,
        lower_bound_exceeds_one=interval[0] > E_VALUE_BOUND,
        conditioned_samples=int(conditioned.size),
        conditioned_mean=conditioned_mean,
        conditioned_interval=conditioned_interval,
        conditioned_e_validity_ratio=(
            None if conditioned_mean is None else conditioned_mean / E_VALUE_BOUND
        ),
        conditioned_lower_bound_exceeds_one=conditioned_exceeds,
        analytic_mean=analytic[0],
        analytic_conditioned_mean=analytic[1],
        per_seed=tuple(per_seed),
    )


def _bootstrap_interval(
    values: np.ndarray, *, seed: int, resamples: int
) -> tuple[float, float]:
    """Percentile bootstrap of the sample mean.

    A likelihood ratio is not a proportion, so a Wilson interval does not apply
    to it; the bootstrap makes no distributional claim about a heavy-tailed
    multiplier. Resampling is blocked to bound memory, and the block size is
    part of the determinism contract.
    """
    if values.size == 0:
        raise ValueError("cannot bootstrap an empty sample")
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    filled = 0
    while filled < resamples:
        block = min(_BOOTSTRAP_BLOCK, resamples - filled)
        index = rng.integers(0, values.size, size=(block, values.size))
        means[filled : filled + block] = values[index].mean(axis=1)
        filled += block
    tail = (1.0 - _BOOTSTRAP_CONFIDENCE) / 2
    return float(np.quantile(means, tail)), float(np.quantile(means, 1.0 - tail))


def _row_seed(bootstrap_seed: int, label: str, suffix: str) -> int:
    """Per-row resampling seed, derived from the row's identity.

    Deriving it from the label rather than from a running counter keeps a row's
    interval identical no matter which other rows are present in the sweep.
    """
    key = f"{bootstrap_seed}:{label}:{suffix}".encode()
    return int.from_bytes(hashlib.sha256(key).digest()[:8], "big")


def _validate_null_design(
    *,
    k: int,
    n_tasks: int,
    seeds: Sequence[int],
    gamma: float,
    accuracy: float,
    bootstrap_resamples: int | None = None,
) -> None:
    if k < 1:
        raise ValueError("k must be at least one")
    if n_tasks < 1:
        raise ValueError("n_tasks must be at least one")
    if not seeds:
        raise ValueError("at least one seed is required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be unique")
    _check_unit("gamma", gamma, closed=True)
    _check_unit("judge_accuracy", accuracy, closed=False)
    if bootstrap_resamples is not None and bootstrap_resamples < 1:
        raise ValueError("bootstrap_resamples must be at least one")


def _check_assumptions(assumptions: NullAssumptions) -> None:
    """Validated at the point of use, so an assumption can be built and shown
    before it is judged."""
    if assumptions.tier0_signal_slots < 0:
        raise ValueError("tier0_signal_slots must not be negative")
    for rate in assumptions.tier0_signal_rates():
        _check_unit("tier0_signal_rate", rate, closed=True)
    _check_unit(
        "verification_no_purchase_rate", assumptions.verification_no_purchase_rate, closed=True
    )
    for rate in assumptions.verification_reproduce_rates():
        _check_unit("verification_reproduce_rate", rate, closed=True)
        if rate + assumptions.verification_no_purchase_rate > 1.0:
            raise ValueError("verification outcome probabilities must not exceed one")


def _seed_mean_json(row: SeedMean) -> dict[str, object]:
    return {
        "seed": row.seed,
        "samples": row.samples,
        "mean": _num(row.mean),
        "conditioned_samples": row.conditioned_samples,
        "conditioned_mean": _optional(row.conditioned_mean),
    }


def _expectation_json(row: NullExpectation) -> dict[str, object]:
    return {
        "channel": row.channel,
        "schedule": row.schedule,
        "label": row.label,
        "gamma": _optional(row.gamma),
        "assumed_rate": _optional(row.assumed_rate),
        "assumption": row.assumption,
        "condition": row.condition,
        "samples": row.samples,
        "mean": _num(row.mean),
        "interval": _pair(row.interval),
        "e_validity_ratio": _num(row.e_validity_ratio),
        "lower_bound_exceeds_one": row.lower_bound_exceeds_one,
        "conditioned_samples": row.conditioned_samples,
        "conditioned_mean": _optional(row.conditioned_mean),
        "conditioned_interval": _pair(row.conditioned_interval),
        "conditioned_e_validity_ratio": _optional(row.conditioned_e_validity_ratio),
        "conditioned_lower_bound_exceeds_one": row.conditioned_lower_bound_exceeds_one,
        "analytic_mean": _optional(row.analytic_mean),
        "analytic_conditioned_mean": _optional(row.analytic_conditioned_mean),
        "per_seed": [_seed_mean_json(entry) for entry in row.per_seed],
    }


def _ville_json(cell: VilleCell) -> dict[str, object]:
    return {
        "label": cell.label,
        "gamma": _num(cell.gamma),
        "alpha": _num(cell.alpha),
        "composition": cell.composition,
        "arm": cell.arm,
        "bound": _num(cell.bound),
        "is_factory_alpha": cell.is_factory_alpha,
        "gate_reachable": cell.gate_reachable,
        "null_tasks": cell.null_tasks,
        "candidates": cell.candidates,
        "candidate_rate": _optional(cell.candidate_rate),
        "wrong_certifications": cell.wrong_certifications,
        "wrong_certification_rate": _optional(cell.wrong_certification_rate),
        "wrong_certification_interval": _pair(cell.wrong_certification_interval),
        "wrong_certification_rate_all_null_tasks": _optional(
            cell.wrong_certification_rate_all_null_tasks
        ),
        "excess_ratio": _optional(cell.excess_ratio),
        "exceeds_bound": cell.exceeds_bound,
        "ville_crossings": cell.ville_crossings,
        "ville_crossing_rate": _optional(cell.ville_crossing_rate),
        "discards": cell.discards,
        "per_seed": [
            {
                "seed": entry.seed,
                "null_tasks": entry.null_tasks,
                "candidates": entry.candidates,
                "wrong_certifications": entry.wrong_certifications,
                "ville_crossings": entry.ville_crossings,
                "discards": entry.discards,
            }
            for entry in cell.per_seed
        ],
    }
