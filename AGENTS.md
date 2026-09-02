# AGENTS.md — standing construction guide

This file is the mandatory entry point for any coding agent working in this repository.
It owns durable operating rules, not transient branch names, test counts, spend totals, or
nightly status. Dynamic phase status lives only in `docs/roadmap.md`.

## 1. Instruction and document authority

Follow, in order:

1. the current owner/user instruction;
2. this file for repository authority, safety, and work protocol;
3. `docs/architecture/target-algorithm.md` for target product contracts;
4. `docs/acceptance/evolution-gates.md` for definitions of done and quantitative gates;
5. `docs/roadmap.md` for dependency order and current status, and `docs/mainline.md` for
   the working sequence to the product, the definition of "product", corpus policy, and the
   decisions reserved to the owner;
6. the selected task in `docs/implementation/agent-work-orders.md` for implementation
   method;
7. active decisions in `DECISIONS.md` for narrow trade-offs and reversal conditions;
8. code/tests for current behavior;
9. dated acceptance reports and old plans as historical evidence only.

Authority is by domain, not “newest prose wins.” A decision that changes an architecture
invariant or acceptance gate must update the owning normative document in the same change.
If normative documents conflict, stop the affected implementation and repair the conflict;
do not choose the easiest interpretation.

Read `docs/README.md` for the complete documentation map and anti-drift rules.

## 2. Locate and inspect the repository

The checkout path is machine-dependent. Work from the Git root containing this file:

```bash
git rev-parse --show-toplevel
git status --short --branch
git remote -v
git rev-parse HEAD
git log -5 --oneline
```

Expected origin:

```text
https://github.com/IcantFind-a-username/Attest.git
```

Never initialize or scaffold a replacement repository. Do not assume an old macOS/Windows
absolute path from a report. Preserve unrelated dirty-worktree changes; they belong to the
user or another task.

<a id="product-north-star"></a>

## 3. Product north star

This section is the sole repository authority for Attest's durable product north star.

> “Attest 的首要目标不是普通 bug scanner。它应当学习并分析整个代码库，理解并合理拆分架构，精准定位问题，并能见微知著地指出对整个项目质量影响最大的 Top 问题；具体 bug 可以同时检测和指出，但属于这一系统级代码理解与质量诊断能力的自然副产物，而不是唯一或最高层目标。”

Normatively, product success means system-level repository understanding, coherent
architecture decomposition, cross-cutting impact analysis, and Top-issue prioritization.
Concrete bug findings are expected natural by-products of that capability, not its sole or
highest goal.

This north star governs candidate scope, ranking, evidence and corpus design, and product
success metrics. Attest remains an evidence-first, LLM-driven project evaluator that spends
model/tool/execution budget efficiently and publishes only claims backed by a trusted,
replayable, claim-bound certificate. Receipt-only certification, security/isolation, and
honest measurement remain mandatory constraints, not substitutes for product success.

The target separation is:

```text
Candidate Discovery
      -> Evidence Scheduler/Core (chooses what to buy next; no speech authority)
      -> Evidence Executors (models, tools, generated tests, isolated runs)
      -> Certification Kernel (only authority that can create CertifiedFinding)
      -> PR Publication Policy (family control, dedup, hard public cap)
      -> Presentation
```

Multi-model work is useful as heterogeneous roles and marginal-value actions: proposer,
skeptic, test designer, repairer, causal checker. Model agreement is correlated ranking
information. It is never a vote, quorum, independent likelihood product, or certificate.

## 4. Current implementation warning

Do not confuse target contracts with current behavior:

- production review is a fixed S/T/V pipeline in `src/attest/review`;
- `src/attest/core.Engine` is research/simulation code and is not in the product path;
  production currently reuses only the generic `core.betting.decide` helper;
- S/T price only positive evidence, so current product wealth is **not an e-process**;
- at factory alpha, cap arithmetic normally forces positive differential V before speech,
  but this is not a runtime invariant for all configurations;
- since C-02 (`383ee65`) CI publishes only validator-accepted receipts and verifies every
  candidate S/T did not discard; head configuration can still influence policy until C-03;
- manual `attest verify --reproduced` is not a trusted differential receipt;
- `max_findings` currently limits inline placement, not all author-visible findings;
- current head/base execution proves a behavioral difference but lacks the complete exact-
  node, semantic-binding, fresh-state, and authenticated-provenance target receipt;
- current language-level process/network guards are best-effort containment, not a security
  boundary for untrusted head code;
- the current process audit covers the entire reproduction pytest interpreter, so trusted
  runner bootstrap can set the same child-process marker as reviewed code; two retained
  Black replays first triggered on Python 3.8 `platform.uname()` invoking `uname -p` before
  the generated test entered `black.format_str` or Click's `CliRunner`;
- historical real replay produced only abstentions in the reported attempts, so it did not
  estimate product precision or recall;
- synthetic S/T scheduling savings are mechanism evidence, not production Core efficacy.

These gaps are work-order inputs. Never rewrite the architecture to bless a current bypass.

## 5. Shortest safe reading path

For ordinary implementation:

1. this file;
2. `docs/mainline.md` §2 for the first unfinished step, then `docs/roadmap.md` for that
   order's status and dependencies;
3. the exact work-order section;
4. only the linked architecture sections and Gate IDs;
5. the affected code and tests;
6. active narrow decision entries referenced by the task.

Read historical plans/reports only to investigate provenance. In particular,
`docs/superpowers/plans/2026-08-29-*.md` are completed archives and contain requirements
that the evolution roadmap intentionally reverses.

## 6. Non-negotiable product invariants

Stable IDs are defined in the architecture and acceptance documents.

1. **Receipt-only publication (`INV-CERT-001`).** Every author-visible finding must map to
   exactly one accepted current-task `CertificationReceipt`. Scheduler/S/T/wealth/manual
   state can never substitute.
2. **Trusted task and policy.** Review the immutable head against its resolved merge-base;
   safety policy is base-owned/protected and receipt-bound. Head content cannot relax it.
3. **Correlated model evidence.** Never multiply or count panel agreement as independent
   evidence. Use it only for discovery/ranking until a separately valid observation exists.
4. **Kernel independence.** Certification imports no model SDK, scheduler, GitHub API,
   repository config loader, or subprocess runner. Presentation accepts certified outputs,
   not raw gate results.
5. **Manual separation.** Human/self-reported reproduction is labeled separately and never
   enters autonomous certification or automated precision/FPR denominators.
6. **PR-level safety and hard public cap.** Per-candidate thresholds plus cosmetic top-N
   are insufficient. Public inline+summary claims obey the base-owned family policy and
   hard cap.
7. **Mixed outcomes remain scored.** A task/candidate DEFER cannot erase another finding
   already shown to an author.
8. **DEFER is abstention.** It is not a true negative, correct silence, refutation, or proof
   of precision. No surfaced finding means precision is undefined.
9. **Exact, fresh, claim-bound execution.** Accepted receipts bind task, SHAs, policy,
   candidate/claim/hunk, exact test/node, environment/executor, fresh per-run artifacts, and
   causal/semantic policy.
10. **Secretless untrusted execution.** Project/head code runs only in the supported
    secretless OS boundary. Missing security capability fails closed.
11. **Scheduler has no speech authority.** Core may rank the next action only. It starts
    shadow, advances through real within-PR evaluation, and always leaves certification
    unchanged. Online state, candidates, reservations, budget, and observations remain
    task/PR-local; discovery does not invent a candidate ID and evidence actions cannot bind
    a candidate from another task.
12. **New-code evidence is class-specific.** `new_code_candidate` remains unpriced and
    unpublished until a separate counterfactual contract and empirical gate are approved.
13. **No outcome-aware retry.** Schema/collection repair is precommitted and completes
    before behavioral outcomes. Trying tests until one passes the gate invalidates the
    trial.
14. **Product-blind semantic truth (`INV-TRUTH-001`).** Location overlap, unresolved cases,
    product-dependent review, or selective omission cannot establish correctness or
    detection.
15. **No unmeasured claim.** Synthetic, fixture, corpus, shadow, and production results are
    named at their actual evidence level with numerator, denominator, interval, abstention,
    and version.

Violating one is rework, not a small regression.

## 7. Repository and git discipline

- Use conventional commit subjects: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`,
  `chore:`.
- Feature/fix work uses a focused `feature/*` or `fix/*` branch. Small docs/chore work may
  be direct only when the current task permits it.
- Never put an AI-assistant or vendor-agent name, including your own, in branch names,
  commit messages, code comments, or generated documentation. The commit hook is only a
  partial backstop. Never use `--no-verify` or weaken the hook.
- Model IDs that are necessary product data stay in the designated versioned data/config
  files; do not repeat them in commit subjects.
- Keep commits small and single-purpose. One work order may use several commits; one commit
  must not smuggle in an unrelated work order.
- Never use destructive commands such as hard reset/checkout over user changes. Never
  rewrite historical benchmark/ledger/receipt artifacts in place.
- A managed worktree is allowed for isolated feature work. One writer owns a file set in a
  worktree. Read-only reviewers may share the checkout; concurrent writers must not edit
  overlapping files.
- Do not push, open a PR, create/delete a remote, or merge unless the current owner request
  or an explicitly approved acceptance work order requires it. Local implementation does
  not imply remote mutation authority.
- The working tree of this repository is the only directory an agent may read as input,
  execute against, or write to. Other repositories or projects on the same machine are out
  of bounds even for read-only "evaluation", even when a previous conversation mentioned
  them, and even when the report would say nothing was written there. Any external corpus
  the work needs (a real repository to review, a defect population to score) must be named
  in the work order or in an owner-approved fixture list before the first read, and it is
  brought in by cloning its remote into the gitignored `.attest/corpora/<name>/` path under
  this working tree at a recorded commit — never by opening the owner's local checkout of
  that project, which may hold uncommitted work and is not a reproducible input. Owner
  permission to "use project X" means clone X; prior context and the name of a directory
  on disk are not authorization. See D-070.

## 8. Remote, release, third-party, and secret rules

- `origin` is the owner's repository. Public package/Marketplace release, visibility
  changes, and third-party repository interaction require a new explicit owner action.
- Historical authorization for private scratch acceptance does not make every task a remote
  task. Follow the selected work order and current instruction.
- Third-party repositories/corpora are read-only inputs. Never post comments, issues, PRs,
  reactions, or writes to a repository the owner does not own.
- Never print, echo, log, commit, or include API/GitHub credentials in artifacts. Verify
  credential presence only through safe metadata when a paid/remote task is authorized.
- The privileged controller may hold credentials; the untrusted executor never receives
  them. Environment-name filtering is not sufficient isolation.
- Public/user artifacts must be bounded and redacted. Hidden truth and private source stay
  access-controlled; committed manifests contain safe metadata and digests.

## 9. Spend and authority

- `DEVSPEND.md` is the sole owner of the approved development cap, settled total, and
  remaining headroom. Read it at task start; never copy, exceed, or raise its cap without
  explicit owner authorization.
- Every paid call requires an approved work-order protocol, explicit paid opt-in, precharge,
  durable per-call checkpoint, and ledger row. Failed/ambiguous calls are recorded.
- Product per-PR budget is not development budget.
- Do not start a paid study that cannot reach its preregistered minimum n within the approved
  remaining cap.
- Stop and ask before increasing the total cap, changing any factory alpha/LR/channel cap,
  selecting a PR-level statistical policy, pricing a new evidence class, promoting a learned
  scheduler, selecting a production isolation backend when not already decided, or enabling
  public release.

## 10. Work-order selection

`docs/roadmap.md` is the only owner of status and dependency order. `docs/mainline.md`
fixes the sequence in which the remaining orders are worked, what "product" means, which
corpora may be used without asking, and the four decisions reserved to the owner; the next
task is its first unfinished step unless the owner says otherwise.

The owner directs the destination and does not read code. Only §16 items and the four
decisions in `docs/mainline.md` §5 go to the owner. Every other choice — library, layout,
schema, retry, naming, tooling, test shape — is the agent's, decided by ordinary industry
practice (search when unsure), recorded in a `DECISIONS.md` entry of at most six lines. A
handoff is at most one page with at most three owner items, each a yes/no with a default.

The mainline, so that every agent carries the same picture without opening the file:

```text
product = outside Python repo installs from a stable ref and gets PR comments, every
          comment receipt-backed and offline-verifiable, head code secretless, silent on
          all controls of a human-labelled corpus, one clean shadow run, L-01 exit list.

C-02 -> C-03 -> C-04 -> R-03 -> R-01 -> V-01 -> E-02 pilot (fork on numbers, §4)
     -> C-05 -> V-02 -> X-01 -> X-02 -> V-03 -> E-02 held-out -> E-01 -> E-04 -> L-01

off the mainline until after L-01: S-*, N-01, X-03, R-04, pricing/F research, any scan.
corpora: owner's GitHub repos (clone, no asking), BugsInPy, SWE-bench Verified;
         committed dev/held-out split before the first run.
owner decides only: A multiplicity method, B isolation backend, C paid spend, D release.
```

Before editing:

1. choose exactly one first-unblocked work order — the first unfinished mainline step
   unless the owner says otherwise;
2. verify its dependency Gate IDs and artifacts, not only checkbox state;
3. record baseline SHA, claimed files, task scope, and whether it is paid/security/remote;
4. run its focused pre-change test;
5. if dependencies or owner gates are missing, work only on an explicitly independent
   task or prepare a decision package.

Do not start a later recall/scheduler task to avoid a difficult certification/security
dependency. Do not port research code just because it exists.

Step 5 is an exit, not a licence. One task may propose at most one new work order, and only
as a decision package for the owner; it may not implement it, chain further orders behind
it, or open a new work-order prefix series. A new CLI subcommand, a new product surface
(for example a whole-repository scanner beside the PR reviewer), or a new owner-queue
longer than three items is an architecture decision reserved to the owner under §16. When
the requested measurement cannot be taken with the code and corpora that exist, the
deliverable is the sentence that says so and why, not a product that makes it possible.

## 11. Implementation protocol

Follow the detailed template in `docs/implementation/agent-work-orders.md`.

For every behavior change:

1. write one focused failing test and observe the relevant RED;
2. implement the smallest typed boundary/behavior that makes it GREEN;
3. run the tests covering the changed modules immediately, adjacent tests once the change
   settles;
4. add adversarial/fail-closed cases for trust, persistence, or statistics boundaries;
5. run the full portable gates once at the end of the work order, not after every change;
6. inspect the entire diff for authority bypass, compatibility, secret, denominator, and
   overclaim problems;
7. request independent review before completion;
8. fix confirmed findings and rerun affected gates;
9. update roadmap/decision/evidence links only after the gate exists.

Orders that only diagnose, measure, instrument, or report change no behavior: they carry no
RED step and this sequence does not apply to them — their deliverable is the number or the
finding. Never write a test whose only assertion is that an object constructs or a call does
not raise, one written to move a coverage number, or one whose only failure mode is a typo
mypy already catches. If coverage dips while staying above the product-package floor because
an order legitimately needed no test, report the number rather than adding a filler test.
See `docs/implementation/agent-work-orders.md` §3.1 and D-058.

The review/repair loop is bounded by D-049:

- run exactly one independent review pass per work-order branch;
- fix only defects reproduced in that pass; unreproduced concerns and every finding from a
  second review round go to `docs/backlog.md`, one line each, rather than another code commit;
- any one stop signal ends the task in a handoff report: three consecutive commits to the
  same file where additions exceed deletions, eight commits or three hours on one task
  (whichever comes first), or the task's stated measurement is in hand;
- a task is complete only when its stated measurement exists. Plans and checkbox exhaustion
  are background, not authority to overrun these bounds.

Do not weaken a regression pin, skip/xfail a failing security test, lower the product-package
coverage threshold, change a denominator, or relax a receipt check to make the suite pass.

## 12. Change-impact matrix

| If you touch | You must inspect/run |
|---|---|
| certification types/kernel/policy | all `tests/certification`, boundary import tests, receipt mutation/adversarial tests, CI publication properties |
| diff/task/config/Git refs | merge-base, shallow/drift, base-owned-policy, action-entrypoint and real temporary-repo tests |
| executor/reproduction/JUnit | executor + certification receipt + containment/security + fresh-state + benchmark receipt tests |
| presentation/GitHub/CLI | receipt-only publication, hard-cap, mixed-DEFER, sanitized-copy, API-failure tests |
| ledger/checkpoint/artifact schema | legacy readers, crash injection at every transition, drift binding, cost reconciliation, tamper tests |
| benchmark metrics/report/matcher | mixed outcomes, undefined denominators, semantic blind truth, repeats/clustering, deterministic goldens |
| scheduler/Core adapter | import authority, shadow equivalence, propensity/overlap, within-PR ordering, outage fallback |
| model/prompt/schema | version/digest bindings, budget, checkpoints, no truth leakage, new study stratum |
| action/sandbox scripts | fork/same-repo trust, secretless boundary, kernel capability probes, target-runner integration |
| factory statistics/evidence class | owner decision, decision log, preregistered calibration and all downstream gates |
| normative docs | G-DOC-001 links, IDs, domain authority, historical banners, claim language |

## 13. Portable verification

Use the environment/lock specified by the current branch. Typical portable commands are:

```bash
python -m pytest --cov=src/attest --cov-report=term-missing
python -m coverage report --include='src/attest/benchmark/*' --fail-under=0
python -m coverage report --include='src/attest/core/*' --fail-under=0
python -m ruff check .
python -m mypy src/attest
git diff --check
```

Inside an existing POSIX venv, replace `python` with `.venv/bin/python`; on Windows use the
venv interpreter under `.venv\Scripts`. Never assume a platform-specific path in code.

The coverage Gate applies `fail_under = 90` only to the production packages
`attest.review`, `attest.cli`, and `attest.github`. The same run prints separate
informational coverage reports for `attest.benchmark` and `attest.core` with no threshold.
Benchmark is a frozen measurement tool whose correctness is established on known inputs;
Core is research-only and frozen. Core code must not grow without explicit owner approval.
Ordinary work-order/wave Gates use one supported Python; the final integration Gate uses
both the locked minimum and primary Python versions.

Repository gates:

- satisfy the commands, quality/coverage thresholds, determinism conditions, and
  integration rules canonically defined by `G-CODE-001` and `G-CODE-002`;
- no skipped security integration may be claimed as a pass.

Report the command, code SHA, environment/lock digest, pass/fail summary, and any exactly
reproduced pre-existing failure. Do not quote an old test count as a current gate.

## 14. Decision and document updates

- Before assigning a decision ID, scan all of `DECISIONS.md`, take the highest existing
  `D-NNN` **across both entry formats — the historical `- **D-NNN` bullets and the newer
  `### D-NNN —` headings** — and use the next number. Scanning only one format silently
  misses every entry in the other. Entries are not stored strictly in numeric order; never
  trust a cached number or only the last line.
- Every material trade-off gets a dated `DECISIONS.md` entry with status, scope, evidence,
  consequences, reversal conditions, superseded entries, affected invariants/Gates, and
  affected files/tests.
- Preserve old decisions as history. Add amendments; do not silently edit their evidence.
- If a decision changes target behavior or thresholds, update architecture/acceptance in
  the same commit. A dangling decision is not active authority.
- Phase status changes only in `docs/roadmap.md` and only after Gate evidence and independent
  review.
- Historical acceptance reports are append-only evidence; corrections use a visible
  erratum, not a rewrite that erases the original observation.

## 15. Independent review

Every work order receives a review by an agent/person who did not author the implementation.
Review against:

- the selected work-order scope;
- linked architecture invariant IDs;
- linked Gate IDs;
- actual diff and tests;
- authority bypasses and fail-open fallbacks;
- measurement units/denominators and claim wording;
- backward compatibility and artifact migration;
- secrets, remote effects, spend, and rollback.

The reviewer lists concrete findings by severity and file/line. The implementer verifies
each finding on actual code, fixes confirmed ones, records rejected ones with evidence, and
reruns gates. “Reviewed” without findings/resolution is not evidence.

## 16. Stop-and-ask conditions

Stop the affected path and request an owner decision before:

- factory alpha, LR, channel cap, default hard-publication cap, or statistical family policy,
  including the alpha auto-tighten trio protected by D-048: `PRECISION_TARGET`,
  `PRECISION_WINDOW`, and `ALPHA_FLOOR`;
- new-code or any new evidence-class pricing/certification contract;
- production isolation backend/platform commitment or controlled-subprocess profile /
  allowlist policy;
- paid work beyond approved protocol/cap;
- learned scheduler promotion from shadow to control;
- monitor intervention/quarantine;
- remote/public release, marketplace/package publishing, repository visibility, or writes
  to third-party systems;
- changing an architecture red line because current code cannot satisfy it;
- adding a CLI subcommand, a product surface, or a work-order prefix series that
  `docs/roadmap.md` does not already list, or reading/executing against any directory
  outside this repository's working tree (§7, §10);
- outcome-dependent sample/exclusion/retry changes;
- destructive handling of user/other-agent work.

Failing a quantitative gate does not itself require permission to diagnose or prepare an
experiment; it does require permission to lower/change the gate or broaden scope.

## 17. Handoff evidence

Every implementation handoff states:

```text
Work-order ID and dependency gates
Baseline and final SHA/branch
Files owned/changed
Behavioral contract and RED observed
Implementation and compatibility/migration
Focused, adjacent, full, security/empirical gate results
Artifact paths and digests
Paid/remote actions and exact cost, or explicit none
Independent review findings and resolutions
Known limits, rollback, and next unblocked work orders
```

If incomplete, say which Gate is missing and preserve structured DEFER/silent behavior. Do
not call a safe abstention a completed quality result.

## 18. Code map

```text
src/attest/review       current discovery, fixed S/T/V review flow, executor and ledger
src/attest/core         research binary-judge engine; generic decide helper reused today
src/attest/benchmark    corpus, receipts, replay/live/stability/experiments/reporting
src/attest/github       GitHub context, API client and presentation
src/attest/cli          local entry points
src/attest/data         product pricing/model configuration
src/attest/certification target package introduced by C-01
src/attest/scheduler     target package introduced by S-01
src/attest/execution     target package introduced by X-01
tests/                  deterministic unit/integration/adversarial tests
benchmarks/             frozen, versioned protocols/manifests/evidence
docs/                   normative map plus dated historical evidence
```

## 19. Historical references

- `docs/real-data-evaluation-status.md` — dated overnight report with audit errata;
- `docs/acceptance/phase-3.md` — historical Action integration smoke;
- `docs/superpowers/plans/` — completed archived implementation plans;
- `DECISIONS.md` D-020 through D-037 — historical differential/evaluation work;
- `DEVSPEND.md` — sole development API spend ledger.

They explain how the repository arrived here. They do not override the active target,
roadmap, or acceptance gates.
