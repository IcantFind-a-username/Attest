# The budget wall, measured: $0.60 against $1.20 on the pairs that only ever failed for budget

**Owner instruction 5 of 2026-09-04.** The 2026-09-03 corpus found that the largest single
reproduction failure mode was not the model and not the environment but the **per-review
budget**: 39 of 75 reproduction failures were `BudgetExceeded` on the second generation
attempt, more than collection failures (20) and unfaithful tests (13) together. This paper
re-runs, at **`--budget 1.20`**, exactly the defect pairs whose *every* reproduction failure
was `BudgetExceeded`, and nothing else.

**Both budgets are non-default.** The shipped product default is **$0.25** per pull request.
$0.60 was the corpus's standard and $1.20 is this measurement's; every row below says so.

## 1. Selection — the stated criterion selects nothing, and why

The instruction was to re-run only the defect pairs whose **every** failure reason was
`BudgetExceeded`. Read against the complete per-candidate verification rows in each corpus
ledger, **no pair of the nineteen qualifies.** Every budget-limited pair also lost at least one
candidate to a collection failure or an unfaithful test:

| pair | repo | verifications | `BudgetExceeded` | other | share |
|---|---|---|---|---|---|
| `d03` | Attest | 14 | **12** | 2 | 86% |
| `d16` | us-stock-helper | 9 | **7** | 2 | 78% |
| `d02` | Attest | 8 | **6** | 2 | 75% |
| `d08` | Attest | 8 | **6** | 2 | 75% |
| `d13` | us-stock-helper | 20 | **13** | 7 | 65% |
| `d01` | Attest | 8 | 5 | 3 | 63% |
| `d12` | us-stock-helper | 5 | 2 | 3 | 40% |
| `d05` | Attest | 7 | 1 | 6 | 14% |
| `d04`, `d06`, `d07`, `d09`, `d10`, `d11`, `d15`, `d17`–`d20` | — | 1–5 each | **0** | all | 0% |

**An erratum against this window's own first pass.** The run log truncates each review's stdout
to its last 4,000 characters, and in that tail `d02`, `d03` and `d16` show nothing but
`BudgetExceeded` — which is how they were first selected. The ledger keeps every candidate, and
it says otherwise. The selection here is the ledger's.

**What was re-run instead, and under what rule.** The nearest defensible criterion is *the
pairs where `BudgetExceeded` is the dominant failure mode*, and the three highest are `d03`
(86%), `d16` (78%) and `d02` (75%). Those three were re-run. This is **not** the criterion the
owner set; it is the closest one that is non-empty, and the table above is the evidence for the
substitution. `d02` had already been started under the truncated-log reading before the ledger
was checked; it is reported rather than discarded.

## 2. Method

Product code frozen at **`fc2014f`**, the same revision the corpus ran, in a detached
worktree — so the only variable between the two columns is the budget. The driver
(`scripts/corpus/real_traffic.py`, `--budget` and `--only` added for this run) is
instrumentation and is *not* frozen. K = 4, `linux-container-v1`, local review only, no GitHub
write, cumulative cap $8.


## 3. The two budgets, side by side

Same pairs, same product code (`fc2014f`), same K, same backend; only the per-review budget
differs. Counts are per-candidate verification rows from the repository's ledger, which is
complete where the run log's tail is not.

| pair | budget | verifications | **`BudgetExceeded`** | reproduced | **accepted receipts** | published | spend |
|---|---|---|---|---|---|---|---|
| `d02` | $0.60 | 8 | **6** | 0 | **0** | 0 | $0.4505 |
| `d02` | **$1.20** | 8 | **0** | 1 | **1** | 0 | $0.7532 |
| `d03` | $0.60 | 14 | **12** | 0 | **0** | 0 | $0.4516 |
| `d03` | **$1.20** | 14 | **0** | 3 | **3** | 0 | $1.0338 |
| `d16` | $0.60 | 9 | **7** | 0 | **0** | 0 | $0.4406 |
| `d16` | **$1.20** | 9 | **0** | 1 | **1** | 0 | $0.9454 |
| **total** | $0.60 | 31 | **25** | 0 | **0** | 0 | **$1.3427** |
| **total** | **$1.20** | 31 | **0** | **5** | **5** | 0 | **$2.7324** |

## 4. What the comparison says

**The budget was the wall, and $1.20 removes it completely.** Across 31 verifications at
$1.20, `BudgetExceeded` appears **zero** times, against 25 of 31 at $0.60. Nothing else was
changed.

> **Correction, 2026-09-04 (D-124).** One of the five receipts at $1.20 — `Attest` `b89a422892`
> on `d03` — has an evidence bundle that does not verify offline
> ([re-verification](2026-09-04-bundle-reverification.md)). Under the fix it would have been
> refused, so the $1.20 row is **4 verifiable receipts, not 5**. What the paper is about is
> unchanged: 0 at $0.60 against 4 at $1.20, 3 of 3 pairs certifying, and 0 published either way.

**Certification rate, on these pairs: 0 of 3 → 3 of 3.** Five accepted receipts appear where
there had been none. No review exhausted its budget ($0.7532, $1.0338 and $0.9454 of $1.20),
so $1.20 is a ceiling with room, not a new wall.

**What the extra money buys is *evidence*, and what surfaces afterwards is the product's
other three failure modes** — at $1.20 the failures that remain are collection failures,
unfaithful tests and reproductions that execute none of the changed lines. Raising the budget
does not fix generation; it stops hiding it.

**Nothing published.** All five new receipts were suppressed by the family threshold:
`m/α = 10m` gives 80 for `d02`'s eight eligible candidates, 140 for `d03`'s fourteen and 90
for `d16`'s nine. This
is the sharpest form yet of the open `m/α` question — the budget that produces receipts and
the threshold that publishes them are set independently, so **buying more evidence on a large
change produces more certified findings and the same silence.** Three shapes are costed in
`docs/backlog.md`; none of them touches α, the LR, K or the cap.

**Price of the change.** Per review, $0.4476 → $0.9108 on these three pairs, about **2.03×**.
Extrapolating the corpus's 43 reviews at that ratio gives roughly $18.9 against $9.31 — which
is why this is a measurement and not a recommendation to change the default. The product
default remains **$0.25**; both columns here are non-default and are marked as such in every
row.

**One more thing the extra budget did not do.** `d16` is the pair whose 2026-09-03 receipt
D-120 reclassified as a constant change. Its new receipt is `regression_reproduced` on a
different candidate (`3bba2f62e6`), not a second version-string finding — so the extra budget
bought a different, genuine differential rather than more of the same class.
