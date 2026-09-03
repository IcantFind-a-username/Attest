# The self-containment gate, measured: three receipts, one of them on real traffic

Owner instructions 1 and 6 of 2026-09-03f. Product code at `2bba19a` (D-114 the
self-contained reproduction and its collection gate, D-115 the generation model,
D-117 the plan order). **Every row names both models and says whether the budget
was the product default.**

## 1. The three runs

| # | case | pair (head → base) | proposals | reproduction | `--budget` | backend | units | cand. | eligible | **certified** | **published** | spend |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Attest PR #8 | `445c5a1` → `e0867eb` | `claude-sonnet-5` | `claude-opus-5` | **0.60 (not the default 0.25)** | `local_development_best_effort` | 1 | 1 | 1 | **1** | **1** | $0.033891 |
| 2 | `pytest-dev__pytest-10051` | SWE-bench pair | `claude-sonnet-5` | `claude-opus-5` | **0.60 (not the default)** | `linux-container-v1` | 1 | 1 | 1 | **1** | **1** | $0.051904 |
| 3 | `us-stock-helper` receipt pilot | `d7be758` → `8ed7811` | `claude-sonnet-5` | `claude-opus-5` | **0.60 (not the default)** | `linux-container-v1` | 3 of 3 | 12 | 9 | **1** | 0 — below the family threshold | $0.437427 |

A fourth charge belongs to row 1: an earlier attempt at the same pair spent
**$0.019138** on its proposal stage and was then killed at 10 minutes while
`docker build` waited on a `python:3.13-slim` pull this host cannot complete.
Nothing was certified on that attempt; the proposals it bought were replayed
from the attempt cache by the run in row 1, which is why row 1's own proposal
cost is small. Window spend for all four: **$0.542360**.

Row 3 is the headline: **the first receipt this product has ever produced on
real third-party traffic** — real repository, real fix, containerised
reproduction, sealed bundle, offline verifier accepted. It was **not published**;
§3 says why, and that is not a defect.

## 2. Rows 1 and 2 are the two cases D-114 was written for

Both had failed under both models before this change, and both failed for
scaffolding rather than for judgement about the diff.

| case | before (2026-09-03e) | after (this run) |
|---|---|---|
| Attest PR #8 | sonnet: `NameError: TruthDefect is not defined` — the file had **no import statement at all**. opus: `ModuleNotFoundError: test_matcher` at collection — it imported a helper from the repository's own `tests/` | **head FAIL 3/3, base PASS 3/3, certified, published.** The generated file imports what it uses: `from attest.benchmark.matcher import MatchResult, match_findings` and `from attest.benchmark.schema import Placement, Prediction, TruthDefect` |
| `pytest-10051` | sonnet: `assert 0 == 1` on both sides — it logged at INFO without `caplog.set_level`, so the precondition failed and the anchored `clear()` was never reached | **head FAIL 3/3, base PASS 3/3, certified, published.** The generated test opens with `caplog.set_level(logging.INFO)` |

Both fixes are the two clauses the prompt gained. The third clause — the static
rejection of a test-module import — did not have to fire on either case; the
generator did not attempt one.

Row 2 also costs less than the same case did last window under a single-model
opus review: **$0.0519 against $0.1931**, because proposals stayed on the
default model. It produced one candidate rather than two.

## 3. Row 3: a receipt, and the family policy holding

```text
verification 58a3076775  reproduced  head FAIL 3/3, base PASS 3/3
certification 58a3076775 accepted    receipt c229fb6992bb…  bundle e6626dc16283…
                                     executor_profile linux-container-v1
publication_policy       e-value Bonferroni; eligible 9; family threshold 90.0;
                         mean e-value 8.688593; published []; suppressed
                         [58a3076775: below family threshold]
```

`attest verify --bundle … --require-seal` accepted it in place: *accepted:
receipt c229fb69… for 58a3076775 (linux-container-v1); seal verified*. The
bundle stays in the run's own gitignored worktree
(`.attest/pilot-d116/head/.attest/evidence/20260903-170105-9b14404e/58a3076775`)
rather than being copied into this repository.

**Why nothing was published.** Twelve candidates, nine of them regression
eligible, so the C-05 family threshold is `m/α = 9/0.1 = 90` and the one
certified finding's e-value is below it. This is the multiplicity policy the
owner selected doing exactly what it is for: a nine-candidate family does not
publish on one receipt. The silence is documented and the receipt is on file.

**What the receipt actually says, and why it is the weakest kind.** The certified
claim is `scoring.py:167` — `method_version` reads `"…-v1"` on head where the
repaired revision discloses `"…-v2"` — and the generated test asserts exactly
that string:

```python
result = score_horizon(features)
assert result.method_version == "explainable-horizon-score-v2"
```

That is a true differential (it fails on head 3/3, passes on base 3/3, and the
asserted line is inside the diff) and it is **an assertion about a disclosed
version string, not about the behaviour the fix repaired**. It is close to the
shape V-02 exists to exclude — a test that branches on source version — and it
passed the binding check because the version literal is itself on a changed
line. Owner item 1 below.

**The regression the pair was chosen for was not certified.** The two candidates
that named it (`cd6f06774e`, `8fe277af3e` — a confirmed pattern keeps voting
after its neckline is lost) both produced tests that **fail on base as well**;
six more eligible candidates never generated a test at all, each stopping at
`BudgetExceeded` on the second generation attempt (`… projected total $0.67
exceeds budget $0.60`). Breadth, again: 12 candidates from a 274-line reverted
fix.

## 4. The pair, and the free check that qualified it

D-116: head = the repairing commit's parent, base = the repairing commit, and a
pair counts only if the fix's own human-written tests discriminate it. Run
before any paid call, no model and no spend, on `python 3.12.2` with
`PYTHONPATH=.` inside `services/analysis_core`:

| side | `tests/test_scoring.py -k PatternFactorInForce` |
|---|---|
| head `d7be758` | **4 failed, 1 passed** |
| base `8ed7811` | **5 passed** |

The pair discriminates. The D-109 selection, which reviewed `d7be758` against
*its own parent*, was reviewing a pair with nothing in it.

## 5. What these three runs do not establish

- **n = 3, one run each.** Three certifications are not a rate, and two of the
  three cases were chosen precisely because they had failed before.
- **No run used the product's default budget.** All three ran at `--budget 0.60`.
  At the shipped $0.25 the reproduction stage reserves two generation attempts at
  the generation model's price — roughly $0.09 each on these prompts — so a
  review that spends much on discovery may not be able to afford one. Row 3
  exhausted $0.60 with six reproductions unattempted. The default is unchanged
  by owner instruction; this is what it now buys.
- **Row 1 ran on the host adapter,** not in a container: this machine's docker
  still cannot pull `python:3.13-slim`, and a probe started for this run returned
  nothing in 75 s. Rows 1 and 2 are therefore not backend-comparable.
- **Row 3 published nothing,** so the receipt-backed *comment* branch of the L-01
  step-16 exit is still unexercised on real traffic. What is now exercised is the
  receipt.
- **The static test-module rejection is unexercised on real traffic.** It has a
  RED and it never fired in these three runs.
