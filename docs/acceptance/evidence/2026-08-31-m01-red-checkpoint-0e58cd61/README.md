# M-01 RED checkpoint — accepted baseline `0e58cd61`

This checkpoint is pre-implementation evidence for M-01/G-MEASURE-001. The checkout was
`feature/m01-authoritative-outcomes` at accepted SHA
`0e58cd61a1a63c51a329d5c1a5509181be32adfa`. Before these tests were added, the locked
offline CPython 3.12.8 environment passed full pytest, Ruff, Mypy (47 source files),
`pip check`, `git diff --check`, and clean status.

## Valid RED observations

- `coordinated-outcome-rewrite-red.log` / `.exit`: exit 1 at the exact node ID printed in
  the log. Product findings and matches were removed, all caller summaries were recomputed,
  detection changed from 1.0 to 0.0, paid evidence was retained, and publication failed to
  reject it (`DID NOT RAISE`).
- `mixed-publication-loss-red-final.log` / `.exit`: exit 1 at the exact node ID printed in
  the log. Preceding real-path assertions established five candidates, four published
  findings (three inline plus one overflow), one unresolved candidate, and API score 4/1/3;
  live calibration then erased the case (`evaluated_cases` was 0 instead of 1).

`red-tests.patch` is the patch against the accepted SHA that reconstructs these RED tests.

## Retained construction attempts — not RED evidence

- `mixed-publication-loss-red-attempt-1.*`: invalid fixture construction; semantic
  coalescing produced only three predictions, so it failed before the intended report join.
- `mixed-publication-loss-red-attempt-2.*`: invalid fixture construction; semantic
  coalescing produced only three candidates, so it failed before the intended report join.
- `mixed-publication-loss-red-attempt-3.*`: exit 0 runner-only characterization. It proved
  the corrected fixture retained four scored runner predictions but did not exercise the
  report loss and is not a RED.

All providers were deterministic local fakes/loopback. Paid actions, provider-network
calls, remote writes, and spend were all zero.
