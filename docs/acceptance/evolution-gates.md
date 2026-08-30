# Evolution acceptance gates

Status: **normative acceptance authority**

Applies to: work orders in `docs/implementation/agent-work-orders.md`

Default confidence level: 95%, two-sided unless a one-sided design is preregistered

This document owns quantitative thresholds. Roadmaps and work orders reference Gate IDs;
they must not invent easier local definitions of done.

## 1. Gate classes

| Class | Meaning | Typical authority |
|---|---|---|
| `DOC` | instructions are coherent, traceable, and non-misleading | repository review |
| `CODE` | deterministic implementation/property/security tests | CI and independent review |
| `MEASURE` | measurement process cannot hide or fabricate outcomes | artifact verifier |
| `OFFLINE` | frozen corpus/replay/controlled experiment | preregistered protocol |
| `HUMAN` | semantic truth established independently of product | blind adjudicators |
| `SHADOW` | natural traffic measured with no author-visible findings | authorized deployment |
| `RCT` | real scheduler treatment effect | randomized/paired protocol |
| `RELEASE` | combined product/security/operations readiness | owner decision |

Passing a lower class never implies a higher one. A unit test proves implementation
behavior, not a real-world error rate. A constructed repository is a smoke fixture, not a
population. A synthetic simulator validates its own mechanism under its assumptions, not
production savings.

## 2. Measurement units

Every report declares its unit before its numerator and denominator.

| Unit | Definition | Use |
|---|---|---|
| task attempt | one immutable task/policy/code/model configuration | operational completion |
| candidate | one deterministic semantic candidate cluster | generation/eligibility analysis |
| receipt attempt | one frozen reproduction under one policy | verifier outcome analysis |
| certified finding | kernel-accepted claim before PR selection | certification analysis |
| author-visible finding | one claim actually shown inline or in summary | precision and harm |
| PR | one reviewed change; wrong if any author-visible finding is wrong | family-level safety |
| semantic defect opportunity | one blinded, eligible real defect | detection/recall |
| repository | top-level correlation cluster | uncertainty and generalization |
| paid call | one provider dispatch attempt | spend/exactly-once accounting |
| executor job/run | one isolated job/repeat | security, decisiveness, stability |

Do not use candidates as independent PRs, repeat runs as independent semantic defects, or
changed lines as semantic truth.

## 3. Outcome and denominator rules

### G-MEASURE-001 — Mixed outcomes never erase harm

**Invariant:** every author-visible finding enters semantic-precision and PR-any-wrong
accounting even if another candidate or the task is `DEFER`.

Required classification:

```text
task_status: completed | partially_deferred | fully_deferred | failed
finding_status: published | certified_suppressed | unresolved | rejected
accuracy_status: correct | wrong | unadjudicated | not_applicable
```

DEFER affects only unresolved opportunities. It is not a true negative, a correct silence,
or evidence of precision. A positive case that DEFERs without a correct surface is a
deployment miss. If no finding is adjudicated, precision is undefined (`null`), not 0 or 1.

**Pass:** exhaustive state tests cover 0/1/many findings, task/candidate DEFER, overflow,
and mixed outcomes across CI, API, live, baseline, report, and serialized artifacts; counts
match publication ledger events exactly.

**Fail:** any task-level status can remove an already-visible prediction from scoring.

### Core metrics

For adjudicated author-visible findings:

```text
semantic_precision = correct_author_visible_findings / all_adjudicated_author_visible_findings
```

For null/control PRs:

```text
pr_false_publication_rate = PRs_with_at_least_one_wrong_visible_finding / adjudicated_null_PRs
```

For eligible defects:

```text
eligible_detection = eligible_defects_with_at_least_one_correct_visible_or_shadow_finding
                     / all_eligible_semantic_defects
```

For execution:

```text
structured_generation_success = frozen_valid_repro_specs / eligible_generation_attempts
decisive_execution_rate = reproduced_or_not_reproduced / eligible_execution_attempts
defer_rate = deferred_opportunities / all_eligible_opportunities
```

Conditional accuracy excluding abstentions may be reported as a diagnostic only when the
unconditional delivery/detection metric is adjacent and equally prominent.

## 4. Statistical rules

1. Protocol, primary outcome, population, strata, exclusions, retries, n, stop rules, code
   SHA, model/prompt/tool versions, and budget are frozen before outcomes.
2. Default simple-binomial intervals are 95% Wilson intervals. Repository/PR-correlated
   studies also report a repo-cluster bootstrap or justified cluster-robust interval; the
   more conservative primary interval controls the claim.
3. Paired policies use paired differences/randomization inference or cluster bootstrap,
   not overlapping independent intervals.
4. Candidate-level observations from one PR are not independent. Scheduler comparisons
   preserve PR boundaries and rank only candidates available inside that PR.
5. Repeated runs measure operational variation and are clustered by original case. They do
   not increase the semantic-accuracy denominator.
6. Fixed-n studies do not stop after a convenient run of zeros. A sequential study needs a
   preregistered alpha-spending/e-process design appropriate to that metric; ordinary Wilson
   intervals after optional stopping are not sufficient.
7. Model/prompt/code/policy/executor changes start a new stratum or study. Pooling requires
   a preregistered justification and version effect analysis.
8. Exclusions are determined without looking at product outcome and remain visible with
   evidence. Post-outcome exclusions invalidate the headline analysis.
9. Report numerator, denominator, point estimate, interval, cluster count, missingness,
   DEFER taxonomy, cost, and protocol deviations. A rounded headline is insufficient.
10. Any pass-condition metric whose denominator or required baseline event count is zero,
    undefined, or below its preregistered event/cluster floor is `INSUFFICIENT`, never
    coerced to 0, 1, or infinity. An absolute-effect substitute is permitted only when that
    endpoint and its threshold were frozen by the Gate/protocol before outcomes.
11. A gate failure cannot be repaired by changing the denominator, renaming DEFER, or
    switching to a secondary metric after observation.

Useful all-success reference: 35/35 has a two-sided Wilson lower bound just above 0.90. It
is a minimum evidence shape for a ≥90% precision claim, not a target sample size if any
errors occur or clustering reduces effective n.

## 5. Repository-wide deterministic gates

### G-DOC-001 — Documentation traceability

**Applies to:** F-00 and every later normative-document change.

**Pass conditions:**

- all normative relative links resolve;
- every work-order and Gate ID is unique;
- roadmap completion entries name implementation commit, required Gate IDs, and evidence;
- active documents do not say product wealth is an e-process, that all-DEFER proves
  precision, or that the historical corpus has no receipt;
- historical plans/reports carry a historical/evidence banner;
- thresholds appear canonically here and are referenced elsewhere;
- a decision that changes an invariant/gate updates the affected normative document in the
  same change;
- independent reviewers cover information architecture, implementation executability, and
  acceptance validity.

**Evidence:** link-check output, forbidden-claim scan, traceability table, review findings
and resolutions, `git diff --check`.

### G-CODE-001 — Portable quality gate

**Applies to:** every code work order.

**Pass conditions:**

- focused RED observed, then GREEN;
- all adjacent tests pass;
- full `pytest`, `ruff check .`, and `mypy src/attest` pass under the locked supported
  toolchain;
- total source coverage ≥90%; `attest.core` stays ≥99% until intentionally replaced;
- no test depends on current wall-clock date, global user environment, network, or secret;
- minimum supported Python/tool combination is tested;
- `git diff --check` clean;
- independent review has no unresolved P0/P1 finding.

Test count is reported as an observation, never frozen as the gate.

### G-CODE-002 — Boundary mutation strength

**Applies to:** Certification Kernel, receipt validation, policy, isolation protocol.

**Pass:** table/property tests cover every enum/state/binding field; a mutation test or
purpose-built guard-removal test proves each security/certification check has teeth. Unknown
versions/classes/fields fail closed where required.

## 6. Measurement integrity gates

### G-MEASURE-002 — Receipt evidence and authority

**Applies to:** M-02, V-01, V-03, corpus studies.

**Pass conditions:**

- a `validated` result requires complete bounded run evidence under its declared protocol;
- included and excluded outcomes both retain attempt evidence;
- test/output/JUnit/command/interpreter/environment/source/executor artifacts are
  content-addressed;
- receipt APIs distinguish hash integrity, authorized provenance, and semantic-policy
  acceptance;
- minimal hand-authored `{pair_id,status}` rows cannot authorize scoring;
- v1 historical receipt remains readable only as `historical_integrity_only`;
- offline verification identifies the exact mismatching field/artifact.

**Fail:** rewriting receipt and results together can create current scoring authority
without authorized execution evidence.

### G-MEASURE-003 — Paid-call exactly-once and drift binding

**Applies to:** M-03 and every paid study.

**Pass conditions:**

- failure injection after every state transition proves no automatic duplicate dispatch;
- `dispatched` without response is durable `ambiguous_cost`, never silently free/retried;
- response settlement/consumption is idempotent;
- predeclaration binds repository, resolved SHAs, diff/truth/receipt/policy, code,
  model/provider/prompt/schema, interpreter/environment, and budget;
- drift fails before a new paid call;
- workflow/process failure invalidates acceptance even when comments exist;
- trial IDs join one-to-one with spend rows and artifacts.

### G-MEASURE-004 — Blind semantic adjudication

**Invariant ID:** `INV-TRUTH-001`.

**Applies to:** E-01/E-02/E-04/E-05/N-01 truth labels, including null/control identity.

**Pass conditions:**

- product never sees hidden truth/test/fix message/role;
- null/control identity and the absence/presence of an eligible semantic defect are
  established independently of product output, frozen before the run, and finally resolved
  under the same no-selective-exclusion rule;
- two reviewers independently judge claim semantics, not only file/line;
- reviewer disagreement and resolution are stored; an adjudication policy is frozen;
- inter-rater agreement is reported and AC1 or kappa must be at least 0.70; initial
  unresolved disagreement must be at most 5%. A failed agreement gate triggers rubric /
  reviewer retraining and a newly blinded adjudication pass, never selective relabeling;
- before any Gate metric is evaluated, 100% of rows in its preregistered truth population
  must have a final resolved label under the frozen resolver rule. An unresolved final label
  makes that metric `INSUFFICIENT`; it cannot be excluded from the population or treated as
  clean/correct. The 5% process ceiling is not permission to use unresolved metric rows;
- all generated predictions retain bounded claim/scenario/plan text for blind review;
- when a study samples silent units from natural traffic (currently E-04), sampling is
  randomized with known inclusion probability. This clause is N/A with a stated reason for
  fixed paired corpora or scheduler trials that do not sample a natural silent population.

## 7. Certification gates

### G-CERT-001 — No accepted receipt, no public finding

**Invariant ID:** `INV-CERT-001`.

**Applies to:** C-01/C-02.

**Test design:** exhaust votes 1..K, T 0/1/2+, all allowed alpha/config values, candidate
legacy actions, absent/deferred/negative/positive receipts, malicious scheduler values, and
direct presentation calls.

**Pass:** for every author-visible publication event there is exactly one current-task
`AcceptedReceipt`; modifying task, SHA, claim, test, policy, environment, or receipt state
prevents publication. S/T/Core alone produce zero findings at alpha .15, .4, or any allowed
value. A true fixture still publishes through the receipt path.

**Fail/stop:** any bypass is P0 and blocks all recall/scheduler release work.

### G-CERT-002 — Merge-base and base-owned policy

**Invariant IDs:** `INV-TASK-001`, `INV-POLICY-001`.

**Applies to:** C-03.

**Pass:** criss-cross/advanced-base fixtures resolve declared merge-base deterministically;
head `.attest.toml` cannot relax safety, cap, isolation, evidence, or family policy; policy
bytes/source/digest bind task and receipt; unresolved shallow history DEFERs; task is
revalidated before publication.

### G-CERT-003 — Self-reported evidence separation

**Invariant ID:** `INV-EVIDENCE-001`.

**Applies to:** C-04.

**Pass:** manual `--reproduced` creates only a typed self-report; it cannot produce an
automated accepted receipt, GitHub finding, or automated precision/FPR row. Legacy rows are
visible in a separate namespace and never silently upgraded.

### G-CERT-004 — PR family policy and hard cap

**Invariant IDs:** `INV-FAMILY-001`, `INV-PRESENT-001`.

**Applies to:** C-05.

**Pass:** owner-approved family policy has explicit alpha semantics and property tests;
candidate/sample multiplicity is reduced at semantic-cluster level; author-visible inline
plus summary findings never exceed three at the initial policy; suppressed certified
findings stay private with reasons; permutation/tie tests are deterministic; benchmark
reports PR-any-wrong exposure.

**Fail:** a fourth claim is visible anywhere, or max-findings remains layout-only.

## 8. Semantic receipt gates

### G-SEM-001 — Exact execution identity

**Applies to:** V-01.

**Pass:** accepted receipt proves the exact intended node was collected/executed once per
run, with zero skip/xfail ambiguity; N accepted fresh head failures and N accepted base
passes use identical test bytes/profile/interpreter/environment; all artifacts and SHAs
verify offline. Zero/many tests, collection/setup error, source-conditional test, or missing
structured result rejects.

### G-SEM-002 — Claim/diff causal binding

**Applies to:** V-02.

**Pilot design:** preregister at least 30 legitimate eligible regressions and all named
adversarial classes (unrelated bug, file/SHA branching, target not reached, setup-only
failure, wrong hunk, behavior unchanged by alleged cause). Keep technique-selection and
final-evaluation sets disjoint.

**Pass:** final policy rejects 100% of preregistered adversarial cases; accepts at least 80%
of legitimate pilot regressions with 95% Wilson lower bound at least 65%; all observations
and policy version are receipt-bound. Unsupported/inconclusive binding DEFERs.

If n=30 cannot meet the interval requirement despite high point performance, enlarge using
the preregistered continuation rule; do not lower the bound.

### G-SEM-003 — Fresh state and provenance

**Applies to:** V-03.

**Pass:** marker/cache/daemon/environment fixtures cannot affect later repeats; each repeat
is persisted before the next; crash/resume never double-counts; job result cannot forge the
controller provenance envelope or replay it to another task; controller secret is absent
from executor; offline verifier detects every tamper.

## 9. Recall engineering gates

### G-RECALL-001 — Structured generation robustness

**Applies to:** R-01/R-02/R-03/R-04 before the full corpus gate.

**Population:** frozen supported Python-regression development set, stratified by diff size,
layout, deletion/rename, project test style, and context requirement. No outcome-dependent
exclusions.

**Pass:**

- valid frozen reproduction spec for ≥95% of eligible attempts;
- decisive execution (`reproduced` or `not_reproduced`) for ≥80% of eligible executions;
- no model/test repair after behavioral outcome observation;
- zero new false confirmations on the fixed contemporaneous null/adversarial development
  slice and no regression in certification invariant tests. This is a diagnostic
  non-regression check, not a pass of `G-NULL-001`; E-01 later supplies the release-grade
  current-code null measurement;
- per-stratum cost, latency, and DEFER reasons reported;
- unsupported language/new-code/profile cases are separate, not placed in the eligible
  denominator.

### G-RECALL-002 — Eligible semantic regression detection

**Applies to:** E-02.

**Pass:** point eligible detection ≥70% and repo-clustered/Wilson 95% lower bound ≥50% on
the hidden semantic regression corpus. All DEFER/no-surface eligible cases count as misses.

This gate does not authorize a natural-PR recall claim; E-04 does.

## 10. Isolation and security gates

### G-SEC-001 — Secretless execution protocol

**Applies to:** X-01.

**Pass:** request schema exposes only content-addressed declared inputs; traversal/symlink/
digest/nonce/version attacks reject; result transitions are authenticated and replay-safe;
untrusted job gets no controller/model/GitHub/check-out credential; current in-process
adapter is labeled non-production.

### G-SEC-002 — OS boundary adversarial suite

**Applies to:** X-02 and release.

**Pass:** on the exact production backend, every preregistered secret, `/proc`, home/git,
filesystem, raw-network, DNS/IPv6, native syscall, fork/thread bomb, exec, daemon, resource,
namespace, and result-spoof fixture is actually dispatched and reaches a trusted attempt
marker on the supported backend. A sandbox-external supervisor/kernel observation must then
prove OS denial or forced termination. A pre-dispatch/`unsupported` DEFER does not count as
attack coverage and leaves that backend/profile unsupported for release. The positive
fixture succeeds, cleanup is complete, and missing kernel primitives fail closed. Run in an
isolated canary CI environment with no real secret.

**Fail/stop:** any canary read, host-network egress, persistent process, writable host path,
or forgeable result is P0. Do not compensate with Python hooks or documentation warnings.

### G-SEC-003 — Controlled subprocess profiles

**Applies to:** X-03.

**Pass:** every allowed child matches executable digest/path, argv grammar, cwd, env,
filesystem/network policy, and resource cap; grandchildren remain contained and recorded;
PATH shadowing/argv escape/wrong digest/network/write escape reject; preregistered legitimate
shelling fixtures become decisive; process-free remains default.

## 11. Empirical safety and semantic gates

### G-NULL-001 — Current-code natural-null safety

**Applies to:** E-01 and any certification-policy release candidate.

**Population/design:** at least 600 unique adjudicated null candidates, at least 30
repositories, preregistered natural and adversarial strata, current exact binary/policy,
one immutable trial record per attempt. Include at least 381 independent adjudicated null
PRs if zero PR errors; more are required when errors occur or clustering weakens the bound.

**Primary pass conditions:**

- PR-any-wrong-publication 95% conservative upper bound ≤1%;
- candidate false-confirm 95% conservative upper bound ≤1.28% as a diagnostic continuity
  target, with actual no-purchase/DEFER rate adjacent;
- no unadjudicated author-visible finding in the denominator;
- repo-cluster analysis does not cross either bound;
- all trials have replayable v2 evidence bundles.

**Safety stop:** third false confirmation before n=600, any systematic receipt bypass, or
any high-severity false publication triggers immediate stop/root-cause review. The final
gate still uses intervals; stopping does not turn partial data into a pass.

**Permitted claim:** “On the preregistered current-code null population, the upper bound was
X.” It does not prove e-process validity or transfer to all PRs.

### G-CORPUS-001 — Hidden semantic corpus validity

**Applies to:** E-02.

**Design:** at least 120 independent real regressions and 120 paired controls from at least
20 repositories; hidden human-authored oracle fails buggy three times and passes fixed
three times; two blind semantic reviewers; product cannot see truth/test/fix role.

**Pass conditions:**

- G-MEASURE-004 blind adjudication passes;
- 100% of findings that the frozen product would expose to an author or to the declared
  shadow surface are adjudicated. A missing, unresolved, or selectively omitted visible
  finding invalidates the precision gate; it is not removed from the denominator;
- semantic precision 95% conservative lower bound ≥90% with at least 35 adjudicated correct
  findings and enough total findings for the observed error count;
- G-RECALL-002 passes;
- zero wrong certified control findings in the initial 120-control corpus; its finite
  interval is reported and not misrepresented as a 1% bound;
- generation/execution/defer/cost/latency broken out by repo and stratum;
- no location-only TP, outcome-based exclusion, or leaked hidden test.

**Safety stop:** third wrong confirmed finding, truth leak, artifact/protocol drift, or
budget exhaustion before minimum n.

**Permitted claim:** corpus-scoped semantic precision/detection only, with intervals and
eligibility definition.

### G-STAB-001 — Nontrivial operational stability

**Applies to:** E-03.

**Design:** 20 heterogeneous cases ×10 repeats; at least five surface-capable regressions,
five near-threshold/DEFER cases, and five controls. Fresh state; fixed model/prompt/tool/code
versions; cluster by case.

**Pass:** modal outcome nonagreement point rate <5% and case-cluster bootstrap 95% upper
bound <10%; surface/non-surface and DEFER flip reported separately; semantic cluster
Jaccard, anchor dispersion, cost, and latency reported; no high-severity wrong surface in
any repeat.

**Futility stop:** if the pilot cases all land in structurally forced drawer/silence or no
case can surface, redesign the set and do not publish a stability claim.

### G-SHADOW-001 — Prospective natural-PR utility and safety

**Applies to:** E-04 and release.

**Design:** at least 500 authorized natural PRs across at least 30 repositories; no
author-visible finding; adjudicate every shadow finding plus a known-probability random
sample of at least 200 silent PRs; preserve language/diff/new-code/size strata.

**Pass conditions:**

- at least 100 adjudicated shadow findings;
- every PR selected for truth ascertainment—whether it had a shadow finding or was sampled
  from silence—receives the same preregistered product-blind defect audit. The audit uses
  evidence independent of the product result, such as two-expert diff review plus a declared
  resolver, hidden tests, or post-merge failure/fix evidence, and records defect semantics,
  severity, support eligibility, and opportunity-to-detect before revealing product output;
- unknown or disputed PR truth is `unresolved`, never clean/no-opportunity. The primary
  eligible-detection analysis requires resolved opportunity status for 100% of the
  design-weighted audited sample and at least 100 independently confirmed eligible defect
  opportunities. Any unresolved sampled PR makes eligible detection `INSUFFICIENT`; it may
  be reported in sensitivity analysis but cannot be dropped, imputed as clean, or bypass
  the primary lower-bound requirement;
- silent-PR sampling records nonzero inclusion probability before outcomes. Eligible
  detection and its interval use a preregistered Horvitz–Thompson, Hájek, or equivalent
  design-weighted estimator, or a uniform-probability PR adjudication sample. Naively
  computing detection on certainty-included finding PRs plus an unweighted silent sample is
  an automatic failure;
- semantic precision 95% conservative lower bound ≥90%;
- PR-any-wrong-shadow-finding 95% upper bound ≤1%;
- supported eligible-defect detection point ≥60% and 95% lower bound ≥50%;
- acknowledgement/status p99 ≤60 seconds from job start;
- final decision p95 ≤600 seconds for supported tasks;
- zero budget ceiling violation and complete cost/latency distributions;
- DEFER and all-silence are reported; all-silence fails utility regardless of precision.

**Safety stop:** five high-severity wrong shadow findings, any receipt/security bypass, or
after ≥30 adjudicated findings a precision lower bound <80% pending root-cause review.

**Permitted claim:** prospective shadow result on the authorized population, not general
production performance.

### G-NEWCODE-001 — New-code evidence-contract decision readiness

**Applies to:** N-01 and any proposal to create a certifiable new-code evidence class.
Passing this gate authorizes an owner decision on a contract; it does **not** authorize a
likelihood ratio, automated certificate, or public finding.

**Design:** preregister a hidden, product-blind pilot with at least 60 independently
adjudicated new-code defects and 60 paired clean additions from at least 15 repositories.
Include more than one language/project stratum and adversarial cases where a generated test
asserts an invented specification, branches on source/version, proves an unrelated defect,
or passes under an equally plausible alternative implementation. Compare at least three
falsifiable contract families, including the always-abstain baseline; examples are an
external specification oracle, metamorphic/property relations, and mutation/patch-ablation
with independent semantic adjudication.

**Pass conditions:**

- every proposed contract states its counterfactual, trust root, supported population,
  failure semantics, required receipt fields, and how a negative/control result can refute
  the claim;
- no regression-channel LR, base-symbol-absence heuristic, model agreement, or planted
  single fixture is reused as truth authority;
- all candidate visible/shadow-visible outcomes are adjudicated and reported under
  `G-MEASURE-004`, including wrong, DEFER, unsupported, and no-finding outcomes;
- the decision packet reports contract-specific null-error intervals, eligible detection,
  semantic precision, PR-level harm, cost, latency, containment compatibility, and
  applicability by stratum; uncertainty and multiplicity across compared contracts are
  controlled by the preregistered method;
- raw bundles let an independent reviewer reproduce every table, exclusion, and receipt
  decision without revealing hidden truth to the product run;
- the packet names one of `reject`, `collect_more`, or `recommend_contract`; it cannot name
  or tune an LR.

**After owner selection:** create a separate implementation/calibration work order whose
N-series ID is assigned only then, and require that class to pass its own `G-CERT-*`,
`G-SEM-*`, `G-NULL-001`, `G-CORPUS-001`, and `G-SHADOW-001` applicability before public
use. Until then, `new_code_candidate` remains a typed abstention.

## 12. Scheduler gates

### G-SCHED-001 — Scheduler data readiness

**Applies to:** S-01 through S-04.

**Schema/shadow pass for S-01/S-02:** every action has immutable state/action/policy version
and task/PR ID. A candidate ID is required if and only if the tagged action is
candidate-scoped; task-scoped discovery must not invent one. Each action also records the
applicable model/prompt/tool/executor versions, reservation/cost/latency/deadline, typed
outcome, and selection propensity when randomized. For S-01 through S-03, shadow on/off
produces identical execution and publication, and the event stream reconstructs task-local
budget and outcomes.

For S-04, the ordinary production action manifest and publication remain identical on/off;
only preregistered, separately budgeted audit jobs may add execution. Their outputs live in
a non-public audit namespace, cannot enter the live `CertifiedFinding`/family-selection set,
and are evaluated only as offline labels through the same pure receipt validator. Tests must
fail if any audit action/receipt changes a normal task decision or author-visible byte.

**Additional learned-evaluation readiness for S-03/S-04:** at least 500 global adjudicated
candidate outcomes, a repository-grouped train/evaluation split, and a complete overlap /
applicability report. S-01/S-02 may complete and collect the events needed for this stage;
no learned policy may be evaluated or promoted until the additional readiness conditions
pass.

Every state/action/reservation/budget operation is task/PR-local: discovery actions are
task-scoped, evidence actions are candidate-scoped with a candidate belonging to that task,
and no reservation, remaining budget, observation, or action may transfer across task IDs.
Cross-task/cross-PR construction and replay tests must fail closed.

### G-SCHED-002 — Within-PR scheduler benefit

**Applies to:** E-05 promotion from shadow to execution-order control.

**Estimand:** benefit of ordering actions available **within the same PR** under the same
budget and deadline. Cross-PR pooled sorting is invalid because production cannot transfer
one PR's verification budget to another.

**Design:** at least 1,000 eligible candidates, 200 certifiable positives, 300 eligible
multi-action PR clusters, and 30 repositories. Every included PR has at least two feasible
actions known before scheduling whose relative order can differ. A preregistered
cluster-level power calculation may require more than these floors. Randomize policy at PR
level within strata with at least 60 eligible PRs per arm, or use a within-PR paired replay
with at least 100 eligible multi-action PRs only when all relevant action outcomes were
obtained by an approved audit slice. Compare FCFS, deterministic priority, and learned
policy. Cluster inference by repo/PR; no repository may contribute more than 10% of PR
clusters or analysis weight. Keep an exhaustive audit slice of at least 20% where safe and
budgeted.

Before relative endpoints are computed, the frozen FCFS arm must contain at least 50
verified true findings across at least 30 PRs, and at least 100 deadline-induced unprocessed
eligible actions across at least 50 PRs. The preregistered power analysis may require higher
event floors. If either denominator is zero or below its event/cluster floor, the
corresponding relative endpoint is `INSUFFICIENT`; the analysis may not switch post hoc to
an infinite ratio, a different denominator, or an absolute endpoint.

**Primary pass conditions:**

- verified true findings per fixed budget improves with point estimate ≥10% and paired/
  clustered 95% lower bound >0;
- true findings at equal budget are noninferior with margin 0;
- the upper confidence bound on the PR-any-wrong risk difference is at most +0.25
  percentage points;
- deadline-induced unprocessed DEFER falls ≥20%;
- propensity/overlap and audit-slice diagnostics pass;
- result survives repo, diff-size, and provider-version sensitivity analysis.

**Futility stop:** after the preregistered interim n, the confidence interval excludes the
10% target on the harmful side or safety degrades. Retain deterministic priority/shadow.

The historical synthetic 11.5–33% result does not count: it pooled candidates across tasks
and used assumed outcomes/costs.

### G-SCHED-003 — Monitor intervention eligibility

**Applies only if automatic quarantine/braking is proposed later.** Log-only monitoring
does not need to pass this to ship as telemetry.

**Design:** use an independent prospective holdout not used to choose thresholds, canary
families, or monitor features. Include at least five materially distinct failure families,
30 independent canary sequences per family, 1,000 healthy task sequences, 30 repositories,
and 100 control-arm wrong-certification events across at least 30 PR/repository clusters.
No repository contributes more than 10% of clusters or analysis weight. A preregistered
cluster-aware power calculation may require larger floors; any unmet floor or zero baseline
event is `INSUFFICIENT`.

**Pass before any intervention:** canary sensitivity 95% lower bound ≥90%; bootstrap /
clustered upper confidence bound for p95 detection delay ≤200 purchases; healthy-run
false-brake 95% upper bound ≤5%; wrong-certification reduction 95% lower bound ≥50%; added
abstention 95% upper bound ≤10 percentage points; cost-difference 95% upper bound ≤0;
results pass failure-family/repository/version sensitivity analysis; spend-share drift alone
never triggers. Before this Gate **and** a separate owner decision, no automatic
intervention is permitted. Even after both, a monitor may only apply a base-policy-bound,
fail-safe dispatch/purchase brake or pre-certification task quarantine/operational DEFER.
It never changes an existing receipt or Certification Kernel output, creates a
`CertifiedFinding`, changes PR family/publication selection or presentation, increases
eligibility, restores a suppressed family member, exceeds the hard cap, or reads head policy
to relax the intervention. Certification and speech authority remain independent of the
scheduler. A global publication kill switch belongs to L-01 operational policy, not a
scheduler monitor.

### G-MODEL-001 — Multi-model support and comparison

**Applies when:** more than one model/version/role policy is evaluated or deployed.

**Pass conditions:**

- every action records exact provider, model/version/alias resolution, role, prompt/schema,
  sampling parameters, and pricing digest before outcome;
- repeated samples, models from one provider/family, and different roles on one PR are
  treated as correlated observations, never multiplied or counted as independent n;
- every deployed provider/model/version/role/prompt-schema routing cell—or the preregistered
  routing policy plus its worst supported cell—independently meets the applicable safety
  gate and utility gate for the population it receives. A cell marked
  `excluded`/`insufficient` may run only in non-public offline or isolated shadow evaluation;
  it cannot control purchases, receive pilot traffic, or contribute to live certification,
  family selection, or presentation;
- a policy that requires multiple deployed cells uses an intersection-union decision and
  reports worst-cell plus macro results; selective cell/model claims control multiplicity
  with the preregistered method;
- with fewer than five genuinely distinct model strata, no random-effects “generalizes to
  models” claim is made; results are exact-model/version scoped;
- alias/version drift starts a new stratum and pauses pooled promotion;
- comparative value is incremental decisive trusted receipts per cost/latency under the
  same within-PR opportunities, while certification and family policy stay fixed.

Passing this gate can justify model routing or role assignment. It never turns multi-model
agreement into certification evidence.

## 13. Release gate

### G-RELEASE-001 — Private external pilot readiness

**Required:** `G-DOC-001`, `G-CODE-001`, `G-CODE-002`, `G-MEASURE-001` through
`G-MEASURE-004`, `G-CERT-001` through `G-CERT-004`, `G-SEM-001` through `G-SEM-003`,
`G-SEC-001` through `G-SEC-003`, `G-NULL-001`, `G-CORPUS-001`, `G-STAB-001`, and
`G-SHADOW-001`. If any scheduler seam or shadow policy is deployed, its applicable
`G-SCHED-001` stage must pass: schema/shadow for S-01/S-02 and full learned readiness for
S-03/S-04. `G-SCHED-002` is additionally required if a learned scheduler controls execution
order, and `G-SCHED-003` if a monitor automatically intervenes; only a completely disabled /
omitted scheduler is N/A. `G-MODEL-001` is required whenever more than one model, version,
or role policy is evaluated or deployed in the pilot; only one frozen model/version/role is
N/A. `G-NEWCODE-001` alone is never a release gate; if the capability matrix
claims new-code certification, the owner-selected post-N-01 implementation must also pass
all applicable certification, semantic, null, corpus, and prospective gates as a distinct
evidence class.

**Operational pass:** immutable install ref; supported platform/profile matrix; base-policy
reference; privacy/retention and cost controls; incident response, kill switch, and rollback
tested; GitHub/model/executor outage drills fail safely; no active P0/P1; participant/repo
authorization; owner approves the pilot. Public publishing remains a separate owner action.

## 14. Minimum evidence bundle

Every empirical gate stores a bounded, content-addressed bundle:

```text
study.json                 protocol ID/version, hypothesis, estimand, gates
preregistration.json       n, strata, exclusions, retries, stops, budget
environment.json           code SHA, dirty flag, lock/interpreter/OS/backend digests
models.json                provider/model/prompt/schema versions and pricing snapshot
provider-artifacts/        bounded redacted/encrypted request-response cassettes or an
                           access-controlled manifest with public content digests
manifest.json              opaque cases/tasks and immutable source refs
truth.enc-or-separated/    access-controlled truth; never product-visible
trials.jsonl               one immutable trial/action/outcome ID per row
receipts/                  receipt manifests and bounded artifact digests
costs.jsonl                reservations, dispatch ambiguity, settlement
adjudication.jsonl         blinded labels, reviewer IDs, disagreement/resolution
analysis.py-or-command.txt exact deterministic analysis entrypoint
report.json                machine-readable metrics/intervals/deviations
report.md                  human interpretation and permitted claims
ARTIFACTS.sha256           digest inventory
review.md                  independent protocol/result review and resolutions
```

The bundle records rejected/excluded/deferred trials as carefully as successful ones.
Secrets, raw unbounded output, private repository source, and hidden truth are stored only
in appropriate access-controlled locations; committed manifests contain digests and safe
metadata.

## 15. Claim language matrix

| Evidence | Allowed | Not allowed |
|---|---|---|
| unit/property tests | “the implementation enforces X on covered states” | error-rate or real-world quality claim |
| constructed fixture/smoke Action | “the end-to-end path worked on these fixtures” | independent validation, precision, recall |
| synthetic experiment | “under these assumptions, mechanism A did X” | production savings or calibration |
| historical 0/296 | “constructed pre-fix observation, 0/296, with stated interval/design limits” | current-binary guarantee or e-process proof |
| all-DEFER replay | “0 surfaced attempts; reasons were…” | precision held, recall=0 under an excluded denominator |
| G-NULL-001 | null-population bound for exact code/protocol | all-PR precision or e-validity theorem |
| G-CORPUS-001 | hidden-corpus semantic precision/detection | natural-PR performance |
| G-SHADOW-001 | prospective shadow performance on authorized population | public production result |
| G-SCHED-002 | real within-PR scheduler effect | cross-PR pooled/synthetic VOI claim |
| G-NEWCODE-001 | decision packet recommends one contract for separate implementation | new-code certification, LR validity, or permission to publish |

Never write “multi-model consensus certified,” “the betting layer absorbed variance,” or
“from never wrong” from finite zero-event observations. Prefer exact population, code
version, numerator/denominator, interval, and abstention rate.
