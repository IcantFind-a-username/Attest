# M-01 Task 5 dual-Python recovery acceptance — 2026-08-31

Status: **PASS M-01 — `G-MEASURE-001` and `G-CODE-001`; Phase 0 complete.**

This is a superseding recovery observation. It changes only the current acceptance status;
the earlier [Task 4 / failed-environment report](2026-08-31-m01-mixed-outcome.md) and its
two `ENOSPC` attempts remain immutable history and are not reclassified as passes.

## Binding and evidence

- Final implementation: `5efe3d1c046fef04d197542cc8abe3f413a92d56`;
  tree `a2909b5ef345d56ba0f95f8283a847c1309956d1`.
- Latest fetched `origin/main`: `1f6f73eb72f5ed45b129c4d7ff937cc23b409e5c`;
  verified ancestor of the implementation.
- `ff0e638` is documentation/evidence-only relative to `5efe3d1` over `src`, `tests`,
  `scripts`, project/lock files, and `.github`.
- Recovery bundle:
  [`evidence/2026-08-31-m01-task5-recovery-5efe3d1`](evidence/2026-08-31-m01-task5-recovery-5efe3d1).
- Root manifest SHA-256:
  `d98c510ba5ba8860a27bed57e3d08d86a90b2c4cb758ec1b252ae1ae2956e89b`.

## `G-MEASURE-001`

Task 4's fixed-SHA before/after measurement remains the semantic acceptance observation:
the baseline failed exactly with `legacy_mixed_outcome_denominator`; the current reducer
passed in 20/20 isolated processes, with `semantic_n=1`, `operational_repeats=20`, five
candidates, four published findings, one unresolved candidate, and one partially deferred
task. All 20 isolation digests were distinct and the semantic digest was identical; the
aggregate receipt SHA-256 is
`77899f8a69ce78c0d2d2b75c67554e48ff27595aa15f39bcc597a996391ccd9f`.

The implementation's focused matrix covers 0/1/many findings, task/candidate DEFER,
overflow, and mixed outcomes through CI, API, live, baseline, report, serialized artifacts,
and ledger parity. The final independent review's reproduced non-`surface` delivery P1 is
closed by `5efe3d1`; the same reviewer confirmed normal inline/overflow paths and reported
P0=0/P1=0. An already visible finding can no longer be removed from scoring by task DEFER.

## `G-CODE-001` recovery matrix

Each fresh detached exact-SHA environment ran serially, installed the locked toolchain from
the same offline wheelhouse under an `env -i` allowlist, and invoked full pytest exactly
once. Test counts are observations, not Gate constants.

| Check | Python 3.11.5 | Python 3.12.8 |
|---|---:|---:|
| full pytest | 1543/1543, RC 0 | 1543/1543, RC 0 |
| total coverage | 12373/13728 = 90.129662% | 12373/13728 = 90.129662% |
| `attest.core` coverage | 428/429 = 99.766900% | 428/429 = 99.766900% |
| Ruff 0.16.5 | PASS | PASS |
| Mypy 2.3.1 | PASS, 49 files | PASS, 49 files |
| `pip check` | PASS | PASS |
| exact SHA / detached / clean / diff | PASS | PASS |
| frozen-v1 receipt/results/protocol | PASS | PASS |

The Python 3.11 and 3.12 child manifests have respectively 150 and 58 entries and verify
offline. Their SHA-256 values are
`902d895b312d9b1fa8ce930e9a7212e025432049fe2fd2ee73fae37316003f02` and
`02d94476ad00633c8d8e350048bb76a296b3ad7a7a8fdc859fd66f03a66f467a`.
The Python 3.12 manifest excludes precisely inventoried duplicate post-Gate logs written by
a stale delegated task; it was rebuilt after that task stopped, and no Gate was rerun.

Frozen historical v1 SHA-256 values remained exact in both environments:

- receipt: `e8cabb89471bb369a93ce82399a342eaddbf7ed8994d5420aef66256d013ce40`;
- validation results: `e90b2acfb9753db196cd7d2cf999dc2fa24bbd91bb84d908b476682c1b441288`;
- protocol: `2a6019533a1c01abbf905e57b0b15017b806aeeee6028e496b0149a4a1f2246c`.

## Conclusion and limits

M-01 now passes its authoritative mixed-outcome accounting contract and portable code Gate;
with accepted M-02 and M-03 evidence, Phase 0 is complete and C-01 is unblocked but not
started. No paid/provider call, remote write, factory-statistics/pricing change, Gate
relaxation, C-01/Core/C-02 work, or product-code mutation occurred during recovery.

Permitted claim: current versioned accounting preserves every author-visible outcome beside
DEFER and reproduces the committed mixed-outcome semantic unit across 20 isolated processes.
This does **not** establish public-corpus precision/recall, north-star architecture quality,
provider quality, production reliability, or a release decision.
