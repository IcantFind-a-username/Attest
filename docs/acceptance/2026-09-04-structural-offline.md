# The green level v0 measured offline: 24% of Python-touching units, $0.00, zero model calls

**Owner instruction 6 of 2026-09-04c.** Detector
[`src/attest/review/structural.py`](../../src/attest/review/structural.py), driver
[`scripts/corpus/structural_offline.py`](../../scripts/corpus/structural_offline.py), data
[`2026-09-04-structural-offline.json`](evidence/2026-09-04-structural-offline.json).

One class only: **the same implementation in two or more places.** Evidence: two coordinates
and a similarity measure, computed by an algorithm. A model is not called at all in this
measurement, and cannot be called in the detector at any time.

## 1. The rule, in this level's terms

Mainline §1.1: *the LLM thinks; an algorithm decides whether it may speak.* Green is the
cheapest place to demonstrate it, which is why it is first (§1.3). Here the algorithm decides
**twice**:

- **whether there is a finding** — two function bodies normalise to token sequences whose
  similarity clears 0.92, both clear a size floor (40 tokens, 4 statements), their lengths are
  within 15% of each other, and at least one is in a file the change touched;
- **whether the sentence may be said** — a fixed denylist of coordinate-free hedges ("may",
  "possibly", "consider", "likely", "可能", "建议重构") is applied to the published text, and
  it is applied **to the model's sentence exactly as it is applied to ours**. A hedging model is
  dropped and the deterministic sentence stands alone; the refusal is recorded, not hidden.

Normalisation erases identifiers, argument names and literal values — a renamed copy is still a
copy — and keeps attribute and callee names, so two functions that merely rhyme structurally do
not match. Docstrings are dropped. Test modules are excluded.

## 2. Trigger rate on real traffic

The E-04 stratum-v2 population: 100 units of the owner's most recent traffic, the same
population D-125's effect was measured on.

| | units | with changed Python | **units that speak** | findings |
|---|---|---|---|---|
| **real traffic** | 100 | 33 | **8** | 12 |
| **`G-NULL-001a` null controls** | 58 | 58 | **13** | 14 |

**8% of all units and 24.2% of Python-touching units produce at least one finding**; controls,
22.4%. Median findings per speaking unit: 1.

**The control rate is not a false-publication rate.** Duplication is a property of the code, not
of whether the commit was a defect, so a null control speaking is expected and correct. Green
claims a structural fact and makes no claim about defects — which is what makes it cheap to be
right about, and is also the limit of what it is worth.

## 3. Five adjudicated by hand

Sampled one per distinct pair and repository from the twelve traffic findings (four of the
twelve are the same pair seen at two commits).

| # | the pair | similarity | my judgment |
|---|---|---|---|
| 1 | `us-stock-helper` `patterns.py:334 _local_extrema` / `patterns_shapes.py:493 _local_extrema` | 1.000 | **True and worth saying.** Byte-for-byte identical, copied into a second module. |
| 2 | `Corum` `dependence.py:238 _validate_unit_interval` / `models.py:54 _require_probability` | 0.939 | **True, and the most useful of the five.** The same `[0,1]` validation written twice; one returns the float, one returns `None`. |
| 3 | `Attest` `scripts/corpus/natural_null.py:28 _classify` / `benchmark/prospective.py:317 classify_subject` | 0.962 | **True.** A script re-implements a library function with different return values (`None` vs `"fix"`/`"other"`) and one extra prefix. A latent divergence. |
| 4 | `Attest` `review/eligibility.py:72 show_file_at` / `review/planner.py:332 show_file_at` | 1.000 | **True, exact.** The same helper twice, one with a docstring. |
| 5 | `us-stock-helper` `evidence_provider.py:195 _seconds` / `market_brief.py:170 _env_fetch_deadline_seconds` | 0.933 | **Borderline.** Same env-parsing shape, but the second adds an upper bound (`0 < x <= 300`) and different messages. "The same implementation" overstates it; "these two parsers differ only in the bound" would not. |

**Four clearly true, one overstated, none false.** The one overstatement is at the bottom of the
similarity range, which suggests the threshold is if anything slightly low for the sentence the
level produces — a tuning question, and one no held-out slice has yet been spent on.

## 4. What this measurement does not establish

- **Nothing is wired into publication.** v0 is the detector, its adjudicators and this
  measurement; making green an author-visible channel is the green level's own step.
- **No model has been called, ever, by this code.** The one call is designed, tested with a stub
  and never exercised against the API — so the claim "the model's hedge is dropped" is proven
  against a stub, not against a model.
- **The constants are chosen, not tuned.** 0.92, 40 tokens, 4 statements, ±15% length: none of
  them has been fitted, and none may be fitted on a slice this measurement used.
- **Five is a small adjudication** and I adjudicated my own tool's output, on repositories that
  include `Attest` itself — the standing disclosed conflict.
