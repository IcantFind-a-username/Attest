# Serial oracle independent review

Reviewed once, read-only, at driver `e849467bd0cf7371774ec0617b076e321c012975`,
baseline `57fd994`, branch `chore/serial-oracle-compatibility`.
Scope: `git diff -w` for the historical driver, serial protocol, prior recovered
result, unchanged container adapter, and current preparation/request artifacts.

## Findings

No reproduced blocking or nonblocking defect in the reviewed change.

- `scripts/corpus/historical_oracle.py:169`: serial reuse requires a prior successful
  build and matching case, both source revisions, fixed oracle bytes and requirements.
  It records the prior result digest and reuses its immutable image reference;
  local inspect must return that exact image ID. The serial branch skips pull/build.
- `scripts/corpus/historical_oracle.py:278`: execution still uses the existing
  ContainerAdapter and Controller. Only the image provenance `cached` flag changes.
  Network-none, non-root, read-only mounts, default pid/scratch settings and resource
  limits remain in the same unchanged implementation.
- `scripts/corpus/historical_oracle.py:303`: the sole pytest launch change is `-n 0`.
  Bootstrap, original node, oracle overlay, environment and fresh output paths remain
  unchanged. The current fixed-0 request confirms 120 s CPU/wall, 2048 MiB and the
  same six explicit environment values.
- `scripts/corpus/historical_oracle.py:324`: existing accepted-envelope, exact one-test
  JUnit counts, no error/skip, and fixed exit 0 / buggy exit 1 checks are preserved.
  Three pairs and first non-discriminating-pair stop remain unchanged.
- `benchmarks/studies/repository-holdout-v1/serial-oracle.md`: interpretation is bounded
  to serial oracle feasibility in a reconstructed environment; parallel equivalence,
  semantic truth, controls, product compatibility, receipts and recall are excluded.

## Artifact limits

At inspection, `.attest/corpora/historical-oracle-keras8-serial-r1/result.json` was
`started` with zero completed runs. Preparation records match prior source-tree,
requirements, original launch-script and image-inspection output hashes. This review
does not sign off a behavioral result. The controller must classify any retained
startup/collection/runtime failure separately from a completed wrong oracle pattern.
No target code executed by the reviewer; no network, paid call, held-out source read,
remote mutation or product modification.

## Checks and reuse

`git diff --check 57fd994` passed. Diff stat at inspection: 3 files, 166 insertions,
90 deletions (DEVSPEND.md, serial-oracle.md, historical_oracle.py); the driver includes
indentation-only movement around its retained build branch. No product test gate was
run by this diagnostic reviewer, as specified by the frozen protocol.

Reused existing `_atomic_write`, `write_canonical_json`, `sha256_bytes`,
`validation_junit_counts`, `archive`, `ContainerImage`, `ContainerAdapter` and
`Controller`; no equivalent new helper or tool added. Reviewer owns only this report.
