# Independent oracle-input reader review

Reviewed commit `98c32fa`, one bounded static pass. No blocking findings in the specified reader/protocol scope.

## Evidence

- `scripts/corpus/freeze_swebench_oracles.py:28-45`: requires all six frozen IDs, exact runtime revisions, complete runtime status, a nonempty subset of strictly boolean runtime-ready rows, and the pinned Parquet SHA-256 before Arrow projection.
- `scripts/corpus/freeze_swebench_oracles.py:46-50`: projects the declared original fields and selects only qualified IDs, then verifies exact returned identity/count coverage. No problem-statement column is requested.
- `scripts/corpus/freeze_swebench_oracles.py:65-82`: verifies repository/base identity, nonempty original patches, valid unique original node lists, and at least one failure node. Validation parses node values separately; the saved original row is not rewritten into repaired nodes or test bytes.
- `scripts/corpus/freeze_swebench_oracles.py:51,81-88`: creates a fresh private directory and explicitly makes each original row private. The manifest contains identity, provenance hashes, node counts and execution-tool versions; it includes neither patches nor node contents. Shared canonical atomic writing is reused.
- `benchmarks/studies/swebench-independent-v1/oracle-inputs.md:21-27`: correctly distinguishes input availability from executable qualification and later semantic/control gates.

## Limits and checks

Static review only. I did not open Parquet, oracle rows, or hidden values; run the reader, builds, model calls, or network operations; or change implementation. Ruff and actual artifact/provenance checks remain the controller's acceptance checks. Runtime readiness of three rows is the supplied premise, not independently remeasured here. Arrow filtering limits returned rows; this review makes no claim about physical Parquet row-group decoding.

Reviewed diff stat: two files changed, 120 insertions (`oracle-inputs.md`: 27; `freeze_swebench_oracles.py`: 93). Reviewer writes only this ignored report; no tracked implementation diff.

Reused inventory: `sha256_bytes`, `write_canonical_json` (therefore canonical JSON and atomic writing), existing metadata projection precedent. New tools: none.

Paid/remote actions and cost: none, $0.
