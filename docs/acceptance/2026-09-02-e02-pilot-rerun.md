# E-02 pilot re-run — dev slice after D-078 steps a and b (mainline §2 step 7, second pass)

Date: 2026-09-02. Code: main at the commit recorded in the roadmap Progress entry. Evidence
level: **dev-slice pilot**, not `G-RECALL-002`; the held-out slice remains untouched.

## What changed since the first pass

- step a (`ee9a0fb`, D-079): the reproduction generator sees the head and merge-base
  definitions, imports and existing tests, and must assert merge-base behaviour;
- step b (`4db546c`, D-080): truncated proposal samples are salvaged, unusable ones get one
  precommitted repair, attempts are cached by digest;
- executor-side interpreter rule (`5520d61`, D-079): every pilot project resolved to
  CPython 3.9.19 on this host; pytest trees carry a version satisfying their `minversion`.

Same population, construction, controls, runner and K as the
[first pass](2026-09-02-e02-pilot.md).

## Table

| population | n | candidates | eligible | certified | published | spend |
|---|---|---|---|---|---|---|
| defects | 8 | 7 | 7 | 5 | 5 | $0.9387 |
| controls | 8 | 1 | 1 | 0 | 0 | $0.1682 |

Per case (latest task):

| case | candidates | verification outcomes | certified | published | spend |
|---|---|---|---|---|---|
| psf__requests-1766--docs-only | 0 | - | 0 | 0 | $0.0089 |
| psf__requests-1766--test-only | 0 | - | 0 | 0 | $0.0154 |
| psf__requests-1766 | 1 | {'reproduced': 1} | 1 | 1 | $0.0728 |
| psf__requests-2931--test-only | 0 | - | 0 | 0 | $0.0147 |
| psf__requests-2931 | 1 | {'deferred': 1} | 0 | 0 | $0.1734 |
| pylint-dev__pylint-4970--test-only | 0 | - | 0 | 0 | $0.0404 |
| pylint-dev__pylint-4970 | 2 | {'reproduced': 2} | 2 | 2 | $0.0826 |
| pylint-dev__pylint-6386--docs-only | 0 | - | 0 | 0 | $0.0083 |
| pylint-dev__pylint-6386 | 0 | - | 0 | 0 | $0.1381 |
| pytest-dev__pytest-10081--docs-only | 0 | - | 0 | 0 | $0.0086 |
| pytest-dev__pytest-10081 | 1 | {'deferred': 1} | 0 | 0 | $0.1222 |
| pytest-dev__pytest-5809--test-only | 1 | {'deferred': 1} | 0 | 0 | $0.0496 |
| pytest-dev__pytest-5809 | 1 | {'reproduced': 1} | 1 | 1 | $0.0571 |
| pytest-dev__pytest-6202--test-only | 0 | - | 0 | 0 | $0.0223 |
| pytest-dev__pytest-6202 | 1 | {'reproduced': 1} | 1 | 1 | $0.1581 |
| pytest-dev__pytest-7236 | 0 | - | 0 | 0 | $0.1344 |

## Reading (mainline §4 fork)

certified 5 ≥ 5 and control false publications 0 → per mainline §4 the mainline continues to step 8, C-05. The five certified findings sit on four of the eight regressions (pylint-4970 certified both of its same-defect candidates, the multiplicity C-05 exists to control); requests-1766, pytest-5809 and pytest-6202 certified once each. Silence 4/8: pylint-6386 and pytest-7236 produced no candidates (their samples were empty or exhausted the 2,400-token bound while reasoning), requests-2931's generated test still fails on base, pytest-10081's generator returned `{}` twice. Recovery over the 64 proposal samples: 17 intact, 34 empty, 4 truncated samples repaired by the single precommitted retry, 9 empty after the bound was consumed by reasoning, 0 unrecoverable; deterministic salvage never triggered because truncated samples carried no complete finding.

## Spend

Latest-task spend for the 16 cases: $1.1072 (defects $0.9387, controls $0.1682); no case was retried in this pass. Settled in `DEVSPEND.md` against the $2.50 reservation.

## Gate

Full gate on main after steps a and b (`98465a7`..`87f232d`): 1628 passed, production coverage 91.59%, Ruff, Mypy and `git diff --check` clean.
