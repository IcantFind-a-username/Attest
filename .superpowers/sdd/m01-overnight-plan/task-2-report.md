# Task 2 checkpoint report — authoritative comparison outcomes

Status: implementation checkpoint complete; M-01 and Task 3 are not complete.

## Binding

- Baseline: `b9ff22733daee9e78c8302ed3ad190978d9cc85a`
- Implementation: `184e7fc1379c54fa417b64f0bab2141a8fdd609a`
- Tree: `e6cbc879f5d1da4576b0c5793e3198a67613046f`
- Branch: `feature/m01-authoritative-outcomes`
- Scope: nine tracked implementation/test files; no protocol fixture, lock, action,
  historical evidence, or factory-statistics change.

## Contract implemented

- Comparison checkpoint v7 predeclares the exact three-arm Cartesian outcome slots before
  any provider/tool factory. Product, bare-prompt, and Ruff terminal outcomes are written
  once and the complete set is sealed once by the comparison owner.
- Versioned launch/final receipts are persisted in an external authority root. They bind a
  unique run identity, canonical checkpoint/outcome/authority-root identities,
  `comparison.json`, the outcome predeclaration, the final seal, and the ordered outcome
  tree. Finalization and final-receipt publication freshly revalidate all roots,
  `comparison.json`, seal, and outcome bytes before the irreversible write.
- First execution, completed resume, settled-before-slot crash recovery, and report
  publication all reconstruct runs from fresh strict outcome slots plus fresh paid-call
  reconciliation. Factories are not constructed for already settled or sealed work.
- Paid checkpoint/artifact reads use one dir-fd/O_NOFOLLOW component chain. Artifact
  response objects, their declared digests, checkpoint responses, cost rows, and token
  evidence are exact-joined. Symlink/hardlink/rogue descendants fail closed.
- Reports require an exact external `ComparisonPublicationAuthority`. Empty executions are
  internal `not_executed` diagnostics only; the CLI emits no authoritative comparison
  report for that case.
- An exception after a possible publication boundary is not converted into an empty
  terminal outcome. Lacking an independent trusted post-publication reconstruction seam in
  Task 2, the comparison fails closed and produces no final receipt.

## TDD evidence

Focused REDs were observed before the corresponding GREEN, including:

- finalization accepted swapped checkpoint/authority roots or changed `comparison.json`;
- launch accepted a run identity different from `comparison.json`;
- empty execution and a `ComparisonMeasurements` subclass reached report publication;
- paid descendants reached Path-based readers through a symlink;
- artifact `response` could differ while retaining the old declared response digest;
- a rogue outcome-root entry was ignored;
- stale outcome/seal bytes could be written under an earlier final candidate;
- six settled-before-slot corruptions (missing reconciliation, duplicate/orphan/mismatched
  spend, missing artifact, wrong reconciliation digest) lacked factoryless exact recovery.

The new attacks now fail at their named authority boundary. The existing coordinated
caller rewrite, in-place Ruff outcome plus seal rewrite, A/B root substitution, legacy
checkpoint rejection, full completed resume, and bare-before-Ruff crash tests also pass.

## Verification at implementation SHA

- `/private/tmp/attest-m01-0e58cd6-venv/bin/python -m pytest -p no:cacheprovider
  tests/benchmark/test_measurement.py tests/benchmark/test_checkpoints.py
  tests/benchmark/test_baselines.py tests/benchmark/test_api.py
  tests/benchmark/test_runner.py -q` — **334 passed**, exit 0.
- Changed-file `ruff check` over the nine files — **pass**, exit 0.
- `python -m mypy src/attest` — **Success: no issues found in 49 source files**, exit 0.
- `git diff --check` — **pass**, exit 0.
- Full `ruff check .` — exit 1 solely for `I001` in unchanged
  `src/attest/review/ci.py`. Exact baseline reproduction:
  `git show b9ff227:src/attest/review/ci.py | python -m ruff check
  --stdin-filename src/attest/review/ci.py -` — the same sole `I001`, exit 1. This
  checkpoint intentionally does not modify that accepted-base file.

Full-repository/coverage, dual-Python clean gates, and independent delta review follow this
checkpoint and are not claimed by this report yet.

## Remaining scope and limits

- Task 3 remains open: four-state mixed-outcome denominators and partially-deferred/failed
  surfaced findings are not accepted by this checkpoint.
- Live and stability sealed-outcome migrations, stable-ID adjudication, CLI constructed
  before/after evidence, and the 20-run operational-consistency harness remain later M-01
  tasks.
- The receipts prove exact local durable joins against the separately retained owner root;
  without external signing they do not prove resistance to an actor that can coordinate a
  rewrite of every predeclaration, paid, outcome, and owner root.
- No paid call, provider network call, remote write, constant/pricing change, or historical
  artifact rewrite occurred.
