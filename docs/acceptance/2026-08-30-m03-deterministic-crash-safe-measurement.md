# M-03 deterministic, version-locked, crash-safe measurement — 2026-08-30

> **ERRATUM — INVALIDATED 2026-08-30.** The original PASS below was recorded
> before final review identified four P1 completion blockers: a completed live
> case could lose its call checkpoint while retaining spend/artifact evidence;
> a comparison DEFER could discard already-settled spend and did not publish a
> validated reconciliation binding; the Action installed a floating runtime
> outside the audited lock; and the clean-environment logs predated the accepted
> SHA. This report remains as historical evidence and must not be used to claim
> M-03 completion. A separate revalidation report will supersede it only after
> the corrected implementation SHA passes both clean interpreter Gates and
> independent review.

Status: **INVALIDATED** (original recorded status: PASS for M-03,
`G-CODE-001`, and `G-MEASURE-003`)

This report accepts implementation commit
`cf8778d13accb410750ec3558f83d7de85e747a0` from baseline
`bcfd9d8624a03858ea5aa71fff84412e6efa6606`. The acceptance-record SHA is the
commit containing this file and is reported in the final handoff.

No M-01, M-02, C-01, Certification Kernel, Core, factory statistical constant,
paid provider, or remote mutation is included.

## Scope and repository state

- branch: `feature/evidence-scheduler-roadmap`;
- baseline SHA: `bcfd9d8624a03858ea5aa71fff84412e6efa6606`;
- implementation SHA: `cf8778d13accb410750ec3558f83d7de85e747a0`;
- starting state: dirty M-03 candidate at the baseline SHA (12 modified tracked files
  and 3 untracked M-03 files); the complete starting diff and status were reviewed before
  changes, and no user change was reset, stashed, or overwritten;
- implementation state: clean immediately after the implementation commit;
- final acceptance state: this report, D-045, and the roadmap M-03 status are the only
  post-implementation changes;
- paid actions: none;
- remote mutations: none;
- network/provider calls: none; all provider tests used local fakes or cassettes.

## RED evidence retained

The work preserved or reproduced each failure before its fix:

1. `ruff check .` reported exactly three import errors: import order in
   `src/attest/benchmark/live.py` and `tests/benchmark/test_live.py`, plus
   `Callable` imported from `typing` instead of `collections.abc` in
   `tests/test_phase3_acceptance.py`.
2. The first Python 3.11 clean install failed while building editable metadata with
   `ModuleNotFoundError: editables`; this proved the first lock draft was not a complete
   build/runtime/test closure.
3. The first trial/spend/artifact table produced seven failures because call reconciliation
   records, authoritative per-call cost rows, or call artifacts were absent.
4. The first static pass produced four Mypy errors for unchecked checkpoint ordinals.
5. Independent review reproduced four fail-open cases: orphan spend, orphan artifact,
   missing stability spend, and missing stability artifact. The added tests failed because
   no exception was raised.
6. Independent review then removed the entire `repeat-N-calls` directory and reproduced
   acceptance of a self-consistent empty evidence set. That RED led to observation schema
   v2 binding the expected call count and evidence digest.
7. A controller-drift test initially failed at collection because code identity had no
   paid-controller digest seam.

The pre-existing wall-clock assertion was also converted to two injected dates. Workflow
process/conclusion failures were covered before acceptance artifacts could be trusted.

## GREEN behavior

- clocks are injected and event dates are tested at `2026-08-29` and `2031-01-02`;
- predeclarations bind repository identity, resolved SHAs, diff/truth/receipt/policy,
  provider/model/prompt/schema, interpreter/environment, code, and budget;
- code identity covers package Python/TOML/JSON plus the paid benchmark and acceptance
  controller entrypoints;
- every provider/generator subcall uses `reserved -> dispatched -> response_persisted ->
  consumed`, or durable `ambiguous_cost`;
- a dispatched call without a durable response is never automatically retried;
- response replay, settlement, and consumption are idempotent;
- every terminal call joins exactly one checkpoint, spend row, and content-addressed
  artifact; missing, duplicate, mismatched, and orphan evidence fail closed;
- live case artifacts, cost summaries, and calibration reports carry the verified paid-call
  joins;
- stability observation schema v2 binds call count and the full reconciliation digest, so a
  missing spend row, artifact, or whole call-evidence directory invalidates resumption;
- workflow exit status and final conclusion must both be successful;
- old call/live/stability/comparison schemas fail with actionable supported-version errors.

## Crash durability boundary

Checkpoint, artifact, ledger, and enclosing-state replacement writes a complete temporary
file and then uses same-directory `os.replace`. For the M-03 controller/process-crash
contract, observers therefore see the prior complete file or the replacement. Failure
injection covers every public call transition:

| Crash boundary | Resume result | Redispatch |
|---|---|---|
| `reserved` | dispatch once | one initial dispatch only |
| `dispatched`, no response | durable `ambiguous_cost`; claims withheld | none |
| durable artifact/`response_persisted` | response and settlement replayed | none |
| settled/`consumed` | existing spend/artifact verified | none |

Crashes between artifact, spend, and terminal checkpoint writes are recovered by verifying
the already durable artifact/row before advancing. This contract is process-crash safety on
one local filesystem; it does not claim distributed transactions or power-loss durability.

## Trial/spend/artifact reconciliation matrix

| Case | Result |
|---|---|
| normal one-to-one join | PASS |
| missing spend row | fail closed |
| duplicate spend row | fail closed |
| mismatched trial/call identity | fail closed |
| missing or misbound artifact | fail closed |
| orphan spend row or artifact | fail closed |
| entire stability call-evidence directory missing | fail closed via observation binding |
| `ambiguous_cost` resume | no automatic retry; claims withheld |
| response/settlement/consumption replay | idempotent; one spend row and artifact |

## Complete lock and clean installs

`requirements-toolchain.lock` contains exact pins for the build frontend/backend,
editable-build support, project runtime closure, and all Gate tools/transitive dependencies.
`pip==26.2.1` and `setuptools==83.0.0` are pinned rather than inherited from `venv`.
Only NumPy differs by an explicit interpreter marker because no one wheel version in the
available local artifacts spans both required CPython versions.

- lock SHA-256:
  `76908dd8dc527b59e95ab856cf67656946a4c1bf8eecbb0d95430a2161341c11`;
- local wheelhouse inventory SHA-256:
  `6a8c4eada5ad1197fef3a0ccb04536df3375f003b58cbba0ec5f861d613029e9`;
- install source: pre-existing local pip cache/audit artifacts only; `--no-index` prevented
  remote access;
- project install: editable, `--no-deps --no-build-isolation`, after the complete lock;
- both environments: `include-system-site-packages = false`, `pip check` PASS.

Commands, repeated with `python3.11` and `python3.12`:

```text
pythonX.Y -m venv <fresh-dir>/venv
<fresh-dir>/venv/bin/python -m pip install --no-index \
  --find-links <local-wheelhouse> -r requirements-toolchain.lock
<fresh-dir>/venv/bin/python -m pip install --no-index --no-deps \
  --no-build-isolation -e .
<fresh-dir>/venv/bin/python -m pip check
<fresh-dir>/venv/bin/python -VV
<fresh-dir>/venv/bin/python -m pip freeze --all
```

| Field | Minimum environment | Primary environment |
|---|---|---|
| Python | CPython 3.11.5 | CPython 3.12.8 |
| platform | macOS 26.5.2, Darwin 25.5.0, arm64 | macOS 26.5.2, Darwin 25.5.0, arm64 |
| pip | 26.2.1 | 26.2.1 |
| NumPy marker | 2.4.6 | 2.5.2 |
| freeze digest | `d1e192528f5db36d37baa2958a90611648c5b67c293474ccf569609a8a1f5e2a` | `48992ef69161a893ec7350643c15fb3ee4ef408399ea63b3228520c65b12dde0` |
| runtime environment digest | `a2db048e977ee7846607d282992c9e67a2e549a444f29d94c276ab96bc84c565` | `b505be2eaf33a0b45c6986bd6fecd167ffc806a62bcb566567a9b97a1bb42bf9` |
| code digest | `bbc9468b12ad1d37cf9ad388c885664602f3308424c8988723881ea41f45ff1f` | same |

## Final Gate results

The following sequence ran independently in both fresh environments:

```text
pytest tests/test_phase3_acceptance.py tests/benchmark/test_checkpoints.py \
  tests/benchmark/test_live.py tests/benchmark/test_stability.py \
  tests/benchmark/test_api.py tests/benchmark/test_baselines.py -q
pytest tests/benchmark -q
pytest
ruff check .
mypy src/attest
pytest --cov=src/attest --cov-report=term-missing
git diff --check
```

| Gate | Python 3.11.5 | Python 3.12.8 |
|---|---|---|
| focused, 168 collected | PASS | PASS |
| benchmark, 434 collected | PASS | PASS |
| full pytest | 814 passed | 814 passed |
| Ruff 0.16.5 | PASS | PASS |
| Mypy 2.3.1 | PASS, 47 files | PASS, 47 files |
| coverage | 92.52% | 92.52% |
| `attest.core` coverage | ≥99% | ≥99% |
| `pip check` | PASS | PASS |
| `git diff --check` | PASS | PASS |

Test counts are observations, not frozen Gate thresholds.

## Independent review

The reviewer did not participate in implementation. The first review reported four P1s:
orphan evidence, stability resume bypass, incomplete bootstrap/evidence proof, and incomplete
controller code digest. After fixes, three were closed; the reviewer then found the
whole-directory stability deletion case. Observation schema v2 closed that case. Final
re-review reported:

- P0: none;
- P1: none;
- P2/P3: no new findings;
- M-03: PASS;
- `G-CODE-001`: PASS;
- `G-MEASURE-003`: PASS.

## Known limitations and rollback

- Linux x86_64 remains a declared lock target but was not available for this local
  acceptance run; this report proves the required minimum/primary interpreters on the
  recorded macOS arm64 platform, not a Linux execution result.
- The local wheelhouse is installation evidence, not a committed binary artifact. The
  portable source of truth is the exact transitive lock and its digest; artifact hashes are
  optional supply-chain hardening, not a condition in the current Gates.
- Provider responses in these tests are bounded local fixtures; no empirical model-quality
  or production reliability claim follows.
- For rollback, retain all call state, use the last compatible schema reader, keep
  `ambiguous_cost` unresolved, and withhold metrics. Revert the lock only to another
  declared lock that passes both supported interpreter Gates. Never coerce old paid-call
  state or automatically retry uncertain dispatch.
