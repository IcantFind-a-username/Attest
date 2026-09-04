# The green level as an author-visible channel, and its adjudicator against a real model (D-133)

**Owner instruction 4 of 2026-09-05.** Driver
[`scripts/corpus/structural_wording_check.py`](../../scripts/corpus/structural_wording_check.py),
data [before](evidence/2026-09-05-structural-wording-check.json) and
[after](evidence/2026-09-05-structural-wording-check-v2.json). **Cost $0.058770**,
`claude-sonnet-5` (the shipped default), 20 model calls in two runs of ten.

## 1. The measurement the owner asked for first: does the adjudicator hold against a model?

D-130 shipped the wording adjudicator and proved it only against a stub that hedged on purpose.
Ten findings the offline measurement already produced were handed to the real default model,
which was asked to state each one in plain language and propose a fix. **It was told nothing
about the rule** — no instruction to name a file, no list of banned words. The point is what a
model does unprompted.

| | run 1 — denylist only | run 2 — denylist + coordinate rule |
|---|---|---|
| findings asked | 10 | 10 |
| the model's sentence published | 7 | 4 |
| dropped | **3**, all for `'likely'` | **6**, all for `'likely'`/`'may'` |
| published sentences naming a coordinate | **7 of 7** | **4 of 4** |
| **coordinate-free prose admitted** | **0** | **0** |
| dropped for naming no coordinate | — | **0** |
| spend | $0.028920 | $0.029850 |

Per finding, run 1:

| # | the two coordinates | adjudicator | why |
|---|---|---|---|
| 1 | `patterns.py:334` / `patterns_shapes.py:493` | published | named both files and the function |
| 2 | `patterns_shapes.py:451` / `:653` | published | named both functions and the file |
| 3 | `patterns_shapes.py:596` / `:776` | published | named both functions |
| 4 | `dependence.py:238` / `models.py:54` | **dropped** | hedged: `likely` |
| 5 | `evidence_provider.py:195` / `market_brief.py:170` | published | named both helpers and both files |
| 6 | `patterns.py:334` / `patterns_shapes.py:477` | published | named the function and both files |
| 7 | `patterns_shapes.py:435` / `:633` | published | named both functions |
| 8 | `patterns_shapes.py:576` / `:759` | published | named both functions with line ranges |
| 9 | `natural_null.py:28` / `prospective.py:317` | **dropped** | hedged: `likely` |
| 10 | `service.py:123` / `:147` | **dropped** | hedged: `likely` |

**Nothing failed to be stopped, so nothing was repaired.** The owner's instruction was to fix
whatever the adjudicator could not hold; it held on all ten.

## 2. A blind spot was closed anyway, and this report does not call that a catch

A denylist stops a hedge. It cannot stop *"These two functions do exactly the same work, so one
of them is dead weight and should be deleted."* — no banned phrase, no place to look, and green's
entire claim is that a reader can go and see it. `describe` now also refuses prose that names
**no coordinate**: neither path, neither base name, neither function name.

Run 2 is that rule measured: **it never fired on ten further calls.** Across 20 model calls the
coordinate requirement has cost nothing observable and caught nothing. It is a guard against a
sentence this model did not write, on n = 20. The run-to-run difference in hedging (3 dropped,
then 6) is the model's own variance, not the rule's.

## 3. The channel

- **At most two green notes per pull request** (`MAX_STRUCTURAL_COMMENTS = 2`).
- **Marked `structural`.** Each inline comment opens `Structural (no defect claimed):`, carries
  `<!-- attest:structural:attest.structural.duplicate-implementation.v1 -->`, and says
  `Category: structural. This is a measurement over the two coordinates above, not a
  reproduction: no test was generated and no receipt backs it.`
- **Partitioned from red.** The summary renders green under its own heading — *"Structural
  observations — measured, not reproduced; no defect is claimed"* — after the red section,
  which is untouched. Green never uses "verified", "finding" or "receipt".
- **The wording states only coordinates and the measure.** The claim line is
  `evidence_sentence`, which is deterministic and every clause of which is a path, a line range,
  a token count or a similarity. **The model's paragraph is a separate labelled "Suggested fix"**
  and `StructuralNote` holds the two in separate fields, so dropping the advice never changes
  what is claimed.

## 4. Limits

- **Green is measured, not reproduced, and claims no defect.** Duplication is a property of the
  code, not of the commit; the `G-NULL-001a` nulls speak at 22.4% and that is not an error rate
  (D-130).
- **n = 20 model calls, one model, one class, one prompt.** A different model, a longer prompt,
  or a finding with no obvious fix could all produce coordinate-free prose that this run did not.
- **The denylist is a denylist**, English and Chinese, and a hedge phrased outside it passes.
- **The wiring is new and its blast radius is deliberately zero.** `run_ci` computes green after
  every receipt decision is made; any exception in that path yields no notes; the model call is
  reserved and settled against the review's own budget under `structural-wording`; the drift
  guard now covers a green-only run. Nothing about red changed, and the RED for the wiring is
  `tests/test_ci_flow.py::test_a_duplicated_implementation_reaches_the_author_as_a_structural_comment`.
