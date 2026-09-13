# The A/B/C probe arms, 2026-09-14 — prepared, not dispatched

**D-246 step 5, the owner instruction of 2026-09-14.** Three dispatches of `mutation-recall.yml`
over the same forty trials, **$1.00 per case, K=5, `linux-container-v1`, the local review path,
read-only clones, nothing written anywhere**, each admitted at the D-244 p95 reservation and
capped by the driver at $5.00 (reservation $15.00 in all, [DEVSPEND](../../DEVSPEND.md), window
2026-09-14). **Only the probe's one call differs** between the arms -- `generate_probe`'s
provider, model and output bound (`ProbeCall`) -- and the proposals and the reproduction generator
are the shipped ones in all three. **Nothing below has run.** The tables are filled by
`scripts/acceptance/probe_arms_report.py` from the three artifacts; the reading is written after.

## The arms

| arm | `arm` input | trials file | the probe's call |
|---|---|---|---|
| **A** | `A` | `trials-arm-A.jsonl` | the shipped call: the generation model, thinking disabled, the probe's own output bound -- the same call as the 11 of 40 (D-245) and 12 of 40 (D-240) runs, so a third run of it is the jitter control the other two are read against |
| **B** | `B` | `trials-arm-B.jsonl` | the generation model, thinking adaptive at effort medium, 8,000 output tokens |
| **C** | `C` | `trials-arm-C.jsonl` | the proposal model, thinking adaptive at effort medium, 8,000 output tokens |

Every trial row carries `probe_call` (the arm, its model, thinking, effort and output bound), so an
arm is legible from its own file; the ledgers' `review_run.spend_breakdown` (D-243) carries the
probe stage's cost and model per case; `elapsed_s` is the case's wall clock.

## The default rule, pre-registered before the first call

1. The default probe call is the arm with the best **cost per certified case**.
2. A dearer arm becomes the default only if it certifies **at least three more cases** than the
   cheaper one **and** each gained case's mechanism can be named from its ledger -- the probe it
   chose, what the merge base recorded, the reason the receipt was accepted -- by a person, case
   by case.
3. An arm whose **median per-case wall clock is more than twice A's** is not the default,
   whatever it certifies.
4. AGENTS.md §9: one re-run of the forty moves about ±2 cases on its own; a difference of two
   cases or fewer decides nothing.
5. A case the cap or the budget refused is a miss for that arm and is named; the denominator is
   forty for every arm.

## 1. The three arms side by side

*(filled by the script: cases run, certified of 40 with its Wilson interval, the boundary
thirteen's certified, spend, the probe stage's spend, cost per certified case, median wall clock,
cases refused by the cap.)*

## 2. Gained and lost against A, case by case

*(filled by the script; then, for every case an arm gains against A, the person reading the
ledgers writes one line: the certifying probe, what the merge base recorded, why the receipt was
accepted -- or "the mechanism cannot be named", which fails rule 2.)*

## 3. The rule applied

*(the script's verdict lines, then the reading: which arm the rule names as the default, or that
it names none.)*

## 4. What is and is not claimed

- Retrieval is the same in all three arms (D-246's repaired index); what differs is how the probe
  is asked for. A gain here is a gain of the search, not of the context.
- Not natural traffic; the forty are planted mutations, and the boundary thirteen are their own
  column because D-245 expected the most movement there and saw none.
- The p95 reservation admits each arm's cases from the study's whole history, which is the
  shipped call's; a dearer arm may overshoot its $5.00 cap by at most one case's distance between
  the p95 and the $1.00 ceiling (D-244).
