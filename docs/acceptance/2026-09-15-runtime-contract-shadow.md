# Runtime contract observations in original test context — D-258

## Outcome

The shadow prototype observes consistent concrete bindings in all three frozen synthetic
positive cases, including a cache-clearing autouse fixture and a fixture-built receiver.
All twelve development controls abstain. It restores **no product certifications**:
the three historical gain cases all remain unsupported by this prototype.

This establishes a limited mechanism, not product recall, precision, a false-positive rate,
or readiness for 1.0.0. No receipt is issued or verified from these observations. The
same-process recorder is untrusted; a well-formed forged packet can defeat its consistency
checks. The existing experimental context refusals and default v5.1 remain unchanged.

## Scope and versions

- Owner-directed shadow experiment; baseline `9458278479447e668e7b3e7e51bade35e5c83831`.
- Branch: `feature/runtime-contract-shadow`.
- Frozen cases/protocol: `108743b`; initial implementation: `89723b0`.
- Final code, cases and measurement driver: `47dd7b5` (full SHA and file digests in the
  [manifest](evidence/2026-09-15-runtime-contract-shadow/manifest.json)).
- Dependencies: D-257's local-context repair and retained gate evidence. This experiment
  advances no mainline release gate and changes no certification or isolation contract.
- API/model spend: **$0.00**. No paid provider calls, remote writes, push, PR or release.

The only runtime consumer is the committed measurement script. The production review,
kernel, selection strategy and presentation do not import or consume these observations.

## What executes and what is checked

Discovery uses the repository diff and existing AST index. The supported shape is one
direct equality assertion with a Python function/method call on the left. A unique method
name can nominate a fixture-based call, but the runtime callable must match the indexed
changed definition. Selection is sorted and capped at eight sites before execution.

For each supported source site, the existing `execute_repro(tree_target=...)`, Controller
and `linux-container-v1` execute four fresh trees: original base, instrumented base,
original head and instrumented head. All retain their repository fixtures, hooks and
module code. The original/overlay test digests, observer digest, exact source revisions,
request/result records, JUnit and bounded output are retained. The overlay is explicitly
separate from the original revision identity.

The recorder captures callable metadata, passed arguments, receiver dictionary, returned
value and the assertion's expected value. The host validates typed snapshot shapes,
source/site identities, matching concrete bindings, one completed node, a retained head
assertion, common execution identity, and original-versus-overlay outcome agreement.
Only a base-pass/head-fail pair can be `binding_observed`; every result carries
`receipt_eligible=false`. This label supplies no publication authority.

## Final container measurements

The final driver was committed before both runs. Raw case rows are in
[final-synthetic.json](evidence/2026-09-15-runtime-contract-shadow/final-synthetic.json)
and [final-gains.json](evidence/2026-09-15-runtime-contract-shadow/final-gains.json).

| Frozen population | Distinct development cases | Shadow result |
|---|---:|---|
| Legal contract, cache-clearing fixture, fixture receiver | 3 | 3 binding observations |
| Fixture/hook/import/decorator substitution controls | 8 | 8 actual-callee mismatches |
| Unreachable assertion | 1 | Assertion never observed |
| Receiver already mutated by the real test | 1 | No base-pass/head-fail assertion |
| Withdrawn expectation | 1 | Refused before execution |
| Observer-name collision | 1 | Refused before execution |
| Three historical contract gains | 3 | 0 supported binding observations |

The 15 synthetic cases produced 52 executions; the historical set produced four more.
Executions, parameter rows and observations are not independent defects or controls.
The twelve controls were used for development and are related synthetic scenarios. Their
abstentions do not establish general zero false positives; two never entered execution.
No product precision denominator exists because this experiment cannot publish.

Historical cases, individually:

- **packaging-boundary-08:** the original and instrumented test each collect five parameter
  rows. Both base runs pass all five; both head runs fail three and pass two. The current
  one-node binding contract refuses the aggregate. No failing parameter row was selected
  after observing the outcome, and no parameter-level binding support was added.
- **packaging-guard_raise-06:** no supported direct equality site was discovered for the
  changed definition. No execution was attempted. The existing raises-oriented contract
  is outside this prototype's supported shape.
- **urllib3-none_guard-18:** no supported direct equality site was discovered for the
  changed method. No execution was attempted; indirect/helper association remains open.

Discovery records zero-site cases. Its bounded refusal list also includes unrelated
unsupported assertions and can omit target-specific detail; omitted counts are retained.
Consequently, an empty site list means this reader found no supported site, not that the
repository contains no contract. The historical three are development regressions, not
a held-out evaluation, and this run supplies no new forty-case total.

## Independent review and repair

One [independent review](evidence/2026-09-15-runtime-contract-shadow/independent-review.md)
reproduced two P2 defects in shadow interpretation:

1. Python equality collapsed `True`, `1` and `1.0`, incorrectly accepting changed inputs
   as identical in a behavior-equivalent implementation control.
2. Present-but-null argument and binding fields passed the packet presence checks.

Formal regression tests produced three failures (two numeric controls and one malformed
packet). Version 2 snapshots now tag primitive and container kinds; the host validates
their bounded grammar and compares canonical bytes. The 16 runtime tests and 48 combined
focused tests pass. These review cases are separate from the frozen 15-case population.
The implementer verified the fixes; no second independent review is claimed.

## Pilot history and environment

Pilot records are retained unchanged, with final evidence distinguished in the manifest.

- `smoke-1`: invalid infrastructure run. Relative Docker mount paths prevented execution;
  its abstentions are not successful controls. The driver now resolves paths absolutely.
- `smoke-2` and `dev-all`: development diagnostics using the earlier untyped v1 packet;
  superseded for final measurement, not overwritten or relabeled.
- `dev-gains`: packaging could not collect because `pretend` was absent. This is an
  environment failure, not a negative semantic result.
- `dev-gains-deps`: diagnostic after the declared test-dependency repair and v2 changes;
  final measurement repeats the cases from the committed final driver.

Before obtaining any packaging behavioral outcomes, the driver constructed a shared test
image using the base tree's flat `dependency-groups.test` declaration through the existing
requirements/image builder. Declaration and image-input digests are recorded. This adds
no assertion, changes no test selection, and does not modify production image building.
Complex dependency groups remain unsupported. The same image serves all four executions.

The host gate explicitly sets `PYTHONPATH` to this checkout's `src`: the existing hidden
editable-install path file otherwise prevents subprocess imports on this machine.
`DOCKER_CONFIG` uses the repository-local client configuration, avoiding the previously
observed desktop credential-helper hang. This is not a clean-install or release test.

## Gate

Final code gate results and exact command/environment are recorded in
[gate-environment.json](evidence/2026-09-15-runtime-contract-shadow/gate-environment.json),
[gate-result.json](evidence/2026-09-15-runtime-contract-shadow/gate-result.json) and
[gate.log](evidence/2026-09-15-runtime-contract-shadow/gate.log).
Final code `47dd7b50bdbf1ea541522cb91d025e6f451e84ea`: **2,542 tests passed, zero
failures/skips**, exit 0; certification/execution coverage **93.42%**. The single full
run took 2,225.70 seconds on Python 3.12.2/macOS arm64 with Docker 27.5.1. Ruff and
Mypy pass (100 source files); source/test/driver bytes remained unchanged during the gate.
[Separate coverage observations](evidence/2026-09-15-runtime-contract-shadow/coverage-sections.log)
carry no peripheral threshold. The final documentation commit does not change gated code.
This is one supported-Python work-order gate, not the two-version release integration gate.

## Remaining boundary and next decision

The recorder shares a process with the code being examined. Callable metadata and a source
file hash are not authenticated proof of the code that executed. Passed arguments and a
receiver dictionary omit hidden globals, defaults, imported state and transitive effects.
AST rewriting may alter introspection or timing; equal outcomes catch some interference
but do not prove semantic equivalence. Valid packet grammar does not solve forgery.

**Keep this prototype in shadow.** A bounded next decision package should specify an exact
collected parameter-node/assertion association and the threat model for obtaining trustworthy
runtime evidence before any kernel integration. Predeclare fresh controls and held-out
repositories before evaluating a promoted design. Do not buy a forty-case rerun to answer
this binding question; model search quality is a different experiment.

Rollback is removal/reversion of the isolated shadow modules and measurement driver. No
product receipt migration, default change or publication rollback is needed. The prior
comment-format improvements remain intact and were not changed in this task.
