"""Experiment-only ablation of the correlated-panel discount (D-007).

The single scientific claim this file exists to test: **K samples drawn from one
model are a correlated panel, not K independent witnesses.** Aggregating them as
independent evidence — the naive product ``LR1 ** votes`` — manufactures
confidence that is not in the data. The production schedule prices the
correlation instead: vote ``m`` contributes ``LR1 ** ((1 - RHO) ** (m - 1))``,
with the whole channel capped at ``S_CAP``.

This module is a measuring instrument, not a policy. It **reads** the factory
constants from :mod:`attest.review.channels` and compares an alternative
aggregator offline; it never redefines a constant, never imports a mutable copy,
and never writes back. Below 500 global ledger labels no recalibration is
permissible at all (architecture red line 5), so every number produced here is a
recommendation for the owner, never an authorisation.

Honesty boundaries, restated in every emitted report:

* the panels are **synthetic** Bernoulli draws with a clone-correlation
  parameter, not samples from any real model — nothing here was measured on a
  live system, and no network, subprocess, or API call is involved;
* the vote channel prices only *positive* votes (a candidate exists because some
  sample proposed it), so neither aggregator is a martingale-valid e-value; the
  cap, not a Ville bound, is what holds the discounted arm;
* every preregistered seed and every configuration is reported, including the
  ones where the discount loses power.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from typing import NamedTuple

import numpy as np

from attest.benchmark.metrics import wilson_interval
from attest.core.betting import decide
from attest.review.channels import LR1, RHO, S_CAP, VOTE_LR, votes_lr

NAIVE_ARM = "naive_independent"
DISCOUNTED_ARM = "correlation_discounted"

#: Alphas that the product actually ships or documents.
FACTORY_ALPHAS: tuple[float, ...] = (0.05, 0.1)

#: Preregistered sweep. Fixed before any result was looked at. ``RHO`` appears as
#: a sweep point on purpose: it is the one correlation level at which the
#: production discount's assumption is exactly true.
DEFAULT_GAMMAS: tuple[float, ...] = (0.0, 0.3, RHO, 0.9, 0.99)
DEFAULT_SEEDS: tuple[int, ...] = (11, 22, 33, 44, 55)

HONESTY_NOTES: tuple[str, ...] = (
    "synthetic_panels: votes are simulated Bernoulli draws with a clone "
    "correlation parameter, not samples from any real model. No model, network, "
    "or subprocess call was made; nothing here is a measurement of the product.",
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
    """Per-seed counts, published so no seed can be selected after the fact."""

    seed: int
    certifications: int
    wrong_certifications: int
    true_certifications: int
    abstentions: int


@dataclass(frozen=True)
class ArmOutcome:
    """Pooled outcome for one aggregator at one (gamma, alpha) cell."""

    aggregator: str
    tasks: int
    positive_tasks: int
    negative_tasks: int
    certifications: int
    wrong_certifications: int
    true_certifications: int
    discards: int
    abstentions: int
    wrong_certification_rate: float | None
    wrong_certification_interval: tuple[float, float] | None
    true_certification_rate: float | None
    certification_precision: float | None
    certification_precision_interval: tuple[float, float] | None
    abstention_rate: float | None
    per_seed: tuple[SeedCounts, ...]


@dataclass(frozen=True)
class AblationCell:
    """Both arms at one correlation level and one gate."""

    gamma: float
    alpha: float
    discounted_can_certify: bool
    naive: ArmOutcome
    discounted: ArmOutcome


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
) -> AblationReport:
    """Run both aggregators through the production gate over the whole grid.

    For every ``(gamma, alpha, seed)`` the naive and the discounted vote
    aggregator are each pushed through :func:`attest.core.betting.decide`. Counts
    are pooled across seeds; per-seed rows are retained so no favourable seed can
    be selected afterwards.
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
        for alpha in alphas:
            naive_map = _decision_map(naive_votes_lr, k, alpha)
            discounted_map = _decision_map(votes_lr, k, alpha)
            runs = [panels[(gamma, seed)] for seed in seeds]
            cells.append(
                AblationCell(
                    gamma=gamma,
                    alpha=alpha,
                    discounted_can_certify=any(code == 1 for code in discounted_map),
                    naive=_arm_outcome(NAIVE_ARM, naive_map, runs),
                    discounted=_arm_outcome(DISCOUNTED_ARM, discounted_map, runs),
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
        },
        constants={
            "lr1": LR1,
            "rho": RHO,
            "s_cap": S_CAP,
            "vote_lr": list(VOTE_LR),
        },
        derived={
            "discount_speech_window": [_num(low), _num(high)],
            "factory_alphas": list(FACTORY_ALPHAS),
            "factory_gate_reachable_on_votes_alone": {
                str(_num(alpha)): bool(1.0 / alpha <= S_CAP) for alpha in FACTORY_ALPHAS
            },
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
    aggregator: str, decision_map: Sequence[int | None], runs: Sequence[PanelResult]
) -> ArmOutcome:
    certify = np.array([code == 1 for code in decision_map])
    discard = np.array([code == 0 for code in decision_map])

    per_seed: list[SeedCounts] = []
    tasks = positives = negatives = 0
    certifications = wrong = true = discards = abstentions = 0
    for panel in runs:
        certified = certify[panel.votes]
        discarded = discard[panel.votes]
        seed_certified = int(certified.sum())
        seed_wrong = int((certified & (panel.theta == 0)).sum())
        seed_true = int((certified & (panel.theta == 1)).sum())
        seed_discards = int(discarded.sum())
        seed_abstentions = panel.n_tasks - seed_certified - seed_discards
        per_seed.append(
            SeedCounts(
                seed=panel.seed,
                certifications=seed_certified,
                wrong_certifications=seed_wrong,
                true_certifications=seed_true,
                abstentions=seed_abstentions,
            )
        )
        tasks += panel.n_tasks
        positives += int((panel.theta == 1).sum())
        negatives += int((panel.theta == 0).sum())
        certifications += seed_certified
        wrong += seed_wrong
        true += seed_true
        discards += seed_discards
        abstentions += seed_abstentions

    return ArmOutcome(
        aggregator=aggregator,
        tasks=tasks,
        positive_tasks=positives,
        negative_tasks=negatives,
        certifications=certifications,
        wrong_certifications=wrong,
        true_certifications=true,
        discards=discards,
        abstentions=abstentions,
        wrong_certification_rate=_rate(wrong, negatives),
        wrong_certification_interval=_interval(wrong, negatives),
        true_certification_rate=_rate(true, positives),
        certification_precision=_rate(true, certifications),
        certification_precision_interval=_interval(true, certifications),
        abstention_rate=_rate(abstentions, tasks),
        per_seed=tuple(per_seed),
    )


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
        "certifications": arm.certifications,
        "wrong_certifications": arm.wrong_certifications,
        "true_certifications": arm.true_certifications,
        "discards": arm.discards,
        "abstentions": arm.abstentions,
        "wrong_certification_rate": _optional(arm.wrong_certification_rate),
        "wrong_certification_interval": _pair(arm.wrong_certification_interval),
        "true_certification_rate": _optional(arm.true_certification_rate),
        "certification_precision": _optional(arm.certification_precision),
        "certification_precision_interval": _pair(arm.certification_precision_interval),
        "abstention_rate": _optional(arm.abstention_rate),
        "per_seed": [
            {
                "seed": row.seed,
                "certifications": row.certifications,
                "wrong_certifications": row.wrong_certifications,
                "true_certifications": row.true_certifications,
                "abstentions": row.abstentions,
            }
            for row in arm.per_seed
        ],
    }


def _cell_json(cell: AblationCell) -> dict[str, object]:
    return {
        "gamma": _num(cell.gamma),
        "alpha": _num(cell.alpha),
        "discounted_can_certify": cell.discounted_can_certify,
        "naive": _arm_json(cell.naive),
        "discounted": _arm_json(cell.discounted),
    }


def _digest(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
