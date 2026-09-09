# Every receipt the score bar has ever hidden — a free census of all 220 ledgers

**Owner instruction 1 of this window.** Question: *has the priority-score threshold ever hidden a
reproduction V had already accepted?*

**Answer: yes, 35 times, and 29 of those 35 were held back by a bar the score could not have
reached under any evidence this product actually buys.** No model call, no execution, **$0.00**:
the census reads ledgers already on disk. Data:
[`evidence/2026-09-12-suppression-census.json`](evidence/2026-09-12-suppression-census.json).

## 1. What was read, and what a row here means

Every `*.jsonl` under `.attest/` and `docs/acceptance/evidence/` — **220 files, 574
`publication_policy` rows**. That row is written by `run_verification_stage` immediately after
`select_for_publication`, and it lists `published` and `suppressed` by candidate id with a
reason.

The population is closed by construction: `select_for_publication` is called with
`certified_by_id.values()`, so **every id in a `suppressed` list is a certified finding** — an
accepted receipt, a reproduction the kernel took. The census confirms it row by row rather than
resting on the code path: all 48 suppressed entries carry a same-task `certification` row reading
`accepted` and a same-task `verification` row reading `reproduced`.

| | |
|---|---|
| published entries | **84** |
| suppressed entries | **48** (deduped by task + candidate + reason; no duplicates were found) |
| — `below family threshold` | **35** — 33 distinct candidates over 17 distinct reviews |
| — `same defect as a published finding` | **13** |
| — `beyond the hard author-visible cap` | **0** |
| all suppressed are `certification: accepted` + `verification: reproduced` | **48 of 48** |

The 13 same-defect suppressions are the cluster rule working: in each one the defect *was*
published, under another candidate id, and only the duplicate line was withheld. **The hard cap
has never suppressed anything.** The rest of this report is about the 35.

**What this census does not count.** Candidates the intent discriminator drawered, the probe
refused, or the executor deferred never became certified findings and never reached
`select_for_publication`. They are not suppressions of evidence; they are the absence of it. Only
the last gate — score against `m_u/α` — is measured here.

## 2. The score field, and the one that looks like it

The `review` ledger row carries `wealth_final`, and it is **not** the priority score the
publication policy applies. `ledger.record_review` is called in `run_review`'s
`review_accounting` phase, **before** verification, and the row says so itself: every one of the
2,589 review rows in this repository reads `authority: "ranking"`.

Three independent checks pin the real score at **`review` wealth × 20**:

1. `channels.verification_lr(reproduced=True)` returns `V_CAP = 20.0`;
2. on the 35 `publication_policy` rows whose `eligible_count` is 1, `mean_e_value` *is* that one
   candidate's score, and it equals the review row's `wealth_final` × 20 in **35 of 35** rows
   (2.0 → 40.0, 2.9485 → 58.970769, 3.0 → 60.0);
3. the two suppressed candidates that also have a same-task `ci_final` decision — the row whose
   comment says *"the S/T/V wealth is kept beside it"* — read 40.0 and 60.0 where their review
   rows read 2.0 and 3.0.

A published finding settles it from the other side: 16 of the 84 published entries have a review
row reading `wealth_final: 2.0`, and no bar is ever below `1/α` = 10. A score of 2.0 could not
have published anything.

**This corrects a number in [D-182](../../DECISIONS.md).** That entry describes the 25 findings
its replay would have published as being at *"priority scores **2.0–3.0** against bars of
**50–140**"*, and concludes that *"no suppressed score is within a factor of **17** of its bar."*
The scores are the pre-verification ranking field. Read at the value the policy actually applied,
the same suppressions are at **40.0–60.0** against the same bars, and the nearest is within a
factor of **1.017**. D-182's decision is the owner's and is not reopened here; the arithmetic
underneath one of its sentences is.

## 3. The ceiling, which is the real finding

`S` caps at 3.0, `T` caps at 3.0, `V` is 20.0, so a certified finding could in principle score
180. It never has. **Across all 2,589 recorded `review` rows in this repository, the channels
bought are `("S",)` and nothing else** — `T` has never contributed to any recorded score, not in
the corpus drivers (which pass `tier0_commands=[]`) and not on shipped traffic: the external
receipt of 2026-09-12, run from `@v0.1.0-rc.2` with the quickstart defaults and therefore
`tier0_commands = ["ruff"]`, recorded `channels_bought: ["S"]` and `wealth_final: 3.0` → 60.0.

So the reachable ceiling of a certified finding, as this product has actually ever run, is

    S_CAP x V_CAP = 3.0 x 20.0 = 60.0

and the bar is `m_u/α` = **10 · m_u** at the factory α of 0.1. Therefore:

> **A change unit holding 7 or more eligible candidates cannot publish a receipt at all.**
> 60 < 70. Not improbably — arithmetically, whatever the evidence shows.

The four distinct scores ever observed are 40.00, 52.78, 58.97 and 60.00: the S vote schedule
(2.00, 2.64, 2.95, 3.00) times 20.

## 4. The 35, each with its candidate id, score and the `m_u` in force

Sorted by how close each came. `score/bar` above 1 would have published.

| candidate | score | bar `m_u/α` | score/bar | `m_u` | α | class | ledger |
|---|---|---|---|---|---|---|---|
| `f118070241` | 58.97 | 60.0 | **0.983** | 6 | 0.1 | (pre-schema) | us-stock-helper |
| `a47e7a8fa9` | 60.00 | 70.0 | 0.857 | 7 | 0.1 | regression_reproduced | attest |
| `db100c9818` | 60.00 | 70.0 | 0.857 | 7 | 0.1 | regression_reproduced | attest |
| `1cf3efe423` | 40.00 | 50.0 | 0.800 | 5 | 0.1 | regression_reproduced | attest |
| `683c292257` | 40.00 | 50.0 | 0.800 | 5 | 0.1 | regression_reproduced | attest |
| `bb40cb1629` | 40.00 | 50.0 | 0.800 | 5 | 0.1 | regression_reproduced | attest |
| `250c5e3d67` | 40.00 | 50.0 | 0.800 | 5 | 0.1 | regression_reproduced | attest |
| `33aa333ec0` | 40.00 | 50.0 | 0.800 | 5 | 0.1 | regression_reproduced | us-stock-helper |
| `103aa42a3c` | 52.78 | 70.0 | 0.754 | 7 | 0.1 | behavior_change | attest |
| `6cce86432e` | 52.78 | 70.0 | 0.754 | 7 | 0.1 | regression_reproduced | attest |
| `c5b90ad887` | 60.00 | 80.0 | 0.750 | 8 | 0.1 | regression_reproduced | us-stock-helper |
| `58a3076775` | 58.97 | 90.0 | 0.655 | 9 | 0.1 | regression_reproduced | pilot-d116 |
| `058f573208` | 40.00 | 70.0 | 0.571 | 7 | 0.1 | regression_reproduced | attest |
| `0ab1e8313a` | 40.00 | 70.0 | 0.571 | 7 | 0.1 | regression_reproduced | attest |
| `0e910940fa` | 40.00 | 70.0 | 0.571 | 7 | 0.1 | regression_reproduced | attest |
| `5576277bdb` | 40.00 | 70.0 | 0.571 | 7 | 0.1 | regression_reproduced | attest |
| `99e457d77f` | 40.00 | 70.0 | 0.571 | 7 | 0.1 | regression_reproduced | attest |
| `27dd3692d7` | 40.00 | 70.0 † | 0.571 | 7 | 0.1 | regression_reproduced | us-stock-helper |
| `33243bfa2e` | 40.00 | 70.0 † | 0.571 | 7 | 0.1 | regression_reproduced | us-stock-helper |
| `8f3851fe4b` | 40.00 | 80.0 | 0.500 | 8 | 0.1 | regression_reproduced | attest |
| `3bba2f62e6` | 40.00 | 90.0 | 0.444 | 9 | 0.1 | regression_reproduced | us-stock-helper |
| `1d0af73c3e` | 40.00 | 100.0 | 0.400 | 10 | 0.1 | regression_reproduced | us-stock-helper |
| `b89a422892` | 52.78 | 140.0 | 0.377 | 14 | 0.1 | behavior_change | attest |
| `dad85d4e84` | 52.78 | 140.0 | 0.377 | 14 | 0.1 | regression_reproduced | attest |
| `0561204f7d` | 40.00 | 110.0 | 0.364 | 11 | 0.1 | regression_reproduced | attest |
| `14b3a1e026` | 40.00 | 110.0 | 0.364 | 11 | 0.1 | regression_reproduced | attest |
| `14b3a1e026` ‡ | 40.00 | 110.0 | 0.364 | 11 | 0.1 | regression_reproduced | attest |
| `25d170ba38` | 40.00 | 110.0 | 0.364 | 11 | 0.1 | regression_reproduced | attest |
| `5f4497390b` | 40.00 | 110.0 | 0.364 | 11 | 0.1 | regression_reproduced | attest |
| `240836f2e0` | 40.00 | 120.0 | 0.333 | 12 | 0.1 | regression_reproduced | us-stock-helper |
| `240836f2e0` ‡ | 40.00 | 120.0 | 0.333 | 12 | 0.1 | regression_reproduced | us-stock-helper |
| `2c982b3cf3` | 40.00 | 120.0 | 0.333 | 12 | 0.1 | regression_reproduced | us-stock-helper |
| `3a3b414a24` | 40.00 | 120.0 | 0.333 | 12 | 0.1 | regression_reproduced | us-stock-helper |
| `67dae52f8e` | 40.00 | 120.0 | 0.333 | 12 | 0.1 | regression_reproduced | us-stock-helper |
| `d2c15a3f07` | 40.00 | 140.0 | 0.286 | 14 | 0.1 | regression_reproduced | attest |

† the row records two unit thresholds (70.0 and 80.0) and not which one the candidate's own unit
carried. Both exceed the score, so the suppression is unambiguous and the smaller is quoted.
Three rows of the 50.0 group are the same shape — `{10.0, 50.0}` — and there the reason itself
resolves it: a score of 40.0 recorded as *below* its bar cannot have been judged at 10.0.

‡ the same candidate in a second review of the same repository: two reviews, not one row counted
twice. 33 distinct candidates, 35 suppressions.

**Split by whether the bar was reachable at all:**

| | count |
|---|---|
| bar **above 60.0** — no certified finding of any strength could have cleared it | **29** |
| bar at or below 60.0 — the finding lost on its S vote count | **6** |

The six are `f118070241` (58.97 against 60.0, one vote short of the S cap), and five at 40.0
against 50.0 — two S votes where three would have published.

## 5. What this does and does not say

**Says.** The bar is not a rare tie-breaker. It suppressed 35 accepted reproductions, and in 29
of them the outcome was fixed before the evidence was bought: the unit had 7 or more eligible
candidates, so its bar was above the reachable ceiling. `m_u` counts *eligible candidates*, not
defects, so a change unit that produces many plausible candidates is the one whose real defect is
hardest to publish.

**Does not say.** Whether any of the 35 is *right*. A reproduction proves a differential, and the
intent discriminator has already run — but nothing here adjudicates whether the author should
have been told. This is a count of what the bar hides, exactly as D-182's baseline was, and like
it, it changes no rule. `alpha`, the likelihood ratios, `k_samples`, the hard cap and the
publication rule are untouched by this report.

**And one thing worth the owner's attention.** The `T` channel has never fired. Whatever the
tier-0 signal was meant to contribute to ranking, it contributes nothing today, and the score's
whole dynamic range on certified findings is the four values of the S vote schedule.
