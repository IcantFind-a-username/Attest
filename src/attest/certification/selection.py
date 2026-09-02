"""PR-level publication policy over certified findings (C-05, mainline §5 A).

Owner-selected method (2026-09-02): e-value Bonferroni. With ``m`` eligible
candidates in the pull request a certified finding may be published only when
its e-value (the S/T/V wealth) is at least ``m / alpha``; same-defect findings
are clustered first and count once; at most ``hard_cap`` findings are
author-visible anywhere (inline or summary); the arithmetic mean of the
eligible candidates' e-values reports the PR-level global null. Suppressed
certified findings stay private with a reason. Pure: no I/O, no ranking
inputs beyond the declared e-values, deterministic tie-breaks.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from .clustering import publication_clusters
from .types import CertifiedFinding

PUBLICATION_POLICY_SCHEMA_VERSION = "attest.publication-policy.v1"
PUBLICATION_METHOD = "e-value Bonferroni"
DEFAULT_HARD_CAP = 3

REASON_BELOW_THRESHOLD = "below family threshold"
REASON_SAME_DEFECT = "same defect as a published finding"
REASON_BEYOND_CAP = "beyond the hard author-visible cap"


class CertifiedSelection(Protocol):
    def select(
        self, findings: tuple[CertifiedFinding, ...]
    ) -> tuple[CertifiedFinding, ...]: ...


@dataclass(frozen=True)
class ScoredFinding:
    finding: CertifiedFinding
    e_value: float


@dataclass(frozen=True)
class FamilyPolicy:
    alpha: float
    eligible_count: int
    hard_cap: int = DEFAULT_HARD_CAP

    @property
    def family_threshold(self) -> float:
        return max(1, self.eligible_count) / self.alpha


@dataclass(frozen=True)
class Suppressed:
    finding: CertifiedFinding
    reason: str


@dataclass(frozen=True)
class Selection:
    published: tuple[CertifiedFinding, ...]
    suppressed: tuple[Suppressed, ...]
    clusters: tuple[tuple[str, ...], ...]  # candidate ids per publication cluster
    family_threshold: float
    mean_e_value: float | None  # arithmetic mean over the eligible candidates


def _candidate_id(finding: CertifiedFinding) -> str:
    return finding.accepted_receipt.receipt.candidate_id


def select_for_publication(
    scored: Sequence[ScoredFinding],
    policy: FamilyPolicy,
    eligible_e_values: Sequence[float],
) -> Selection:
    """Cluster, threshold at m/alpha, cap; every suppression carries its reason."""
    if not 0 < policy.alpha < 1 or policy.hard_cap < 0:
        raise ValueError("family policy requires 0 < alpha < 1 and a non-negative cap")
    by_id = {_candidate_id(item.finding): item for item in scored}
    threshold = policy.family_threshold
    clusters = publication_clusters([item.finding for item in scored])
    representatives: list[ScoredFinding] = []
    suppressed: list[Suppressed] = []
    for cluster in clusters:
        members = sorted(
            (by_id[_candidate_id(finding)] for finding in cluster),
            key=lambda item: (-item.e_value, _candidate_id(item.finding)),
        )
        representative, others = members[0], members[1:]
        if representative.e_value >= threshold:
            representatives.append(representative)
            suppressed.extend(Suppressed(item.finding, REASON_SAME_DEFECT) for item in others)
        else:
            suppressed.extend(Suppressed(item.finding, REASON_BELOW_THRESHOLD) for item in members)
    representatives.sort(key=lambda item: (-item.e_value, _candidate_id(item.finding)))
    published = representatives[: policy.hard_cap]
    suppressed.extend(
        Suppressed(item.finding, REASON_BEYOND_CAP) for item in representatives[policy.hard_cap :]
    )
    suppressed.sort(key=lambda item: _candidate_id(item.finding))
    mean = (
        sum(eligible_e_values) / len(eligible_e_values) if eligible_e_values else None
    )
    return Selection(
        published=tuple(item.finding for item in published),
        suppressed=tuple(suppressed),
        clusters=tuple(
            tuple(_candidate_id(finding) for finding in cluster) for cluster in clusters
        ),
        family_threshold=threshold,
        mean_e_value=mean,
    )
