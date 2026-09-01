# Choosing a population on which F's discrimination can actually be measured

Date: 2026-09-01 · baseline `9abb0ac` · dated evidence report, not a roadmap.

Wave 5 (D-064) redefined F as graded change heat and measured it once. The measurement
did not fail because the signal was badly defined; it failed because the **measurement
population** carried no comparable distribution at the unit the product emits. The control
arm produced 1 candidate against 25. This document selects a different population and
records the reason **before** the measurement runs, as `AGENTS.md` §16 requires.

Scope limits fixed in advance: the F signal definition is D-064's four raw fields and does
not change here; F stays unpriced; no factory constant, alpha, channel cap, coverage
threshold or gate threshold is touched.

## 1. What the existing run record says about when the product emits candidates

The question is: on what input does the product produce candidates that do **not** contain
a known defect? The record answers it more sharply than expected, because the wave-5 design
happens to hold every diff property constant except one.

The 18 wave-5 cases are 9 pairs, each run twice. `developer_fix_control` reviews head =
fixed commit against base = buggy commit; `historical_bug_replay` reviews head = buggy
commit against base = fixed commit. The two arms of a pair are the **same diff in opposite
directions**, so the manifest's `changed_locations` are byte-identical between them.

| pair | file | old-side hunks (lines) | new-side hunks (lines) | control candidates | replay candidates |
|---|---|---|---|---|---|
| pair-169429c32175 | `black.py` | 7 (8) | 7 (17) | 0 | 7 |
| pair-53f336eb966b | `black.py` | 1 (1) | 1 (1) | 0 | 2 |
| pair-662a533eb0f0 | `black.py` | 3 (9) | 3 (40) | 1 | 2 |
| pair-8419788e183e | `black.py` | 1 (1) | 2 (14) | 0 | 2 |
| pair-acc00ce9f068 | `black.py` | 1 (1) | 2 (4) | 0 | 3 |
| pair-d4c758e1cde3 | `black.py` | 7 (9) | 9 (44) | 0 | 0 |
| pair-dee2edc00ad8 | `black.py` | 2 (4) | 2 (11) | 0 | 4 |
| pair-e61fb0c608f2 | `blib2to3/pgen2/tokenize.py` | 2 (3) | 2 (4) | 0 | 1 |
| pair-e6fd59112ec9 | `black.py` | 2 (2) | 2 (2) | 0 | 4 |
| **total** | | | | **1** | **25** |

Read the table by rows. Diff size does not predict yield: the largest labelled diff
(pair-d4c758e1cde3) yields 0 in both directions, and a 1-line diff (pair-53f336eb966b)
yields 2 in the replay direction. File type does not predict it — 8 of 9 pairs touch the
same file. Hunk count does not predict it. The only property that separates a 0 from a 7 in
this table is **which direction the diff runs**, and direction is exactly what the columns
differ by while everything else is held identical.

The same asymmetry appears in the older dogfood record. The per-candidate records for those
runs were written into throwaway checkouts and are gone; `DEVSPEND.md` is the surviving
account, and it is consistent:

- a real third-party project, **617 added lines → 0 candidates** ($0.2352);
- a semantics-preserving refactor as negative control, K = 5 → **0 candidates**;
- against which real reviews that did emit: pygments K = 5 surfaced the `RawTokenFormatter`
  crash, corum K = 5 produced one drawer candidate later refuted by verification, the
  new-code discriminator check produced 1, and the differential-V regression review
  produced 2.

**Answer to the question, stated as the record supports it.** Candidate yield tracks
whether the change *removes or narrows* an existing behavior, not how large it is or what
it touches. Every recorded input that produced candidates with no known defect is either a
reverted-fix head where the candidate did not land on the labelled region, or a real
third-party review that produced a drawer candidate. Every recorded pure-addition or
semantics-preserving input produced zero. Wave 5's control arm was empty for this reason and
not by accident: applying a fix is an addition-shaped change. Any population built out of
"clean commits" inherits that emptiness.

One further fact from the same record, which constrains wave 3 before it starts: across all
26 candidates the T channel bought nothing — `T = 1.0` on every row — and `S` took only the
values 2.0, 2.639, 2.9485 and 3.0. **Observed `S·T` therefore tops out at 3.0**, against
D-063's *reachable* ceiling of 9.

## 2. The candidate populations, evaluated

### P1 — recent PRs from real open-source repositories

- *Zero-cost acquisition?* No. Cloning is free and the network is reachable, but a candidate
  only exists after a paid proposer call. At the wave-5 rate ($0.036–$0.161 per case, mean
  $0.088) a 9-case run costs roughly $0.8, and a run large enough to yield ~25 candidates is
  at or over the $1.00 cap for this task.
- *Expected yield?* Unbounded uncertainty. The single real-world data point in the record —
  617 added lines, 0 candidates — is the same failure mode wave 5 hit.
- *Truth available?* **None.** "This PR contains no defect" would be an assertion about
  unreviewed third-party code. `INV-TRUTH-001` forbids exactly this: product-dependent
  review cannot establish correctness, and neither can the absence of a bug report.

### P2 — the corpus project's own non-defect commits (refactors, docs, dependency bumps)

- *Zero-cost acquisition?* For the input, yes: the `black` checkouts in the corpus cache
  carry full history offline (393 commits reachable from the pair-169429c32175 head). For
  candidates, no — same paid proposer call, same ~$0.8 for 9 cases.
- *Expected yield?* Docs and dependency bumps are pure additions and are the exact shape
  that produced 0 in every record. Only deletion-shaped refactors would yield candidates.
- *Truth available?* Weak, and confounded. Selecting refactors "that were never later
  fixed" is a filter keyed on repair-worded commit history — the same vocabulary F's
  `repair_share` field reads. F's window looks backward from the reviewed revision and the
  filter looks forward, so it is not a direct circularity, but it is a selection effect on
  the same variable that I could declare and could not bound.

### P3 — the 26 candidates already on record, split by whether the anchor lands on the corpus's labelled defect region

- *Zero-cost acquisition?* **Yes, completely.** Every input is committed: the 26 rows with
  `finding_id`, `file`, `line` and all four F raw values in the D-064 artifact; the
  manifest's `changed_locations`; and D-062's matcher with its pre-registered
  `DEFAULT_LINE_SLACK = 3`, its slack sweep, and its unlabelled-hunk rule. No model call, no
  execution, no new generation.
- *Expected yield?* 26 candidates, split into two non-empty groups. D-062 published the
  match rate on D-059's four surfaced findings as 2/4 at slack 3 (3/4 once D-061 corrected
  one receipt), so both a matching and a non-matching group will exist and the non-matching
  group will be the larger.
- *Truth available?* The corpus's own head-side labelled span — the only product-blind
  label this project holds — plus a claim-by-claim manual read.

## 3. Selection: P3, and why

1. **It is the only one of the three with a product-blind label.** P1 has no label. P2's
   label is "nobody fixed it afterwards", which is an absence of evidence and is keyed on
   the same repair vocabulary F reads. P3's label is the corpus patch, fixed before this
   project existed and never shown to the product.
2. **It is the only one that places both groups inside the same reviewed revision.** This is
   the decisive reason. If F were priced it would multiply *this* candidate's wealth against
   *that* candidate's on the *same* head — the decision F would change is a within-revision
   one. P1 and P2 can only produce a between-repository or between-revision contrast, which
   is not the comparison the pricing question asks.
3. **It turns D-064's stated confound into a control.** D-064 warned that a BugsInPy head
   sits at the bug-introducing commit, so the defect region was necessarily touched recently
   in that head's own history — which inflates the defect side of a *between-arm*
   comparison. Within one head both groups share the revision and the reference date, so
   that inflation applies to the arm as a whole. It does not disappear (the labelled span is
   itself the recently-touched span) but it is narrowed from "the whole defect arm" to "the
   labelled lines", and it is stated rather than assumed away.
4. **It costs nothing and generates nothing.** D-063 recorded that the generation-prompt
   change makes any *new* run incomparable with D-059 along the generation-quality
   dimension. P3 performs no generation, so that incomparability does not enter — a point
   restated in the results report.
5. **It is the direct repair of the wave-5 blocker.** Wave 5 lacked a comparable
   distribution at candidate granularity. P3 supplies 26 rows at exactly that granularity.

## 4. Limits of P3, declared before the numbers exist

- **"Does not match the labelled span" is not "verified free of defect."** Black plausibly
  contains other genuine defects at these anchors; the D-059/D-062 record already holds one
  candidate (`ed1d3ea89b`) whose reproduction failed on both sides. The label this study can
  defend is *does not anchor on the corpus's labelled defect region for this case*, and that
  is the phrasing every reported number will carry.
- **Pure-insertion fixes are unlabelled on the head side.** D-062 pre-registered this: a fix
  hunk that is a pure insertion has no old-side span, so a real defect can sit where the
  corpus never points. Each candidate is reported with its case's
  `unlabelled_hunks_present` flag, and a non-match on such a case is weaker evidence than a
  non-match on a fully labelled case. No match is ever inferred from an unlabelled hunk.
- **One project, one run, n = 26.** No significance test will be run and no statistical
  conclusion may be read into the tables. Distributions are printed side by side for that
  reason.
- **These are pre-V candidates.** All 26 recorded wealths equal `S·T` exactly; V was not
  purchased for any of them. That is the population where an F multiplier would apply, which
  is what makes it the right unit — and it also means the arithmetic in §5 is the arithmetic
  that governs.

## 5. Wave 3's decision rule, pre-registered

At an F cap of `c`, a candidate crosses the surfacing threshold of 10 only if
`S·T·c ≥ 10`. At the owner's `c = 1.2` that requires `S·T ≥ 8.334`.

- D-063's exhaustive grid puts the **reachable** `S·T` ceiling at 9, so `c = 1.2` does clear
  the threshold at that ceiling. That statement is correct and is not in dispute.
- The **observed** `S·T` in this population tops out at **3.0** (`T = 1.0` on all 26 rows),
  a factor of 2.8 below what `c = 1.2` needs.

So the counterfactual is computable and its result is already determined by arithmetic that
has nothing to do with F's discrimination: at `c = 1.2`, zero candidates cross, in both
groups. Wave 3 will report that, will report the cap that *would* be required against the
observed maximum (`10 / 3.0 = 3.34`), and will report the false-trigger column at that
hypothetical cap so the trade-off is visible rather than asserted. Reporting "0 crossings"
alone would hide which of the two facts caused it.

**The rule, fixed now:** F is worth an owner pricing argument only if, at some cap, it lifts
at least one labelled-defect candidate across the threshold while lifting strictly fewer
non-labelled ones. If the four fields do not separate the groups, that is a legitimate
result and it terminates the line of work in `docs/backlog.md` with the pricing layer
recorded as not activatable under foreseeable evidence. No fifth or sixth slice of the same
history will be attempted, and no alpha, cap or constant will be moved to force a crossing.

---

# Results

Everything below was produced by
`scripts/acceptance/d065_candidate_unit_discrimination.py` from committed
artifacts only: the frozen manifest, the wave-5 counterfactual record and D-064's
recorded F values. **No model call, no execution, no generation, $0.00.** D-063
recorded that the changed generation prompt makes any *new* run incomparable with
D-059 along the generation-quality dimension; that incomparability does not enter
here, because nothing was generated — these are the same 26 candidates D-064
measured, regrouped.

Artifact: `docs/acceptance/evidence/2026-09-01-d065-candidate-unit-discrimination/result.json`.

## 6. The split, and what the non-defect group turned out to be

At the pre-registered `line_slack = 3`: **20** candidates anchor on a labelled
defect region, **5** do not, and **1** sits on a fix-applying head where no
labelled defect exists at all.

Sensitivity across D-062's ladder — the split is stable from slack 3 upward and
moves a lot below it, so the pre-registered value sits just inside the plateau
rather than on a cliff:

| line slack | 0 | 1 | 2 | **3** | 4 | 5 | 10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| on labelled defect | 10 | 14 | 18 | **20** | 20 | 20 | 20 |
| off labelled defect | 15 | 11 | 7 | **5** | 5 | 5 | 5 |

**The composition of the off-label group is the result's main weakness and has to
be read before its numbers.** Four of its five members anchor in
`tests/test_black.py`. That file is genuinely part of the reviewed diff — the
corpus checkouts show `pair-169429c32175` touching `black.py`,
`tests/data/bracketmatch.py` and `tests/test_black.py` — but BugsInPy's
`bug_patch.txt` labels only the source hunks, so **a test-file anchor cannot be
labelled at all, by construction**. It is unlabelable, not verified clean. The
fifth member is `black.py:610`, 16 lines from the nearest label, on a case whose
fix carries an unlabelled pure-insertion hunk; its claim ("the early-return guard
for empty input was removed from `decode_bytes`") reads like a real second defect
in the same reverted hunk that the corpus simply does not point at. D-062 recorded
the same anchor as unmatched-with-unlabelled-hunks in a different run.

So this population did give the candidate-unit comparison wave 5 lacked, and both
groups are non-empty — but the non-defect side is small (n = 5) and is mostly
"test file", not "clean production code". That is the honest description of it.

## 7. The four fields, per candidate

`d` is the anchor's distance to the nearest labelled span; `—` means the field is
undefined because no commit touched the line in the trailing 12 months. Bands are
quartiles against an in-repository ruler of D-064's non-defect anchor lines from
the same projects (n = 42 for commits/authors, n = 33 for the two fields that
need at least one commit).

### On labelled defect region (n = 20)

| finding | anchor | d | commits | repair_share | authors | days | bands (c/r/a/d) |
|---|---|---:|---:|---:|---:|---:|---|
| `ecd0d8a55f` | `black.py:3128` | 0 | 0 | — | 0 | — | Q1/—/Q1/— |
| `947e73f5b0` | `black.py:3132` | 2 | 0 | — | 0 | — | Q1/—/Q1/— |
| `49780192ad` | `black.py:729` | 0 | 2 | 0.00 | 2 | 35 | Q4/Q2/Q4/Q1 |
| `1aef9852c1` | `black.py:733` | 2 | 2 | 0.00 | 2 | 35 | Q4/Q2/Q4/Q1 |
| `d86821caa8` | `black.py:736` | 1 | 2 | 0.00 | 2 | 35 | Q4/Q2/Q4/Q1 |
| `bebe817fe9` | `black.py:954` | 0 | 2 | 0.00 | 1 | 105 | Q4/Q2/Q3/Q3 |
| `37fe34cc56` | `black.py:959` | 2 | 1 | 0.00 | 1 | 122 | Q2/Q2/Q3/Q3 |
| `28c783fdb3` | `black.py:961` | 0 | 1 | 0.00 | 1 | 122 | Q2/Q2/Q3/Q3 |
| `1011d00037` | `black.py:981` | 2 | 1 | 0.00 | 1 | 122 | Q2/Q2/Q3/Q3 |
| `2abb294691` | `black.py:982` | 1 | 1 | 0.00 | 1 | 122 | Q2/Q2/Q3/Q3 |
| `24ee361fb0` | `black.py:985` | 0 | 2 | 0.00 | 1 | 105 | Q4/Q2/Q3/Q3 |
| `3be013b832` | `blib2to3/pgen2/tokenize.py:519` | 0 | 2 | 0.00 | 1 | 152 | Q4/Q2/Q3/Q3 |
| `fdac4eb193` | `black.py:397` | 0 | 0 | — | 0 | — | Q1/—/Q1/— |
| `d28323d300` | `black.py:2947` | 1 | 1 | 0.00 | 1 | 90 | Q2/Q2/Q3/Q3 |
| `68d9425c5c` | `black.py:2951` | 3 | 3 | 0.00 | 2 | 11 | Q4/Q2/Q4/Q1 |
| `c42968ae5a` | `black.py:626` | 0 | 2 | 0.00 | 2 | 65 | Q4/Q2/Q4/Q1 |
| `5841c3a234` | `black.py:1355` | 0 | 0 | — | 0 | — | Q1/—/Q1/— |
| `ec728e8f03` | `black.py:2493` | 0 | 2 | 0.00 | 1 | 252 | Q4/Q2/Q3/Q4 |
| `1db8d034eb` | `black.py:2494` | 1 | 3 | 0.33 | 2 | 30 | Q4/Q4/Q4/Q1 |
| `f101fb39b7` | `black.py:2496` | 3 | 3 | 0.33 | 2 | 30 | Q4/Q4/Q4/Q1 |

### Off labelled defect region (n = 5)

| finding | anchor | d | commits | repair_share | authors | days | bands (c/r/a/d) |
|---|---|---:|---:|---:|---:|---:|---|
| `ef0ff1eb65` | `tests/test_black.py:100` | — | 1 | 0.00 | 1 | 82 | Q2/Q2/Q3/Q2 |
| `ad88dcb0af` | `tests/test_black.py:453` | — | 1 | 0.00 | 1 | 84 | Q2/Q2/Q3/Q3 |
| `0c62269412` | `tests/test_black.py:461` | — | 1 | 0.00 | 1 | 356 | Q2/Q2/Q3/Q4 |
| `00afbee573` | `tests/test_black.py:1645` | — | 1 | **1.00** | 1 | 262 | Q2/Q4/Q3/Q4 |
| `a11831e7c2` | `black.py:610` | 16 | 1 | 0.00 | 1 | 0 | Q2/Q2/Q3/Q1 |

### Fix-applying head, no labelled defect exists (n = 1)

| finding | anchor | commits | repair_share | authors | days | bands (c/r/a/d) |
|---|---|---:|---:|---:|---:|---|
| `aa80cdc675` | `black.py:3123` | 1 | **1.00** | 1 | 0 | Q2/Q4/Q3/Q1 |

## 8. The four fields, side by side

| field | on labelled defect | off labelled defect | fix-applying head |
|---|---|---|---|
| commits | n = 20 · median 2 · p25 1 · p75 2 · mean 1.50 · max 3 | n = 5 · median 1 · p25 1 · p75 1 · mean 1.00 · max 1 | n = 1 · 1 |
| repair_share | n = 16 · median 0.00 · p75 0.00 · mean **0.042** · max 0.33 | n = 5 · median 0.00 · p75 0.00 · mean **0.200** · max 1.00 | n = 1 · 1.00 |
| distinct_authors | n = 20 · median 1 · p25 1 · p75 2 · mean 1.15 · max 2 | n = 5 · median 1 · p25 1 · p75 1 · mean 1.00 · max 1 | n = 1 · 1 |
| days_since_last_change | n = 16 · median **97.5** · p25 35 · p75 122 · mean **89.6** · max 252 | n = 5 · median **84** · p25 82 · p75 262 · mean **156.8** · max 356 | n = 1 · 0 |

No significance test was run and none may be read in. n = 5 on one side.

Three things are visible in the tables and are worth naming, all of them
statements about these 26 rows and nothing more.

**The two fields D-064 called directionally suggestive do not carry to this
unit.** At the anchor-line unit D-064 reported defect lines with a higher repair
share (mean 0.30 vs 0.14) and a shorter time since last change (median 65 vs 109).
At the candidate unit both invert or dissolve: repair share is *higher* in the
off-label group (mean 0.200 vs 0.042), and days-since-last-change disagrees with
itself — the median says the off-label group was touched **more** recently
(84 vs 97.5) while the mean says much less recently (156.8 vs 89.6), because two
off-label values (262, 356) carry a five-element sample. Meanwhile the two fields
D-064 found flat at the line unit — commits and distinct authors — are the two
that show any separation here, weakly and in the expected direction (medians 2 vs
1; means 1.50 vs 1.00 and 1.15 vs 1.00). Which fields carry is not stable across
the two units.

**F is close to constant inside a single review.** Across the seven cases that
produced more than one candidate, `repair_share` takes exactly one distinct value
in six of them (0.00 in five); `distinct_authors` spans at most 2 values with a
spread of ≤ 2; `commits` spreads ≤ 3. Three candidates in `case-2dad0cb4c5b5`
carry the identical tuple (2, 0.00, 2, 35), and four in `case-3efff8123ae7` carry
(1, 0.00, 1, 122). This matters more than any of the group means: a priced F would
multiply one candidate against another **on the same head**, and a quantity that
barely moves inside a head cannot re-order what a reviewer sees in one review,
whatever it does across a corpus.

**The bands do not separate the groups either.** Every off-label candidate sits at
commits Q2 and authors Q3 — no spread at all against the in-repository ruler —
while the on-label group straddles Q1, Q2 and Q4 on both. The single highest
repair-share band (Q4) is reached by two on-label candidates and by two of the
three rows that are *not* on a labelled defect (`00afbee573` and the fix-applying
head's `aa80cdc675`, both at repair_share 1.00). F is also **undefined** on 4 of
20 on-label candidates (no commit touched the line in the window) and on 0 of 5
off-label ones.

## 9. Wave 3 — what pricing F at 1.2 would actually do

| F cap | needs `S·T ≥` | crossings, on-label | crossings, off-label | crossings, fix-applying head |
|---:|---:|---:|---:|---:|
| **1.2** | **8.334** | **0** | **0** | **0** |
| 1.5 | 6.667 | 0 | 0 | 0 |
| 2.0 | 5.000 | 0 | 0 | 0 |
| 3.0 | 3.333 | 0 | 0 | 0 |
| 3.34 | 2.994 | 5 | 1 | 0 |
| 4.0 | 2.500 | 12 | 4 | 0 |
| 5.0 | 2.000 | 20 | 5 | 1 |

**At the owner's cap of 1.2, no candidate speaks — in either group.** The
requested "full text of every candidate that would speak" is therefore empty, and
the false-trigger count on the non-defect group is 0 for the trivial reason that
the trigger count is 0 everywhere. Reporting only "0 crossings" would hide which
fact caused it, so here is the cause:

- crossing requires `S·T·c ≥ 10`, so `c = 1.2` requires `S·T ≥ 8.334`;
- the observed maximum `S·T` over all 26 candidates is **3.0**;
- `T = 1.0` on **every one of the 26** — the T channel bought nothing at all;
- `S` took only four values: 2.0 (×10), 2.639 (×9), 2.9485 (×1), 3.0 (×6).

The owner's arithmetic is correct where it was aimed: against D-063's *reachable*
`S·T` ceiling of 9, a cap of 1.2 does clear 10, since `9 × 1.2 = 10.8`. The gap is
that the reachable ceiling has never been observed. Against the observed ceiling
of 3.0 the cap would have to be `10 / 3.0 = 3.34` before a single candidate
crosses — nearly three times the value that the reachable ceiling suggests, and
far outside any cap this project would defend.

Two further points, both structural rather than empirical:

**A flat cap cannot discriminate, by construction.** If every candidate is
multiplied by the same `c`, the crossing set is exactly `{S·T ≥ 10/c}` — a
function of S and T alone that carries no F information whatsoever. That is why
the 3.34 row splits 5:1 and the 4.0 row 12:4: those are the S·T distributions of
the two groups (20:5), not discrimination. At cap 5.0 *everything* crosses,
including `aa80cdc675` — the candidate on a **fixed** revision, where the known
defect is absent by construction.

**At cap 1.2 the answer is invariant to how F is graded.** Some future F might map
its four raw values to a multiplier in [1, 1.2] instead of a flat 1.2. It would
change nothing here: any multiplier bounded above by 1.2 still requires
`S·T ≥ 8.334`, and nothing in this population is within a factor of 2.7 of that.
The binding constraint is S·T, not F. No graded map was simulated, because the
inequality settles it and simulating one would only be a fifth slice of the same
history.

## 10. Judgement

**Can the pricing layer be activated? On the evidence this project holds: no — and
F is not the reason.**

The reason is that `S·T` never approaches its own reachable ceiling. D-063
established the structural bound (`S·T ≤ 9 < 10`, smallest wealth 0.5 > 0.1, so
only V crosses and V crosses alone) and measured 0 changed decisions across 45
reachable combinations, 26 recorded candidates and 20 rows over D-059's findings.
This study adds the observed distribution behind that bound: max `S·T` = 3.0,
`T = 1.0` on all 26, `S ≤ 3.0`. A fourth channel capped anywhere a channel cap
would plausibly be set does not close a factor-of-2.8 gap, and closing it by
raising a cap or moving alpha is exactly the change §16 reserves to the owner and
that this task forbids.

Separately, and on its own terms, **F did not discriminate at the candidate unit**
on this population. Of its four fields, the two that looked promising at the
anchor-line unit invert or dissolve; the two that were flat there separate the
groups only weakly; the percentile bands do not separate them; and the field
values are near-constant within a single review, which is the unit where a priced
F would have to act. n = 5 on the non-defect side and four of those five are
unlabelable test-file anchors, so this is not a refutation of F either — it is a
measurement that failed to find the signal, at the unit that matters, on the best
population available at zero cost.

Both halves of that are recorded in `docs/backlog.md`. Per the pre-registered
rule in §5, no fifth slice of the history was attempted, and no cap, alpha or
constant was moved.
