"""The change unit a publication family is counted over (D-125).

C-05 counted the multiplicity family over the whole pull request: a certified
finding published only at ``e >= m/alpha`` for the ``m`` eligible candidates in
the PR. On real traffic ``m`` is not small -- median 4.5 and up to 14 across the
2026-09-03 corpus -- so a large change is close to unpublishable by
construction, and the product is silent exactly where a reviewer is most useful.

Owner decision 2 of 2026-09-04 takes backlog option (a): the family is one
**change unit**, and the unit is the **changed file** the candidate is anchored
in. Three properties are load-bearing and are what the RED checks:

* **order-invariant** -- a candidate's unit is a function of its own anchor
  path alone, so no permutation of candidates, samples, files or diff hunks can
  move a candidate between units or change any unit's size;
* **deterministic** -- the same anchor always gives the same unit, with no
  clock, no hash of a mutable set, and no dependence on what else was found;
* **total** -- every candidate has exactly one unit, so the units partition the
  eligible set and every eligible candidate is counted in exactly one family.

Deliberately *not* the planner's ``PlanUnit``. That unit exists to pack prompt
context under a character bound: its membership depends on ``MAX_UNIT_CHARS``
and on how much retrieved context each file happened to attract, so a statistical
family defined on it would move when a prompt budget moved. The file is the
coarsest thing a reviewer already reasons about that the diff alone determines.

This module is the seam. If the unit definition ever changes -- to a function, a
hunk, or a package -- it changes here, `CHANGE_UNIT_POLICY_VERSION` moves with
it, and every threshold downstream follows without another edit.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

CHANGE_UNIT_POLICY_VERSION = "attest.change-unit.file.v1"


def change_unit(path: str) -> str:
    """The unit identifier for a candidate anchored at ``path``.

    Normalised only for separator style, so a Windows-style anchor and a POSIX
    one for the same file are one unit rather than two.
    """
    return path.replace("\\", "/")


def unit_counts(paths: Iterable[str]) -> Mapping[str, int]:
    """Eligible candidates per unit. The result is a plain dict keyed by unit;
    iteration order of the input cannot affect any count."""
    counts: dict[str, int] = {}
    for path in paths:
        unit = change_unit(path)
        counts[unit] = counts.get(unit, 0) + 1
    return counts
