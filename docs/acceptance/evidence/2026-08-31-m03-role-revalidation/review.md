# M-03 independent role-accounting review — 2026-08-31

Reviewer: independent agent `m03_role_accounting_review_2`; it did not participate in
implementation and made no repository edits.

Reviewed implementation: `bce13f00e5f3e5002b457a930d9378ec8d171e88`, including the
complete role-accounting change from the invalidated `81bf625` acceptance and all final
SHA-bound Gate evidence in this directory.

## Result

- P0: 0
- P1: 0
- P2: 1
- M-03: PASS
- G-CODE-001: PASS
- G-MEASURE-003: PASS

The review independently reproduced and caused correction of three additional P1s after
the first implementation candidate:

1. coordinated checkpoint/artifact/spend role rewriting survived reconciliation because
   the canonical request-role preimage was not persisted;
2. stability report digest omitted per-repeat call reconciliation digests;
3. comparison publication accepted fabricated paid evidence for the local Ruff arm.

The final implementation rejects those cases, preserves settled product and oracle cost
through post-settlement exceptions, uses non-overlapping role totals, distinguishes a
bound zero-call record from missing evidence, and replays/resumes without new dispatch.
The reviewer also verified the final Python 3.11.5/3.12.8 logs: 213 focused, 479
benchmark, 860 full tests, Ruff, Mypy, 92.36% coverage, `pip check`, diff check, and clean
state all passed.

## P2 and boundary

The public pure reducer API, principally `build_calibration_report`, assumes its caller
has already established authoritative rows and does not itself reopen checkpoint,
artifact, and ledger paths. The current production/CLI route through `run_live_local`
performs that authority verification before invoking the reducer, so there is no current
publication-entry bypass. Hardening the standalone reducer API remains non-blocking.

An actor able to rewrite every local authority file and recompute every digest remains
outside M-03's integrity/process-crash boundary. External authenticated roots belong to
the later V-03/X-01 dependency path.

Paid actions: none. Remote mutations: none. Provider network calls: none.
