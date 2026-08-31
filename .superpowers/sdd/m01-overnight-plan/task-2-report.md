# Task 2 checkpoint report — authoritative comparison outcomes

Status: implementation checkpoint complete; M-01 and Task 3 are not complete.

## Binding

- Baseline: `b9ff22733daee9e78c8302ed3ad190978d9cc85a`
- Implementation: `9efa0455353deb3722450c7ce3fe89d145a4a738`
- Tree: `35cd321a75a8c0c6343fcb9f3fa8aead303831d5`
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
- A bare-prompt exception after a durable response likewise propagates before any bare/Ruff
  outcome or final receipt is written. Baseline worktree materialization failures are
  conservative hard failures: neither fresh nor settled-recovery state is converted into
  an outcome with an empty or invented paid-evidence digest.
- Before any provider-backed fresh reconstruction or final-receipt write, the issuance and
  report paths share one exact-set check: reconciliation-marker keys and paid arm/case roots
  must both equal the frozen product/bare trial set. Orphan roots/markers and a missing
  zero-call paid root fail closed without being recreated.

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
- a bare response followed by an ordinary exception was rewritten as two DEFER outcomes,
  after which an external final receipt was occupied before paid reconstruction failed;
- fresh and settled-recovery materialization failures could occupy bare/Ruff write-once
  slots with an empty paid digest;
- orphan paid roots, orphan reconciliation markers, and deletion of a legitimate zero-call
  paid root were accepted until after final issuance (the deleted root was silently
  recreated by reconstruction).

The new attacks now fail at their named authority boundary. The existing coordinated
caller rewrite, in-place Ruff outcome plus seal rewrite, A/B root substitution, legacy
checkpoint rejection, full completed resume, and bare-before-Ruff crash tests also pass.

## Verification at implementation SHA

- Sixteen targeted tests spanning normal three-arm execution, full resume, product/bare
  settled-before-slot recovery, post-response/publication failures, fresh/recovery
  materialization refusal, orphan marker/root refusal, zero-call-root deletion, and oracle
  spend preservation — **16 passed**, exit 0.
- Changed-file `ruff check` over the two files changed after the earlier checkpoint —
  **pass**, exit 0.
- `python -m mypy src/attest` — **Success: no issues found in 49 source files**, exit 0.
- `git diff --check` — **pass**, exit 0.
- The five-file matrix reached **337 passed**, exit 0, immediately before the final
  exact-set hardening. Because those production/tests bytes subsequently changed, that run
  is recorded only as an intermediate regression and is not claimed as the final-SHA Gate.
- Full `ruff check .` — exit 1 solely for `I001` in unchanged
  `src/attest/review/ci.py`. Exact baseline reproduction:
  `git show b9ff227:src/attest/review/ci.py | python -m ruff check
  --stdin-filename src/attest/review/ci.py -` — the same sole `I001`, exit 1. This
  checkpoint intentionally does not modify that accepted-base file.

Full-repository/coverage, dual-Python clean gates, and independent delta re-review must run
from `9efa0455353deb3722450c7ce3fe89d145a4a738`; the terminated `184e7fc` Gate logs are
invalidated and are not claimed by this report.

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
