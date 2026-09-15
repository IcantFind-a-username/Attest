# Free product-path smoke succeeds on the current host

E-02 preparation, D-266; baseline `3d91427`, measured code/protocol commit `19bb9c4`,
branch `chore/product-path-readiness`. The historical Keras runtime failure remains open;
this distinct diagnostic checks whether the existing product path still executes.

| Selected development fixture | Verification rows | Actual differential probes | Certified / red publication selections |
|---|---:|---:|---:|
| itsdangerous-boundary-07--forward | 1 | 1 | 1 / 1 |
| mahmoud/boltons#481 | 5 | 4 | 0 / 0 |

Both frozen candidate populations rebuild exactly and record zero protocol-name refusals.
The itsdangerous receipt binds head FAIL 3/3 and base PASS 3/3 under `linux-container-v1`;
offline verification with the existing controller key and `require_seal=True` accepts it.
The controller key is neither copied nor included in evidence.

Boltons' four executed probes produce behavior-change evidence without a receipt. Its
fifth verification cannot obtain an additional frozen probe; a sixth candidate is skipped
by the existing per-unit verification cap. A `local_development_best_effort` label on that
skipped row is not an executed local fallback. This distinction prevents calling five rows
five differentials, or interpreting every abstention as a correct negative.

Elapsed times are 10.1 s and 19.0 s. Actual model/API spend is **$0**. The frozen provider
charges historical token counts internally: $0.032519 and $0.126263, totaling $0.158782.
These are simulated budget charges, not a bill or a prediction of fresh-model cost.

## Scope and fidelity

The [preregistered smoke](../../benchmarks/studies/repository-holdout-v1/product-readiness.md)
selects the first previously published forty row and first previously probed control row.
This deliberate known-outcome selection exercises paths; it is not an independent sample,
new recall estimate, precision measurement or zero-FPR claim. No population score is made.

The existing `frozen_e2e.py` driver is unchanged. Arm S retains intent v5.1 and disables
contract search, with its documented replay overrides: K=5, simulated $1 budget, value notes
enabled, gate notes/shadow and auto-tightening disabled. Frozen proposals are mechanically
reconstructed from ledger metadata, not original verbatim model proposals; only decisive
historical probes exist. This checks the product's `run_review` and receipt/publication
selection paths under those replay settings, not fresh discovery or complete factory-setting
equivalence. No GitHub client posts a comment; all-level presentation was not measured.

One [independent artifact review](../../benchmarks/studies/repository-holdout-v1/product-readiness-evidence/independent-review.md)
found no concrete defect and checked actual execution versus skipped rows. The controller
performed the cryptographic bundle verification separately. Script Ruff, input/output
digests, empty-input guards, redaction and immutable product/population checks pass in
[validation](../../benchmarks/studies/repository-holdout-v1/product-readiness-evidence/validation.json).
No product source/tests changed and no full product gate was rerun for the unchanged driver.

## Next prerequisite

Current-host product execution works on these modern development fixtures. The serial
Keras failure therefore does not establish a general product-execution outage. Independent
corpus qualification remains missing: original human-authored oracles, product-compatible
execution, blind semantic labels and matched reasonable-change controls must be established
before spending on that new population. A product-runtime qualification protocol may use
the product's own image selection/build behavior and record its actual success or failure;
it must not silently substitute versions and claim an original historical environment.

The replay writes its reconstructed responses through the normal proposal attempt cache.
Any fresh-model evaluation must isolate caches/work directories from this smoke and all
earlier frozen runs. Reusing those responses would invalidate a fresh-discovery claim;
the paid protocol must bind cache initialization and replay accounting explicitly.

No held-out source was read or executed, no paid call or remote write occurred, and defaults,
certification and isolation remain unchanged. The long task continues toward a valid paid
evaluation; this smoke is an intermediate artifact, not its final performance report.
