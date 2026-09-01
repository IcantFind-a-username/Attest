# M-03 immutable paid-call role revalidation — 2026-08-31

Status: **PASS** for M-03, `G-CODE-001`, and `G-MEASURE-003`.

This report supersedes, but does not erase, the explicitly
[INVALIDATED `81bf625` acceptance](2026-08-30-m03-revalidation.md). The accepted
implementation is `bce13f00e5f3e5002b457a930d9378ec8d171e88`; the acceptance-record
commit changes documentation/evidence only and is reported in the final handoff.

No M-01, M-02, C-01, Certification Kernel, Core, factory alpha/LR/channel cap,
paid provider action, or remote mutation is included.

## Repository state and scope

- branch: `feature/evidence-scheduler-roadmap`;
- historical invalid acceptance: `81bf625`;
- explicit reopening/erratum: `e155103`;
- first role-aware implementation, later invalidated: `7dfdfab`;
- request/report authority correction: `bf0a84b`, later invalidated by a remaining
  comparison publication P1;
- final implementation: `bce13f0`, clean before both accepted Gates;
- both detached checkouts: clean before and after their complete Gate;
- main checkout after implementation: dirty only with this acceptance/evidence update;
- paid actions, provider network calls, and remote mutations: none.

The accepted evidence bundle is
[`evidence/2026-08-31-m03-role-revalidation/`](evidence/2026-08-31-m03-role-revalidation/).
The `7dfdfab` and `bf0a84b` observations are retained in adjacent directories with
prominent `INVALIDATED.md` markers and are not reused.

## RED → GREEN

The original review finding was confirmed rather than accepted mechanically: paid-call
identity did not distinguish `product` from `benchmark_oracle`, so stability, live, and
comparison could misclassify or independently restate spend. The unified role-aware
implementation made the requested focused regressions GREEN, after which the new
independent reviewer found and reproduced three further RED cases:

1. rewriting role consistently in checkpoint, artifact, and spend row survived offline
   reconciliation while the original request digest remained unchanged;
2. changing a stability observation's reconciliation digest did not change the report
   digest;
3. adding fabricated paid rows and spend to the local Ruff arm, then rebuilding its
   summary, produced a comparison report without any corresponding ledger authority.

The first two failures invalidated `7dfdfab`; the third invalidated `bf0a84b`. Each Gate
was discarded before accepting the next implementation SHA. On `bce13f0`, the exact
regressions and their neighboring suites are GREEN.

## Unified authority contract

- Roles are the closed set `product` and `benchmark_oracle`; role is selected through a
  scoped provider before dispatch and is never inferred from call order.
- Call checkpoint schema v5 persists the canonical request preimage, including role, and
  recomputes its digest during offline loading. Artifact and cost schemas v4 carry the
  same request/role authority. Missing, unknown, drifted, or role-rewritten evidence fails
  closed. Old roleless schemas receive an explicit unsupported-version error.
- Predeclarations bind the allowed roles. Checkpoints, content-addressed artifacts, spend
  rows, reconciliation records, observations/results, ledgers, and report digests carry
  or derive from the same role-aware rows.
- Stability predeclaration/report schema v4 keeps observation schema v3 and now publishes
  per-repeat call counts and reconciliation digests. Product, oracle, and total spend are
  replaced with authoritative row totals even after evaluation raises following a settled
  product or oracle response.
- Live schema v4 and calibration schema v3 derive case, artifact, ledger, and report
  product/oracle/total values from verified rows. A result claiming `0.01` against rows
  totaling `0.0004` is rejected.
- Comparison checkpoint v5, reconciliation v2, and report v3 retain disjoint role totals.
  In the mixed fixture, total `0.0144` is product `0.0108` plus oracle `0.0036`; product is
  never reported as `0.0144` with oracle added again. The Ruff local-tool arm permits tool
  time but no provider calls, model tokens/identity, or paid spend.
- A legitimate zero-call run binds count zero plus the canonical empty reconciliation
  digest. Deleting evidence from a non-empty completed run disagrees with that stored
  binding and fails closed.

## Trial → spend → artifact and crash behavior

Every dispatched paid call must join exactly one call checkpoint, one content-addressed
artifact, and one spend row with the same trial/call ID, model, predeclaration, canonical
request digest, and role. Validation is bidirectional and rejects missing, duplicate,
mismatched, orphaned, or reclassified evidence. `ambiguous_cost` is durable and is never
automatically retried; response settlement and consumption replay are idempotent.

Failure injection covers `reserved`, `dispatched`, `response_persisted`, and `consumed`.
Same-directory complete temporary writes followed by `os.replace` expose the old complete
file or replacement across a controller/process crash. A dispatched call without a
durable response becomes `ambiguous_cost`; a durable response is replayed without another
provider dispatch. This is a single-local-filesystem process-crash contract, not a
distributed transaction or power-loss claim.

## Locked runtime and Action

`action.yml` uses declared CPython `3.12.8`, installs the complete audited
`requirements-toolchain.lock`, installs the project with `--no-deps
--no-build-isolation`, and runs `pip check`. This remains the M-03-consistent choice:
`G-CODE-001` covers the shipped primary path, so leaving that path on a floating Python or
dependency resolution while claiming a fully locked environment would be contradictory.

- lock SHA-256:
  `76908dd8dc527b59e95ab856cf67656946a4c1bf8eecbb0d95430a2161341c11`;
- local offline wheelhouse inventory SHA-256:
  `65e07106d4b90c72b204012a1bbec7cf78f6866c815312cbb9db620a3131c325`;
- platform: macOS 26.5.2 / Darwin 25.5.0 / arm64;
- both venvs: `include-system-site-packages = false`;
- project installation did not re-resolve dependencies.

## Final-SHA Gate results

Both fresh detached checkouts of `bce13f0` ran the following complete sequence after
offline lock installation:

```text
pytest tests/test_phase3_acceptance.py tests/benchmark/test_checkpoints.py \
  tests/benchmark/test_live.py tests/benchmark/test_stability.py \
  tests/benchmark/test_api.py tests/benchmark/test_baselines.py -q
pytest tests/benchmark -q
pytest -q
ruff check .
mypy src/attest
pytest --cov=src/attest --cov-report=term-missing -q
pip check
git diff --check
test -z "$(git status --porcelain=v1)"
```

| Gate | Python 3.11.5 | Python 3.12.8 |
|---|---:|---:|
| focused | 213 PASS | 213 PASS |
| benchmark | 479 PASS | 479 PASS |
| full pytest | 860 PASS | 860 PASS |
| Ruff 0.16.5 | PASS | PASS |
| Mypy 2.3.1 | PASS, 47 files | PASS, 47 files |
| coverage | 92.36% | 92.36% |
| `attest.core` coverage | ≥99% | ≥99% |
| `pip check` | PASS | PASS |
| diff / clean checkout | PASS | PASS |

Test counts are observations, not frozen thresholds.

| Identity | Python 3.11 | Python 3.12 |
|---|---|---|
| interpreter | `cpython-3.11.5-darwin-arm64` | `cpython-3.12.8-darwin-arm64` |
| environment SHA-256 | `a2db048e977ee7846607d282992c9e67a2e549a444f29d94c276ab96bc84c565` | `b505be2eaf33a0b45c6986bd6fecd167ffc806a62bcb566567a9b97a1bb42bf9` |
| code SHA-256 | `8b2c15761ee7b02f64dd02ad9478bd79373dfc472e01ea642e4c481d7d7dda40` | same |
| freeze SHA-256 | `fb0afeecf7a8a11eda1c27c5bd4dd8ecca22c3e85e5c23f6e9c0b36c44551932` | `95b1b85e2bc5bbc8e214a27a1f63e95b1f6f71542dd22ffecad3f6419cb3b7ae` |
| Gate log SHA-256 | `185441da9e0a8be5c116fba42443c20c4fe18314e5659f55fbbeb1ee8f48b108` | `bec933ff46e2829a708e0a510be1df72756e78e7b500da3c7cc6f33aaa41a5bc` |

## Independent review

The new reviewer did not participate in implementation. It reviewed the complete role
change, found the three additional P1s above, verified each RED and correction, and then
signed off `bce13f0` plus its final-SHA logs with P0=0, P1=0, P2=1. It judged M-03,
`G-CODE-001`, and `G-MEASURE-003` PASS. See
[`review.md`](evidence/2026-08-31-m03-role-revalidation/review.md).

## Known limits and rollback

- The one P2 is standalone pure-reducer API hardening: direct
  `build_calibration_report(LIVE)` trusts caller-established rows rather than reopening
  filesystem authority. The only current CLI/production path, `run_live_local`, verifies
  checkpoint/artifact/ledger authority first; no present publication entry bypass exists.
- An actor able to rewrite every local authority file and recompute every digest cannot be
  detected without an external authenticated root. That belongs to V-03/X-01, not M-03.
- Linux x86_64 remains a lock target but was not locally available; this report proves the
  required minimum and primary Python strata on the recorded macOS arm64 host.
- Fake/cassette/offline results make no provider-quality or production-reliability claim.
- Rollback retains paid-call state and uses its exact compatible schema reader. Unknown
  dispatches remain `ambiguous_cost`; never coerce old roleless state or redispatch an
  uncertain call.

Paid actions = none. Remote mutations = none.

## 2026-08-31 append-only integration erratum

The observations above remain immutable evidence for `bce13f0`; their v5 comparison
checkpoint, v3 comparison/calibration reports, live v4 state, stability v4 predeclaration,
and evaluation-binding v1 statements are historical facts about that SHA. They are not the
current writer versions after M-02/M-03 integration, and this erratum does not rewrite them.

The accepted integration implementation
`14a57fb3eeaf7c38f136a5e82151f8d3c738af5b` uses comparison checkpoint v6,
comparison report v4, calibration report v4, live predeclaration/per-case checkpoint v5,
stability predeclaration v5 with stability report v4, and evaluation binding v2. Older
checkpoint/predeclaration forms are retained as historical bytes and rejected for current
resume/replay; report artifacts remain historical-only. Benchmark report v3, live
calibration report v4, and validation receipt V1/V2 are not silently reinterpreted.

The integration also supersedes the prior P2 observation under the now-explicit Phase 0
execution boundary: current V2 HMAC authority is production-reachable only through pure
non-executing `verify-validation`; no supported current-V2 production execution workflow
exists before X-01/V-03 or a public-key protocol. Final integration review is
P0=0/P1=0/P2=0 and the dual-Python evidence is recorded in
[`2026-08-31-m02-m03-integration-revalidation.md`](2026-08-31-m02-m03-integration-revalidation.md).
