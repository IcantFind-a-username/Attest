# Paid check (b): dev-slice re-run after owner fixes 1-5 (fourth pass)

Date: 2026-09-03. Code: `c2814b8` (fixes 1-5 `cf1d60d`..`505023b`, the attempt-digest
binding `d03687c`, the tests-directory roots `8e94b42`, the fix-4 amendment `0c6d012`,
item 6 `ac3343c`), run from a detached checkout of that commit against the primary
checkout's corpus. Same population, construction, controls, interpreters and K as the
[C-05 pass](2026-09-02-e02-pilot-rerun-c05.md). Evidence level: **dev-slice pilot**; the
held-out slice remains untouched.

## Table

| population | n | candidates | eligible | certified | published | samples | no text returned | true abstentions | spend |
|---|---|---|---|---|---|---|---|---|---|
| defects | 8 | 19 | 19 | 6 | 5 | 36 | 0 | 5 | $0.7127 |
| controls | 8 | 1 | 1 | 0 | 0 | 32 | 0 | 28 | $0.1384 |

Certified: 6 candidates on 5/8 defects (C-05 pass: 4 on 4/8). Published: 5 candidates on
5/8 defects. Silence 3/8. Control false publications: 0/8. No sample without text (C-05
pass: 8 of 32 defect samples). `samples` counts one per review unit: pylint-6386 planned two
units, so it has 8.

Per case (latest task):

| case | candidates | eligible | certified | published | samples | no text | abstained | verification | spend |
|---|---|---|---|---|---|---|---|---|---|
| psf__requests-1766--docs-only | 0 | 0 | 0 | 0 | 4 | 0 | 4 | - | $0.0076 |
| psf__requests-1766--test-only | 0 | 0 | 0 | 0 | 4 | 0 | 4 | - | $0.0154 |
| psf__requests-1766 | 1 | 1 | 1 | 1 | 4 | 0 | 0 | {'reproduced': 1} | $0.0619 |
| psf__requests-2931--test-only | 0 | 0 | 0 | 0 | 4 | 0 | 4 | - | $0.0147 |
| psf__requests-2931 | 4 | 4 | 1 | 1 | 4 | 0 | 0 | {'reproduced': 1, 'not_reproduced': 2, 'deferred': 1} | $0.1336 |
| pylint-dev__pylint-4970--test-only | 0 | 0 | 0 | 0 | 4 | 0 | 4 | - | $0.0219 |
| pylint-dev__pylint-4970 | 2 | 2 | 2 | 1 | 4 | 0 | 0 | {'reproduced': 2} | $0.0560 |
| pylint-dev__pylint-6386--docs-only | 0 | 0 | 0 | 0 | 4 | 0 | 4 | - | $0.0083 |
| pylint-dev__pylint-6386 | 4 | 4 | 1 | 1 | 8 | 0 | 4 | {'reproduced': 1, 'deferred': 2, 'not_reproduced': 1} | $0.1686 |
| pytest-dev__pytest-10081--docs-only | 0 | 0 | 0 | 0 | 4 | 0 | 4 | - | $0.0085 |
| pytest-dev__pytest-10081 | 1 | 1 | 0 | 0 | 4 | 0 | 0 | {'deferred': 1} | $0.0593 |
| pytest-dev__pytest-5809--test-only | 1 | 1 | 0 | 0 | 4 | 0 | 0 | {'not_reproduced': 1} | $0.0415 |
| pytest-dev__pytest-5809 | 3 | 3 | 1 | 1 | 4 | 0 | 1 | {'deferred': 2, 'reproduced': 1} | $0.0639 |
| pytest-dev__pytest-6202--test-only | 0 | 0 | 0 | 0 | 4 | 0 | 4 | - | $0.0205 |
| pytest-dev__pytest-6202 | 1 | 1 | 0 | 0 | 4 | 0 | 0 | {'deferred': 1} | $0.0573 |
| pytest-dev__pytest-7236 | 3 | 3 | 0 | 0 | 4 | 0 | 0 | {'not_reproduced': 2, 'deferred': 1} | $0.1121 |

psf__requests-2931 -> ['unfaithful generated test: fails on base as well']
pylint-dev__pylint-6386 -> ['unfaithful generated test: fails on base as well']
pytest-dev__pytest-10081 -> ['collection deferred: pytest collection/import/syntax or infrastructure failure d']
pytest-dev__pytest-5809 -> ['head run 1/3 deferred: pytest collection/import/syntax or infrastructure failure']
pytest-dev__pytest-6202 -> ['unfaithful generated test: fails on base as well']
pytest-dev__pytest-7236 -> ['head run 1/3 deferred: reproduction attempted to create a child process']

## Reading

- Fix 1 removed the no-text class entirely (0/68 samples; 8/32 on the defect PRs before);
  every defect PR now yields candidates, and the candidate count rose from 7 to 19 because
  the samples that used to exhaust the bound now return findings.
- The five true abstentions on defects are one whole unit of pylint-6386 (4/4 samples on a
  unit that contains no defect) and one sample of pytest-5809; the 28 control abstentions
  are 7 of 8 controls abstaining 4/4 and the test-only control of pytest-5809 proposing one
  candidate that failed to reproduce. Both shares are explained by content, not by
  exhaustion, so the condition for continuing to the held-out slice holds.
- Certified 5/8 defects: requests-1766, requests-2931, pylint-4970 (two same-defect
  candidates, one published), pylint-6386, pytest-5809. New since the C-05 pass:
  pylint-6386 and pytest-5809 (both had no candidates then).
- Silent 3/8: pytest-10081 (collection failure of the generated test), pytest-6202
  (unfaithful), pytest-7236 (a generated test spawned a child process; two others passed on
  head). The remaining losses are generation quality on pytest's own repository.
- Family policy: pylint-4970's second certified candidate suppressed as the same defect;
  the published findings all clear their PR's m/α.

## Spend

$0.8511 (defects $0.7127, controls $0.1384) of the $1.20 reservation; settled in
`DEVSPEND.md`.
