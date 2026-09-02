"""Cross-sample dedup: order-invariant clustering of findings that name one defect.

Discovery clusters (schema ``attest.discovery-cluster.v1``) are connected
components of the pairwise similarity graph: two findings are similar when
their anchors are close (same file, within a few lines) and their claims are
lexically similar. Components, representatives, provenance and output order
are all functions of the candidate *multiset*, never of the order in which
model samples completed. Votes count distinct samples in a cluster; cluster
size is correlated ranking information and never independent evidence.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from attest.review.schema import ClusterMember, Finding

CLUSTER_SCHEMA_VERSION = "attest.discovery-cluster.v1"

LINE_SLACK = 3
# same defect, different wording: independent samples describe one bug very
# differently, so the lexical bar is graded by anchor agreement — an exact
# line match needs only weak overlap, a nearby line needs substantially more
# (calibrated on the first dogfood run, D-013)
JACCARD_EXACT_LINE = 0.15
JACCARD_NEAR_LINE = 0.35

_WORD_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
_STOP = {
    "the",
    "a",
    "an",
    "is",
    "are",
    "was",
    "be",
    "been",
    "to",
    "of",
    "in",
    "on",
    "and",
    "or",
    "if",
    "it",
    "this",
    "that",
    "with",
    "for",
    "as",
    "by",
    "can",
    "will",
    "may",
    "when",
    "not",
    "no",
}


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text)} - _STOP


def _jaccard(a: Finding, b: Finding) -> float:
    ta = _tokens(a.claim) | _tokens(a.failure_scenario)
    tb = _tokens(b.claim) | _tokens(b.failure_scenario)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _similar(a: Finding, b: Finding) -> bool:
    if a.file != b.file or abs(a.line - b.line) > LINE_SLACK:
        return False
    threshold = JACCARD_EXACT_LINE if a.line == b.line else JACCARD_NEAR_LINE
    return _jaccard(a, b) >= threshold


@dataclass(frozen=True, order=True)
class _Member:
    """One validated finding with its provenance, ordered canonically."""

    file: str
    line: int
    claim: str
    failure_scenario: str
    falsification_plan: str
    sample_id: int

    def finding(self) -> Finding:
        return Finding(
            claim=self.claim,
            file=self.file,
            line=self.line,
            failure_scenario=self.failure_scenario,
            falsification_plan=self.falsification_plan,
        )


def _components(members: list[_Member]) -> list[list[int]]:
    """Connected components under ``_similar``; members arrive canonically sorted."""
    parent = list(range(len(members)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    findings = [member.finding() for member in members]
    for i in range(len(members)):
        for j in range(i + 1, len(members)):
            if _similar(findings[i], findings[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    groups: dict[int, list[int]] = {}
    for i in range(len(members)):
        groups.setdefault(find(i), []).append(i)
    return [groups[root] for root in sorted(groups)]


def cluster_id_for(members: list[ClusterMember]) -> str:
    """Stable identity of a cluster: a digest of its sorted anchor/claim set.

    Sample ids are excluded so the identity survives any completion order.
    """
    key = "\n".join(
        f"{member.file}:{member.line}:{member.claim}"
        for member in sorted(members, key=lambda m: (m.file, m.line, m.claim))
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _representative(members: list[_Member]) -> _Member:
    """The medoid: highest total similarity to the rest, ties to canonical order."""
    findings = [member.finding() for member in members]
    scored = [
        (
            -sum(_jaccard(findings[i], findings[j]) for j in range(len(members)) if j != i),
            members[i],
        )
        for i in range(len(members))
    ]
    return min(scored)[1]


def _longest(values: list[str]) -> str:
    return min(values, key=lambda value: (-len(value), value))


def cluster_findings(per_sample: list[list[Finding]]) -> list[Finding]:
    """per_sample[i] = validated findings from sample i.

    Returns one merged candidate per cluster. The result — membership,
    representative, details, votes and order — is identical for every
    permutation of samples and of findings within a sample.
    """
    members = sorted(
        _Member(
            file=f.file,
            line=f.line,
            claim=f.claim,
            failure_scenario=f.failure_scenario,
            falsification_plan=f.falsification_plan,
            sample_id=sample_id,
        )
        for sample_id, findings in enumerate(per_sample)
        for f in findings
    )
    merged: list[Finding] = []
    for component in _components(members):
        group = [members[i] for i in component]
        representative = _representative(group)
        provenance = [
            ClusterMember(
                sample_id=member.sample_id,
                file=member.file,
                line=member.line,
                claim=member.claim,
            )
            for member in group
        ]
        sample_ids = sorted({member.sample_id for member in group})
        merged.append(
            Finding(
                claim=representative.claim,
                file=representative.file,
                line=representative.line,
                failure_scenario=_longest([member.failure_scenario for member in group]),
                falsification_plan=_longest([member.falsification_plan for member in group]),
                votes=len(sample_ids),
                sample_ids=sample_ids,
                cluster_id=cluster_id_for(provenance),
                members=provenance,
            )
        )
    return sorted(merged, key=lambda f: (f.file, f.line, f.claim))


def merge_findings(per_sample: list[list[Finding]]) -> list[Finding]:
    """Compatibility name for ``cluster_findings``."""
    return cluster_findings(per_sample)
