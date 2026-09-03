# Handoff — 2026-09-04b (`5ebcf88` → this commit): the bundle was broken, the family was wrong, and a control published

**Window spend $13.187897 of $45; cumulative $47.837626 of the owner's new $90.** Product code
touched in four places (D-124, D-125, D-126, the silence line); everything else is measurement.
Remote writes: **none**. Gates at the tip: `ruff` clean, `mypy` clean over 80 files,
`git diff --check` clean, `pytest` exit 0 over the suite minus the docker-gated isolation
module, **and `tests/benchmark` green as well** — run exclusively. Run *concurrently* with the
`G-NULL-001a` study it produced three `test_m01_offline_measurement_probe` module-fixture errors
that vanish when nothing else touches the checkout; the same suite is green at `5ebcf88` in a
separate worktree and green at this tip when run alone. That is the 2026-09-02 backlog item —
**keep full-suite gates exclusive** — reproduced, not a regression from this window.

## 1. Product condition 2 was failing in the field (D-124)

`execute_differential` may replace the generated test before any behavioural run (D-114) and did
so by rebinding its own local `spec`; `verify_candidate` returned the **first** spec, so the
bundle was written from a test that never ran while `receipt.test_digest` named the one that did.

Three fail-closed changes: the differential carries the spec it executed; certification refuses
bytes whose digest is not the receipt's; and **certification verifies its own bundle offline,
seal included, before anything is author-visible** — a failure is a DEFER carrying the verifier's
own reasons. Two REDs, both confirmed failing on `5ebcf88`.

**All 86 bundles on this host re-verified: 44 accept, 42 do not**
([report](acceptance/2026-09-04-bundle-reverification.md)). **Four** are this defect, one of them
published; **38** are schema drift from before V-03/X-01. All 40 inside the workspace carry an
`unverifiable_v1.json` marker beside the manifest; nothing was deleted.

**Corrected corpus table:** certified 18 → **16**, below-threshold 8 → **7** (rows `d11`, `c02`).
Publication needs two numbers: **6 of the 7 publications stand**, and **the fixed product would
still have published 7** — the withdrawn receipt was a cluster representative and refusing it
promotes `38c316089d` on `d11`. Both are in the table. Errata added to the budget-wall and numpy
papers (5 → 4 and 7 → 6 verifiable receipts; their headlines unchanged).

## 2. The family is the change unit (D-125)

`e >= m_u/alpha` for the eligible candidates in the anchor's **file**, not the pull request.
`alpha`, LR, K and the cap untouched. The unit lives alone in `certification/units.py` behind a
policy version; the RED checks order-invariance, determinism and totality.
**The guarantee is now `alpha` within a unit and `hard_cap × alpha` across a PR, and that
weakening is the decision** — stated in the module, the paper and D-125.

Whole corpus recomputed offline through the real selector, $0
([paper](acceptance/2026-09-04-family-per-change-unit.md)): **the old rule reproduces the ledger
on 121 of 121 reviews**, publications go **12 → 24**, and **no control gains one** — which is the
condition the owner set for adoption. Median `m_u` is 2 against a median PR `m` of 4.

## 3. The default budget is $1.00 (D-126)

Two independent measurements: the budget wall (25 of 31 `BudgetExceeded` and 0 receipts at
$0.60, against 0 and 5 at $1.20) and the corpus's own count (39 of 75 reproduction failures).
Every operator page now carries the **measured** cost instead of the cap — $0.22 mean per review,
$0.31 on a PR with real code, $0.06 documentation-only. **Stated caveat: $1.00 is above two of
the three measured large changes, not all three** ($1.0338 on `d03`).

## 4. E-04 stratum v2 — 100 units, 7 shadow findings, nothing published

All 100 ran, none deferred, **$11.089240** ([report](acceptance/2026-09-04-e04-stratum-v2.md)).
495 candidates, 129 eligible, **21 receipts, 7 shadow findings on 3 units**. The 45
documentation units produced no eligible candidate at all, at $0.017 each. Every silence now
says `read N of M units` unconditionally — the product printed the "of M" only when the budget
bound it, which was found eleven units in; the stratum was **stopped, re-frozen and restarted
from zero** rather than finished under code that failed its own protocol.

**The number that matters:** replaying those three units through the pre-D-125 bar publishes
**nothing**. Under yesterday's rule this entire run would have been silent, with 21 receipts and
none author-visible. **This stratum is not prospective** and says so everywhere; `G-SHADOW-001`
is not advanced.

## 5. `G-NULL-001a` ran, and **failed** (D-127) — read this one first

58 controls qualified from **903 pre-cutoff commits examined** across eight public clones (a
**6.4%** qualification rate; 826 of 845 rejections are the untouched check). Manifest committed
before any paid call. Priced at the owner's $1.20/review, n = 100 costs $120, so $26 was reserved
with a hard cap.

**On the fifteenth control the product published — and the publication is wrong.**
`jinja` `ac3ac6c9`, 1,641 days old, untouched: it replaces one `functools.wraps` with a stacked
pair and says so in its own comment — *"the name from the async function"*. The generated test
asserts the **sync** name and fails on head for exactly that reason. The receipt is mechanically
perfect: head 3/3, base 3/3, isolation, fresh state, changed lines executed, bundle verifies.

**Root cause is structural.** Every rule asks *did the behaviour change, and is it bound to this
diff* — yes, twice. Only D-102 asks *did the author mean it*, and only for a `raise`/`assert` in
changed lines; this code raises nothing, and the receipt records the discriminator's silence
verbatim. **An intended change of a returned value is invisible to every discriminator the
product owns.** Separately: the published prose and the assertion that actually failed are
different claims, and nothing checks that they agree.

Per the owner's rule the run **stopped at once and was not resumed** — the fix moves what
publishes, so it is an owner decision of D-102's class. 43 controls unrun, **$25.41 released**.
Full account: [report](acceptance/2026-09-04-g-null-001a.md).

## 6. Mainline §1: three of six hold, and **no tag**

[Condition by condition](acceptance/2026-09-04-mainline-six-conditions.md). 1 **now holds** (the
Action commented on an outside repository). 2 **holds, and the previous "holds" was wrong**. 3, 4
and 5 do not. **Condition 4 moved further away, not closer**: it asks for silence on every
control, and §5 is the first properly qualified control the product has not been silent on.
`v0.1.0-pilot.1` remains the install ref.

## 7. Not done, and why

- **`G-NULL-001a` beyond n = 15.** The stop rule fired and the fix is the owner's; resuming
  before it would spend money on a known-broken condition.
- **The seven E-04 shadow findings are unadjudicated.** `G-SHADOW-001` needs a product-blind
  audit on evidence independent of the product; the agent that produced them is neither.
  `semantic_precision: INSUFFICIENT`, and `safety_stop_reached: false` means "none adjudicated
  wrong", not "none is wrong".
- **n = 100 for `G-NULL-001a` was not reached.** 58 was the population's yield at the
  preregistered quota; reaching 100 needs ~650 more commits screened (~2h of blame), and n = 300
  needs ~4,700, which those eight repositories do not contain. **More repositories, not more
  money.**
- **Bundles already written are not repaired.** The executed test bytes still exist under
  `.attest/repro/…`, but rewriting a sealed bundle is the forgery the seal exists to prevent.
- **No `G-SEC-002` work** (condition 3 untouched), no new-code pricing, no scheduler.

## 8. For the owner — three items

1. **A discriminator for intended behaviour change, or a narrower publication class (D-127).**
   The product cannot tell "the author changed what this returns" from "the author broke it",
   and it published on that. Shapes worth pricing, none touching alpha/LR/K/cap: (a) extend the
   intent policy from new rejections to *any* changed-line-bound behavioural difference, with a
   base-tree witness required exactly as D-102 requires one; (b) publish only when the reproduction's
   failure is a crash rather than a value mismatch; (c) require the claim's prose and the test's
   failing assertion to agree before publication, which also fixes the second defect in §5.
   **Until one of these lands, `G-NULL-001a` cannot be resumed and condition 4 cannot move.**
2. **Read D-125 and D-127 together.** The family change is what made the product speak — 7 shadow
   findings where the old rule published none — and D-127 says it does not yet know when to keep
   quiet. Keeping D-125 and fixing D-127 is one coherent position; so is reverting D-125 until
   D-127 is fixed. **Both are defensible and this is the owner's call.**
3. **`G-NULL-001a`'s population: more repositories, or a looser control rule?** The 6.4%
   qualification rate is the amendment applied to *every* changed text file, so a deleted
   changelog disqualifies a commit for reasons unrelated to defects (`click`: 3 of 120).
   Restricting the untouched check to the files a review can anchor in — Python — would raise the
   yield sharply and is a change to D-122, not to this window's work.
