# The family is the change unit — the whole corpus recomputed, old against new

**D-125**, owner decision 2 of 2026-09-04 (backlog option (a) of the three shapes costed on
2026-09-03). The publication family stops being the pull request and becomes the **change
unit**, and the change unit is the **changed file the candidate is anchored in**. `alpha`, the
likelihood ratio, `K` and the hard cap are untouched.

Everything below is a **replay**: `scripts/corpus/replay_family.py` reads the recorded
candidates, ledgers and receipt bundles and asks the real `select_for_publication` again. No
model call, no execution, **$0.00**. Result:
[`evidence/2026-09-04-family-replay.json`](evidence/2026-09-04-family-replay.json).

## 1. The replay reproduces the record before it is asked anything else

For each of the **66** reviews with a `publication_policy` row across the three corpus clones,
the old rule is replayed over everything the run certified and compared with what the ledger
recorded. **66 of 66 match, exactly.** A task whose replay did not reproduce its own record
would be excluded from the comparison rather than counted; none was. That is what licenses the
new column.

The e-value each candidate carried is reconstructed as the ranking wealth times the V channel's
likelihood ratio — the same product C-05 was handed. It is checked, not assumed: a wrong
reconstruction would not have reproduced 66 ledger rows.

## 2. Old against new, per review

Every review that certified anything, on the **D-124-corrected** population (receipts whose
bundles verify offline). Reviews that certified nothing publish nothing under either rule and
are omitted; all 66 are in the JSON.

| case | population | m (PR) | units | old published | new published | |
|---|---|---|---|---|---|---|
| `d05` | defect (Attest) | 7 | 3 | 0 | **3** | **+3** |
| `d13` | defect (us-stock-helper) | 8 | 6 | 0 | **1** | **+1** |
| `d02` | defect (Attest) | 8 | 4 | 0 | **1** | **+1** |
| `d03` | defect (Attest) | 14 | 5 | 0 | 0 | |
| `d16` | defect (us-stock-helper) | 9 | 3 | 0 | 0 | |
| `d09` | defect (us-stock-helper) | 3 | 1 | 2 | 2 | |
| `d10` | defect (us-stock-helper) | 2 | 1 | 1 | 1 | |
| `d11` | defect (us-stock-helper) | 4 | 1 | 2 | 2 | |
| `d06` | defect (Attest) | 1 | 1 | 1 | 1 | |
| `d17` | defect (Corum) | 2 | 2 | 1 | 1 | |
| `d18` | defect (Corum) | 4 | 1 | 1 | 1 | |
| `d19` | defect (Corum) | 1 | 1 | 1 | 1 | |
| `d20` | defect (Corum) | 1 | 1 | 1 | 1 | |
| `c02` | **control** | 10 | 1 | **0** | **0** | |
| `c04` | **control** | 5 | 1 | **0** | **0** | |
| `c03` | control (mis-stratified) | 1 | 1 | 1 | 1 | |
| `c05` | control | 5 | 1 | 1 | 1 | |

**Totals across all 66 replayed reviews: 12 → 17 publications.**

## 3. The control condition, which is the one that decides adoption

The owner's rule for this decision: *any publication in the control group and the run stops for
root cause; the rule is not adopted.*

**No control gains a publication.** `c02` and `c04` certified findings and both stay below their
own unit's bar — `c02`'s ten eligible candidates are all in one file, so its bar is unchanged at
100 and its single certified receipt (e = 60) is suppressed exactly as before. Every other
control certified nothing under either rule. The two controls that already published, `c03` and
`c05`, publish the same finding under both rules; both were adjudicated true positives on
2026-09-03 — `c03` is the planted drill regression that should never have been in the control
population, and `c05` is a real defect in a commit the plan filed as documentation. The new rule
introduces neither.

**So the rule is adopted.** The five new publications are all on defect pairs.

## 4. Why the bar moves, measured

Across the 49 replayed reviews that had any eligible candidate:

| | n | median | mean | max | share at a bar ≥ 30 |
|---|---|---|---|---|---|
| PR-wide `m` | 49 reviews | 4 | 5.08 | 14 | 32 of 49 |
| per-unit `m_u` | 89 units | **2** | **2.80** | 10 | 36 of 89 |

Forty of the 89 units hold exactly one eligible candidate, so their bar is `1/alpha = 10` — the
smallest the method allows. That is the whole mechanism: a large change is many small families,
not one large one, and the candidate that used to compete with thirteen strangers in other files
now competes with the two or three findings in its own.

## 5. The five new publications

Each is a certified receipt — head fails 3 of 3, base passes 3 of 3, the changed lines executed,
the intent discriminator satisfied — that the PR-wide bar suppressed and its own unit's bar does
not.

| finding | file | e-value | unit bar | PR bar |
|---|---|---|---|---|
| `db100c9818` | `src/attest/execution/container_adapter.py:74` — a removed probe timeout lets a wedged docker daemon hang `image_digest` | 60.0 | 10 | 70 |
| `a47e7a8fa9` | `src/attest/execution/container_images.py:222` — build-context assembly no longer wrapped, so an `OSError` escapes `ensure_image` | 60.0 | 50 | 70 |
| `103aa42a3c` | `src/attest/execution/container_images.py:258` — a byte/str slice on the build-failure tail raises `TypeError` | 52.8 | 50 | 70 |
| `c5b90ad887` | `scripts/local_runtime_support.py:589` — an environment variable the deployment still expects is no longer set | 60.0 | 10 | 80 |
| `8f3851fe4b` | `scripts/corpus/swebench_pilot.py:319` — `--model` removed while `config.model` is still read, so the default cannot be overridden | 40.0 | 30 | 80 |

The hard cap is still binding and still hard: on `d05` **four** cluster representatives clear
their unit bars and only three are author-visible; the fourth is suppressed as *beyond the hard
author-visible cap*, not as below a threshold.

Three of the five are in `Attest`'s own repository — a **disclosed conflict of interest**, the
same one the corpus reports for every `Attest` row. One is in `us-stock-helper`, an outside
repository.

## 6. The rule ran, on 100 units it had never seen

The replay above is a counterfactual over recorded reviews. Later the same night the rule ran
for real: **E-04 stratum v2, 100 units of the owner's most recent traffic**
([report](2026-09-04-e04-stratum-v2.md)). It produced **21 accepted receipts and 7 shadow
findings on 3 units**.

Replaying those three units through the PR-wide bar — the same offline replay, now validating
121 of 121 recorded reviews — publishes **nothing**:

| unit | eligible `m` | units | PR-wide bar | old rule | **new rule** |
|---|---|---|---|---|---|
| `Attest@34affaf` | 7 | 3 | 70 | 0 | **1** |
| `us-stock-helper@7245680` | 20 | 8 | 200 | 0 | **3** |
| `us-stock-helper@cdf221f` | 16 | 5 | 160 | 0 | **3** |

**Under the previous rule that entire 100-unit run would have been silent** — 21 receipts, none
of them author-visible. That is the backlog item's claim, observed rather than argued.

It also moves the risk. A product that publishes nothing cannot be wrong in public. This one now
can, and **none of the seven has been adjudicated**: the shadow study's `semantic_precision` is
`INSUFFICIENT` and its safety stop, which is defined on *wrong* findings, cannot be evaluated
until someone product-blind reads them. The corpus replay's control condition (§3) is evidence
that the rule does not fire on commits believed defect-free; it is not evidence that these seven
are right.

## 7. What this replay does not establish

- **It is not a precision measurement.** Five findings on three reviews, on a population where
  the defect pairs were constructed by reversing known fixes. That the receipts are valid says
  the behaviour changed and the base did not have it; it does not say a reviewer wanted to hear
  about it.
- **The guarantee is weaker, and the weakening is the decision.** Bonferroni over `m_u` controls
  the family-wise error rate at `alpha` **inside a change unit**. Across a pull request the bound
  is now `hard_cap × alpha` — at most three findings are ever author-visible, and each carries
  its own unit's rate. Any split of `alpha` across units that preserved the PR-level rate gives
  back exactly the `m/alpha` bar it replaced; there is no free version of this.
- **The unit is the file, and a file is a crude unit.** A 900-line module with five unrelated
  defects is one family; two files that were edited for one reason are two. A finer unit (the
  enclosing function, or the diff hunk) would be closer to what "one change" means and is a
  change to `attest/certification/units.py` alone.
- **The replay assumes the run is otherwise unchanged.** Publication is the last stage, after
  every paid call, so a different bar cannot change what was proposed, what was eligible or what
  reproduced. It can only change which certified receipts become author-visible.
