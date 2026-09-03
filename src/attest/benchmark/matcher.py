"""Deterministic one-to-one matching of surfaced findings to hidden truth."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from attest.benchmark.schema import Prediction, TruthDefect, is_scored_placement


@dataclass(frozen=True)
class MatchResult:
    """The scoreable outcome for one surfaced prediction."""

    finding_id: str
    defect_id: str | None
    matched: bool


def match_findings(
    truth_defects: tuple[TruthDefect, ...],
    predictions: tuple[Prediction, ...],
    *,
    line_slack: int = 0,
) -> tuple[MatchResult, ...]:
    """Match only surfaced, differentially reproduced predictions to one truth each."""
    if line_slack < 0:
        raise ValueError("line_slack must not be negative")
    surfaced = tuple(
        prediction for prediction in predictions if is_scored_placement(prediction.placement)
    )
    edges = tuple(
        tuple(
            (truth_index, _anchor_distance(prediction.line, truth))
            for truth_index, truth in enumerate(truth_defects)
            if _compatible(prediction, truth, line_slack)
        )
        if prediction.repro_status == "buggy_fail_fixed_pass"
        else ()
        for prediction in surfaced
    )
    matched = _best_matching(surfaced, truth_defects, edges)
    return tuple(
        MatchResult(
            finding_id=prediction.finding_id,
            defect_id=truth_defects[matched[index]].defect_id if index in matched else None,
            matched=index in matched,
        )
        for index, prediction in enumerate(surfaced)
    )


def _compatible(prediction: Prediction, truth: TruthDefect, line_slack: int) -> bool:
    return (
        prediction.case_id == truth.case_id
        and _normal_path(prediction.file) == _normal_path(truth.file)
        and _anchor_distance(prediction.line, truth) <= line_slack
    )


def _normal_path(path: str) -> str:
    return PurePosixPath(path).as_posix()


def _anchor_distance(line: int, truth: TruthDefect) -> int:
    if truth.start_line <= line <= truth.end_line:
        return 0
    return min(abs(line - truth.start_line), abs(line - truth.end_line))


def _best_matching(
    predictions: tuple[Prediction, ...],
    truths: tuple[TruthDefect, ...],
    edges: tuple[tuple[tuple[int, int], ...], ...],
) -> dict[int, int]:
    best: dict[int, int] = {}
    best_key: tuple[object, ...] | None = None

    def consider(candidate: dict[int, int]) -> None:
        nonlocal best, best_key
        edge_key = tuple(
            sorted(
                (
                    _anchor_distance(predictions[prediction_index].line, truths[truth_index]),
                    truths[truth_index].defect_id,
                    predictions[prediction_index].finding_id,
                )
                for prediction_index, truth_index in candidate.items()
            )
        )
        candidate_key: tuple[object, ...] = (
            -len(candidate),
            sum(distance for distance, _, _ in edge_key),
            edge_key,
        )
        if best_key is None or candidate_key < best_key:
            best = dict(candidate)
            best_key = candidate_key

    def search(index: int, assigned_truths: set[int], candidate: dict[int, int]) -> None:
        if index == len(predictions):
            consider(candidate)
            return
        search(index + 1, assigned_truths, candidate)
        for truth_index, _ in edges[index]:
            if truth_index in assigned_truths:
                continue
            assigned_truths.add(truth_index)
            candidate[index] = truth_index
            search(index + 1, assigned_truths, candidate)
            del candidate[index]
            assigned_truths.remove(truth_index)

    search(0, set(), {})
    return best
