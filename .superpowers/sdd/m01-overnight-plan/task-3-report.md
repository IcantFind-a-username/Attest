# Task 3 report — authoritative mixed-outcome accounting

Status: complete on `feature/m01-authoritative-outcomes` from baseline
`7138482cbfe771108ac7163b8dcf1820bb761d02`. Initial implementation commit:
`c86c957fcde97d5ba6479553bc5cdea247ccf6bb`; final post-review sealing commit:
`c680641d0858a186b4ee49b7e2eafadd236c0679`. No paid provider, network provider,
remote write, factory-constant change, pricing change, Core change, or historical
evidence rewrite occurred.

## Contract delivered

- `MeasurementRecord` stays on wire schema v2. Current headline accuracy, harm,
  task status, and missingness now have one reducer,
  `reduce_measurements`, with reducer semantics `mixed_outcome_v3`.
- The primary semantic population is exactly repeat zero; operational repeats,
  operational missingness, channels, latency, and cost remain separate. Live
  strata now count semantic cases/surfaced cases from repeat zero only.
- Completed, partially deferred, fully deferred, and failed tasks retain every
  already-published finding. A positive non-completed task without a correct
  visible finding is a deployment miss. Only completed silent NULL controls are
  true negatives; a non-completed NULL task with a wrong visible finding remains
  adjudicated PR harm.
- NULL, POSITIVE, and UNADJUDICATED are distinct. Manifest controls use explicit
  empty truth and are adjudicated to NULL before persistence; generic absent truth
  remains UNADJUDICATED and withholds current accuracy rather than falling back to
  legacy scoring. Primary visible UNADJUDICATED accuracy is surfaced as missingness.
- The API adjudicates each measurement exactly once before artifact persistence.
  Compatibility `ProjectEvaluationScore` and top-level status/reason are projections
  of the strict measurement and are checked for consistency.
- Pre-execution taskless failures remain exclusions through the exact empty
  transcript sentinel. Once a task exists, post-execution authority/persistence
  failure propagates; published findings cannot disappear into an exclusion or
  synthetic DEFER.
- Comparison first-run, sealed rebuild, and resume preserve product
  `product_measurement`. Product run findings use an exact `finding_id` projection
  from that adjudicated record; validator/rebuild/report paths share the projection
  and never rematch product truth. Bare-prompt and Ruff remain explicitly
  `legacy_v1_scoring`; Task 3 did not add a third scorer.
- Report, live, stability, replay/compare CLI, and current channel outcomes consume
  the reducer or exact measurement projection. Current validation authority refuses
  legacy-only records and zero-record fallbacks. Stability observation v4,
  predeclaration/report v5 persist strict measurements and reject older evidence
  rather than silently reinterpreting it.
- Surfaced statistics and precision share one ledger snapshot/population. Only
  reconciled successful delivery events surface a finding; a planned `ci_final`
  row cannot create a phantom publication during a crash window.

The five-unit authoritative truth table is frozen by
`test_authoritative_five_unit_truth_table_keeps_harm_misses_and_task_state`:

- semantic units `5`; statuses completed/partial/full/failed = `2/1/1/1`;
- published/unresolved = `3/2`;
- correct/wrong/precision = `1/2/1⁄3`;
- eligible/detected/missed/detection = `4/1/3/1⁄4`;
- NULL PRs/false-positive PRs/FPR = `2/1/1⁄2`;
- adjudicated PRs/any-wrong PRs/rate = `5/2/2⁄5`.

## RED/GREEN evidence

- Initial eight-file focused command exited 1 with 539 passing and two failing
  legacy expectations. The comparison rewrite test still mutated caller
  `ArmRun` rather than sealed measurement evidence, and the mixed-publication
  expectation still treated current evidence as unadjudicated.
- The required compare CLI node was initially absent (pytest exit 4); after the
  node was added it exposed missing current `outcome_accounting`, then passed with
  the sealed product projection.
- Coordinated caller/product tampering now fails at the exact `finding_id` join;
  first-run, resume, and validator tamper selections pass.
- The taskless/transcript, outer status/reason, abstention exact-set, primary versus
  operational UNADJUDICATED, primary visible missingness, NULL reservation, and
  API status-projection injections all pass their focused selections.
- Strata had a recorded exact RED:

  ```text
  .venv/bin/python -m pytest \
    tests/benchmark/test_live.py::TestCalibrationReport::test_current_channel_outcomes_join_exact_operational_repeat -q
  exit 1: 3 failed; cases was 2, expected semantic cases 1
  ```

  The minimal repeat-zero strata filter plus exact outer-repeat validation then
  produced `6 passed`, exit 0.
- The final authorized-path review reports P0/P1/P2 = `0/0/0`.

## Final verification

- Required eight-file focused Gate, after every production change:

  ```text
  .venv/bin/python -m pytest \
    tests/benchmark/test_measurement.py tests/benchmark/test_api.py \
    tests/benchmark/test_baselines.py tests/benchmark/test_report.py \
    tests/benchmark/test_live.py tests/benchmark/test_stability.py \
    tests/benchmark/test_cli.py tests/test_cli_e2e.py -q
  exit 0: 563 passed, 0 failed
  ```

  Collection split: API 49, baselines 123, CLI 14, live 119,
  measurement 182, report 32, stability 23, CLI E2E 21.
- Adjacent Gate:

  ```text
  .venv/bin/python -m pytest \
    tests/benchmark/test_runner.py tests/benchmark/test_metrics.py -q
  exit 0: 66 passed, 0 failed
  ```

- Owned-file Ruff: `All checks passed!`, exit 0.
- Required mypy command over benchmark, CLI, and ledger: `Success: no issues
  found in 19 source files`, exit 0. The controller's broader `src/attest` mypy
  check also passed 49 source files.
- `git diff --check`: exit 0.
- `git diff -U0 -- tests | rg '^\+\s+(from|import) '`: no matches; no new
  function-body imports.
- Repository-root and `tests/` conftests exist and hold the shared local-Ruff and
  comparison-authority fixtures.
- No dual-Python/full-repository Gate was run here; Task 5 owns that Gate.

## Diff and volume

Implementation diff before this report:

```text
18 tracked files changed, 2726 insertions(+), 521 deletions(-)
root/tests conftest additions: 35 lines
```

Final staged diff including the two conftests and this report:
`21 files changed, 2952 insertions(+), 521 deletions(-)`.

Production: `1228 added / 260 deleted / +968 net`, below the `+1500` limit.
Tests plus the two conftests: `1533 added / 261 deleted / +1272 net`.

The tracked per-file `git diff --stat` was:

```text
 scripts/benchmark.py                |  73 ++++---
 src/attest/benchmark/api.py         | 152 ++++++++++---
 src/attest/benchmark/baselines.py   | 214 +++++++++++++++---
 src/attest/benchmark/live.py        | 269 +++++++++++++++++++----
 src/attest/benchmark/measurement.py | 113 +++++++++-
 src/attest/benchmark/report.py      | 322 ++++++++++++++++++++++++---
 src/attest/benchmark/stability.py   | 238 ++++++++++++++------
 src/attest/cli/main.py              |  15 +-
 src/attest/review/ledger.py         |  92 +++++---
 tests/benchmark/test_api.py         | 151 ++++++++++++-
 tests/benchmark/test_baselines.py   | 248 +++++++++++++++++++--
 tests/benchmark/test_cli.py         |  64 +++++-
 tests/benchmark/test_live.py        | 419 +++++++++++++++++++++++++++++++++---
 tests/benchmark/test_measurement.py | 354 ++++++++++++++++++------------
 tests/benchmark/test_report.py      | 283 ++++++++++++++++++++++--
 tests/benchmark/test_runner.py      |  48 ++++-
 tests/benchmark/test_stability.py   | 174 ++++++++++-----
 tests/test_cli_e2e.py               |  18 ++
```

## Tool reuse and additions

Reused existing tools:

- canonical JSON and atomic artifact/outcome writers;
- report digest construction;
- `wilson_interval`;
- the existing matcher for the single API adjudication and explicit legacy
  bare/Ruff paths only;
- legacy `aggregate(RunRecord)` only behind the named legacy adapter;
- the existing delivery reconciliation and credential-filter tuple.

Approved additions:

- `measurement_summary_payload` plus its one recursive float normalizer: a pure
  `dataclasses.asdict` projection with no scoring, matching, receipt, or delivery
  logic;
- `_product_measurement_matches`: a pure exact-`finding_id` projection from an
  already-adjudicated `MeasurementRecord`, shared by first run, rebuild/resume,
  and validation.

No other scorer, matcher, digest, receipt, canonical serializer, or atomic-write
primitive was added.

The required duplicate scan still finds historical canonical/atomic helpers in
`checkpoints.py`, `stability.py`, `baselines.py`, `live.py`, and `report.py`, in
addition to the canonical implementation in `artifacts.py`. None was introduced
by this Task 3 diff. Consolidating those pre-existing implementations is an
explicit whole-tree debt and was not mixed into this bounded change.

## Fixed-SHA closure

- Final post-review sealing at `c680641` corrected silent-run versus abstention reporting,
  bound exact stability observations into canonical evidence, rejected non-finite wealth
  and extra nested fields, and retained exact current denominators. Full pytest, Ruff,
  mypy (49 source files), and diff check passed; final review P0/P1/P2 = 0/0/0.

- `git rev-parse c86c957^` resolves the baseline above, and
  `git cat-file -e <baseline>^{commit}` succeeds.
- The historical ledger fixture now states the current delivery contract directly:
  a `ci_final` row is a publication plan, not successful delivery authority. Without
  a reconciled successful delivery event, public `Ledger.surfaced_precision()`
  returns `(None, 0)`. The successful-delivery path remains covered by
  `tests/benchmark/test_runner.py`.
- Closure Gate:
  `.venv/bin/python -m pytest -q tests/test_budget_ledger.py tests/benchmark/test_runner.py`
  — exit 0, `81 passed / 0 failed`; owned-test Ruff and `git diff --check`
  also exit 0.
- Closure diff: two files only — this report and `tests/test_budget_ledger.py`;
  `23 insertions / 11 deletions`.
- Tool reuse: the existing public `Ledger` API and existing delivery reconciliation;
  no new helper, scorer, serializer, matcher, digest, receipt, or atomic-write tool.
