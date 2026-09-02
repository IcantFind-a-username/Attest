# Owner instruction 4: R-01 context versus a cached package block (dev slice, comparison only)

Date: 2026-09-03. Code: `2931753` (instruction 3's caching `c17c46e` plus the
`package-cache` strategy), run from a detached checkout of that commit against the primary
checkout's corpus. Population: the 8 dev-slice regression PRs of the E-02 pilot, K=4, one
run per arm, default model `claude-sonnet-5`, thinking disabled (fix 1). Evidence level:
**dev-slice comparison**; the default strategy is unchanged and switching is the owner's
decision.

Arms:

- **r01** — the existing planner context (definitions, callers, old side, test names per
  unit), now with instruction 3's prompt caching and first-token-staggered fan-out;
- **package-cache** — the anchored module's whole package and its project's `tests`
  directory (≤ 120,000 characters) as one `cache_control` system block ahead of the role
  instruction, reused by every proposal sample, the reproduction generation and its repair.

Cache-read share counts proposal prompt tokens only (uncached + cache writes + cache reads
from the review's sample observations); generation calls are priced in the spend but their
usage is not in the ledger row.

### r01 (existing planner context): 8 PRs

| case | candidates | certified | published | no text | prompt tokens | cache read | read share | spend |
|---|---|---|---|---|---|---|---|---|
| psf__requests-1766 | 1 | 1 | 1 | 0 | 15612 | 15604 | 100% | $0.0371 |
| psf__requests-2931 | 3 | 1 | 1 | 0 | 17136 | 12846 | 75% | $0.1081 |
| pylint-dev__pylint-4970 | 1 | 1 | 1 | 0 | 5764 | 4317 | 75% | $0.0381 |
| pylint-dev__pylint-6386 | 3 | 1 | 1 | 0 | 33156 | 24855 | 75% | $0.1193 |
| pytest-dev__pytest-10081 | 1 | 0 | 0 | 0 | 11972 | 8973 | 75% | $0.0484 |
| pytest-dev__pytest-5809 | 1 | 0 | 0 | 0 | 7912 | 5928 | 75% | $0.0348 |
| pytest-dev__pytest-6202 | 1 | 0 | 0 | 0 | 9556 | 7161 | 75% | $0.0500 |
| pytest-dev__pytest-7236 | 1 | 0 | 0 | 0 | 19208 | 14400 | 75% | $0.0504 |

totals: certified 4, published 4, no text 0, spend $0.4862 ($0.0608 per PR), proposal prompt tokens 120316, cache read share 78%

### package-cache (variant): 8 PRs

| case | candidates | certified | published | no text | prompt tokens | cache read | read share | spend |
|---|---|---|---|---|---|---|---|---|
| psf__requests-1766 | 1 | 0 | 0 | 0 | 220112 | 165078 | 75% | $0.1821 |
| psf__requests-2931 | 2 | 0 | 0 | 0 | 141756 | 106311 | 75% | $0.2258 |
| pylint-dev__pylint-4970 | 2 | 1 | 1 | 0 | 147952 | 110958 | 75% | $0.2480 |
| pylint-dev__pylint-6386 | 4 | 0 | 0 | 0 | 166696 | 125016 | 75% | $0.2763 |
| pytest-dev__pytest-10081 | 1 | 0 | 0 | 0 | 139500 | 104619 | 75% | $0.2286 |
| pytest-dev__pytest-5809 | 0 | 0 | 0 | 0 | 163368 | 122520 | 75% | $0.1270 |
| pytest-dev__pytest-6202 | 1 | 1 | 1 | 0 | 147944 | 110952 | 75% | $0.2431 |
| pytest-dev__pytest-7236 | 2 | 0 | 0 | 0 | 141840 | 106374 | 75% | $0.2228 |

totals: certified 2, published 2, no text 0, spend $1.7537 ($0.2192 per PR), proposal prompt tokens 1269168, cache read share 75%

## Reading

- Certified: r01 4 (requests-1766, requests-2931, pylint-4970, pylint-6386) against
  package-cache 2 (pylint-4970, pytest-6202). The variant found pytest-6202, which r01
  missed in this run and in paid check (b), and lost three that r01 certifies.
- No sample without text in either arm (fix 1 holds under both prompt shapes).
- Cost per PR: r01 $0.0608, package-cache $0.2192 — 3.6× — because the shared block is
  130-220k tokens per PR: written once at 1.25× and read at 0.1× by the other samples and by
  generation, which is exactly the 75% read share on every PR (one write, three reads across
  four samples), but the block itself is 8-20× larger than r01's context.
- r01's read share is also 75% per PR (100% on requests-1766 only because its entry was still
  warm from the instruction-3 RED run minutes earlier).
- Recommendation (owner's call): keep `r01` as the default. The cached block does not buy
  recall at this size and multiplies input cost; if a larger context is ever wanted, a
  bounded, relevance-ordered block (the anchored module plus the test module that names it)
  is the shape to try, not the whole package.

## Spend

r01 $0.4862 + package-cache $1.7537 = $2.2399 of the $2.50 reservation; settled in
`DEVSPEND.md`.
