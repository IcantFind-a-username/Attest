# `attest.intent.v4.1`: clause (c) narrowed to a recognisable mention, and it changes nothing

**Owner instruction 1 of 2026-09-05 (owner item 2 of the previous handoff).** Replay driver
[`scripts/corpus/intent_v4_replay.py`](../../scripts/corpus/intent_v4_replay.py) (schema
`attest.intent-v4-replay.v2`), data
[`evidence/2026-09-05-intent-v41-replay.json`](evidence/2026-09-05-intent-v41-replay.json).
**$0.00, no model call, no execution** — file reads and an AST walk over the receipts the
corpus already recorded.

## 1. The rule

D-132's clause (c) drawers a value receipt when the same diff also changed a test, a docstring,
a documentation or changelog line, or an inline comment **touching the anchored symbol**. It
recognised "touching" two ways, and only one of them was safe:

- **by position** — prose the change moved *inside the body* of a touched symbol, in the
  anchored file. The link is where the line sits. This is the clause that stops
  `urllib3 c7b9adcb`.
- **by vocabulary** — in every other changed file, an added or removed line that *names* a
  touched symbol, matched as a word. `readings`, `decision`, `snapshot`, `main` are names; they
  are also English, and D-132's own entry said so and left it.

**`attest.intent.v4.1` (D-134) changes the second one and nothing else.** A name is a mention
only where it appears in a **recognisable form**:

1. **backticked** — `` `slug` ``, ``` ``slug`` ```, ``:meth:`Pool._make_request` ``: the writer
   marked it up as code;
2. **dot-qualified** — `mod.slug`, `slug.upper`: a name with a namespace around it is not a
   sentence;
3. **a bare name English does not supply** — at least **8** characters and not in a curated list
   of ordinary English words ([`src/attest/review/vocabulary.py`](../../src/attest/review/vocabulary.py)).

Position is untouched. The escape hatch is the *form*, not the vocabulary: a changelog that says
``` ``snapshot`` now returns the last row ``` is still intent, because the author pointed at the
code.

## 2. The two columns

57 replayable receipts, 138 reviews, one observation per receipt, two mention rules over the
same bytes. The v4 column recomputes clause (c) with `find_intent_evidence(distinctive=False)`,
so v4 and v4.1 differ by the mention rule and by nothing else.

| | v2 | v3 | v4 | **v4.1** |
|---|---|---|---|---|
| certifying receipts (57) | 57 | 21 | 9 | **9** |
| — the value class (48) | 48 | 12 | 0 | **0** |
| — crash (7) + rejection (2) | 9 | 9 | 9 | **9** |
| publications over 138 reviews | 28 | 15 | 6 | **6** |
| **control publications** | 2 | 1 | 0 | **0** |
| control receipts certifying (4) | 4 | 2 | 0 | **0** |

**The controls stay at 0, which was the stop condition, and the value class comes back at 0,
which was the question.** The v2 column reproduces the ledger on **72 of 72** rows written under
today's family rule.

## 3. What the narrowing actually removed

Clause (c) fires on **42 of the 48** value receipts under v4 and on **the same 42** under v4.1.
Not one receipt's verdict moved in either direction: `certifying_under_v4_1_not_v4` and
`drawered_by_v4_1_not_v4` are both **empty**.

Underneath the verdicts it did remove evidence. Of **87** recorded (symbol, file) sites, **15
are dropped** — 17% — across **4** receipts, and every one of the four kept another site:

| receipt | dropped sites |
|---|---|
| `us-stock-helper 1d0af73c3e` | `render` in a runbook, `summary` in a smoke test |
| `us-stock-helper e5d9505259` | `readings` ×2, `snapshot` ×4 |
| `us-stock-helper 16cab71ac4` | `decision` ×5 |
| `us-stock-helper 3cd7bdd217` | `decision` ×5 |

**Those are exactly the words D-132 predicted would collide with English, and they are all of
them.** The 72 surviving sites are positional, backticked, dot-qualified, or long unusual names
— `_make_request`, `async_variant`, `detect_ma5_pullback_pattern`, `build_component_environment`.
`snapshot` and `_reason` appear on *both* lists: dropped where a comment used the word, kept where
the author wrote it as code. That is the rule doing what it is for.

## 4. What this measures, and what it does not

- **It measures the size of the vocabulary problem: 15 sites of 87, 0 verdicts.** D-132 recorded
  "an unknown fraction of the 42 corpus hits is false". The fraction is now known at the level of
  *sites*, and at the level of *receipts* it is **zero on this corpus** — every receipt clause (c)
  drawers is drawered by at least one mention a reader would recognise as pointing at code.
- **It does not say clause (c) is right.** A recognisable mention can still be about something
  the receipt is not about. That question is adjudication, not replay, and it is the
  [12-receipt sample](2026-09-05-value-class-adjudication.md).
- **It does not recover the value class.** Nothing here was ever going to: the 48 value receipts
  fail (a) 32 times, (b) twice and (c) 42 times, and **all six** receipts that (c) does not touch
  pin nothing at all under (a) — there is no value for a base tree to have specified.
- **The wordlist is curated, not a dictionary**, and a curated list is a place a future name can
  hide. The cost of a wrong entry is bounded on one side only: a word wrongly *in* the list makes
  the rule publish more, so the list is the thing to grow slowly. The measured effect of today's
  list is 15 sites and 0 receipts.

## 5. Reproduce

```bash
.venv/bin/python scripts/corpus/intent_v4_replay.py --json /tmp/replay.json
```

Offline, free, and deterministic given the corpora on this host. Four receipts of one task are
skipped: the observer inputs they need are not on this host, the same four the v4 replay skipped.
