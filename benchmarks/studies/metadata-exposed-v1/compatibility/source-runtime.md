# Natural-pair source-mounted runtime diagnostic

This is the next free compatibility step authorized by the owner, following D-277.
It does not amend the failed D-276 qualification, its population or its minimum.
No product score or paid dispatch is authorized by a successful import.

## Fixed inputs and execution

Reuse `swebench_source_runtime.py --study natural-pairs`, `check_runtime`, the existing
native fixture, and `wheel_overlay.apply_wheel`. Bind the complete ordered four-row
`cases.json` to qualification and freeze digests with `natural_cases`. Match every
build row's identity and revision to that population and the committed build record.
Preserve both scikit-learn build failures as build-unqualified; do not rebuild them.
Use a fresh `.attest/corpora/natural-pair-source-runtime` directory, no overwrite.

Run the generic native fixture first; failure stops corpus execution. Then run each
successful Astropy revision once, parent before head, with its own digest-bound
wheel and immutable source export. Refuse symlinks before extraction. Reuse strict
wheel transfer: original tracked bytes stay unchanged, and only admitted generated
native/version files may be added. Never use one revision's artifacts for the other.

Reuse the existing Python 3.10 source-runtime recipe: recorded compiler builder,
digest-resolved slim runtime, declared runtime/test extras, and creation-date package
upper bounds. Preserve resolved dependency freezes and image digests. This is a
compatibility environment, not a complete historical lock. Do not change per-case
pins or retry based on results. Build-time downloads are allowed; execution uses the
secretless, network-disabled ContainerAdapter and the product's execute_repro path.
The controller ignores project addopts while retaining other ini settings and
conftest behavior; plugin autoload stays disabled. This follows the separately gated
executor fix, not a plugin allowance or a new isolation policy.

Runtime-ready requires one collected test, zero skip/xfail, zero exit, network guard,
NOT_REPRODUCED, and every imported package rooted at `/attest/tree/`. The generic
fixture additionally checks its native function returns the frozen value. Record
all outcomes, stages and reasons, original input digests, driver/helper digests,
exact Attest SHA, image identity, transfer record and execution artifacts. Commit
this driver and protocol before invocation, after one independent review. The
executor's fixed-SHA gate must pass before execution; it does not certify this
measurement adapter. No project source or original oracle test is modified here.

## Interpretation and next boundary

Four revision records represent two source cases. Runtime-ready is neither an
original-test differential nor product certification, recall, precision or FPR.
Qualified defects/controls remain zero in this diagnostic. A separate frozen step
must run unchanged original human tests on the natural parent/head and retain
independent reasonable-change controls. One compatible pair cannot satisfy the
three-defect/two-repository minimum. No paid calls, reservations, default rule,
statistical policy, publication cap, remote writes or release changes are made.
