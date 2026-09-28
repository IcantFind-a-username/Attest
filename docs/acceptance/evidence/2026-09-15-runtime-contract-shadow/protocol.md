# D-258: owner-approved runtime contract shadow prototype

Baseline: 9458278479447e668e7b3e7e51bade35e5c83831.
Branch: feature/runtime-contract-shadow. API budget: $0. Remote writes: none.
The owner approved the preceding five-step proposal with “做”.
Dependency: D-257 gate e540e0d (2,526 tests, 93.42% boundary coverage), verified on disk.

## Scope and ownership

Instrumentation/measurement only: no certification rule, receipt, default or publication
change. Root owns review/contract_runtime.py, review/_contract_observer.py,
scripts/corpus/runtime_contract_{cases,shadow}.py, tests/test_runtime_contract.py and
this task's evidence/report/status entries. One independent reviewer owns only its report.
The collector runs through execute_repro(tree_target=...), Controller and ContainerAdapter;
no new executor or security policy. Never label the same-process observer tamper-proof.

## Frozen acceptance population and order

1. All seven D-257 context scenarios from context_cases.CASES, plus its positional-row
   callback variant: reasonable raw implementation changes with substituted test callables.
2. D-255 legal_contract; a new ancestor autouse fixture that only clears a cache; a new
   method test with fixture-supplied receiver state: legitimate regression positives.
3. D-255 unreachable_assert and receiver_mutated: original test does not establish the
   proposed out-of-context regression. A head-side changed expected value: withdrawn contract.
4. An instrument-name collision: must refuse instrumentation, not replace the binding.
5. The three prior experimental gains, selected only as development regressions:
   packaging-boundary-08, packaging-guard_raise-06, urllib3-none_guard-18, at the already
   approved .attest/corpora/mutations-v1-recall commits. No truth enters discovery.

This is a development population, not a held-out or independent FPR estimate. Keep every
case, including zero discovered sites, collection/setup failures, skips and unsupported
expectations. Do not retry based on behavioural outcomes.

## Selection, execution, and interpretation

Discover changed definitions from repository/diff and use the existing AST index to find
calls in test assertions. First supported subset: one direct equality assertion, with a
Python function or bound method call on its left. Literal/structural bounded snapshots only;
unknown input/expected/receiver representations refuse. Unsupported raises/helpers remain
visible discovery limitations. Sort by file/node/line; at most eight sites per revision pair,
chosen before any execution. No model/probe hints or mutation locations in this step.

For each selected site, run the same original node and an instrumented copy, on base and
head, in four fresh runs using the same container image. Preserve original fixture/setup
and module code in both copies. Declare and hash the instrumentation overlay separately
from revision identity. Preserve original/overlay test bytes and protocol records.

The observer records actual callable coordinates, receiver state, concrete arguments,
returned value, expected value and equality result. The controller checks source/site and
run identities, observed call identity, identical input/receiver/expected values, source
contract retained at head, original-vs-instrumented outcome agreement, and missing/duplicate
records. Binding observations are shadow data only; receipt eligibility is always false.
Original base must pass and head fail for an observed regression-shaped pair; a passing
head, changed expectation, substituted callee or unreachable assertion does not qualify.
Missing/forged/inconsistent records cannot be silently accepted by the shadow interpreter.
Same-process artifact forgery remains a promotion blocker even if ordinary consistency
checks pass. Neither matching source locations nor test PASS/FAIL alone establishes truth.

## Deliverables and gates

Frozen driver committed before measurement; one bounded review, only reproduced findings
fixed; relevant tests, one final full pytest/ruff/mypy gate and separate peripheral coverage.
Report per-case binding recovery, losses, abstention/failure, overlay effects, source/driver
SHA and digests. Seven-commit/three-hour working limit; stop at the measurement, not further
feature work. No promotion, paid forty, release, new CLI or replacement contract algorithm.

## Pre-outcome environment repair and review amendment

The first smoke used relative mount paths, so Docker never started; those observations
are invalid infrastructure runs, not controls passing. The driver now resolves its paths.
A preliminary packaging run could not collect any test because `pretend` was absent.
Before any behavioural measurement on those nodes, derive a test image from the base's
flat `[dependency-groups].test` strings through the existing requirements/image builder.
Keep the image-only requirements overlay separate and hashed; run original and observed
base/head against the same resulting image. No dependency guessed from an outcome, no
production bootstrap/backend change, no test assertion or selection change. If the group
is complex, collection still fails or parameterized nodes cannot be bound, retain that
failure rather than broadening the subset. Missing dependency repairs are not gate-hunting.

The one independent review reproduced numeric-type conflation and null binding fields.
The final recorder uses typed snapshots and the host validates their grammar. Version the
incompatible shadow packet as v2; v1 pilot records remain untouched and are not reclassified
as final evidence. Review controls are reported separately from the frozen 15-case suite.
The protocol's malformed-record refusal covers invalid structure/identity, not a guarantee
against a project forging a well-formed same-process record; that trust boundary remains open.
