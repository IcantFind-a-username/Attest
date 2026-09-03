# `G-NULL-001`, amended: what an evidence-based control costs, and why the current population is zero

**Nothing here was run against a model. No paid call was made for this paper.** It records
the owner's 2026-09-04 decision — option C, plus an amended control definition and an
affordable sample size — prices it against the measured unit cost, and reports one measurement
that changes the answer: **under the new definition, this account owns no controls at all.**

The normative text is in [`evolution-gates.md`](evolution-gates.md) (`G-NULL-001` amendment
and the new, weaker `G-NULL-001a`). This paper is the pricing and the evidence behind it.

## 1. The new control definition

A commit qualifies as a control when **both** hold, checked positively before any paid call:

1. **age** — its committer date is at least six months before the measurement date;
2. **untouched** — no later commit on the default branch touches a line it added. For every
   file it modified, every line it added must still be present at the branch tip and still
   blamed to it.

Any later commit disqualifies, fix or not. Deciding "was that a fix?" is the subjective
judgement this definition exists to remove, and the conservative reading only ever drops
controls. Implemented in
[`scripts/corpus/qualify_controls.py`](../../scripts/corpus/qualify_controls.py); it makes no
model call and reads only git.

**Why this replaces the old rule.** The 2026-09-03 corpus picked controls by commit subject.
`c05` was a `docs:` commit that also added an unguarded `json.loads(...)` and published a true
defect; `c03` was a planted drill commit swept in by a subject filter. A stratum defined by
what a commit is *about* carries no evidence about whether it is *correct*, so it cannot
support a false-publication rate — and neither could `G-NULL-001` built the same way.

## 2. The measurement that decides the price: 0 of 25

Requalifying the corpus's own controls, as of 2026-09-04, against each clone's own tip:

| check | result |
|---|---|
| **both checks (a control under the new rule)** | **0 of 25** |
| age ≥ 6 months | **0 of 25** — oldest control commit is 41 days |
| no later commit touched its added lines | 9 of 25 pass, 5 fail, 11 undefined (unmerged branch, or newer than the clone) |

The age check is not close, and it is not a property of the sample:

| repository | commits | first commit | age of history |
|---|---|---|---|
| `Attest` | 271 | 2026-08-29 | **6 days** |
| `Corum` | 23 | 2026-08-28 | **7 days** |
| `us-stock-helper` | 265 | 2026-07-24 | **6 weeks** |

**Every repository this account owns is younger than the control definition requires.** The
amended `G-NULL-001` population therefore cannot contain a single commit from the owner's own
repositories — not today, and not until 2027-01 at the earliest for `us-stock-helper`. The
whole of any run must come from the public clones the owner authorised on 2026-09-04.

## 3. The price, and the floor the price cannot move

Unit price from the 43 measured reviews: **$0.2177** per review, bounds $0.1397 (control) and
$0.3427 (refactor control). With zero observed errors the 95% upper bound on the per-review
wrong-publication rate is `1 - 0.05^(1/n)`.

| n reviews | 95% upper bound | at $0.1397 | **at $0.2177** | at $0.3427 | reachable under a $45 cap? |
|---|---|---|---|---|---|
| 60 | 4.87% | $8.38 | **$13.06** | $20.56 | yes |
| 100 | 2.95% | $13.97 | **$21.77** | $34.27 | yes, with a raise |
| 150 | 1.98% | $20.95 | **$32.66** | $51.41 | only with a raise |
| 200 | 1.49% | $27.94 | **$43.54** | $68.54 | no |
| 300 | **0.99%** | $41.91 | **$65.31** | $102.81 | no |
| 381 (as written) | 0.78% | $53.23 | **$82.94** | $130.57 | no |

**No amendment to the control definition moves the ≤1% bound.** It needs n ≥ 300 whatever a
review costs, and 300 reviews cost more than the whole approved cap. That is why the amended
gate is published as a *different* gate, `G-NULL-001a`, whose permitted claim always carries
its own n and bound. Passing it is never a pass of `G-NULL-001`.

**Recommended shape, if the owner wants a number this quarter:** n = 100 at $21.77 (range
$13.97–$34.27), giving a 95% upper bound of **2.95%**. It is affordable next to option C's
E-04 (~$21.77) under a cap around $55, and it is honest about being three times the release
bound.

## 4. What the population now has to be, and what it costs to assemble

Public repositories with at least six months of history, cloned read-only into
`.attest/corpora/<name>/` at a recorded commit (AGENTS.md §7), never written to (§8).

| item | cost |
|---|---|
| qualifying candidate commits (`qualify_controls.py`) | **$0.00** — git only; wall time roughly linear in commits × files |
| cloning and pinning ~10–30 repositories | $0.00, disk and bandwidth |
| the n reviews themselves | the table in §3 |
| product-blind adjudication of every author-visible finding | **not API spend** — the hidden cost, and the reason a wrong publication must stop the run |

**The repository-count blocker is gone** (public clones supply ≥30 clusters); the sample-size
floor and the adjudication labour are not.

## 5. The bias this definition introduces, stated rather than rounded off

A line untouched for six months is a line nobody had to fix **and** a line nobody exercises.
The population is therefore biased toward **cold code**, and a product that is silent on cold
code will look safer than it is. The bias is not estimated by this design.

Every run under the amendment must report the **mean eligible candidates per control** beside
the 2026-09-03 baseline of **2.9 per review**. A population that produces far fewer eligible
candidates per review is a population the product barely looked at, and its null rate should be
read as an upper-bound artefact rather than a safety result.

## 6. What was deliberately not done

- **No run.** The owner's instruction was to write the amendment and the pricing.
- **No driver.** `scripts/corpus/real_traffic.py` still reads the old frozen plan; wiring the
  qualifier into a population builder is the next step and is unpriced here.
- **`G-NULL-001` itself is untouched as a pass condition.** It stays in the document, unpassed,
  so that no future report can quote `G-NULL-001a`'s number under its name.
