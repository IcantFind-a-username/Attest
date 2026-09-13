# The next experiment: the same forty, old context against new (prepared, not run)

**Prepared under D-247 on 2026-09-14; the switch and the reservation exist and nothing has been
dispatched.** The owner raised the cumulative cap to **$160** on 2026-09-14, and **$10.00** is
reserved for the two arms in `DEVSPEND.md`; the dispatch itself waits on the owner's word, as
every paid run does. The question it answers is the only one D-247 leaves open: **does the
repaired evidence chain change any verdict?**

## The comparison

One frozen population, one model, one budget, one set of rules; the **only** difference is the
first probe's context.

| | arm OLD | arm NEW |
|---|---|---|
| first-probe hint | conditions + asserted values + literal list (the code before D-247) | the same, plus the routes block and the merge-base specification (D-247) |
| everything else | `claude-opus-5`, thinking disabled, K=5, `$1.00` per case, `linux-container-v1`, the shipped certification, intent and publication rules, no outcome-aware retry | identical |
| population | `benchmarks/studies/mutations-v1-recall`, the same forty, rebuilt from the frozen sample, not re-drawn | identical |
| trials file | `trials-context-old.jsonl` | `trials-context-new.jsonl` |

**How the old arm is obtained.** Not by deleting code and not by checking out an older commit:
`ProbeCall(include_routes=False)` asks for the hint as it stood before D-247, so both arms run one
build and differ in one field. The driver takes `--context new|old` (the workflow input `context`),
writes `trials-context-<context>.jsonl`, and records `context` and `include_routes` in **every**
trial row, so an arm is legible from its own file. One caveat on the record, checked rather than
assumed: the old arm is not byte-identical to pre-D-247. Compared case by case on the forty rebuilt
trees, the two hints differ on 39 of 40 **only** in `_asserted_block`'s revision label (*the
repository's own tests* → *the head revision's own tests*); the fortieth produces no hint in either;
and the `literals_hint` the ledger records is identical on 40 of 40.

    python scripts/corpus/mutation_recall.py run --allow-paid-api --context old --reserve 5.00
    python scripts/corpus/mutation_recall.py run --allow-paid-api --context new --reserve 5.00

## What is recorded, per case

Certified or not, and its class; the routes the hint offered and whether the certifying probe
entered through one of them (the ledger's `probe_observation` row already carries the probe's
imports, setup and expression, and D-246's `literals_hint`); whether a merge-base specification
was quoted and whether the receipt cites it; spend; wall clock; the probe stage's own spend from
`review_run.spend_breakdown`; and every case the cap refused, by name.

## What may be concluded, and what may not

- The denominator is forty in both arms; a case a cap refuses is a miss, named.
- **AGENTS.md §9 binds**: one re-run of this corpus moves about ±2 cases on its own. A difference
  of two or fewer decides nothing, and a difference is attributed only case by case, by naming the
  route the certifying probe took.
- The control that makes the comparison readable is the **same-configuration re-run**: arm OLD is
  itself a re-run of a call that has now scored 12, 12 and 11 on this corpus, so its own spread is
  the yardstick the NEW arm is read against. Without that control the experiment cannot separate
  the context from the search.
- This corpus is planted mutations, not natural traffic. A gain here is not a claim about real
  pull requests; the three real-PR batches are the population for that, and they are unmeasured
  under D-246 and D-247 alike.

## Cost, to be reserved before any call

Three arms' worth of history says a forty-case pass costs **$2.0 to $3.0** at $1.00 per case with
the D-244 p95 reservation admitting each case (A $2.71, B $3.02, C $1.99 on 2026-09-14). Two arms
is **$4 to $6**; **$5.00 per arm, $10.00 in all, is reserved** in `DEVSPEND.md` (window 2026-09-14b),
which is also the mutation study's own `cost_cap_usd` per dispatch. Settled after each arm, before
the next is dispatched, as the three probe arms were.
