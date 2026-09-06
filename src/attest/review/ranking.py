"""Which reproductions a review buys, and in what order (D-168).

Two measurements set this up. The 2026-09-07 budget re-run raised `budget_usd`
from $0.25 to $1.00 on the seventeen commits the budget had starved: six times
the money, three times the candidates (105 -> 331), **and not one verdict
moved**. 167 of those candidates were drawered `no-reproduction-bought` -- the
ranking never reached them. Raising the budget raises discovery, and discovery
re-starves the budget.

So the knob is not the budget; it is what the budget is spent *on*. Owner
decision 1 of 2026-09-07 sets three rules, and this module holds the two that
are about candidates (the third, discovery's share of the budget, is
`budget.PROPOSAL_SHARE`):

**Order.** Candidates are ranked by **cluster size**, descending -- how many
proposal findings merged into this one candidate -- and ties are broken by a
**static credibility** score computed without a model: whether the anchor sits
inside a definition in a source unit, and whether that definition is called
anywhere in the tree. `finding_id` breaks what remains, so the order is a total
order and no permutation of samples, findings or files can change it.

Cluster size is not evidence that a defect is real -- the mainline says so about
publication and it is no less true here. It is evidence that the *proposal
stage* converged, which is the only thing available before a reproduction is
bought. On the seventeen-commit population it separates 36 candidates from 190;
the credibility tiebreak is what ranks the other 190, where the old key (the
gate's wealth) was flat at 2.0 and the effective order was the finding id's
hash.

**Cap.** At most `verification_cap_per_unit` candidates per **change unit** (the
changed file, `certification.units`) may buy a reproduction. The rest are
recorded, in the ledger and in `--explain`, as `ranked below verification cap`.
A cap is not a claim that the ones below it are wrong; it is a statement that a
review which has already bought three reproductions in one file is better spent
in the next file.

Free: `ast` and file reads, no model, no execution, no network. Bounded by the
same file and byte caps the impact level uses, and every uncertainty scores
zero rather than guessing.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from attest.certification.units import change_unit
from attest.review.candidates import StoredCandidate
from attest.review.impact import CallGraph, build_call_graph, is_test_path, read_tree

VERIFICATION_RANKING_POLICY_VERSION = "attest.verification-ranking.cluster-size.v1"

# Owner decision 1 of 2026-09-07: three, and policy-configurable. Three is what
# a reviewer would read in one file before moving on, and on the 2026-09-07
# population it is above the per-file median (1) and below the maximum (24).
DEFAULT_VERIFICATION_CAP = 3

# the drawer reason, verbatim, for a candidate the cap held back
RANKED_BELOW_CAP = "ranked below verification cap"


@dataclass(frozen=True)
class Credibility:
    """Two facts about an anchor, both decidable from the head tree alone."""

    #: the anchor is a line inside a `def` or `class` of a non-test Python file
    anchor_in_source_unit: bool
    #: the definition the anchor sits in is called somewhere in this repository
    has_call_site: bool
    #: the name of that definition, for the record; "" when there is none
    symbol: str = ""

    @property
    def score(self) -> int:
        return int(self.anchor_in_source_unit) + int(self.has_call_site)

    def to_row(self) -> dict[str, object]:
        return {
            "anchor_in_source_unit": self.anchor_in_source_unit,
            "has_call_site": self.has_call_site,
            "symbol": self.symbol,
            "score": self.score,
        }


UNKNOWN = Credibility(anchor_in_source_unit=False, has_call_site=False)


class CredibilityIndex:
    """One tree read, one call graph, answers for every candidate of a review.

    Built lazily and held for the life of a review: reading a tree twice for
    the same head is waste, and reading it at two different moments would be a
    ranking that depends on when it was asked.
    """

    def __init__(self, sources: Mapping[str, str] | None = None, graph: CallGraph | None = None):
        self._sources = dict(sources or {})
        self._graph = graph if graph is not None else build_call_graph(self._sources)
        self._spans: dict[str, tuple[tuple[int, int, str], ...]] = {}

    @classmethod
    def for_tree(cls, root: Path) -> CredibilityIndex:
        try:
            sources = read_tree(root)
        except (OSError, ValueError):
            sources = {}
        return cls(sources)

    def _definition_spans(self, path: str) -> tuple[tuple[int, int, str], ...]:
        """(first line, last line, name) of every definition of one file."""
        held = self._spans.get(path)
        if held is not None:
            return held
        spans = [
            (definition.line, definition.end_line, definition.name)
            for definitions in self._graph.definitions.values()
            for definition in definitions
            if definition.path == path
        ]
        # innermost first: a nested `def` is what a line inside it is about
        spans.sort(key=lambda span: (span[1] - span[0], span[0], span[2]))
        self._spans[path] = tuple(spans)
        return self._spans[path]

    def of(self, file: str, line: int) -> Credibility:
        path = change_unit(file)
        if not path.endswith(".py") or is_test_path(path) or path not in self._sources:
            return UNKNOWN
        for first, last, name in self._definition_spans(path):
            if first <= line <= last:
                called = any(
                    site.path != path or not (first <= site.line <= last)
                    for site in self._graph.sites.get(name, ())
                )
                return Credibility(
                    anchor_in_source_unit=True, has_call_site=called, symbol=name
                )
        # a real source file, but the anchor is module-level: no symbol, so no
        # call site can be claimed either
        return UNKNOWN


def cluster_size(candidate: StoredCandidate) -> int:
    return len(candidate.finding.members)


def rank(
    candidates: Iterable[StoredCandidate], index: CredibilityIndex | None = None
) -> list[StoredCandidate]:
    """Candidates in purchase order: cluster size, credibility, finding id.

    Total, so the result does not depend on the input order; and computed from
    the head tree and the cluster alone, so it does not depend on the clock, on
    what else was found, or on anything a model wrote.
    """
    items = list(candidates)
    if index is None:
        return sorted(items, key=lambda item: (-cluster_size(item), item.finding.finding_id))
    return sorted(
        items,
        key=lambda item: (
            -cluster_size(item),
            -index.of(item.finding.file, item.finding.line).score,
            item.finding.finding_id,
        ),
    )


def within_cap(ranked: Sequence[StoredCandidate], cap: int) -> tuple[set[str], dict[str, str]]:
    """(finding ids that may buy a reproduction, reason for each that may not).

    ``ranked`` must already be in purchase order; the cap counts down each
    change unit independently, so a review spends across the files it touched
    rather than exhausting itself inside the first one.
    """
    seen: dict[str, int] = {}
    allowed: set[str] = set()
    refused: dict[str, str] = {}
    for item in ranked:
        unit = change_unit(item.finding.file)
        position = seen.get(unit, 0) + 1
        seen[unit] = position
        if position <= cap:
            allowed.add(item.finding.finding_id)
        else:
            refused[item.finding.finding_id] = (
                f"{RANKED_BELOW_CAP}: {position} of {unit}'s candidates by cluster size and "
                f"static credibility; this review buys at most {cap} reproduction(s) per "
                "change unit"
            )
    return allowed, refused
