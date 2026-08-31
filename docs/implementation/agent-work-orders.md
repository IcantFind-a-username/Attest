# Agent work orders

Status: **normative implementation guide**

Architecture: [`../architecture/target-algorithm.md`](../architecture/target-algorithm.md)

Order/status: [`../roadmap.md`](../roadmap.md)

Acceptance: [`../acceptance/evolution-gates.md`](../acceptance/evolution-gates.md)

Across work orders, candidates, ranking, evidence, corpora, and success metrics must cover
every dimension of the [Product north star](../../AGENTS.md#product-north-star); this guide
does not redefine that product authority.

This file is deliberately detailed. A construction agent should be able to select one
unblocked work order, find its seams, write the first failing test, and hand back an
auditable change without reconstructing the project strategy from chat history.

## 1. How to use this file

1. Read root `AGENTS.md`, the target architecture, roadmap, and acceptance gates.
2. Select exactly one unblocked work order from the roadmap. Do not start a downstream
   order because it looks easier.
3. Verify dependency evidence in the repository; a checked roadmap box without its tests
   and artifacts is not sufficient.
4. Claim a non-overlapping file set. One writer owns a file until review handoff.
5. Write the named RED test first and run it to observe the intended failure.
6. Implement the smallest typed seam that satisfies the target contract.
7. Run focused tests after every small change, then adjacent tests, then repository gates.
8. Perform an explicit adversarial self-review against the task's escape hatches.
9. Request an independent review. Fix confirmed findings and rerun the affected gates.
10. Update the roadmap checkbox/progress and `DECISIONS.md` only when the evidence exists.

An agent may split a work order into smaller commits, but must not combine two work orders
unless the roadmap declares them inseparable. No task authorizes a factory-statistical
constant change, paid API call, remote mutation, public release, or third-party write.

## 2. Mandatory preflight

From the checkout containing `AGENTS.md`:

```bash
git status --short --branch
git remote -v
git rev-parse HEAD
git log -5 --oneline
python --version
```

Then record:

- selected work-order ID;
- baseline SHA and branch;
- dependency commits/artifacts;
- files claimed for writing;
- current focused test result;
- whether the task is offline-only, security-sensitive, or budgeted.

If the worktree has unrelated changes, preserve them. If another writer owns an overlapping
file, stop that overlap; do not resolve it by overwriting or stashing another agent's work.

## 3. Universal implementation constraints

### 3.1 TDD sequence

For every behavior change:

```text
one focused RED -> minimal GREEN -> adjacent regressions -> adversarial RED/GREEN
-> full static/test gates -> independent review
```

A test that passes before the change is not the task's RED. A mock-only test is
insufficient when the contract concerns real Git, process, filesystem, JUnit, or crash
behavior; add a minimal real boundary fixture.

### 3.2 Versioning and compatibility

- New persisted records receive an explicit schema/protocol version.
- Readers may support legacy rows with a clearly named legacy semantic mode.
- Never rewrite historical ledger, receipt, or benchmark artifacts in place.
- Unknown enum values or future versions fail closed at certification/security boundaries.
- Migration adapters may translate shape, but cannot invent missing authority or evidence.

### 3.3 Evidence versus ranking

- Scheduler/S/T/model/tool signals are `RankingFeature` or `EvidenceObservation`, never a
  `CertificationReceipt` field that contributes truth authority.
- Only the Certification Kernel returns `CertifiedFinding`.
- Presentation functions accept certified outputs, not raw wealth or `GateResult`.
- Manual `self_reported` evidence is never coerced into differential evidence.

### 3.4 Paid and crash-prone operations

Persist a state transition before and after each paid or irreversible boundary:

```text
planned -> reserved -> dispatched -> response_persisted -> settled -> consumed
```

On recovery:

- `planned` may run;
- `reserved` may be cancelled only if dispatch is provably absent;
- `dispatched` without durable response is `ambiguous_cost` and must not auto-repeat;
- `response_persisted` may settle/consume idempotently;
- settled cost is never charged twice.

### 3.5 Security

Tests execute untrusted project code. Same-repository ownership does not make it trusted.
No implementation may call a language-level socket hook or environment filtering a
production security boundary. Until X-02 passes, describe current execution as
best-effort containment and keep deployment scope explicit.

## 4. Definition of done for every work order

A construction record is the composition of the selected work-order section, its
traceability row, the roadmap status/dependencies, the file-ownership map, and the family
defaults below. It is construction-ready only when that composition names every field
below. An implementing agent must resolve placeholders against the current tree at
preflight and repeat the resolved values in its handoff:

- status and hard dependencies, with dependency commit/evidence paths;
- concrete files **and symbols/interfaces** expected to change;
- in-scope behavior and explicit non-goals;
- applicable invariant and Gate IDs;
- one named prechange RED plus adversarial REDs. For a non-code study, RED is an offline
  protocol/manifest/analysis validator or dry-run fixture that rejects missing, forged,
  leaked, selectively excluded, or underpowered evidence; it never requires a paid call;
- the smallest intended GREEN implementation and exact focused/adjacent commands;
- compatibility and migration handling;
- a concrete rollback/reversal switch or artifact policy;
- applicability of security, receipt authority, manual evidence, multiplicity, new-code,
  remote-write, and paid-budget boundaries, using `N/A — reason` rather than silence;
- required evidence bundle and independent-review handoff.

Omitting a field from both the section and its applicable family default, or writing an
unexplained `N/A`, means the task is not ready to start or complete. The handoff must still
instantiate the exact symbols, test command, switch/caller/artifact, and boundary result;
copying “family default” is not an acceptable handoff.

| Family | Explicit non-goal | Mandatory rollback/reversal | Boundary applicability when the section is silent |
|---|---|---|---|
| F | no runtime behavior or empirical claim | keep the new authority set inactive until `G-DOC-001`; revert/correct it as one set | no remote or paid action; runtime boundaries are specified only |
| M | no certification-policy or model-quality change | retain versioned legacy readers, withhold affected metrics, and never rewrite historical rows | receipt/manual/mixed-outcome/cost authority applies; no remote action; paid tests need approval |
| C | no recall/model tuning | disable the new public path or fail to no-finding while retaining typed receipts; never restore a bypass | receipt, base policy, manual separation, multiplicity, and all author-visible surfaces apply |
| V | no scheduler ranking or UI expansion | reject/DEFER the new receipt version and keep artifacts; never infer missing evidence | receipt, provenance, semantic binding, fresh state, security channel, and bounded artifacts apply |
| R | no weaker Certification Kernel | disable the new planner/recovery/priority seam and use the last safe eligible path or abstain | no truth leak/outcome-aware retry; security profiles, new-code strata, and paid budgets apply |
| X | no production fallback to language-only containment | disable the backend/profile and DEFER unsupported execution; retain signed protocol evidence | every untrusted-code, secret, filesystem, network, process, and result-forgery boundary applies |
| S | no certification/publication authority | disable shadow/control policy and select the frozen deterministic fallback or abstain | task-local budget/reservation, propensity, correlated models, receipt-only outcomes, and paid approval apply |
| E | no product-policy mutation during a frozen study | seal partial/failed evidence, block the claim, and start a new version rather than edit outcomes | truth, receipts, isolation, multiplicity, versions, privacy, human/paid authorization apply |
| N | no LR, certificate, or public enablement | disable research command, seal evidence, and keep new-code abstaining | every new-code/truth/security/receipt/multiplicity/model/paid boundary applies; remote writes forbidden |
| L | no automatic public release | exercise kill switch, stop new jobs, retain evidence, and pin the last safe artifact | all boundaries apply; none may be silently marked N/A |

For a code work order, the exact focused command is `.venv/bin/pytest <tests named by the
section> -q`, followed by the adjacent package and standard repository gates in §6. If the
named target does not exist, its initial collection/import failure is part of RED and the
agent creates the specific test module stated in the handoff. Empirical tasks use the
explicit offline validator/dry-run commands in their sections before any authorized live
study.

A task is complete only when all applicable items exist:

- focused RED was observed and is named in the handoff;
- focused, adjacent, and full required gates pass;
- changed behavior has adversarial and fail-closed coverage;
- persisted/public schema changes have version and legacy-reader tests;
- no secret or raw unbounded provider/test output enters git;
- documentation and user-visible copy match actual reachable behavior;
- no factory statistical constant changed without a separately approved decision;
- `git diff --check` is clean;
- independent review found no unresolved P0/P1 issue;
- roadmap/decision/evidence references are updated in the same change where required.

A precisely reproduced pre-existing unrelated failure may be recorded in a non-completion
handoff with status `BLOCKED_BY_<work-order>`, but it never passes `G-CODE-001`, never marks
the checkbox complete, and never supports a release or empirical claim. A work order that
does not require `G-CODE-001` is judged only by its own declared gates.

Handoff format:

```text
Work order:
Baseline / final commit:
Behavioral contract:
RED observed:
Implementation summary:
Focused / adjacent / full gates:
Artifacts and digests:
Compatibility/migration:
Rollback/reversal:
Boundary applicability (security/receipt/manual/multiplicity/new-code/remote/paid):
Security and statistical review:
Known limits:
Independent review and fixes:
Next unblocked work orders:
```

## 5. File ownership map

This map prevents accidental architectural smearing. It is a target, so early tasks may
adapt current files while introducing the new owner.

| Concern | Target owner | Current seams to adapt |
|---|---|---|
| immutable task/policy/receipt validation | `src/attest/certification/` | `review/gate.py`, `review/executor.py`, `review/ci.py` |
| discovery/diff/context/candidates | `src/attest/review/` | `diffs.py`, `proposer.py`, `schema.py`, `dedup.py`, `candidates.py` |
| action selection and learning | `src/attest/scheduler/` | `review/channels.py`, `core/*`, `benchmark/experiments.py` |
| untrusted job protocol/runners | `src/attest/execution/` | `review/executor.py`, action scripts |
| GitHub/CLI rendering | `src/attest/github/`, `src/attest/cli/` | `review/report.py`, `review/ci.py` |
| immutable event/cost/label ledger | `src/attest/review/ledger.py` initially | benchmark checkpoints and artifacts |
| evaluation and gates | `src/attest/benchmark/` | scripts and frozen benchmark assets |

Do not move files only for aesthetics. Introduce a contract, route callers, verify parity,
then remove the old path in a separate reviewable step.

### Traceability index

| Work order | Current gap IDs | Primary invariant IDs | Completion / later Gate IDs |
|---|---|---|---|
| F-00 | N/A — documentation authority drift has no GAP ID | N/A — `G-DOC-001` owns documentation consistency | `G-DOC-001` |
| M-01 | `GAP-MEASURE-01` | `INV-MEASURE-001` | `G-MEASURE-001`, `G-CODE-001` |
| M-02 | `GAP-CORPUS-01` | `INV-RECEIPT-001` | `G-MEASURE-002`, `G-CODE-001`, `G-CODE-002` |
| M-03 | `GAP-CRASH-01` | `INV-COST-001`, `INV-VERSION-001` | `G-MEASURE-003`, `G-CODE-001` |
| C-01/C-02 | `GAP-CERT-01` | `INV-CERT-001`, `INV-CERT-002`, `INV-VERSION-001` | `G-CERT-001`, `G-CODE-001`, `G-CODE-002` |
| C-03 | `GAP-POLICY-01`, `GAP-TASK-01` | `INV-TASK-001`, `INV-POLICY-001` | `G-CERT-002`, `G-CODE-001`, `G-CODE-002` |
| C-04 | `GAP-MANUAL-01` | `INV-EVIDENCE-001` | `G-CERT-003`, `G-CODE-001` |
| C-05 | `GAP-FAMILY-01` | `INV-FAMILY-001`, `INV-PRESENT-001` | `G-CERT-004`, `G-CODE-001`, `G-CODE-002` |
| V-01 | `GAP-RECEIPT-01` | `INV-RECEIPT-001` | `G-SEM-001`, `G-MEASURE-002`, `G-CODE-001`, `G-CODE-002` |
| V-02 | `GAP-RECEIPT-01` | `INV-RECEIPT-001` | `G-SEM-002`, `G-CODE-001`, `G-CODE-002` |
| V-03 | `GAP-RECEIPT-01`, `GAP-CRASH-01` | `INV-RECEIPT-001`, `INV-COST-001`, `INV-SEC-001` | `G-SEM-003`, `G-SEC-001`, `G-MEASURE-003`, `G-CODE-001`, `G-CODE-002` |
| R-01/R-02/R-03/R-04 | `GAP-RECALL-01`, `GAP-TASK-01` | `INV-ORDER-001`, `INV-CERT-002` | code completion: `G-CODE-001`, `G-RECALL-001`; later E-02 promotion: `G-RECALL-002` |
| X-01 | `GAP-SEC-01` | `INV-SEC-001`, `INV-RECEIPT-001` | `G-SEC-001`, `G-CODE-001`, `G-CODE-002` |
| X-02 | `GAP-SEC-01` | `INV-SEC-001`, `INV-RECEIPT-001` | `G-SEC-002`, `G-CODE-001`, `G-CODE-002` |
| X-03 | `GAP-SEC-01` | `INV-SEC-001`, `INV-RECEIPT-001` | `G-SEC-003`, `G-CODE-001`, `G-CODE-002` |
| S-01/S-02 | `GAP-CORE-01` | `INV-SCHED-001`, `INV-SCHED-002`, `INV-ORDER-001` | `G-CODE-001` and schema/shadow `G-SCHED-001`; `G-MODEL-001` whenever >1 model/version/role is evaluated or deployed, otherwise N/A |
| S-03/S-04 | `GAP-CORE-01` | `INV-SCHED-001`, `INV-SCHED-002`, `INV-ORDER-001` | `G-CODE-001`, full learned-readiness `G-SCHED-001`; the same conditional `G-MODEL-001`; later intervention also `G-SCHED-003` |
| E-01 | `GAP-CERT-01`, `GAP-MEASURE-01` | `INV-MEASURE-001`, `INV-TRUTH-001`, `INV-CERT-001` | `G-CODE-001`, `G-NULL-001`, `G-MEASURE-001` through `G-MEASURE-004` |
| E-02 | `GAP-CORPUS-01`, `GAP-RECALL-01` | `INV-TRUTH-001`, `INV-RECEIPT-001`, `INV-MEASURE-001` | `G-CODE-001`, `G-CORPUS-001`, `G-RECALL-002`, `G-MEASURE-004` |
| E-03 | `GAP-RECALL-01` | `INV-ORDER-001` | `G-CODE-001`, `G-STAB-001` |
| E-04 | `GAP-CORPUS-01`, `GAP-RECALL-01` | `INV-CERT-001`, `INV-TASK-001`, `INV-POLICY-001`, `INV-RECEIPT-001`, `INV-PRESENT-001`, `INV-MEASURE-001`, `INV-TRUTH-001`, `INV-SEC-001`, `INV-VERSION-001` | `G-CODE-001`, `G-SHADOW-001`, `G-MEASURE-004` |
| E-05 | `GAP-CORE-01` | `INV-SCHED-001`, `INV-SCHED-002`, `INV-ORDER-001`, `INV-TRUTH-001` | `G-CODE-001`, `G-SCHED-001`, `G-SCHED-002`, `G-MEASURE-004`; `G-MODEL-001` whenever >1 model/version/role is evaluated or deployed, otherwise N/A |
| N-01 | `GAP-NEWCODE-01` | `INV-CERT-001`, `INV-EVIDENCE-001`, `INV-TRUTH-001` | `G-CODE-001`, `G-NEWCODE-001`, `G-MEASURE-004` |
| L-01 | N/A — release aggregates completed gaps | `INV-CERT-001`, `INV-CERT-002`, `INV-TASK-001`, `INV-POLICY-001`, `INV-EVIDENCE-001`, `INV-RECEIPT-001`, `INV-VERSION-001`, `INV-FAMILY-001`, `INV-PRESENT-001`, `INV-MEASURE-001`, `INV-TRUTH-001`, `INV-ORDER-001`, `INV-SCHED-001`, `INV-SCHED-002`, `INV-COST-001`, `INV-SEC-001` | `G-RELEASE-001` |

---

# Foundation and measurement

## F-00 — Evolution scaffold

**Goal:** make repository intent, current gaps, task order, and evidence requirements
unambiguous to future agents.

**Depends on:** none; baseline repository audit only.

**Files:** `AGENTS.md`, `README.md`, `pyproject.toml`, `DECISIONS.md`,
`docs/README.md`, `docs/architecture/target-algorithm.md`, `docs/roadmap.md`, this file,
`docs/acceptance/evolution-gates.md`, and a historical-status banner.

**Prechange RED:** the old agent guide names a stale branch/decision/test count and an
already-completed task list as current authority; completed plans have no archive boundary;
no canonical invariant/Gate/work-order graph exists; product metadata repeats an e-process
claim withdrawn by D-026. Treat a missing-link, duplicate/missing-ID, authority-conflict, or
forbidden-claim scan failure as RED for `G-DOC-001`.

**Checks:**

- all relative links resolve;
- product metadata does not call current wealth an e-process;
- current/historical/normative documents are visibly separated;
- work-order IDs match roadmap IDs and acceptance stages;
- `git diff --check` passes;
- independent reviewers inspect architecture, task decomposition, and acceptance science.

**Handoff artifact:** the documentation diff and independent-review report. No paid or
remote action is permitted.

**Acceptance:** `G-DOC-001`; this documentation-only work order does not claim
`G-CODE-001`. Any metadata syntax touched by F-00 must still parse, and the current full
suite result is recorded as context without converting a pre-existing failure into a pass.

**GREEN:** run `git diff --check`; parse all changed Markdown relative links; verify unique
and fully referenced `INV-*`, `G-*`, `GAP-*`, and work-order IDs; scan active normative
documents for superseded claims; obtain independent architecture, work-order, acceptance,
and final whole-tree reviews. Record the exact commands and outputs in a dated acceptance
note.

**Rollback/reversal:** if a normative-owner conflict remains, keep F-00 in review and do
not direct agents to the new roadmap. The scaffold is reverted or corrected as one
authority set; never leave a half-active new roadmap beside active completed plans.

**Boundary applicability:** documentation authority is in scope. Runtime security,
receipt, manual-evidence, multiplicity, and new-code behavior are specified but unchanged;
remote writes and paid calls are forbidden for F-00.

**Focused code-test target:** N/A — F-00 is documentation-only. Its executable RED/GREEN
is the link/ID/claim/metadata validation named above plus `git diff --check`.

## M-01 — Preserve every author-visible outcome

**Goal:** close the mixed surface+DEFER scoring hole. A task-level abstention never erases
a finding already visible to an author.

**Depends on:** F-00.

**Modify:**

- create `src/attest/benchmark/measurement.py` as the versioned owner of outcome units and
  denominator construction;
- `src/attest/benchmark/api.py` (`ProjectEvaluationResult`, `_result`, `_score`);
- `src/attest/benchmark/schema.py` (`RunRecord`, prediction/status schema);
- `src/attest/benchmark/report.py` aggregation input;
- `src/attest/benchmark/live.py` (`case_payload`, `build_calibration_report` path);
- `src/attest/benchmark/baselines.py` product-arm scoring;
- `scripts/benchmark.py` serialized fields.

**Tests:**

- `tests/test_ci_flow.py` retains a fixture with author-visible surfaces plus another
  candidate DEFER;
- create `tests/benchmark/test_measurement.py` for the exhaustive outcome-state matrix;
- add `tests/benchmark/test_api.py::test_mixed_surface_defer_preserves_predictions`;
- add `tests/benchmark/test_report.py::test_author_visible_findings_are_scored_when_task_defers`;
- add equivalent live and baseline tests.

**RED:** feed the existing mixed CI result through `evaluate_project`/calibration report;
assert the surface appears in finding precision and PR-any-false accounting while the
unresolved candidate appears in abstention taxonomy. Current code drops the scored case.

**Implementation:**

1. model `task_status` independently from `predictions` and `unresolved_candidates`;
2. derive `author_visible` from final publication events/placement, not top-level status;
3. always send author-visible predictions to matching/scoring;
4. apply DEFER only to unresolved opportunity/delivery fields;
5. version serialized `RunRecord`; preserve legacy all-deferred interpretation explicitly;
6. add invariants that publication count equals the ledger/API/benchmark visible count.

**Acceptance:** focused benchmark tests plus all `tests/benchmark`; no denominator changes
without golden report updates that state the migration. Add one property test over all
combinations of {0,1,4 surfaces}×{no defer,candidate defer,task defer}.

**Risk/rollback:** report numbers will change. Never preserve old numbers by retaining the
bug; label old reports `legacy_v1_scoring` and produce a versioned comparison.

**GREEN:** `.venv/bin/pytest tests/benchmark/test_measurement.py
tests/benchmark/test_api.py tests/benchmark/test_report.py -q`, then
`.venv/bin/pytest tests/benchmark -q` and §6. The named mixed-outcome property must fail on
the baseline and pass without deleting any visible event.

**Rollback/reversal:** route readers to the explicit `legacy_v1_scoring` adapter and
withhold new metrics; never route new rows through the buggy all-task DEFER shortcut.

**Boundary applicability:** measurement/receipt joins, manual versus automated outcomes,
PR multiplicity, and new-code abstention taxonomy apply; security runtime is unchanged;
remote writes are N/A because this is offline scoring; paid runs require separate approval.

## M-02 — Make validation authority evidence-bearing

**Goal:** a corpus validation receipt must prove which bounded executions produced its
status, not merely hash a status row that could be hand-authored.

**Depends on:** F-00.

**Modify:** `src/attest/benchmark/corpus.py`, `artifacts.py`, `report.py`,
`benchmarks/attest-v1/protocol.md`; add a v2 receipt fixture without replacing v1.

**Tests:** `tests/benchmark/test_corpus.py`, `test_artifacts.py`, `test_report.py`.

**RED cases:**

- `{pair_id, status: validated}` without six run records;
- a validated row with zero output evidence or differing runner/profile/interpreter;
- excluded row claiming “run evidence” without any run;
- altered stdout/JUnit artifact under unchanged summary;
- result/manifest signed by an unknown provenance key or missing local authority envelope.

**Implementation:**

1. define `ValidationAttempt`, `ValidationRun`, `ValidationResultV2`, and
   `ValidationReceiptV2` with canonical JSON;
2. require 3 fixed PASS and 3 stable buggy FAIL accepted runs, or bounded evidence for the
   explicit exclusion reason;
3. persist bounded output/JUnit content as content-addressed artifacts, not only hashes;
4. bind runner/isolation/interpreter/environment/repository SHAs and protocol;
5. separate integrity (`digests match`), provenance (`authorized runner envelope`), and
   semantics (`oracle policy accepts`) in APIs and reports;
6. retain a read-only v1 loader whose authority is `historical_integrity_only`.

**Acceptance:** forged minimal receipt rejected; v1 artifact still inspectable but cannot
authorize v2 scoring; every included/excluded pair has auditable attempt evidence; offline
verification returns precise failure paths.

**Risk/rollback:** do not mutate `benchmarks/attest-v1/receipt.json`. Add versioned assets
or a new corpus directory after protocol freeze.

**GREEN:** `.venv/bin/pytest tests/benchmark/test_corpus.py
tests/benchmark/test_artifacts.py tests/benchmark/test_report.py -q`, then all benchmark
tests and §6. Offline verification must distinguish integrity, provenance, and semantic
authority for every forged fixture.

**Rollback/reversal:** disable v2 scoring authority, retain the read-only
`historical_integrity_only` v1 loader and all immutable v2 evidence, and withhold metrics;
never synthesize missing runs or edit v1 artifacts.

**Boundary applicability:** receipt/provenance and manual-authority separation apply;
security profile metadata is validated but no untrusted live run is authorized; corpus
multiplicity/new-code strata remain explicit; remote and paid actions are N/A for GREEN.

## M-03 — Deterministic, version-locked, crash-safe measurement

**Goal:** make full gates and paid studies reproducible across dates, tool versions, and
crash boundaries.

**Depends on:** F-00; coordinate persisted-schema work with M-01/M-02.

**Modify:**

- `tests/test_phase3_acceptance.py` and acceptance clock seams;
- `src/attest/benchmark/live.py`, `stability.py`, `baselines.py` checkpoints;
- `src/attest/benchmark/api.py` predeclaration bindings;
- `pyproject.toml` plus generated lockfile/CI setup chosen by the project;
- acceptance scripts where workflow exit codes are inspected.

**RED cases:**

- run the date-sensitive test under two injected dates;
- crash after each paid provider/generator call but before repeat/case completion;
- `dispatched` call with no durable response;
- resume under changed SHA, prompt/model ID, truth, interpreter, receipt, or policy;
- GitHub workflow command returns nonzero despite parseable comments;
- run supported minimum Python with the locked mypy/ruff versions.

**Implementation:**

1. inject clocks and compare relative/event dates, never wall-clock literals;
2. bind predeclaration to repository identity, resolved SHAs, diff/truth/receipt digests,
   provider/model/prompt/schema versions, interpreter/environment, and code version;
3. checkpoint each paid subcall using the universal transition machine, binding an
   immutable product or benchmark-oracle role through request, checkpoint, artifact,
   spend, reconciliation, and report digest;
4. represent uncertain dispatch as `ambiguous_cost`, block automatic replay, and withhold
   claims until resolved;
5. require workflow process exit/conclusion success in acceptance;
6. lock the supported dev/test toolchain and test the declared minimum runtime.

**Acceptance:** two clean installs from the lock produce the same full-gate result; all
failure-point tests are table-driven; resumption makes no duplicate paid call; drift fails
before provider execution; old checkpoint readers fail with actionable version messages.

**Risk/rollback:** generated locks can be platform-sensitive. Keep declared target Linux
and supported local development environments explicit; do not loosen types to accommodate
an accidentally newer tool.

**GREEN:** `.venv/bin/pytest tests/test_phase3_acceptance.py
tests/benchmark/test_live.py tests/benchmark/test_stability.py
tests/benchmark/test_api.py -q`, followed by all benchmark/acceptance tests and §6 in the
locked minimum and primary environments. Each injected crash boundary must settle once or
remain `ambiguous_cost` without a second dispatch.

**Rollback/reversal:** stop/resume through the last compatible checkpoint reader, mark
ambiguous calls unresolved, and keep metrics withheld. Revert a lock only to a declared,
tested lock artifact; never auto-repeat uncertain paid calls.

**Boundary applicability:** receipt/version/cost authority applies; manual/multiplicity/
new-code semantics are unchanged; security metadata is bound but X-* owns isolation;
remote calls and paid crash tests require explicit opt-in, while cassette RED/GREEN is local.

---

# Certification Kernel

## C-01 — Introduce the versioned certification domain

**Goal:** create a small pure package that owns policy, receipts, validation, rejection
reasons, and certified results without importing model, GitHub, scheduler, or subprocess
code.

**Depends on:** M-01, M-02 schema lessons, M-03 version conventions.

**Create:**

- `src/attest/certification/__init__.py`;
- `types.py` — frozen task/policy/receipt/result records;
- `policy.py` — base policy and version validation;
- `validate.py` — pure receipt validation;
- `selection.py` placeholder interface for C-05;
- `tests/certification/` mirrors the modules.

**RED:** import failure followed by table-driven tests for every missing/mismatched field:
task, repo, merge-base/head, diff, candidate, normalized claim, test, policy, environment,
executor, run counts, result class, provenance, and unknown version.

**Implementation:**

1. define opaque IDs/digests and canonical normalization at construction;
2. return typed `AcceptedReceipt` or exhaustive `ReceiptRejection`, never bool/exception for
   ordinary invalid evidence;
3. make `CertifiedFinding` constructible only from an accepted receipt;
4. keep ranking scores/wealth absent from receipt validity;
5. add JSON adapters at the boundary, not inside the pure validator;
6. enforce import tests preventing certification from importing `attest.core`, provider,
   GitHub, ledger, or executor modules.

**Acceptance:** `G-CODE-001`, `G-CODE-002`, and the C-01 portion of `G-CERT-001`.
Mutation testing must demonstrate guards for every binding field. Exhaustive state tests
are welcome only if dependencies stay dev-only and deterministic.

**Risk/rollback:** avoid a “god receipt” copied directly from current ledger. Start with a
strict v2 regression receipt and add new classes only through decisions and tests.

**GREEN:** `.venv/bin/pytest tests/certification -q`, then
`.venv/bin/pytest tests/test_gate.py tests/test_executor.py -q` and §6. The architectural
import test and field-by-field mutation guards must pass.

**Rollback/reversal:** leave C-01 types/reader available but disable all callers that treat
v2 as accepted; return typed rejection/DEFER. Never fall back to raw wealth or legacy
two-field validation as certification.

**Boundary applicability:** receipt, manual namespace, new evidence-class versioning, and
unknown-version fail-closed behavior apply; PR multiplicity is a later selection step;
execution security is metadata-only here; remote/paid operations are N/A.

## C-02 — Enforce receipt-only public speech

**Goal:** structurally remove every path by which S/T/wealth/config/manual state can publish
without an accepted receipt.

**Depends on:** C-01, M-01.

**Modify:** `src/attest/review/run.py`, `gate.py`, `ci.py`, `report.py`,
`src/attest/github/presentation.py`, `client.py`, `src/attest/cli/main.py`; add adapters from
current executor output to candidate receipt attempts.

**Replace intentionally:**

- `tests/test_ci_flow.py::test_ci_does_not_verify_an_already_terminal_surface` must become
  a negative security regression using the known bypass configurations and the canonical
  matrix in `G-CERT-001`: S/T alone never publish;
- any experiment test relying on factory direct speech must be labeled legacy/synthetic and
  kept outside product contract.

**RED matrix:**

- the complete votes/T/config/evidence-state matrix owned by `G-CERT-001`;
- malicious head alpha, old candidate action=`surface`, forged `GateResult`, scheduler score
  infinity, presentation called directly;
- accepted receipt for wrong task/SHA/claim;
- receipt accepted then task superseded before publication.

**Implementation:**

1. `run_review` produces candidates/ranking only;
2. CI sends candidate attempts through executor and C-01 validator;
3. presentation accepts `Sequence[CertifiedFinding]` and operational status separately;
4. record legacy wealth for analysis but do not use it as speech authority;
5. revalidate task/head immediately before author-visible write;
6. delete/close adapters that construct presentation findings from raw `GateResult`.

**Acceptance:** property `author_visible -> current AcceptedReceipt` across the matrix;
zero generator receipt means zero findings; current true regression still publishes;
negative/refactor/new-code fixtures remain silent/typed; benchmark joins by receipt ID.

**Risk/rollback:** this may change local CLI semantics and experiments. Preserve a named
`legacy_factory_simulation` only inside benchmark experiments; never leave a product flag
that restores bypass.

**GREEN:** `.venv/bin/pytest tests/test_ci_flow.py
tests/test_github_presentation.py tests/test_cli_e2e.py tests/test_review_run.py -q`, then
the certification package, all review/GitHub tests, and §6. Run the full configuration /
state matrix from `G-CERT-001` and prove every visible item owns a current receipt ID.

**Rollback/reversal:** disable author-visible publication and return operational
DEFER/no-finding while retaining receipt attempts; the benchmark-only
`legacy_factory_simulation` must remain unreachable from CLI/CI/GitHub callers.

**Boundary applicability:** receipt-only speech, manual separation, all public surfaces,
PR multiplicity handoff, and typed new-code abstention apply; execution uses the current
declared trust class pending X-*; no paid/remote acceptance without authorization.

## C-03 — Resolve merge-base and load base-owned policy

**Goal:** define the reviewed counterfactual and safety policy from trusted destination
state, not pull-request head content.

**Depends on:** C-01, C-02.

**Modify:** `src/attest/github/context.py`, `review/diffs.py`, `review/config.py`, `review/ci.py`,
`scripts/action-entrypoint.sh`, `action.yml`; certification task/policy adapters.

**Tests:** `tests/test_diffs.py`, `test_config_report.py`, `test_ci_flow.py`,
`test_action_entrypoint.py`, GitHub context tests.

**RED cases:**

- base branch advanced after PR fork; verify merge-base diff, not base-tip two-dot semantics;
- head changes `.attest.toml` alpha/caps/executor profile/model budget;
- base policy missing/invalid, protected default fallback, and policy digest mismatch;
- shallow clone cannot resolve merge-base;
- event base SHA and repository identity drift before publication.

**Implementation:**

1. resolve full immutable head and merge-base before proposal;
2. obtain policy bytes from destination/base trust root or protected action inputs;
3. divide policy into safety fields (never head-owned) and optional head hints that cannot
   weaken limits;
4. digest resolved policy into `ReviewTask` and every receipt;
5. fetch depth explicitly or DEFER when merge-base is unavailable;
6. use three-dot/explicit merge-base diff consistently across discovery and execution.

**Acceptance:** head policy mutation has zero effect on safety decision; merge-base fixture
reviews only intended PR changes; policy drift invalidates receipt; action logs policy
source/digest without secrets.

**GREEN:** `.venv/bin/pytest tests/test_diffs.py tests/test_config_report.py
tests/test_ci_flow.py tests/test_action_entrypoint.py -q`, then all GitHub/review tests and
§6. Exercise real temporary Git repositories for advanced-base, shallow-clone, and
head-policy mutation cases.

**Rollback/reversal:** disable the affected review with typed policy/task DEFER and retain
the resolved manifest; never read safety fields from head or silently revert to two-dot
base-tip semantics.

**Boundary applicability:** base-owned security/executor/budget/publication policy,
receipt task identity, multiplicity cap, manual separation, and new-code classification all
apply; remote fetch/write tests use local bare repositories unless separately authorized;
paid calls are N/A.

## C-04 — Separate manual/self-reported evidence

**Goal:** keep human workflow utility without contaminating autonomous certificates or
metrics.

**Depends on:** C-01, C-02.

**Modify:** `src/attest/cli/main.py`, `review/ledger.py`, candidate/result reporting,
benchmark schema/report/readers; CLI docs.

**RED:** `attest verify --reproduced` without receipt must not create `CertifiedFinding`,
GitHub surface, automated `verification` evidence, or precision/FPR denominator. Old rows
remain readable as `legacy_self_reported_unknown`.

**Implementation:**

1. introduce `SelfReportedEvidence` ledger kind and explicit actor/source;
2. rename CLI copy to avoid “verified” equivalence or require an evidence-bundle input for
   true receipt import;
3. separate local task notes from autonomous publication;
4. migrate stats into manual and automated sections;
5. reject self-reported IDs at certification JSON boundary.

**Acceptance:** end-to-end CLI tests, schema migration tests, and report goldens prove the
separation. No compatibility alias may silently buy V.

**GREEN:** `.venv/bin/pytest tests/test_cli_e2e.py
tests/benchmark/test_schema.py tests/benchmark/test_report.py tests/test_ci_flow.py -q`,
then CLI/benchmark/certification tests and §6. Importing every legacy self-report fixture
must remain non-authoritative.

**Rollback/reversal:** keep the legacy reader in the explicit
`legacy_self_reported_unknown` namespace or disable the manual command; never map it back to
automated V, a `CertifiedFinding`, or an accuracy denominator.

**Boundary applicability:** manual/automated receipt separation is primary; public
surfaces and metrics apply; PR multiplicity/new-code remain separate types; execution
security, remote writes, and paid calls are N/A.

## C-05 — PR-level multiplicity and hard public cap

**Goal:** control at-least-one-wrong-publication exposure and make the base-owned hard cap
owned by `G-CERT-004` true across every author-visible surface.

**Depends on:** the decision-package stage depends on C-02. Policy implementation and
acceptance are hard-blocked until the owner selects the family method from that package.
C-05 itself owns the minimum order-invariant semantic-cluster seam needed by
`G-CERT-004`; it may not defer that contract to R-03 or reuse the current first-match
greedy order.

**Create/modify:** `certification/clustering.py` and `certification/selection.py`,
certification policy/types, an adapter from current `review/dedup.py`, GitHub presentation,
review report/ledger, benchmark PR metrics, and permutation/transitive-cluster tests. R-03
may later extend discovery eligibility and migration, but a change to publication cluster
identity requires a new schema/policy version and re-runs `G-CERT-004`.

**Decision package before code:** compare fixed per-PR budget/e-value allocation, ordered
testing, alpha spending, or another explicit family policy. State assumptions, meaning of
alpha, behavior as candidate count grows, and replay impact. Cosmetic top-N is not an
option.

**RED:**

- below/equal/above-cap accepted sets, duplicates, equal scores, and shuffled completion
  order, using the canonical value/matrix in `G-CERT-004`;
- all permutations of a transitive similarity chain produce the same cluster membership,
  stable cluster IDs, representative, selected set, and suppressed reasons;
- combined inline+summary cap;
- suppressed certified finding must be private-ledger only;
- family exposure metric counts PR once;
- head cannot raise cap or family budget.

**Implementation:**

1. apply family policy to semantic clusters, not raw model samples;
2. deterministic tie-break on trusted/declared fields;
3. return selected and suppressed-with-reason sets;
4. presentation receives only selected set;
5. benchmark records all certified candidates but author-harm metrics use published set;
6. property-test monotonicity/reordering invariants required by the selected method.

**Acceptance:** author-visible count never exceeds cap; PR-level gate simulations and
natural-null E-01 use the same implementation; owner-approved semantics recorded in a new
decision.

**GREEN:** `.venv/bin/pytest tests/certification/test_clustering.py
tests/certification/test_selection.py tests/test_dedup.py
tests/test_github_presentation.py tests/benchmark/test_metrics.py -q`, then all
certification/GitHub/benchmark tests and §6. Exhaustively permute the declared small
candidate sets and run the owner-approved family-policy simulation.

**Rollback/reversal:** fail publication closed or use the last versioned owner-approved
selection policy with its matching cluster schema; retain suppressed reasons. Never revert
to cosmetic layout-only top-N or order-dependent first-match clusters.

**Boundary applicability:** PR-level multiplicity and every author-visible surface are
primary; receipt-only eligibility and base-owned policy apply; manual/new-code outcomes
cannot bypass selection; execution security and paid/remote operations are N/A.

---

# Verification and receipt integrity

## V-01 — Exact-node, replayable execution bundle

**Goal:** prove exactly what ran, where, and how for every accepted differential repeat.

**Depends on:** C-01; coordinate with X-01 protocol.

**Modify/create:** receipt types; `src/attest/review/executor.py` initially; later
`src/attest/execution/`; artifact store; ledger adapters; `tests/test_executor.py` and
certification receipt tests.

**RED cases:** zero collected tests, two collected tests, selected node absent, skip,
xfail/xpass, collection warning/error, test file conditional on source version, different
argv/interpreter/env between sides, mutated test bytes, truncated evidence without digest,
and JUnit count disagreement.

**Implementation:**

1. version `ReproSpec` with exact node selector and expected collection count;
2. run collection validation before behavioral repeats under the same environment;
3. capture structured counts for tests/failures/errors/skips/xfail where available;
4. content-address exact test, bounded stdout/stderr, JUnit, command, interpreter,
   dependency/environment, source, and executor profile;
5. emit per-run records and a manifest used directly by C-01;
6. make missing/unparseable evidence DEFER rather than infer from return code.

**Acceptance:** every adversarial case rejects; positive regression receipt verifies
offline; changing one byte invalidates it; evidence bundle stays bounded and secret-free.

**GREEN:** `.venv/bin/pytest tests/execution/test_exact_node.py
tests/certification/test_receipt.py tests/test_executor.py -q`, then all execution/
certification tests and §6. The focused suite must parse real JUnit from a temporary project,
not only mocks.

**Rollback/reversal:** reject/DEFER v2 execution receipts and retain their bundles while
using the last accepted schema reader for history; never infer node/count/result from return
code or restore a receipt path missing exact evidence.

**Boundary applicability:** exact receipt authority and bounded secret-free artifacts are
primary; fresh-state/provenance continues in V-03; manual/new-code/multiplicity do not alter
execution identity; untrusted execution is development-only until X-02; no remote/paid run.

## V-02 — Bind observed behavior to claim and diff

**Goal:** reject a generated test that proves a real but different bug, targets unchanged
code, or branches on source/version rather than manifesting the claim.

**Depends on:** V-01, C-01. Owner selects final binding policy from evidence.

**Create:** a `certification/binding.py` policy seam and experiment harness under
`benchmark/`; avoid baking one technique directly into executor.

**RED/adversarial corpus:**

- test asserts an unrelated known failure elsewhere;
- test reads file contents/Git SHA and fails conditionally;
- test never executes the anchored symbol;
- failure occurs in setup/teardown, not the target path;
- patch reversion/mutation of the claimed hunk does not change outcome;
- stack reaches target but claim semantics are wrong;
- multi-hunk diff where test proves the wrong hunk.

**Compare:** trace/coverage reachability, changed-line coverage, dynamic patch ablation,
mutation of the alleged cause, focused dependency slicing, and blind semantic adjudication.

**Implementation:** expose each as a typed binding observation, then let versioned policy
select required observations. Never train/test thresholds on the same adversarial corpus.

**Acceptance:** selected policy rejects all preregistered adversarial fixtures; legitimate
eligible regression recall meets the V-02 pilot threshold; receipt records raw binding
observations and policy version; unsupported binding DEFERs.

**GREEN:** `.venv/bin/pytest tests/certification/test_binding.py
tests/benchmark/test_binding_experiment.py tests/test_executor.py -q`, then all
certification/benchmark tests and §6. Freeze the adversarial and legitimate pilot split
before comparing policies; the owner records the selected policy decision.

**Rollback/reversal:** disable the candidate binding policy and DEFER affected receipts;
retain raw observations and frozen comparison data. Never fall back to location-only or
stack-reached semantics as certification.

**Boundary applicability:** semantic receipt authority, hidden/blind adjudication, and
new-code class separation apply; manual evidence and multiplicity cannot repair a failed
binding; X-* owns OS security; paid pilot execution needs explicit authorization; no remote
write.

## V-03 — Fresh repeats and authenticated provenance

**Goal:** make N repeats independent of mutable executor state and make the controller
origin of an evidence bundle verifiable.

**Depends on:** V-01, M-03, and X-01. Authenticated provenance cannot be implemented on a
same-user writable result channel; X-01 is a hard dependency, not a later optional adapter.

**Modify/create:** certification receipt/provenance types and pure validator;
`src/attest/execution/protocol.py` plus controller result sealing and executor repeat
lifecycle; `tests/certification/test_provenance.py` and
`tests/execution/test_fresh_repeats.py`. Re-resolve exact existing adapters at preflight.

**RED cases:** test writes a marker/cache affecting later run, daemon survives, cwd mutates,
environment changes, base/head share writable state, crash after repeat 1/2, result bundle
rewritten by job code, controller envelope copied to another task.

**Implementation:**

1. fresh writable layer/process namespace per repeat;
2. immutable shared source blobs only;
3. atomic per-run persistence before next repeat;
4. controller-created nonce/job ID and authenticated result envelope bound to artifact
   Merkle/root digest;
5. explicit platform trust root and offline verifier;
6. no private signing key inside untrusted executor.

**Acceptance:** state-leak fixtures no longer affect later repeats; crash/resume never counts
or repeats an ambiguous run; tampering/task replay rejects; positive bundles verify offline;
`G-SEC-001`, `G-SEM-003`, and the applicable code/mutation gates pass.

**GREEN:** `.venv/bin/pytest tests/certification/test_provenance.py
tests/execution/test_fresh_repeats.py tests/execution/test_protocol.py -q`, then all
execution/certification tests and §6. Verify a positive bundle offline, then mutate every
task/run/root binding one at a time.

**Rollback/reversal:** disable acceptance of the new provenance version and DEFER new
execution; preserve per-run artifacts and ambiguous-cost states. Never keep publication
live on a same-user writable or unauthenticated result channel.

**Boundary applicability:** receipt provenance, secretless controller/executor separation,
fresh state, crash cost, and task replay apply; manual/new-code/multiplicity remain typed
outside provenance; local fixtures are free, any remote/paid run needs approval.

---

# Recall and discovery

## R-01 — Semantic diff and context planner

**Goal:** replace monolithic full-diff prompting with stable semantic chunks and retrieved
context, including deletion-side evidence.

**Depends on:** C-03 merge-base semantics; C-02 safety invariant.

**Create/modify:** `review/diffs.py`, new `review/planner.py`, proposer prompt interface,
candidate/schema anchors, budget accounting; tests with real temporary repos.

**RED cases:** pure deletion, rename+edit, moved function, new module, generated file,
multi-language PR, very large diff, call-site-only change, config/test interaction, and
definition outside the 200-line window.

**Implementation:**

1. stable file/hunk/chunk IDs over merge-base diff;
2. represent old/new anchors and rename lineage;
3. retrieve bounded definitions, callers, tests, type/config/dependency context with digest;
4. allocate per-chunk/context budgets and record omissions;
5. prompt per planned unit; preserve task-wide dedup later;
6. typed unsupported/oversize abstentions, never silent truncation.

**Acceptance:** permutation/determinism tests, no truth leakage, no context outside repo,
budget exactness, and replay comparison showing eligible-candidate yield by stratum without
safety regression.

**GREEN:** `.venv/bin/pytest tests/test_planner.py tests/test_diffs.py
tests/test_proposer.py tests/test_candidates.py -q`, then all review tests and §6. Use real
temporary Git histories for each diff shape and assert byte-stable plan IDs under input
permutation.

**Rollback/reversal:** disable the planner adapter and return to the last bounded discovery
path or abstain for unsupported diffs; retain plan/context digests. Never truncate silently
or bypass the receipt kernel.

**Boundary applicability:** base task/diff identity, context privacy, task-local budget,
new-code/language/profile strata, and no truth leakage apply; receipt/publication authority
is unchanged; no manual, remote, or paid operation in GREEN.

## R-02 — Precommitted structured-output recovery

**Goal:** recover schema/collection failures without allowing outcome-aware cherry-picking.

**Depends on:** M-03 paid-call checkpoints, V-01 schema.

**Modify/create:** proposer/generator parsing, new recovery policy module, artifact/checkpoint
records, benchmark outcome taxonomy.

**RED:** malformed envelope with recoverable JSON, truncated JSON, extra prose, wrong enum,
missing field requiring model repair, collection-only import/name error, repeated identical
failure, and any attempted retry after observing head/base behavior.

**Implementation:**

1. deterministic local parse repair first;
2. preregister maximum model schema-repair attempts and context visibility;
3. optionally repair collection defects before any behavioral execution;
4. freeze the final test before head/base outcomes;
5. cache attempts by immutable digest and checkpoint every paid call;
6. record success by attempt and all failure/defer reasons.

**Acceptance:** `G-RECALL-001`; no test/body mutation after first behavioral result; cost cap
exact; contemporaneous null/adversarial gate unchanged.

**GREEN:** `.venv/bin/pytest tests/test_recovery.py tests/test_proposer.py
tests/test_executor.py tests/benchmark/test_live.py -q`, then review/benchmark tests and §6.
The event log must prove that every permitted repair precedes the first behavioral outcome
and every paid attempt owns a checkpoint.

**Rollback/reversal:** disable model repair and use deterministic parse recovery only, then
typed DEFER; retain all attempts/cost states. Never retry after head/base outcomes or erase
failed paid attempts.

**Boundary applicability:** receipt schema freeze, outcome-aware retry prohibition,
task-local cost, executor profile, and new-code strata apply; manual/multiplicity are
unchanged; paid/provider fixtures require opt-in, remote writes are N/A.

## R-03 — Order-invariant dedup and eligibility

**Goal:** make candidates stable under sample completion order and avoid expensive execution
for structurally unsupported cases.

**Depends on:** R-01 candidate IDs and the C-05 publication-cluster schema/migration
contract. R-03 may enrich discovery clustering but cannot silently change C-05 IDs.

**Modify/create:** replace `review/dedup.py` internals behind a versioned clustering API;
candidate store schema; eligibility classifier using diff/executor/policy facts.

**RED:** all permutations of the same candidate multiset, transitive similarity chain,
same-line different defect, same-defect multi-anchor, rename aliases, duplicate across
chunks/models, new-code/non-Python/deletion/profile-infeasible cases.

**Implementation:**

1. construct deterministic graph edges from declared normalized features;
2. cluster with stable component/medoid/tie-break semantics;
3. retain every member/provenance and do not treat cluster size as independent evidence;
4. produce typed eligibility and required executor/evidence class;
5. migrate old greedy cluster IDs as legacy only.

**Acceptance:** permutation property passes; adversarial semantic distinctions preserved;
candidate count/cost changes reported; C-05 cap operates on clusters.

**GREEN:** `.venv/bin/pytest tests/test_dedup.py tests/test_candidates.py
tests/test_eligibility.py tests/certification/test_clustering.py -q`, then all review/
certification tests and §6. Exhaustively permute small candidate multisets and compare
cluster membership, ID, representative, eligibility, and provenance bytes.

**Rollback/reversal:** keep the new cluster schema disabled and read legacy greedy IDs only
as legacy provenance; use C-05's last versioned publication clusters or abstain. Never let
input completion order select public claims.

**Boundary applicability:** candidate/sample multiplicity, task ownership, new-code/
language/profile eligibility, and correlated model provenance apply; certification remains
receipt-only; security is profile metadata; no manual, remote, or paid operation.

## R-04 — Feasibility-aware deterministic priority

**Goal:** use current cheap signals to spend verification time on candidates most likely to
produce a decisive trusted receipt, while Core remains shadow.

**Depends on:** R-01/R-02/R-03, S-01 event schema, C-02.

**Modify:** CI verification queue, scheduler deterministic policy, deadline/defer reporting,
benchmark paired replay.

**RED:** candidate order permutations, shared deadline, unreachable/unsupported candidate
ahead of eligible regression, equal priority, generation cost exhaustion, and scheduler
failure fallback.

**Implementation:**

1. rank by explicit deterministic tuple using S/T only as ranking plus feasibility/cost;
2. persist original FCFS and chosen rank/features;
3. preflight candidate-specific receipt reachability/eligibility before paid generation;
4. do not change certification result for any candidate receiving the same observations;
5. provide stable FCFS fallback.

**Acceptance:** paired replay reports true surfaces, deadline-induced unprocessed DEFER,
cost, and latency at equal completed verification; no true surface is lost; costs and
tie-breaking are deterministic. This is the `G-RECALL-001` development diagnostic, not a
scheduler-benefit claim; E-05/`G-SCHED-002` remains required for learned promotion.

**GREEN:** `.venv/bin/pytest tests/scheduler/test_deterministic.py
tests/test_ci_flow.py tests/benchmark/test_experiments.py -q`, then scheduler/review/
benchmark tests and §6. Replay the same sealed opportunities under FCFS and priority with
identical task-local budget/deadline.

**Rollback/reversal:** switch the queue to stable FCFS or abstain if scheduler state is
invalid; keep both rank logs. Rollback cannot change any candidate's receipt validity,
family selection, or public result given the same observations.

**Boundary applicability:** `INV-SCHED-002`, receipt-only outcomes, PR-local budgets,
multiplicity, profile feasibility, model correlation, and paid-call accounting apply;
manual/new-code remain strata; remote writes are N/A.

---

# Execution isolation

## X-01 — Content-addressed controller/executor protocol

**Goal:** separate privileged orchestration from untrusted code execution without changing
receipt semantics.

**Depends on:** V-01 fields stable; C-01 validation.

**Create:** `src/attest/execution/{types,protocol,controller,local_adapter}.py`; versioned job
JSON schema; protocol tests and adapters from current executor.

**RED:** missing/extra field, path traversal, symlink, digest mismatch, wrong task nonce,
unbounded artifact, duplicate result, stale result, result before dispatch, executor crash,
controller restart, and job attempting to include a secret.

**Implementation:**

1. controller materializes immutable content-addressed inputs;
2. executor request contains no credential and only explicit mounts/resources/profile;
3. result references bounded artifacts and authenticated job nonce;
4. state machine follows M-03 transitions;
5. current in-process runner becomes `local_development_best_effort`, never production;
6. C-01 validates only protocol-normalized receipts.

**Acceptance:** protocol fuzz/property tests, parity on existing executor fixtures, and an
import/secret audit prove the untrusted payload cannot request arbitrary host paths or env.

**GREEN:** `.venv/bin/pytest tests/execution/test_protocol.py
tests/execution/test_controller.py tests/test_executor.py -q`, then all execution/
certification tests and §6. Fuzz canonical request/result parsing and crash/replay of the
real local development adapter.

**Rollback/reversal:** disable protocol dispatch and DEFER execution while retaining job /
result artifacts; the local adapter remains explicitly development-only and cannot be
selected by a production profile.

**Boundary applicability:** secretless request shape, task nonce, artifact bounds,
receipt provenance, crash cost, and result forgery apply; manual/new-code/multiplicity are
carried only as typed metadata; no remote or paid operation.

## X-02 — Production Linux OS isolation backend

**Goal:** enforce network, filesystem, process, resource, and secret isolation below the
language runtime.

**Depends on:** X-01, V-03 authenticated provenance/result verification, and an
owner/platform decision.

**Create:** backend under `src/attest/execution/`; a versioned backend/profile directory;
`scripts/security/run-red-team.sh`; `tests/execution/test_linux_isolation.py`; and a CI
security workflow that uses only canary secrets.

**RED-team fixtures:** read parent env and `/proc`, read home and git credentials, write
outside scratch, raw socket/DNS/IPv6/Unix socket, `ctypes` syscalls, native helper, fork/
thread bomb, exec shell, symlink/hardlink/device access, mount namespace escape, cgroup
resource exhaustion, background daemon, signal abuse, and forged result.

**Implementation requirements:** secretless environment; read-only source; empty/minimal
root; default-deny network namespace; seccomp/landlock/container equivalent; cgroup v2 or
equivalent limits; non-root UID; bounded writable tmp; killed job namespace; immutable
backend/profile digest in receipt.

**Acceptance:** `G-SEC-002` passes: every supported-platform attack fixture is actually
dispatched and reaches its trusted attempt marker, and the external supervisor/kernel
records OS denial or termination. Pre-dispatch or `unsupported` DEFER does not pass; it
marks that backend/profile unreleasable. The controller canary remains unread, the positive
pytest fixture works, teardown leaves no process/mount/temp state, and a missing required
kernel primitive fails closed.

**GREEN:** `.venv/bin/pytest tests/execution/test_linux_isolation.py
tests/execution/test_protocol.py -q` plus `scripts/security/run-red-team.sh --backend
<resolved-backend> --all`, then all execution/security tests and §6 on the declared Linux
kernel. Store trusted supervisor attempt/denial markers for every case.

**Rollback/reversal:** disable the backend/profile and DEFER untrusted execution; preserve
security artifacts and canary audit. Production must not fall back to
`local_development_best_effort` or a language hook.

**Boundary applicability:** all secret/network/filesystem/process/resource/provenance
boundaries apply; receipt and task identities are mandatory; manual/multiplicity/new-code
cannot waive security; CI/remote backend testing requires owner-approved infrastructure,
but no paid model call is needed.

## X-03 — Controlled subprocess profiles

**Goal:** support legitimate project tooling without turning isolation into an unrestricted
shell.

**Depends on:** the profile decision-package stage depends on X-02. Implementing or
enabling any production subprocess profile is hard-blocked until the owner selects its
executable/argv/policy contract from that package.

**Create/modify:** versioned execution profiles, allowlist matcher, receipt child-process
records, docs support matrix, black-like integration fixtures.

**RED:** allowed executable wrong digest, allowed basename at wrong path, argv wildcard
escape, env injection, child spawns grandchild, process cap, output bomb, network attempt,
write outside declared paths, undeclared compiler/shell, PATH shadowing.

**Implementation:** explicit executable digest/path, argv grammar, cwd, env allowlist,
filesystem/network policy, process tree cap, per-child resource ledger. No free-form shell
string and no repository-owned profile that can weaken base policy.

**Acceptance:** preregistered legitimate fixtures become decisive; every escape fixture
still fails; containment DEFER taxonomy and receipt show exact child chain; process-free
profile remains default.

**GREEN:** `.venv/bin/pytest tests/execution/test_profiles.py
tests/execution/test_linux_isolation.py tests/test_executor.py -q`, then the same external
red-team driver for every declared profile and §6. Test real bounded child/grandchild trees,
not only matcher strings.

**Rollback/reversal:** disable the affected subprocess profile and use process-free
execution or typed DEFER; retain child-chain receipts. Never broaden to shell strings,
PATH lookup, repository-owned policy, or an unrestricted executable.

**Boundary applicability:** all X-02 boundaries plus executable digest/argv/cwd/env/process
tree apply; receipt records the full child chain; manual/multiplicity/new-code cannot relax
profiles; remote infrastructure needs approval, paid model calls are N/A.

---

# Core scheduler

## S-01 — Scheduler seam and event schema

**Goal:** represent arbitrary evidence actions and outcomes without coupling them to
certification.

**Depends on:** M-01/M-03, C-01.

**Create:** `src/attest/scheduler/{types,policy,events}.py`; ledger schema adapters; tests.

**Types:** `SchedulerState`, `ActionKind`, tagged union `ScheduledAction =
TaskScopedDiscoveryAction | CandidateScopedEvidenceAction`, `ObservationKind`,
`EvidenceObservation`, `ActionOutcome`, `PolicyDecision`, `SelectionPropensity`, and
`DelayedLabel`.

**RED:** unknown action/outcome/version, missing cost/deadline/provider version, zero/invalid
propensity, a discovery action with a fake candidate, an evidence action whose candidate is
missing or belongs to another task, cross-task reservation/budget/observation replay, label
before candidate, duplicate settlement, certification type imported, and serialization
round-trip.

**Implementation:** immutable/versioned records; explicit missingness; candidate/evidence
scope for repository understanding, architecture decomposition, and cross-cutting impact,
plus Top-issue rank/rationale; task-scoped discovery versus same-task candidate-scoped
evidence binding; task-local reservation, remaining budget, observation, cost/latency,
model/prompt/tool/executor version, randomized propensity, and delayed-label provenance.
Add architectural import tests forbidding scheduler -> certification decision/presentation
dependencies and fail-closed property tests for `INV-SCHED-002`.

**Acceptance:** all current S/T/generator/executor actions can be losslessly represented;
shadow logging cannot alter calls; event stream reconstructs budget and outcome taxonomy.

**GREEN:** `.venv/bin/pytest tests/scheduler/test_types.py
tests/scheduler/test_events.py tests/test_budget_ledger.py -q`, then all scheduler/review
ledger tests and §6. Property tests must reject every cross-task combination and replay the
same task-local ledger to byte-identical state.

**Rollback/reversal:** disable scheduler event emission/consumption and retain the versioned
ledger for diagnosis; use the pre-scheduler deterministic flow or abstain. Never coerce an
unknown event or borrow another task's budget/reservation.

**Boundary applicability:** task/PR locality, cost, model/tool/executor versions, receipt-
only outcomes, manual/new-code typed states, and multiplicity context apply; no security
execution, remote write, or paid call is needed for schema GREEN.

## S-02 — Deterministic shadow baselines

**Goal:** establish real counterfactual baselines before a learned Core exists.

**Depends on:** S-01; M-01; R-03 when available.

**Create/modify:** scheduler policies for FCFS, S/T priority, and feasibility-aware priority;
CI shadow logger; benchmark replay and overlap diagnostics.

**RED:** shadow enabled/disabled must produce byte-equivalent execution/public output;
completion-order shuffle; deadline/cost tie; unsupported candidate; missing feature fallback.

**Implementation:** compute all baseline choices from the same immutable state, log ranks
and whether the chosen action was observed, never purchase an extra action outside an
approved audit slice.

**Acceptance:** no behavioral diff outside ledger; deterministic replay; enough overlap is
reported rather than assumed; synthetic 11.5–33% result is labeled simulation-only.

**GREEN:** `.venv/bin/pytest tests/scheduler/test_shadow.py
tests/test_ci_flow.py tests/benchmark/test_experiments.py -q`, then scheduler/CI/benchmark
tests and §6. Compare shadow-off/on output and executed-call manifests byte-for-byte across
completion-order permutations.

**Rollback/reversal:** disable the shadow logger/policies and keep execution on the frozen
current order; retain shadow events with policy version. No rollback may alter certification
or reinterpret the synthetic result as real.

**Boundary applicability:** task-local scheduling, propensities/overlap, correlated
models, receipt outcomes, PR multiplicity, new-code/profile strata, and cost apply; manual
evidence is observation-only; no extra paid/remote action outside approved audit slices.

## S-03 — Learned Core shadow policy

**Goal:** evolve Core into a contextual marginal-value scheduler for typed actions.

**Depends on:** S-01/S-02 and the data-readiness conditions in `G-SCHED-001`; no label
leakage.

**Create:** new scheduler learner/model modules and offline training command. Keep
`src/attest/core` regression-pinned; adapt reusable math only with provenance/tests.

**Features:** diff/project strata, candidate cluster/role, accumulated observations,
provider/model/prompt/tool versions, executor profile, cost, latency, remaining budget/
deadline. Do not use hidden truth at decision time.

**Actions/outcomes:** all S-01 types, including abstain. Model incremental decisive-receipt
yield and resource cost, not a truth probability used for publication.

**RED:** train/eval split leakage, repo leakage across folds, thin/unseen cell, missing
version, extreme base-rate shift, provider removal, delayed/MNAR labels, deterministic
fallback, serialization incompatibility.

**Implementation:** repo-grouped cross-fitting; hierarchical shrinkage; calibrated uncertainty;
versioned policy artifact and training-data digest; explicit applicability/overlap; fallback;
shadow-only integration.

**Acceptance:** reproducible training, fold isolation tests, calibration/overlap report,
no product behavior change, and no promotion claim before E-05.

**GREEN:** `.venv/bin/pytest tests/scheduler/test_learner.py
tests/scheduler/test_policy_artifact.py tests/test_regression_pins.py -q`, then scheduler/
core/benchmark tests and §6. Retraining from the same sealed digest must reproduce the
artifact; shadow on/off execution/public bytes remain equal.

**Rollback/reversal:** remove the learned artifact from the shadow registry and select the
versioned deterministic baseline or abstain; retain training/evaluation digests. Never use
the learner's score in Certification Kernel or public family selection.

**Boundary applicability:** repo-grouped truth separation, task-local actions, delayed/
MNAR labels, exact multi-model versions/correlation, receipt-only outcomes, cost, and
new-code/profile strata apply; training is offline; paid data collection needs approval;
remote writes/manual certification are N/A.

## S-04 — Randomized exploration and log-only monitor

**Goal:** obtain counterfactual data and detect drift without an unsafe automatic brake.

**Depends on:** S-03, approved budget, S-01 propensities.

**Modify/create:** stratified exploration policy, audit-slice budget, scheduler monitor,
ledger/reporting, canary and healthy-stream tests.

**RED:** propensity mismatch, exploration above cap, excluded trust class, randomization
not reproducible from committed seed protocol, monitor acting on publication, spend-share
alarm alone causing intervention, model-version drift pooled as healthy, audit receipt
entering the live `CertifiedFinding`/family set, or an audit result changing the ordinary
task's decision/public bytes.

**Implementation:** preregister strata/probability/cap; record exact propensity and policy
version; execute audit actions under the production security/receipt validator but persist
their result as a private `ShadowReceiptEvaluation` (or equivalently explicit non-public
type) that cannot be consumed by live certification selection or presentation; account
audit spend separately; monitor emits events only.

**Acceptance:** budget cannot be exceeded; propensity replay matches; monitor sensitivity
and false-alarm rates are measured; no intervention interface reaches certification or
presentation.

**GREEN:** `.venv/bin/pytest tests/scheduler/test_exploration.py
tests/test_exploration.py tests/test_monitor.py tests/scheduler/test_monitor.py -q`, then
scheduler/core/benchmark tests and §6. Seed replay must reproduce assignments/propensities;
mutation tests prove the monitor has no publication/certification call edge and that an
accepted audit receipt still cannot change normal execution, family selection, or any
author-visible byte.

**Rollback/reversal:** set exploration allocation to disabled, keep deterministic shadow,
and leave the monitor log-only or disable it; retain propensity/events. Never quarantine,
brake, or spend again on an ambiguously dispatched action during rollback.

**Boundary applicability:** approved task-local exploration budget, exact propensity,
model-version correlation, secretless audited execution, receipt-only outcome, PR
multiplicity, and new-code strata apply; manual labels are delayed outcomes only; paid/live
traffic and any remote integration require explicit authorization.

---

# Empirical gates

Taken together, E-* corpora must include every north-star dimension, and primary metrics
must report dimension coverage and Top-issue ranking quality; bug-local regression results
alone are insufficient.

## E-01 — Current-code natural-null safety

**Goal:** measure the actual false-confirm/publication mechanism on the exact candidate and
PR populations, not a constructed pre-fix sequence.

**Depends on:** M-01/M-02/M-03, C-01 through C-05, V-01 through V-03, and X-02 for
execution of repository code.

**Create/modify:** `src/attest/benchmark/natural_null.py`; a `natural-null` subcommand in
`scripts/benchmark.py`; `tests/benchmark/test_natural_null.py`; immutable protocol,
manifest, checkpoints, adjudication, and report schema under
`benchmarks/studies/e01-natural-null-v<N>/`.

**Prechange RED:** an offline preflight fixture must reject a manifest missing fixed sample
size/sequential rule, PR/repository clusters, strata, current code/policy/model/tool digests,
receipt-authority version, adjudication plan, or safety stop. It must reject importing the
historical 296 trials, outcome-aware replacement, duplicate PR/candidate IDs, and a report
that treats DEFER or an unadjudicated visible finding as a null success.

**Implementation/GREEN:** implement the population, sample, cluster, stratum, interval,
checkpoint, and stop-rule contract by referencing `G-NULL-001`, not copying its thresholds.
Run `.venv/bin/pytest tests/benchmark/test_natural_null.py tests/benchmark/test_metrics.py
-q`, then all benchmark tests and repository gates. Exercise a zero-cost offline fixture
end-to-end. The work-order checkbox remains open until an authorized frozen study produces
the complete Gate evidence bundle and passes `G-NULL-001`.

**Acceptance:** `G-NULL-001` plus `G-MEASURE-001` through `G-MEASURE-004`; construction
tests alone do not complete the empirical work order.

**Rollback/reversal:** no product path changes. Seal failed/insufficient study bundles as
immutable failed evidence, keep the current safety claim blocked, and start a new protocol
version rather than editing observations or exclusions.

**Boundary applicability:** receipt authority, PR multiplicity, semantic adjudication,
OS isolation, and paid-budget approval apply; manual evidence is excluded; new-code strata
may be measured only as typed abstention and cannot inherit regression certification.

## E-02 — Hidden semantic regression corpus

**Goal:** measure semantic precision and deployment detection on real regressions and
controls with truth invisible to the product.

**Depends on:** R-01/R-02/R-03, X-02/X-03 for supported profiles, and E-01 safety green.

**Create/modify:** `src/attest/benchmark/semantic_corpus.py` and
`semantic_matcher.py` (or versioned successors/adapters to current `corpus.py`/`matcher.py`);
`tests/benchmark/test_semantic_corpus.py` and `test_semantic_matcher.py`; a new immutable
`benchmarks/studies/e02-semantic-corpus-v<N>/` protocol/receipt/report directory.

**Prechange RED:** offline fixtures must reject location-only truth, product-visible hidden
tests/fix roles, missing polarity/eligibility labels, unresolved reviewer disagreement,
selectively absent visible findings, role leakage through filenames/metadata, reused
semantic cases counted as independent, or corpus receipts without authorized executions.

**Implementation/GREEN:** implement `G-MEASURE-004`, `G-CORPUS-001`, and
`G-RECALL-002`; truth names defect semantics rather than all changed lines. Run
`.venv/bin/pytest tests/benchmark/test_semantic_corpus.py
tests/benchmark/test_semantic_matcher.py -q`, all benchmark tests, then repository gates. A
blinded miniature fixture must round-trip before any paid run. Complete only after the
authorized hidden study passes the applicable gates with every attempt/exclusion retained
and every visible finding adjudicated.

**Acceptance:** `G-CORPUS-001`, `G-RECALL-002`, and `G-MEASURE-004`; no location-only or
receiptless metric counts.

**Rollback/reversal:** keep historical corpora readable but non-authoritative; a leaked or
invalid corpus version is permanently quarantined, never relabeled. Failure leaves corpus
claims blocked and requires a new blind version.

**Boundary applicability:** hidden-truth separation, receipt authority, OS profiles,
multiplicity, manual-evidence exclusion, paid/human authorization, and semantic new-code
stratification apply. This regression corpus does not certify the new-code class.

## E-03 — Heterogeneous operational stability

**Goal:** measure decision and delivery variance where a decision can actually change.

**Depends on:** E-02 cases and stable paid-call checkpointing.

**Create/modify:** `src/attest/benchmark/stability.py`, its CLI wiring in
`scripts/benchmark.py`, `tests/benchmark/test_stability.py`, and immutable
`benchmarks/studies/e03-stability-v<N>/` protocol/run/report artifacts.

**Prechange RED:** the protocol validator rejects an all-drawer/all-silence design, repeat
rows counted as independent semantic cases, reused writable state, missing case/repo IDs,
version drift pooled into one stratum, missing surface-versus-DEFER outcomes, or a report
that calls no-flip a success when no case could change decision.

**Implementation/GREEN:** implement the heterogeneous cases/repeats/strata in
`G-STAB-001`. Fresh state and fixed version strata are mandatory; repeats never enter the
accuracy denominator. Run `.venv/bin/pytest tests/benchmark/test_stability.py -q`, all
benchmark tests, and repository gates; then a zero-cost cassette dry run. Complete only
when the frozen authorized study passes `G-STAB-001`.

**Acceptance:** `G-STAB-001`; repeated runs remain operational observations and never
inflate semantic sample size.

**Metrics:** surface/non-surface and DEFER flip, semantic-cluster Jaccard, anchor dispersion,
candidate/receipt/cost/latency variance, repo/case-cluster intervals.

**Rollback/reversal:** no runtime policy changes. Preserve a failed/futile run bundle and
keep the stability claim blocked; changed cases or versions start a new protocol.

**Boundary applicability:** fresh-state/provenance and paid-call checkpoints apply;
security/profile strata are recorded; manual, multiplicity, and new-code fields are
reported where applicable but cannot be used to enlarge semantic n.

## E-04 — Prospective natural-PR shadow

**Goal:** measure safety, utility, cost, and latency on the distribution the product will
actually see, with no author-visible comments.

**Depends on:** E-01/E-02, X-02, C-* publication simulation, owner/participant authorization.

**Create/modify:** `src/attest/benchmark/prospective.py`, shadow-action integration that is
type-separated from presentation, `tests/benchmark/test_prospective.py`, and immutable
`benchmarks/studies/e04-prospective-v<N>/` protocol/authorization/sample/report artifacts.

**Prechange RED:** preflight rejects missing authorization, recommendation/sample selection
recorded after outcomes, zero/missing silent-PR inclusion probabilities, unweighted
certainty-included findings plus silent sample, product-dependent truth audit, unknown
truth treated as clean/no-opportunity, unadjudicated shadow findings, incomplete outcome
capture, or any author-visible side effect.

**Design/GREEN:** implement the authorized traffic, complete shadow-finding adjudication,
known-probability silent sampling, independent blinded defect audit, strata, propensities,
and version bindings in `G-SHADOW-001`. Run `.venv/bin/pytest
tests/benchmark/test_prospective.py -q`, all benchmark tests, repository gates, and a
zero-cost fixture proving shadow on/off publication identity. Complete only after the
authorized prospective study passes `G-SHADOW-001`; insufficient truth events remain
`INSUFFICIENT`, not a clean sample.

**Acceptance:** `G-SHADOW-001` and its prerequisite measurement/security gates; no remote
comment or author-visible finding is permitted by E-04.

**Metrics:** semantic precision, PR-any-wrong rate, eligible-defect detection, surface and
DEFER rate, p50/p95 final latency, status latency, cost, executor safety events, strata.

**Rollback/reversal:** disable the shadow collector, retain authorization/audit logs and
sealed partial evidence, and make no utility/safety claim. A compromised sample or truth
process requires a new protocol; it is never repaired by excluding outcomes.

**Boundary applicability:** no remote comments/writes; OS isolation, receipt validation,
PR multiplicity simulation, new-code strata, privacy/retention, human adjudication, and
separately approved paid budget all apply. Manual evidence remains a separate outcome.

## E-05 — Scheduler randomized comparison

**Goal:** decide whether Core should control execution order.

**Depends on:** S-04, E-02 and/or E-04 labeled population.

**Create/modify:** `src/attest/benchmark/scheduler_trial.py`, the corresponding
`scripts/benchmark.py` subcommand, `tests/benchmark/test_scheduler_trial.py`, and immutable
`benchmarks/studies/e05-scheduler-v<N>/` protocol/randomization/audit/report artifacts.

**Prechange RED:** reject cross-PR candidate pooling, transferred reservations/budget,
single-action PRs counted as ordering opportunities, unequal arm budgets/deadlines,
missing propensities, post-outcome assignment, insufficient randomized/paired PR clusters,
repository concentration above the Gate limit, or an audit slice chosen after outcomes.

**Design/GREEN:** implement the within-PR randomization/paired replay, cluster-power
preflight, candidate/event/PR minimums, strata, equal budgets/deadlines, and audit slice by
reference to `G-SCHED-002`. Run `.venv/bin/pytest
tests/benchmark/test_scheduler_trial.py -q`, all scheduler/benchmark tests, repository
gates, and deterministic offline replay. Complete only when the authorized trial passes
`G-SCHED-002`; otherwise Core remains shadow or deterministic priority wins.

**Acceptance:** `G-SCHED-001`, `G-SCHED-002`, `G-MEASURE-004`, and `G-MODEL-001` where
multiple model/version/role-policy cells are evaluated or deployed.

**Metrics:** verified true findings per dollar/executor-second, cost at fixed semantic
detection, deadline-induced DEFER, false publication, latency; paired/clustered intervals.

**Rollback/reversal:** switch execution order back to the frozen deterministic policy;
retain event propensities and sealed failed-trial evidence. Scheduler rollback cannot alter
certification, receipts, or publication selection.

**Boundary applicability:** `INV-SCHED-002`, receipt-only outcomes,
model/version/role-policy correlation and routing cells, PR multiplicity, OS-isolated
audited actions, and paid/randomization approval apply; manual and new-code outcomes are
separate strata, not transferable truth.

## N-01 — New-code evidence-contract decision packet

**Goal:** determine whether any falsifiable, safe evidence contract is worth implementing
for newly added code without selecting an LR or enabling publication.

**Depends on:** D-043, E-02 blind-semantic tooling, X-02/X-03 for supported execution
profiles, M-02 receipt authority, and explicit owner approval for the hidden pilot budget.

**Create/modify:** `src/attest/benchmark/new_code_contract.py`; a decision-packet subcommand
in `scripts/benchmark.py`; `tests/benchmark/test_new_code_contract.py`; immutable
`benchmarks/studies/n01-new-code-contract-v<N>/` alternatives, hidden-pilot manifest,
adjudication, receipts, analysis, and recommendation artifacts. It must not modify
Certification Kernel or public presentation code.

**Prechange RED:** the validator rejects a packet that reuses regression LR/base-pass
semantics, treats base-symbol absence/model agreement as truth, lacks an always-abstain
baseline or negative/control falsifier, leaks hidden truth, omits a compared alternative,
tunes after outcomes, excludes wrong/DEFER outcomes, or emits a numeric LR/public enablement.

**Implementation/GREEN:** encode at least the contract alternatives and complete pilot
design required by `G-NEWCODE-001`; implement blinded, multiplicity-aware, reproducible
comparison and the result enum `reject | collect_more | recommend_contract`. Run
`.venv/bin/pytest tests/benchmark/test_new_code_contract.py -q`, all benchmark tests, and
repository gates; then a zero-cost hidden-fixture dry run. Complete N-01 only when an
authorized evidence bundle passes `G-NEWCODE-001` and an independent reviewer reproduces
the packet. Even GREEN leaves production abstaining.

**Acceptance:** `G-NEWCODE-001` and `G-MEASURE-004`; this is decision readiness only and
cannot satisfy a certification or release gate.

**Rollback/reversal:** remove/disable only the research command, retain sealed evidence,
and keep `new_code_candidate` unpriced. A recommended contract requires an owner decision
and a newly scoped post-selection N-series work order whose ID is assigned only after that
decision; rejected alternatives cannot be revived by tuning a constant on the same data.

**Boundary applicability:** new-code, semantic truth, receipt authority, security profiles,
PR multiplicity, multiple-model correlation, paid/human authorization, and hidden-data
controls all apply; manual evidence and remote/public writes are forbidden.

---

# Release

## L-01 — First external pilot package

**Goal:** make the accepted system operable and reversible for a small authorized user set.

**Depends on:** every applicable component Gate referenced by `G-RELEASE-001`, excluding
the L-01 operational pass that this work order creates; owner authorization to prepare the
package and, separately before any live interaction, to run the private pilot dry-run. The
public release/marketplace/enable decision is post-L-01 and is not a prerequisite.

**Modify/create:** `docs/operations/{support-matrix,incident-response,pilot}.md`;
`src/attest/release/{policy,preflight,kill_switch}.py` or adapters at the resolved CLI/Action
seams; `scripts/release/drill.py`; `tests/release/test_preflight.py` and
`test_kill_switch.py`; installation/version docs, immutable action ref, base-policy
reference, privacy/retention policy, telemetry disclosure, cost controls, pilot protocol,
and final claim matrix.

**RED/acceptance drills:** revoked model credential, GitHub outage/rate limit, executor
unavailable, budget exhaustion, superseded PR, malicious same-repo change, receipt verifier
failure, rollback to prior action ref, ledger/artifact retention failure.

**GREEN:** the focused release tests and `scripts/release/drill.py --offline --all` prove
every drill reaches the declared safe state, the kill switch suppresses new work without
destroying evidence, and rollback resolves to the pinned prior artifact. Then run all
repository, security, and release gates. A real pilot dry run needs owner authorization;
the owner performs the separate publish/enable action.

**Acceptance:** `G-RELEASE-001`; every drill fails safely; no unsupported public claim;
action install ref is immutable; pilot repositories/participants authorize shadow or
comments. New-code remains explicitly unsupported unless the separate post-N-01 path has
passed its own gates.

**Rollback/reversal:** activate the tested kill switch, stop dispatching new jobs, keep
receipts/ledger artifacts readable, pin users to the last known safe immutable action, and
notify only the authorized pilot cohort under the incident plan. Rollback never downgrades
receipt validation or isolation.

**Boundary applicability:** all security, receipt, manual-evidence, PR multiplicity,
new-code capability, remote-write, privacy/retention, incident, and production-budget
boundaries apply; no `N/A` is permitted for L-01.

## 6. Standard verification commands

Use the repository environment/lock selected by M-03. On the current POSIX checkout the
intended gates are:

```bash
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src/attest
.venv/bin/pytest --cov=src/attest --cov-report=term-missing
git diff --check
```

Do not report a historical test count as current evidence. Report the command, code SHA,
environment/lock digest, timestamp/clock mode, pass/fail counts, and any pre-existing
failure. Security, corpus, paid, and prospective tasks add the phase-specific commands and
artifacts from the acceptance document.
