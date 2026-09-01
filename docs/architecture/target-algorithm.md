# Target algorithm architecture

Status: **normative target**

Baseline audited: `main@c945788` on 2026-08-30

Decisions: D-038 through D-049

## 1. Outcome

Attest should become an LLM-driven project evaluator that finds important defects with
high precision, useful recall, bounded cost, and evidence a developer can independently
re-run. It is not a multi-model voting product and it is not allowed to turn model
agreement into a publication certificate.

The target separates two jobs that the current repository partially mixes:

- **Search and scheduling** may use fallible, correlated, adaptive signals to spend the
  next dollar or second well.
- **Certification** is a small, deterministic, fail-closed kernel. It decides whether a
  finding may be published from a policy-bound, content-addressed execution receipt.

The governing contracts are:

> Every public finding requires a trusted `CertificationReceipt` accepted by the
> Certification Kernel for the current task, immutable revisions, claim, and base-owned
> policy. Receipt acceptance makes a finding eligible; the PR publication policy may still
> suppress it for deduplication, family control, or the hard public cap. The scheduler,
> model panel, pull-request configuration, manual flags, and presentation layer cannot
> create or override eligibility.

## 2. Current implementation versus target

### 2.1 What is currently real

The product path under `src/attest/review` is a fixed S/T/V pipeline:

1. the proposer samples one model K times over a diff;
2. lexical deduplication forms candidates and a capped S score;
3. nearby static diagnostics add a T score;
4. candidates in the drawer may receive V after a generated pytest runs three times on
   head and three times on base;
5. the generic wealth threshold and GitHub layer decide placement.

At the factory `alpha=0.1`, S×T is capped at 9 against a surfacing threshold of 10, so a
positive V supplies the decisive factor for every reachable combination — not usually, but
in all 45 of them (D-063). The multiplication of the purchased channels has therefore never
crossed a threshold its strongest single channel had not already crossed: 0 changed
decisions over the reachable grid, over every candidate on record, and over D-059's
findings at every reachable S. D-065 adds the observed distribution behind that bound —
`S×T` has never exceeded 3.0 in a real run, with `T = 1.0` on all 26 recorded candidates.
This is a property of the frozen factory tables at this alpha, not a runtime guarantee:
`alpha >= 1/9` removes it (see the gap list below), and raising a cap or pricing a new
channel changes the enumeration and requires its own. The S and T factors price only
positive evidence; they are not e-values, and the product wealth is not an e-process.
Current error control therefore rests on factory arithmetic and the reliability of
differential reproduction, not on a general sequential-validity theorem.

### 2.2 What `attest.core` currently is

`src/attest/core` is a research/simulation engine for two or three binary judges. It
learns plug-in conditional tables from exploration data, chooses purchases by expected
information, and exposes a monitor. The production review path imports only the generic
`decide` helper; it does not run `Engine`.

The existing Core assumptions do not fit real review scheduling without redesign:

- exactly two or three binary judges;
- binary truth and verdicts;
- immediate labels after every task;
- a fixed 0.5 prior implicit in odds conversion;
- stationary/exchangeable tasks;
- thin plug-in tables without a distribution-free guarantee;
- no prompt/model/version context;
- no schema failure, latency, deadline, or abstain action.

Core is therefore preserved as research code and evolved behind a new scheduling
interface. It is not activated as a certifier.

### 2.3 Known gaps and closed regression obligations

The roadmap tracks unresolved implementation gaps and recently closed gaps that remain
regression obligations, not hypothetical polish:

- `alpha >= 1/9` can currently let S/T surface before differential verification, and CI
  intentionally skips verification for an already-terminal candidate.
- pull-request head configuration can influence the gate; policy is not base-owned.
- `attest verify --reproduced` is a self-report path that can buy the same V factor without
  a differential execution receipt.
- `max_findings` controls inline placement, while overflow surfaces remain author-visible;
  there is no PR-level multiplicity policy.
- head-fail/base-pass proves a behavioral difference but does not by itself bind that
  difference to the stated claim or changed hunk.
- JUnit handling does not yet prove exactly one intended node ran with zero skip/xfail;
  repeat runs may share mutable worktree state.
- the ledger does not retain a complete, content-addressed reproduction bundle.
- M-01's versioned outcome accounting now preserves author-visible findings beside
  candidate/task DEFER and closes the former mixed-outcome denominator hole; this does not
  by itself authorize public accuracy.
- V2 validation types and the offline verifier reject incomplete/unauthorized evidence, but
  no current V2 authority may accompany production execution pending X-01/V-03; the frozen
  corpus receipt is historical V1 integrity evidence, not current scoring authority.
- M-03's current paid live/stability/comparison paths use locked tools and role-bound,
  crash-safe checkpoints; every future paid/execution path must reuse that state contract.
- current containment is a best-effort same-user process guard, not a security boundary.
- the dated historical replay report contains only abstaining bug-replay attempts; schema
  robustness, project context, and safe subprocess support are observed recall blockers.
  Counts and current status belong in `docs/roadmap.md` and dated evidence, not this target.

### 2.4 Current-to-target gap and closure index

| ID | Current seam/evidence | Target owner | Work orders |
|---|---|---|---|
| `GAP-CERT-01` | `review.ci.run_ci` verifies only drawer candidates; the alpha=.15 test preserves direct S/T surface | Certification Kernel | C-01/C-02 |
| `GAP-POLICY-01` | `review.config.load_config` reads the head worktree; safety fields are not destination-owned | immutable task/policy | C-03 |
| `GAP-MANUAL-01` | CLI `verify --reproduced` applies legacy V without a differential bundle | evidence namespaces | C-04 |
| `GAP-FAMILY-01` | `gate.apply_gate` and presentation keep overflow author-visible; no PR family policy | PR publication policy | C-05 |
| `GAP-RECEIPT-01` | executor/ledger lack exact-node, complete environment/run artifacts, semantic binding, and authenticated provenance | receipt/kernel/execution | V-01/V-02/V-03 |
| `GAP-TASK-01` | diff path accepts a base ref without one task-wide merge-base/base-policy manifest | immutable task | C-03/R-01 |
| `GAP-MEASURE-01` | **Closed by M-01 at `5efe3d1`:** versioned accounting preserves every author-visible outcome beside DEFER | measurement contract | M-01 complete; regression obligation |
| `GAP-CORPUS-01` | V2 evidence/provenance verification exists, but production execution has no current V2 authority and the frozen corpus remains historical V1 | measurement authority | M-02 complete; X-01/V-03/E-02 remain |
| `GAP-CRASH-01` | **Closed for current measurement paths by M-03:** paid roles, calls, artifacts, spend, resume, and locked tools are bound fail-closed | measurement state machine | M-03 complete; reuse obligation |
| `GAP-SEC-01` | credentials and untrusted same-repo code share a runner; language hooks are best-effort | controller/executor split | X-01/X-02/X-03 |
| `GAP-RECALL-01` | monolithic context, strict schema, deletion/new-code/non-Python limits, process-free execution | discovery/execution | R-01 through R-04, X-03 |
| `GAP-CORE-01` | `core.Engine` is disconnected and binary-judge-specific; synthetic priority pools tasks | scheduler | S-01 through S-04, E-05 |
| `GAP-NEWCODE-01` | `new_code_candidate` is only a typed abstention; no class-specific counterfactual or calibration exists | evidence-contract research | N-01 |

Line numbers intentionally do not live in this table. Each work order names the current
symbols and tests; agents re-resolve exact lines at task start.

## 3. Target data flow

```text
immutable PR context + base-owned policy
                 │
                 ▼
        Candidate Discovery
  diff planner / retrieval / proposers
                 │ CandidateRecord[]
                 ▼
       Evidence Scheduler (Core)
 rank next action; shadow first; no speech authority
                 │ ScheduledAction
                 ▼
         Evidence Executors
 model roles / tools / repro generation / isolated execution
                 │ EvidenceObservation + artifact digests
                 ├──────────────────────┐
                 ▼                      │
       Certification Kernel             │
 deterministic receipt validation       │ feedback outcomes,
 claim/revision/policy binding           │ costs, latency,
 PR-level publication policy             │ delayed labels
                 │ CertifiedFinding      │
                 ▼                      │
          Presentation Layer             │
 max-public cap / GitHub / CLI            │
                 │                      │
                 └──────── Ledger ──────┘
```

No upward arrow grants publication authority. Feedback may improve future scheduling,
but it cannot retroactively make an invalid receipt valid.

## 4. Boundary types

These are conceptual contracts. Work orders introduce concrete frozen dataclasses and
versioned JSON schemas before moving behavior.

### 4.1 `ReviewTask`

Required fields:

- stable task ID;
- repository identity;
- base ref requested by the event;
- resolved merge-base SHA;
- immutable head SHA;
- policy source SHA and policy digest;
- diff digest and changed-file metadata;
- global wall-clock deadline, model budget, execution budget;
- execution trust class (`local_trusted`, `same_repo_untrusted`, `fork_untrusted`);
- schema/protocol versions.

The task ID must be derived from immutable inputs. A retry on changed inputs is a new
task, not a continuation.

### 4.2 `CandidateRecord`

Required fields:

- task ID and candidate ID;
- normalized claim, failure scenario, falsification plan;
- one or more old/new-side anchors with diff-hunk IDs;
- discovery source, model/prompt/schema versions, and response digest;
- provenance links to raw bounded artifacts;
- dedup cluster ID and deterministic cluster membership;
- untrusted ranking features separated from trusted evidence;
- lifecycle state and explicit eligibility/defer reasons.

Candidate identity must not depend on processing order. Equivalent input sets must yield
the same clusters under permutation.

### 4.3 `ScheduledAction`

The scheduler may choose one of:

- ask a proposer role for another candidate;
- ask a skeptic/refuter role to attack a candidate;
- retrieve more repository or dependency context;
- run a deterministic static/dynamic tool;
- generate or schema-repair a reproduction before behavioral execution;
- execute a frozen reproduction on head, base, or a declared control;
- request causal/coverage evidence;
- stop spending and abstain.

`ScheduledAction` is a tagged union, not one record with a fake nullable candidate:

- `TaskScopedDiscoveryAction` always binds task/PR, policy, reservation, maximum price,
  deadline, and selection propensity where randomized. It has no candidate ID because a
  candidate does not exist yet.
- `CandidateScopedEvidenceAction` binds the same fields plus a candidate ID that must belong
  to that exact task. Refutation, context retrieval for a known claim, reproduction,
  execution, and causal checks use this branch.

Each branch also binds the exact model/tool/executor profile and version whenever that
resource is used. State, actions, reservations, remaining budget, and observations are
task-local. A scheduler cannot transfer a candidate, reservation, purchased outcome, or
unused budget between PRs; cross-task pooling is permitted only in offline model training
after the events have been sealed, never in online action execution.

### 4.4 `EvidenceObservation`

Observations are typed events, not likelihood ratios by default. Examples include:

- candidate proposed, duplicate, invalid schema, or no candidate;
- tool diagnostic with tool and rule identity;
- reproduction generated or repaired;
- exact test node passed, failed, skipped, timed out, or violated containment;
- head/base differential outcome;
- coverage/trace reached or did not reach target code;
- cost, token, latency, and executor termination data;
- later human label with adjudicator provenance.

An observation records the action propensity and all version/digest bindings needed for
offline policy evaluation. Missing fields make it ineligible for learning, not silently
defaulted.

### 4.5 `CertificationReceipt`

A receipt is valid only when it contains or content-addresses all of:

- receipt schema and certification-policy versions;
- task, repository, merge-base, head, diff, candidate, and normalized-claim digests;
- base-owned policy source and digest;
- exact generated test bytes and digest;
- exact selected test node and collection result;
- command argv, cwd contract, interpreter digest, dependency/environment digest;
- executor image/profile digest and isolation attestation;
- fresh-run IDs and per-run stdout/stderr/JUnit artifact digests;
- exactly N accepted head results and N accepted base results;
- zero skip/xfail/unselected-test ambiguity;
- normalized failure signatures and a causal/coverage binding result;
- start/end timestamps, deadline, resource use, and termination reason;
- controller signature or trusted provenance envelope;
- final evidence class and all reasons for rejection/defer.

The receipt contains no secrets. Its validity is reproducible offline from the evidence
bundle except for an explicitly named platform-attestation trust root.

### 4.6 `CertifiedFinding`

A certified finding binds one accepted receipt to author-visible text and one or more
anchors. It cannot be constructed by the scheduler or presentation layer. Publication
policy then applies PR-level limits and multiplicity handling to the complete set of
certified findings.

## 5. Candidate Discovery

Discovery optimizes eligible defect hypotheses, not comments per sample.

### 5.1 Diff planning

The planner must:

- resolve the event base to the merge-base with the immutable head;
- represent additions, modifications, deletions, renames, and test/config changes;
- create stable hunk/chunk IDs;
- budget context per semantic unit instead of sending one monolithic full diff K times;
- retrieve definitions, callers, tests, types, configuration, and old-side context;
- disclose unsupported languages and generated/binary files as typed abstentions.

Pure deletions need old-side anchors. New symbols need a distinct eligibility path; they
must not be forced into a regression receipt that assumes the symbol exists on base.

### 5.2 Model roles

Models are heterogeneous workers, even when the same provider serves multiple roles:

- **proposer**: generate falsifiable defect hypotheses;
- **skeptic/refuter**: find semantic or provenance reasons a hypothesis is wrong;
- **test designer**: produce a minimal reproduction specification;
- **repairer**: repair schema/collection defects without seeing behavioral outcomes when
  the retry policy allows it;
- **causal checker**: connect the observed failure to the stated claim and changed hunk.

Role, prompt version, provider/model ID, and context digest are first-class features.
Agreement between roles may influence priority, but never certifies a finding.

### 5.3 Deduplication

Deduplication should be deterministic, order-invariant, and auditable. A cluster must
retain every member and its provenance. It may combine multiple anchors for one semantic
defect but must not collapse distinct failure mechanisms merely because they share a line.

## 6. Evidence Scheduler: the target role for Core

### 6.1 Authority boundary

Core decides **what to buy next**, including when to stop. It never decides whether a
finding is true enough to publish. Its scores are advisory ranking values and must not be
fed into the Certification Kernel as evidence.

The first production-compatible scheduler can be deterministic S/T priority. The learned
Core starts in shadow mode and logs counterfactual choices without changing execution
order. Only the promotion gates in `docs/acceptance/evolution-gates.md` may advance it.

### 6.2 Objective

The primary utility is expected incremental probability of obtaining a decisive,
trusted receipt per marginal cost and time, subject to hard budgets and deadlines:

```text
utility(action | state)
  = E[delta P(decisive trusted receipt) | state, action]
      / weighted(cost_usd, latency, scarce executor time)
```

Secondary penalties cover duplicated candidates, schema failures, containment defers,
deadline starvation, and concentration on one repository/model. “Probability the claim
is true” is not itself the optimization target because the scheduler cannot certify it.

### 6.3 Learning requirements

A learned scheduler must support:

- arbitrary typed actions rather than two or three binary judges;
- delayed and partially missing labels;
- realistic, stratified base rates;
- hierarchical/cross-fitted estimates with thin-cell shrinkage;
- propensity logging and a randomized exploration slice;
- cost, latency, deadline, and capacity constraints;
- provider/model/prompt/tool versioning and nonstationarity detection;
- repo-clustered evaluation and off-policy diagnostics;
- deterministic fallback when a model or learner is unavailable.

No adaptive policy may train and evaluate on the same outcome without a declared split or
valid online design.

### 6.4 Multi-model evaluation

Multiple models are useful when they have different marginal value. They are not treated
as independent witnesses and their votes are never multiplied or counted into a quorum.

The scheduler learns questions such as:

- Which proposer finds a nonduplicate, executable candidate for this diff class?
- Which skeptic most cheaply rejects a likely hallucination?
- Which test designer produces a collection-valid reproduction for this project shape?
- Which tool/model action reduces deadline-induced DEFER?

Required comparisons include same-model repeated sampling, heterogeneous role assignment,
and marginal ablations. A more expensive model is promoted only if its incremental trusted
receipt yield justifies cost and latency under a paired or randomized evaluation.

### 6.5 Exploration and monitor

Randomized all-buy or expanded-verification traffic is a small, preregistered shadow slice.
It supplies unbiased counterfactual data and has an explicit cost cap. The monitor is
log-only until healthy-stream specificity and canary sensitivity pass their gates. A
spend-share drift alarm alone cannot stop publication; the Certification Kernel remains
the safety boundary.

Audit actions run in an isolated shadow namespace. They obey the same task-local budget,
secretless execution, receipt validation, and artifact rules, but their receipt evaluations
are label data only: they cannot enter the live task's `CertifiedFinding` set, PR family
selection, summary, inline comments, or operational decision. Before E-05 promotion, the
ordinary-path action manifest and every author-visible byte are identical with S-04 on or
off except for private audit ledger/artifacts and separately accounted audit spend.

### 6.6 What “start Core” means

Starting Core is a staged integration, not adding `Engine(...)` to `run_ci`:

1. **S-01 double-write:** production behavior stays unchanged while every real PR-local
   candidate/action/outcome is emitted through the generic scheduler event seam.
2. **S-02 deterministic shadow:** FCFS, current S/T priority, and feasibility priority
   compute counterfactual next actions from the same state. No extra paid action and no
   execution-order change.
3. **S-03 learned shadow:** reuse or redesign useful Core ideas—exploration slices,
   expected marginal information, shrinkage, monitoring—behind the arbitrary-action
   interface. Do not reinterpret binary judges as models voting on truth and do not wire the
   current `Engine` directly to candidates.
4. **S-04 measured exploration:** a separately budgeted randomized/audit slice supplies the
   counterfactual outcomes that observational logs lack.
5. **E-05 promotion decision:** only a real within-PR comparison can let the scheduler
   control purchase order. Certification remains unchanged before and after promotion.

Thus Core becomes useful early as instrumentation and shadow ranking, while its learned
policy activates only after enough versioned, semantic, propensity-bearing outcomes exist.

## 7. Evidence Executors

### 7.1 Controller/executor split

The privileged controller may hold the model credential and GitHub write token. It may
materialize immutable inputs and publish already-certified results. It must never execute
pull-request code.

The unprivileged executor receives only a content-addressed job bundle. It has:

- no model or GitHub credentials;
- no checkout credentials or host home-directory access;
- a read-only source mount plus a bounded writable scratch area;
- default-deny network enforced below the language runtime;
- cgroup/job-object CPU, memory, process, file, and wall limits;
- a seccomp/sandbox/container profile or equivalent OS primitive;
- a clean environment and explicit interpreter/dependency image;
- an authenticated result channel back to the controller.

Same-repository pull requests are untrusted for execution. Repository ownership is not a
sandbox property.

### 7.2 Controlled subprocess support

Mature projects legitimately invoke formatters, compilers, or worker processes. Support
is profile-based, not a blanket relaxation:

- a process-free profile remains the default;
- a declared tool allowlist identifies executable digest, argv pattern, working directory,
  environment, child/process cap, and filesystem/network policy;
- undeclared process, thread, exec, or network attempts produce typed DEFER;
- every child is contained in the same kernel boundary and appears in the receipt.

### 7.3 Repetition integrity

Each accepted repeat starts from a fresh source snapshot and fresh writable state. Runs
may share immutable blobs but not caches, environment mutations, generated files, or
processes. The controller records each run before scheduling the next so a crash cannot
silently duplicate a paid call or count an ambiguous execution. Every paid-call record
also binds an immutable execution role; product and benchmark-oracle spend are disjoint
authority classes and are never reconstructed from call order or independently stated
report fields.

## 8. Certification Kernel

### 8.1 Kernel properties

The kernel is:

- deterministic and side-effect free;
- independent of model SDKs, scheduler code, GitHub APIs, and repository configuration;
- small enough for exhaustive state/property tests;
- versioned, with explicit migration and compatibility rules;
- fail-closed on missing, unknown, contradictory, stale, or unauthenticated fields.

### 8.2 Regression certificate

The initial certifiable class remains an existing-code regression. Acceptance requires,
at minimum:

1. the exact intended test node is collected once per run;
2. that node executes and deterministically demonstrates the claimed failure on head;
3. the exact same test and execution profile passes on merge-base;
4. no accepted run is skipped, xfailed, infrastructure-failed, or collection-ambiguous;
5. the failure reaches the claimed code and is causally attributable to the relevant diff,
   under the selected binding policy;
6. all artifacts and immutable inputs match the receipt;
7. the receipt was produced under the base-owned policy for this task.

Head fail/base pass without semantic binding is differential evidence, not automatically
a publication certificate.

### 8.3 New-code class

`new_code_candidate` remains a typed, unpriced abstention until its own evidence contract
and empirical gate are approved. It is not unlocked by choosing one plausible LR. Likely
certification designs require a base-side counterfactual harness, mutation/patch ablation,
specification oracle, or human-authored invariant. Each design must be calibrated as a
separate evidence class.

### 8.4 Manual evidence

Manual `--reproduced` input becomes `self_reported` evidence. It may be useful in a local
workflow, but it cannot produce a differential `CertificationReceipt`, enter automated
precision/FPR estimates, or publish through the autonomous GitHub path unless a distinct
human-attestation policy is explicitly designed and labeled.

### 8.5 PR-level publication policy

The kernel returns the complete certified set. A deterministic PR policy then:

- controls family-level false-publication exposure;
- applies the base-owned hard author-visible cap across inline and summary; its canonical
  initial numeric acceptance value is owned by `G-CERT-004`;
- deduplicates semantic clusters before the cap;
- records suppressed certified findings in the private ledger with a reason;
- never calls author-visible overflow “drawer” or hides it from harm accounting;
- defines deterministic tie-breaking independent of worker completion order.

The exact multiplicity method is a task in the roadmap; the invariant is that a per-candidate
threshold plus a cosmetic top-three layout is insufficient.

## 9. Presentation and ledger

Presentation receives only `CertifiedFinding` or explicit task-level operational status.
It cannot inspect raw scheduler scores to decide speech. Status comments must not reveal
uncertified claims.

Every author-visible finding is recorded before or atomically with publication. If any
candidate also DEFERs, the published findings still count in precision/FPR and harm
metrics. Operational task status and finding-level accuracy are separate dimensions.

The ledger must distinguish:

- candidate state;
- scheduler action and propensity;
- evidence observation;
- certification result;
- publication placement;
- task-level abstention/defer;
- manual/self-reported evidence;
- human semantic label;
- cost settlement and ambiguous cost.

## 10. Measurement contract

The unit of author harm is an author-visible finding. The unit of PR-level safety is a PR
with at least one wrong author-visible finding. The unit of opportunity is an eligible,
human-adjudicated semantic defect. These denominators are never interchanged.

Rules:

- DEFER is an abstention, not a true negative and not proof of precision.
- A positive case with no eligible surface is a deployment miss even when it safely DEFERS.
- If nothing surfaces, finding precision is undefined, not 100%.
- Mixed surface+DEFER retains every surface in accuracy and harm accounting.
- Repeats measure operational stability; they do not enlarge the independent accuracy
  denominator.
- Location overlap is insufficient for semantic true-positive status.
- Intervals cluster at the repository/PR unit when candidates share context.
- Fixed-n or alpha-spending rules are declared before outcomes are observed.
- Synthetic experiments are mechanism tests, never production-effect estimates.

Quantitative gates and permitted claim language live in
[`../acceptance/evolution-gates.md`](../acceptance/evolution-gates.md).

## 11. Threat model

| Threat | Required defense | Fail-closed result |
|---|---|---|
| PR changes `.attest.toml` to relax speech | base-owned signed/digested policy; kernel ignores head policy | task policy invalid / DEFER |
| S/T or Core score crosses a threshold | types prohibit score input to kernel | no receipt, no surface |
| manual flag impersonates V | distinct `self_reported` type and ledger namespace | autonomous publication rejected |
| generated test targets another defect | claim/hunk/trace or causal binding | receipt rejected |
| base actually imports head code | immutable independent mounts and import provenance | receipt rejected |
| test collects zero/many nodes or skips | exact-node/count/JUnit checks | receipt rejected |
| repeat mutates later runs | fresh writable state and run IDs | receipt rejected |
| head code reads secrets | secretless OS-isolated executor | job terminated / DEFER |
| repository shells out | declared executor profile only | undeclared process / DEFER |
| receipt files are rewritten together | signed provenance envelope plus raw artifacts | receipt rejected |
| many candidates amplify PR harm | family policy plus hard public cap | deterministic suppression |
| mixed DEFER hides a published FP | finding-level scoring independent of task status | surface remains in numerator |
| adaptive retries cherry-pick behavior | precommitted repair policy; no outcome-aware retries | trial invalid |
| model upgrade changes behavior | version/digest stratification and drift monitor | no pooling across versions |

## 12. Cross-cutting invariants

These stable IDs must become executable property tests:

| ID | Invariant |
|---|---|
| `INV-CERT-001` | `published_finding -> accepted_current_task_receipt` for every allowed configuration. |
| `INV-CERT-002` | Changing S/T/Core scores alone never changes certification. |
| `INV-TASK-001` | Receipt task/repository/merge-base/head/diff identity matches the current immutable task. |
| `INV-POLICY-001` | Head-owned configuration alone never weakens destination policy; policy mismatch rejects. |
| `INV-EVIDENCE-001` | Manual/self-reported evidence never becomes an automated receipt or metric row. |
| `INV-RECEIPT-001` | Receipt claim/test/node/environment/executor/run/provenance mismatch always rejects. |
| `INV-VERSION-001` | Unknown schema, evidence class, executor profile, or policy version fails closed. |
| `INV-FAMILY-001` | PR-level selection applies the declared family policy to semantic clusters. |
| `INV-PRESENT-001` | Public findings across all author-visible surfaces never exceed the hard cap. |
| `INV-MEASURE-001` | Every published finding remains in harm accounting even if the task or another candidate DEFERs. |
| `INV-TRUTH-001` | Accuracy/detection truth is product-blind and semantic; location-only, unresolved, selectively omitted, or product-dependent labels cannot pass a Gate. |
| `INV-ORDER-001` | Permuting otherwise identical candidate/model completion order does not change clusters, certification, or publication selection. |
| `INV-SCHED-001` | Scheduler outage falls back or abstains; scheduler output cannot bypass certification. |
| `INV-SCHED-002` | Every online scheduler state, action, reservation, budget, candidate, and observation is task/PR-local; discovery has no fake candidate and evidence actions bind a candidate owned by that task. |
| `INV-COST-001` | A controller crash cannot count an unpersisted paid call as free, replay it silently, erase its settled cost, or reclassify product and benchmark-oracle spend. |
| `INV-SEC-001` | Untrusted execution receives no privileged secret and has no undeclared host-network/filesystem route. |

## 13. Migration seams

The implementation should introduce boundaries before deleting old code:

- create `attest.certification` for receipt types, policy, validation, and PR selection;
- create `attest.scheduler` for action/state/events and deterministic/shadow policies;
- move execution protocol and controller adapters toward `attest.execution` while keeping
  current executor behavior behind an adapter;
- keep discovery under `attest.review` initially, then expose typed candidate records;
- make GitHub presentation consume certified outputs only;
- keep `attest.core` regression pins intact while an adapter or successor scheduler is
  evaluated in shadow mode;
- version ledger records and provide readers for old rows instead of rewriting history.

The exact task order and file-level seams are in
[`../implementation/agent-work-orders.md`](../implementation/agent-work-orders.md).

## 14. Non-goals until evidence exists

- claiming the product wealth is an e-process;
- setting a new LR for new-code findings by judgment alone;
- using model majority, unanimity, debate outcome, or self-confidence as certification;
- automatic monitor intervention before specificity is measured;
- publishing a precision/recall claim from all-DEFER runs;
- calling BugsInPy reverse fixes natural pull requests;
- treating two smoke repositories as independent statistical validation;
- releasing publicly before isolation, calibration, and prospective-shadow gates pass.

## 15. Owner decisions that remain real decisions

Agents may build experiments and decision packages, but must not silently decide:

- the exact PR-level multiplicity policy;
- the first certifiable new-code evidence contract;
- which OS isolation backend(s) define the supported production platform;
- the budget for large real-corpus and prospective studies;
- promotion of a learned scheduler from shadow to execution control;
- public release, marketplace publication, or third-party commenting.
