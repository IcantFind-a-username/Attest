# Why generated reproductions do not discriminate: the corrected population, and the two real failures

Owner instruction 1 of 2026-09-03e: correct the §5 population before measuring generation,
classify what is left, and record whether the failure changes with the model. **No product
code was changed for this measurement** (the two product changes in this window are D-110 and
D-111, which the owner ordered separately).

**Every table names the model.** The runner review of PR #8 and the `pytest-10051` rerun both
ran `claude-sonnet-5`, the product default in `src/attest/data/pricing.toml`.

## 1. The population was wrong: `d7be758` had no regression to find

Method (no model call, no spend): for each reviewed pair, take the **human-written tests the
repairing commit ships**, copy that file into a worktree of the reviewed commit and of its
parent, and run only the tests the fix added, on both sides. Interpreter: `python 3.12.2`;
`services/analysis_core` declares no dependencies, so `PYTHONPATH=.` is the whole environment.

| pair | fix commit's tests | head (the reviewed commit) | base (its parent) | discriminates? |
|---|---|---|---|---|
| `d7be758` / `375ab52` | `2d4a0d8` → `Ma5PullbackTests::test_forming_invalidation_copy_describes_the_daily_rule` | **FAIL** | **FAIL** (identical assertion, identical text) | **no** |
| `e17c686` / `8d2257a` | `8ed7811` → `PatternFactorInForceTests` (5 tests) | 4 FAIL / 1 PASS | 2 FAIL / 3 PASS | **yes — 3 of 5** |

### `d7be758`: no regression, correct silence

The fix's own test fails **the same way on both sides**, so the defect `2d4a0d8` repaired was
already present at the parent. `git log -S` and `git blame` say where it came from: the wrong
copy was introduced by **`e17c686`**, and all `d7be758` did to that line was rewrite
`touch_ma5` as `ma5[touch_index]` — a refactor that preserved the (already wrong) semantics.

The D-109 selection blamed the lines the fix *removed* at the fix's parent, which returns the
last commit to **touch** a line, not the commit that **introduced the defect**. That is the
population defect. Both reproductions Attest executed on this pair ran against a pair with
nothing to certify, and both reported `pytest passed on head in 3/3 runs` — **the correct
answer**. Two of the six rows in the old §5 table are therefore not generation failures at all.

### `e17c686`: a real regression, and Attest missed it — at discovery, not at generation

Three of the fix's five tests pass on the parent and fail on the reviewed commit:
`test_a_confirmed_pattern_stops_voting_once_its_neckline_is_lost`,
`test_a_confirmed_ma5_pullback_stops_voting_below_the_average`,
`test_equal_magnitude_votes_prefer_the_latest_signal`. (One more fails on base only, and one
fails on both because it pins the fix's own `method_version` bump.) The pair really does
regress.

Attest's single candidate on that pair was **not about it**: it claimed `__init__.py:80` might
raise `ImportError`. The run status says why — `read 2 of 4 units, budget-limited`, and the two
units it never read are `us_stock_helper_core/patterns_shapes.py` and
`us_stock_helper_core/scoring.py`, **the two files that carry the regression**. The generated
test then passed on head, which is the right verdict for a claim that is not a defect.

So this row is a **missed defect at discovery under a budget stop**, not a generation failure.
It is the case D-111 was written for, and D-111 makes it *worse*, not better: bounding breadth
buys reproduction depth by giving up unit coverage. That trade is the owner's, and it is now
explicit.

### The corrected §5 table

| population | model | executed | verdict | after this correction |
|---|---|---|---|---|
| receipt pilot `d7be758` ×2 | `claude-sonnet-5` | 2 | `pytest passed on head in 3/3 runs` | **no regression in the pair — correct silence** |
| receipt pilot `e17c686` ×1 | `claude-sonnet-5` | 1 | `pytest passed on head in 3/3 runs` | **regression real but never proposed** (its units were budget-omitted); the verdict on the claim that *was* proposed is correct |
| 2026-09-03c pilot `f58bf64` ×1 | `claude-sonnet-5` | 1 | `references a symbol absent from head` | no regression in the pair ([report](2026-09-03-l01-private-pilot.md): none of the six commits regressed against its parent) — correct silence |
| **runner review PR #8** | `claude-sonnet-5` | 1 | `fails on base as well` | **real failure** |
| **`pytest-dev__pytest-10051`** | `claude-sonnet-5` | 1 | `fails on base as well` | **real failure** |

**"Six of six" was not a measurement of generation.** Four of the six ran against pairs where
either no regression existed or none was proposed. The generation question stands on **two**
cases, and n = 2 supports no rate at all.

## 2. The two real failures, classified

Both generated tests, exported verbatim from the run artifacts, with the base-side output.

| # | case | model | backend | failure text | **class** |
|---|---|---|---|---|---|
| 1 | Attest PR #8 (`445c5a1` over `e0867eb`) | `claude-sonnet-5` | `linux-container-v1` (GitHub runner) | `NameError: name 'TruthDefect' is not defined` — identical on head and base | **environment / import error** |
| 2 | `pytest-dev__pytest-10051` | `claude-sonnet-5` | `linux-container-v1` (host) | `assert 0 == 1 where 0 = len([])` — identical on head and base | **asserted behaviour the base does not have either** |

Neither is "depends on a symbol only head has": that class is real (the 2026-09-03c pilot) but
does not appear among the two survivors.

### Case 1 — the test has no imports at all

The traceback's line numbers are the whole story: `def` on line 1, a three-line docstring, and
the first statement — `truth = TruthDefect(...)` — on **line 5**. There is no import
statement in the file. The product code was never reached, on either side; `fails on base as
well` is technically true and diagnostically empty.

### Case 2 — the discriminating half of the test never runs

```python
import logging


def test_caplog_clear_preserves_records_list_alias(caplog):
    records_ref = caplog.records
    logging.getLogger(__name__).info("hello")
    assert len(records_ref) == 1     # <- fails identically on head and base

    caplog.clear()
    assert records_ref is caplog.records
    assert len(records_ref) == 0
```

The candidate was **right**: it anchors `LogCaptureFixture.clear` (eligibility:
`definition LogCaptureFixture.clear exists at the merge-base`) and its falsification plan says
to take `handler = caplog.handler; records_ref = handler.records`, log, clear, and check the
alias. The generated test then drifted from its own plan — it aliased `caplog.records` instead
of `caplog.handler.records` and, fatally, logged at `INFO` without `caplog.set_level`, so
nothing was captured and the **precondition** failed on both sides. `caplog.clear()`, the
anchored call, is never executed on either side.

The shape of both failures is the same: **the generated test's scaffolding is wrong, so the
diff is never exercised**. Neither is evidence that a faithful test is hard to write for these
defects.

## 3. The same two cases with `claude-opus-5`, K=4

Owner instruction 1c. Reservation written before the first call; `--budget` 0.60 per review
because at opus prices four samples estimate $0.3517, which does not fit the 60% discovery
share of a $0.50 budget — the first attempt DEFERred on exactly that and spent **$0.00**.

| case | model | backend | candidates | eligible | reproductions | **certified** | published | spend |
|---|---|---|---|---|---|---|---|---|
| `pytest-dev__pytest-10051` | **`claude-opus-5`** | `linux-container-v1` | 2 | 2 | 2 | **2** | **2** | $0.193112 |
| `pytest-dev__pytest-10051` | `claude-sonnet-5` | `linux-container-v1` | 1 | 1 | 1 | 0 | 0 | $0.019502 |
| Attest PR #8 pair | **`claude-opus-5`** | `local_development_best_effort` | 1 | 1 | 1 | 0 | 0 | $0.079220 |
| Attest PR #8 pair | `claude-sonnet-5` | `linux-container-v1` (runner) | 1 | 1 | 1 | 0 | 0 | $0.030100 |

**`pytest-10051` certified.** Two receipts, head FAIL 3/3 and base PASS 3/3, both sealed
bundles, published through the ordinary family policy — the first receipt-backed publication
this case has ever produced. One of the two generated tests drives the defect through
`pytest`'s own `Pytester`:

```python
def test_caplog_clear_preserves_records_alias(pytester: Pytester) -> None:
    pytester.makepyfile(test_alias="""
        import logging
        def test_alias(caplog):
            logging.getLogger().warning("before")
            records = caplog.records
            assert [r.getMessage() for r in records] == ["before"]
            caplog.clear()
            assert records == []
            ...
    """)
    result = pytester.runpytest()
    result.assert_outcomes(passed=1)
```

It logs at `WARNING` (captured by default), takes the alias, calls `clear()`, and asserts on
the alias — the plan the sonnet test was given and did not follow.

**The Attest pair still fails, and still on scaffolding**, but differently: opus imports
`from test_matcher import _prediction, _truth`, a helper module in the repository's own
`tests/` directory that is not importable from `.attest-repro/`, so the run DEFERs at
`collection deferred: … (exit code 2)` with `ModuleNotFoundError: No module named
'test_matcher'`. Same class as before (**environment / import error**), a different mistake
inside it. Caveat: this run used the host adapter, because this machine's docker cannot pull
`python:3.13-slim`; the import failure is a property of the generated file, not of the backend.

## 4. What this changes

- **Generation is model-sensitive, not stage-broken.** On the one case where a real regression,
  a correct candidate and a working environment all lined up, changing only the model turned
  0 receipts into 2.
- **The remaining failure mode is scaffolding**, three for three across both models on the two
  real cases: no imports, a non-importable import, a missing `caplog.set_level`. The
  reproduction prompt is where that is fixed — the generated file must be self-contained and
  must exercise the anchored call.
- **The opus import failure is D-089 working, half way.** That decision put the nearest test
  module's imports, fixtures and helpers into the generation context precisely because the
  generator was inventing constructor arguments and package paths ("six of six haiku
  reproductions … guessed"). Opus used what it was shown — `_prediction` and `_truth` are real
  helpers in `tests/benchmark/test_matcher.py` — and then `import`ed them, which cannot work
  from `.attest-repro/`. The context says *these helpers exist*; nothing says *your file must
  stand alone*. That sentence is the smallest next product change, and this window did not make
  it (instruction 1d: no product code).
- **n = 2, one run each.** Nothing here is a rate. The opus result is a single run whose
  proposal samples were bought once; a repeat would replay from the attempt cache and prove
  only determinism.

## 5. Limits

- Human tests were run on the host, not in a container; `analysis_core` has no dependencies, so
  the environment is the interpreter alone.
- The `d7be758` correction rests on the fix's *own* test. A different test could in principle
  discriminate that pair; none is claimed to exist.
- The PR #8 opus run is not backend-comparable to the runner run (host adapter vs container).
- Both opus runs used `--budget 0.60`; the sonnet runs used $0.25. Budget is not held constant
  across the model comparison, and a larger budget cannot by itself make a test faithful.
