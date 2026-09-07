# The crash-class held-out sample, re-measured after the D-185 repair — 2026-09-11

**Owner instruction 2 of this window**, following owner item 1 of the
[2026-09-10 handoff](../overnight-handoff-2026-09-10.md), answered *yes, and narrowly*. D-185
said the held-out crash-class recall could not be re-taken. This report is the re-take, at the
factory configuration, on the code that repairs it (**D-186**).

**The one sentence.** The repair works exactly as designed — **17 of 17** `no JUnit artifact`
verdicts became a stated refusal and **no other verdict moved because of it** — and what the
honest number then says is worse than *4 of 16*: **9 of the 16 cases are outside what this
product can review at all**, so the crash-class denominator is **7**, the numerator is **2**,
and **2 of the 4 receipts `G-RECALL-002`'s number was built on came from a project Attest can no
longer run.**

## 1. What is held fixed, and what is not

The population is **not re-sampled**: the same 16 crash/exception cases D-158 makes the held-out
denominator, the same ids, the same plan file, the same clones. Factory configuration —
`--budget 1.00` and the shipped `samples` (5, D-183) — containers, **local review only: no
GitHub client is constructed, so no publication surface exists**.

| column | when | code | K |
|---|---|---|---|
| `.probe` | 2026-09-06 | `attest.intent.v4.1`, before D-168 | 4 |
| `.k5` | 2026-09-10 | `attest.intent.v4.2`, D-174–D-180 | 5 |
| **`.d186`** | **2026-09-11** | **the same, plus D-186 and D-189** | **5** |

`.probe` is the column `G-RECALL-002`'s **4 of 16** comes from.

Two things about this run that a reader has to know before reading any number from it:

1. **Discovery was not re-bought. All 80 proposal samples — 5 per case, 16 cases — were
   replayed from the immutable attempt cache**, so the candidate sets are *byte-identical* to
   the `.k5` column rather than merely similar, and every dollar of the $1.4297 went to
   generation, which is not cached. That is the cleanest comparison available for a change that
   lives entirely on the verification path: discovery is held fixed by construction, not by
   assumption.
2. **`--code` is pinned to `7a506db` for 15 cases and to `1fd5563` for the sixteenth.** The
   difference between them is D-189, a ledger *reader* change that decides whether a review can
   start — see §4. It cannot change a verdict, and the sixteenth case's verdict is discussed as
   what it is: a second draw of generation, not a consequence of either fix.

## 2. What D-186 did, counted

| | `.k5` | **`.d186`** |
|---|---|---|
| verdicts reading `missing or malformed JUnit evidence: ValueError: no JUnit artifact` | **17** | **0** |
| verdicts reading `reproduction interpreter outside the project's declared range` | 0 | **17** |
| any other verdict changed by the repair | — | **0** |

The 17 are exactly the 17 D-185 named, across the same 7 `pytest-dev__pytest` cases
(`5787`, `5840`, `6197`, `7205`, `7324`, `7490`, `7571`), candidate for candidate. The full
before/after list is in the [evidence](evidence/2026-09-11-heldout-after-d186.json).

What an operator now reads, end to end, out of a real review of `pytest-dev__pytest-7324`:

```
DEFER: verification deferred: probe deferred on base: reproduction interpreter outside the
project's declared range: pytest collected no test under python 3.12, and this project
declares a range outside 3.10-3.13 (missing or malformed JUnit evidence: ValueError: no
JUnit artifact) (2 candidates)
```

Cause first, evidence after it in brackets. **The conjunction held on real traffic in both
directions**: `pylint-dev__pylint-4661` fails collection too — `pytest collection/import/syntax
or infrastructure failure (exit code 2)` — and declares 3.10, so it keeps its ordinary DEFER and
is not refused. That is the case the second condition exists for.

## 3. The recall number, and the denominator it is honestly over

| | `.probe` (K=4) | `.k5` (K=5) | **`.d186`** |
|---|---|---|---|
| certified | **4 of 16** | 1 of 16 | **2 of 16** |
| refused: outside the interpreter range | 0 | 0 (reported as a missing artifact) | **7** |
| refused: image will not build | 0 | 2 | **2** |
| reviewed and no receipt | 11 | 6 | **5** |
| reported as a broken host | 1 | 7 | **0** |
| candidates | 44 | 48 | 48 |
| spend | $1.8347 | $1.6840 | **$1.4297** |

Per case:

| case | `.probe` K=4 | `.k5` K=5 | **`.d186`** |
|---|---|---|---|
| `psf__requests-1724` | reviewed, no receipt | refused: bootstrap | **refused: bootstrap** |
| `psf__requests-2317` | reported as a broken host | refused: bootstrap | **refused: bootstrap** |
| `psf__requests-5414` | **certified** | **certified** | **certified** |
| `psf__requests-6028` | reviewed, no receipt | reviewed, no receipt | reviewed, no receipt |
| `pylint-dev__pylint-4661` | reviewed, no receipt | reviewed, no receipt | reviewed, no receipt |
| `pylint-dev__pylint-6528` | reviewed, no receipt | reviewed, no receipt | reviewed, no receipt |
| `pylint-dev__pylint-6903` | reviewed, no receipt | reviewed, no receipt | reviewed, no receipt |
| `pytest-dev__pytest-10051` | **certified** | reviewed, no receipt | reviewed, no receipt |
| `pytest-dev__pytest-10356` | reviewed, no receipt | reviewed, no receipt | **certified** |
| `pytest-dev__pytest-5787` | reviewed, no receipt | broken host | **refused: interpreter** |
| `pytest-dev__pytest-5840` | reviewed, no receipt | broken host | **refused: interpreter** |
| `pytest-dev__pytest-6197` | **certified** | broken host | **refused: interpreter** |
| `pytest-dev__pytest-7205` | reviewed, no receipt | broken host | **refused: interpreter** |
| `pytest-dev__pytest-7324` | **certified** | broken host | **refused: interpreter** |
| `pytest-dev__pytest-7490` | reviewed, no receipt | broken host | **refused: interpreter** |
| `pytest-dev__pytest-7571` | reviewed, no receipt | broken host | **refused: interpreter** |

### The four candidate-level changes, each with its id

- **`pytest-dev__pytest-6197` `16694a06e5`** — K=4 `reproduced`; now **refused**: the project is
  outside the interpreter range. *A receipt lost to D-162, and the loss is now named.*
- **`pytest-dev__pytest-7324` `78e76aebd9`** — K=4 `reproduced`; now **refused**, same cause.
  *The second lost receipt.*
- **`pytest-dev__pytest-10051` `1af71a4893`** — K=4 `reproduced`; at `.k5` and `.d186`
  drawered by `attest.intent.v4.2` (*"the base tree does not specify the value this assertion
  pins about the symbol this change touched"*). **This is D-174, measured on 2026-09-10 and
  unchanged here** — not this window.
- **`pytest-dev__pytest-10356` `e9223c7815`** — `deferred` on intent at `.probe` and `.k5`,
  **`reproduced` here** (head FAIL 3/3, base PASS 3/3). **This is not either fix.** Discovery
  was replayed byte-identically, so the candidate is the same one; what differs is the
  *generated probe*, which is bought fresh every run. It is one draw of generation variance on
  a case that had never been drawn twice at K=5, and it is reported as that rather than as a
  gain.

`psf__requests-5414` `520c57974d` certifies in every column that could run it.

### So can `G-RECALL-002` have a number again?

**Yes, and it is a smaller number over a smaller denominator, which is the point.**

- The blocker D-185 named is **gone**: the sample runs, every case reaches a verdict or a stated
  refusal, and nothing is silently unreviewable.
- The honest denominator is **not 16**. Nine of the sixteen are refused before any evidence
  exists — 7 outside the supported interpreter range, 2 whose image will not build — and a
  refusal is neither a miss nor a detection. **Eligible-and-supported: 7. Certified: 2.**
- **The comparison with *4 of 16* is not like-for-like and must not be quoted as a regression
  from 25% to 12.5%.** Two of those four (`6197`, `7324`) are `pytest` cases that were reviewed
  on 2026-09-06 under Python 3.9 and cannot be reviewed at all today. `G-RECALL-002`'s recorded
  number was, in part, bought on a configuration the product no longer ships.
- The gate still **fails** — it asks for ≥70% point detection and a ≥50% clustered lower bound,
  and 2 of 7 is 29% on a sample far too small to carry an interval worth printing. What changed
  is that it fails for a reason the report can state, over a population it can name.

**The measurement this corpus can no longer take is the one it was built for.** Half of its
`pytest` half is out of range, and the honest repair is a corpus decision, not a code one: see
the owner item in the handoff.

## 4. The defect the run found — D-189, fixed here

`pytest-dev__pytest-10356` could not be reviewed at all. `run_review` raised, **before buying
anything**:

```
ValueError: delivery member does not match its ci_final surface decision
```

The cause is in the ledger the **previous** review of that case wrote, on 2026-09-10: it posted
one yellow (a) note and no receipt, and journalled the note as a delivery member —
`{"finding_id": "src/_pytest/mark/structures.py:358", "placement": "impact"}`. `ci_final`
records **candidate** decisions and knows nothing about a coordinate, so the reconciliation
refused the row on the next read. **D-180's family again: the product wrote a row it will refuse
to read.**

The repair reconciles a delivery member only when its placement is one `ci_final` can produce
(`inline`, `overflow`); a note placement is skipped and anything else fails closed. The
load-bearing half is that a note is **excluded** from the surfaced projection rather than
admitted to it — that projection is the precision window the alpha auto-tighten reads (D-048),
and a `file:line` coordinate must never enter it. The old code could not make that mistake
because it raised first: the guard was right and the writer was wrong.

**Blast radius, at its real width.** On the GitHub Action the ledger does not survive a fresh
checkout, so no shipped review has ever hit this. It bites wherever a ledger persists across
reviews of one worktree — every corpus driver, every local dogfood loop. Nothing published is
impeached: the failure is a refusal to start, never a wrong claim, and no recorded measurement
changes, because the check has always raised on such a ledger rather than counting a coordinate
as surfaced. On the real `pytest-10356` ledger the projection now returns the two genuine inline
receipts of 2026-09-03 and not the coordinate.

## 5. Cost, and the stop rule

| | |
|---|---|
| reserved | **$5.00** |
| spent | **$1.4297** (16 reviews) |
| released | **$3.5703** |
| largest single review | **$0.1939** (`pytest-dev__pytest-7571`) |
| proposal calls bought | **0** — all 80 samples replayed from the attempt cache |

The owner's stop rule — *stop immediately if the run passes $5.00* — was never approached. The
predicted rate ("about $2") was right: $1.4297 against $1.6840 for the same 16 cases the day
before, the difference being the cached discovery.

## 6. Release readiness, re-read against the four `FAIL`s

The 2026-09-10 report left four. Where each stands after this window:

| # | 2026-09-10 | **now** | what is still missing |
|---|---|---|---|
| 1 | **The held-out crash-class recall cannot be re-taken (D-185)** | **the blocker is closed; the gate still fails** | the sample runs and every case reaches a verdict or a stated refusal. What replaces the blocker is a *corpus* problem: 9 of 16 cases are outside what the product supports, so the denominator is 7 and `G-RECALL-002` needs a **larger eligible population** — cases whose projects run on 3.10+ — before its ≥70% can be tested at all |
| 2 | **The factory K costs a receipt, and nothing says so to an operator** | **the second half is closed (D-187); the first half stands** | the product now names the trade when the discovery ceiling actually bites — which unit, how much short, and the `budget-usd` that would have covered it. `budget-usd` $1.00 and `samples` 5 are unchanged by owner decision, so `click cd4674a6de` is still lost; what is gone is the silence about it |
| 3 | **No outside repository has ever received a receipt-backed comment** | **unmoved** | the owner names a repository (≈$1 a pull request). Nothing in this report substitutes for it |
| 4 | **Control noise at K=5 is unmeasured** | **unmoved** | the three free levels are K-independent by construction; for red it is 126 controls, ≈$126 at the cap |

The five unpassed gates of 2026-09-10 are unchanged in count. `G-RECALL-002` keeps its own row
and its blocker has changed shape: it was *"the corpus cannot be re-measured"* and it is now
*"the corpus is too small once the unsupported cases are removed"*.

## Gates for this window's own changes

```
python -m pytest --cov=src/attest --cov-report=term-missing
python -m ruff check .
python -m mypy src/attest
git diff --check
```

Recorded in the handoff, at the final commit of the branch.

Baseline `d361198` → `fix/d-185-collect-refusal`. **No constant moved**: `alpha`, the likelihood
ratios, `k_samples`, the hard cap, `budget-usd` and the supported interpreter range 3.10–3.13
are all untouched.
