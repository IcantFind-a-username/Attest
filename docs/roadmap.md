# Evolution roadmap

Status: **normative execution order**

Roadmap epoch: 2026-08-30

Baseline: `main@c945788` before the evolution scaffold

## 1. Destination

Attest's durable product direction is governed only by the
[Product north star](../AGENTS.md#product-north-star). This roadmap owns dependency order
and status; it does not redefine that outcome.

The delivery architecture retains this separation:

```text
Discovery -> Evidence Scheduler/Core -> Evidence Executors
                                      -> Certification Kernel -> Presentation
                         outcomes/labels/costs -> Scheduler learning
```

Core is activated only as a shadow evidence scheduler and later, if measured, as an
execution-order controller. It is never a voter or certifier. Public speech is controlled
only by a trusted, claim-bound differential receipt and a PR-level publication policy.

The north star does not change the current sequence: Phase 0's trusted-measurement
prerequisite and C-01's pure certification domain are complete, while receipt-only product
routing remains the next evidence-safety boundary rather than the product goal.
S-01 and all later evaluations must cover repository understanding, architecture
decomposition, cross-cutting impact, and Top-issue prioritization. Current BugsInPy and
local-regression metrics are bounded evidence and cannot establish that product outcome.

The architecture contract is
[`architecture/target-algorithm.md`](architecture/target-algorithm.md). Exact work orders
are in [`implementation/agent-work-orders.md`](implementation/agent-work-orders.md).
Quantitative gates are in [`acceptance/evolution-gates.md`](acceptance/evolution-gates.md).

## 2. Honest baseline

### 2.1 Implemented

- fixed S/T/V review pipeline and ledger;
- generated Python reproduction with head/base detached worktrees and N=3 repeats;
- evidence classes for regression reproduced, not reproduced, unfaithful, new code, and
  indeterminate;
- GitHub Action smoke acceptance on regression/control/new-code fixtures;
- generic benchmark/replay/live/stability/experiment infrastructure;
- frozen 20-pair metadata corpus and historical hash-bound receipt with 9/20
  receipt-validated pairs;
- 761-test inventory at the historical overnight timestamp, with coverage/ruff/mypy gates
  then reported green;
- synthetic evidence that S/T priority can save verification budget under its assumptions.

### 2.2 Not established

- no defensible real-world precision, recall, or PR-level false-publication rate;
- no proof that the current product wealth is an e-process;
- no current-code replication of the historical 0/296 null result at comparable size;
- no semantic truth corpus hidden from the product;
- no production security boundary for same-repository head code;
- no scheduler operating in the product path;
- no safe publication contract for new-code defects;
- no prospective natural-PR result;
- no release readiness.

All five historical bug-replay attempts DEFERred and surfaced delivery was 0/5; finding
precision and recall were not estimable under the repository's own scoring contract. The
controls were silent 4/4, a small smoke result rather than a useful FPR bound.

### 2.3 Immediate hazards

These are P0 even though many happy-path tests pass:

1. the runtime does not enforce “no differential receipt, no speech” for all alpha/config
   values;
2. head configuration may relax policy;
3. manual reproduction can share the automated V accounting path;
4. receipts lack sufficient execution and semantic provenance;
5. the configured inline limit is not a hard cap across every author-visible surface.

## 3. Program rules

1. **Safety contract before recall.** Recall work may run in offline/shadow mode, but it
   cannot reach public presentation until receipt-only publication is structural.
2. **Instrumentation before adaptation.** Scheduler work starts only after event,
   propensity, cost, and mixed-outcome accounting are trustworthy.
3. **Interfaces before migrations.** Add versioned domain types/adapters, then move one
   caller at a time; do not rewrite `review`, `core`, and `benchmark` together.
4. **Shadow before control.** A learned scheduler must first log counterfactual choices,
   then pass replay/randomized gates, then control order; it never controls certification.
5. **Class-specific evidence.** Existing-code regression and new-code defects have
   different counterfactuals and never share a guessed constant.
6. **No result without an evidence bundle.** Headline numbers require trial-level,
   content-addressed artifacts tied to code/model/tool versions and a fixed protocol.
7. **One task, one reviewable change.** Each work order has a focused RED, a minimal GREEN,
   adjacent regression tests, and an independent review checkpoint.
8. **Stop conditions are outcomes.** A phase that fails its gate produces a decision
   package; it does not lower the gate or rename abstention as success.

### NOW / NEXT / LATER

| Horizon | Work | Why now |
|---|---|---|
| **NOW** | owner fixes 1-5 of 2026-09-03 (generator/provider honesty, empty-sample classification, import bootstrap, generator context, local differential stage), then the paid re-runs (a) and (b), then X-02 (mainline §2 step 11) with the environment bootstrap folded into the container adapter | the us-stock-helper trials showed every candidate correct and every one silent for generator and bootstrap reasons; X-01 is done and X-02/V-03 follow the fixes |
| **NEXT** | remaining C/V/X work in dependency order | make receipt-only publication structural, define an authenticated execution channel, and upgrade differential behavior into a real certificate |
| **PARALLEL AFTER SEAMS** | S-01/S-02 shadow instrumentation | it can collect/log without changing certification once measurement and type boundaries exist |
| **LATER** | R-*, X-02/X-03, S-03/S-04, E-*, N-01, L-01 | recall, learned scheduling, class-specific new-code research, and release require the safety/instrumentation spine first |
| **LATER (proposal)** | a TypeScript executor (vitest/jest differential reproduction) — decision package in `implementation/typescript-executor-decision-package.md`; work-order number is the owner's | it reuses the X-01 protocol and the certification kernel unchanged; only the job, the coverage source and the image are language-specific; placed after L-01 |

C-01 through C-04, R-03, R-01 and V-01 are complete. `mainline.md` fixes the working order from here to L-01; the E-02 pilot is next.
V-01 follows R-03 and R-01 rather than preceding them, because the pilot measurement needs
candidates before it needs richer receipts. The follow-on V-funnel implementation through `e0f2db0` added complete
per-candidate run evidence and a reproduction-only 3,000-token cap. It did not change runner
policy or measure the post-change truncation rate. D-057 blocks only another paid V-funnel
replay or a runner-policy change pending owner direction; it does not block C-02 or V-01.
Core is not the next direct production switch.

## 4. Dependency graph

```text
F-00 -> M-01, M-02, M-03
M-01 + M-02 + M-03 -> C-01
C-01 + M-01 -> C-02
C-01 + C-02 -> C-03, C-04
C-02 -> C-05 decision-package stage -> owner family-policy selection
owner family-policy selection -> C-05 implementation/acceptance stage
C-01 -> V-01
V-01 + C-01 -> V-02 comparison/decision-package stage
owner binding-policy selection -> V-02 implementation/acceptance stage
V-01 + C-01 -> X-01
V-01 + M-03 + X-01 -> V-03

M-01 + M-03 + C-01 -> S-01 -> S-02
S-01 + S-02 + full G-SCHED-001 data readiness -> S-03
S-03 + approved exploration budget -> S-04

C-02 + C-03 -> R-01
M-03 + V-01 -> R-02
R-01 + C-05 cluster schema -> R-03
R-01 + R-02 + R-03 + S-01 + C-02 -> R-04

X-01 + V-03 + owner backend decision -> X-02
X-02 -> X-03 profile decision-package stage
owner subprocess-profile selection -> X-03 implementation/acceptance stage

M-01 + M-02 + M-03 + C-01..C-05 + V-01..V-03 + X-02 -> E-01
E-01 + R-01 + R-02 + R-03 + X-02 + X-03 -> E-02
E-02 + M-03 -> E-03
E-01 + E-02 + X-02 + C-01..C-05 + authorization -> E-04
S-04 + (E-02 or E-04 labeled population) -> E-05
E-02 + X-02 + X-03 + M-02 + owner pilot approval -> N-01
applicable component gates + owner authorization to prepare/pilot-dry-run -> L-01
L-01 + G-RELEASE-001 evidence -> separate owner public-release/enable decision
```

These are exact hard work-order or explicitly named intra-work-order stage dependencies;
phase entry/exit gates below are additional barriers, and owner decisions/authorizations
shown here are not implied. Decision-package stages may prepare alternatives, but the same
work order cannot implement or pass acceptance until the named owner selection. “C-01..C-05”
means each named work order, not an undocumented phase shortcut. R-03 may enrich S-02 later
but is not a hard prerequisite for the first deterministic shadow baseline. Parallel work
is allowed only across independent branches and non-overlapping file sets. One writer owns
a file set until handoff.

## 5. Phase 0 — truth and measurement foundation

Goal: make repository instructions and measurements impossible to misread before behavior
changes.

Status: **complete** — F-00 and M-01 through M-03 have their required evidence and Gates.

### Work orders

- [x] **F-00 — evolution scaffold.** Target architecture, roadmap, work orders, Gates,
  current-truth boundary, and decisions passed `G-DOC-001`; evidence is recorded in
  [`acceptance/2026-08-30-evolution-scaffold.md`](acceptance/2026-08-30-evolution-scaffold.md).
- [x] **M-01 — author-visible outcome accounting.** Final implementation `5efe3d1`
  separates task status, finding accuracy, PR harm, and delivery so every public finding
  remains scored beside DEFER. The fixed-SHA 20-process measurement, final P0=0/P1=0
  review, and fresh Python 3.11/3.12 `G-MEASURE-001` / `G-CODE-001` recovery Gates are
  bound by the
  [`2026-08-31 recovery acceptance`](acceptance/2026-08-31-m01-task5-recovery.md).
- [x] **M-02 — receipt authority and raw validation evidence.** Reject incomplete/manual
  validation rows, retain bounded fixed/buggy run evidence, and distinguish integrity,
  provenance, and semantic authority. Integrated implementation `14a57fb` passed fresh
  Python 3.11/3.12 `G-MEASURE-002`, `G-CODE-001`, and `G-CODE-002` Gates with final
  contract/security/manifest review P0=0/P1=0; see the
  [`2026-08-31 integration acceptance`](acceptance/2026-08-31-m02-m03-integration-revalidation.md).
  The original [`2026-08-30 report`](acceptance/2026-08-30-m02-validation-receipts.md)
  remains **BLOCKED BY EVIDENCE** historical proof of its then-failing branch Gate.
- [x] **M-03 — deterministic and crash-safe measurement.** The role-bound implementation
  `bce13f0` passed fresh Python 3.11/3.12 Gates and a new independent review with
  P0=0/P1=0; see the
  [`2026-08-31 acceptance`](acceptance/2026-08-31-m03-role-revalidation.md). The
  earlier `81bf625` PASS remains explicitly INVALIDATED historical evidence. Integration
  SHA `14a57fb` revalidated M-03 while versioning comparison/live/stability state; see the
  [`integration acceptance`](acceptance/2026-08-31-m02-m03-integration-revalidation.md).

### Entry

- clean understanding of `main@c945788` behavior;
- no factory constant changes;
- no paid calls.

### Exit

Required gates: `G-DOC-001`, `G-MEASURE-001`, `G-MEASURE-002`, `G-MEASURE-003`, and
`G-CODE-001`; M-02's receipt-authority boundary also requires `G-CODE-002`.

- all author-visible outcomes survive scoring regardless of DEFER;
- an incomplete two-field `validated` receipt row is rejected;
- full test gates are date-independent and reproducible in the supported toolchain;
- a crash after each paid-call boundary cannot silently repeat or erase cost;
- documents and metadata contain no active e-process claim for the product wealth.

### Stop conditions

- a compatibility change would silently reinterpret committed benchmark results;
- the event schema cannot distinguish historical rows from new authoritative rows;
- fixing checkpoint semantics requires provider support not available in the current API.

In each case, version the protocol and preserve old rows instead of coercing them.

## 6. Phase 1 — Certification Kernel v2

Goal: make the publication contract true by construction for every supported configuration.

### Work orders

- [x] **C-01 — versioned certification domain.** Implementation `e955f29` adds frozen
  task/policy/subject/receipt/result types, a pure exhaustive validator, and an unimplemented
  C-05 selection protocol under `attest.certification`. It passed the C-01 portion of
  `G-CERT-001`, field-by-field `G-CODE-002` mutation guards, P0=0/P1=0 self-review, and the
  single-Python `G-CODE-001` Wave 6 Gate; exact evidence is in
  [`overnight-handoff.md`](overnight-handoff.md). It has no presentation caller and does not
  claim C-02 or the full publication invariant.
- [x] **C-02 — receipt-only speech.** Implementation `383ee65` routes every non-discarded
  candidate through differential execution and the C-01 validator; CI, the CLI report and
  GitHub presentation consume only `CertifiedFinding`. The S/T direct-surface path is
  deleted and replaced by a negative `G-CERT-001` regression over alpha 0.15/0.4 with and
  without auto-tighten and cap variants (D-058: one RED, no exhaustive property matrix).
- [x] **C-03 — merge-base and base-owned policy.** Implementation `fc1ae04` (+ `248adfb`) resolves the
  event merge-base (DEFER when unavailable), loads the destination policy from the committed
  `.attest.toml` at that commit or factory defaults with protected Action inputs on top,
  digests source and values into the task and every receipt, and revalidates HEAD before
  publication. One RED: a head that sets alpha 1.0 while the base advances runs under
  factory alpha, reviews only the merge-base diff, and verifies against the merge-base.
- [x] **C-04 — self-report separation.** Implementation `71b99aa` records manual
  reproductions as `self_report` rows, marks S/T review rows `authority: ranking`, keeps
  legacy `verified_*` rows readable in `legacy_self_reported_unknown`, and excludes all of
  them from the surfaced population, precision, and alpha tightening. One RED: a manual
  `--reproduced` moves no finding, no precision window, and no alpha.
- [x] **C-05 — PR family and hard-publication policy** (implementation `2b3d4c9`, D-081;
  owner selected mainline §5 A; RED
  `test_pr_family_policy_caps_publication_and_counts_a_defect_once`). Choose and implement a PR-level
  multiplicity method, a minimal order-invariant semantic-cluster seam, deterministic
  tie-breaks, and a true author-visible cap across inline and summary surfaces. R-03 may
  extend later discovery clustering but cannot supply this prerequisite after the fact.

### Entry

- Phase 0 measurement contract green;
- owner approves the chosen C-05 family policy before implementation of its statistical
  rule; agents may prepare alternatives first.

### Exit

Required gates: `G-CODE-001`, `G-CODE-002`, and `G-CERT-001` through `G-CERT-004`.

- `published -> accepted current receipt` holds across every allowed alpha/config/state;
- a PR that changes `.attest.toml` cannot weaken destination policy;
- `attest verify --reproduced` cannot manufacture an automated certificate;
- no GitHub/API path publishes more than the hard cap;
- PR-level safety exposure is reported with the selected multiplicity method;
- existing historical ledger remains readable with explicit legacy semantics.

### Stop conditions

- any presentation caller can still accept `GateResult` or raw wealth;
- any policy field is sourced only from head;
- the chosen multiplicity method cannot explain the meaning of alpha at PR level;
- a compatibility shortcut relabels a manual event as a differential receipt.

## 7. Phase 2 — receipt semantic integrity

Goal: upgrade “head fails/base passes” into a replayable, claim-bound certificate.

### Work orders

- [x] **V-01 — exact-node execution evidence** (implementation `cf5c356`, D-077; RED
  `test_accepted_receipt_verifies_offline_and_any_flipped_byte_rejects`). Version the
  reproduction schema and bundle
  exact test bytes, node ID, collection count, zero skip/xfail, per-run JUnit/output,
  commands, interpreter/environment/executor digests, and immutable revisions.
- [x] **V-02 — semantic and causal binding** (implementation `dd99320`, D-083; RED
  `test_differential_test_that_never_executes_a_changed_line_is_not_a_regression`; the
  `G-SEM-002` preregistered pilot remains open). Compare trace/coverage/mutation/patch-ablation
  alternatives on adversarial tests; adopt the smallest binding policy that rejects tests
  proving another bug or source-version branching.
- [x] **X-01 — content-addressed execution protocol.** Split privileged controller from
  executor through a versioned request/result protocol with task nonce, immutable artifact
  digests, development adapter, and a result-verification seam. Done 2026-09-03 (see
  Progress; the RED is `tests/execution/test_controller.py::test_result_answering_another_nonce_is_rejected`;
  origin authentication of the envelope is V-03).
- [x] **V-03 — fresh-state and provenance envelope.** Give every repeat a fresh writable
  state; persist each run atomically; sign or otherwise authenticate controller provenance;
  provide an offline receipt verifier. Done 2026-09-03 (see Progress; the RED is
  `tests/execution/test_fresh_repeats.py::test_a_run_started_on_stale_state_is_rejected_by_the_verifier`;
  the seal is an HMAC under a repository-local controller key, a public-key trust root is a
  later version).

### Entry

- C-01 pure kernel exists;
- C-02 routes publication through the kernel;
- no new evidence class is priced.

### Exit

Required gates: `G-CODE-001`, `G-CODE-002`, `G-MEASURE-002`, `G-MEASURE-003`,
`G-SEC-001`, and `G-SEM-001` through `G-SEM-003`.

- zero-test, multi-test, skip, xfail, stale-node, version-conditional, unrelated-defect,
  base-imports-head, and mutable-state adversarial fixtures all reject;
- every accepted receipt can be replayed from its artifact manifest without secrets;
- modifying claim, hunk, test, SHA, policy, environment, or any accepted run invalidates
  the receipt;
- current regression fixtures still certify through the new type, not through an adapter
  escape hatch.

### Stop conditions

- causal binding rejects legitimate supported regressions at a rate that prevents the
  preregistered pilot gate;
- a platform cannot provide provenance stronger than same-user writable JSON;
- evidence bundles expose source secrets or unbounded output.

## 8. Phase 3 — recall and reproduction robustness

Goal: increase the number of eligible candidates that reach a decisive receipt without
weakening the kernel.

### Work orders

- [x] **R-01 — semantic diff/context planner** (implementation `3fe6c1b`..`8d9394c`, D-076;
  the cross-file RED `test_cross_file_defect_context_contains_the_unchanged_caller` and a
  five-PR real-corpus trial). Merge-base chunks, old-side deletion
  anchors, renames, definition/caller/test retrieval, language/project profiles, and
  per-chunk budgets.
- [x] **R-02 — structured-output recovery** (implementation `4db546c`, D-080; RED
  `test_truncated_sample_is_salvaged_and_unusable_sample_gets_one_cached_repair`; pulled
  forward by the D-078 fork). Separate schema/collection repair from
  behavioral execution; precommit retry counts and visibility; cache by immutable digest;
  forbid outcome-aware retries.
- [x] **R-03 — deterministic dedup and eligibility** (implementation `36dc85b`, D-075; taken
  before R-01/C-05 per `mainline.md` §2 with a minimal cluster schema C-05 may version).
  Replace order-dependent greedy
  clustering; retain provenance; classify regression/new-code/non-Python/executor-profile
  feasibility before expensive generation.
- [ ] **R-04 — feasibility-aware priority.** Use deterministic S/T plus predicted execution
  feasibility to order V work within deadlines; record counterfactual FCFS and cost.

### Entry

- Phase 1 publication invariant green;
- V-01 evidence bundle available so improvements are measurable;
- fixed replay protocol and no paid-call retry ambiguity.

### Exit

Required gates: `G-CODE-001`, `G-RECALL-001`, and `G-RECALL-002` when the hidden
semantic corpus is executed.

- structured generation, decisive execution, and eligible-regression detection meet their
  canonical acceptance gates;
- null false-confirm bounds do not degrade;
- new-code and unsupported-language abstentions remain separate, visible strata;
- no retry policy conditions on observed head/base behavior unless the entire policy is
  separately calibrated.

### Stop conditions

- recall rises only by increasing wrong or semantically unbound receipts;
- prompt/context changes make artifact provenance irreproducible;
- costs exceed the preregistered phase cap before the minimum sample is reached.

## 9. Phase 4 — secretless isolated execution

Goal: run project code with an actual operating-system boundary and regain selected real
test idioms safely.

### Work orders

- **Foundation dependency:** X-01 is completed in Phase 2 before V-03; Phase 4 must use that
  protocol and may not invent a second result channel.
- [x] **X-02 — OS isolation backend.** Implement and threat-test one production Linux
  backend with no secrets, default-deny network, read-only source, bounded writable space,
  cgroup/process/resource limits, and authenticated results. Done 2026-09-03 as
  `linux-container-v1` (see Progress; the RED is `tests/execution/test_linux_isolation.py`
  in real containers; result authentication is V-03; `G-SEC-002`'s full red-team matrix on
  the declared CI platform remains open).
- [ ] **X-03 — controlled subprocess profiles.** Add digest/argv allowlists for legitimate
  tools and child-process containment; keep process-free default and typed DEFER.

### Entry

- X-01 protocol and V-03 authenticated provenance pass `G-SEC-001`/`G-SEM-003`;
- owner approves the production platform/backend selection;
- red-team fixtures and secret canaries exist before implementation.

### Exit

Required gates: `G-CODE-001`, `G-CODE-002`, `G-SEC-001`, `G-SEC-002`, and
`G-SEC-003`.

- untrusted code cannot read controller/model/GitHub credentials in adversarial tests;
- raw sockets and undeclared processes fail below Python-level monkeypatches;
- filesystem escape, `/proc`/host-env discovery, checkout credential access, fork bombs,
  cgroup escape attempts, and result spoofing are blocked or fail closed;
- declared black-like shelling cases can run within a bounded profile;
- every child and resource limit appears in the receipt;
- cross-repository/fork trust classes have explicit supported or skipped behavior.

### Stop conditions

- CI platform cannot supply the required kernel boundary;
- the result channel can be forged by the job under test;
- enabling subprocesses broadens access outside the declared executable/profile.

## 10. Phase 5 — Core as shadow evidence scheduler

Goal: learn which next action buys a decisive trusted receipt most efficiently, without
changing publication safety.

### Work orders

- [ ] **S-01 — scheduler seam and event schema.** Add typed state/action/observation,
  reservation, propensity, outcome, cost, latency, version, and delayed-label records.
- [ ] **S-02 — deterministic shadow baselines.** Log FCFS, current S/T priority,
  feasibility-aware priority, and exhaustive-audit counterfactuals without controlling
  execution.
- [ ] **S-03 — learned Core shadow.** Build a contextual/hierarchical policy for arbitrary
  actions; version models/prompts; cross-fit; use deterministic fallback; preserve old
  `attest.core` regression pins.
- [ ] **S-04 — randomized exploration and monitor.** Add a capped, preregistered exploration
  slice and a log-only drift monitor; do not quarantine or brake publication.

### Entry

- Phase 0 event/cost accounting green;
- C-01 ensures scheduler scores cannot enter certification;
- the data-readiness threshold in `G-SCHED-001` before learned-policy evaluation;
- exploration budget separately approved.

### Exit for shadow completion

Required gates: `G-CODE-001` and `G-SCHED-001`. Promotion to execution-order control also
requires `G-SCHED-002`; any intervention requires `G-SCHED-003`.
Evaluating or deploying more than one model, version, or role policy also requires
`G-MODEL-001`; only one frozen model/version/role is N/A.

- every scheduled action has the versioned fields required by `G-SCHED-001`;
- shadow choices cannot alter execution or presentation in property tests;
- off-policy/replay estimates are repo-clustered and pass overlap diagnostics;
- learned policy beats neither baseline by claim alone; it advances only through E-05;
- monitor specificity/sensitivity are reported, with intervention disabled.

### Stop conditions

- action propensities are absent or zero where evaluation needs overlap;
- labels leak from the evaluation fold into policy training;
- provider/model upgrades are pooled without version strata;
- a scheduler score affects certification or publication selection.

## 11. Phase 6 — empirical calibration and utility

Goal: replace constructed anecdotes and synthetic assumptions with preregistered,
replayable evidence on the current code.

### Work orders

- [ ] **E-01 — natural-null safety study.** Execute the current-code, cross-repository
  protocol required by `G-NULL-001` with full v2 receipts.
- [ ] **E-02 — hidden semantic corpus.** Execute blind semantic truth, control, precision,
  and eligible-detection protocols in `G-MEASURE-004`, `G-CORPUS-001`, and
  `G-RECALL-002`.
- [ ] **E-03 — heterogeneous stability.** Execute the nontrivial repeated-case design in
  `G-STAB-001`; repeats remain operational only.
- [ ] **E-04 — prospective natural-PR shadow.** Execute the authorized traffic, blind
  adjudication, silent sampling, safety, utility, cost, and latency design in
  `G-SHADOW-001`.
- [ ] **E-05 — scheduler randomized comparison.** Execute the within-PR treatment and
  audit-slice design in `G-SCHED-002`; cross-PR pooled ranking is forbidden.
- [ ] **N-01 — new-code evidence-contract decision packet (owner-gated, no pricing).**
  Compare falsifiable class-specific counterfactuals on a hidden new-code/control pilot,
  preserve the always-abstain baseline, and produce only `reject`, `collect_more`, or
  `recommend_contract` under `G-NEWCODE-001`. This work order cannot choose an LR or enable
  publication.

### Entry

- the exact implementation under study is frozen and identified;
- sample size, strata, exclusions, retry rules, primary metrics, stopping rules, and cost
  cap are preregistered;
- artifact storage and blinded truth access are tested;
- paid budget and human adjudication capacity are approved.

### Exit

Required gates: `G-CODE-001`, `G-NULL-001`, `G-CORPUS-001`, `G-RECALL-002`, `G-STAB-001`,
`G-SHADOW-001`, `G-MEASURE-004`, `G-SCHED-002`, and `G-NEWCODE-001` for the claims,
promotions, or owner decisions each governs.

Every study independently satisfies its gate in the acceptance document. Failing one gate blocks
only the claim/promotion it governs, but cannot be averaged away by another study.

### Stop conditions

- artifacts or truth blindness are compromised;
- code/model/prompt changes mid-study without starting a new stratum;
- outcome peeking changes sample size or retries outside the preregistered rule;
- the cost cap is reached before minimum n;
- safety stop threshold is reached.

## 12. Phase 7 — first external pilot and release decision

Goal: admit real users only after product safety, isolation, usefulness, and operability are
measured together.

### Work orders

- [ ] **L-01 — release candidate.** Stable install ref, minimal quickstart, base-owned
  policy docs, executor support matrix, privacy/retention policy, failure-mode copy,
  rollback/kill switch, and private-user pilot.

### Mandatory prerequisites

- every applicable component Gate referenced by `G-RELEASE-001` is green; its L-01
  operational pass is the phase exit, not an entry prerequisite;
- learned scheduler may remain shadow; if it controls order, `G-SCHED-002` must pass;
- no active P0/P1 security or receipt-integrity defect;
- development and production cost limits are distinct and enforced;
- owner authorizes preparation of the release package; any live private-pilot interaction
  separately requires owner and participant/repository authorization. Public publication,
  marketplace listing, and general enablement remain post-L-01 owner actions;
- the capability matrix remains regression-only for public findings unless a post-N-01
  implementation work order—assigned an ID only after owner contract selection—and all
  class-specific certification/null/corpus/shadow gates have separately passed; N-01 alone
  never enables new-code speech.

### Exit

- `G-RELEASE-001`, including its L-01 operational pass, is green;
- private pilot has an incident/rollback path and no unreviewed secret boundary;
- published claims use only language permitted by completed gates;
- pilot-readiness and reversal conditions are logged in `DECISIONS.md`;
- the final public release/enable decision remains a separate owner action after L-01.

## 13. Decision points

Agents should prepare evidence packages for these decisions instead of guessing:

| Decision | Earliest point | Required package |
|---|---|---|
| PR-level multiplicity method | C-05 | alternatives, semantics of alpha, replay effects, property tests |
| causal binding policy | V-02 | adversarial rejection and eligible-regression recall comparison |
| production isolation backend | X-02 | threat model, supported CI platform, escape tests, operating cost |
| controlled subprocess profiles | X-03 | real project cases, allowlist design, escape tests, DEFER trade-off |
| learned scheduler controls order | after E-05 | randomized/paired benefit with no safety regression |
| new-code evidence contract | after N-01 / `G-NEWCODE-001` | falsifiable alternatives, hidden pilot, null/semantic/cost/security comparison; owner selects or rejects, never an LR from N-01 |
| public release | after L-01 | all mandatory gates, support/rollback/privacy/cost evidence |

## 14. Risk register

| ID | Risk | Impact | Primary controls / owner |
|---|---|---|---|
| `RISK-CERT-01` | S/T/config/manual path publishes without receipt | P0 wrong public claim | C-01/C-02/C-03/C-04; `G-CERT-001`, `G-CERT-002`, `G-CERT-003` |
| `RISK-FAMILY-01` | candidate multiplicity or overflow amplifies PR harm | P0/P1 safety and false product promise | C-05; `G-CERT-004`, `G-NULL-001` |
| `RISK-MEASURE-01` | mixed DEFER erases author-visible FP/TP | P0 false precision | M-01; `G-MEASURE-001` |
| `RISK-RECEIPT-01` | hash-consistent but fabricated/incomplete evidence | P0 false certificate/evaluation | M-02, V-01/V-03; `G-MEASURE-002`, `G-SEM-001`, `G-SEM-003` |
| `RISK-SEMANTIC-01` | test proves another defect or branches on source version | P0 wrong semantic claim | V-02; `G-SEM-002` |
| `RISK-SEC-01` | head code reads secrets, reaches network, or forges results | P0 credential/remote compromise | X-01/X-02/X-03; `G-SEC-001` through `G-SEC-003` |
| `RISK-RECALL-01` | safety is achieved only by near-total abstention | product has no utility | R-* and E-02/E-04; `G-RECALL-001`, `G-RECALL-002`, `G-SHADOW-001` |
| `RISK-NEWCODE-01` | pressure to cover new code invents an LR without a counterfactual | P0 false certification in dominant PR class | D-043, N-01, `G-NEWCODE-001`; assign a post-selection implementation ID only after owner choice |
| `RISK-SCHED-01` | Core learns selection bias or cross-PR impossible allocation | wasted cost/incorrect promotion | S-01/S-04/E-05; `INV-SCHED-002`, propensities, and `G-SCHED-001` through `G-SCHED-003` |
| `RISK-DRIFT-01` | provider/model/prompt/tool changes invalidate pooled calibration | silent quality decay | M-03/S-01/S-04; version strata and log-only monitor |
| `RISK-COST-01` | crash/retry duplicates paid calls or study cannot finish in cap | financial/measurement invalidity | M-03; `G-MEASURE-003` |
| `RISK-EXTERNAL-01` | one project/reverse-fix corpus is generalized to natural PRs | misleading product claim | E-02/E-04; `G-CORPUS-001`, `G-SHADOW-001` |
| `RISK-DOC-01` | old plan/status becomes active agent authority again | reimplementation of known defects | F-00/D-044; `G-DOC-001` |

Any P0 risk observed in a public/shadow/security study triggers the corresponding Gate stop
rule. Risk severity is not reduced because the system abstained elsewhere.

## 15. Progress update protocol

Only this file owns phase status.

When a work order completes:

1. change its checkbox only after all required artifacts and independent review exist;
2. add the implementing commit(s) and evidence-bundle path under a dated `Progress` entry;
3. record material trade-offs in `DECISIONS.md`;
4. do not rewrite historical result files;
5. if a gate fails, record `FAILED` or `BLOCKED BY EVIDENCE` with the measured reason;
6. never mark a phase complete from test count alone.

### Progress

- **2026-09-03 — L-01, owner-free parts:** one commit
  (`feat: base-owned kill switch and the L-01 operations documents`). New
  `docs/operations/`: quickstart (fresh clone to a verified comment or an explained
  silence), executor support matrix, failure-mode copy, kill switch and rollback, privacy
  and retention draft. The kill switch is `enabled = false` in the base branch's
  `.attest.toml`; the RED failed on the unpatched path (the key was unknown and the review
  ran) and passes after: base disabled, head re-enabled, zero provider calls, an explicit
  final status. Publication, the pilot repository and the retention defaults remain the
  owner's (mainline §5 D); the quickstart's verbatim execution on an outside repository is
  the L-01 RED and waits for that repository. See D-099.

- **2026-09-03 — item 7 (finding as test):** one commit
  (`feat: present a verified finding as its runnable test with runs, logs and the bundle`).
  The RED failed on the unpatched path (the comment carried a test node id but no test) and
  passes after: the test and command copied out of the PR comment fail on head and pass on
  base. See D-098.

- **2026-09-03 — V-03 complete:** one commit
  (`feat: fresh writable state per run, a controller seal on every bundle, and the offline verifier (V-03)`).
  The RED failed on the unpatched path (run records carried no freshness evidence and the
  verifier accepted a rewritten record) and passes after: a bundle whose run record says the
  writable state was not fresh is rejected offline; the controller creates the outputs
  directory empty for every run and names what it removed; every accepted bundle is sealed
  with HMAC-SHA256 under `.attest/controller.key` (mode 0600, outside every executor mount);
  a seal made with another key or naming another bundle rejects; `attest verify --bundle DIR
  [--key FILE] [--require-seal]` verifies offline and exits non-zero on rejection. See D-097.

- **2026-09-03 — X-02 complete (linux-container-v1) with the environment bootstrap (item 8):**
  one commit (`feat: run head code in a Linux container with an environment bootstrap (X-02)`).
  Real-container RED (`tests/execution/test_linux_isolation.py`, skipped only without a
  docker daemon): the planted regression fails 3/3 on head and passes 3/3 on base inside the
  container with the changed line traced; the controller's canary is unreadable; a socket
  connect and writes to the tree, `/etc` and the inputs mount fail and mark the run; uid 65534,
  no capabilities, `RLIMIT_NPROC` (0,0), `--network none`, read-only root. Container smoke on
  the dev slice (`psf__requests-1766`, task `20260903-015318-4cbfcc96`): head FAIL 3/3, base
  PASS 3/3, certified and published as in the C-05 re-run; the receipt's executor profile is
  `linux-container-v1`, its executor digest binds the image
  (`attest-repro:eb26a92d9d1a10b7`, python 3.9.25 by the classifier rule) and the bundle
  verifies offline. The first two smoke attempts DEFERred honestly: `environment bootstrap
  failed` (the project's pinned `requirements.txt` cannot install; requirements files are now
  best-effort, the project install is required) and `process guard did not initialize`
  (`--ulimit nproc=0:0` raced the VM's per-uid process count at exec; the limit is now set by
  a launcher inside the container). Production (`attest ci`, the pilot driver) never falls
  back to the host adapter; the test suite runs on the host adapter unless marked
  `real_backend`. Spend $0.0239 of the $0.10 smoke reservation. See D-096.

- **2026-09-03 — owner instruction 4, result:** report
  [`acceptance/2026-09-03-r01-cache-variant.md`](acceptance/2026-09-03-r01-cache-variant.md).
  r01: 4 certified / 4 published, $0.4862 ($0.0608 per PR), 78% of proposal prompt tokens
  read from cache; package-cache: 2 certified / 2 published, $1.7537 ($0.2192 per PR), 75%.
  No sample without text in either arm. Recommendation: keep `r01`; the owner decides.
  Spend $2.2399 of the $2.50 reservation, settled.

- **2026-09-03 — owner instruction 4 (R-01 cache-variant experiment), code:** one commit
  (`feat: package-cache context strategy for the R-01 comparison (default unchanged)`).
  `context_strategy = "package-cache"` sends the anchored package and its tests as one
  cached system block reused by every sample, generation and repair; the pilot driver gets
  `--context-strategy` and `--results-suffix`. The two-arm run and its table follow in the
  next entry. See D-095.

- **2026-09-03 — owner instruction 3 (prompt caching, staggered fan-out, cache pricing):**
  one commit (`perf: cache the shared prompt prefix, stagger the fan-out on the first token,
  price cache writes and reads apart`). Unit RED: sample 0 goes alone, samples 1-3 start
  after its first token and settle at the cache-read price; the run costs less than four
  cold samples. Real-API RED on `psf__requests-1766` (task `20260903-013450-3fd08afb`,
  $0.0455): sample 0 wrote 3,901 prompt tokens to the cache, samples 1-3 each read 3,901
  (`cache_read_input_tokens` > 0 on the second sample), the review cost $0.0248 against
  $0.0439 for the same case in paid check (b), and the finding was verified and published
  as before; the run status reports `cache_read_input_tokens: 11703` of 15,612 prompt
  tokens. See D-094.

- **2026-09-03 — paid check (b), dev-slice re-run after fixes 1-5:** report
  [`acceptance/2026-09-03-e02-pilot-rerun-fixes.md`](acceptance/2026-09-03-e02-pilot-rerun-fixes.md).
  Defects 8: 19 candidates, 6 certified on 5/8, 5 published, 0 samples without text, 5 true
  abstentions; controls 8: 0 false publications, 28/32 true abstentions. Spend $0.8511,
  settled. The condition for the held-out slice (zero control publications, explainable
  abstentions) holds.

- **2026-09-03 — items 9 and 10:** two commits (`feat: show the drawer in attest stats`,
  `refactor: user-facing wording without statistical terms`). Item 9's RED failed on the
  unpatched path (no `--drawer`) and passes after: an unverified candidate appears with its
  votes and `reproduction: unfaithful test`, and an `attest feedback` label shows beside it.
  Item 10 changes display strings only. See D-092, D-093.

- **2026-09-03 — paid check (a), us-stock-helper trial A/B re-run:** report
  [`acceptance/2026-09-03-us-stock-helper-trial-rerun.md`](acceptance/2026-09-03-us-stock-helper-trial-rerun.md).
  Trial B: 6 candidates, 3 certified, 1 published with a receipt from `attest review`
  (the 3f6b67b defect), $0.2261. Trial A: the 375ab52 defect proposed 5/5 runs, generated,
  executed with changed lines traced, never faithful (the breadth driver's availability
  threshold), silent with the reason shown, $0.1812 over five runs. Spend $0.4073 of the
  $1.00 reservation, settled.

- **2026-09-03 — item 6 (silence receipt):** one commit
  (`feat: report a run status with counts and reproduction failure categories`). The RED
  failed on the unpatched path (no status section) and passes after: a fully silent CI run's
  final comment carries a collapsed section with change units, candidates, eligible,
  attempts and per-attempt failure categories, and no uncertified content. See D-091.

- **2026-09-03 — fix-4 amendment:** one commit
  (`feat: rank test helpers by use and show representative tests to the generator`), from
  trial A runs 2-5 (paid check (a)); see D-089 amendment and
  [`acceptance/2026-09-03-us-stock-helper-trial-rerun.md`](acceptance/2026-09-03-us-stock-helper-trial-rerun.md).

- **2026-09-03 — X-01 gate and the fix-3 amendment:** full gate on `4788d1d` in the
  detached worktree: 909 s wall, production coverage 91.81%, Ruff, Mypy and
  `git diff --check` clean, no failures (the M-01 probe passes with the linked venv). Trial A
  re-run after fixes 1-5 (task `20260903-010906-b302e7c2`, $0.0757): the generator now
  returns text and the candidate is again exactly the 375ab52 defect, but the generated test
  imported the project's test module by name and failed on both trees (unfaithful, not
  published); one commit (`fix: expose each project's tests directory to reproductions`)
  appends the projects' `tests` directories to the import roots and tells the generator.
  The RED (a reproduction importing helpers from the nearest test module by name certifies)
  failed before and passes after. See D-088 amendment.

- **2026-09-03 — owner fix 5 (local differential stage):** one commit
  (`feat: run the differential stage from attest review and resolve commit ids at the entry`).
  `attest review` now runs the verification stage CI runs (one shared function; CI's
  behaviour and ledger rows are unchanged), renders certified findings, and replaces the
  `attest verify` hint with an honest skip note when the tree is dirty or no distinct base
  commit is given; short ids are normalised to 40-hex at the entry. The RED failed on the
  unpatched path (`run_review` had no `verify` and published nothing) and passes after: a
  planted regression reviewed with a 7-character base id publishes one receipt whose
  merge-base and head are the full ids. Gate: see the follow-up entry. See D-090.

- **2026-09-03 — owner fix 4 (generator context):** one commit
  (`feat: show the generator signatures and the nearest test module's fixtures and helpers`).
  The RED failed on the unpatched path (no signature or fixture section) and passes after on
  a `services/svc/src` layout. The paid check is the trial A re-run (a). Gate: see the
  follow-up entry. See D-089.

- **2026-09-03 — owner fix 2 (empty-sample classification):** one commit
  (`feat: count no-text responses apart from true abstentions`). The review notes and the
  pilot table report `no text returned` and `abstained (empty findings list)` separately;
  D-082 recomputed on the C-05 re-run: defects 20 intact / 8 no-text / 4 abstentions,
  controls 2 intact / 30 abstentions / 0 no-text. The RED failed on the unpatched path (no
  such note) and passes after. Gate: see the follow-up entry. See D-087.

- **2026-09-03 — owner fix 3 (import bootstrap):** one commit
  (`fix: import the reviewed tree's packages first and name a shadowed anchor`). Project
  roots under the tree (bounded discovery of `pyproject.toml`/`setup.py`/`setup.cfg` and
  their `src`) lead `PYTHONPATH` and are re-pinned at the front of `sys.path` by the guard;
  a head run whose anchored module came from outside the tree DEFERs as `UNBOUND` naming
  the origin. Both REDs failed on the unpatched path (a same-name stale copy made the head
  "pass" 3/3 with 0 executed lines) and pass after. Gate: see the follow-up entry. See D-088.

- **2026-09-03 — owner fix 1 (generator/provider honesty):** one commit
  (`fix: disable thinking for structured generation and report no-text responses honestly`).
  Structured calls disable thinking where the model accepts it (or ask for `effort: low`
  where thinking is always on); a response without a text block is `generation_no_text
  (stop_reason=…, blocks=…)` in the proposer's sample observations and the generator's
  ledger reason, never `{}` and never a schema mismatch. The RED failed on the unpatched
  path (a thinking-only `max_tokens` response was reported as a schema mismatch with
  `raw="{}"`) and passes after. Gate: see the follow-up entry. See D-086.

- **2026-09-03 — X-01 complete:** implementation is the commit
  `feat: split the controller from the executor behind a nonced, content-addressed protocol`
  (new `attest.execution` package: types, strict protocol, controller, `local_development_best_effort`
  adapter; `execute_repro` is controller-side only and reads nothing the controller did not
  verify against the request nonce and digests). The RED failed on the unpatched path (no
  protocol: any bytes in the work directory were the result) and passes after: an envelope
  answering another request's nonce, an artifact whose bytes disagree with their digest, a
  duplicate or never-issued result, an executor crash and a job left dispatched across a
  controller restart are all rejected and buy nothing. Run records and receipts carry the
  executor profile and backend digest the runs themselves recorded. Full gate: see the
  follow-up entry once the committed tree's gate has run. See D-085.

- **2026-09-03 — step 0 (owner, 2026-09-03): the V-02 tracer is confined to the reproduction
  window:** one commit (`perf: confine the V-02 line tracer to the reproduction window`).
  The tracer is a pytest plugin that installs
  `sys.settrace` only around the collected item's protocol; bootstrap, collection and imports
  are untraced, and only lines the test drives count (the V-02 fixture binds line 2, not 1-2).
  The RED failed on the unpatched path (the attest tracer was installed at import time, so the
  probe failed on both trees as unfaithful) and passes after. Full gate on the committed tree in
  a detached worktree: 793 s wall (13.2 min, against 35 min at `dd99320`), production coverage
  91.59%, Ruff, Mypy and `git diff --check` clean; the eight `test_m01_offline_measurement_probe`
  cases errored inside that run only because the worktree had no `.venv` (the probe invokes
  `ROOT/.venv/bin/python`) and passed 8/8 alone once one was linked. See D-084.

- **2026-09-02 — V-02 complete (policy adopted, pilot open):** implementation `dd99320`;
  the RED failed on the unpatched path (a source-reading test counted as reproduced) and
  passes after, while the genuine reproduction stays bound (executed changed lines 1-2).
  Receipt schema moves to v3 with the binding policy version and observation digest.
  Full gate on `dd99320`: 1630 passed, production coverage 91.55%, Ruff, Mypy and `git diff --check` clean (35 min: the tracer slows the executor suite; backlog). The `G-SEM-002` pilot (≥ 30 preregistered regressions) is not run here.

- **2026-09-02 — C-05 complete:** implementation `2b3d4c9` (publication clusters, e-value
  Bonferroni at m/α, hard cap three, private suppression with reasons, PR-level mean
  e-value) and `927bece` (proposal bound 3,200, D-082). The RED failed on the unpatched
  path (all four certified same-defect findings published) and passes after. Full gate on `927bece`: 1623 passed, production coverage 91.57%, Ruff, Mypy and `git diff --check` clean, with five tests and the M-01 probe adapted afterwards to the family-policy counts (`2b3d4c9`..`47229a8`; the probe passes standalone against both the current tree and its baseline); the window-end gate re-verifies the whole tree.
  Dev-slice re-run with both changes
  ([`acceptance/2026-09-02-e02-pilot-rerun-c05.md`](acceptance/2026-09-02-e02-pilot-rerun-c05.md)):
  candidates 7, eligible 7, certified 4 candidates on 4/8 defects, published 4, controls
  0/8, spend $1.1709; the duplicate publication is gone and every published finding clears
  its PR's m/α.

- **2026-09-02 — D-078 step c (dev-slice re-run):** report
  [`acceptance/2026-09-02-e02-pilot-rerun.md`](acceptance/2026-09-02-e02-pilot-rerun.md).
| population | n | candidates | eligible | certified | published | spend |
|---|---|---|---|---|---|---|
| defects | 8 | 7 | 7 | 5 | 5 | $0.9387 |
| controls | 8 | 1 | 1 | 0 | 0 | $0.1682 |
  certified 5 ≥ 5 and control false publications 0 → per mainline §4 the mainline continues to step 8, C-05. The five certified findings sit on four of the eight regressions (pylint-4970 certified both of its same-defect candidates, the multiplicity C-05 exists to control); requests-1766, pytest-5809 and pytest-6202 certified once each. Silence 4/8: pylint-6386 and pytest-7236 produced no candidates (their samples were empty or exhausted the 2,400-token bound while reasoning), requests-2931's generated test still fails on base, pytest-10081's generator returned `{}` twice. Recovery over the 64 proposal samples: 17 intact, 34 empty, 4 truncated samples repaired by the single precommitted retry, 9 empty after the bound was consumed by reasoning, 0 unrecoverable; deterministic salvage never triggered because truncated samples carried no complete finding.

- **2026-09-02 — D-078 steps a and b:** step a `ee9a0fb` gives the reproduction generator
  the planner's head/merge-base definitions, imports and test references with a prompt that
  asserts merge-base behaviour; measurement on the six eligible-uncertified pilot
  candidates: 5 of 6 faithful (head FAIL 3/3, base PASS 3/3): requests-2931 first candidate, pylint-4970 second, pytest-10081, pytest-6202 both; the remaining requests-2931 candidate still guesses the base URL encoding. Two earlier passes at 2/6 and 0/3 were interpreter-blocked (pytest 5.x cannot compile on 3.11's AST; a 0.0.0 version failed pytest's minversion), which set the executor-side interpreter rule: the highest available interpreter within the project's declared `Programming Language :: Python :: 3.X` classifiers, else the oldest available (3.9); CPython 3.8 is excluded because its eager `platform.uname()` trips the process guard (owner item 3, 2026-09-02). (D-079). Step b `4db546c` adds precommitted recovery of
  truncated proposal samples with an immutable attempt cache (D-080). The pilot builder
  now commits a pytest version that satisfies its `minversion`. Step c (dev-slice re-run)
  follows.

- **2026-09-02 — E-02 pilot (step 7) run:** report
  [`acceptance/2026-09-02-e02-pilot.md`](acceptance/2026-09-02-e02-pilot.md). Dev slice, 8
  SWE-bench Verified regression PRs + 8 controls, K=4, full product path: candidates 8,
  eligible 8, certified 2 (both true regressions, bundles verify offline), control false
  publications 0/8, silence 6/8, ledger spend $1.8601. Losses: eligible→certified 6 of 8
  candidates (unfaithful, `{}`, non-failing generated tests), and 10/32 proposal samples
  truncated. Fork outcome in D-078; one kernel defect (claim bounded as an identifier)
  fixed in `4561686`. E-02 itself (held-out, `G-RECALL-002`) remains open.

- **2026-09-02 — V-01 complete:** implementation `cf5c356`; the RED failed on the unpatched
  path (no bundle, no offline verifier) and passes after: an accepted receipt from the
  planted regression verifies from its bundle alone, and every sampled byte flip across
  `receipt.json`, the test bytes, a run artifact and a run record is rejected. Full gate on the committed tree: 1624 passed, production coverage 91.95%, Ruff, Mypy
  and `git diff --check` clean; the one `test_api` failure expected the pre-V-01 run
  sequence and now records the collection run (`2a94a94`). See D-077.

- **2026-09-02 — R-01 complete:** implementation `3fe6c1b` (planner and unit-wise proposal),
  `ae0c22a` (symbols from enclosing definitions), `35b8c97`/`8d9394c` (pruned walk, generic
  names). The RED failed on the unpatched path (prompt = diff only) and passes after; a
  19-file 107k-char real diff plans into 9 units in 12.6 s deterministically. Trial numbers
  are in D-076 and settled in `DEVSPEND.md`. Full gate on the committed tree: 1624 passed, production coverage 91.94%, Ruff, Mypy and
  `git diff --check` clean. See D-076.

- **2026-09-02 — R-03 complete:** implementation `36dc85b`; the RED
  (`test_permuted_batches_yield_identical_clusters_and_eligibility`) failed on the unpatched
  path (no classifier; representative chosen by sample order) and passes after over all
  sample permutations and within-sample reversals. Full gate on the committed tree: 1621 passed, production coverage 92.21%, Ruff, Mypy
  and `git diff --check` clean; the two `test_runner` failures were fixtures whose
  findings anchored on new code and were certified by the shared reproduction (a V-02
  gap); reshaped as regressions in `cce63e1`, after which the file passes. See D-075.

- **2026-09-02 — C-04 complete:** implementation `71b99aa`; the RED
  (`test_manual_reproduction_moves_no_finding_and_no_precision_window`) failed on the
  unpatched path (wealth 2.6 → 52.8, `=> surface`) and passes after. Full gate on the committed tree with no concurrent process: 1622 passed, 0 failed,
  production coverage 92.16%, Ruff, Mypy and `git diff --check` clean; the M-01 probe
  cases passed inside this run.
  See D-074.

- **2026-09-02 — C-03 complete:** implementation `fc1ae04`; the RED
  (`test_head_policy_is_ignored_and_the_diff_is_merge_base_to_head`) failed on the unpatched
  path with the head's invalid alpha aborting the review and passes after. Full gate on the committed tree: 1596 passed, production coverage 92.22%, Ruff, Mypy
  and `git diff --check` clean; 22 `test_baselines` failures were the harness's reverse
  historical pairs meeting true merge-base semantics, fixed in `248adfb`, after which
  `tests/benchmark` passes in full. Three `test_m01_offline_measurement_probe` fixture
  errors appear only in the whole-suite run (they pass alone, in `tests/benchmark`, and
  with `--cov`); logged in `docs/backlog.md` for attribution, not claimed as passing.
  See D-073.

- **2026-09-02 — C-02 complete:** implementation `383ee65` adds `review.certify` (executor
  output → `CertificationReceipt` → `validate_receipt`), verifies every candidate S/T did
  not discard, records a `certification` ledger row per attempt, and makes presentation and
  the CLI report accept only `CertifiedFinding`. `ci_final.action == "surface"` now means an
  accepted receipt. The one RED (`test_st_cap_without_accepted_receipt_never_reaches_the_author`)
  went red on the unpatched path (published, zero verification rows) and green after. Full
  gate on the dirty pre-commit tree: 1616 passed, production coverage 92.55%, Ruff, Mypy and
  `git diff --check` clean; the four `test_m01_offline_measurement_probe` cases that need a
  clean tree were re-run after the commit. See D-072.

- **2026-08-31 — M-01 Task 5 recovery accepted; Phase 0 complete:** final implementation
  `5efe3d1` retains Task 4's versioned before/after and 20-process mixed-outcome result and
  closes independent review at P0=0/P1=0. After preserving the original `ENOSPC` attempts
  as failed-environment history and safely reclaiming reconstructible temporary space,
  fresh detached exact-SHA Python 3.11.5 and 3.12.8 environments each invoked full pytest
  once and passed 1543/1543 tests, total coverage 12373/13728 (90.129662%), core coverage
  428/429 (99.766900%), Ruff, Mypy, `pip check`, provenance, clean/diff, and frozen-v1
  hashes. M-01, `G-MEASURE-001`, and `G-CODE-001` pass; with M-02/M-03 already accepted,
  Phase 0 is complete and C-01 is unblocked but not started. The superseding
  [`acceptance report`](acceptance/2026-08-31-m01-task5-recovery.md) binds the raw bundle;
  root manifest SHA-256 is
  `d98c510ba5ba8860a27bed57e3d08d86a90b2c4cb758ec1b252ae1ae2956e89b`.

- **2026-08-31 — M-01 Task 5 failed on host storage; still open:** implementation
  `dd37a8e` closes reproduced outer-row, strict-reader, delivery-decision join, and
  physical-order defects; final candidate `5efe3d1` closes the independent review's one
  reproduced non-surface-delivery P1, with resolution P0=0/P1=0. The focused matrix and
  static Gates passed. Fresh exact-SHA Python 3.11 and 3.12 environments each invoked full
  pytest once, but the host volume returned `ENOSPC` at 97% / about 99% (RC 120) before test
  totals or coverage existed. No retry occurred. Under D-049 this is `FAILED ENVIRONMENT`,
  not `G-CODE-001`; M-01, `G-MEASURE-001`, and Phase 0 remain open, and C-01 must not start.
  Task 4's 20-process measurement remains valid; raw Task 5 evidence and exact recovery
  preflight are linked from
  [`acceptance/2026-08-31-m01-mixed-outcome.md`](acceptance/2026-08-31-m01-mixed-outcome.md).

- **2026-08-31 — M-02/M-03 integration accepted; Phase 0 remains open:** implementation
  `14a57fb` integrates M-02 receipt/raw-evidence authority with M-03 immutable paid-call
  role, reconciliation, checkpoint, and report authority. Clean detached CPython 3.11.5
  and 3.12.8 environments passed focused M-02, `G-CODE-002`, M-03 regressions, all
  benchmark tests, full pytest/coverage, Ruff, Mypy, `pip check`, diff, v1 integrity, and
  clean-state Gates. Final contract, security, and manifest/receipt reviews reported no
  P0/P1 blockers, and final sealed-bundle audit reported P0=0/P1=0/P2=0. The evidence is
  [`acceptance/evidence/2026-08-31-phase0-m02-m03-integration-14a57fb3eeaf7c38f136a5e82151f8d3c738af5b/`](acceptance/evidence/2026-08-31-phase0-m02-m03-integration-14a57fb3eeaf7c38f136a5e82151f8d3c738af5b/),
  with `ARTIFACTS.sha256` digest
  `a3d52f8752f893a8ff959cde1c73f28e5dedf5d1eefc3746ab1f426f7e4345c9`.
  M-01/G-MEASURE-001 remains open, comparison accuracy quality is not accepted, and
  Phase 0 has not exited. See
  [`acceptance/2026-08-31-m02-m03-integration-revalidation.md`](acceptance/2026-08-31-m02-m03-integration-revalidation.md).

- **2026-08-31 — M-03 role accounting revalidated:** implementation `bce13f0`
  binds immutable `product`/`benchmark_oracle` roles through canonical call requests,
  checkpoints, artifacts, spend rows, stability/live/comparison reconciliation, and
  report digests; the Ruff local-tool arm cannot acquire fabricated paid evidence. Fresh
  clean CPython 3.11.5 and 3.12.8 environments each passed 213 focused, 479 benchmark,
  and 860 full tests, Ruff, Mypy, 92.36% coverage, `pip check`, diff, and clean-tree
  checks. A new independent reviewer reported P0=0, P1=0, P2=1 and accepted M-03,
  `G-CODE-001`, and `G-MEASURE-003`. See
  [`acceptance/2026-08-31-m03-role-revalidation.md`](acceptance/2026-08-31-m03-role-revalidation.md).

- **2026-08-30 — M-03 reopened after role-accounting review:** the `81bf625` PASS
  record is INVALIDATED but preserved. Independent review reproduced three P1s with
  one root cause: paid-call reconciliation did not bind an immutable product/oracle
  role, so stability, live, and comparison could erase, misclassify, overlap, or
  independently restate authoritative spend. The earlier `5e4234d` clean-install
  logs remain historical observations only and will not be reused for acceptance.

- **2026-08-30 — M-03 revalidated:** implementation `5e4234d` binds every paid
  checkpoint/artifact/spend row to its model and complete predeclaration, closes live and
  comparison whole-evidence erasure, and makes the shipped Action consume CPython 3.12.8
  plus the exact full lock. Fresh Python 3.11.5 and 3.12.8 checkouts each passed 189
  focused, 455 benchmark, and 836 full tests, Ruff, Mypy, 92.41% coverage, `pip check`,
  diff, and clean-tree checks. Final independent review reported P0=0, P1=0, P2=0. See
  [`acceptance/2026-08-30-m03-revalidation.md`](acceptance/2026-08-30-m03-revalidation.md).

- **2026-08-30 — M-03 reopened:** final review found four P1 completion blockers after
  `b897852`; its PASS status and linked acceptance report are INVALIDATED but retained as
  historical evidence. M-03 remains open until the corrected implementation commit itself
  passes fresh Python 3.11/3.12 Gates and an uninvolved reviewer clears all P0/P1.

- **2026-08-30 — M-03 complete:** deterministic clocks, full predeclaration bindings,
  universal paid-subcall checkpoints, fail-closed trial/spend/artifact reconciliation,
  workflow conclusion checks, and the complete locked 3.11/3.12 toolchain were accepted
  in implementation commit `cf8778d`. Both fresh environments passed 814 tests, Ruff,
  Mypy, 92.52% coverage, `pip check`, and diff checks; final independent review reported
  no P0/P1. See
  [`acceptance/2026-08-30-m03-deterministic-crash-safe-measurement.md`](acceptance/2026-08-30-m03-deterministic-crash-safe-measurement.md).

- **2026-08-30 — F-00 complete:** normative document split, target architecture, exact
  dependency roadmap, 30 construction-ready work orders, and 29 acceptance Gates were
  accepted from the audited `c945788` baseline in implementation commit `e52a43b`. See
  [`acceptance/2026-08-30-evolution-scaffold.md`](acceptance/2026-08-30-evolution-scaffold.md).
  The full suite remains `760 passed, 1 failed` on the pre-existing date-sensitive case;
  this does not pass `G-CODE-001` and is assigned to M-03.
