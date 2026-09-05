# Mainline to the product

This is the ordered list of steps between the current code and a product an outside
repository can install. It is written for the agent doing the work. The owner directs the
destination and answers the four decisions in §5; everything else is the agent's to decide,
using ordinary industry practice, and to record in one short `DECISIONS.md` entry.

Authority: `docs/roadmap.md` still owns work-order status and dependency order; this file
fixes the sequence in which the roadmap's orders are worked and the definition of "product".
When the two disagree, repair the roadmap. Work-order details, gates, and file seams are in
`docs/implementation/agent-work-orders.md` and `docs/acceptance/evolution-gates.md`.

## 1. What "product" means

The product is complete when all of the following hold, and not before:

1. an outside Python repository can install attest from a stable ref, add the Action, and
   receive PR comments — nothing else is a deliverable of this mainline;
2. every author-visible finding carries **the evidence form of its speech level (§1.1) and was
   admitted by that level's non-model adjudicator**, and where that form is a differential
   receipt (test fails on head, passes on base, in isolation, repeated) an offline verifier
   accepts it (`G-CERT-001`, `G-SEM-001`) — *amended 2026-09-04c: until then this condition
   named the receipt as the only admissible form, which made three of the four levels
   unshippable by definition*;
3. head code cannot read secrets, reach the network, or forge a result (`G-SEC-001`..`003`);
4. on a held-out human-labelled defect corpus the product is silent on every control and
   certifies a stated, non-trivial share of eligible defects (`G-RECALL-002`,
   `G-NULL-001`);
5. one prospective shadow run on the owner's live repositories has produced no false
   publication (`G-SHADOW-001`);
6. the roadmap's L-01 exit list (install ref, quickstart, base-owned policy docs, support
   matrix, privacy/retention, failure copy, kill switch, rollback) is done.

Anything not needed for those six is not on the mainline. Explicitly off it until after
L-01: the learned scheduler (S-*), the pricing-layer and F-facet research, controlled
subprocess allowlists (X-03), feasibility priority (R-04), and any whole-repository scan
surface. **N-01 is no longer off the mainline** — it is the gate level of §1.1.

### 1.1 The four levels of speech, and the evidence each one owes

*Owner decision, 2026-09-04c.* One rule runs through all four:

> **The LLM thinks; an algorithm decides whether it may speak.**

Every level has an adjudicator that **does not call a model**. A model may propose, phrase and
suggest; it may never be the thing that decides a finding is publishable. A level with no
working adjudicator ships nothing, however good its proposals look.

| level | what it claims | the evidence form it owes | its adjudicator (no model) |
|---|---|---|---|
| **red** | this change broke something that worked | a **differential receipt**: the generated test fails on head, passes on base, in isolation, repeated, changed lines executed, bundle verifies offline | the certification kernel, the binding policy, and the intent discriminator (D-102, D-120, D-128) |
| **gate** | this new code fails on an input the change makes reachable | an **executable failure of new code** on a witnessed reachable input — there is no base revision to compare against, so the failure itself is the evidence | reachability of the input plus the same execution, isolation and repetition the receipt demands (N-01) |
| **yellow** | this looks wrong, and here is exactly what I checked | the model states a hypothesis as **premises**; a deterministic checker verifies each premise separately; the finding states **only the premises that were verified** and its confidence is a function of which ones were | the premise checker: an unverified premise is deleted from the text, not softened |
| **green** | this is structurally so, here and here | a **computable structural measure** with **at least two concrete coordinates** (file and line, both ends) | the measure itself; the model is called only after the measure holds, and only to translate it and propose a fix |

Three consequences the levels are chosen for:

- **A level is defined by who decides, not by how sure the model sounds.** "Probably", "may",
  "consider refactoring" are not a level; they are the absence of one. Green in particular must
  never speak without coordinates.
- **Confidence is derived, never asserted.** At yellow the confidence is a stated function of
  the verified premises. A model-supplied confidence number is not evidence and is not shown.
- **Silence stays free.** Every level keeps the existing rule: no admissible evidence, no
  publication, and the drawer records why.

### 1.2 How a repository gets it: one way, and no keys

*Owner decision, 2026-09-04c.* **The only supported integration is a GitHub Action plus a
repository Secret.** The consuming repository stores its own `ANTHROPIC_API_KEY` as a
repository (or organization) Secret; the Action passes it to the review process as an
environment variable inside the repository's own runner.

**The product does not touch, store, transmit or log any key.** No hosted service, no proxy, no
key upload, no "connect your account" flow, no key written to disk or to a ledger, and no key
value in any log line, receipt, bundle or error message — a missing key is reported by name
only (§ the failure copy in `docs/github-action.md`). Anything that would require the product to
hold a customer key is out of scope for this mainline, whatever it would enable.

`attest init` is **demoted to an optional convenience** that writes a workflow file the operator
could have copied by hand. It is ordered last, after every level ships, and no step depends on
it. The quickstart's first screen is the workflow file itself, copyable whole.

### 1.3 The order the levels are built in, and why

**v3 → green → gate → yellow.** *Owner decision, 2026-09-04c.*

1. **v3, then v4, then v4.1** (`attest.intent.v4.1`, D-134; v4 was D-132, v3 D-128) — done.
   Red stops publishing intended value changes, and after `urllib3 c7b9adcb` published under v3
   it also stops when the failing assertion is not an assertion, when the value it pins is
   generic, and when the diff states its own intent — which it does only where the diff names
   the symbol in a form a reader takes for code (D-134). On the corpus replay the value class
   certifies **0 of 48** under v4 and under v4.1: the recall cost is the decision.
2. **green** — first, because it costs **zero execution and near-zero API**: the measure is
   computed deterministically and the model is called once, after the evidence already holds. It
   is therefore the cheapest possible test of the whole architecture — *does "the LLM thinks, the
   algorithm decides" actually hold up when a real level ships on it?* — and if the answer is no,
   it is discovered for the price of a lint pass rather than the price of a corpus.
   **Author-visible since D-133** (2026-09-05): at most two notes per pull request, marked
   `structural`, in their own section, wording adjudicated against the real model first.
3. **gate** — second, because it needs execution and isolation, which already exist, but a
   reachability witness, which does not. **In shadow since D-137** (owner decision 2 of
   2026-09-05c): `docs/design/gate-level.md` is implemented and runs behind
   `ReviewConfig.gate_shadow`, which is **off** in the product; on, a review additionally asks
   the gate question of its new-code candidates and writes the answer to the ledger and to
   `.attest/shadow/gate/` and to nothing else. `G-NEWCODE-001` now says in its own text that
   the pilot precondition governs speech rather than observation and that shadow records count
   toward its 120 cases, so the two documents agree and the reading is **A with the carve-out**:
   the design is N-01's first contract alternative, it ships early only in shadow, and the
   pilot's defects are collected by the thing itself.
4. **yellow** — last, because a premise checker is the largest new deterministic surface of the
   four and the easiest to fake; it should be built when the pattern it follows has already been
   demonstrated twice.

## 2. Steps, in order

One step per task. Each step names its goal, the single required RED test (D-058), its exit
gate, and what it must not do. A step is done when the RED passes, the repository gates
pass once at the end, and the roadmap checkbox and a `DECISIONS.md` entry exist.

| # | Order | Goal | The one RED | Exit |
|---|---|---|---|---|
| 1 | C-02 | CI, CLI and GitHub presentation consume only `CertifiedFinding`; the S/T direct-surface path is deleted | a finding at S·T cap with no receipt produces no author-visible output under every alpha and config | `G-CERT-001` |
| 2 | C-03 | merge-base resolved; policy loaded from base/defaults, digested into task and receipt; head cannot relax it | head sets alpha=1.0; output equals the base-policy output | `G-CERT-002` |
| 3 | C-04 | manual/rename evidence lives in its own namespace, never enters automated publication or calibration denominators; old ledgers readable unchanged | one manual reproduction row moves no finding across a threshold and no precision window | `G-CERT-003` |
| 4 | R-03 | order-invariant dedup; candidates classified regression / new-code / non-Python / unsupported-executor before any paid generation; only regression-eligible candidates enter V | shuffle a candidate batch: clusters and eligibility labels are identical | `G-RECALL-001` (dedup part) |
| 5 | R-01 | merge-base chunks, old-side deletion anchors, renames, definition/caller/test retrieval, per-chunk budget | a cross-file defect (callee signature changed, caller not) — the proposer context contains the caller | roadmap R-01 |
| 6 | V-01 | reproduction schema versioned; receipt binds test bytes, node id, collection count, zero skip/xfail, per-run output, commands, interpreter and environment digests | flip any byte of a receipt; the verifier rejects it | `G-SEM-001` |
| 7 | E-02 pilot | run the full pipeline (K=4) on the dev slice of the corpus in §3; report candidates, eligible, certified, control false publications, silence rate; no product code changes | none — the deliverable is the table | fork in §4 |
| 8 | C-05 | PR-level multiplicity per §5 decision A; order-invariant semantic cluster seam; deterministic tie-breaks; one hard author-visible cap across inline and summary | a PR with m eligible candidates never publishes more than the cap, and never publishes one whose e-value is below the family threshold | `G-CERT-004` |
| 9 | V-02 | the smallest binding policy that rejects a test proving a different defect or branching on source version; compare trace/coverage/mutation/patch-ablation on adversarial tests, adopt one | an adversarial test that passes the differential check but exercises none of the diff lines is rejected | `G-SEM-002` |
| 10 | X-01 | privileged controller split from executor by a versioned request/result protocol with task nonce and content-addressed artifacts; development adapter | an executor result whose artifact digest does not match the request nonce is rejected | roadmap X-01 |
| 11 | X-02 | one production Linux isolation backend per §5 decision B: no network, read-only root, non-root, no inherited env, fresh tmpfs | head code that reads an env secret, opens a socket, or writes outside the work dir fails and the run is marked, not certified | `G-SEC-001`..`003` |
| 12 | V-03 | fresh writable state per repeat; atomic per-run persistence; authenticated controller provenance; offline receipt verifier shipped as a CLI | a receipt produced by a run with a stale work dir is rejected | `G-SEM-003` |
| 13 | E-02 held-out | the full protocol on the held-out slice of §3; blind semantic truth, controls, precision, eligible detection | none — numbers | `G-RECALL-002`, `G-MEASURE-004`, `G-CORPUS-001` |
| 14 | E-01 | natural-null study on the owner's repositories' real recent PRs (no known defect) | none — numbers | `G-NULL-001` |
| 15 | E-04 | prospective shadow on the owner's live repositories, blind, no publication | none — numbers | `G-SHADOW-001` |
| 16 | L-01 | stable install ref, quickstart, base-owned policy docs, executor support matrix, privacy/retention, failure-mode copy, kill switch and rollback, private pilot on one outside repository | the quickstart executed verbatim on a fresh clone of an outside repository yields a receipt-backed comment or a documented silence — **the silence branch is met on nine commits; the receipt branch has never been taken** (D-109, whose population was mis-constructed: see §3 and D-116) | L-01 exit; §5 decision D |

R-02 (structured-output recovery) is pulled forward between steps 7 and 8 only if the
step-7 table shows schema/parse failure as the largest loss between "candidates" and
"eligible". Otherwise it waits until after L-01.

## 3. Corpora

All corpora enter as clones under `.attest/corpora/<name>/` at a recorded commit
(`AGENTS.md` §7). No corpus is ever a sibling directory on the owner's machine.

- **Owner repositories.** Any repository under the owner's GitHub account may be cloned and
  used as a practice, control, natural-null or shadow population without asking. They are
  never the only defect corpus (RISK-EXTERNAL-01).
  **Pair construction for a receipt pilot (D-116, correcting D-109):** for a repairing
  commit `F`, the pair is **head = `F^` (the parent), base = `F`** — never "the commit that
  last touched the lines `F` removed", which is what `git blame` answers and which selected a
  pair with no regression in it. A pair enters the population only if `F`'s **own
  human-written tests discriminate it**: copied onto both sides and run there, at least one
  test fails on head and passes on base. That check costs nothing and is run before any
  paid review.
- **BugsInPy.** Already importable through `attest.benchmark.corpus.import_bugsinpy` from a
  pinned local tree; human-verified real Python defects with the fixing commit. Use it for
  eligible-regression cases.
- **SWE-bench Verified.** 500 human-validated Python instances, each with a base commit, a
  gold patch and hidden `FAIL_TO_PASS` tests. Build a regression PR as base = base_commit
  with the gold patch applied, head = base_commit; the product must never see the gold
  tests — they are used only to score whether the product's own generated test is a true
  reproduction. This is the preferred hidden-truth corpus for steps 7 and 13.
- **Controls.** Refactor-only, docs-only and test-only commits from the same repositories,
  built the same way, in at least equal number to defects.
- **Split.** Before step 7, write the instance list once: a dev slice (at most 20% of
  instances, used for steps 7 and for debugging) and a held-out slice (used once, at
  step 13). The split is committed before any run and never edited afterwards. No factory
  constant is tuned on either slice; a constant change remains a §16 owner decision.

## 4. The fork after step 7

The step-7 table decides the next task without asking the owner:

- certified ≥ 5 on the dev slice and control false publications = 0: continue to step 8;
- certified < 5 and the largest loss is candidates→eligible: revisit step 4 (R-03), then
  R-02 if parse failure dominates;
- certified < 5 and the largest loss is eligible→certified: revisit step 5 (R-01) context,
  then the executor's reproduction prompt and token budget within their existing caps;
- any control false publication: stop, root-cause under RISK-CERT-01, fix, re-run the dev
  slice; nothing else proceeds until it is zero.

## 5. Decisions the owner makes — everything else is the agent's

Each comes with a recommended default; the owner can answer with one word.

| | Decision | Needed before | Recommended default |
|---|---|---|---|
| A | PR-level multiplicity method | step 8 | e-value Bonferroni: a candidate publishes only when its e-value ≥ m/α for m eligible candidates in the PR, plus the hard inline cap; the arithmetic mean of the candidates' e-values reports the PR-level global null |
| B | production isolation backend | step 11 | rootless OCI container (Docker or Podman, whichever the CI platform provides) with `--network none`, read-only rootfs, tmpfs work dir, non-root user, empty environment, dropped capabilities; GitHub Actions Linux runners first |
| C | paid spend for steps 7, 13, 14, 15 | before each | agent posts the pre-reservation in `DEVSPEND.md`; owner raises the cap or not |
| D | public release and the pilot repository | step 16 | owner names the repository; agent does the rest |

Everything not in that table — library choice, file layout, error handling, schema
details, retry policy, test shape, naming, which linters, how to structure a CLI — is the
agent's call under ordinary industry practice. Search when unsure, decide, write one
`DECISIONS.md` entry of at most six lines, and move on. The owner does not read code.

## 6. Reporting

A step's handoff is at most one page: baseline and final SHA, the RED and its result, the
numbers if the step produced any, at most three items for the owner (each a yes/no
question with a default), and the one-line decision entry. A backlog item for an
unreproduced observation goes to `docs/backlog.md`, not to the owner. Twenty-three open
questions is a failed handoff, not a thorough one.
