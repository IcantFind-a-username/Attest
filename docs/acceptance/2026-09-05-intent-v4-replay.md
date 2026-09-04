# `attest.intent.v4` replayed beside v2 and v3, on every receipt the corpus holds (D-132)

**Owner instruction 1 of 2026-09-05.** Driver
[`scripts/corpus/intent_v4_replay.py`](../../scripts/corpus/intent_v4_replay.py), data
[`2026-09-05-intent-v4-replay.json`](evidence/2026-09-05-intent-v4-replay.json).
**Cost $0.00** — no model call, no execution, no repository write. Two worktrees per recorded
revision pair, the generated test out of each bundle, each head run's JUnit **message and
longrepr**, the diff's file list from `git diff --name-only`, and one observation read under
three rules.

**The headline is not the control column, which is what the rule was asked for. It is the value
column: 48 → 12 → 0.** On this corpus v4 certifies nothing at all in the class the product
lives in.

## 1. What was replayed

Every `verification` row that reproduced and whose evidence bundle is on this host, across the
four working clones and **all eight `G-NULL-001a` control clones this host holds a ledger for**
— `urllib3` included, because it is the control v4 exists to stop. **57 of 61**; the four not
replayed are `us-stock-helper` tasks whose observer inputs are no longer here, listed in the
data as `skipped` and counted nowhere.

All three columns come from **one observation over one set of bytes**, differing only by the
rule applied. The v3 column recomputes its own `pinned_values` with `assertion_pinned_values`
— v3's set was every `assert` in the reproduction and v4's is the failing one's — so the
columns differ by the rules and never by the inputs. Raise origins cannot be replayed from a
bundle, so a receipt the run recorded as a **new rejection** carries its recorded rejection
fields into every column; 2 of the 57 are of that shape and no value rule reaches them.

**The v2 column agrees with the class each run recorded on 57 of 57**, and reproduces the
ledger on **69 of the 69** publication rows written under today's family rule (D-125).

## 2. Receipts: 57 → 21 → 9

| shape of the head failure | receipts | v2 | v3 | **v4** |
|---|---|---|---|---|
| **value mismatch** (the test's own assertion failed) | 48 | 48 | 12 | **0** |
| crash (the code raised) | 7 | 7 | 7 | **7** |
| new rejection (D-102) | 2 | 2 | 2 | **2** |
| constant substitution (D-120) | 0 | — | — | — |
| **total** | **57** | **57** | **21** | **9** |

Why each of the 48 value receipts stops under v4, in the order the rule asks:

| the drawer's reason | receipts |
|---|---|
| this change rewrites the base tree's own specification of that value | 1 |
| **intent stated in the change itself** (clause c) | 39 |
| the failing assertion pins no value at all (clause a) | 6 |
| the failing assertion pins only a generic constant (clause b) | 0 |
| **certifies** | **0** |

## 3. Each clause on its own, over the 48 value receipts

Asked independently — *would this clause drawer a receipt the other two let through?*

| clause | drawers | of the 12 v3 certified |
|---|---|---|
| **(a)** the pinned set is the failing assertion's | 32 | 12 |
| **(b)** a generic constant is not a specification | 2 | 0 |
| **(c)** the diff states its own intent | 42 | 8 |

**(a) alone accounts for all twelve v3 survivors**, because on this corpus the failing frame is
usually not an `assert` at all: a `with pytest.raises(...)` that did not raise, a stub the test
defines and raises from, a helper. **(b) does no work here once (a) is in place** — the pinned
set is empty before genericity can be asked. Its case is `urllib3 c7b9adcb` under *v3's* pinned
set of `["False"]`, which is a counterfactual on this data and a unit test
(`test_a_pinned_set_of_only_generic_constants_goes_to_the_drawer`) rather than a corpus row.
**(c) is the broadest**: 42 of 48 real diffs say somewhere what they meant.

## 4. The control condition: 2 → 1 → 0

| control | v2 | v3 | v4 | what stops it under v4 |
|---|---|---|---|---|
| `jinja ac3ac6c9` ×2 | certifies | drawer | **drawer** | (a) and (c), independently |
| `urllib3 c7b9adcb` ×2 | certifies | **certifies** | **drawer** | (a) and (c), independently |

**Control publications: 2 → 1 → 0.** `urllib3` is the receipt D-131 stopped the run over: v3
read `pinned_values: ["False"]` off an assertion that never executed and found `is False`
somewhere in urllib3's tests. Under v4 the longrepr's innermost frame is
`test_repro.py:43`, a bare `raise AssertionError` inside a stub the reproduction defines, so
the failing assertion pins nothing; and independently, the diff rewrites the comment directly
above the condition it widens, inside `_make_request`, which is intent evidence in the anchored
file itself.

## 5. Publications: 28 → 15 → 6 over 135 reviews

|  | reviews | publications | of which controls |
|---|---|---|---|
| under `attest.intent.v2` | 135 | **28** | 2 |
| under `attest.intent.v3` | 135 | **15** | 1 |
| under **`attest.intent.v4`** | 135 | **6** | **0** |

Seven reviews change between v3 and v4. The six that still publish are the crash and rejection
classes; **no value regression publishes anywhere in this corpus under v4.**

## 6. Read this next to D-128, because the direction is the same and the size is not

D-125 took publications from 12 to 24. D-128 took them from 27 to 14. D-132 takes them from 15
to 6. Against the pre-D-125 product the net is now clearly **below** where it started, and the
class that fell is the one that carried the product. The two control publications this project
has ever made are both stopped; so is everything else in that class.

## 6b. Clause (a) is proved against real pytest output, not only against the replay

The replay reads longreprs out of recorded bundles. The end-to-end proof that clause (a) finds
the right assertion in *live* output is this repository's own comparison fixture
(`tests/benchmark/test_baselines.py`): a real `pytest` run, a real JUnit file, a reproduction
whose assertion is `runpy.run_path('calc.py')['value']() == 7`. Under v4 the product arm still
certifies it — the longrepr's innermost frame is that assert, the pinned value is `7`, and the
base tree's `test_calc.py` states it.

**And the same fixture is where v4's cost first showed up.** It pinned `1` before this window,
which clause (b) makes generic; the arm stopped certifying and the fixture — not the rule — was
changed to state `7`. Two more followed: `tests/benchmark/test_corpus.py`'s oracle fixture, and
the **M-01 offline measurement probe**, whose frozen cassette pins `1`. That one needed a new
frozen artifact rather than an edit: `benchmarks/attest-v2/cassettes-m01-v2/m01-mixed-5-v2.json`,
the same cassette with `3 → 7`, restores the probe's measurement exactly (`published_count == 1`,
baseline `(5, 4, 1)`), and `m01-mixed-5-v1.json` is kept unmodified beside it. **Three fixtures
in this repository stopped certifying the moment (b) landed. That is the clearest available
statement of how much of the value class rested on `0` and `1`.**

## 7. Limits — read every one of them

- **This is a replay, not a run.** Nothing was regenerated and nothing was executed. A product
  running under v4 from the start would generate different reproductions, because the generator
  is not told about the rule — and clause (a) is precisely a rule about *where the reproduction
  fails*, which a generator could be told to control.
- **Clause (c) matches a symbol name as a word, and common names collide.** Spot-checking the
  42: `geopolitics_reading` named in the test the same diff deletes is intent; `readings`
  matched in another module's rewritten docstring, `decision` in an unrelated function's prose,
  `_reason`, `snapshot`, `main` — these are vocabulary, not intent. **An unknown fraction of the
  42 is false.** The rule is the one instructed and over-drawering is the safe direction, so it
  is reported rather than tuned; narrowing it is the owner's.
- **"Certifies under v3 and not under v4" says nothing about which were real defects.** Only two
  labels on this corpus are certain — `jinja` and `urllib3` are wrong — and v4 gets both right.
  The 12 it takes away from v3 are unadjudicated.
- **0 in the value class is a corpus fact, not a theorem.** The publishing branch exists and is
  tested (`test_a_specified_value_with_no_intent_evidence_in_the_diff_publishes`); no real
  receipt here reaches it.
- **Two clones contribute most of the receipts** and three of `Attest`'s own repository's rows
  are in the population — the standing disclosed conflict.
- The population grew by two receipts and eight reviews since D-128's replay, because more
  controls ran; the v2 and v3 columns here are therefore not identical to D-128's numbers and
  are not meant to be.
