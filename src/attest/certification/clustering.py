"""Order-invariant publication clusters over certified findings (C-05).

Two certified findings describe one defect for publication purposes when their
receipts bind the same reproduction (identical test digest) or their anchors
sit in the same file within ``LINE_SLACK`` lines. Clusters are connected
components of that relation, computed over a canonically sorted input, so
membership and representative never depend on arrival order. Cluster size is
correlated evidence about one defect and is never counted as more.
"""

from __future__ import annotations

from collections.abc import Sequence

from .types import CertifiedFinding

PUBLICATION_CLUSTER_SCHEMA_VERSION = "attest.publication-cluster.v1"
LINE_SLACK = 3


def _candidate_id(finding: CertifiedFinding) -> str:
    return finding.accepted_receipt.receipt.candidate_id


def _same_defect(a: CertifiedFinding, b: CertifiedFinding) -> bool:
    if a.accepted_receipt.receipt.test_digest == b.accepted_receipt.receipt.test_digest:
        return True
    return any(
        x.path == y.path and abs(x.line - y.line) <= LINE_SLACK
        for x in a.anchors
        for y in b.anchors
    )


def publication_clusters(
    findings: Sequence[CertifiedFinding],
) -> tuple[tuple[CertifiedFinding, ...], ...]:
    """Connected components under ``_same_defect``; deterministic in and out."""
    ordered = sorted(findings, key=_candidate_id)
    parent = list(range(len(ordered)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(ordered)):
        for j in range(i + 1, len(ordered)):
            if _same_defect(ordered[i], ordered[j]):
                ri, rj = find(i), find(j)
                if ri != rj:
                    parent[max(ri, rj)] = min(ri, rj)
    groups: dict[int, list[CertifiedFinding]] = {}
    for i, finding in enumerate(ordered):
        groups.setdefault(find(i), []).append(finding)
    return tuple(tuple(groups[root]) for root in sorted(groups))
