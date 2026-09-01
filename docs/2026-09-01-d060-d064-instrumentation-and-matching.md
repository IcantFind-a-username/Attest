# D-060 – D-064 handoff — report attribution, the oracle's API, the matcher rule, the pricing instrument, and F

- **Work order:** the five waves the owner scoped on top of D-059, run in order.
- **Baseline:** `feature/m01-audit-window-and-repeat-semantics` @ `157a9fc`, clean tree.
- **Branch:** `feature/m01-audit-window-and-repeat-semantics`, **now on `origin`**.
- **Paid/remote actions:** **zero paid calls, $0.00.** Every number below comes from local
  execution or from re-scoring frozen artifacts. `DEVSPEND.md` is unchanged because there is
  nothing to record. The one remote action is the branch push the owner asked for.
- **Decisions:** D-060 through D-064. The highest existing entry was D-059, scanned across
  both the `- **D-NNN` bullets and the `### D-NNN —` headings.

## Wave 1 — the branch is off this machine, and two report-layer defects are closed

The branch is pushed; the four certified receipts and their evidence chain no longer exist
only here.

**Defect A — no evidence class named its judge.** `runner.py` let the benchmark oracle's
per-finding class overwrite the product's, and every report printed the survivor unlabelled.
`Prediction` now carries `product_evidence_class` and `oracle_evidence_class` side by side
with `evidence_class_authority` naming which one is effective; the merge happens once, in
`extract_predictions_from_rows`, and keeps both.

**Defect B — counts came from surfaced predictions only.** Every candidate the gate did not
surface disappeared. Counts are built from the durable per-candidate verification records
when they exist, and `basis` states which denominator was used.

Replayed on the committed D-059 artifact, no re-execution and no model call:

| | before | after |
|---|---|---|
| run total | `{regression_reproduced: 3, unfaithful: 1}` | product over 23 candidates `{indeterminate: 17, regression_reproduced: 4, unfaithful: 2}`; oracle over its 4 receipts `{regression_reproduced: 3, unfaithful: 1}`; `oracle_overturned_product: 1` |
| `case-81039ffa0c1e` | `{}` | product `{indeterminate: 1, unfaithful: 1}` over its 2 candidates |
| `case-c6f141a2be09` | `{unfaithful: 1}` | product `regression_reproduced` beside oracle `unfaithful`, disagreement counted |

The second row is defect B in one line: a case holding two classified candidates reported an
empty map. The third is defect A: `{unfaithful: 1}` was unreadable, because it did not say
that the product had certified the finding and the oracle had overturned it.

Report schema version 4 -> 5.

## Wave 2 — the oracle's reproduction, and both numbers

The one D-059 oracle receipt that refuted a product certificate did so with a test that
raised on both revisions. Replayed through the product's own `execute_differential` at the
pair's two SHAs, 3 repeats per side, corpus Python 3.8.3, **zero paid calls**:

| body | head runs | base runs | status | class |
|---|---|---|---|---|
| as generated: `black.Mode(line_length=88)` -> `format_str(src, line_length=88)` | FAIL 3/3 | FAIL 3/3 | `buggy_fail_fixed_fail` | `unfaithful` |
| corrected: `format_str(src, mode=...)`, the API that revision defines | FAIL 3/3 | PASS 3/3 | `buggy_fail_fixed_pass` | `regression_reproduced` |

So D-059's `differential_v.confirmed` is **3 of 4 as recorded and 4 of 4 corrected**, and its
`oracle_overturned_product` is 1 as recorded and 0 corrected. Both are reported; neither
replaces the other.

The justification does not depend on that outcome, and was stated before it was known: a test
that raises identically on both revisions has zero discriminating power whichever side is
right, so it is not evidence about the finding in either direction.

The durable part is a prompt constraint: the generator must call only names the supplied
source context shows the revision defining, and must not guard the call under test with a
`try`/`except` around an alternative spelling. That prompt is shared by the product proposer
and the oracle, so **generation changes on both arms and the next paid run is not
generation-comparable to D-059's.** No RED test is named — the change is a prompt whose
effect is model behaviour, and the only deterministic test would assert a substring, which
D-058 §3.1 forbids. `scripts/acceptance/d060_oracle_api_replay.py` is the durable check.

## Wave 3 — the matcher rule was written down before it was written

D-062's pre-registration was committed at `35ecaa5`, **before `matcher.py` was touched**. It
records the rule, two grounds that hold on the corpus's construction alone, and the count
expected at each tolerance.

The two grounds, both true before any run existed: an anchor names the *statement* a proposer
is talking about while a truth span names the *lines a patch touched*, and a Python
statement's header, condition and guarded call routinely sit on different physical lines; and
a fix hunk that is a pure insertion has no head-side line range at all, so the reverted head
carries a defect the corpus never labels.

The rule as applied: `line_slack = 3`; truth spans unchanged, because they already equal
every head-side hunk — verified across all 19 `historical_bug_replay` cases of `attest-v1`
with zero mismatches, so the frozen manifest and its digest are untouched; and unmatched
findings in a case with unlabelled fix hunks are flagged rather than folded silently into the
miss count.

Re-scored, no execution and no model call:

| receipts | old rule (`line_slack = 0`) | new rule (`line_slack = 3`) | **declared in advance** |
|---|---:|---:|---:|
| D-059 as recorded | 1 / 4 | **2 / 4** | 2 / 4 |
| with wave 2's corrected receipt | 1 / 4 | **3 / 4** | 3 / 4 |

Sweep (as recorded / corrected): slack 0 -> 1 / 1; 1 -> 2 / 2; 2 through 10 -> 2 / 3;
16 -> 3 / 4. **Every tolerance in [2, 15] gives the same answer,** so the count does not hinge
on the value chosen — that sweep, not the author's word, is what makes the choice auditable.

Every declared number held. `20d686ba82` matches at no tolerance below 16, as declared, and
its case carries 1 head-side label against 2 fix-side hunks, so it is flagged. One thing was
not declared and is recorded as such: under the old rule `b1e7f57dc2` was also flagged,
because its case likewise has 1 label against 2 hunks; the flag clears once it matches.

**Limit of this pre-registration, stated plainly:** the author had already read D-059's
per-finding distances when choosing the value, so this is a recorded rule with a declared
prediction, not a blind one. The sweep is the part that does not depend on the author.

`matched` is a count of location bindings. Precision and recall remain **not estimated**.

## Wave 4 — the pricing layer now reports whether it is load-bearing

Every candidate carries one recorded field, `pricing_changed_decision`: whether the decision
taken on the full wealth differs from the decision the strongest single purchased channel
would have taken against the same threshold. It is written to the durable per-candidate
`review` ledger row and the candidate store, and surfaced by `attest stats` and the
calibration report beside precision, abstention rate and silence precision. **The gate never
reads it.**

Backfilled over every per-candidate record held, no model call and no execution:

| source | candidates | changed |
|---|---:|---:|
| exhaustive reachable channel grid at alpha = 0.1 | 45 combinations | **0** |
| 2026-09-01 history counterfactual (S, T, wealth recorded) | 26 | **0** |
| D-059's four surfaced findings, over every reachable S | 4 (20 rows) | **0** |

**The wealth multiplication has changed a decision zero times to date,** and the grid says
why it is structural rather than incidental: with the frozen factory tables `S * T` tops out
at 9, below the surfacing threshold of 10, while the smallest reachable wealth is 0.5, above
the discard threshold of 0.1. Only V reaches the threshold, and V = 20 alone already reaches
it. Every certified receipt this project has produced was decided by V on its own.

This is not an argument to remove S, T or the multiplication, and it is not an accuracy
statement. Raising a cap, lowering alpha or pricing a new channel changes the enumeration and
needs its own. A second test pins that the instrument does fire when the product genuinely
decides something its strongest channel does not.

## Wave 5 — F redefined once, measured once, still unpriced

v1 asked whether a recent revert or hotfix owned the anchor line, and fired 0/26. F now
records four raw values and thresholds none of them: commits touching the anchor line in the
trailing 12 months, the share whose subject matches a recorded repair vocabulary, distinct
authors, and days since the line last changed. The window ends at **the reviewed revision's
own commit date**, so a 2019 revision is asked about its own year. F buys no wealth, orders
nothing, vetoes nothing and reaches no publication path.

The measure is **discrimination, not trigger rate.** Both units are reported; the full
per-candidate table is in the artifact's `per_candidate.rows`.

### Per candidate — the unit the product emits

| field | `historical_bug_replay` (n = 25) | `developer_fix_control` (n = 1) |
|---|---|---|
| commits | median 1, p25 1, p75 2 | 1 |
| repair_share | median 0.00 (n = 21 defined) | 1.00 |
| distinct_authors | median 1, p25 1, p75 2 | 1 |
| days_since_last_change | median 90, p25 35, p75 122 (n = 21) | 0 |

The control arm produced **one** candidate. There is no distribution to compare at this unit,
and that is the result, not a formatting problem.

### Per anchor line — 72 labelled defect lines against 72 non-defect lines

Control lines are fixed-stride lines from the same file at the same revision, at least 10
lines from every changed location, chosen without reference to what the signal says.

| field | defect line (n = 72) | non-defect line (n = 72) |
|---|---|---|
| commits | median 1, p25 1, p75 2, mean 1.32, max 4 | median 1, p25 0, p75 2, mean 1.13, max 9 |
| repair_share | median 0.00, p75 1.00, mean 0.30 (n = 54) | median 0.00, p75 0.00, mean 0.14 (n = 51) |
| distinct_authors | median 1, p25 1, p75 1, mean 0.99 | median 1, p25 0, p75 1, mean 0.81 |
| days_since_last_change | median 65, p25 11, p75 122, mean 86 (n = 54) | median 109, p25 74, p75 158, mean 126 (n = 51) |

**No significance test was run and none should be read in.** Small samples, one project,
heavily overlapping distributions, printed side by side.

### Judgement on this channel

The redefinition did what it was for. v1 was constant and therefore could not discriminate
anything; v2 is not constant, and two of its four fields point the way one would expect —
defect lines were touched more recently and by a larger share of repair-worded commits. The
other two have identical medians.

That is not enough to price F, and it is not a refutation. The blocking gap is the candidate
unit: the control arm emits almost no candidates, so on this corpus F cannot be evaluated
where it would actually be used. Pricing would need a control arm that produces candidates
and a second corpus, each with its own owner-approved work order.

One caveat any future pricing argument has to bound first: a BugsInPy head sits at the
bug-introducing commit, so the defect region was necessarily touched recently in that head's
own history. Real pull requests also review recently changed code, so the analogy is not
empty, but the size of that inflation is unmeasured.

**Stopping here by design.** One redefinition, one measurement, no third or fourth slice.
The result and the conditions are in `docs/backlog.md`.

## What did not change

No factory statistical constant, alpha, LR, channel cap, hard-publication cap, gate
threshold, coverage threshold, product-package coverage floor, containment behaviour,
execution timeout or resource limit. F is not priced and does not enter wealth. C-02, V-01,
X-01 and V-03 were not touched. The frozen `attest-v1` manifest, its digest and its
validation receipt are unchanged. Accuracy, precision and recall remain **not estimated**.

## Artifacts

| path | SHA-256 |
|---|---|
| `docs/acceptance/evidence/2026-09-01-d060-oracle-api-replay/result.json` | `a78ddabd88f04436dd1daf58dcca32fa284147d5e68765134da2b66973e66d1b` |
| `docs/acceptance/evidence/2026-09-01-d062-matcher-rescore/result.json` | `e2071ec565bea435c99b9d8457d1d68031742a06bf7f81de340e3f7bd6fe509b` |
| `docs/acceptance/evidence/2026-09-01-d063-pricing-instrument/result.json` | `4c1b84e2131cb56a4495e1c50e46ec0a801ea281f0f14d24b9eb8f1b7dfa91a7` |
| `docs/acceptance/evidence/2026-09-01-d064-history-heat/result.json` | `e1f8658cf7fa7d84594141b361612e7f802d8f7bc16913cbb266dc1d941daa99` |

All four are regenerable from `scripts/acceptance/`.

## Gate

Run on `e6efadf81d3cdd37d93d1329a4fb7f9691eb63c5`; the two later commits touch only `docs/`
and no source file changed after this run started.

| command | result |
|---|---|
| `python -m pytest --cov=src/attest --cov-report=term-missing` | **pass**, exit 0, 1628 tests, 1 skipped |
| `python -m ruff check .` | **pass** |
| `python -m mypy src/attest` | **pass**, 57 source files |
| `git diff --check` | **pass** |

**Coverage: 92.37% total, threshold 90.0% reached.** The production packages the Gate applies
the floor to: `attest.cli` 96%, `attest.github` 91–100% per module, `attest.review` 88–100%
per module. The two modules this task changed most in `attest.review` read
`gate.py` **100%** and `history.py` **90%**. Nothing was papered over with filler tests
(D-058 §3.1); every test added here pins a named contract.

Environment: `.venv`, CPython 3.12.2, darwin. This is the ordinary work-order Gate on one
supported Python; the dual-version integration Gate is not claimed.

## Independent review

One pass, per D-049. One defect was reproduced and fixed in this branch: a taskless
pre-execution defer emitted a bare `{}` for its evidence-class counts, which under the new
shape reads as a map missing its judge keys rather than as an honest empty census. Fixed in
`e6efadf`. One unreproduced concern went to `docs/backlog.md`: the graded F observation walks
line history with `git log -L` rather than reading one blame record; measured at ~0.1 s per
candidate here and on the corpus checkouts, and it fails open at 15 s, so no defect exists to
fix, but the worst case on a very large history is unmeasured.

## Known limits and next unblocked work

- Precision and recall remain **not estimated**, and `matched = 2/4` or `3/4` does not change
  that. No validation receipt with scoring authority exists for `attest-v1`.
- The next paid run is **not generation-comparable** to D-059's, because wave 2 changed the
  shared generator prompt.
- F cannot be evaluated at the candidate unit on this corpus: the control arm emits almost no
  candidates. That, and a second corpus, are the prerequisites for any pricing argument.
- D-059's dominant remaining loss is still the per-case product budget at `--budget-usd 0.16`
  (15 of 23 candidates), an evaluation knob rather than a product guard.
- Untouched and still owner-gated: C-02, V-01, X-01, V-03, the process-audit window widening,
  and any pricing of F.
