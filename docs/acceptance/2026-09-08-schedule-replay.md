# The discovery schedule, replayed offline over two populations

**Owner decision 1 of 2026-09-07 · D-168.** Data:
[17 commits](evidence/2026-09-08-schedule-replay-17.json) ·
[11 forward pairs](evidence/2026-09-08-schedule-replay-forward.json) · driver
`scripts/corpus/schedule_replay.py`. **$0.00** — nothing was bought; the ledgers, plans,
candidate stores and per-sample token counts of the two recorded runs were already on disk.

## The rule

1. the **proposal stage** may spend at most **30%** of one review's budget, the first change
   unit included (`PROPOSAL_SHARE` 0.6 → 0.3, and D-111's first-unit exemption removed);
2. candidates rank by **cluster size** descending, ties broken by **static credibility** — the
   anchor is inside a definition in a non-test Python file (+1), and that definition is called
   somewhere in the tree (+1) — then by `finding_id`;
3. at most **3** reproductions per **change unit** (the changed file); the rest are recorded, in
   the ledger and in `--explain`, as `ranked below verification cap`.

## What is exact and what is estimated

**Exact.** The plan's per-unit character counts, so which units the ceiling admits is arithmetic
on recorded numbers. Discovery's actual cost, priced from the recorded per-sample token counts at
the shipped table — with samples the attempt cache **replayed** counted at $0.00, which is what
they cost. Every candidate's anchor, cluster size and eligibility. The credibility score,
recomputed from the head tree of the recorded commit. Which candidates the recorded run verified,
and which receipts it published.

**Estimated.** What one reproduction costs. The ledger records a review's total and each
verification's outcome, not each verification's price, so the replay uses each run's own mean —
`(total − discovery) / verifications attempted`. Predicted spend is therefore a mean-cost
projection and is not quoted to the cent.

**One modelling detail decides the answer, and getting it wrong reverses the result.** A
reservation is *transient*: `propose` reserves K samples at the 3,200-token output bound, then
`settle` replaces each reservation with what the call actually cost. So a unit is admitted when
*what discovery has already spent* plus *this unit's reservation* fits the ceiling — not when the
sum of all reservations fits. The first version of this replay accumulated reservations, read the
ceiling as three times tighter than it is, and reported that the rule would lose two of the three
receipts. It does not. The corrected model is in `units_under_the_share`, with the reason.

## The two populations

| | **17 commits** (D-166, `--budget 1.00`) | **11 forward pairs** (2026-09-06b probe run) |
|---|---|---|
| units read | 76 → **46** | 31 → **31** |
| regression-eligible candidates | 168 → **142** | 98 → **98** |
| reproductions bought | 168 → **79** | 98 → **51** |
| held back by the per-unit cap | — → **63** | — → **47** |
| spend | $10.2659 → **$5.2353** | $2.0313 → **$1.0763** |
| **receipts published** | 0 → **0** | **3 → 3** |
| candidates verified that were not before | **0** | **0** |
| first unit refused by the 30% ceiling | **0 of 17** | **0 of 11** |

**Half the money, every receipt.** The forward pairs are the only population in this project's
history where red has ever published, and all three receipts — `488ede460e` (click),
`ac074352b1` (itsdangerous), `0c8e71fe96` (more-itertools) — are still bought.

### Per commit, the 17

| commit | repo | units | eligible | reproductions bought | predicted / recorded |
|---|---|---|---|---|---|
| `eede42194d` | attest | 5/5 | 24/24 | 10 of 24 | $0.3688 / $0.8852 |
| `9b1c9a8699` | attest | 1/1 | 4/4 | 3 of 4 | $0.1931 / $0.2575 |
| `8537f6a9d3` | attest | 3/3 | 0/0 | 0 of 0 | $0.0636 / $0.0636 |
| `150804a34b` | attest | 3/4 | 16/16 | 13 of 16 | $0.7337 / $0.9171 |
| `993ae171e7` | attest | 1/1 | 5/5 | 3 of 5 | $0.2731 / $0.4551 |
| `48b418c895` | attest | 3/10 | 7/22 | 3 of 22 | $0.2130 / $0.9169 |
| `c88f67e599` | attest | 4/6 | 20/20 | 9 of 20 | $0.4522 / $0.8994 |
| `820b973d09` | attest | 2/2 | 2/2 | 2 of 2 | $0.1573 / $0.1573 |
| `84c75985a0` | attest | 3/9 | 0/11 | 0 of 11 | $0.1499 / $0.8763 |
| `6579a8fec7` | attest | 3/5 | 8/8 | 3 of 8 | $0.3218 / $0.7150 |
| `4c3492065c` | attest | 2/2 | 0/0 | 0 of 0 | $0.0158 / $0.0158 |
| `3f6b67b0b6` | us-stock-helper | 1/1 | 8/8 | 3 of 8 | $0.1917 / $0.5113 |
| `ead0bd75d4` | us-stock-helper | 3/3 | 8/8 | 5 of 8 | $0.4002 / $0.5846 |
| `4ef2226bcf` | us-stock-helper | 3/3 | 9/9 | 6 of 9 | $0.4732 / $0.6588 |
| `801fb292ce` | us-stock-helper | 4/8 | 10/10 | 6 of 10 | $0.5162 / $0.8856 |
| `abefa25f7d` | us-stock-helper | 2/6 | 7/7 | 3 of 7 | $0.2095 / $0.6054 |
| `8cfab6c5a7` | us-stock-helper | 3/7 | 14/14 | 10 of 14 | $0.5021 / $0.8609 |

Two commits lose most of their candidates to the **share** rather than the cap — `48b418c895`
(10 units → 3) and `84c75985a0` (9 → 3) — and both were wholly silent in the recorded run.

## A correction to D-166

D-166 read the drawer's **167 `no-reproduction-bought`** as *"never ranked high enough to buy a
reproduction"*. That is not what happened. Of the 331 candidates:

| class | count | bought a reproduction attempt |
|---|---|---|
| `regression` | **168** | **168 — all of them** |
| `new_code` | 128 | 0, by construction (the gate level's population) |
| `non_python` | 35 | 0, by construction |

Every regression-eligible candidate reached a reproduction. The 167 are the **ineligible** ones,
which have no verification reason to record and therefore fall into the empty-reason class. So
the sentence to keep from D-166 is not *"the ranking never reached them"* — it is that **a larger
budget buys more candidates that can never be certified**. That is what the 30% share stops.

## The cliff, named now

The 30% ceiling is checked against the **preflight reservation**, which prices K samples at the
3,200-token output bound. Across the 17 commits that bound reserved **$3.1538** where discovery
actually spent **$1.0671** — the estimate overstates a real proposal by **3.0×**, so the ceiling
bites about three times harder than "30% of the budget" sounds.

At **K=4** (both recorded runs) no review of the 28 is refused its first unit. At **K=5** — the
shipped default — exactly one is:

| review | first unit | K=4 reservation | K=5 reservation | ceiling at $1.00 |
|---|---|---|---|---|
| `click cd4674a6` (`0c37806d`) | 47,448 chars | $0.2545 | **$0.3182** | $0.30 |

That review is one of the three that published a receipt. It would defer with a stated budget
reason — a contract line, not a silence — but it would publish nothing. **`k_samples = 4` or
`budget_usd >= 1.06` removes the cliff**; which one is the owner's call, and it is item 1 of this
window's owner list.

## What the cap does not change

The publication family. `m` is still every regression-eligible candidate of the change unit, so
the cap cannot make anything publish that would not have published before. It decides what is
bought, never what may speak.
