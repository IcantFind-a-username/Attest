# The 20 forward-pair generation failures, classified — 2026-09-06

D-140 measured the wall on forward pairs: **20 of the 31 answered candidates** ended as
`unfaithful generated test: fails on base as well`. This document opens all 20 and says what
each one actually did, because "the generation is bad" is not a finding anyone can act on.

**Free.** Every classification is read from the recorded `verification` ledger row of the
review that produced it — the row carries the generated test's source, the three head runs and
the three base runs in full. Nothing was re-run and nothing was paid for. Source:
`.attest/corpora/gnull/{click,itsdangerous,more-itertools}/.attest/ledger.jsonl`, the same
findings the [forward-pair report](2026-09-05-forward-pair-reviews.md) tabulates.

## 1. The four classes the owner asked for, counted

| class | n | share |
|---|---|---|
| **environment / dependency import error** | **0** | 0% |
| **asserted a behaviour the base does not have either** | **18** | 90% |
| — B1: the failure is *identical* on head and base; the claim's premise about base was false | 11 | 55% |
| — B2: the failure *differs*; the test encodes the head-era contract, base's is a different one | 7 | 35% |
| **references a symbol or signature only head has** | **1** | 5% |
| **other** | **1** | 5% |

**The environment class is empty, so the conditional backlog item does not fire.** Not one of
the 20 failed on an import, a missing dependency, a version conflict or a collection error.
That is not because the corpus has no such problem — it is because those failures never reach
this verdict: they are recorded as `collection deferred` (1 candidate) or
`isolation backend unavailable` (3 candidates, the `attrs` and `packaging` pairs whose images
would not build on Python 3.13 / 3.9). Era-matched interpreters and pinned dependencies are the
fix for **those 4**, and they are worth exactly that; they would have changed **none of the 20**.

The dominant class is a *knowledge* failure, not an environment one: **18 of 20 generated tests
assert something the base revision does not do**, so the reproduction cannot discriminate. On a
reversed pair the diff is the repair and states the defect; on a forward pair the proposer must
infer the base's behaviour from the diff alone, and 18 times out of 20 it inferred wrong.

## 2. Every case

`head E` and `base E` are the first assertion/exception line of each side's first run.

### B1 — identical failure on both sides (11)

The test executed on both revisions and produced **the same error on each**. The generated test
is a statement about how the code *ought* to behave that is false on head and base alike; the
candidate's premise ("base did X") was never checked.

| # | repo · head | finding | anchor | what base did |
|---|---|---|---|---|
| 1 | `click` `0585f456ba` | `0f367118c2` | `termui.py:269` | the test's own `value_proc` raised `UsageError` on both sides; the reprompt loop it expected exists on neither |
| 2 | `click` `0585f456ba` | `1389e7d11d` | `termui.py:126` | `_build_prompt(..., show_default="hint", default=None)` returns `"Enter value [(hint)]: "` on **both**; the test asserted `"Enter value: "` |
| 3 | `click` `0585f456ba` | `30a5ce2d3c` | `termui.py:270` | `value_proc` is called with the falsy default on both; "not reprocessed" is true of neither |
| 4 | `click` `0585f456ba` | `34128dc2a2` | `termui.py:245` | a `Path` default stays a `PosixPath` on both; the asserted `str` conversion happens on neither |
| 5 | `click` `0585f456ba` | `99e1314cc4` | `termui.py:260` | a list default raises `TypeError` inside `int()` on both |
| 6 | `click` `0585f456ba` | `cac89100da` | `termui.py:152` | `convert()` is called for a matching default on both |
| 7 | `click` `cd4674a6de` | `6522feec26` | `types.py:205` | a bare `ValueError` produces an empty `BadParameter` message on both |
| 8 | `itsdangerous` `3703fbdedd` | `5486de076b` | `jws.py:215` | a list `exp` raises `TypeError` out of `int()` on both, not the asserted `BadHeader` |
| 9 | `itsdangerous` `3703fbdedd` | `72859502fb` | `signer.py:24` | a `str` signature raises `TypeError` out of `constant_time_compare` on both, not the asserted `False` |
| 10 | `itsdangerous` `3703fbdedd` | `e369c66f11` | `jws.py:216` | same list-`exp` `TypeError`, reached through `loads` |
| 11 | `more-itertools` `390a3db74c` | `119e489be4` | `recipes.py:222` | `all_equal` over-consumes on both; the test asserted the base implementation does not, and it does |

### B2 — different failure on base: the test encodes the head-era contract (7)

All seven are the same pair, `click 19fd4d6e18` (fish shell completion). Head serialises a
completion as three newline-separated fields; **the base does not have that format at all** — it
emits `type,value\thelp` on one line. Every generated test asserts some property *of the
three-line contract* (field count, escaping, tab handling), so on base it fails for the trivial
reason that base's output is a different shape.

| # | finding | anchor | head E (abridged) | base E (abridged) |
|---|---|---|---|---|
| 12 | `457771a1e8` | `shell_completion.py:436` | `'plain\nvalue\nline1\\nline2'` ≠ expected | `'plain,value\tline1\nline2'` ≠ expected |
| 13 | `8397d3f1d5` | `:437` | `pl` (type field truncated) | `assert 'pl' == 'pl\\nain'` |
| 14 | `155ef5b6b8` | `:195` | `plain` | `plain,value\tC:\path` — 1 field, not 3 |
| 15 | `50c92eacb6` | `:435` | literal tab left in value | `ValueError: not enough values to unpack (expected 3, got 1)` |
| 16 | `aaab2e272a` | `:438` | formatted completion contains newline | `assert 'plain,--at' == 'plain'` |
| 17 | `d9da8ab508` | `:432` | literal `_` help indistinguishable | `assert 'plain,value\t_' == 'plain'` |
| 18 | `eae3dab7a5` | `:434` | expected 3 fields, got 4 | expected 3 fields, got 2 |

These are the *least* wrong of the 20: the model understood head, and the head-side failures in
column 3 are real observations about head's escaping. What it could not know from the diff is
that the base predates the format entirely — so no assertion phrased in head's vocabulary can
be a differential.

### H — a symbol or signature only head has (1)

| # | repo · head | finding | anchor | base |
|---|---|---|---|---|
| 19 | `click` `cd4674a6de` | `d9609539dd` | `_termui_impl.py:618` | `TypeError: _tempfilepager() missing 2 required positional arguments: 'cmd_parts' and 'color'` — the test calls head's signature, which base does not have |

### O — other (1)

| # | repo · head | finding | anchor | what happened |
|---|---|---|---|---|
| 20 | `itsdangerous` `3703fbdedd` | `bf96d32ed3` | `tests/test_itsdangerous/test_serializer.py:16` | the generated test **defined its own copy** of `coerce_str` at `test_repro.py:9` instead of importing the tree's, so both sides executed the *same* pasted head code and failed identically. The product under review was never called |

Case 20 is the only one of the 20 where the reproduction did not exercise the tree at all; the
binding check (V-02) would have refused it had it reached head-only failure, and the base run
refused it first.

## 3. What this says, and what it does not

- **It is not an environment problem.** Era-matched Python and dependency pinning are worth
  doing for the 4 candidates that DEFERred at image bootstrap or collection, and they buy
  nothing here.
- **It is a base-knowledge problem.** 18 of 20 asserted a behaviour base does not have. The
  proposer sees the forward diff and a head-side context window; the base revision's actual
  behaviour is not in either. The cheap experiment this suggests — *observe the base before
  writing the assertion*, i.e. let the generator run an exploratory probe on the base tree and
  quote its output — is recorded in [`backlog.md`](../backlog.md) and **not implemented**;
  changing generation is a measurement-invalidating change to make mid-study.
- **`n` is 11 pairs and 20 tests.** This is a classification of one window's failures, not a
  rate. Nothing here licenses a claim about how often generation fails in general.
