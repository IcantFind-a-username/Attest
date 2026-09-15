# Serial oracle reaches collection, then the historical runtime crashes

E-02 preparation, D-265; 2026-09-16. Baseline `57fd994`, protocol `c0bf824`, measured
driver `e849467bd0cf7371774ec0617b076e321c012975`, branch
`chore/serial-oracle-compatibility`. Owner-directed autonomous evaluation preparation.

## Measurement

One frozen development case, keras/8; two jobs, zero completed target tests, zero usable
JUnit results, zero qualified defects and zero product evaluations. **Serial launch did
not qualify the oracle.** Both fixed and buggy jobs reach test collection, emit native
`Aborted` and `Segmentation fault` traces and reach the adapter's 120-second timeout.
Both envelopes have `timed_out=true`, `exit_code=null`, `junit_counts=null`.

The matching trace runs from `tests/keras/engine/test_topology.py:16` at module import
through Keras GPU availability/session setup into TensorFlow graph creation
(`tensorflow_core/python/framework/c_api_util.py:46`). This locates a pre-assertion native
runtime failure; it does not distinguish emulation, numerical dependencies, resource
limits or a library defect as the root cause. No target assertion ran, so this is not a
negative oracle result or a product miss. Envelope acceptance alone proves neither.

The protocol stops after this first non-discriminating pair. No additional repeat,
plugin disablement, dependency replacement, oracle edit or resource-policy change followed.

## What was held fixed

The [serial protocol](../../benchmarks/studies/repository-holdout-v1/serial-oracle.md)
was committed before dispatch. The driver reuses the successful D-264 image, exactly
`sha256:869b6deb283abd536330a54cec36779b955c4fb0af8dafec98c0917f472bdb09`, with its
42 original exact dependency pins and exported compiler/package inventory. There is no
new image pull or build. Source revisions, requirements and fixed oracle bytes match
the prior record; that record's digest and the image identity are bound in the new run.

The only test-launch difference is `-n 0`, overriding the original configured `-n 2`.
Both configuration files and source/test trees remain byte-identical to the prior exports;
all plugins, fixtures, numerical environment settings, ContainerAdapter limits and fresh
outputs remain in force. This was a distinct precommitted compatibility arm, not a rewrite
of the original parallel failure. That original record remains immutable.

## Review and evidence

One [independent review](../../benchmarks/studies/repository-holdout-v1/serial-oracle-evidence/independent-review.md)
found no confirmed defect in the script/provenance change and inspected the fixed request
while the run was pending. It did not certify the later outcome. The controller validated
both final envelopes, raw hashes, launch differences, failure traces and missing JUnit.

[Validation](../../benchmarks/studies/repository-holdout-v1/serial-oracle-evidence/validation.json)
records exact script/protocol/environment identities and artifact digests. Raw records stay
in `.attest/corpora/historical-oracle-keras8-serial-r1/`; committed projections redact local
root/home paths and normalize rendered whitespace. Existing SHA/JSON/archive/execution
helpers are reused. Ruff and artifact/diff checks pass. No product code/tests changed and
no product RED or full product gate was run for this diagnostic.

## Consequence for the long task

The first candidate remains environment-unqualified. A paid model run on it would not
resolve this pre-assertion failure. Original parallel startup and serial native collection
are separate retained blockers, not multiple independent defects. Four other development
cases and all 20 held-out candidates remain unexecuted and are not replacements.

The owner has authorized eventual paid evaluation within the existing development cap,
and explicitly directed stopping after its final report. No paid call has occurred;
recorded headroom is $4.542889 and must be rechecked before any reservation. The independent
population still lacks qualified oracles, semantic labels and matched controls. The next
bounded task must establish an executable, product-compatible evaluation path or record
why the existing inputs cannot supply it; it must not purchase a misleading recall number.

Attest model/API spend **$0**. No push, remote write, new backend, policy/default change,
held-out access, receipt or release. The long task remains active; this is an intermediate
prerequisite result. G-CORPUS-001 and semantic qualification remain open.
