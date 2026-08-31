# Task 2 checkpoint report — authoritative comparison outcomes

Status: implementation checkpoint complete; M-01 and Task 3 are not complete.

## Binding

- Baseline: `b9ff22733daee9e78c8302ed3ad190978d9cc85a`
- Implementation: `eddfee6736f18331b42045074d02de3892461dcb`
- Tree: `cd55929f4a1495126a7d94cc8fb84f8366e47635`
- Prior live-route checkpoint: `0cde430146ee3664aeaeeb40c02f8a336564cf6e`
- Settlement-recovery hardening: `0b5d75ed7309f4fcfa8721be6e9ab1d4ce9fc350`
- Branch: `feature/m01-authoritative-outcomes`
- Scope: twelve tracked implementation/test files; no protocol fixture, lock, action,
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
- Settlement-before-slot recovery separately requires an existing marker and paid case root
  to have identical presence before constructing `CheckpointedProvider`; a zero-call marker
  cannot recreate a deleted root, and a root without its marker is also rejected.
- Calibration routing now consumes exact current `MeasurementRecord` payloads. A valid
  `fully_deferred` record remains in current outcome accounting while also entering the
  explicit abstention list, and it never enters legacy scoring. The route requires the
  payload's non-empty reason and exact outer/transcript task-ID join. Taskless payloads keep
  the historical exclusion priority and do not enter outcome accounting, while a malformed
  current measurement dictionary still fails its strict decoder before exclusion.
- Fresh product/bare reconciliation is durable before either provider factory is entered.
  The controller preconstructs the empty checkpoint skeleton around a late-bound delegate,
  holds no-follow directory descriptors for checkpoint root, arm, case, calls, and
  artifacts across factory construction, and exact-compares their device/inode/mode
  identities before binding or dispatch. Marker, directory, or paid-evidence drift fails
  before provider sampling, outcome writes, or final publication.

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
- a zero-call bare marker retained after a settlement-before-slot crash could likewise
  recreate its deleted paid root during resume and then obtain an external final receipt.
- the first dual-Python Gate attempt against `f01a4af` exposed 39 stale live-test fixtures
  that omitted the now-required current measurement; after replacing the fixture with an
  honest typed record, the remaining live RED showed `fully_deferred` entering legacy
  scoring instead of abstention;
- a current `fully_deferred` payload without its reason was accepted, taskless current
  payloads entered v2 outcome accounting, wrong/empty/non-string outer task IDs were not
  joined to the delivery transcript, and a malformed taskless measurement dictionary could
  bypass strict decoding.
- provider factories ran before a durable reconciliation marker, could remove or replace
  that marker, inject paid evidence, or redirect its parent; after marker ordering was
  repaired, a factory could still rename a paid arm and replace it with an outside symlink.
  Controlled guard removal on the final fixture produced two product-provider calls and one
  bare-provider call plus outside checkpoint writes before the late publication guard.
- the CLI end-to-end assertion still pinned the former six-field `CiRun` payload and the
  full coverage Gate exposed newly added authority/recovery paths that lacked adversarial
  execution coverage.

The new attacks now fail at their named authority boundary. The existing coordinated
caller rewrite, in-place Ruff outcome plus seal rewrite, A/B root substitution, legacy
checkpoint rejection, full completed resume, and bare-before-Ruff crash tests also pass.

## Verification at implementation SHA

- Seventeen targeted tests spanning normal three-arm execution, full resume, product/bare
  settled-before-slot recovery, post-response/publication failures, fresh/recovery
  materialization refusal, orphan marker/root refusal, zero-call-root deletion, and oracle
  spend preservation — **17 passed**, exit 0 at the final implementation tree.
- Changed-file `ruff check` over the two files changed after the earlier checkpoint —
  **pass**, exit 0.
- `python -m pytest -p no:cacheprovider -q tests/test_ci_flow.py` — **16 passed**, exit 0.
- `python -m ruff check .` — **pass**, exit 0 at
  `0cde430146ee3664aeaeeb40c02f8a336564cf6e`.
- `python -m mypy src/attest` — **Success: no issues found in 49 source files**, exit 0.
- `git diff --check` — **pass**, exit 0.
- Final live-route focused selection — **7 passed**, exit 0.
- `tests/benchmark/test_live.py` — **106 collected and passed**, exit 0.
- Combined API/runner/live selection — **207 collected and passed**, exit 0.
- The five-file matrix reached **337 passed**, exit 0, immediately before the final
  exact-set hardening. Because those production/tests bytes subsequently changed, that run
  is recorded only as an intermediate regression and is not claimed as the final-SHA Gate.
- Final paid-factory marker/directory and settled-resume matrix — **39 passed**, exit 0.
  It covers product/bare marker ordering and identity drift, injected evidence, failed
  factories, outside marker-parent aliases, outside paid-arm aliases, exact five-descriptor
  closure, same-shaped arm/calls/artifacts replacement on return and exception, completed
  resume, and settled-before-slot recovery.
- Controlled removal of the paid-directory identity check — **2 failed as required**:
  product made two provider calls and bare made one. Restoring the exact implementation
  yielded the public alias test plus replacement matrix — **14 passed**, exit 0.
- Python 3.12.8 full repository coverage at the exact implementation tree — **1445 passed**,
  exit 0; total source coverage **11920/13240 = 90.030211%** and `attest.core`
  **428/429 = 99.766900%**.
- `python -m ruff check .` — **pass**, exit 0; `python -m mypy src/attest` —
  **Success: no issues found in 49 source files**, exit 0; `git diff --check` — **pass**,
  exit 0.
- Three bounded independent re-reviews of the final paid-factory directory-identity delta
  report **P0=0/P1=0/P2=0**. The review explicitly covers both paid arms, no bind/sample,
  unchanged outside bytes, five closed descriptors, same-shaped leaf replacement, and
  resume with no slot/final side effect.

Local raw RED/GREEN logs for the Gate integration repair are retained outside the repository
under `/private/tmp/m01-task2-*`: `test-live-f01-red`,
`test-live-post-helper-blocker`, `live-missing-reason-red`,
`live-taskless-exclusion-red`, `live-task-id-join-red`,
`live-taskless-malformed-red`, `live-route-focused-green`,
`test-live-current-green`, `api-runner-live-green`,
`live-integration-collection`, and `live-integration-static-green` (each with its adjacent
`.exit` marker where applicable). They are diagnostic logs, not a sealed acceptance bundle.

The final coverage-repair diagnostics are likewise retained outside the repository:
`m01-task2-provider-paid-alias-real-red`,
`m01-task2-provider-paid-alias-real-green`,
`m01-task2-provider-directory-lease-final-4`,
`m01-task2-provider-directory-lease-static-3`, and
`m01-task2-local-final-coverage` (with adjacent `.exit`/JSON files where applicable).

The dual-Python full Gate attempts against `f01a4af` failed on the stale live fixture and are
invalidated. The local Python 3.12.8 full/coverage Gate is now green at the exact
`eddfee6736f18331b42045074d02de3892461dcb` tree. The clean detached Python 3.11.5 Gate is
also green: 1046 benchmark tests collected and passed, 1445 full tests passed, coverage was
11920/13240 total and 428/429 for `attest.core`, and Ruff/mypy/pip/diff/v1-integrity/clean
state all exited zero. Its 30-file ledger is
`/private/tmp/attest-m01-task2-final-311.hFXniR`, whose `ARTIFACTS.sha256` digest is
`e33cade9ef8a36705a62ea55157b90c026cbeb503bda13eb2d132bbd6f95cce9`. A clean detached
Python 3.12 acceptance bundle, if required beyond the exact-tree local Gate, is not claimed
here. The terminated `184e7fc` Gate logs remain invalidated.

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
