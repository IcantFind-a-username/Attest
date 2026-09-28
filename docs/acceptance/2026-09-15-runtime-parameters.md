# Parameter-node binding in runtime shadow observations — D-259

## Result

The previously unsupported `packaging-boundary-08` now has a consistent runtime binding
observation for three of its five parameter rows. The other two rows pass on both revisions.
All five are retained and this counts as **one development case**, not three defects.
The other two historical cases remain outside the supported assertion shape.

This restores **one shadow binding, no product certification**. The production pipeline,
default v5.1, kernel and D-257 context refusals are unchanged. The same-process observer,
pytest marker and JUnit remain forgeable; no authentication or semantic proof is claimed.
There is no new forty-case recall estimate, held-out result or 1.0 release conclusion.

## Scope, versions and contract

- Owner-directed continuation; baseline `f6900c4e410352b8536f13021a94fad167f4a0b2`.
- Branch `fix/runtime-parameter-binding`; frozen cases/protocol `652ff89`, implementation
  `b6a6656`, final code and driver `a4efbca` (full identities/digests in the manifest).
- Reuse the D-258 driver, original test nodes, AST index, fixture builders, Controller and
  `linux-container-v1`; no new executor, product CLI, model call or certificate contract.
- Development model/API cost **$0.00**; no push, PR, remote write or release.

The recorder adds pytest's current call-stage node to a v3 packet. The host pairs complete
identity sets, requires exactly one event per node, checks per-node original/overlay
outcomes and compares typed inputs, receiver state and expectations. Order is not identity.
All rows execute in the original test invocation; no failed-row selection or outcome-driven
rerun occurs. Missing, duplicate, unknown, skipped, errored or changed populations refuse.
The 32-row admission limit is retained. Larger node reports state their omitted count;
raw JUnit remains in the run record. No truncated population can supply a binding.

Single-node diagnostics remain available. Historical v2 evidence is untouched and is not
reclassified by v3. The only consumer is the measurement script; nothing in production
uses these observations to authorize a finding. `receipt_eligible` remains false.

## Frozen container measurements

See [synthetic rows](evidence/2026-09-15-runtime-parameters/final-synthetic.json) and
[historical rows](evidence/2026-09-15-runtime-parameters/final-gains.json).

| Population | Scenarios/cases | Result |
|---|---:|---|
| D-258 synthetic positives | 3 | 3 binding observations, retained |
| D-258 expected-refusal scenarios | 12 | All still refuse |
| Parameter regression and order variant | 2 | Both observe one broken row and retain the passing sibling |
| Swapped inputs and updated expectation | 2 | No node has a bound regression |
| Changed IDs and skipped head | 2 | Whole population refuses; all node reports retained |
| Historical gain cases | 3 | 1 binding observation, 2 unsupported |

The synthetic set is 21 scenarios: five positives and sixteen expected refusals, with
76 executions. The historical set adds four executions. These are related development
scenarios, not independent statistical samples. Some refusal controls contain real code
changes whose test context is no longer comparable; they are not an FPR calibration set.
Repeated rows, executions and order variants must not inflate independent defect counts.

**Historical case attribution:**

- `packaging-boundary-08`: both original and instrumented base runs pass all five rows;
  both head runs fail three and pass two. D-258 recorded the same aggregate outcomes but
  refused the multi-node population. D-259 records and aligns each node and its binding,
  recovering one case without adding a probe, changing an input or selecting a failing row.
- `packaging-guard_raise-06` and `urllib3-none_guard-18`: still zero supported direct equality
  sites; neither executes. Raises/helper association was not expanded.

The prior 15 synthetic verdicts have no gained or lost cases. The historical comparison
gains only `packaging-boundary-08` as a shadow observation and loses none. This does not
reverse D-257's withdrawal of the product certifications.

## Tests and independent review

The initial focused test fails on both parameter positives under v2. After the change,
the node-based comparison accepts both, including reversed execution order with stable IDs.
Tests also reject missing/duplicate/unknown/exchanged events, duplicate JUnit identities and
per-node outcome swaps that preserve the aggregate outcome; event-array reordering is safe.

One [independent review](evidence/2026-09-15-runtime-parameters/independent-review.md)
reproduced a P2 reporting omission: changed-ID and skipped populations refused correctly,
but their verdict summaries omitted node identities. Two formal REDs pin the omission.
The final fix retains a bounded per-run census before admission; skips still refuse.
The implementer verified the fix; no second independent review is claimed.

The final focused run passes **61 tests** (29 runtime tests plus 32 adjacent tests).
The exact full-gate command, environment, result and logs are retained under
[the evidence manifest](evidence/2026-09-15-runtime-parameters/manifest.json).
Final code `a4efbca51ab73c3536f3170c3a44af43c37ca529`: **2,555 tests passed, zero
failures/skips**, exit 0; certification/execution coverage **93.42%**. Ruff and Mypy
pass (100 source files). The single full run took 2,310.60 seconds on Python 3.12.2,
macOS arm64 and Docker 27.5.1. Source/tests/driver stayed frozen throughout.
[Separate coverage observations](evidence/2026-09-15-runtime-parameters/coverage-sections.log)
have no peripheral threshold. This is a one-Python work-order gate, not a release gate.
The existing local editable-install issue is handled by explicit `PYTHONPATH=$PWD/src`;
Docker uses the repository-local client configuration. No clean-install claim is made.
The experiment began September 15 and the gate finished September 16 in Singapore;
the artifact directory retains the start date and manifests record UTC timestamps.

## Limits and next decision

Node labels improve consistency, not trust. A project can forge its environment marker,
in-process event packet or JUnit; matching them is not independent corroboration. Hidden
globals/defaults, transitive state, instrumentation effects and semantic correctness remain
unproved. The original/overlay parity checks detect only certain interference effects.

Keep v3 shadow-only. The next useful decision package is a concrete trusted-observation
contract and threat model, including a reproduction of well-formed same-process forgery
and how a proposed verifier would reject it. Do not promote these records or buy another
model search run to compensate for this evidence-boundary gap. Any eventual product claim
needs separately frozen, previously unused semantic evaluation cases and controls.

Rollback: revert the isolated parameter-binding commits; keep both v2 and v3 artifacts as
historical evidence. No receipt migration or production rollback is needed. The earlier
readable-comment changes remain intact.
