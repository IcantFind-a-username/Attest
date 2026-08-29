"""Sequential conditional betting: per-task e-values and the odds-threshold gate."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from attest.core.tables import Tables


def task_lr_canonical(
    tables: Tables, verdicts: Mapping[str, int], order: Sequence[str] | None = None
) -> float:
    """Canonical-order product of conditional plug-in LRs over the purchased set.

    Kept for legacy comparison; adaptive purchasing with canonical-order betting
    has a known missingness bias (RESULTS §6) and is not the default.
    """
    judges = tables.judges if order is None else list(order)
    lr = 1.0
    seen: dict[str, int] = {}
    for j in judges:
        if j in verdicts:
            lr *= tables.lr_factor(j, seen, verdicts[j])
            seen[j] = verdicts[j]
    return lr


def task_lr_purchase_order(
    tables: Tables, order: Sequence[str], verdicts: Mapping[str, int]
) -> float:
    """Purchase-order product: each bet conditions on exactly what was known."""
    lr = 1.0
    seen: dict[str, int] = {}
    for j in order:
        lr *= tables.lr_factor(j, seen, verdicts[j])
        seen[j] = verdicts[j]
    return lr


def decide(wealth: float, alpha: float) -> int | None:
    """Pure odds-threshold gate: 1 = certified true (surface), 0 = certified
    false (silent discard), None = defer (drawer). Nothing else decides."""
    if wealth >= 1.0 / alpha:
        return 1
    if wealth <= alpha:
        return 0
    return None
