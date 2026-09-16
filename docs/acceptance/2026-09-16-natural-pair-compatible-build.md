# Natural-pair compatibility builds — 2026-09-16

## Result

Under the owner's explicit compatibility authorization, four separate revision
builds completed: **2 succeeded and 2 failed**. Astropy's natural parent/head pair
now has independently built wheels. Neither scikit-learn revision built under
the frozen uniform recipe. Model/API spend is **$0**.

| Case | Parent | Introducing head | What is established |
|---|---|---|---|
| astropy-14309 | Built | Built | One complete pair of revision-specific wheels |
| scikit-learn-25931 | Build failed | Build failed | Package discovery still prevents building |

These are four builds of two source cases, not four defects. No project runtime,
human test, certification or paid review was executed. Qualified defect and control
counts remain zero. D-276's two default-build failures and sample shortfall remain
unchanged; successful assisted builds are not added to its results.

## Method and concrete failure

Baseline `4df5ef8`; executed driver `727c0842a4d163b006dc5cd4c31fa7541fc8e311`.
The existing compatible-build driver was extended with a study selector. It uses
Python 3.10 in a compiler-bearing, digest-pinned builder and creation-date upper
bounds for declared direct/build requirements and build tools. Requirement
specifiers remain binding. The shared cutoff is each original case's creation
date, not its introducing-commit date; this is not an exact historical environment
or full transitive lock. Parent/head constraint bytes match within each pair.

Astropy passes the build phase that previously failed on `setuptools.dep_util`.
Scikit-learn's parent and head both fail with setuptools' multiple-top-level-package
error. The bounded recipe therefore does not solve this older build backend's
compatibility. No per-case dependency retry, source edit or implicit fallback was
used. Failed builds remain in the four-attempt population.

Source builds receive exported trees and constraints, without host credentials,
SSH forwarding or host sockets. Dependencies can be fetched at build time; runtime
isolation has not been changed. Native artifacts were produced separately for
each successful revision and were not copied between parent and head.

## Review and validation

One independent review found a P2 manifest-admission omission: revision tuples
were checked, but cutoff, output path and order were not. Before execution, the
driver was changed to compare full ordered entries derived from digest-bound
qualification and freeze records. The exact input passes; altered cutoff, path
traversal, reversed order, changed revision and duplicate-row mutations all refuse.
[Review](../../benchmarks/studies/metadata-exposed-v1/compatibility/independent-review.md)
and [resolution](../../benchmarks/studies/metadata-exposed-v1/compatibility/review-resolution.md)
are retained. No build preceded the correction and no second review was run.

All four terminal identities, log hashes, successful exported artifact hashes,
single-wheel presence and isolated build metadata were verified. Ruff and
`git diff --check` pass. Product source/tests remain identical to gated `0b6d3b1`;
the existing full code gate was not rerun or described as a new gate here.
No push, publication, paid call, reservation, default-rule or budget-cap change.

- [Frozen protocol and four inputs](../../benchmarks/studies/metadata-exposed-v1/compatibility/compatible-runtime.md).
- [All build records](../../benchmarks/studies/metadata-exposed-v1/compatibility/build-evidence/result.json).
- [Manifest and artifact digests](../../benchmarks/studies/metadata-exposed-v1/compatibility/build-evidence/manifest.json).
- [Resolved isolated dependencies](../../benchmarks/studies/metadata-exposed-v1/compatibility/build-evidence/isolated-dependencies.json).

## Next authorized boundary

This bounded build task ends with the four-attempt measurement. The next useful
compatibility step is a separately frozen, source-mounted runtime check for the
successful Astropy revisions, using the existing reviewed generated-file transfer
and secretless container adapter. Preserve original tracked bytes; each revision
must use its own wheel. Keep both failed scikit-learn revisions as not runnable,
without another build recipe in this task.

A mounted runtime check still is not the unchanged-human-test parent PASS / head
FAIL witness. Such a witness, independent controls and the unchanged minimum
sample are required before a paid study. One compatible pair cannot meet a
three-defect minimum; the paid real-performance report remains unfinished.
