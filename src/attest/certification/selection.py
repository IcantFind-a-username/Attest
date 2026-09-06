"""Publication policy over certified findings (C-05, mainline §5 A; D-125).

Owner-selected method (2026-09-02): e-value Bonferroni. A certified finding may
be published only when its e-value (the S/T/V wealth) is at least
``m_u / alpha``, where ``m_u`` is the number of eligible candidates in **its own
change unit** (D-125, owner decision 2 of 2026-09-04) -- until then the count was
the whole pull request's. Same-defect findings are clustered first and count
once, and a cluster is judged in the unit of its representative; at most
``hard_cap`` findings are author-visible anywhere (inline or summary); the
arithmetic mean of the eligible candidates' e-values reports the PR-level global
null. Suppressed certified findings stay private with a reason. Pure: no I/O, no
ranking inputs beyond the declared e-values, deterministic tie-breaks.

**What the guarantee is, corrected (D-174).** Bonferroni over ``m_u`` controls
the family-wise error rate at ``alpha`` **inside one change unit, and nowhere
else**. Across a pull request the units are separate families, so the union bound
over the ``U`` units that carried an eligible candidate is
``pr_error_bound = min(1, U * alpha)``.

D-125 said this bound was ``hard_cap * alpha``, reasoning that at most
``hard_cap`` claims are ever visible. That is wrong, and in the unsafe direction:
**the cap truncates the display, not the search.** A unit whose null was rejected
was searched and rejected whether or not the cap then hid the finding, and a
Monte-Carlo over this very function makes the gap concrete -- ten units at
``alpha = 0.1``, each with one candidate whose e-value is a valid e-value under
the null, publishes something in **65%** of pull requests
(``1 - 0.9**10``), against the ``hard_cap * alpha = 0.3`` D-125 claimed
(`tests/certification/test_pr_error_bound.py`).

Two things follow, and neither is a code change to the arithmetic. ``alpha``, the
likelihood ratio, ``K`` and the cap are untouched -- restoring a PR-level rate is
an owner decision under §16, not an agent's. What changes is that every selection
now **reports the bound it actually offers**: ``units_searched``,
``pr_error_bound``, and ``e_value_validity``.

**``e_value_validity`` is ``"assumed-calibrated"``, and that word is load-bearing.**
The wealth this module thresholds is a fixed product of likelihood ratios
(D-007), not a quantity anyone has proved is an e-value: S and T price only
positive evidence, so ``E[wealth] <= 1`` under the null is an assumption of the
factor table and not a theorem about it. Every bound above is conditional on it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from .clustering import publication_clusters
from .types import CertifiedFinding
from .units import CHANGE_UNIT_POLICY_VERSION, change_unit

# v3 (D-174) adds `units_searched`, `pr_error_bound` and `e_value_validity`.
PUBLICATION_POLICY_SCHEMA_VERSION = "attest.publication-policy.v3"
PUBLICATION_METHOD = "e-value Bonferroni"
DEFAULT_HARD_CAP = 3

REASON_BELOW_THRESHOLD = "below family threshold"
REASON_SAME_DEFECT = "same defect as a published finding"
REASON_BEYOND_CAP = "beyond the hard author-visible cap"

# D-174: the wealth is a fixed product of likelihood ratios (D-007), not a
# quantity shown to satisfy `E[wealth] <= 1` under the null. Every bound this
# module reports is conditional on that assumption, and says so.
E_VALUE_VALIDITY = "assumed-calibrated"


class CertifiedSelection(Protocol):
    def select(self, findings: tuple[CertifiedFinding, ...]) -> tuple[CertifiedFinding, ...]: ...


@dataclass(frozen=True)
class ScoredFinding:
    finding: CertifiedFinding
    e_value: float


@dataclass(frozen=True)
class FamilyPolicy:
    """``eligible_units`` maps a change unit to its eligible-candidate count.
    ``eligible_count`` stays the PR-wide total: it is what the global-null mean
    is reported over, and it is what the pre-D-125 threshold was computed from."""

    alpha: float
    eligible_count: int
    hard_cap: int = DEFAULT_HARD_CAP
    eligible_units: Mapping[str, int] = field(default_factory=dict)
    unit_policy_version: str = CHANGE_UNIT_POLICY_VERSION

    def threshold_for(self, unit: str) -> float:
        """The bar a finding in ``unit`` must clear. A unit the eligible map does
        not name has one candidate by construction -- the certified finding
        itself -- so it is counted as one, never as zero."""
        return max(1, self.eligible_units.get(unit, 1)) / self.alpha

    @property
    def pr_family_threshold(self) -> float:
        """The pre-D-125 PR-wide bar, kept for comparison and reporting."""
        return max(1, self.eligible_count) / self.alpha

    @property
    def units_searched(self) -> int:
        """``U``: the change units that carried an eligible candidate.

        A unit with no eligible candidate ran no test and cannot have rejected a
        null, so it is not in the union bound. When the eligible map is empty --
        a caller that did not supply it -- the pull request is one family."""
        return len(self.eligible_units) or 1

    @property
    def pr_error_bound(self) -> float:
        """``min(1, U * alpha)``: the union bound over the units searched.

        Conditional on the e-values being calibrated (:data:`E_VALUE_VALIDITY`).
        It is not ``hard_cap * alpha``: the cap hides findings after the search,
        and a hidden false claim is still a rejected null."""
        return min(1.0, self.units_searched * self.alpha)


@dataclass(frozen=True)
class Suppressed:
    finding: CertifiedFinding
    reason: str


@dataclass(frozen=True)
class Selection:
    published: tuple[CertifiedFinding, ...]
    suppressed: tuple[Suppressed, ...]
    clusters: tuple[tuple[str, ...], ...]  # candidate ids per publication cluster
    family_threshold: float  # the PR-wide bar, reported (D-125: no longer applied)
    mean_e_value: float | None  # arithmetic mean over the eligible candidates
    # D-125: the bar actually applied to each cluster, by the representative's unit
    unit_thresholds: Mapping[str, float] = field(default_factory=dict)
    # D-174: what the PR-level guarantee actually is, on every selection
    units_searched: int = 1
    pr_error_bound: float = 1.0
    e_value_validity: str = E_VALUE_VALIDITY


def _candidate_id(finding: CertifiedFinding) -> str:
    return finding.accepted_receipt.receipt.candidate_id


def finding_unit(finding: CertifiedFinding) -> str:
    """A certified finding's change unit: the unit of its first anchor. Anchors
    are frozen on the finding in a fixed order, so this cannot vary."""
    return change_unit(finding.anchors[0].path)


def select_for_publication(
    scored: Sequence[ScoredFinding],
    policy: FamilyPolicy,
    eligible_e_values: Sequence[float],
) -> Selection:
    """Cluster, threshold each cluster at its own unit's ``m_u/alpha``, cap;
    every suppression carries its reason."""
    if not 0 < policy.alpha < 1 or policy.hard_cap < 0:
        raise ValueError("family policy requires 0 < alpha < 1 and a non-negative cap")
    by_id = {_candidate_id(item.finding): item for item in scored}
    threshold = policy.pr_family_threshold
    clusters = publication_clusters([item.finding for item in scored])
    representatives: list[ScoredFinding] = []
    suppressed: list[Suppressed] = []
    applied: dict[str, float] = {}
    for cluster in clusters:
        members = sorted(
            (by_id[_candidate_id(finding)] for finding in cluster),
            key=lambda item: (-item.e_value, _candidate_id(item.finding)),
        )
        representative, others = members[0], members[1:]
        # D-125: the family is the representative's change unit, not the PR
        unit = finding_unit(representative.finding)
        unit_threshold = policy.threshold_for(unit)
        applied[unit] = unit_threshold
        if representative.e_value >= unit_threshold:
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
    mean = sum(eligible_e_values) / len(eligible_e_values) if eligible_e_values else None
    return Selection(
        published=tuple(item.finding for item in published),
        suppressed=tuple(suppressed),
        clusters=tuple(
            tuple(_candidate_id(finding) for finding in cluster) for cluster in clusters
        ),
        family_threshold=threshold,
        mean_e_value=mean,
        unit_thresholds=dict(sorted(applied.items())),
        units_searched=policy.units_searched,
        pr_error_bound=policy.pr_error_bound,
        e_value_validity=E_VALUE_VALIDITY,
    )
