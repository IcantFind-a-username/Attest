# `attest.intent.v3` replayed over every receipt the corpus holds (D-128)

**Owner instruction 2 of 2026-09-04c.** Driver
[`scripts/corpus/intent_v3_replay.py`](../../scripts/corpus/intent_v3_replay.py), data
[`2026-09-04-intent-v3-replay.json`](evidence/2026-09-04-intent-v3-replay.json).
**Cost $0.00** — no model call, no execution, no repository write. Two worktrees per recorded
revision pair, the generated test out of each bundle, the head failure messages out of each
bundle's JUnit, and the observer run twice.

**The headline is the recall cost, and it is large: 55 certified receipts become 19.** The rule
is the owner's, unmodified; nothing here was relaxed to make the number smaller.

## 1. What was replayed, and what the old side is

Every `verification` row across the four working clones and the four `G-NULL-001a` control
clones whose outcome was `reproduced` and whose evidence bundle is on this host: **55 of 59**.
The four that are not replayed are two `us-stock-helper` tasks whose observer inputs are no
longer on this host; they are listed in the data as `skipped` and counted nowhere.

Both sides come from **the same code path on the same bytes**. The old side is the observation
re-derived and then stamped `attest.intent.v2`, so D-127's four fields are not part of the
policy it is judged under; the new side is the same observation under `attest.intent.v3`. Raise
origins cannot be replayed from a bundle, so a receipt the run recorded as a **new rejection**
carries its recorded rejection fields across to both sides — the value rule never applies to
one, and 2 of the 55 are of that shape.

The old side agrees with the class each run recorded on **55 of 55**.

## 2. Receipts: 55 → 19

| shape of the head failure | receipts | certify under v2 | certify under v3 |
|---|---|---|---|
| **value mismatch** (the test's own assertion failed) | 46 | 46 | **10** |
| crash (the code raised) | 7 | 7 | 7 |
| new rejection (D-102) | 2 | 2 | 2 |
| constant substitution (D-120) | 0 | — | — |
| **total** | **55** | **55** | **19** |

**36 receipts move to the drawer — 65% of everything this corpus ever certified.** The value
class is where the product lives: 46 of 55 receipts, 84%.

Why each of the 36 stops:

| the drawer's reason | receipts |
|---|---|
| the base tree does not specify the value the assertion pins | 19 |
| the assertion pins no value at all (it compares against a name or a call) | 16 |
| this change rewrites the base tree's own specification of that value | 1 |

The **16 that pin nothing** are the shape worth reading twice. `assert mod.add(*_pair()) ==
EXPECTED` compares against a name the project's own test module defines — which is a *stronger*
statement of the old value than a literal, and v3 cannot see it, because resolving a name to a
value is not a file read. That is a known, stated limit of this design and not an accident of
the corpus.

## 3. The ten that survive, and how thin four of them are

| clone | anchored file | what the assertion pins | where the base tree says it |
|---|---|---|---|
| `attest` | `execution/container_images.py` | `'timed out'` | `tests/test_ci_flow.py` |
| `attest` | `scripts/corpus/heldout_run.py` | `None`, `0` | `tests/test_action_entrypoint.py` |
| `attest` | `scripts/corpus/swebench_pilot.py` | `None`, `True`, `0`, `'claude-opus-5'` | `DEVSPEND.md`, two test modules |
| `corum` ×3 | `src/corum/models.py` | `'Reviewer.cost'` | `AGENTS.md` |
| `corum` | `src/corum/models.py` | `2` | `tests/test_calibration.py` |
| `us-stock-helper` | `market_gateway/opend_adapter.py` | `'US.NVDA'` | `services/market_gateway/README.md` |
| `us-stock-helper` ×2 | `information_layer/factors/unsupported.py` | `None` | `deploy/tests/test_deployment_configuration.py` |

**Four of the ten rest only on generic constants** — `None`, `0`, `2`, `True`. A generic
constant is asserted somewhere in almost any tree, so for those four the "specification" the
receipt contradicts is a coincidence of vocabulary rather than a statement about this function.
**v3's protection is weakest exactly where the pinned value is generic**, and that is the first
thing to fix if the owner wants the rule narrower. It is reported here rather than fixed,
because narrowing it is another move of what publishes.

> **This prediction was confirmed the same night, on a live control.** The resumed
> `G-NULL-001a` run published `urllib3 c7b9adcb` under v3 on a pinned set of exactly `["False"]`
> (D-131, [report](2026-09-04-g-null-001a-resumed.md)). Read this paragraph as an observation,
> not a caveat.

## 4. The control condition: `jinja ac3ac6c9` is drawered, and no control certifies

Both `ac3ac6c9` receipts — the one that published and its sibling — go to the drawer for the
same reason: **the base tree states neither name the reproductions assert**.

```
pinned  'True', 'from_normal', 'normal_func'      specified  (nothing)
verdict value change confirmed, intent unknown: the base tree does not specify the value
        this assertion pins (返回值变化已证实，意图未知)
```

Under `attest.intent.v2` the same observation on the same bytes yields `regression_reproduced`
and **no verdict at all** — which is how it published. **Control receipts certifying: 2 → 0.
Control publications: 1 → 0.**

## 5. Publications: 27 → 14 over 125 reviews

Every review with a `publication_policy` row, replayed through the real selector under the
family policy in force (D-125, per change unit): **123 reviews in the four working clones and 2
in the control clones**.

|  | reviews | publications |
|---|---|---|
| under `attest.intent.v2` | 125 | **27** |
| under `attest.intent.v3` | 125 | **14** |
| of which controls | 2 | **1 → 0** |

**11 reviews change.** The replay is checked against the ledger where the ledger is comparable:
**59 of the 125 rows were written under publication-policy `v2` (D-125's rule), and the old
replay reproduces all 59.** The other 66 predate D-125 and were written under the PR-wide
family, so today's policy is not expected to reproduce them and they are not used as a check;
they are still counted on both sides, which is an apples-to-apples D-127 comparison.

The recorded total across all 125 rows is 22, against the old replay's 27; the gap is entirely
the D-125 family change on pre-D-125 rows and is [already on the record](2026-09-04-family-per-change-unit.md).

## 6. Read D-125 and D-128 together, because they point opposite ways

D-125 took publications from 12 to 24 on this corpus. D-128 takes them from 27 to 14. **The net
of the two, against the pre-D-125 product, is roughly where the product started** — but not the
same fourteen findings, and with one difference that is the whole point: the control that
published no longer does.

## 7. Limits

- **This is a replay, not a run.** No reproduction was regenerated and no test was executed;
  the observation is recomputed from bytes that already exist. A product running under v3 from
  the start would generate different reproductions, because the generator is not told about the
  rule.
- **The 46 value-class receipts are not adjudicated.** "Certifies under v2 and not under v3"
  says nothing about which of them were real defects. On this corpus we know only one label for
  certain — `jinja ac3ac6c9` is wrong — and v3 gets that one right.
- **Four of the surviving ten are thin** (§3), so "10 survive" overstates how many rest on a
  specification that is actually about the function under test.
- **Two clones contribute 46 of 55 receipts** (`attest` 20, `us-stock-helper` 26), and three of
  the surviving ten are in `Attest`'s own repository — the standing disclosed conflict.
