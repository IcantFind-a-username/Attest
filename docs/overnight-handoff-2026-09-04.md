# Handoff — 2026-09-04 (`8a8d31a` → this commit): the budget was the wall, and the boundary held

**Window spend $3.181403 of $10; cumulative $34.649729 of $45.** Gates green on the GitHub
runner for the sync push (`33777373652`, 20m14s). Remote writes: `push main`, and the four
authorised `us-stock-helper` writes — nothing else.

## 1. Sync

`origin/main` carried `d3ec1b8`'s wrongly-scoped first cut of D-120 and its **failed** gates
run. The local eight commits were a fast-forward, so the rebase was a no-op; pushed, and
**`97fc907`'s correct rule — the literals the failing assertion's condition rests on, drawered
only when all of them are substituted — is now the version on `origin/main`, with green gates.**

## 2. Two budgets, on the pairs the budget was blocking ([paper](acceptance/2026-09-04-budget-wall.md))

Product code frozen at `fc2014f`; only the budget differs. **Both budgets are non-default —
the product default is $0.25.**

| | verifications | `BudgetExceeded` | reproduced | **receipts** | published | spend |
|---|---|---|---|---|---|---|
| `d02`+`d03`+`d16` at **$0.60** | 31 | **25** | 0 | **0** | 0 | $1.3427 |
| `d02`+`d03`+`d16` at **$1.20** | 31 | **0** | 5 | **5** | **0** | $2.7324 |

**Certification: 0 of 3 pairs → 3 of 3.** No review exhausted $1.20. What remains at $1.20 are
the other three failure modes — collection, faithfulness, binding: more budget does not fix
generation, it stops hiding it. **Nothing published**: thresholds of 80, 140 and 90 against
`m/α = 10m`.

**Erratum.** The stated criterion — pairs whose *every* failure was `BudgetExceeded` — selects
**zero** pairs against the complete ledger; the run log truncates stdout to 4,000 characters
and only looks pure. The three re-run are the ones where it dominates (86%, 78%, 75%).

## 3. numpy, and `Corum` ([paper](acceptance/2026-09-04-numpy-under-the-thread-cap.md), D-123)

`OPENBLAS_NUM_THREADS`/`OMP_NUM_THREADS`/`MKL_NUM_THREADS` = 1 in the job environment.
**`RLIMIT_NPROC` stays 0** — the option that keeps the boundary. Same four pairs, same
`--budget 0.60`, same container backend: **0 of 4 pairs → 4 of 4; 0 → 7 receipts; 0 → 4
published; $0.4046 against $0.5622.** Four pairs unblocked from one known cause measure no
recall.

## 4. `us-stock-helper` — condition 1 holds ([paper](acceptance/2026-09-04-us-stock-helper-action-comment.md))

Re-run of `33749092145` succeeded: the runner built the production image, ran a reproduction
in it and **posted a comment on an outside repository for the first time**. The comment is
`DEFER` — the candidate was found and correctly ruled a regression, then the generated test did
not collect. $0.044403, 0 certified. #4 closed, branch deleted, 404 confirmed.
**Screenshot: `docs/acceptance/assets/2026-09-04-us-stock-helper-pr4-comment.png`.**

## 5. `G-NULL-001` amended and priced ([paper](acceptance/2026-09-04-g-null-001-amendment.md), D-122)

A control is now: ≥6 months old **and** no later commit on the default branch touches a line it
added (`scripts/corpus/qualify_controls.py`, git only, $0). Requalifying the corpus:
**0 of 25 — and the age check alone decides every row.** The three repositories' whole
histories are 6 days, 7 days and 6 weeks, so **this account owns no controls under its own new
definition**; the population must be public clones (owner-authorised, read-only).

| n | 95% upper bound | cost at $0.2177 |
|---|---|---|
| 100 (**recommended**) | **2.95%** | **$21.77** ($13.97–$34.27) |
| 300 | 0.99% — the gate's bound | $65.31 |

≤1% needs n ≥ 300 whatever a review costs, above the whole cap. So `G-NULL-001` stays unpassed
and the affordable version is published beside it as **`G-NULL-001a`**, whose claim always
carries its own n and bound. **Nothing was run.** Bias stated: the rule selects cold code.

## 6. Not done, and why

- **`G-NULL-001` itself, and E-04 to 100 units** — instruction was to price, not run; option C's
  cap raise is not authorised.
- **The numpy fixture test did not finish on this host.** Its image (a tree declaring numpy) did
  not build inside the window. It is committed as the docker-gated guard; the fix's evidence is
  the direct container reproduction plus the `Corum` re-run, not a green fixture.
- **No product change beyond the two the owner ordered** (D-121 verifier, D-123 environment).
- **Receipts written before `attest.intent.v2` were unverifiable**; that is now fixed (D-121) and
  all 17 v1 bundles on this host verify again.

## 7. For the owner — three items

1. **An accepted, *published* receipt exists whose bundle does not verify offline.** Three cases,
   one of them published (`us-stock-helper` `75ce7a3425`, 2026-09-03): the bundle's
   `test_repro.py` is empty (`b"\n"`) while `receipt.test_digest` names the real test. Lead:
   `certify.py` builds the bundle's bytes from `verification.spec.test_body`, which is empty on
   a dedup/cluster path. **This is mainline §1 condition 2 failing in the field.** A background
   task is queued.
2. **Five certified receipts, zero published.** The budget that buys evidence and the threshold
   that publishes it are set independently; on a large change the product is silent by
   construction. Three shapes are costed in `backlog.md`, none touching α, LR, K or the cap.
   [define the family per change unit]
3. **`G-NULL-001a`: pick n and the clone list.** [n = 100, $21.77, bound 2.95%; cap raised to
   ~$55 so E-04's 100 units fit beside it]
