"""The same review, said to a machine (D-163).

`attest review` prints four levels, a silence line and an accounting line, and
every one of those is written for a person. A pipeline that wants to gate a
merge, chart a speech rate or bill a repository has to parse prose to get at
numbers the run already had, and a parser of prose is a bug waiting for a
rewording.

So the same run is also available as one JSON object. It is a **projection of
what the text report says, not a second report**: the levels are the same
lines, the silence reason distribution is the same histogram the accounting
line prints, and the spend and elapsed are the same numbers. Nothing here is
computed that the terminal does not already show.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, cast

from attest.certification.types import CertifiedFinding
from attest.review.candidates import CandidateStore
from attest.review.gate import GateOutcome
from attest.review.ledger import Ledger
from attest.review.output_contract import budget_unverified
from attest.review.report import _candidates as candidates_of
from attest.review.report import drawer_reason_class
from attest.review.status import RunStatus

REVIEW_JSON_SCHEMA_VERSION = "attest.review-json.v1"
STATS_JSON_SCHEMA_VERSION = "attest.stats-json.v1"


def _finding_ids(certified: Sequence[CertifiedFinding]) -> set[str]:
    return {finding.accepted_receipt.receipt.candidate_id for finding in certified}


def _spend_by_finding(entries: Sequence[Mapping[str, Any]], task_id: str) -> dict[str, float]:
    """What each candidate cost, from the rows the review already wrote."""
    spend: dict[str, float] = {}
    for row in entries:
        if row.get("kind") != "review" or (task_id and row.get("task_id") != task_id):
            continue
        finding_id = row.get("finding_id")
        value = row.get("spend")
        if type(finding_id) is not str or type(value) not in {int, float}:
            continue
        spend[finding_id] = spend.get(finding_id, 0.0) + float(cast(float, value))
    return spend


def review_json(
    *,
    repo: Path,
    task_id: str,
    alpha: float,
    outcome: GateOutcome,
    certified: Sequence[CertifiedFinding],
    spend_usd: float,
    budget_usd: float,
    elapsed_s: float,
    deferred_reason: str | None,
    status: RunStatus | None,
    reasons: Mapping[str, str] | None,
    lines: Mapping[str, Sequence[str]],
    notes: Sequence[str] = (),
) -> dict[str, Any]:
    """One review as a machine-readable object.

    ``lines`` is the rendered contract line of each level, keyed by level name,
    exactly as the terminal prints them -- so a consumer that wants the sentence
    gets the same sentence, and one that wants the numbers never reads it.
    """
    certified_ids = _finding_ids(certified)
    drawer = [
        result
        for result in candidates_of(outcome)
        if result.finding.finding_id not in certified_ids
    ]
    per_finding = _spend_by_finding(Ledger(repo).entries(), task_id)
    histogram = Counter(
        drawer_reason_class((reasons or {}).get(result.finding.finding_id, ""))
        for result in drawer
    )
    silent_candidates = [
        {
            "finding_id": result.finding.finding_id,
            "file": result.finding.file,
            "line": result.finding.line,
            "wealth": round(result.wealth, 6),
            "reason_class": drawer_reason_class((reasons or {}).get(result.finding.finding_id, "")),
            "reason": (reasons or {}).get(result.finding.finding_id, ""),
            "spend_usd": round(per_finding.get(result.finding.finding_id, 0.0), 6),
        }
        for result in sorted(drawer, key=lambda item: item.wealth, reverse=True)
    ]
    spoke = {level: list(values) for level, values in lines.items() if values}
    return {
        "schema_version": REVIEW_JSON_SCHEMA_VERSION,
        "task_id": task_id,
        "alpha": alpha,
        "spend_usd": round(spend_usd, 6),
        "budget_usd": round(budget_usd, 6),
        "elapsed_s": round(elapsed_s, 3),
        "deferred_reason": deferred_reason,
        "notes": list(notes),
        "units": {
            "read": status.units_read if status is not None else 0,
            "planned": (status.units_planned or status.units_read) if status is not None else 0,
        },
        "levels": {level: spoke.get(level, []) for level in ("red", "gate", "yellow", "green")},
        "silent": not spoke,
        "candidates": {
            "total": len(certified) + len(drawer) + len(outcome.discarded),
            "certified": len(certified),
            "drawer": len(drawer),
            "discarded": len(outcome.discarded),
        },
        "drawer_reasons": dict(sorted(histogram.items())),
        "unverified_by_budget": budget_unverified(reasons),
        "silent_candidates": silent_candidates,
    }


def _level_of(row: Mapping[str, Any]) -> str | None:
    """Which level a ledger row is evidence of having spoken."""
    kind = row.get("kind")
    if kind == "certification" and row.get("outcome") == "accepted":
        return "red"
    if kind == "structural_note":
        return "green"
    if kind in {"impact_note", "nullability_note"}:
        return "yellow"
    if kind == "gate_observation":
        return "gate"
    return None


def stats_json(repo: Path, *, entries: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Everything `attest stats` knows about one repository, as numbers.

    Speech rate is per **review**, not per finding: the question a reader has is
    "how often does this thing say anything", and two notes in one pull request
    is one occasion of speech.
    """
    ledger = Ledger(repo)
    rows = list(entries if entries is not None else ledger.entries())
    final_tasks = {str(row.get("task_id", "")) for row in rows if row.get("kind") == "ci_final"}
    run_tasks = [
        str(row.get("task_id", ""))
        for row in rows
        if row.get("kind") == "review_run" and str(row.get("task_id", "")) not in final_tasks
    ] + sorted(final_tasks)
    reviews = len(run_tasks)
    spoke: dict[str, set[str]] = {level: set() for level in ("red", "gate", "yellow", "green")}
    for row in rows:
        level = _level_of(row)
        if level is not None:
            spoke[level].add(str(row.get("task_id", "")))
    spend = sum(
        float(cast(float, row.get("spend_usd", 0.0)))
        for row in rows
        if row.get("kind") in {"review_run", "ci_final"}
        and type(row.get("spend_usd")) in {int, float}
    )
    drawer_reasons = Counter(
        drawer_reason_class(str(row.get("reason", "")))
        for row in rows
        if row.get("kind") == "verification" and row.get("outcome") != "reproduced"
    )
    images = [row for row in rows if row.get("kind") == "image_cache"]
    hits = sum(1 for row in images if row.get("cached") is True)
    latencies = sorted(
        float(cast(float, row["elapsed_s"]))
        for row in rows
        if row.get("kind") in {"review_run", "ci_final"} and type(row.get("elapsed_s")) is float
    )
    try:
        candidates = sum(len(CandidateStore(repo).load(task)) for task in run_tasks)
    except Exception:  # noqa: BLE001 - a summary never fails a repository
        candidates = 0
    return {
        "schema_version": STATS_JSON_SCHEMA_VERSION,
        "repository": str(repo),
        "reviews": reviews,
        "candidates": candidates,
        "speech_rate": {
            level: (round(len(tasks & set(run_tasks)) / reviews, 6) if reviews else None)
            for level, tasks in spoke.items()
        },
        "spoke_on": {level: len(tasks & set(run_tasks)) for level, tasks in spoke.items()},
        "spend_usd": round(spend, 6),
        "spend_per_review_usd": round(spend / reviews, 6) if reviews else None,
        "drawer_reasons": dict(sorted(drawer_reasons.items())),
        "images": {
            "lookups": len(images),
            "hits": hits,
            "hit_rate": round(hits / len(images), 4) if images else None,
        },
        "p50_elapsed_s": latencies[len(latencies) // 2] if latencies else None,
    }


def dumps(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, indent=1, sort_keys=False, ensure_ascii=False)
