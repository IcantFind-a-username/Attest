# M-03 deterministic, version-locked, crash-safe measurement revalidation — 2026-08-30

Status: **INVALIDATED** — the PASS recorded at `81bf625` is retained below as
historical evidence, but it is not a current M-03 completion claim.

> **ERRATUM — INVALIDATED 2026-08-30.** Independent review reproduced three P1
> failures with one root cause: paid-call evidence did not bind an immutable
> `product` versus `benchmark_oracle` role, and reports trusted separately supplied
> spend fields. This allowed role ambiguity, overlapping product/oracle accounting,
> post-settlement cost erasure, and report totals that disagreed with authoritative
> call rows. The clean-install results below remain valid observations for
> `5e4234d`, but do not establish the corrected role-aware contract and cannot be
> reused to accept a later implementation SHA. M-03 is reopened pending unified RED
> → GREEN repair, fresh SHA-bound Python 3.11/3.12 Gates, and a new independent
> review with P0/P1=0.

This report supersedes, but does not erase, the explicitly
[INVALIDATED historical acceptance](2026-08-30-m03-deterministic-crash-safe-measurement.md).
The accepted implementation is
`5e4234dc71959ac67093d3f56c301324ba1eaa73`, derived from the original M-03
baseline `bcfd9d8624a03858ea5aa71fff84412e6efa6606`. The invalid PASS record was
`b89785239f38ee5bc7a09c7f7c1d205116e62bf1`; invalidation/reopening was committed
as `dba29aead10903541848fae61491dcdd8c4f69a2`.

No M-01, M-02, C-01, Certification Kernel, Core, factory alpha/LR/channel cap,
paid provider action, or remote mutation is included.

## Repository state and scope

- branch: `feature/evidence-scheduler-roadmap`;
- `b897852`: clean historical acceptance head, subsequently invalidated;
- `dba29ae`: clean reopened baseline retaining the old report as INVALIDATED;
- `5e4234d`: clean final implementation commit and the exact SHA checked out for
  both accepted environments;
- final acceptance-record SHA: the commit containing this report and roadmap
  update, reported in the handoff; it changes documentation/evidence only;
- paid actions: none;
- provider/network calls: none; tests use local fakes and cassettes;
- remote mutations: none; no push, PR, or remote write occurred.

The revalidation evidence bundle is
[`evidence/2026-08-30-m03-revalidation/`](evidence/2026-08-30-m03-revalidation/).

## RED → GREEN evidence

Each blocker was reproduced on the then-current implementation before its fix.

1. `ruff check .` reproduced the three reported import errors; minimal import-only
   corrections made the focused static check green.
2. Removing `calls/000000.json` from a completed live case while retaining its
   artifact/spend was accepted; publication now reconstructs the authoritative
   checkpoint/spend/artifact join and fails closed.
3. A settled provider response followed by an `evaluate_project` exception returned
   a zero-cost DEFER; the DEFER now retains authoritative spend and reconciliation
   rows/digest.
4. The Action used a floating runtime and ranged dependency resolution; D-046 now
   requires primary CPython 3.12.8 plus the exact full lock and `pip check`.
5. Review reproduced post-settlement new-ordinal dispatch and publication without
   rereading artifacts; settled replays now impose a no-new-ordinal bound and reports
   reread call evidence through a no-dispatch verifier.
6. Review reproduced model drift, omission of one paid arm, self-consistent empty
   measurement replacement, orphan paid-call roots, invalid frozen binding fields,
   and coordinated model metadata rewrite. Comparison schema v4 now binds every
   `(case, arm, trial, model)` to a complete frozen evaluation binding, requires the
   exact three-arm run matrix, recomputes summaries/evaluated IDs, reverse-scans
   reconciliation and call roots, and rejects absent authority.
7. Universal call schema v3 and artifact/cost schema v2 bind `model_id` plus the
   canonical full-predeclaration digest through checkpoint, artifact, spend row,
   reconciliation, and report. The coordinated rewrite regression is now GREEN.
8. A legitimate predeclared empty comparison remains publishable as `not_executed`;
   this does not permit replacing an executed study with a rootless empty matrix.

Intermediate candidates `7031d54`, `800b92a`, `b723c74`, `c0d7898`, `c095717`, and
`6dd465c` were rejected when review found a remaining P1. Their test runs are not used
as acceptance evidence for `5e4234d`.

## Trial → spend → artifact and crash contract

Every paid subcall has one trial/call ID, one call checkpoint, one content-addressed
artifact, and one spend row. The reconciliation record carries their paths/digests,
model ID, and full-predeclaration digest. Validation runs both from declared trials to
evidence and from persisted evidence back to the declared trial matrix.

| Case | Result |
|---|---|
| normal one-to-one join | PASS |
| missing/duplicate/mismatched spend | fail closed |
| missing/misbound/orphan artifact | fail closed |
| missing checkpoint with retained spend/artifact | fail closed |
| omitted paid arm/trial or rootless empty replacement | fail closed |
| orphan paid-call root or reconciliation marker | fail closed |
| frozen binding/model/provider/policy/code drift | fail closed |
| coordinated model rewrite without rewriting call evidence | fail closed |
| `ambiguous_cost` | durable; no automatic retry |
| response settlement/consumption replay | idempotent; no duplicate dispatch/row |

Failure injection covers `reserved`, `dispatched`, `response_persisted`, and
`consumed`. Same-directory complete temporary writes followed by `os.replace` expose
the prior complete file or replacement to another process. Resume after a durable
response reuses it; a dispatch without a durable response becomes `ambiguous_cost`.
This is controller/process-crash safety on one local filesystem, not a distributed
transaction or power-loss durability claim.

## Complete lock and Action runtime

`requirements-toolchain.lock` exactly pins the build backend/frontend, editable-build
support, runtime closure, Gate tools, pip, setuptools, and transitive dependencies.
NumPy has explicit Python-version markers because the accepted 3.11 and 3.12 strata
use different compatible wheels. D-046 selects CPython 3.12.8 in `action.yml`, installs
that lock, installs Attest with `--no-deps --no-build-isolation`, and runs `pip check`.
This is the technically consistent choice because M-03 owns CI setup and
`G-CODE-001` requires the shipped primary path to consume the audited toolchain;
narrowing the claim would leave the M-03 Action outside its own reproducibility Gate.

- lock SHA-256:
  `76908dd8dc527b59e95ab856cf67656946a4c1bf8eecbb0d95430a2161341c11`;
- local wheelhouse content/inventory SHA-256:
  `00a6be8145596bc464735d89805dfe699a13791feac09e87dc766420b9c7f755`;
- install source: pre-existing local wheelhouse with `--no-index`;
- both venvs: `include-system-site-packages = false`;
- no dependency re-resolution for the editable project.

Clean-install commands, run independently with `python3.11` and `python3.12`:

```text
git worktree add --detach <fresh>/checkout 5e4234dc71959ac67093d3f56c301324ba1eaa73
pythonX.Y -m venv <fresh>/venv
<fresh>/venv/bin/python -m pip install --no-index \
  --find-links <local-wheelhouse> -r requirements-toolchain.lock
<fresh>/venv/bin/python -m pip install --no-index \
  --find-links <local-wheelhouse> --no-deps --no-build-isolation -e .
<fresh>/venv/bin/python -m pip check
```

## Final-SHA Gate results

Both environments ran the following sequence from clean detached checkouts of
`5e4234d` after installation:

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
|---|---|---|
| focused | 189 passed | 189 passed |
| benchmark | 455 passed | 455 passed |
| full pytest | 836 passed | 836 passed |
| Ruff 0.16.5 | PASS | PASS |
| Mypy 2.3.1 | PASS, 47 source files | PASS, 47 source files |
| coverage | 92.41% | 92.41% |
| `attest.core` coverage | ≥99% | ≥99% |
| `pip check` | PASS | PASS |
| `git diff --check` / clean checkout | PASS | PASS |

Test counts are observations, not frozen thresholds.

| Identity | Python 3.11 | Python 3.12 |
|---|---|---|
| interpreter | `cpython-3.11.5-darwin-arm64` | `cpython-3.12.8-darwin-arm64` |
| platform | macOS 26.5.2 / Darwin 25.5.0 / arm64 | same |
| environment SHA-256 | `a2db048e977ee7846607d282992c9e67a2e549a444f29d94c276ab96bc84c565` | `b505be2eaf33a0b45c6986bd6fecd167ffc806a62bcb566567a9b97a1bb42bf9` |
| code SHA-256 | `6f39f562de64bc7dd428665beeb98fc3cd2198f47b998904f3acac6434c45852` | same |
| freeze SHA-256 | `bd906ca867bb62f2ea0be0ced514891175408ba44efe0724498b7e50c6156814` | `9ebd47cb80fe2a686abd97ae6c72908b025b617aadd93fd17e48540cecbc9753` |
| full-Gate log SHA-256 | `c627ee8e135de7306c356eb7e7c56bb2ec330ed353adc53ea4d633d59ab9062d` | `474471adac5f3621991b61741add93bfba12252c8ee22f41cd84045c227d509f` |

## Independent review

The reviewer did not participate in implementation. Review repeatedly attacked the full
M-03 diff, and every reported P1 was reproduced before correction. The final review of
`bcfd9d8..5e4234d`, after the final-SHA dual-environment Gate, reported P0=0, P1=0,
P2=0 and judged M-03, `G-CODE-001`, and `G-MEASURE-003` PASS. Details are in
[`review.md`](evidence/2026-08-30-m03-revalidation/review.md).

## Known limits and rollback

- Linux x86_64 remains a declared lock target but was not locally available; this report
  proves the required minimum/primary Python strata on the recorded macOS arm64 host.
- The wheelhouse is local installation evidence, not a committed binary mirror. The exact
  source lock is the portable dependency authority.
- Local evidence is fail-closed against missing, inconsistent, or drifted state. Defending
  against an attacker who rewrites every local artifact and recomputes all digests would
  require an external authenticated root and is outside M-03's process-crash contract.
- Fake/cassette results make no empirical provider-quality or production-reliability claim.
- Rollback retains all paid-call state and uses its compatible schema reader. Unknown
  dispatches remain `ambiguous_cost`; metrics are withheld. Never coerce old state or
  automatically redispatch an uncertain call.
