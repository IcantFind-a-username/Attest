"""Deterministic one-to-one matching of surfaced findings to hidden truth.

Two properties of the corpus, both true of its construction and independent of
any run, decide how this module has to behave (D-062).

An anchor names the *statement* a proposer is talking about; a labelled truth
span names the *lines a patch touched*. A Python statement's header, condition
and guarded call routinely sit on different physical lines, so a zero-line
tolerance rejects anchors that name the right statement. ``DEFAULT_LINE_SLACK``
is therefore one statement's typical physical extent, and every scoring report
carries a sensitivity sweep so the value is auditable rather than asserted.

A fix hunk that is a pure insertion has no head-side line range, so the
reverted head carries a real defect at a position the corpus never labels.
Such hunks are counted and named — never inferred into a match.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath

from attest.benchmark.schema import (
    BenchmarkCase,
    Prediction,
    TruthDefect,
    is_scored_placement,
)

DEFAULT_LINE_SLACK = 3
LINE_SLACK_SWEEP = (0, 1, 2, 3, 4, 5, 10)


@dataclass(frozen=True)
class MatchResult:
    """The scoreable outcome for one surfaced prediction."""

    finding_id: str
    defect_id: str | None
    matched: bool
    unlabelled_hunks_present: bool = False


@dataclass(frozen=True)
class HunkLabelling:
    """How much of one case's fix the corpus can label on the head side."""

    case_id: str
    head_side_labelled_hunks: int
    fix_side_hunks: int

    @property
    def unlabelled_hunks(self) -> int:
        """Fix hunks with no head-side span, floored at zero.

        A pure insertion in the fix contributes a ``new``-side location and no
        ``old``-side one, so the head revision holds a defect the corpus cannot
        point at by line. The manifest records the two sides as a flat list
        without pairing them, so this is an indicator derived from those counts,
        not an exact hunk-by-hunk reconciliation.
        """
        return max(0, self.fix_side_hunks - self.head_side_labelled_hunks)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "head_side_labelled_hunks": self.head_side_labelled_hunks,
            "fix_side_hunks": self.fix_side_hunks,
            "unlabelled_hunks": self.unlabelled_hunks,
        }


def hunk_labelling(case: BenchmarkCase) -> HunkLabelling:
    """Count one case's head-side labels against its fix's hunks."""
    return HunkLabelling(
        case_id=case.case_id,
        head_side_labelled_hunks=sum(
            1 for location in case.changed_locations if location.side == "old"
        ),
        fix_side_hunks=sum(
            1 for location in case.changed_locations if location.side == "new"
        ),
    )


def line_slack_sweep(
    truth_defects: tuple[TruthDefect, ...],
    predictions: tuple[Prediction, ...],
    *,
    values: Sequence[int] = LINE_SLACK_SWEEP,
) -> dict[str, int]:
    """Match counts across a fixed tolerance ladder.

    A single tolerance is a claim; the ladder is the evidence that the count
    does not hinge on the exact value chosen.
    """
    return {
        str(value): sum(
            1
            for result in match_findings(
                truth_defects, predictions, line_slack=value
            )
            if result.matched
        )
        for value in values
    }


def match_findings(
    truth_defects: tuple[TruthDefect, ...],
    predictions: tuple[Prediction, ...],
    *,
    line_slack: int = 0,
    cases: Iterable[BenchmarkCase] = (),
) -> tuple[MatchResult, ...]:
    """Match only surfaced, differentially reproduced predictions to one truth each.

    ``cases`` is optional context used to flag an unmatched finding whose case
    holds fix hunks the corpus cannot label on the head side. The flag records
    a limit of the labelling; it never turns a miss into a match.
    """
    if line_slack < 0:
        raise ValueError("line_slack must not be negative")
    unlabelled = {
        case.case_id
        for case in cases
        if hunk_labelling(case).unlabelled_hunks > 0
    }
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
            unlabelled_hunks_present=(
                index not in matched and prediction.case_id in unlabelled
            ),
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
    return PurePosixPath(path.replace("\\", "/")).as_posix()


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
