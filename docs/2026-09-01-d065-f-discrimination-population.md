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
