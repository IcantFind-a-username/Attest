# Independent remainder freeze review

Reviewed HEAD 7224dcabcd3b6b69ab89c62ffb4a7880883f3870, producer delta ea73b72..0775937, in one bounded metadata-only pass.

## Finding

- **P2 — audit input digest is already stale.** `scripts/corpus/freeze_case_holdout.py:97` includes the active `.attest/remainder-freeze-work/freeze.log` in its recursive input inventory; line 187 persists the empty-file SHA-256, then line 192 writes producer output to that same retained log. The manifest's recorded digest equals `sha256_bytes(b"")`, while the current log contains the 34-candidate summary. Of 1,238 retained input records, this is the only reproduced digest mismatch. The selection is unaffected (the summary has no case identity), but an exact retained-input replay cannot validate the manifest without a visible provenance correction. Preserve the freeze and explain the empty-at-snapshot record; do not silently rewrite history or resample.

## Checks and limits

- Set equality verifies all 58 candidates are exactly prior eligible identities minus every selected identity in the three predecessor manifests. No duplicate, replenished, or omitted identity.
- The selected list equals all eligible candidates sorted by the exact `attest-remainder-v1|repo|instance_id` digest: 34 selected, 24 excluded, Django and Matplotlib only. No quota/truncation path is used by remainder mode.
- Candidate eligibility agrees with recorded exposure lists. Recomputing private-record needle matches from retained records produced no discrepancy, including the changed producer log.
- Driver, protocol, parent inventory and split digests match. Administrative references are limited to both predecessor freezes and structurally validated installation-only screening records.
- Enumerating the declared work directories found no unrecorded matching-extension files before this review was written. Producer inspection confirms dynamic non-symlink work-directory enumeration and corpus summary coverage, pinned-input checks, baseline-bound tracked search, and no selection rerun when a freeze exists.
- Owner authorization and protocol retain metadata-exposed scope, no recall/untouched-holdout claim, no source/hidden truth reads before freeze, no replacement, and unchanged paid/release limits.
- This is freeze metadata review only, not semantic qualification, test execution, full repository gates, or evidence of successful product evaluation. No source checkouts, Parquet columns, oracle payloads, control diffs, network, model calls or containers were used. Cost: zero.

## Reuse and changes

Reused `attest.benchmark.artifacts.sha256_bytes` for digest/order checks and inspected the existing canonical writer integration. No new helper or measurement tool. Only this ignored review artifact was written; tracked diff stat: zero files changed. Review artifact: one new Markdown file.
