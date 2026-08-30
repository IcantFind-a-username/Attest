"""Preregistered benchmark summary metrics and Wilson uncertainty intervals."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import NormalDist, pvariance

from attest.benchmark.matcher import match_findings
from attest.benchmark.schema import (
    BenchmarkCase,
    Prediction,
    RunRecord,
    TruthDefect,
    is_scored_placement,
)

#: Oracle reproduction statuses that record an oracle which could not decide.
#: The differential oracle is the only source of ground truth for a surfaced
#: finding, so a case resting on one of these has no truth to be scored
#: against: it is excluded, never charged to the product as a false positive
#: and a false negative at once.
INCONCLUSIVE_REPRO_STATUSES = frozenset({"deferred"})
ORACLE_INCONCLUSIVE_REASON = "oracle_inconclusive"


@dataclass(frozen=True)
class MetricExclusion:
    """One case removed from every accuracy denominator, with its reason."""

    case_id: str
    reason: str


@dataclass(frozen=True)
class BenchmarkReport:
    """Case, finding, timing, and uncertainty outcomes for preregistered runs."""

    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    decided_cases: int
    excluded_cases: tuple[MetricExclusion, ...]
    finding_true_positives: int
    finding_false_positives: int
    clean_false_positive_rate: float | None
    specificity: float | None
    all_positive_detection: float | None
    finding_precision: float | None
    conditional_recall: float | None
    abstention_rate: float | None
    duplicate_surfaces: int
    delivery_rate: float | None
    delivery_p50_s: float | None
    delivery_p95_s: float | None
    deadline_censored: int
    all_positive_detection_interval: tuple[float, float] | None
    finding_precision_interval: tuple[float, float] | None
    clean_false_positive_rate_interval: tuple[float, float] | None


def wilson_interval(successes: int, total: int) -> tuple[float, float] | None:
    """Return the two-sided 95% Wilson score interval, or null without observations."""
    if total < 0 or successes < 0 or successes > total:
        raise ValueError("successes must be between zero and total")
    if total == 0:
        return None
    z = NormalDist().inv_cdf(0.975)
    proportion = successes / total
    z_squared = z * z
    denominator = 1 + z_squared / total
    center = (proportion + z_squared / (2 * total)) / denominator
    half_width = z * math.sqrt(
        proportion * (1 - proportion) / total + z_squared / (4 * total * total)
    ) / denominator
    return max(0.0, center - half_width), min(1.0, center + half_width)


def silence_precision(true_negatives: int, false_negatives: int) -> float | None:
    """TN/(TN+FN): when the tool stayed silent, how often silence was right.

    Both inputs count decided cases only. An abstention is neither a true
    negative nor a false negative, so it never appears here.
    """
    if true_negatives < 0 or false_negatives < 0:
        raise ValueError("silence counts must not be negative")
    total = true_negatives + false_negatives
    return true_negatives / total if total else None


def mean_pairwise_jaccard(sets: Sequence[frozenset[str]]) -> float | None:
    """Mean Jaccard similarity over every unordered pair of surface sets.

    Two empty sets are identical surfaces (similarity 1.0): two runs that both
    stayed silent agreed perfectly. Fewer than two sets have no pair.
    """
    if len(sets) < 2:
        return None
    total = 0.0
    pairs = 0
    for index, left in enumerate(sets):
        for right in sets[index + 1 :]:
            union = left | right
            total += len(left & right) / len(union) if union else 1.0
            pairs += 1
    return total / pairs


@dataclass(frozen=True)
class Dispersion:
    """Mean, population variance, and range of one observed quantity."""

    mean: float
    variance: float
    value_range: float


def dispersion(values: Sequence[float]) -> Dispersion | None:
    """Descriptive dispersion of raw observations, or ``None`` without any.

    The variance is the population variance of exactly the runs observed;
    nothing here extrapolates beyond them.
    """
    if not values:
        return None
    return Dispersion(
        mean=sum(values) / len(values),
        variance=pvariance(values),
        value_range=max(values) - min(values),
    )


def aggregate(
    cases: tuple[BenchmarkCase, ...],
    truth_defects: tuple[TruthDefect, ...],
    runs: tuple[RunRecord, ...],
    *,
    line_slack: int = 0,
) -> BenchmarkReport:
    """Score only fixed repeat zero so correlated repeats never enlarge denominators.

    A case whose surfaced evidence carries an inconclusive oracle status is
    recorded in ``excluded_cases`` and left out of every accuracy numerator and
    denominator. Its delivery timing and silence are still measured: those are
    observations of the run, not claims about correctness.
    """
    _validate_inputs(cases, truth_defects, runs)
    primary_runs = tuple(run for run in runs if run.repeat == 0)
    truths_by_case: dict[str, tuple[TruthDefect, ...]] = {}
    for truth in truth_defects:
        truths_by_case[truth.case_id] = truths_by_case.get(truth.case_id, ()) + (truth,)

    true_positives = false_positives = false_negatives = true_negatives = 0
    finding_true_positives = finding_false_positives = duplicate_surfaces = 0
    abstentions = deadline_censored = timely_deliveries = 0
    delivered_times: list[float] = []
    surfaced_positive_cases = 0
    excluded: list[MetricExclusion] = []

    for run in primary_runs:
        truths = truths_by_case.get(run.case_id, ())
        case = next(case for case in cases if case.case_id == run.case_id)
        surfaced = tuple(
            prediction
            for prediction in run.predictions
            if is_scored_placement(prediction.placement)
        )
        if not surfaced:
            abstentions += 1
        duplicate_surfaces += _duplicate_count(surfaced)

        delivery_at_s = run.delivery_at_s
        if delivery_at_s is not None and delivery_at_s <= run.deadline_s:
            timely_deliveries += 1
            delivered_times.append(delivery_at_s)
        else:
            deadline_censored += 1

        if _oracle_inconclusive(surfaced):
            excluded.append(MetricExclusion(run.case_id, ORACLE_INCONCLUSIVE_REASON))
            continue

        matches = match_findings(truths, run.predictions, line_slack=line_slack)
        matched_count = sum(result.matched for result in matches)
        finding_true_positives += matched_count
        finding_false_positives += len(matches) - matched_count

        if case.role == "historical_bug_replay":
            if surfaced:
                surfaced_positive_cases += 1
            if matched_count:
                true_positives += 1
            else:
                false_negatives += 1
        elif surfaced:
            false_positives += 1
        else:
            true_negatives += 1

    clean_total = false_positives + true_negatives
    positive_total = true_positives + false_negatives
    finding_total = finding_true_positives + finding_false_positives
    return BenchmarkReport(
        true_positives=true_positives,
        false_positives=false_positives,
        false_negatives=false_negatives,
        true_negatives=true_negatives,
        decided_cases=clean_total + positive_total,
        excluded_cases=tuple(excluded),
        finding_true_positives=finding_true_positives,
        finding_false_positives=finding_false_positives,
        clean_false_positive_rate=_ratio(false_positives, clean_total),
        specificity=_ratio(true_negatives, clean_total),
        all_positive_detection=_ratio(true_positives, positive_total),
        finding_precision=_ratio(finding_true_positives, finding_total),
        conditional_recall=_ratio(true_positives, surfaced_positive_cases),
        abstention_rate=_ratio(abstentions, len(primary_runs)),
        duplicate_surfaces=duplicate_surfaces,
        delivery_rate=_ratio(timely_deliveries, len(primary_runs)),
        delivery_p50_s=_nearest_rank(delivered_times, 0.5),
        delivery_p95_s=_nearest_rank(delivered_times, 0.95),
        deadline_censored=deadline_censored,
        all_positive_detection_interval=wilson_interval(true_positives, positive_total),
        finding_precision_interval=wilson_interval(finding_true_positives, finding_total),
        clean_false_positive_rate_interval=wilson_interval(false_positives, clean_total),
    )


def _validate_inputs(
    cases: tuple[BenchmarkCase, ...],
    truth_defects: tuple[TruthDefect, ...],
    runs: tuple[RunRecord, ...],
) -> None:
    case_by_id = {case.case_id: case for case in cases}
    case_ids = set(case_by_id)
    if len(case_ids) != len(cases):
        raise ValueError("duplicate case_id")
    truth_case_ids = {truth.case_id for truth in truth_defects}
    if not truth_case_ids <= case_ids:
        raise ValueError("truth defect references an unknown case_id")
    for case in cases:
        if case.role == "historical_bug_replay" and case.case_id not in truth_case_ids:
            raise ValueError("positive historical_bug_replay case requires truth")
        if case.role == "developer_fix_control" and case.case_id in truth_case_ids:
            raise ValueError("developer_fix_control case must not contain truth")
    primary_case_ids: set[str] = set()
    for run in runs:
        if run.case_id not in case_ids:
            raise ValueError("run references an unknown case_id")
        if run.repeat < 0 or run.deadline_s < 0:
            raise ValueError("repeat and deadline_s must not be negative")
        if run.delivery_at_s is not None and run.delivery_at_s < 0:
            raise ValueError("delivery_at_s must not be negative")
        if any(prediction.case_id != run.case_id for prediction in run.predictions):
            raise ValueError("prediction case_id must match run case_id")
        if run.repeat == 0:
            if run.case_id in primary_case_ids:
                raise ValueError("duplicate preregistered run for case_id")
            primary_case_ids.add(run.case_id)
    missing = case_ids - primary_case_ids
    if missing:
        raise ValueError("missing repeat 0 record for case_id")


def _oracle_inconclusive(surfaced: tuple[Prediction, ...]) -> bool:
    """Whether the oracle failed to decide the evidence this case rests on."""
    return any(
        prediction.repro_status in INCONCLUSIVE_REPRO_STATUSES for prediction in surfaced
    )


def _duplicate_count(predictions: tuple[Prediction, ...]) -> int:
    anchors: set[tuple[str, str, int]] = set()
    duplicates = 0
    for prediction in predictions:
        anchor = (prediction.case_id, prediction.file.replace("\\", "/"), prediction.line)
        if anchor in anchors:
            duplicates += 1
        else:
            anchors.add(anchor)
    return duplicates


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _nearest_rank(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(percentile * len(ordered)) - 1]
