# Forward pairs, reviewed: 3 published of 11, and the value class is 0 of 1

**Owner instruction 3 of 2026-09-05d. D-135, D-140.** Reservation $11.00 (the maximum: 11 reviews
× the `--budget 1.00` ceiling), **spent $2.580400**, $8.419600 released. Driver:
[`scripts/corpus/forward_pair_reviews.py`](../../scripts/corpus/forward_pair_reviews.py).
[Pairs and how they were built](../corpus/forward-pairs.md).
[Data](evidence/2026-09-05d-forward-pair-reviews.json).

**n = 11, and every row below says `fwd`.** A value-class number from a reversed pair may not be
quoted (D-135), so a table that does not say which direction it came from invites exactly the
mistake the policy exists to prevent. Eleven is a thin denominator and this report does not
pretend otherwise; the corpus was not extended this window, by instruction.

`attest.intent.v4.1`, K = 4, `--budget 1.00`, `linux-container-v1`, head = the commit that
introduced the defect, base = its parent, local review only — no GitHub write.

## 1. The table

| # | dir | repo | head | base | candidates | answered about the code | budget-refused | host-blocked | certified | published | value: cert / drawer |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `fwd` | `attrs` | `e048efcb39` | `75723b7720` | 2 | 0 | 0 | 1 | 0 | 0 | 0 / 0 |
| 2 | `fwd` | `attrs` | `7c85d68de2` | `564fade925` | 1 | 1 | 0 | 0 | 0 | 0 | 0 / 0 |
| 3 | `fwd` | `click` | `0585f456ba` | `cfa01eeb78` | 10 | 9 | 0 | 0 | 0 | 0 | 0 / 0 |
| 4 | `fwd` | `click` | `cd4674a6de` | `d5fbd32842` | **42** | 4 | **25** | 1 | 0 | 0 | **0 / 1** |
| 5 | `fwd` | `click` | `19fd4d6e18` | `c69643b60c` | 7 | 7 | 0 | 0 | 0 | 0 | 0 / 0 |
| 6 | `fwd` | `itsdangerous` | `3703fbdedd` | `64048c1106` | 7 | 5 | 0 | 0 | **1** | **1** | 0 / 0 |
| 7 | `fwd` | `more-itertools` | `d63a26e56e` | `d0c20f5946` | 1 | 1 | 0 | 0 | 0 | 0 | 0 / 0 |
| 8 | `fwd` | `more-itertools` | `2deea20ead` | `6235e945d9` | 1 | 1 | 0 | 0 | **1** | **1** | 0 / 0 |
| 9 | `fwd` | `more-itertools` | `71b76842d3` | `3331507287` | 1 | 1 | 0 | 0 | **1** | **1** | 0 / 0 |
| 10 | `fwd` | `more-itertools` | `390a3db74c` | `935db916c7` | 2 | 2 | 0 | 0 | 0 | 0 | 0 / 0 |
| 11 | `fwd` | `packaging` | `527be81862` | `e934f4896e` | 1 | 0 | 0 | 1 | 0 | 0 | 0 / 0 |
| | | **11 pairs** | | | **75** | **31** | **25** | **3** | **3** | **3** | **0 / 1** |

**The three counts after "candidates" are three different things and only one of them is a
denominator.** A candidate the budget refused before buying a reproduction, and a candidate the
container image could not run, were never asked about the code. The recall denominator is
**31 candidates the policy answered about**, across **9 of the 11 pairs**.

## 2. The value class: 0 certified, 1 drawered, n = 11

**This is the first value-class recall number this project may quote, and it is `0 of 1` on the
only value-class candidate eleven forward pairs produced.**

The one candidate: `click cd4674a6de`, `src/click/core.py:2660`, on the parameter
slot-arbitration logic. Drawered by **clause (c)** — *intent stated in the change itself: the
same change also updates a test, a docstring, documentation, a changelog entry or an inline
comment about the symbol under test*.

**That is worth saying carefully, because it is the clause D-135 exonerated on forward pairs.**
The 2026-09-05b adjudication found clause (c) right on 7 of 8 forward receipts and wrong on 4 of
4 reversed ones, and that asymmetry is why reversed pairs are barred from value-class recall.
Here it fires on a **forward** pair — a genuine defect-introducing commit that also touched a
changelog. **One case is a data point, not a refutation**, and this report does not adjudicate it
either way; it is handoff item 2.

**What this number cannot support.** With one value-class candidate in eleven pairs, no recall
rate for the class is estimable — `0 of 1` has a 95% upper bound of 95%. The honest statement is
that **forward pairs in this corpus barely produce value-class candidates at all**, and that is
itself the finding: nine of the eleven defect-introducing commits produced only crash-shaped or
unfaithful candidates.

## 3. The crash class: 3 published, and 2 of them are the defect the later fix repaired

| repo | head | published claim | is it the oracle's defect? |
|---|---|---|---|
| `more-itertools` | `71b76842d3` | `len(element)` is called before the conversion to a tuple, so `product_index` raises `TypeError` for a generator argument that worked before | **yes** — the repairing commit is *"Fix `product_index()` with iterator input"* |
| `more-itertools` | `2deea20ead` | `iterables * repeat` repeats the *tuple of iterables* instead of each pool, changing `random_product` semantics for `repeat > 1` with several iterables | **yes** — the repairing commit is *"Fix `random_product()` as well"* |
| `itsdangerous` | `3703fbdedd` | `BadData.__str__` returns `self.message` directly instead of coercing, so `str(exc)` raises for a non-`str` message | **no** — a *different* real regression in the same commit |

All three are `regression_reproduced`, head FAIL 3/3 and base PASS 3/3 in `linux-container-v1`,
`value_mismatch = false` — the crash class, not the value class.

**The third one is real and this report does not dress it up.** `3703fbdedd` is the "Drop Python
2" merge; it replaced `return text_type(self.message)` with `return self.message`, and
`str(BadData(b"…"))` raises `TypeError: __str__ returned non-string` on head where base coerced.
A true regression, of low severity, and **not** the timezone defect whose test located this
boundary. Finding a different real regression than the oracle's is a **true positive**, not a
miss — but a recall number computed against the oracle would score it as neither.

## 4. Where the other 72 candidates went

| what the verification said | n | what it is |
|---|---|---|
| **the budget ran out** before a reproduction was generated | 25 | all on pair 4, a 42-candidate diff |
| **unfaithful generated test: fails on base as well** | 20 | the generator wrote a test that does not discriminate |
| passed on head in 3/3 runs; base not executed | 4 | the claim did not reproduce at all |
| the container image could not be built or the tree could not be collected | 3 | Python 3.13 and Python 3.9 declarations |
| new-code candidate | 2 | the symbol is absent from base — D-063, not certifiable |
| binding: the reproduction exercises none of the changed lines | 1 | V-02 |
| intent (clause c) | 1 | §2 |

**The wall on forward pairs is generation, and it is a different wall from the one the reversed
corpus shows.** Twenty of the thirty-one answered candidates failed because the generated
reproduction fails on base too — the test captures behaviour that was already there rather than
what the commit changed. That is the predictable cost of the direction: on a **reversed** pair
the diff *is* a repair, so it hands the proposer the defect in its own text; on a **forward**
pair the diff is a feature commit that says nothing about being wrong, and the reproduction has
to find the discriminating input unaided. **Every recall figure taken on the reversed corpus is
inflated by exactly this**, and D-135 said so before this run; here is the measurement.

**The budget wall is the second-largest cause and it is concentrated in one review.** Pair 4's
diff produced 42 candidates, and 25 of them were refused a reproduction at
`projected total $1.0x exceeds budget $1.00`. A per-PR budget is the right shape, but a recall
number taken at `--budget 1.00` on a large diff measures the budget as much as the product.

## 5. What is owed

1. **The clause (c) case of §2 is an adjudication, not a result** — handoff item 2.
2. **A value-class recall number needs value-class candidates**, and eleven forward pairs
   produced one. Either a much larger forward corpus, or the acceptance that this class is rare
   in natural defect-introducing commits and the number will stay uninformative.
3. **Re-running pair 4 at a higher budget** would say whether the 25 refused candidates hide
   anything; at `--budget 3.00` it is about $2.
