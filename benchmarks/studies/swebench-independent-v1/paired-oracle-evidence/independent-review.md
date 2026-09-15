# Independent paired-oracle driver review

Scope: read-only review of the 218-line driver and 35-line protocol before execution. No hidden oracle inputs read, corpus code executed, network action, model call, or tracked file edits.

## Findings

- **P2 — requested node identities are not checked against observed identities** (`scripts/corpus/swebench_paired_oracle.py:186–205`). The driver checks the number of JUnit cases and equality across sides/repeats, but never compares these identities with `nodes`. An original pytest plugin/configuration can replace the selected population with an equally sized population: stable replacement identities with all repaired passes and all buggy failures satisfy every predicate here. This contradicts the protocol's exact requested population requirement. Capture actual collected/executed pytest node IDs and require exact equality to the requested nodes (including uniqueness), then retain the existing side/repeat checks. Count equality alone is insufficient. This is a static predicate finding; no corpus outcome is asserted.

## Other observations

The frozen input payload and runtime record have digest bindings; base revision, wheel revision/digest, and upstream patched file bytes are checked. Wheel transfer preserves source and rejects symlinks. Patch sets are Python-only and disjoint; identical oracle bytes and final tree digests are recorded. Existing Controller/ContainerAdapter provides the intended secretless, network-disabled, read-only, non-root execution boundary. Terminal envelopes/artifact digests are checkpointed before XML scoring; failed discrimination ends the case and does not count a qualified defect/control. Scope wording clearly excludes product evaluation and forward recall. No additional concrete findings from this pass.

## Validation and changes

- `.venv/bin/python -m ruff check scripts/corpus/swebench_paired_oracle.py`: PASS.
- Static review only; driver not executed, so no empirical result or containment pass claimed.
- `git diff --stat`: empty because both reviewed files are untracked. Explicit untracked additions: driver 218 lines, protocol 35 lines (253 total). This review report is ignored and is the only file written by the reviewer.
- Reused tools inspected: canonical_json_bytes, sha256_bytes, write_canonical_json, validation_junit_counts; archive; apply_wheel; existing Controller/ContainerAdapter.
- New tools: none.
