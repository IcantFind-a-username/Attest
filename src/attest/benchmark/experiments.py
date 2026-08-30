"""Experiment-only diagnostics for the factory evidence channels (D-007, D-023).

Five independent measurements live here, sharing one synthetic panel generator:

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
3. :func:`run_null_grid` — Task 8's multi-seed null grid: the REAL
   :class:`attest.core.engine.Engine` on null-only streams derived from the
   shipped generator's own draws, reproducing in-repo the external grid the
   status document could only quote.
4. :func:`run_monitor_policy_experiment` — D-004 follow-up: two reversible
   intervention policies against the alarm-only baseline, with the alarm kinds
   kept strictly separate and a high-error canary that actually errs.
5. :func:`run_two_ledger_experiment` — the owner's architecture question: S/T
   as verification PRIORITY only, certification wealth purchased by V alone,
   speech unchanged at ``certification_wealth >= 1/alpha``, and the
   verification budget a VOI queue saves over FCFS at fixed recall.

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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, NamedTuple

import numpy as np

from attest.benchmark.metrics import wilson_interval
from attest.core.allocation import choose_next, expected_log_e_signed
from attest.core.betting import decide, task_lr_purchase_order
from attest.core.engine import Engine, EngineConfig
from attest.core.exploration import ExplorationSchedule
from attest.core.monitor import WinnersCurseMonitor
from attest.core.stream import Stream, make_stream
from attest.core.tables import Tables
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


# ===========================================================================
# Task 8, experiment A: multi-seed null grids on the REAL core engine.
#
# The status document records an earlier external null grid (0 wrong
# certifications at alpha 0.05 over 80k tasks, 3 at 0.1, 544 at 0.2) that was
# never reproduced inside this repository. This section reproduces the
# measurement properly: preregistered seeds, the shipped attest.core Engine,
# null-only streams built from make_stream's own draws, independent and
# correlated panels, several stream lengths, both alarm kinds reported.
# ===========================================================================

NULL_GRID_EXPERIMENT = "core_engine_null_grid"

#: Preregistered grid. Three alphas including both factory gates plus the
#: loosened 0.2 the external grid used; independent and correlated panels;
#: two stream lengths; twenty seeds. Fixed before any cell was looked at.
DEFAULT_NULL_GRID_ALPHAS: tuple[float, ...] = (0.05, 0.1, 0.2)
DEFAULT_NULL_GRID_LENGTHS: tuple[int, ...] = (500, 2000)
DEFAULT_NULL_GRID_PANEL_GAMMAS: tuple[float, ...] = (0.0, 0.9)
DEFAULT_NULL_GRID_SEEDS: tuple[int, ...] = tuple(range(1, 21))

#: The repository's canonical informative three-judge panel (the accuracies
#: the core behavioural tests run). An uninformative panel cannot certify at
#: all, which would make the grid vacuous rather than safe.
NULL_GRID_ACCURACIES: tuple[float, float, float] = (0.8, 0.75, 0.7)

#: Rolling-window alarms are polled at this cadence and at the final task;
#: the cadence is part of the protocol and of the digest.
DEFAULT_ALARM_POLL_EVERY = 100

_ALARM_KINDS = ("spend_share_drift", "winners_curse_optimism")

#: Owner-provided figures from docs/real-data-evaluation-status.md, recorded
#: for comparison only. They were produced outside this repository, under an
#: unknown protocol, and are never merged into this grid's counts.
_PRIOR_EXTERNAL_MEASUREMENT: dict[str, object] = {
    "wrong_certifications_by_alpha": {"0.05": 0, "0.1": 3, "0.2": 544},
    "tasks_per_alpha": 80000,
    "alarm_summary": (
        "alarms in 12 of 40 runs, all spend_share_drift; a high-error canary "
        "run had no alarm"
    ),
    "independently_reproduced": False,
    "note": (
        "owner-provided figures from docs/real-data-evaluation-status.md; the "
        "generating scripts were never visible in this workspace, so the "
        "numbers are recorded for comparison only and never merged into this "
        "grid's counts"
    ),
}

NULL_GRID_HONESTY_NOTES: tuple[str, ...] = (
    "synthetic_streams: verdicts are the shipped make_stream generator's own "
    "draws, re-expressed under a null-only truth; nothing here samples a real "
    "model and no network or subprocess call is made.",
    "null-only truth: every task's ground truth is theta=0, so every "
    "certified-true decision is a wrong certification by construction and "
    "the theta=1 rows of the learned tables never move off their Laplace "
    "prior. That degeneracy is the real code path on an all-null stream, not "
    "a harness artifact.",
    "one_denominator_by_design: the engine judges every task in the stream — "
    "there is no candidate-selection filter in front of this gate — so the "
    "per-task denominator IS the per-decision denominator here, and it is "
    "named per_task to keep it comparable with reports that do have both.",
    "clone_rate_is_not_correlation: the panel parameter gamma is judge C's "
    "clone rate on judge B, not a pairwise panel correlation; the two "
    "correlated judges are B and C only.",
    "alarm_polling: rolling-window alarms are polled at a preregistered "
    "cadence and at the final task; a kind is counted once per poll in which "
    "it is present, so poll counts are not alarm-event counts.",
    "recommendation_only: this harness reads production code and constants "
    "and never writes them. Fewer than 500 global ledger labels exist "
    "(architecture red line 5), so every number here is a recommendation for "
    "the owner, never an authorisation.",
    "no_seed_selection: every preregistered seed is reported per cell, "
    "including any seed that produces wrong certifications.",
)


@dataclass(frozen=True)
class NullGridSeedRow:
    """One engine run: one seed, one stream, published in full."""

    seed: int
    tasks: int
    certifications: int
    wrong_certifications: int
    discards: int
    abstentions: int
    explored_tasks: int
    total_spend: float
    alarm_kinds: tuple[str, ...]


@dataclass(frozen=True)
class NullGridCell:
    """Pooled counts for one (panel, alpha, stream length) configuration."""

    label: str
    panel: str
    clone_gamma: float
    alpha: float
    stream_length: int
    runs: int
    tasks: int
    certifications: int
    wrong_certifications: int
    discards: int
    abstentions: int
    wrong_certification_rate_per_task: float | None
    wrong_certification_interval_per_task: tuple[float, float] | None
    exceeds_alpha_per_task: bool
    abstention_rate: float | None
    mean_spend_per_task: float | None
    alarm_polls: int
    alarm_poll_counts: dict[str, int]
    alarm_kinds_fired: tuple[str, ...]
    runs_with_any_alarm: int
    runs_with_optimism_alarm: int
    runs_with_drift_alarm: int
    per_seed: tuple[NullGridSeedRow, ...]


@dataclass(frozen=True)
class NullGridReport:
    """The whole grid, content-addressed for pinning."""

    experiment: str
    status: str
    offline: bool
    config: dict[str, object]
    constants: dict[str, object]
    derived: dict[str, object]
    honesty: tuple[str, ...]
    cells: tuple[NullGridCell, ...]
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
            "cells": [_null_grid_cell_json(cell) for cell in self.cells],
        }


def make_null_stream(
    acc_a: float, acc_b: float, acc_c: float, gamma: float, *, seed: int, n: int
) -> Stream:
    """The REAL :func:`attest.core.stream.make_stream` draw under a null truth.

    ``make_stream`` draws a mixed-truth stream; conditioning every task on
    ``theta = 0`` while keeping each judge's per-task agreement draw is exactly
    the XOR of the drawn verdict with the drawn truth. The clone edge survives:
    on a clone task C's verdict equals B's, and XOR by the same truth preserves
    the equality. Nothing is redrawn, so the null stream is byte-derived from
    the shipped generator rather than from a re-implementation of it.
    """
    for name, value in (("acc_a", acc_a), ("acc_b", acc_b), ("acc_c", acc_c)):
        _check_unit(name, value, closed=False)
    _check_unit("gamma", gamma, closed=True)
    if n < 1:
        raise ValueError("n must be at least one")
    stream = make_stream(acc_a, acc_b, acc_c, gamma, seed=seed, n=n, warmup=0)
    verdicts = {
        judge: np.bitwise_xor(votes, stream.theta)
        for judge, votes in stream.verdicts.items()
    }
    return Stream(np.zeros_like(stream.theta), verdicts, stream.explore)


def _verdict_getter(stream: Stream, index: int) -> Callable[[str], int]:
    """One task's verdict lookup, bound eagerly so the loop variable cannot leak."""

    def verdict(judge: str) -> int:
        return int(stream.verdicts[judge][index])

    return verdict


def _null_grid_engine_run(
    stream: Stream, *, alpha: float, engine_seed: int, poll_every: int
) -> tuple[NullGridSeedRow, dict[str, int]]:
    """One shipped-Engine run over one null stream, with periodic alarm polls.

    The loop is :meth:`attest.core.engine.Engine.run_stream` with a poll added;
    a test pins a row of this function against a direct ``run_stream`` call so
    the equivalence is checked rather than asserted. Returns the per-seed row
    and, separately, the number of polls in which each alarm kind was present.
    """
    engine = Engine(EngineConfig(alpha=alpha, seed=engine_seed))
    n = len(stream.theta)
    certifications = discards = explored = 0
    spend = 0.0
    poll_counts = {kind: 0 for kind in _ALARM_KINDS}
    kinds: set[str] = set()
    for index in range(n):
        result = engine.review_task(_verdict_getter(stream, index))
        engine.learn(int(stream.theta[index]), result)
        certifications += result.decision == 1
        discards += result.decision == 0
        explored += result.explored
        spend += sum(result.spend.values())
        if (index + 1) % poll_every == 0 or index == n - 1:
            present = {str(alarm["kind"]) for alarm in engine.monitor.alarms()}
            kinds |= present
            for kind in present:
                poll_counts[kind] = poll_counts.get(kind, 0) + 1
    row = NullGridSeedRow(
        seed=engine_seed,
        tasks=n,
        certifications=certifications,
        wrong_certifications=certifications,
        discards=discards,
        abstentions=n - certifications - discards,
        explored_tasks=explored,
        total_spend=spend,
        alarm_kinds=tuple(sorted(kinds)),
    )
    return row, poll_counts


def run_null_grid(
    *,
    alphas: Sequence[float] = DEFAULT_NULL_GRID_ALPHAS,
    stream_lengths: Sequence[int] = DEFAULT_NULL_GRID_LENGTHS,
    panel_gammas: Sequence[float] = DEFAULT_NULL_GRID_PANEL_GAMMAS,
    seeds: Sequence[int] = DEFAULT_NULL_GRID_SEEDS,
    accuracies: tuple[float, float, float] = NULL_GRID_ACCURACIES,
    alarm_poll_every: int = DEFAULT_ALARM_POLL_EVERY,
) -> NullGridReport:
    """Run the shipped Engine over every preregistered null-grid cell.

    Every task in every stream is a false finding, so every certified-true
    decision is a wrong certification. Both alarm kinds are polled and reported
    separately; the engine seed equals the stream seed so no second seed axis
    exists to select over.
    """
    if not alphas:
        raise ValueError("at least one alpha is required")
    for alpha in alphas:
        _check_unit("alpha", alpha, closed=False)
    if not stream_lengths:
        raise ValueError("at least one stream length is required")
    for length in stream_lengths:
        if length < 1:
            raise ValueError("stream lengths must be at least one")
    if not panel_gammas:
        raise ValueError("at least one panel gamma is required")
    for gamma in panel_gammas:
        _check_unit("gamma", gamma, closed=True)
    if not seeds:
        raise ValueError("at least one seed is required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be unique")
    if len(accuracies) != 3:
        raise ValueError("exactly three judge accuracies are required")
    for accuracy in accuracies:
        _check_unit("judge_accuracy", accuracy, closed=False)
    if alarm_poll_every < 1:
        raise ValueError("alarm_poll_every must be at least one")

    acc_a, acc_b, acc_c = accuracies
    cells: list[NullGridCell] = []
    for gamma in panel_gammas:
        for alpha in alphas:
            for length in stream_lengths:
                runs = [
                    _null_grid_engine_run(
                        make_null_stream(
                            acc_a, acc_b, acc_c, gamma, seed=seed, n=length
                        ),
                        alpha=alpha,
                        engine_seed=seed,
                        poll_every=alarm_poll_every,
                    )
                    for seed in seeds
                ]
                rows = tuple(row for row, _ in runs)
                poll_counts = {kind: 0 for kind in _ALARM_KINDS}
                for _, counts in runs:
                    for kind, count in counts.items():
                        poll_counts[kind] += count
                cells.append(
                    _null_grid_cell(
                        gamma, alpha, length, rows, alarm_poll_every, poll_counts
                    )
                )

    engine_defaults = EngineConfig()
    monitor_defaults = WinnersCurseMonitor()
    report = NullGridReport(
        experiment=NULL_GRID_EXPERIMENT,
        status="insufficient_labels/recommendation_only",
        offline=True,
        config={
            "alphas": [_num(alpha) for alpha in alphas],
            "stream_lengths": list(stream_lengths),
            "panel_gammas": [_num(gamma) for gamma in panel_gammas],
            "seeds": list(seeds),
            "accuracies": [_num(accuracy) for accuracy in accuracies],
            "alarm_poll_every": alarm_poll_every,
            "theta": "null-only: every task's ground truth is theta=0",
            "engine_seed_rule": "engine seed equals stream seed",
            "gammas_are_clone_rates": True,
        },
        constants={
            "engine": {
                "judges": list(engine_defaults.judges),
                "prices": {j: _num(engine_defaults.prices[j]) for j in engine_defaults.judges},
                "variant": engine_defaults.variant,
                "tau": _num(engine_defaults.tau),
                "smoothing": _num(engine_defaults.smoothing),
                "price_aware": engine_defaults.price_aware,
                "eps_hot": _num(engine_defaults.eps_hot),
                "eps_cold": _num(engine_defaults.eps_cold),
                "cell_target": engine_defaults.cell_target,
            },
            "monitor": {
                "window": monitor_defaults.window,
                "optimism_threshold": _num(monitor_defaults.optimism_threshold),
                "min_samples": monitor_defaults.min_samples,
                "drift_threshold": _num(monitor_defaults.drift_threshold),
            },
        },
        derived={
            "prior_external_measurement": dict(_PRIOR_EXTERNAL_MEASUREMENT),
            "wrong_certification_totals_by_alpha": {
                str(_num(alpha)): sum(
                    cell.wrong_certifications for cell in cells if cell.alpha == alpha
                )
                for alpha in alphas
            },
            "tasks_by_alpha": {
                str(_num(alpha)): sum(cell.tasks for cell in cells if cell.alpha == alpha)
                for alpha in alphas
            },
            "cells_exceeding_alpha_per_task": [
                cell.label for cell in cells if cell.exceeds_alpha_per_task
            ],
            "alarm_kinds_ever_fired": sorted(
                {kind for cell in cells for kind in cell.alarm_kinds_fired}
            ),
            "optimism_alarm_ever_fired": any(
                "winners_curse_optimism" in cell.alarm_kinds_fired for cell in cells
            ),
        },
        honesty=NULL_GRID_HONESTY_NOTES,
        cells=tuple(cells),
        digest="",
    )
    return replace(report, digest=_digest(report._payload()))


def _null_grid_cell(
    gamma: float,
    alpha: float,
    length: int,
    rows: tuple[NullGridSeedRow, ...],
    poll_every: int,
    poll_counts: dict[str, int],
) -> NullGridCell:
    tasks = sum(row.tasks for row in rows)
    certifications = sum(row.certifications for row in rows)
    wrong = sum(row.wrong_certifications for row in rows)
    discards = sum(row.discards for row in rows)
    abstentions = sum(row.abstentions for row in rows)
    spend = sum(row.total_spend for row in rows)
    interval = _interval(wrong, tasks)
    polls_per_run = (length + poll_every - 1) // poll_every
    kinds = sorted({kind for row in rows for kind in row.alarm_kinds})
    return NullGridCell(
        label=f"gamma={_num(gamma)}/alpha={_num(alpha)}/n={length}",
        panel="independent" if gamma == 0.0 else "correlated",
        clone_gamma=gamma,
        alpha=alpha,
        stream_length=length,
        runs=len(rows),
        tasks=tasks,
        certifications=certifications,
        wrong_certifications=wrong,
        discards=discards,
        abstentions=abstentions,
        wrong_certification_rate_per_task=_rate(wrong, tasks),
        wrong_certification_interval_per_task=interval,
        exceeds_alpha_per_task=interval is not None and interval[0] > alpha,
        abstention_rate=_rate(abstentions, tasks),
        mean_spend_per_task=None if tasks == 0 else spend / tasks,
        alarm_polls=polls_per_run * len(rows),
        alarm_poll_counts=poll_counts,
        alarm_kinds_fired=tuple(kinds),
        runs_with_any_alarm=sum(1 for row in rows if row.alarm_kinds),
        runs_with_optimism_alarm=sum(
            1 for row in rows if "winners_curse_optimism" in row.alarm_kinds
        ),
        runs_with_drift_alarm=sum(
            1 for row in rows if "spend_share_drift" in row.alarm_kinds
        ),
        per_seed=rows,
    )


def _null_grid_cell_json(cell: NullGridCell) -> dict[str, object]:
    return {
        "label": cell.label,
        "panel": cell.panel,
        "clone_gamma": _num(cell.clone_gamma),
        "alpha": _num(cell.alpha),
        "stream_length": cell.stream_length,
        "runs": cell.runs,
        "tasks": cell.tasks,
        "certifications": cell.certifications,
        "wrong_certifications": cell.wrong_certifications,
        "discards": cell.discards,
        "abstentions": cell.abstentions,
        "wrong_certification_rate_per_task": _optional(
            cell.wrong_certification_rate_per_task
        ),
        "wrong_certification_interval_per_task": _pair(
            cell.wrong_certification_interval_per_task
        ),
        "exceeds_alpha_per_task": cell.exceeds_alpha_per_task,
        "abstention_rate": _optional(cell.abstention_rate),
        "mean_spend_per_task": _optional(cell.mean_spend_per_task),
        "alarm_polls": cell.alarm_polls,
        "alarm_poll_counts": dict(cell.alarm_poll_counts),
        "alarm_kinds_fired": list(cell.alarm_kinds_fired),
        "runs_with_any_alarm": cell.runs_with_any_alarm,
        "runs_with_optimism_alarm": cell.runs_with_optimism_alarm,
        "runs_with_drift_alarm": cell.runs_with_drift_alarm,
        "per_seed": [
            {
                "seed": row.seed,
                "tasks": row.tasks,
                "certifications": row.certifications,
                "wrong_certifications": row.wrong_certifications,
                "discards": row.discards,
                "abstentions": row.abstentions,
                "explored_tasks": row.explored_tasks,
                "total_spend": _num(row.total_spend),
                "alarm_kinds": list(row.alarm_kinds),
            }
            for row in cell.per_seed
        ],
    }


# ===========================================================================
# Task 8, experiment B: monitor intervention policies.
#
# D-004's winner's-curse monitor is alarm-only. This section simulates two
# reversible interventions against the ledger-only baseline on seeded
# streams, keeping winners_curse_optimism strictly separate from
# spend_share_drift throughout: drift alone is never treated as evidence of
# invalid evidence and never triggers a brake. A high-error canary — a
# mid-stream distribution shift that leaves the learned tables stale — is
# included so 'missed unsafe run' is measured against a stream that really
# does produce wrong certifications.
# ===========================================================================

MONITOR_POLICY_EXPERIMENT = "monitor_intervention_policies"

POLICY_LEDGER_ONLY = "ledger_only"
POLICY_QUARANTINE = "quarantine_optimistic_judge"
POLICY_EXPLORATION_RECOVERY = "exploration_only_recovery"
MONITOR_POLICIES: tuple[str, ...] = (
    POLICY_LEDGER_ONLY,
    POLICY_QUARANTINE,
    POLICY_EXPLORATION_RECOVERY,
)

HEALTHY_CONFIGURATION = "healthy"
CANARY_CONFIGURATION = "high_error_canary"

#: The judge whose behaviour shifts mid-stream in the canary. Judge A is the
#: only judge with no clone edge in make_stream, so shifting it never touches
#: the B/C correlation structure.
CANARY_JUDGE = "A"

DEFAULT_POLICY_SEEDS: tuple[int, ...] = DEFAULT_SEEDS
DEFAULT_POLICY_TASKS = 2000
DEFAULT_CANARY_ACCURACY = 0.1
DEFAULT_CANARY_SHIFT_FRACTION = 0.5

#: Second generator per seed for the canary's post-shift draws, so the healthy
#: prefix stays byte-identical to the healthy stream at the same seed.
_CANARY_TAG = 20260831

MONITOR_POLICY_HONESTY_NOTES: tuple[str, ...] = (
    "synthetic_streams: verdicts come from the shipped make_stream generator "
    "(plus a tagged post-shift redraw for the canary judge); nothing here "
    "samples a real model and no network or subprocess call is made.",
    "engine_loop_is_a_pinned_rebuild: the policy driver is a rebuild of "
    "Engine.review_task/learn (po_calib) with two reversible interventions "
    "added — the same approach the Ville section takes to gate."
    "evaluate_finding — and a test pins its ledger-only mode equal to the "
    "shipped Engine, decision for decision, on the same stream and seed.",
    "alarm_kind_separation: winners_curse_optimism and spend_share_drift are "
    "reported separately everywhere, and ONLY winners_curse_optimism can "
    "trigger an intervention. spend_share_drift alone is never treated as "
    "evidence of invalid evidence; it is recorded and left alone.",
    "reversible_interventions_only: quarantine removes the optimistic judge "
    "from ADAPTIVE purchases while its alarm is active — exploration tasks "
    "still buy every judge, which is what lets the tables recover and the "
    "alarm clear — and exploration-only recovery forces the all-buy "
    "calibration slice while any optimism alarm is active. Both switch off "
    "by themselves when the window clears; neither writes to any table "
    "schedule or constant.",
    "designed_canary: the high-error configuration is a preregistered "
    "mid-stream distribution shift (the canary judge's accuracy drops after "
    "the shift point while the learned tables stay stale), not a measured "
    "failure mode of any real judge. It exists so 'missed unsafe run' has an "
    "actually-unsafe run to miss.",
    "recommendation_only: this harness reads production code and constants "
    "and never writes them. Fewer than 500 global ledger labels exist "
    "(architecture red line 5), and monitor behaviour is factory behaviour "
    "under ground rule 8, so every number here is a recommendation for the "
    "owner, never an authorisation.",
    "no_seed_selection: every preregistered seed is reported per cell and "
    "per policy, including seeds where a policy brakes falsely or misses.",
)


class PolicyRun(NamedTuple):
    """One policy-driven stream run, exposed task by task for pinning."""

    policy: str
    decisions: tuple[int | None, ...]
    wealth: tuple[float, ...]
    explored: tuple[bool, ...]
    forced_exploration: tuple[bool, ...]
    intervention_active: tuple[bool, ...]
    optimism_active: tuple[bool, ...]
    drift_active: tuple[bool, ...]
    quarantined: tuple[tuple[str, ...], ...]
    orders: tuple[tuple[str, ...], ...]
    spend: tuple[float, ...]
    intervention_episodes: int


@dataclass(frozen=True)
class PolicySeedRow:
    """One (configuration, policy, seed) run, published in full."""

    seed: int
    tasks: int
    decided: int
    surfaced: int
    discarded: int
    wrong_certifications: int
    wrong_certifications_post_shift: int
    abstentions: int
    explored_tasks: int
    forced_exploration_tasks: int
    intervention_tasks: int
    intervention_episodes: int
    optimism_alarm_tasks: int
    drift_alarm_tasks: int
    total_spend: float
    intervened: bool
    optimism_alarmed: bool
    drift_alarmed: bool
    responded: bool


@dataclass(frozen=True)
class PolicyCell:
    """Pooled outcome for one (configuration, policy) pair.

    ``false_brake_rate`` exists only on healthy cells and only for policies
    that can intervene at all; ``missed_unsafe_run_rate`` exists only on
    canary cells. For the ledger-only baseline the response under measurement
    is the optimism alarm itself, because that arm cannot brake by design.
    """

    label: str
    configuration: str
    policy: str
    alpha: float
    runs: int
    tasks: int
    decided: int
    surfaced: int
    discarded: int
    wrong_certifications: int
    wrong_certifications_post_shift: int
    abstentions: int
    wrong_certification_rate_per_task: float | None
    wrong_certification_interval_per_task: tuple[float, float] | None
    abstention_rate: float | None
    mean_spend_per_task: float | None
    explored_tasks: int
    forced_exploration_tasks: int
    intervention_tasks: int
    intervention_episodes: int
    runs_with_intervention: int
    runs_with_optimism_alarm: int
    runs_with_drift_alarm: int
    runs_with_response: int
    intervention_capable: bool
    false_brake_rate: float | None
    false_brake_interval: tuple[float, float] | None
    missed_unsafe_run_rate: float | None
    missed_unsafe_interval: tuple[float, float] | None
    per_seed: tuple[PolicySeedRow, ...]


@dataclass(frozen=True)
class MonitorPolicyReport:
    """The whole policy comparison, content-addressed for pinning."""

    experiment: str
    status: str
    offline: bool
    config: dict[str, object]
    constants: dict[str, object]
    derived: dict[str, object]
    honesty: tuple[str, ...]
    cells: tuple[PolicyCell, ...]
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
            "cells": [_policy_cell_json(cell) for cell in self.cells],
        }


def optimism_alarm_judges(alarms: Sequence[Mapping[str, Any]]) -> tuple[str, ...]:
    """Judges named by winners_curse_optimism alarms — and nothing else.

    This is the ONLY reading of the alarm list any intervention is allowed to
    act on: spend_share_drift alarms are ignored here by design, because drift
    alone is never evidence of invalid evidence (D-004).
    """
    return tuple(
        sorted(
            {
                str(alarm["judge"])
                for alarm in alarms
                if alarm.get("kind") == "winners_curse_optimism"
            }
        )
    )


def make_canary_stream(
    acc_a: float,
    acc_b: float,
    acc_c: float,
    gamma: float,
    *,
    seed: int,
    n: int,
    canary_accuracy: float,
    shift: int,
) -> Stream:
    """A healthy make_stream draw whose canary judge degrades after ``shift``.

    Tasks before the shift are byte-identical to the healthy stream at the
    same seed. From the shift onward, judge A's verdicts are redrawn from a
    tagged second generator at ``canary_accuracy``, so the tables the engine
    learned on the healthy prefix are stale — the winner's-curse shape.
    B and C are untouched, so the clone structure is preserved exactly.
    """
    for name, value in (("acc_a", acc_a), ("acc_b", acc_b), ("acc_c", acc_c)):
        _check_unit(name, value, closed=False)
    _check_unit("gamma", gamma, closed=True)
    _check_unit("canary_accuracy", canary_accuracy, closed=True)
    if n < 2:
        raise ValueError("n must be at least two")
    if not 1 <= shift < n:
        raise ValueError("shift must lie strictly inside the stream")

    healthy = make_stream(acc_a, acc_b, acc_c, gamma, seed=seed, n=n, warmup=0)
    rng = np.random.default_rng([seed, _CANARY_TAG])
    agrees = rng.random(n) < canary_accuracy
    shifted = np.where(agrees, healthy.theta, 1 - healthy.theta)
    verdicts = dict(healthy.verdicts)
    canary_votes = verdicts[CANARY_JUDGE].copy()
    canary_votes[shift:] = shifted[shift:]
    verdicts[CANARY_JUDGE] = canary_votes
    return Stream(healthy.theta, verdicts, healthy.explore)


def run_policy_stream(
    stream: Stream, *, alpha: float, policy: str, engine_seed: int
) -> PolicyRun:
    """Drive one stream through the engine loop under one monitor policy.

    This is a faithful rebuild of ``Engine.review_task``/``learn`` in the
    default ``po_calib`` variant — same RNG draw order, same purchase rule,
    same monitor records, same calibration-slice learning — with exactly two
    additions, both inert under ``ledger_only``:

    * ``quarantine_optimistic_judge``: judges currently named by a
      winners_curse_optimism alarm are excluded from the ADAPTIVE candidate
      list. Exploration tasks still buy all judges, which is what feeds the
      tables and lets the alarm clear.
    * ``exploration_only_recovery``: while any winners_curse_optimism alarm
      is active, every task is an all-buy exploration task.

    A test pins the ledger-only mode equal to the shipped Engine on the same
    stream and seed, which is what licenses the rebuild.
    """
    if policy not in MONITOR_POLICIES:
        raise ValueError(f"unknown policy {policy!r}")
    config = EngineConfig(alpha=alpha, seed=engine_seed)
    tables = Tables(config.judges, config.smoothing)
    schedule = ExplorationSchedule(config.eps_hot, config.eps_cold, config.cell_target)
    monitor = WinnersCurseMonitor()
    rng = np.random.default_rng(config.seed)

    n = len(stream.theta)
    decisions: list[int | None] = []
    wealths: list[float] = []
    explored_flags: list[bool] = []
    forced_flags: list[bool] = []
    active_flags: list[bool] = []
    optimism_flags: list[bool] = []
    drift_flags: list[bool] = []
    quarantined_rows: list[tuple[str, ...]] = []
    orders: list[tuple[str, ...]] = []
    spends: list[float] = []
    episodes = 0
    previously_active = False

    for index in range(n):
        alarms = monitor.alarms()
        optimism = optimism_alarm_judges(alarms)
        drift = any(alarm.get("kind") == "spend_share_drift" for alarm in alarms)
        quarantined = optimism if policy == POLICY_QUARANTINE else ()
        forced = bool(optimism) and policy == POLICY_EXPLORATION_RECOVERY
        explored = schedule.should_explore(rng, tables) or forced

        order: list[str] = []
        verdicts: dict[str, int] = {}
        spend = 0.0
        if explored:
            all_order = list(config.judges)
            rng.shuffle(all_order)
            wealth = 1.0
            for judge in all_order:
                p1post = wealth / (1.0 + wealth)
                estimated = expected_log_e_signed(tables, judge, verdicts, p1post)
                verdict = int(stream.verdicts[judge][index])
                realized = float(np.log(tables.lr_factor(judge, verdicts, verdict)))
                order.append(judge)
                verdicts[judge] = verdict
                spend += config.prices[judge]
                monitor.record(judge, estimated, realized, config.prices[judge])
                wealth = task_lr_purchase_order(tables, order, verdicts)
        else:
            wealth = 1.0
            while True:
                if decide(wealth, config.alpha) is not None:
                    break
                candidates = [
                    judge
                    for judge in config.judges
                    if judge not in verdicts and judge not in quarantined
                ]
                if not candidates:
                    break
                best, _ = choose_next(
                    tables,
                    candidates,
                    verdicts,
                    wealth,
                    config.prices,
                    config.price_aware,
                    config.tau,
                )
                if best is None:
                    break
                p1post = wealth / (1.0 + wealth)
                estimated = expected_log_e_signed(tables, best, verdicts, p1post)
                verdict = int(stream.verdicts[best][index])
                realized = float(np.log(tables.lr_factor(best, verdicts, verdict)))
                order.append(best)
                verdicts[best] = verdict
                spend += config.prices[best]
                monitor.record(best, estimated, realized, config.prices[best])
                wealth = task_lr_purchase_order(tables, order, verdicts)

        if explored:
            tables.update(int(stream.theta[index]), verdicts)

        active = bool(quarantined) or forced
        if active and not previously_active:
            episodes += 1
        previously_active = active

        decisions.append(decide(wealth, config.alpha))
        wealths.append(wealth)
        explored_flags.append(explored)
        forced_flags.append(forced)
        active_flags.append(active)
        optimism_flags.append(bool(optimism))
        drift_flags.append(drift)
        quarantined_rows.append(tuple(quarantined))
        orders.append(tuple(order))
        spends.append(spend)

    return PolicyRun(
        policy=policy,
        decisions=tuple(decisions),
        wealth=tuple(wealths),
        explored=tuple(explored_flags),
        forced_exploration=tuple(forced_flags),
        intervention_active=tuple(active_flags),
        optimism_active=tuple(optimism_flags),
        drift_active=tuple(drift_flags),
        quarantined=tuple(quarantined_rows),
        orders=tuple(orders),
        spend=tuple(spends),
        intervention_episodes=episodes,
    )


def run_monitor_policy_experiment(
    *,
    alpha: float = 0.1,
    n_tasks: int = DEFAULT_POLICY_TASKS,
    seeds: Sequence[int] = DEFAULT_POLICY_SEEDS,
    gamma: float = 0.0,
    accuracies: tuple[float, float, float] = NULL_GRID_ACCURACIES,
    canary_accuracy: float = DEFAULT_CANARY_ACCURACY,
    canary_shift_fraction: float = DEFAULT_CANARY_SHIFT_FRACTION,
    policies: Sequence[str] = MONITOR_POLICIES,
) -> MonitorPolicyReport:
    """Compare the three policies on shared healthy and canary streams.

    Every policy sees the identical stream at a given (configuration, seed),
    so differences between policies are differences in intervention behaviour
    and its knock-on effect on learning, never in the draw.
    """
    _check_unit("alpha", alpha, closed=False)
    if n_tasks < 2:
        raise ValueError("n_tasks must be at least two")
    if not seeds:
        raise ValueError("at least one seed is required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be unique")
    _check_unit("gamma", gamma, closed=True)
    if len(accuracies) != 3:
        raise ValueError("exactly three judge accuracies are required")
    for accuracy in accuracies:
        _check_unit("judge_accuracy", accuracy, closed=False)
    _check_unit("canary_accuracy", canary_accuracy, closed=True)
    if not 0.0 < canary_shift_fraction < 1.0:
        raise ValueError("canary_shift_fraction must lie strictly inside (0, 1)")
    if not policies:
        raise ValueError("at least one policy is required")
    for policy in policies:
        if policy not in MONITOR_POLICIES:
            raise ValueError(f"unknown policy {policy!r}")
    if len(set(policies)) != len(policies):
        raise ValueError("policies must be unique")

    shift = int(n_tasks * canary_shift_fraction)
    shift = min(max(shift, 1), n_tasks - 1)
    acc_a, acc_b, acc_c = accuracies
    streams: dict[tuple[str, int], Stream] = {}
    for seed in seeds:
        streams[(HEALTHY_CONFIGURATION, seed)] = make_stream(
            acc_a, acc_b, acc_c, gamma, seed=seed, n=n_tasks, warmup=0
        )
        streams[(CANARY_CONFIGURATION, seed)] = make_canary_stream(
            acc_a,
            acc_b,
            acc_c,
            gamma,
            seed=seed,
            n=n_tasks,
            canary_accuracy=canary_accuracy,
            shift=shift,
        )

    cells: list[PolicyCell] = []
    for configuration in (HEALTHY_CONFIGURATION, CANARY_CONFIGURATION):
        for policy in policies:
            rows = tuple(
                _policy_seed_row(
                    streams[(configuration, seed)],
                    alpha=alpha,
                    policy=policy,
                    seed=seed,
                    shift=shift,
                )
                for seed in seeds
            )
            cells.append(_policy_cell(configuration, policy, alpha, rows))

    engine_defaults = EngineConfig()
    monitor_defaults = WinnersCurseMonitor()
    canary_cells = [cell for cell in cells if cell.configuration == CANARY_CONFIGURATION]
    catching = [cell.policy for cell in canary_cells if cell.runs_with_response > 0]
    report = MonitorPolicyReport(
        experiment=MONITOR_POLICY_EXPERIMENT,
        status="insufficient_labels/recommendation_only",
        offline=True,
        config={
            "alpha": _num(alpha),
            "n_tasks": n_tasks,
            "seeds": list(seeds),
            "gamma": _num(gamma),
            "accuracies": [_num(accuracy) for accuracy in accuracies],
            "canary_judge": CANARY_JUDGE,
            "canary_accuracy": _num(canary_accuracy),
            "canary_shift_fraction": _num(canary_shift_fraction),
            "canary_shift_index": shift,
            "policies": list(policies),
            "engine_seed_rule": "engine seed equals stream seed",
            "streams_shared_across_policies": True,
        },
        constants={
            "engine": {
                "judges": list(engine_defaults.judges),
                "prices": {j: _num(engine_defaults.prices[j]) for j in engine_defaults.judges},
                "variant": engine_defaults.variant,
                "tau": _num(engine_defaults.tau),
                "eps_hot": _num(engine_defaults.eps_hot),
                "eps_cold": _num(engine_defaults.eps_cold),
                "cell_target": engine_defaults.cell_target,
            },
            "monitor": {
                "window": monitor_defaults.window,
                "optimism_threshold": _num(monitor_defaults.optimism_threshold),
                "min_samples": monitor_defaults.min_samples,
                "drift_threshold": _num(monitor_defaults.drift_threshold),
            },
        },
        derived={
            "policies_catching_canary": catching,
            "canary_caught_by_any_policy": bool(catching),
            "canary_wrong_certifications_by_policy": {
                cell.policy: cell.wrong_certifications for cell in canary_cells
            },
            "canary_post_shift_wrong_certifications_by_policy": {
                cell.policy: cell.wrong_certifications_post_shift for cell in canary_cells
            },
            "false_brake_rate_by_policy": {
                cell.policy: _optional(cell.false_brake_rate)
                for cell in cells
                if cell.configuration == HEALTHY_CONFIGURATION
            },
            "missed_unsafe_run_rate_by_policy": {
                cell.policy: _optional(cell.missed_unsafe_run_rate)
                for cell in canary_cells
            },
            "mean_spend_per_task_by_cell": {
                cell.label: _optional(cell.mean_spend_per_task) for cell in cells
            },
            "drift_never_triggers_note": (
                "spend_share_drift is reported but can never activate an "
                "intervention; only winners_curse_optimism can"
            ),
        },
        honesty=MONITOR_POLICY_HONESTY_NOTES,
        cells=tuple(cells),
        digest="",
    )
    return replace(report, digest=_digest(report._payload()))


def _policy_seed_row(
    stream: Stream, *, alpha: float, policy: str, seed: int, shift: int
) -> PolicySeedRow:
    run = run_policy_stream(stream, alpha=alpha, policy=policy, engine_seed=seed)
    theta = stream.theta
    n = len(theta)
    decided = surfaced = discarded = wrong = wrong_post = 0
    for index, decision in enumerate(run.decisions):
        if decision is None:
            continue
        decided += 1
        surfaced += decision == 1
        discarded += decision == 0
        if decision != int(theta[index]):
            wrong += 1
            wrong_post += index >= shift
    intervention_tasks = sum(run.intervention_active)
    optimism_tasks = sum(run.optimism_active)
    drift_tasks = sum(run.drift_active)
    capable = policy != POLICY_LEDGER_ONLY
    intervened = intervention_tasks > 0
    optimism_alarmed = optimism_tasks > 0
    return PolicySeedRow(
        seed=seed,
        tasks=n,
        decided=decided,
        surfaced=surfaced,
        discarded=discarded,
        wrong_certifications=wrong,
        wrong_certifications_post_shift=wrong_post,
        abstentions=n - decided,
        explored_tasks=sum(run.explored),
        forced_exploration_tasks=sum(run.forced_exploration),
        intervention_tasks=intervention_tasks,
        intervention_episodes=run.intervention_episodes,
        optimism_alarm_tasks=optimism_tasks,
        drift_alarm_tasks=drift_tasks,
        total_spend=float(sum(run.spend)),
        intervened=intervened,
        optimism_alarmed=optimism_alarmed,
        drift_alarmed=drift_tasks > 0,
        responded=intervened if capable else optimism_alarmed,
    )


def _policy_cell(
    configuration: str, policy: str, alpha: float, rows: tuple[PolicySeedRow, ...]
) -> PolicyCell:
    runs = len(rows)
    tasks = sum(row.tasks for row in rows)
    wrong = sum(row.wrong_certifications for row in rows)
    abstentions = sum(row.abstentions for row in rows)
    spend = sum(row.total_spend for row in rows)
    capable = policy != POLICY_LEDGER_ONLY
    runs_with_intervention = sum(1 for row in rows if row.intervened)
    runs_with_optimism = sum(1 for row in rows if row.optimism_alarmed)
    runs_with_response = sum(1 for row in rows if row.responded)

    false_brake: float | None = None
    false_brake_interval: tuple[float, float] | None = None
    missed: float | None = None
    missed_interval: tuple[float, float] | None = None
    if configuration == HEALTHY_CONFIGURATION and capable:
        false_brake = _rate(runs_with_intervention, runs)
        false_brake_interval = _interval(runs_with_intervention, runs)
    if configuration == CANARY_CONFIGURATION:
        missed_count = runs - (runs_with_intervention if capable else runs_with_optimism)
        missed = _rate(missed_count, runs)
        missed_interval = _interval(missed_count, runs)

    return PolicyCell(
        label=f"{configuration}/{policy}",
        configuration=configuration,
        policy=policy,
        alpha=alpha,
        runs=runs,
        tasks=tasks,
        decided=sum(row.decided for row in rows),
        surfaced=sum(row.surfaced for row in rows),
        discarded=sum(row.discarded for row in rows),
        wrong_certifications=wrong,
        wrong_certifications_post_shift=sum(
            row.wrong_certifications_post_shift for row in rows
        ),
        abstentions=abstentions,
        wrong_certification_rate_per_task=_rate(wrong, tasks),
        wrong_certification_interval_per_task=_interval(wrong, tasks),
        abstention_rate=_rate(abstentions, tasks),
        mean_spend_per_task=None if tasks == 0 else spend / tasks,
        explored_tasks=sum(row.explored_tasks for row in rows),
        forced_exploration_tasks=sum(row.forced_exploration_tasks for row in rows),
        intervention_tasks=sum(row.intervention_tasks for row in rows),
        intervention_episodes=sum(row.intervention_episodes for row in rows),
        runs_with_intervention=runs_with_intervention,
        runs_with_optimism_alarm=runs_with_optimism,
        runs_with_drift_alarm=sum(1 for row in rows if row.drift_alarmed),
        runs_with_response=runs_with_response,
        intervention_capable=capable,
        false_brake_rate=false_brake,
        false_brake_interval=false_brake_interval,
        missed_unsafe_run_rate=missed,
        missed_unsafe_interval=missed_interval,
        per_seed=rows,
    )


def _policy_cell_json(cell: PolicyCell) -> dict[str, object]:
    return {
        "label": cell.label,
        "configuration": cell.configuration,
        "policy": cell.policy,
        "alpha": _num(cell.alpha),
        "runs": cell.runs,
        "tasks": cell.tasks,
        "decided": cell.decided,
        "surfaced": cell.surfaced,
        "discarded": cell.discarded,
        "wrong_certifications": cell.wrong_certifications,
        "wrong_certifications_post_shift": cell.wrong_certifications_post_shift,
        "abstentions": cell.abstentions,
        "wrong_certification_rate_per_task": _optional(
            cell.wrong_certification_rate_per_task
        ),
        "wrong_certification_interval_per_task": _pair(
            cell.wrong_certification_interval_per_task
        ),
        "abstention_rate": _optional(cell.abstention_rate),
        "mean_spend_per_task": _optional(cell.mean_spend_per_task),
        "explored_tasks": cell.explored_tasks,
        "forced_exploration_tasks": cell.forced_exploration_tasks,
        "intervention_tasks": cell.intervention_tasks,
        "intervention_episodes": cell.intervention_episodes,
        "runs_with_intervention": cell.runs_with_intervention,
        "runs_with_optimism_alarm": cell.runs_with_optimism_alarm,
        "runs_with_drift_alarm": cell.runs_with_drift_alarm,
        "runs_with_response": cell.runs_with_response,
        "intervention_capable": cell.intervention_capable,
        "false_brake_rate": _optional(cell.false_brake_rate),
        "false_brake_interval": _pair(cell.false_brake_interval),
        "missed_unsafe_run_rate": _optional(cell.missed_unsafe_run_rate),
        "missed_unsafe_interval": _pair(cell.missed_unsafe_interval),
        "per_seed": [
            {
                "seed": row.seed,
                "tasks": row.tasks,
                "decided": row.decided,
                "surfaced": row.surfaced,
                "discarded": row.discarded,
                "wrong_certifications": row.wrong_certifications,
                "wrong_certifications_post_shift": row.wrong_certifications_post_shift,
                "abstentions": row.abstentions,
                "explored_tasks": row.explored_tasks,
                "forced_exploration_tasks": row.forced_exploration_tasks,
                "intervention_tasks": row.intervention_tasks,
                "intervention_episodes": row.intervention_episodes,
                "optimism_alarm_tasks": row.optimism_alarm_tasks,
                "drift_alarm_tasks": row.drift_alarm_tasks,
                "total_spend": _num(row.total_spend),
                "intervened": row.intervened,
                "optimism_alarmed": row.optimism_alarmed,
                "drift_alarmed": row.drift_alarmed,
                "responded": row.responded,
            }
            for row in cell.per_seed
        ],
    }


# ===========================================================================
# Task 8, experiment C: V-only speech with S/T as ranking — the two-ledger
# model. The owner's central architecture question: what changes if S and T
# stop buying certification wealth and instead only ORDER the verification
# queue, with a separate certification wealth purchased by V alone, while
# speech remains exactly certification_wealth >= 1/alpha?
#
# Nothing here is a patch. The factory arm composes the shipped channel
# functions in the shipped purchase order; the two-ledger arm exists only in
# this harness. Records are a plain typed shape so real labeled ledger rows
# can be fed through the same arms later.
# ===========================================================================

TWO_LEDGER_EXPERIMENT = "v_only_speech_two_ledger"

FACTORY_LEDGER_ARM = "factory_single_ledger"
TWO_LEDGER_ARM = "v_only_two_ledger"

VOI_ORDERING = "st_wealth_priority"
FCFS_ORDERING = "first_come_first_served"

OUTCOME_REPRODUCED = "reproduced"
OUTCOME_NOT_REPRODUCED = "not_reproduced"
OUTCOME_NO_PURCHASE = "no_purchase"
_OUTCOMES = (OUTCOME_REPRODUCED, OUTCOME_NOT_REPRODUCED, OUTCOME_NO_PURCHASE)

DEFAULT_TWO_LEDGER_ALPHAS: tuple[float, ...] = (0.05, 0.1, 0.25, 0.4)
DEFAULT_RECALL_TARGETS: tuple[float, ...] = (0.25, 0.5, 0.75, 0.9)

#: Third generator per seed, so the T and V draws cannot perturb the panel
#: and a rate sweep re-thresholds the same uniforms instead of redrawing.
_TWO_LEDGER_TAG = 20260901

TWO_LEDGER_HONESTY_NOTES: tuple[str, ...] = (
    "synthetic_records: candidates are synthetic panels plus assumed T and V "
    "behaviour, not real ledger rows. No model, network, or subprocess call "
    "was made; nothing here is a measurement of the product. The record shape "
    "(CandidateRecord) is deliberately plain so real labeled records can be "
    "fed through the identical arms later.",
    "assumed_channel_rates: the T signal rates and BOTH reproduction rates "
    "are ASSUMPTION parameters, stated and swept, never fitted. The only "
    "measured anchor is D-031's null-rate measurement (0 false confirmations "
    "in 296 constructed trials, Wilson interval [0, 0.0128]), which is why "
    "the false-reproduction sweep includes 0 and the 0.0128 ceiling; the "
    "true-reproduction rate has no measurement at all.",
    "speech_rule_unchanged: in BOTH arms speech is exactly "
    "certification_wealth >= 1/alpha through the shipped decide(). The arms "
    "differ only in what purchases certification wealth: every channel in "
    "the factory arm, V and only V in the two-ledger arm, where S/T are a "
    "verification PRIORITY (queue ordering) and buy nothing.",
    "not_a_patch: the two-ledger arm is NOT a proposed change and is not "
    "reachable from production code. Adopting it would change "
    "attest.review.gate.evaluate_finding's wealth composition, the CI "
    "verification loop's ordering, and the role of the S/T schedules — all "
    "owner decisions under ground rule 8, none justifiable on synthetic "
    "evidence below 500 global ledger labels (architecture red line 5).",
    "two_denominators: wrong-certification rates are reported per null "
    "candidate (the findings the gate judges — the population alpha bounds) "
    "and per null task (silent panels included). The per-task figure is "
    "always the smaller and is never 'the rate'.",
    "paired_arms: both arms are evaluated on the identical records, and the "
    "two-ledger certification set is a subset of the factory's, so the "
    "comparison is discordant pairs, exact McNemar, and a bootstrap interval "
    "on the paired difference — never overlapping independent intervals.",
    "budget_is_simulated: the verification cost per candidate and the budget "
    "cap are simulation parameters, not measured costs. The VOI-versus-FCFS "
    "saving prices the wealth-as-scheduler proposal under the stated "
    "assumptions only.",
    "recommendation_only: this harness reads the production constants and "
    "never writes them. Fewer than 500 global ledger labels exist, so every "
    "number here is a recommendation for the owner, never an authorisation.",
    "no_seed_selection: every preregistered seed is reported per cell and "
    "per budget row, including seeds where the ordering saves nothing.",
)


@dataclass(frozen=True)
class TwoLedgerAssumptions:
    """Assumed T and V behaviour for synthetic candidate records.

    **These are assumptions, not measurements.** The false-reproduction sweep
    is anchored to D-031 (0/296 trials, interval [0, 0.0128]) but the headline
    rate and everything about the true findings' behaviour is unmeasured.
    """

    true_reproduce_rate: float = 0.8
    false_reproduce_rate: float = 0.005
    false_reproduce_rate_sweep: tuple[float, ...] = (0.0, 0.005, 0.0128)
    verification_no_purchase_rate: float = 0.1
    tier0_signal_slots: int = 2
    tier0_true_signal_rate: float = 0.3
    tier0_false_signal_rate: float = 0.1

    def false_reproduce_rates(self) -> tuple[float, ...]:
        """Sweep points, always including the headline rate."""
        return tuple(sorted({*self.false_reproduce_rate_sweep, self.false_reproduce_rate}))

    def to_json_dict(self) -> dict[str, object]:
        return {
            "true_reproduce_rate": _num(self.true_reproduce_rate),
            "false_reproduce_rate": _num(self.false_reproduce_rate),
            "false_reproduce_rate_sweep": [
                _num(rate) for rate in self.false_reproduce_rates()
            ],
            "verification_no_purchase_rate": _num(self.verification_no_purchase_rate),
            "tier0_signal_slots": self.tier0_signal_slots,
            "tier0_true_signal_rate": _num(self.tier0_true_signal_rate),
            "tier0_false_signal_rate": _num(self.tier0_false_signal_rate),
            "measured": False,
            "note": "assumed T and V behaviour; never measured on real data",
        }


DEFAULT_TWO_LEDGER_ASSUMPTIONS = TwoLedgerAssumptions()


@dataclass(frozen=True)
class CandidateRecord:
    """One candidate finding, in the shape a real labeled ledger row can fill.

    ``verification_outcome`` is the outcome a verification WOULD record if it
    were purchased; whether it is purchased is the budget policy's decision,
    which is exactly the separation the two-ledger model proposes.
    """

    candidate_id: str
    seed: int
    theta: int
    votes: int
    tier0_signals: int
    verification_outcome: str

    def __post_init__(self) -> None:
        if not self.candidate_id:
            raise ValueError("candidate_id must be non-empty")
        if self.theta not in (0, 1):
            raise ValueError("theta must be 0 or 1")
        if self.votes < 1:
            raise ValueError("a candidate exists only if at least one sample voted")
        if self.tier0_signals < 0:
            raise ValueError("tier0_signals must not be negative")
        _check_outcome(self.verification_outcome)


class _SeedRecords(NamedTuple):
    seed: int
    null_tasks: int
    true_tasks: int
    records: tuple[CandidateRecord, ...]


@dataclass(frozen=True)
class TwoLedgerSeedRow:
    seed: int
    null_tasks: int
    true_tasks: int
    candidates: int
    null_candidates: int
    true_candidates: int
    certifications: int
    wrong_certifications: int
    true_certifications: int
    discards: int
    abstentions: int


@dataclass(frozen=True)
class TwoLedgerArmOutcome:
    """One arm's decisions over the shared records, both denominators named."""

    arm: str
    tasks: int
    null_tasks: int
    true_tasks: int
    candidates: int
    null_candidates: int
    true_candidates: int
    certifications: int
    wrong_certifications: int
    true_certifications: int
    discards: int
    abstentions: int
    wrong_certification_rate_per_null_candidate: float | None
    wrong_certification_interval_per_null_candidate: tuple[float, float] | None
    wrong_certification_rate_per_null_task: float | None
    wrong_certification_interval_per_null_task: tuple[float, float] | None
    alpha_excess_per_null_candidate: float | None
    exceeds_alpha_per_null_candidate: bool
    true_certification_rate_per_true_candidate: float | None
    abstention_rate: float | None
    per_seed: tuple[TwoLedgerSeedRow, ...]


@dataclass(frozen=True)
class ArmPairing:
    """Factory versus two-ledger wrong certifications as paired data.

    The arms share every record, and the two-ledger certification set is a
    subset of the factory's (V alone can never certify what the full product
    would not), so every discordant pair runs one way.
    """

    denominator: str
    pairs: int
    both_wrong: int
    factory_only: int
    two_ledger_only: int
    neither_wrong: int
    arms_are_nested: bool
    difference_per_null_candidate: float | None
    difference_interval_per_null_candidate: tuple[float, float] | None
    mcnemar_exact_p: float | None
    intervals_overlap: bool


@dataclass(frozen=True)
class TwoLedgerCell:
    label: str
    alpha: float
    false_reproduce_rate: float
    is_factory_alpha: bool
    factory: TwoLedgerArmOutcome
    two_ledger: TwoLedgerArmOutcome
    paired: ArmPairing


@dataclass(frozen=True)
class BudgetSeedRow:
    seed: int
    candidates: int
    certifiable_true: int
    required_true_certifications: int | None
    budget_voi: int | None
    budget_fcfs: int | None


@dataclass(frozen=True)
class BudgetRow:
    """Verification budget to reach one recall target, per ordering.

    ``budget_*`` counts verifications; ``cost_*`` multiplies by the simulated
    per-candidate verification cost. The recall denominator is the number of
    true candidates the two-ledger arm could certify with an unlimited budget
    at this alpha.
    """

    alpha: float
    recall_target: float
    candidates: int
    certifiable_true: int
    required_true_certifications: int | None
    budget_voi: int | None
    budget_fcfs: int | None
    budget_saving_fraction: float | None
    verification_cost_per_candidate: float
    cost_voi: float | None
    cost_fcfs: float | None
    per_seed: tuple[BudgetSeedRow, ...]


@dataclass(frozen=True)
class TwoLedgerReport:
    """The whole comparison, content-addressed for pinning."""

    experiment: str
    status: str
    offline: bool
    config: dict[str, object]
    constants: dict[str, object]
    derived: dict[str, object]
    honesty: tuple[str, ...]
    cells: tuple[TwoLedgerCell, ...]
    budget: tuple[BudgetRow, ...]
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
            "cells": [_two_ledger_cell_json(cell) for cell in self.cells],
            "budget": [_budget_row_json(row) for row in self.budget],
        }


def _check_outcome(outcome: str) -> None:
    if outcome not in _OUTCOMES:
        raise ValueError(f"unknown verification outcome {outcome!r}")


def _check_two_ledger_assumptions(assumptions: TwoLedgerAssumptions) -> None:
    _check_unit("true_reproduce_rate", assumptions.true_reproduce_rate, closed=True)
    _check_unit(
        "verification_no_purchase_rate",
        assumptions.verification_no_purchase_rate,
        closed=True,
    )
    if assumptions.tier0_signal_slots < 0:
        raise ValueError("tier0_signal_slots must not be negative")
    _check_unit("tier0_true_signal_rate", assumptions.tier0_true_signal_rate, closed=True)
    _check_unit("tier0_false_signal_rate", assumptions.tier0_false_signal_rate, closed=True)
    for rate in assumptions.false_reproduce_rates():
        _check_unit("false_reproduce_rate", rate, closed=True)
        if rate + assumptions.verification_no_purchase_rate > 1.0:
            raise ValueError("verification outcome probabilities must not exceed one")
    if (
        assumptions.true_reproduce_rate + assumptions.verification_no_purchase_rate
        > 1.0
    ):
        raise ValueError("verification outcome probabilities must not exceed one")


def st_priority(*, votes: int, tier0_signals: int) -> float:
    """The S*T wealth the factory would hold before V — as a QUEUE KEY only.

    In the two-ledger model this number buys nothing: it decides which
    candidate gets the next verification slot, and certification wealth is
    untouched until V reports.
    """
    if votes < 0:
        raise ValueError("votes must not be negative")
    if tier0_signals < 0:
        raise ValueError("tier0_signals must not be negative")
    return float(votes_lr(votes) * tier0_lr(tier0_signals))


def two_ledger_certification_wealth(outcome: str, *, verified: bool = True) -> float:
    """Certification wealth purchased by V and only V.

    Unverified candidates (and no-purchase outcomes, D-022's unpriced classes)
    hold wealth exactly 1: silence, not evidence.
    """
    _check_outcome(outcome)
    if not verified or outcome == OUTCOME_NO_PURCHASE:
        return 1.0
    return float(verification_lr(outcome == OUTCOME_REPRODUCED))


def factory_terminal_wealth(
    *, votes: int, signals: int, outcome: str, alpha: float, verified: bool = True
) -> float:
    """The factory arm: shipped channels in the shipped purchase order.

    S first, T only when a signal exists, V only when a verdict exists — and
    every later purchase skipped once the gate has decided, exactly as
    :func:`attest.review.gate.evaluate_finding` composes wealth (the same
    ``_wealth_trace`` rebuild the Ville section pins).
    """
    if votes < 0:
        raise ValueError("votes must not be negative")
    if signals < 0:
        raise ValueError("signals must not be negative")
    _check_outcome(outcome)
    _check_unit("alpha", alpha, closed=False)
    verification = None
    if verified and outcome != OUTCOME_NO_PURCHASE:
        verification = verification_lr(outcome == OUTCOME_REPRODUCED)
    wealth, _ = _wealth_trace(
        vote_lr=votes_lr(votes),
        tier0=tier0_lr(signals) if signals >= 1 else None,
        verification=verification,
        alpha=alpha,
    )
    return wealth


def arm_decisions(
    record: CandidateRecord, *, alpha: float, verified: bool = True
) -> tuple[int | None, int | None]:
    """(factory decision, two-ledger decision) for one record via decide()."""
    factory = decide(
        factory_terminal_wealth(
            votes=record.votes,
            signals=record.tier0_signals,
            outcome=record.verification_outcome,
            alpha=alpha,
            verified=verified,
        ),
        alpha,
    )
    ledger = decide(
        two_ledger_certification_wealth(record.verification_outcome, verified=verified),
        alpha,
    )
    return factory, ledger


def _seed_records(
    *,
    k: int,
    gamma: float,
    judge_accuracy: float,
    n_tasks: int,
    seed: int,
    assumptions: TwoLedgerAssumptions,
    false_reproduce_rate: float,
) -> _SeedRecords:
    """Draw one seed's mixed-truth panel and its assumed T/V outcomes.

    Draw order is part of the contract: the panel comes from
    :func:`simulate_panel` untouched; signals-then-no-purchase-then-reproduce
    uniforms come from a tagged second generator, so sweeping an assumed rate
    re-thresholds the same draws instead of redrawing them.
    """
    panel = simulate_panel(
        gamma=gamma,
        theta_prior=0.5,
        judge_accuracy=judge_accuracy,
        k=k,
        n_tasks=n_tasks,
        seed=seed,
    )
    rng = np.random.default_rng([seed, _TWO_LEDGER_TAG])
    signal_uniforms = rng.random((n_tasks, max(assumptions.tier0_signal_slots, 1)))
    no_purchase_uniforms = rng.random(n_tasks)
    reproduce_uniforms = rng.random(n_tasks)

    records: list[CandidateRecord] = []
    for index in range(n_tasks):
        votes = int(panel.votes[index])
        if votes < 1:
            continue
        theta = int(panel.theta[index])
        signal_rate = (
            assumptions.tier0_true_signal_rate
            if theta
            else assumptions.tier0_false_signal_rate
        )
        slots = signal_uniforms[index, : assumptions.tier0_signal_slots]
        signals = int((slots < signal_rate).sum())
        if no_purchase_uniforms[index] < assumptions.verification_no_purchase_rate:
            outcome = OUTCOME_NO_PURCHASE
        else:
            reproduce_rate = (
                assumptions.true_reproduce_rate if theta else false_reproduce_rate
            )
            outcome = (
                OUTCOME_REPRODUCED
                if reproduce_uniforms[index] < reproduce_rate
                else OUTCOME_NOT_REPRODUCED
            )
        records.append(
            CandidateRecord(
                candidate_id=f"seed{seed}/task{index}",
                seed=seed,
                theta=theta,
                votes=votes,
                tier0_signals=signals,
                verification_outcome=outcome,
            )
        )
    return _SeedRecords(
        seed=seed,
        null_tasks=int((panel.theta == 0).sum()),
        true_tasks=int((panel.theta == 1).sum()),
        records=tuple(records),
    )


def synthesize_candidate_records(
    *,
    k: int,
    gamma: float,
    judge_accuracy: float,
    n_tasks: int,
    seed: int,
    assumptions: TwoLedgerAssumptions = DEFAULT_TWO_LEDGER_ASSUMPTIONS,
    false_reproduce_rate: float,
) -> tuple[CandidateRecord, ...]:
    """Public record synthesizer; see :func:`_seed_records` for the contract."""
    _check_two_ledger_assumptions(assumptions)
    _check_unit("false_reproduce_rate", false_reproduce_rate, closed=True)
    if false_reproduce_rate + assumptions.verification_no_purchase_rate > 1.0:
        raise ValueError("verification outcome probabilities must not exceed one")
    return _seed_records(
        k=k,
        gamma=gamma,
        judge_accuracy=judge_accuracy,
        n_tasks=n_tasks,
        seed=seed,
        assumptions=assumptions,
        false_reproduce_rate=false_reproduce_rate,
    ).records


def run_two_ledger_experiment(
    *,
    alphas: Sequence[float] = DEFAULT_TWO_LEDGER_ALPHAS,
    k: int = 5,
    gamma: float = RHO,
    n_tasks: int = 2000,
    seeds: Sequence[int] = DEFAULT_SEEDS,
    judge_accuracy: float | None = None,
    assumptions: TwoLedgerAssumptions = DEFAULT_TWO_LEDGER_ASSUMPTIONS,
    recall_targets: Sequence[float] = DEFAULT_RECALL_TARGETS,
    verification_cost: float = 1.0,
    bootstrap_resamples: int = DEFAULT_BOOTSTRAP_RESAMPLES,
    bootstrap_seed: int = DEFAULT_BOOTSTRAP_SEED,
) -> TwoLedgerReport:
    """Factory arm versus the two-ledger arm over the preregistered grid.

    The arm comparison verifies every candidate the gate has not already
    decided (unlimited budget), isolating what the wealth composition changes.
    The budget section then prices the scheduler: within the two-ledger arm,
    verifications proceed in S/T-priority order versus arrival order under a
    per-candidate cost, and the row reports the budget each ordering needs to
    reach a fixed recall.
    """
    if not alphas:
        raise ValueError("at least one alpha is required")
    for alpha in alphas:
        _check_unit("alpha", alpha, closed=False)
    if k < 1:
        raise ValueError("k must be at least one")
    if n_tasks < 1:
        raise ValueError("n_tasks must be at least one")
    if not seeds:
        raise ValueError("at least one seed is required")
    if len(set(seeds)) != len(seeds):
        raise ValueError("seeds must be unique")
    _check_unit("gamma", gamma, closed=True)
    accuracy = calibrated_vote_accuracy() if judge_accuracy is None else judge_accuracy
    _check_unit("judge_accuracy", accuracy, closed=False)
    _check_two_ledger_assumptions(assumptions)
    if not recall_targets:
        raise ValueError("at least one recall target is required")
    for target in recall_targets:
        if not 0.0 < target <= 1.0:
            raise ValueError("recall targets must lie in (0, 1]")
    if verification_cost <= 0.0:
        raise ValueError("verification_cost must be positive")
    if bootstrap_resamples < 1:
        raise ValueError("bootstrap_resamples must be at least one")

    rates = assumptions.false_reproduce_rates()
    seed_data: dict[float, tuple[_SeedRecords, ...]] = {
        rate: tuple(
            _seed_records(
                k=k,
                gamma=gamma,
                judge_accuracy=accuracy,
                n_tasks=n_tasks,
                seed=seed,
                assumptions=assumptions,
                false_reproduce_rate=rate,
            )
            for seed in seeds
        )
        for rate in rates
    }

    cells = tuple(
        _two_ledger_cell(
            alpha=alpha,
            rate=rate,
            data=seed_data[rate],
            bootstrap_seed=bootstrap_seed,
            resamples=bootstrap_resamples,
        )
        for alpha in alphas
        for rate in rates
    )
    budget = tuple(
        _budget_row(
            alpha=alpha,
            target=target,
            data=seed_data[assumptions.false_reproduce_rate],
            cost=verification_cost,
        )
        for alpha in alphas
        for target in recall_targets
    )

    report = TwoLedgerReport(
        experiment=TWO_LEDGER_EXPERIMENT,
        status="insufficient_labels/recommendation_only",
        offline=True,
        config={
            "alphas": [_num(alpha) for alpha in alphas],
            "k": k,
            "gamma": _num(gamma),
            "gamma_is_a_clone_rate": True,
            "n_tasks": n_tasks,
            "seeds": list(seeds),
            "theta_prior": 0.5,
            "judge_accuracy": _num(accuracy),
            "judge_accuracy_is_lr1_calibrated": accuracy == calibrated_vote_accuracy(),
            "assumptions": assumptions.to_json_dict(),
            "recall_targets": [_num(target) for target in recall_targets],
            "verification_cost": _num(verification_cost),
            "bootstrap_resamples": bootstrap_resamples,
            "bootstrap_seed": bootstrap_seed,
            "orderings": [VOI_ORDERING, FCFS_ORDERING],
            "budget_rate_note": (
                "budget rows use the headline false-reproduction rate; recall "
                "counts only true candidates, so the rows are identical at "
                "every swept rate"
            ),
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
        derived={
            "speech_feasibility": {
                str(_num(alpha)): {
                    "factory_without_verification": bool(
                        max_reachable_wealth(False) >= 1.0 / alpha
                    ),
                    "factory_with_verification": bool(
                        max_reachable_wealth(True) >= 1.0 / alpha
                    ),
                    "two_ledger_v_only": bool(1.0 / alpha <= V_CAP),
                }
                for alpha in alphas
            },
            "gate_feasibility_factory": {
                str(_num(alpha)): gate_feasibility(alpha) for alpha in alphas
            },
            "factory_alphas": list(FACTORY_ALPHAS),
            "cells_where_arms_differ": [
                cell.label
                for cell in cells
                if cell.paired.factory_only + cell.paired.two_ledger_only > 0
            ],
            "cells_where_arms_are_not_nested": [
                cell.label for cell in cells if not cell.paired.arms_are_nested
            ],
            "interfaces_a_two_ledger_model_would_change": [
                "attest.review.gate.evaluate_finding: certification wealth would "
                "be purchased by V only instead of S*T*V",
                "attest.review.ci: the verification loop would order drawer "
                "candidates by S/T priority instead of arrival order",
                "attest.review.channels: the S and T schedules would become "
                "queue keys and stop buying wealth (constants untouched but "
                "their role redefined)",
            ],
            "owner_decision_required": True,
        },
        honesty=TWO_LEDGER_HONESTY_NOTES,
        cells=cells,
        budget=budget,
        digest="",
    )
    return replace(report, digest=_digest(report._payload()))


def _two_ledger_cell(
    *,
    alpha: float,
    rate: float,
    data: tuple[_SeedRecords, ...],
    bootstrap_seed: int,
    resamples: int,
) -> TwoLedgerCell:
    label = f"alpha={_num(alpha)}/false_reproduce_rate={_num(rate)}"
    factory_rows: list[TwoLedgerSeedRow] = []
    ledger_rows: list[TwoLedgerSeedRow] = []
    factory_wrong_flags: list[np.ndarray] = []
    ledger_wrong_flags: list[np.ndarray] = []
    for entry in data:
        factory_seed: dict[str, int] = {"cert": 0, "wrong": 0, "true": 0, "discard": 0}
        ledger_seed: dict[str, int] = {"cert": 0, "wrong": 0, "true": 0, "discard": 0}
        factory_null: list[bool] = []
        ledger_null: list[bool] = []
        for record in entry.records:
            factory, ledger = arm_decisions(record, alpha=alpha, verified=True)
            for decision, counts in ((factory, factory_seed), (ledger, ledger_seed)):
                if decision == 1:
                    counts["cert"] += 1
                    counts["wrong" if record.theta == 0 else "true"] += 1
                elif decision == 0:
                    counts["discard"] += 1
            if record.theta == 0:
                factory_null.append(factory == 1)
                ledger_null.append(ledger == 1)
        null_candidates = len(factory_null)
        true_candidates = len(entry.records) - null_candidates
        for counts, rows in ((factory_seed, factory_rows), (ledger_seed, ledger_rows)):
            rows.append(
                TwoLedgerSeedRow(
                    seed=entry.seed,
                    null_tasks=entry.null_tasks,
                    true_tasks=entry.true_tasks,
                    candidates=len(entry.records),
                    null_candidates=null_candidates,
                    true_candidates=true_candidates,
                    certifications=counts["cert"],
                    wrong_certifications=counts["wrong"],
                    true_certifications=counts["true"],
                    discards=counts["discard"],
                    abstentions=len(entry.records) - counts["cert"] - counts["discard"],
                )
            )
        factory_wrong_flags.append(np.asarray(factory_null, dtype=bool))
        ledger_wrong_flags.append(np.asarray(ledger_null, dtype=bool))

    factory_wrong = (
        np.concatenate(factory_wrong_flags) if factory_wrong_flags else np.array([], bool)
    )
    ledger_wrong = (
        np.concatenate(ledger_wrong_flags) if ledger_wrong_flags else np.array([], bool)
    )
    return TwoLedgerCell(
        label=label,
        alpha=alpha,
        false_reproduce_rate=rate,
        is_factory_alpha=alpha in FACTORY_ALPHAS,
        factory=_two_ledger_arm(FACTORY_LEDGER_ARM, tuple(factory_rows), alpha),
        two_ledger=_two_ledger_arm(TWO_LEDGER_ARM, tuple(ledger_rows), alpha),
        paired=_arm_pairing(
            factory_wrong,
            ledger_wrong,
            seed=_row_seed(bootstrap_seed, label, "two_ledger_paired"),
            resamples=resamples,
        ),
    )


def _two_ledger_arm(
    arm: str, rows: tuple[TwoLedgerSeedRow, ...], alpha: float
) -> TwoLedgerArmOutcome:
    null_tasks = sum(row.null_tasks for row in rows)
    true_tasks = sum(row.true_tasks for row in rows)
    candidates = sum(row.candidates for row in rows)
    null_candidates = sum(row.null_candidates for row in rows)
    true_candidates = sum(row.true_candidates for row in rows)
    certifications = sum(row.certifications for row in rows)
    wrong = sum(row.wrong_certifications for row in rows)
    true = sum(row.true_certifications for row in rows)
    discards = sum(row.discards for row in rows)
    abstentions = sum(row.abstentions for row in rows)
    per_candidate = _rate(wrong, null_candidates)
    candidate_interval = _interval(wrong, null_candidates)
    return TwoLedgerArmOutcome(
        arm=arm,
        tasks=null_tasks + true_tasks,
        null_tasks=null_tasks,
        true_tasks=true_tasks,
        candidates=candidates,
        null_candidates=null_candidates,
        true_candidates=true_candidates,
        certifications=certifications,
        wrong_certifications=wrong,
        true_certifications=true,
        discards=discards,
        abstentions=abstentions,
        wrong_certification_rate_per_null_candidate=per_candidate,
        wrong_certification_interval_per_null_candidate=candidate_interval,
        wrong_certification_rate_per_null_task=_rate(wrong, null_tasks),
        wrong_certification_interval_per_null_task=_interval(wrong, null_tasks),
        alpha_excess_per_null_candidate=(
            None if per_candidate is None else per_candidate / alpha
        ),
        exceeds_alpha_per_null_candidate=(
            candidate_interval is not None and candidate_interval[0] > alpha
        ),
        true_certification_rate_per_true_candidate=_rate(true, true_candidates),
        abstention_rate=_rate(abstentions, candidates),
        per_seed=rows,
    )


def _arm_pairing(
    factory_wrong: np.ndarray, ledger_wrong: np.ndarray, *, seed: int, resamples: int
) -> ArmPairing:
    pairs = int(factory_wrong.size)
    both = int((factory_wrong & ledger_wrong).sum())
    factory_only = int((factory_wrong & ~ledger_wrong).sum())
    ledger_only = int((ledger_wrong & ~factory_wrong).sum())
    difference: float | None = None
    interval: tuple[float, float] | None = None
    if pairs:
        deltas = factory_wrong.astype(float) - ledger_wrong.astype(float)
        difference = float(deltas.mean())
        interval = _bootstrap_interval(deltas, seed=seed, resamples=resamples)
    factory_interval = _interval(both + factory_only, pairs)
    ledger_interval = _interval(both + ledger_only, pairs)
    overlap = (
        factory_interval is not None
        and ledger_interval is not None
        and factory_interval[0] <= ledger_interval[1]
        and ledger_interval[0] <= factory_interval[1]
    )
    return ArmPairing(
        denominator="null_candidate_tasks",
        pairs=pairs,
        both_wrong=both,
        factory_only=factory_only,
        two_ledger_only=ledger_only,
        neither_wrong=pairs - both - factory_only - ledger_only,
        arms_are_nested=bool((ledger_wrong <= factory_wrong).all()),
        difference_per_null_candidate=difference,
        difference_interval_per_null_candidate=interval,
        mcnemar_exact_p=_mcnemar_exact_p(factory_only, ledger_only),
        intervals_overlap=overlap,
    )


def _certified_true_flags(
    records: Sequence[CandidateRecord], alpha: float
) -> tuple[np.ndarray, np.ndarray]:
    """(certifiable-true flag, priority) per record under the two-ledger arm."""
    certified = np.array(
        [
            record.theta == 1
            and decide(
                two_ledger_certification_wealth(record.verification_outcome), alpha
            )
            == 1
            for record in records
        ],
        dtype=bool,
    )
    priority = np.array(
        [
            st_priority(votes=record.votes, tier0_signals=record.tier0_signals)
            for record in records
        ],
        dtype=float,
    )
    return certified, priority


def _minimal_budget(
    order: Sequence[int], certified: np.ndarray, required: int
) -> int | None:
    """Verifications needed, following ``order``, to certify ``required`` trues."""
    reached = 0
    for spent, index in enumerate(order, start=1):
        reached += bool(certified[index])
        if reached >= required:
            return spent
    return None


def _budget_orders(priority: np.ndarray) -> tuple[list[int], list[int]]:
    """(VOI order, FCFS order) over record indices; arrival breaks VOI ties."""
    arrival = list(range(priority.size))
    voi = sorted(arrival, key=lambda index: (-priority[index], index))
    return voi, arrival


def _budget_row(
    *, alpha: float, target: float, data: tuple[_SeedRecords, ...], cost: float
) -> BudgetRow:
    pooled_records = [record for entry in data for record in entry.records]
    certified, priority = _certified_true_flags(pooled_records, alpha)
    certifiable = int(certified.sum())
    required: int | None = None
    budget_voi: int | None = None
    budget_fcfs: int | None = None
    if certifiable > 0:
        required = math.ceil(target * certifiable)
        voi_order, fcfs_order = _budget_orders(priority)
        budget_voi = _minimal_budget(voi_order, certified, required)
        budget_fcfs = _minimal_budget(fcfs_order, certified, required)

    per_seed: list[BudgetSeedRow] = []
    for entry in data:
        seed_certified, seed_priority = _certified_true_flags(entry.records, alpha)
        seed_total = int(seed_certified.sum())
        seed_required: int | None = None
        seed_voi: int | None = None
        seed_fcfs: int | None = None
        if seed_total > 0:
            seed_required = math.ceil(target * seed_total)
            voi_order, fcfs_order = _budget_orders(seed_priority)
            seed_voi = _minimal_budget(voi_order, seed_certified, seed_required)
            seed_fcfs = _minimal_budget(fcfs_order, seed_certified, seed_required)
        per_seed.append(
            BudgetSeedRow(
                seed=entry.seed,
                candidates=len(entry.records),
                certifiable_true=seed_total,
                required_true_certifications=seed_required,
                budget_voi=seed_voi,
                budget_fcfs=seed_fcfs,
            )
        )

    saving: float | None = None
    if budget_voi is not None and budget_fcfs is not None and budget_fcfs > 0:
        saving = 1.0 - budget_voi / budget_fcfs
    return BudgetRow(
        alpha=alpha,
        recall_target=target,
        candidates=len(pooled_records),
        certifiable_true=certifiable,
        required_true_certifications=required,
        budget_voi=budget_voi,
        budget_fcfs=budget_fcfs,
        budget_saving_fraction=saving,
        verification_cost_per_candidate=cost,
        cost_voi=None if budget_voi is None else budget_voi * cost,
        cost_fcfs=None if budget_fcfs is None else budget_fcfs * cost,
        per_seed=tuple(per_seed),
    )


def _two_ledger_arm_json(arm: TwoLedgerArmOutcome) -> dict[str, object]:
    return {
        "arm": arm.arm,
        "tasks": arm.tasks,
        "null_tasks": arm.null_tasks,
        "true_tasks": arm.true_tasks,
        "candidates": arm.candidates,
        "null_candidates": arm.null_candidates,
        "true_candidates": arm.true_candidates,
        "certifications": arm.certifications,
        "wrong_certifications": arm.wrong_certifications,
        "true_certifications": arm.true_certifications,
        "discards": arm.discards,
        "abstentions": arm.abstentions,
        "wrong_certification_rate_per_null_candidate": _optional(
            arm.wrong_certification_rate_per_null_candidate
        ),
        "wrong_certification_interval_per_null_candidate": _pair(
            arm.wrong_certification_interval_per_null_candidate
        ),
        "wrong_certification_rate_per_null_task": _optional(
            arm.wrong_certification_rate_per_null_task
        ),
        "wrong_certification_interval_per_null_task": _pair(
            arm.wrong_certification_interval_per_null_task
        ),
        "alpha_excess_per_null_candidate": _optional(arm.alpha_excess_per_null_candidate),
        "exceeds_alpha_per_null_candidate": arm.exceeds_alpha_per_null_candidate,
        "true_certification_rate_per_true_candidate": _optional(
            arm.true_certification_rate_per_true_candidate
        ),
        "abstention_rate": _optional(arm.abstention_rate),
        "per_seed": [
            {
                "seed": row.seed,
                "null_tasks": row.null_tasks,
                "true_tasks": row.true_tasks,
                "candidates": row.candidates,
                "null_candidates": row.null_candidates,
                "true_candidates": row.true_candidates,
                "certifications": row.certifications,
                "wrong_certifications": row.wrong_certifications,
                "true_certifications": row.true_certifications,
                "discards": row.discards,
                "abstentions": row.abstentions,
            }
            for row in arm.per_seed
        ],
    }


def _two_ledger_cell_json(cell: TwoLedgerCell) -> dict[str, object]:
    return {
        "label": cell.label,
        "alpha": _num(cell.alpha),
        "false_reproduce_rate": _num(cell.false_reproduce_rate),
        "is_factory_alpha": cell.is_factory_alpha,
        "factory": _two_ledger_arm_json(cell.factory),
        "two_ledger": _two_ledger_arm_json(cell.two_ledger),
        "paired": {
            "denominator": cell.paired.denominator,
            "pairs": cell.paired.pairs,
            "both_wrong": cell.paired.both_wrong,
            "factory_only": cell.paired.factory_only,
            "two_ledger_only": cell.paired.two_ledger_only,
            "neither_wrong": cell.paired.neither_wrong,
            "arms_are_nested": cell.paired.arms_are_nested,
            "difference_per_null_candidate": _optional(
                cell.paired.difference_per_null_candidate
            ),
            "difference_interval_per_null_candidate": _pair(
                cell.paired.difference_interval_per_null_candidate
            ),
            "mcnemar_exact_p": _optional(cell.paired.mcnemar_exact_p),
            "intervals_overlap": cell.paired.intervals_overlap,
        },
    }


def _budget_row_json(row: BudgetRow) -> dict[str, object]:
    return {
        "alpha": _num(row.alpha),
        "recall_target": _num(row.recall_target),
        "candidates": row.candidates,
        "certifiable_true": row.certifiable_true,
        "required_true_certifications": row.required_true_certifications,
        "budget_voi": row.budget_voi,
        "budget_fcfs": row.budget_fcfs,
        "budget_saving_fraction": _optional(row.budget_saving_fraction),
        "verification_cost_per_candidate": _num(row.verification_cost_per_candidate),
        "cost_voi": _optional(row.cost_voi),
        "cost_fcfs": _optional(row.cost_fcfs),
        "orderings": {"voi": VOI_ORDERING, "fcfs": FCFS_ORDERING},
        "per_seed": [
            {
                "seed": entry.seed,
                "candidates": entry.candidates,
                "certifiable_true": entry.certifiable_true,
                "required_true_certifications": entry.required_true_certifications,
                "budget_voi": entry.budget_voi,
                "budget_fcfs": entry.budget_fcfs,
            }
            for entry in row.per_seed
        ],
    }
