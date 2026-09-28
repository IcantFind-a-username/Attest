# D-259 — Parameter-node binding in the existing shadow experiment

Owner instruction: continue and advance quickly. Baseline `f6900c4e410352b8536f13021a94fad167f4a0b2`;
branch `fix/runtime-parameter-binding`. D-258's gate at `47dd7b5` is present and passed.
This is a bounded extension of the existing shadow measurement, not a new product surface.
Root owns the two runtime review modules, existing runtime driver/cases/tests and this
task's reports. One independent reviewer writes only its own report/reproductions.
No paid call, remote write, certification/default change, or production security decision.

## Contract and trust

Run every parameter row of each selected source assertion in the original test order,
using the same four original/observed base/head executions. Never pick a failing row or
rerun based on its result. Record the current pytest node during the call; cross-check
the complete node set and per-node outcomes against JUnit from all four runs. Each node
must have exactly one assertion observation; reject missing, duplicate, unknown, skipped,
setup-error, truncated and changed node sets. Pair by identity, not list order. Bind typed
arguments, receiver, expectation and returned/comparison values separately per node.
Report every node, including passing and refused ones; case recovery counts once.

Packet v3 adds node association. v2 artifacts remain historical, untouched. The pytest
environment marker and JUnit are same-process evidence, neither authenticated nor an
independent witness. This extension improves consistency only. Forgeable records, hidden
state and causal sufficiency remain promotion blockers; receipt eligibility stays false.
No new receipt contract is proposed. Missing capabilities continue to abstain.

## Frozen measurement

Keep all 15 D-258 synthetic cases, plus six parameter scenarios declared before code fixes:
two positives (one broken row and the same rows reordered with stable IDs), and four controls
(inputs exchanged under fixed IDs, parameter IDs changed, head skip, intended expectation
updated). Retain every case and every row. Replay all three historical gain cases without
reading mutation answers into selection; the five packaging parameter rows count as one
development case, never five defects. No held-out/FPR/recall claim from this population.

Freeze the driver/cases before final measurement. Observe focused RED/GREEN and packet
tampering controls; one independent review, then only reproduced fixes. One final full gate
on frozen source, plus Ruff/Mypy and affected real container replay. Reuse existing canonical
JSON/atomic write/digest, executor, index, fixture builder and runner; no duplicate utilities.
Stop at the measurement and handoff, at most eight commits/three hours. The next trust-boundary
design remains a separate decision package; this task cannot promote these records.
