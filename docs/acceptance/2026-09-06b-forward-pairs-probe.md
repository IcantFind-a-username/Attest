# The same 11 forward pairs, under a generator that records instead of asserting — 2026-09-06b

Owner instruction 3 of this window: **change reproduction generation to probe + record/replay**,
and re-run the 11 forward pairs, giving old and new columns for *unfaithful*, *certified* and
*published*. The intent discriminator is `attest.intent.v4.1` and is **unchanged**; the only
thing that moved is how a test gets written.

**Reservation $11.00 (11 reviews × the `--budget 1.00` ceiling), spent $4.0611 over two runs.**
Driver: [`scripts/corpus/forward_pair_reviews.py`](../../scripts/corpus/forward_pair_reviews.py).
[Pairs](../corpus/forward-pairs.md) · [data](evidence/2026-09-06b-forward-pairs-probe.json) ·
old column recomputed from [D-140's recorded data](evidence/2026-09-05d-forward-pair-reviews.json).

## 1. What changed in the generator (D-146)

D-140 measured the wall: **20 of 31 answered candidates** ended as `unfaithful generated test:
fails on base as well`, and [the classification](2026-09-06-forward-pair-generation-failures.md)
found **0 environment failures** and **18 tests asserting a behaviour the base revision does not
have either**. The model was being asked something a forward diff cannot tell it — *what did the
code do before?*

So it is no longer asked:

| | who decides |
|---|---|
| **what to call** — imports, setup, one expression, no expectation | the model |
| **what that call does** | the merge base, executed |
| **the assertion** | the kernel, from the recording |

Two structural guards decide whether a recording is admissible, and both refuse **before** any
head run is bought: the probe must **execute the anchored file on base** (a probe that never
enters the code under review recorded something else), and the observation must be **identical
across three executions** (D-148). The generated test still goes into the evidence bundle and
still verifies offline — §5.

## 2. The two columns

**Old** is D-140's run under the legacy generator. **New** is this window's second run, under
`attest.probe.record-replay.v1` with `PROBE_RECORDINGS = 3`.

| # | repo | head | candidates | answered about the code | **unfaithful** | probe-refused | certified | published |
|---|---|---|---|---|---|---|---|---|
| 1 | `attrs` | `e048efcb39` | 2 → 2 | 0 → 0 | 0 → 0 | 0 | 0 → 0 | 0 → 0 |
| 2 | `attrs` | `7c85d68de2` | 1 → 1 | 1 → 1 | 0 → 0 | 0 | 0 → 0 | 0 → 0 |
| 3 | `click` | `0585f456ba` | 10 → 10 | 9 → 9 | **6 → 0** | 2 | 0 → 0 | 0 → 0 |
| 4 | `click` | `cd4674a6de` | 42 → 93 | 4 → 20 | **2 → 0** | 4 | 0 → **1** | 0 → **1** |
| 5 | `click` | `19fd4d6e18` | 7 → 7 | 7 → 7 | **7 → 0** | 0 | 0 → 0 | 0 → 0 |
| 6 | `itsdangerous` | `3703fbdedd` | 7 → 7 | 5 → 5 | **4 → 0** | 0 | 1 → 1 | 1 → 1 |
| 7 | `more-itertools` | `d63a26e56e` | 1 → 1 | 1 → 1 | 0 → 0 | 0 | 0 → 0 | 0 → 0 |
| 8 | `more-itertools` | `2deea20ead` | 1 → 1 | 1 → 1 | 0 → 0 | **1** | **1 → 0** | **1 → 0** |
| 9 | `more-itertools` | `71b76842d3` | 1 → 1 | 1 → 1 | 0 → 0 | 0 | 1 → 1 | 1 → 1 |
| 10 | `more-itertools` | `390a3db74c` | 2 → 2 | 2 → 2 | **1 → 0** | 0 | 0 → 0 | 0 → 0 |
| 11 | `packaging` | `527be81862` | 1 → 1 | 0 → 0 | 0 → 0 | 0 | 0 → 0 | 0 → 0 |
| | **11 pairs** | | 75 → 132 | **31 → 47** | **20 → 0** | **7** | **3 → 3** | **3 → 3** |

| whole-population | old | **new** |
|---|---|---|
| verification answers | 59 | 98 |
| — answered about the code | 31 | **47** |
| — budget-refused | 25 | 49 |
| — host-blocked | 3 | 2 |
| **unfaithful (`fails on base as well`)** | **20** | **0** |
| probe refused (recording inadmissible) | — | 7 |
| certified | 3 | 3 |
| published | 3 | 3 |
| value class: certified / drawered | 0 / 1 | **0 / 15** |

## 3. What the numbers say, in order of how sure it is

**1. The wall is gone, and it is gone by construction, not by luck.** 20 → 0. The expectation a
replay asserts is what base itself produced three times minutes earlier, so a test that fails on
base as well cannot be written. This is not a measured improvement in the model's judgement; it
is a class of failure that no longer has a way to occur.

**2. Certification did not move: 3 → 3, published 3 → 3.** The generator that removed 20
unfaithful tests did not convert them into receipts. What the 20 became is visible in the row
below them.

**3. The bottleneck moved from generation to intent.** Value-class drawers went **1 → 15**.
Candidates that used to die as unfaithful reproductions now produce genuine differentials — head
behaves differently from base, the receipt would be mechanically perfect — and are then drawered
by `attest.intent.v4.1`, unchanged, because the base tree does not *state* the value the
assertion pins. **That is the same recall cost D-132/D-134 already priced, now paid where it can
be seen.** Before this change the value-class rule was mostly not reached on forward pairs; it
was not that intent was permissive, it was that generation failed first.

**4. The composition of the three publications changed, and both moves are informative.**

- **Lost: `more-itertools 2deea20ead`** (`random_product`). The function returns one of four
  tuples uniformly. The probe path **refuses to record a nondeterministic value** — correctly —
  so it publishes nothing here, while the legacy generator published because the model wrote an
  assertion about the *shape* of the result rather than its value. **This is a real recall cost
  of recording, and it is not a bug**: a value that is not reproducible is not a differential.
- **Gained: `click cd4674a6de`** (`src/click/parser.py:78`, `_unpack_args`). Base returns
  `(('a', ('b',), 'c'), [])` for the probed input and head does not. This pair certified nothing
  under the legacy generator.

**5. The proposer is nondeterministic and one of the eleven pairs shows it loudly.** `click
cd4674a6de` produced 42 candidates in the old run and 93 in this one, which is why its
budget-refused count more than doubled. **Two single runs are being compared**, and no
difference on a single pair should be read as an effect of the generator.

**6. `n` is still 11.** Nothing here estimates a rate.

## 4. The bug the first run found, and the fix (D-148)

This window ran the eleven pairs **twice**, and the first run is why there is a second.

Run 1 (`PROBE_RECORDINGS = 2`, $2.0298) produced `probe replay failed on base` on
`more-itertools 2deea20ead` — the outcome the design says is **structurally impossible**. It was
not impossible; it was improbable. `random_product` returns one of four tuples uniformly, so two
recordings agree one time in four, and this was that time: the pair `(1, 2)` was recorded twice,
the replay asserted it, and base did something else.

**The owner's instruction anticipated this exactly — "if it appears it is a bug" — and it was.**
The fix is in two parts, neither of which pretends the hole can be closed by counting higher:

- **three recordings, not two.** On this very case the third disagreed immediately: run 2's
  refusal reads *"the merge base returned (0, 0), then the merge base returned (0, 2)"*.
- **the reason string stopped lying.** A base failure on the probe path is not a generator
  asserting a behaviour base lacks; it is the **second** stability gate catching a value the
  first was fooled by. It now says *"probe observation did not survive re-execution: base
  produced it N times and then did not; the value is not deterministic."*

No finite number of recordings closes the hole. What bounds it is that the replay's own **three
base runs** must agree as well, so **six identical observations** stand between a
nondeterministic value and a receipt.

The headline table in §2 is run 2 in full, at one implementation. Run 1's numbers, for the
record: 98 answers, 37 about the code, unfaithful **0**, probe-refused 4 plus the one replay
failure, certified 3, published 3.

## 5. The bundle still verifies offline

The generated test in the bundle is the replay, and the recorded expectation is visible in it:

```python
from itsdangerous.exc import BadData


def test_attest_replay():
    exc = BadData(b'not a string')
    _attest_value = str(exc)
    # recorded by executing the expression above on the merge base;
    # no model wrote this expectation
    assert _attest_value == "b'not a string'"
```

```text
accepted: receipt 59d70bd0eb3047b17253b2d4d4ad700479425070d8728428f31f1846392dbb56
for ac074352b1 (linux-container-v1); seal verified
```

**The assertion is written the way a person would write it, and that is load-bearing rather than
cosmetic.** Every rule downstream reads the failing assertion — the changed-line binding,
D-102's rejection origin, and D-132/D-134's value class, which asks whether *the base tree states
the value this assertion pins*. An earlier draft compared a `{'kind': …, 'detail': …}` dictionary
and pinned the string `'6'`; a base test stating `6` could not match it, and the whole value
class would have drawered for a reason that was an artefact of the file's shape. It was caught
by a test on the first real fixture and the assertion now pins the literal.

## 6. Limits

- **Two single runs, one each.** The proposer is nondeterministic; pair 4 is the proof.
- **This is one population.** D-146 has been measured on 11 forward pairs and nowhere else. Its
  effect on the null controls, the held-out slice and ordinary shadow traffic is unmeasured, and
  the null population is closed (D-144), so the first of those will not be bought here.
- **The recall cost of recording is real and is now on the record**: a function whose output is
  not reproducible cannot be probed by recording its output. `random_product` is the first
  measured case.
- **The budget wall is the same wall, and it is bigger only because the diff was.** 49 of 98
  answers were budget refusals against 25 of 59, and **all** of the growth is on `click
  cd4674a6de`, whose proposal produced 93 candidates this time and 42 last time. Per answer the
  probe path is **cheaper**: $2.0313 over 98 answers is $0.0207 each, against $2.5804 over 59,
  or $0.0437. What it costs more of is *executions* — three extra sandboxed runs per
  candidate — which is wall-clock and not budget.
- **`n = 11`.** No rate is estimable, in either column.
