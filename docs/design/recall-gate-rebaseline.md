# Proposal: `G-RECALL-002` is measured on the wrong corpus

**Status: proposal. Nothing here is applied.** The gate's bar stays at **>=70%** and its
population stays the 39 restored SWE-bench Verified instances until an owner decision says
otherwise. This document argues that the bar and the corpus cannot both stand, and proposes
which one to move.

## 1. The gate as it stands

`G-RECALL-002` asks for **>=70% crash-class recall** on the held-out slice of SWE-bench
Verified. Four measurements:

| run | crash-class recall | Wilson 95% |
|---|---|---|
| 2026-09-12 (D-191 rebuild) | 2 of 28 — 7.1% | [2.0%, 22.6%] |
| 2026-09-10 (D-211, D-206 on) | 2 of 31 — 6.5% | [1.8%, 20.7%] |

The **upper** end of the interval has never reached 23%. For 70% to be inside a 95% interval
at n = 31 the point estimate would have to be at least about 17 of 31. The gate is not near;
it is a different order of magnitude, and four windows of work have moved the numerator by
zero.

## 2. Why the corpus cannot pay it, structurally

Three measurements, each free and each already taken, say the ceiling is not about the
adjudicators:

1. **25 of 39 cases have no test call site at all** for anything their diff changed
   (D-212, `2026-09-10-probe-reach.md` §2). Before any rule about literals or receivers,
   two thirds of the corpus offers nothing to derive a probe from.
2. **The corpus is reversed by construction.** A SWE-bench instance's "head" is the buggy
   parent and its "base" is the gold-patched tree, so the differential the product certifies
   is head-fails/base-passes on a pair assembled backwards. Two of the 39 land in clause (c)
   as *reversed-corpus artefacts* and are not defects the product got wrong.
3. **A gold patch is usually not a crash.** 8 of the 39 are value-class and are excluded from
   the denominator by D-158 rather than scored, because a differential receipt about a changed
   *value* is exactly what the intent clause is built to refuse.

None of these is a defect in the product. They are properties of the population.

## 3. What a differential receipt actually needs

The product certifies when, and only when:

- a probe reaches the changed code on the merge base and records a stable observation;
- head produces a different observation, deterministically, 3 of 3 on each side;
- the changed lines are executed on every failing head run (V-02);
- and the intent clause finds the base tree specifies what moved (D-102, D-127, D-132, D-174).

Every one of those is a property of **the pair**, and three of the four are properties the
corpus does not supply for most of its instances. A recall bar over a population that does
not supply them measures the population, not the reviewer.

## 4. The proposal

**Keep a recall gate. Move its population to one where a receipt is possible in principle,
and state the bar over that.**

| | today | proposed |
|---|---|---|
| population | 39 SWE-bench Verified held-out instances, reversed | (a) **forward pairs** — a repository's own `fix:` commit and its parent, head = the buggy commit; plus (b) **mutation injection** — a mechanically introduced crash on a line the tree's own tests reach |
| denominator | crash class after D-158 exclusion | every unit where a defect exists **and** the tree's own tests reach the changed definition |
| bar | >=70% | to be set from the first measurement of the new population, not carried over |
| what it measures | detection on a corpus assembled backwards | detection where the evidence the product requires can exist |

**Why forward pairs.** The 2026-09-05d window measured **3 published of 11** forward pairs at
K = 4 ([report](../acceptance/2026-09-05-forward-pair-reviews.md)) — four times the held-out
rate on a population one quarter the size, and the direction is the one the product ships into. They are also the only pairs where "what did the code do
before?" has an answer the merge base can be executed for.

**Why mutation injection alongside.** A forward-pair corpus is small and its defects are
whatever the repository happened to fix. A mutation corpus supplies an arbitrary number of
units, each with a known ground truth and each **guaranteed reachable**: the mutation is placed
on a line an existing test executes, so failure to certify is always the product's and never
the corpus's. That is what makes a >=X% bar meaningful rather than aspirational.

**What is lost.** SWE-bench Verified is public, external and not chosen by this project, and
that is worth something no self-built corpus has. The proposal does not delete it: it is kept
as a **reported observation** with its two denominators, exactly as D-211 reports it now, and
stops being the thing a release gate turns on.

## 5. What would have to be true before this is applied

1. A frozen protocol for the new population, written and digested **before** any unit runs —
   the discipline E-04's strata already use.
2. A **control arm** in the same run. Every recall number this project has taken on the
   held-out corpus has `control: null`, so none of them says anything about false
   publications; a rebaselined gate must not inherit that.
3. The bar set from the first measurement's interval, and stated as an interval.
4. `G-RECALL-002`'s current figure carried into the new document as the historical row, so
   the change of population is legible rather than a reset.

## 6. What this document does not do

It does not lower the gate. It does not change the population. It does not touch alpha, the
likelihood ratios, K, the publication cap or the support range. It is the argument the owner
asked to have written down, and applying any of it is an `AGENTS.md` §16 decision.
