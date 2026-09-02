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
2. every author-visible finding carries a differential receipt (test fails on head, passes
   on base, in isolation, repeated) that an offline verifier accepts (`G-CERT-001`,
   `G-SEM-001`);
3. head code cannot read secrets, reach the network, or forge a result (`G-SEC-001`..`003`);
4. on a held-out human-labelled defect corpus the product is silent on every control and
   certifies a stated, non-trivial share of eligible defects (`G-RECALL-002`,
   `G-NULL-001`);
5. one prospective shadow run on the owner's live repositories has produced no false
   publication (`G-SHADOW-001`);
6. the roadmap's L-01 exit list (install ref, quickstart, base-owned policy docs, support
   matrix, privacy/retention, failure copy, kill switch, rollback) is done.

Anything not needed for those six is not on the mainline. Explicitly off it until after
L-01: the learned scheduler (S-*), new-code pricing (N-01), the pricing-layer and F-facet
research, controlled subprocess allowlists (X-03), feasibility priority (R-04), and any
whole-repository scan surface.

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
| 16 | L-01 | stable install ref, quickstart, base-owned policy docs, executor support matrix, privacy/retention, failure-mode copy, kill switch and rollback, private pilot on one outside repository | the quickstart executed verbatim on a fresh clone of an outside repository yields a receipt-backed comment or a documented silence | L-01 exit; §5 decision D |

R-02 (structured-output recovery) is pulled forward between steps 7 and 8 only if the
step-7 table shows schema/parse failure as the largest loss between "candidates" and
"eligible". Otherwise it waits until after L-01.

## 3. Corpora

All corpora enter as clones under `.attest/corpora/<name>/` at a recorded commit
(`AGENTS.md` §7). No corpus is ever a sibling directory on the owner's machine.

- **Owner repositories.** Any repository under the owner's GitHub account may be cloned and
  used as a practice, control, natural-null or shadow population without asking. They are
  never the only defect corpus (RISK-EXTERNAL-01).
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
