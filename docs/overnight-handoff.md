# 2026-09-01 overnight handoff

Status: **six scoped waves complete; no finding surfaced; final dual-Python integration
Gate passed.**

This report binds the final implementation SHA
`e955f298cd2722865090d714c1644e258176f628`. The later report-seal commit is
documentation-only; the exact final gated SHA is
`ffd0dd2a5e40e8452e4c407612e624fb93075417`.

## Executive result

- The authoritative branch remained `feature/m01-authoritative-outcomes`; no push, remote
  write, third-party repository write, release, or public presentation occurred.
- Six waves completed. C-01 stopped at the pure versioned domain and validator; C-02,
  V-01, X-01, V-03, Core activation, presentation routing, and runner policy did not start.
- No real or counterfactual finding crossed a publication threshold. There is therefore no
  surfaced-finding headline, reproduction receipt, or wealth trace to preserve.
- Final implementation range `53f4641..e955f29`: 45 files changed, 2,633 insertions,
  879 deletions, net +1,754. The large additions are the bounded Wave 5 probe/evidence and
  C-01's isolated domain plus mutation tests; Wave 1 itself was net -147.
- Final documentation-bound gated range `53f4641..ffd0dd2`: 47 files changed, 3,001
  insertions, 887 deletions, net +2,114. The difference is roadmap, decisions, and this
  complete report.
- One bounded self-review was performed, as required by D-049. Its reproduced missing
  mutation guards were fixed in `e955f29`; final P0=0/P1=0. No second review loop ran.
- Development API spend increased by $2.340150, from $3.593000 to $5.933150 of the $10
  cap. Every call was pre-reserved and recorded in `DEVSPEND.md`.

## Wave ledger and line balance

| Wave | Final SHA | Commits | Added | Deleted | Net | Outcome |
|---|---|---:|---:|---:|---:|---|
| 1 | `0cdf56c` | 5 | 656 | 803 | -147 | coverage scope amended; C1-C7 calibrated/fixed |
| 2 | `0cdf56c` | 0 | 0 | 0 | 0 | complete integration Gate passed |
| 3 | `e25091c` | 4 | 353 | 29 | +324 | stop/token/silence observation and first bounded run |
| 4 | `ff258cd` | 6 | 227 | 53 | +174 | proposal headroom and bounded schema recovery; D-037(c) left out of scope |
| 5 | `638ae65` | 3 | 517 | 21 | +496 | F shadow signal and all-nine-pair counterfactual |
| 6 | `e955f29` | 2 | 907 | 0 | +907 | C-01 pure versioned certification domain |

Wave 4's originally retained in-process prompt wording was removed before Wave 5 closed.
Only D-037(a)'s fenced-JSON tolerance and one bounded retry remain. No runner process or
resource policy changed.

## Coverage Gate amendment and timing

D-050 and the owner-approved red-line-6 amendment now apply:

- hard `fail_under=90` only to `src/attest/review`, `src/attest/cli`, and
  `src/attest/github`; the threshold stayed exactly 90;
- `src/attest/benchmark` and `src/attest/core` print separate informational reports with
  `--fail-under=0`;
- benchmark and Core are frozen against feature growth, and Core cannot gain code without
  owner approval;
- ordinary waves run one supported Python; the final integration Gate runs Python 3.11.5
  and 3.12.8.

Measured complete-Gate wall time:

| Gate | SHA | Tests | Coverage | Wall time |
|---|---|---:|---|---:|
| before amendment | `53f4641` | 1543 passed | total 90.13%, Core 99.77% | 736.62 s |
| after amendment | `0cdf56c` | 1543 passed | product 92.00%, benchmark 89%, Core 99% | 729.77 s |

Delta: **-6.85 seconds (-0.93%)**. This is the required measured number. It changes which
package coverage has Gate authority, not test execution, so the small timing change is
expected; the recurring semantic benefit is that frozen measurement/research packages no
longer decide whether an unrelated product change clears 90%.

## Owner calibration C1-C7

1. **C1 — `scripts/benchmark.py` non-atomic JSON:** reproduced and fixed in `c810cea` by
   reusing `benchmark.artifacts.write_canonical_json`; no new atomic writer exists.
2. **C2 — Phase 3 boundaries:** reproduced environment allowlist and timeout gaps fixed in
   `198e617`; the existing `gh run watch` return-code check was already present and was
   retained. No GitHub write was performed.
3. **C3 — stats unification:** already complete; audited and deliberately not redone.
4. **C4 — `test_ci_flow` reverse dependency on scripts:** reproduced and removed in
   `198e617`; shared pure acceptance validation now lives in the product package.
5. **C5 — benchmark package wall/orphans:** the re-export wall was already removed and
   `verify_artifacts` was already in the product path. `surfaced_predictions` was confirmed
   orphaned and deleted.
6. **C6 — test setup/import structure:** root and `tests/` conftests already existed.
   Function-local imports in `tests/test_executor.py` went from about 59 to 0; shared setup
   moved to fixtures and repeated inputs to parameter tables in `d4812fd`.
7. **C7 — duplicate parameter tables:** audited; only the reproduced duplicate executor
   cases were consolidated. No blind rewrite was performed.

The shared credential tuple in `review/executor.py` was also reused by the offline probe in
`0cdf56c`; no duplicate credential filter was added.

## Wave 3 and Wave 4 operational comparison

Both runs used the same two historical-V1-validated pairs in both roles: two historical
bug replays and two developer-fix controls. V1 proves historical file integrity only; it
does not authorize accuracy. These are operational observations, not public accuracy
numbers.

| Measure | Wave 3 (`50055e2` observation) | Wave 4 (`df40c03` observation) |
|---|---:|---:|
| candidates N | 4 | 7 |
| schema-valid/execution-eligible reproductions M | 3 | 4 |
| head deterministic fail + base pass K | 0 | 0 |
| task abstention | 2/4 = 0.50 | 2/4 = 0.50 |
| actual surfaces | 0 | 0 |
| developer-fix controls | 2/2 silent | 2/2 silent |
| bug replay tasks | 2/2 deferred | 2/2 deferred |
| paid calls | 24 | 27 |
| spend | $0.330626 | $0.433304 |

Stop reasons, counted from the durable call artifacts:

| Role/cap | Wave 3 | Wave 4 |
|---|---:|---:|
| proposer `end_turn` | 16/20 | 19/20 |
| proposer `max_tokens` | 4/20 | 1/20 |
| reproduction `end_turn` | 3/4 | 4/7 |
| reproduction `max_tokens` | 1/4 | 3/7 |
| all calls `end_turn` | 19/24 | 23/27 |
| all calls `max_tokens` | 5/24 | 4/27 |

Increasing `PROPOSER_MAX_OUTPUT_TOKENS` from 1,600 to 2,400 reduced observed proposer
truncation from 4/20 to 1/20 in this one rerun. It did not produce a decisive V receipt.

DEFER reason distribution:

- Wave 3 candidate evidence: one schema-invalid/max-token reproduction and three
  schema-valid candidates that reached execution deferral. The pre-fix report retained
  only two task-level `terminal task status was deferred` reasons, so the three execution
  subreasons are not claimed more specifically. `e25091c` fixed that retention gap for
  later reports.
- Wave 4 candidate evidence: four schema-valid reproductions all hit the unchanged
  child-process guard; one candidate failed schema twice under the fixed one-retry bound;
  two remaining candidates deferred at shared-budget preflight. The task-level report
  retained the child-process reason for both bug cases.

The retry was reserved for both possible calls before the first dispatch, made at most one
retry, settled only calls made, and cancelled unused reservations. D-037(c) is a separately
owned runner-design problem and was not addressed.

Accuracy, finding precision, recall, and silence precision are **not estimated** for either
run. Abstention is neither TP nor FN, and zero surfaces do not establish precision.

## Wave 5 F shadow signal and counterfactual

F's preregistered first slice is true only when `git blame` maps the current anchor line to
a commit within 50 commits of `HEAD` whose full commit message contains the word `revert`
or `hotfix`. The ledger row is `attest.history-signal.v1`, records `priced=false`, and is
excluded from purchases, product wealth, surfaced rows, and publication.

Evidence artifact:
[`result.json`](acceptance/evidence/2026-09-01-wave5-history-counterfactual/result.json)

- artifact SHA-256:
  `f5743ce30c0d3cf2e3eba0d2daec4bd3afd7b4ea0384827f138ae0702ada256d`;
- probe code SHA: `44801f9b9de77a07190b6c0e611ea7a698692ffa`;
- all 9 historical-V1 receipt pairs, both roles: 18 cases;
- 26 candidates total: 25 historical-bug-replay, 1 developer-fix-control;
- **F trigger rate: 0/26 = 0.0**;
- reserved ceiling $2.70; actual spend $1.576220.

Pure offline cap replay:

| Hypothetical F | Historical bug replay crossings | Developer-fix control crossings |
|---:|---|---|
| 1.25 | none | none |
| 1.5 | none | none |
| 2 | none | none |
| 3 | none | none |

The required full candidate lists are therefore empty at all four caps: there is no claim,
anchor, failure scenario, or S×T×F trace to list. The control group also has no false
trigger at any cap. This is evidence that this exact F definition was too sparse on this
one sample, not evidence that F is safe to broaden or price and not evidence of recall.

Call-graph reachability and test-blind-spot slices were not implemented and are in backlog.

## Wave 6 C-01

Implementation `e955f29` creates only `src/attest/certification/`:

- frozen versioned task, base-policy, subject, execution-run, receipt, accepted-receipt,
  anchor, and certified-finding values;
- task v1, policy v1, and strict regression receipt v2;
- pure policy and receipt validators with typed exhaustive rejection codes;
- validator-only `AcceptedReceipt` construction and accepted-receipt-only
  `CertifiedFinding` construction;
- an unimplemented C-05 selection Protocol;
- no re-export wall and no imports from review, benchmark, Core, provider, subprocess,
  ledger, CLI, or GitHub.

RED was the expected `ModuleNotFoundError: No module named 'attest.certification'`.
After GREEN, 59 focused tests pass. Informational focused coverage is 100% for executable
types/policy/validator logic; the only four uncovered statements are the deliberately
unimplemented selection Protocol. Field-by-field mutation guards cover every C-01 binding
and unknown versions/classes. Adjacent gate/executor tests pass. The package has no caller,
so this is the C-01 portion of `G-CERT-001`, not C-02 and not the full publication invariant.

## Gate record before final integration

Commands at every successful wave Gate:

```text
python -m pytest --cov=src/attest --cov-report=term-missing
python -m coverage report --include='src/attest/benchmark/*' --fail-under=0
python -m coverage report --include='src/attest/core/*' --fail-under=0
python -m ruff check .
python -m mypy src/attest
python -m pip check
git diff --check
test -z "$(git status --porcelain=v1)"
```

Verbatim terminal summaries:

```text
baseline 53f4641 (pre-amendment)
1543 passed
total coverage 90.13%; core coverage 99.77%
real 736.62
ruff PASS; mypy PASS; pip check PASS; diff/clean PASS

Wave 1 / Wave 2 0cdf56c
1543 passed
product coverage 92.00%; benchmark 89%; core 99%
real 729.77
All checks passed!
Success: no issues found in 50 source files
No broken requirements found.
CLEAN_TREE_OK

Wave 3 e25091c
1550 passed
product coverage 92%; benchmark 89%; core 99%
real 731.49
All checks passed!
Success: no issues found in 51 source files
No broken requirements found.
CLEAN_TREE_OK

Wave 4 first attempt (reproduced fixture failure)
1550 passed, 3 errors in 603.94s (0:10:03)
ERROR tests/benchmark/test_m01_offline_measurement_probe.py (3 setup users)
cause: the current path correctly used one bounded retry (6 generator calls), while the
      acceptance probe still hard-coded the earlier 5-call guard; baseline remained 5
real 604.49

Wave 4 recovery ff258cd (fixed in under four minutes)
1553 passed in 736.04s (0:12:16)
Required test coverage of 90.0% reached. Total coverage: 92.41%
benchmark 89%; core 99%
All checks passed!
Success: no issues found in 51 source files
No broken requirements found.
real 738.25

Wave 5 638ae65
1556 passed in 762.11s (0:12:42)
Required test coverage of 90.0% reached. Total coverage: 92.39%
benchmark 89%; core 99%
All checks passed!
Success: no issues found in 52 source files
No broken requirements found.
CLEAN_TREE_OK
real 762.63

Wave 6 e955f29
1615 passed in 746.32s (0:12:26)
Required test coverage of 90.0% reached. Total coverage: 92.39%
benchmark 89%; core 99%
All checks passed!
Success: no issues found in 57 source files
No broken requirements found.
CLEAN_TREE_OK
real 746.89
```

The Wave 4 failure was not relabelled as a pass. Its reproduced fixture contract was fixed
within the 20-minute limit and the full Gate was rerun once at `ff258cd`.

## Final dual-Python integration Gate

Exact gated SHA: `ffd0dd2a5e40e8452e4c407612e624fb93075417`.

Toolchain lock SHA-256:
`76908dd8dc527b59e95ab856cf67656946a4c1bf8eecbb0d95430a2161341c11`.
Python 3.11.5 used a fresh environment under `/private/tmp`; Python 3.12.8 used the
branch's existing locked `.venv`. The interpreters ran serially and each invoked full
pytest exactly once.

```text
Python 3.11.5
No broken requirements found.
Required test coverage of 90.0% reached. Total coverage: 92.39%
1615 passed in 765.23s (0:12:45)
real 766.23
benchmark coverage 89% (informational)
core coverage 99% (informational)
All checks passed!
Success: no issues found in 57 source files
No broken requirements found.
CLEAN_TREE_OK
ffd0dd2a5e40e8452e4c407612e624fb93075417
76908dd8dc527b59e95ab856cf67656946a4c1bf8eecbb0d95430a2161341c11

Python 3.12.8
No broken requirements found.
Required test coverage of 90.0% reached. Total coverage: 92.39%
1615 passed in 742.35s (0:12:22)
real 742.92
benchmark coverage 89% (informational)
core coverage 99% (informational)
All checks passed!
Success: no issues found in 57 source files
No broken requirements found.
CLEAN_TREE_OK
ffd0dd2a5e40e8452e4c407612e624fb93075417
76908dd8dc527b59e95ab856cf67656946a4c1bf8eecbb0d95430a2161341c11
```

Both interpreters passed pytest, the unchanged 90% product threshold, informational
benchmark/Core reports, Ruff 0.16.5, Mypy 2.3.1, `pip check`, `git diff --check`, and the
clean-tree assertion. The report-seal commit after this Gate changes only this report and
does not alter code, normative policy, or Gate inputs.

## Public-number boundary

The only honest inherited public baseline remains:

- 9/20 receipt-validated;
- controls 4/4 silent;
- bug attempts 5/5 DEFER, 0/5 surfaced;
- precision and recall not estimated.

This overnight run creates no new public accuracy, precision, recall, or silence-precision
number. The Wave 3/4 operational subset and Wave 5 one-observation counterfactual are
configuration- and SHA-bound engineering evidence only. “Precision held,” “recall = 0,”
or any equivalent denominator claim is not supported.

## Backlog added

1. `src/attest/review/executor.py:46` — D-037(c) remains reproducible, but runner
   process/resource policy and compatibility design are explicitly outside this scope and
   require a separate owner decision. No prompt or runner workaround is retained.
2. `src/attest/review/history.py:1` — call-graph reachability and test-blind-spot F slices
   need independent preregistration and an owner-scoped work order before implementation or
   measurement.

D-053 separately records alpha relaxation as a pending owner decision; no relaxation path
or factory-statistics change exists.

## Spend

| Run | Predeclared bound | Actual |
|---|---:|---:|
| Wave 3, 4-case operational observation | $1.50 reserved | $0.330626 |
| Wave 4, same 4-case bounded rerun | $1.50 reserved | $0.433304 |
| Wave 5, all-nine-pair/18-case F counterfactual | $2.70 reserved | $1.576220 |
| **overnight total** | — | **$2.340150** |

`DEVSPEND.md` now records 30 entries and **$5.933150/$10.00** total. No call was repeated
for an all-DEFER debugging loop, and no current V2 scoring execution was claimed.

## Decisions and next boundary

Added D-050 through D-055: coverage authority, measured proposer headroom, bounded schema
recovery, pending alpha policy, unpriced F observation, and C-01's pure domain.

C-01 is complete. C-02 and V-01 are the first unblocked work orders, but neither is started
or authorized by this handoff. There is no named blocker to the completed overnight scope.

## Follow-on V-funnel work — Wave 1 candidate autopsy (2026-09-01)

This is an append-only follow-up to the overnight report. Baseline SHA was
`2ae5fcf90af73bf618a82899761c03971caea6b7`; `git fetch origin --prune` left
`origin/main` at `1f6f73eb72f5ed45b129c4d7ff937cc23b409e5c`, and the authoritative worktree
was clean. This wave made no model/API call and spent $0.

The four Wave 4 schema-valid reproduction responses can be mapped to candidates from the
durable provider-call order. In `case-3efff8123ae7`, candidate 0 produced a valid body;
candidate 1 exhausted both schema attempts at `max_tokens`; candidate 2 produced a valid
body on its second attempt; candidates 3 and 4 reached no provider call. In
`case-81039ffa0c1e`, both candidates produced valid bodies. Thus the four bodies belong to
`01dd26db09`, `5edf557329`, `ffe9efc79f`, and `45896a87b1`.

| Candidate | Candidate and generated-test summary | Retained evidence class / DEFER | Key retained execution line | Does the process-policy attribution hold? |
|---|---|---|---|---|
| `01dd26db09` (`black.py:956`) | Claim: lost bracket-depth matching breaks nested `for ... in`; body imports `black`, formats the nested-for snippet twice, checks idempotence, then calls `black.assert_equivalent`. Reproduction response: `end_turn`, 1,444 output tokens. | `indeterminate`; `head run 1/3 deferred: reproduction attempted to create a child process`. | The raw pytest stdout/stderr was not retained after the live workspace cleanup. The durable case reason contains the quoted head-run line. | **Yes, individually established.** It is candidate 0, so the case's retained first-DEFER reason binds to it. The head run started but was rejected before head/base classification. |
| `5edf557329` (`black.py:983`) | Claim: lost lambda-depth matching mishandles inner colons; body calls `black.format_str` on a nested-lambda/slice expression and compares exact expected spacing. First generation stopped at `max_tokens`; the one bounded retry returned `end_turn`, 1,633 output tokens and a valid body. | **Not retained per candidate.** It is known to have DEFERRED, but neither its evidence class nor its reason survived in the case artifact. | No per-candidate stdout/stderr or result line survives; only the case-level first reason and the fact that all five candidates deferred were retained. | **Unproven.** It may have hit the same guard, but the durable evidence cannot distinguish that from unfaithful, not-reproduced, or another DEFER. |
| `ffe9efc79f` (`black.py:397`) | Claim: `--config` no longer rejects a missing file cleanly; body uses Click's in-process `CliRunner` on `black.main` with one temporary source file and checks exit code 2. Reproduction response: `end_turn`, 1,429 output tokens. | `indeterminate`; `head run 1/3 deferred: reproduction attempted to create a child process`. | The raw pytest stdout/stderr was not retained. The durable case reason contains the quoted head-run line. | **Yes, individually established.** It is candidate 0, so the retained first-DEFER reason binds to it. |
| `45896a87b1` (`tests/test_black.py:1645`) | Claim: deleting the invalid-config regression test masks the behavior change; body uses `CliRunner` with a nonexistent config and `-c`, checking exit code 2 and an error message. Reproduction response: `end_turn`, 1,095 output tokens. | **Not retained per candidate.** The case artifact proves that both candidates deferred but stores only candidate 0's reason. | No per-candidate stdout/stderr or result line survives. | **Unproven.** The aggregate `(2 candidates)` suffix is a DEFER count, not proof that both reasons were the same. |

Therefore the previous statement that all four schema-valid reproductions hit the unchanged
child-process guard was stronger than the durable evidence. The attribution is individually
established for **2/4**, unproven for **2/4**; none reached a retained head-fail/base-pass
receipt. The missing per-candidate execution result and stdout/stderr are a measurement-
retention gap, not evidence for any of the alternative failure classes.

## Follow-on V-funnel work — evidence retention and process diagnosis (2026-09-01)

This append-only follow-up started from clean SHA
`017a036217de314e4fe8a2f57bcc9f011b1207c3` after `git fetch origin --prune`.
`origin/main` remained `1f6f73eb72f5ed45b129c4d7ff937cc23b409e5c`. No paid model call was
made and no remote write was performed.

### Wave 1 — per-candidate durable verification evidence

Commit `3ff4c7c3312df85743998990941a1a6ad722b437` makes every verification row
retain its own evidence class, DEFER reason, bounded stdout/stderr fragments, and every
head/base repeat as a separate structured result. Case results now project every row as
`candidate_evidence`; duplicate finding identities fail closed. Each stdout and stderr
fragment is limited to 2,000 characters and continues through the existing ledger secret
filter.

The regression case contains two independently verified candidates, each with head runs
1/2/3 and base runs 1/2/3. The before/after observation is:

| Multi-candidate case | Independently addressable evidence records |
|---|---:|
| Before | 1 case-level first-DEFER reason |
| After | 2 candidate records for 2 candidates |

This does not retroactively reconstruct old Wave 4 workspaces. It closes the retention gap
for subsequent runs; old claims remain limited to their old durable artifacts.

### Wave 2 — exact child-process classification chain

Commit `5a684fbee761a14f3b69bb942efeada2e9ffaf8d` records the first process
audit event, its target, and a bounded filename/line/function stack in stderr evidence. It
does not alter the event set, `RLIMIT_NPROC`, the DEFER condition, or any process/resource
policy.

Both retained test bodies were replayed locally with the corpus Python 3.8.3 environment
and their exact historical base/head SHAs. No provider was called.

| Candidate | Test form | Exact first process event | Actual trigger owner | Repeat result |
|---|---|---|---|---|
| `01dd26db09` | direct `black.format_str` | `subprocess.Popen`, target `uname` | runner bootstrap: old pytest imports `py`, then `uuid`, then `platform.uname()` invokes `uname -p` | configured 3; head 1 DEFER, head 2/3 not run, base 0 |
| `ffe9efc79f` | in-process Click `CliRunner` | `subprocess.Popen`, target `uname` | same runner bootstrap, before CliRunner/Black main execution | configured 3; head 1 DEFER, head 2/3 not run, base 0 |

The durable stack for both is:

```text
_pytest/_py/path.py:31 -> uuid.py:57 -> platform.py:891:system
-> platform.py:857:uname -> platform.py:613:_syscmd_uname
-> subprocess.py:411:check_output -> subprocess.Popen('uname', ['uname', '-p'])
```

The guard records the event in generated `sitecustomize` at
`src/attest/review/executor.py:371-398`; after pytest exits, `execute_repro` sees the marker
at line 918 and returns `reproduction attempted to create a child process`. Therefore the
object classified for both candidates is **the reproduction runner's pytest dependency
startup**, not behavior of the reviewed Black code.

Additional execution evidence remains visible rather than being conflated with the guard:
`01dd26db09` ran far enough to produce `black.py:905: KeyError` (exit 1), while
`ffe9efc79f` encountered `ModuleNotFoundError: No module named '_black_version'` during
collection (exit 2). In both cases the earlier process marker controls the final
`indeterminate` DEFER.

Repeat semantics are confirmed by both replay and code at
`src/attest/review/executor.py:1126-1132`: a DEFER on head run 1 returns immediately.
Thus one infrastructure classification can deny a candidate without running head repeats
2/3 or any base repeat. No policy was changed in this wave.

### Wave 3 — independent reproduction output headroom

Commit `3ab116ae9c25c1e23dff7ba2d6cbaf5649cacd65` and D-056 rename the
reproduction-only cap to `REPRO_MAX_OUTPUT_TOKENS` and increase it from 2,000 to 3,000.
Both bounded-retry reservations and the provider hard cap use 3,000. The proposer remains
independent at 2,400; retry count, schema, prompt, execution policy, gate, prices, and
factory statistics are unchanged.

| Reproduction generation | Before | After |
|---|---:|---:|
| Configured output cap | 2,000 | 3,000 |
| Observed `max_tokens` rate | 3/7 (42.9%) | **not measured** |

The post-change rate is deliberately not inferred: this work order forbade paid evaluation,
so there is no post-change sample. No DEVSPEND row was added; the ledger remains 30 entries
and **$5.933150/$10.00**.

### Recommendation only — not implemented

Before another paid corpus run, the owner should decide the runner/guard attribution
boundary exposed above. The next design must preserve kernel containment while preventing
trusted pytest bootstrap (`platform.uname` in this exact old environment) from being
misreported as behavior of reviewed code. This is a runner security-policy decision, not a
generation-prompt problem. After that decision, one preregistered paid rerun can measure the
3,000-token cap's actual truncation rate and downstream receipt yield. No such policy or
rerun is part of this task.

Accuracy, precision, recall, and silence precision remain **not estimated**. This task ran
no new product evaluation and produced no new certification receipt or public accuracy
number.

### Commits, size, and Gate evidence

Final implementation/test SHA before this report-only seal:
`e0f2db029128ca1b98597e68e370aea8c24d78f0`.

Implementation diff from `017a036` through `e0f2db0`:

```text
DECISIONS.md                   | 20 +++++++++++++
src/attest/benchmark/api.py    | 11 +++++++
src/attest/benchmark/runner.py | 33 +++++++++++++++++++++
src/attest/review/executor.py  | 67 ++++++++++++++++++++++++++++++++++++++----
src/attest/review/ledger.py    |  2 ++
tests/benchmark/test_api.py    | 63 +++++++++++++++++++++++++++++++++++++++
tests/test_executor.py         | 27 +++++++++++++++--
7 files changed, 216 insertions(+), 7 deletions(-)
```

Net implementation change: **+209 lines**. Wave commit changes were +150/-0,
+31/-2, +27/-5, and the bounded-fragment self-review guard +8/-0. No new atomic JSON,
digest, matcher, aggregate, or credential-filter implementation was added; the existing
ledger credential filter remains the single authority.

Including this 156-line append-only report, the complete task diff is 8 files changed,
372 insertions, 7 deletions, net **+365 lines**.

Per-wave full Gates, each run from its clean commit:

| Gate | pytest | Wall clock | Ruff | Mypy |
|---|---|---:|---|---|
| Wave 1 (`3ff4c7c`) | all passed | 713.30s | passed | 57 source files, no issues |
| Wave 2 (`5a684fb`) | all passed | 714.67s | passed | 57 source files, no issues |
| Wave 3 (`3ab116a`) | all passed | 714.84s | passed | 57 source files, no issues |

One pre-commit Wave 1 probe was rejected by the repository's existing clean-tree guard
(1 failure/3 setup errors); it is not counted as a Gate. The identical suite passed after
the implementation commit was clean.

Final clean integration Gate at `e0f2db0`:

```text
1617 tests collected
................................................................ [100%]
real 719.08
user 316.01
sys 206.45
All checks passed!
Success: no issues found in 57 source files
No broken requirements found.
CLEAN_TREE_OK
e0f2db029128ca1b98597e68e370aea8c24d78f0
```

One bounded D-049/D-039 self-review found only that the 2,000-character evidence bound
lacked a direct guard test; `e0f2db0` added it. Final review severity is **P0=0/P1=0**.
No second self-review loop ran. The report-seal commit after this Gate changes only this
append-only handoff and does not alter code, tests, decisions, or Gate inputs.
