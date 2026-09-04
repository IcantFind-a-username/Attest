# `G-NULL-001a` resumed under `attest.intent.v3` — and it published again (D-131)

**Owner instruction 2 of 2026-09-04c**, the second half. The offline replay
([report](2026-09-04-intent-v3-replay.md)) showed D-128 drawering both `jinja ac3ac6c9`
receipts and leaving **zero** control publications anywhere in the recorded corpus, so the
remaining controls were resumed as instructed, with the reservation written first.

**36 further controls ran. The 36th published, and the publication is wrong.** Per the owner's
rule the run stopped at once, was root-caused, and was **not fixed and not resumed**.

| | |
|---|---|
| population | the **same** 58 preregistered qualified controls (cutoff, seed and quota unchanged, not re-sampled) |
| run before this window | 15 (under `attest.intent.v2`) |
| **run in this window** | **36** (under `attest.intent.v3`) |
| **total run** | **51 of 58**; 7 never reached |
| candidates / eligible / receipts | 15 / 13 / 2 |
| **wrong publications under v3** | **1** |
| spend | **$1.074700** of an $18.00 reservation; $16.925300 released |
| repositories touched this window | `more-itertools` 13, `packaging` 12, `jinja` 5, `python-dotenv` 5, `urllib3` 1 |

**`G-NULL-001a` still does not pass**, and its permitted claim is still none: the gate is
conditioned on the preregistered n with **zero** wrong publications, and there are now two —
one under each discriminator.

## The control, and what published

`urllib3 c7b9adcb` (2023-12-28, *"Fix TestBrokenPipe on macOS"*), 980 days old, untouched — a
control by the amendment's definition. Three lines, and the diff explains itself:

```python
-            # EPROTOTYPE is needed on macOS
-            if e.errno != errno.EPROTOTYPE:
+            # EPROTOTYPE and ECONNRESET are needed on macOS
+            if e.errno != errno.EPROTOTYPE and e.errno != errno.ECONNRESET:
                 raise
```

The product generated a test asserting that `ECONNRESET` still propagates off macOS. It passes
on the parent and fails on the commit, **because the commit deliberately stopped it
propagating**. Head fails 3 of 3, base passes 3 of 3, the changed lines execute, the bundle
verifies. Same shape as `ac3ac6c9`: a defect claim about a change the author made on purpose
and documented in the same diff.

## Root cause: v3 classified it correctly and then let it through on `False`

The receipt's own intent record is the whole story:

```json
{"policy_version": "attest.intent.v3", "value_mismatch": true,
 "pinned_values": ["False"],
 "value_specified": [["False", "test/test_connectionpool.py"]],
 "value_respecified": []}
```

**v3 saw a value mismatch and admitted it, because the one value the test pins is `False`, and
`urllib3`'s own test suite asserts `is False` somewhere.** Two separable defects compound:

1. **A generic constant is not a specification.** `False`, `None`, `0`, `True` are asserted in
   almost any tree, so "the base tree specifies this value" is satisfied by a coincidence of
   vocabulary rather than by any statement about the function under review. **This was named as
   v3's weakest point in §3 of the replay report, hours before it happened** — four of the ten
   surviving receipts there rested on exactly such constants. It is now observed rather than
   predicted.
2. **The pinned set is computed over every `assert` in the test, not the one that failed.** The
   assertion that actually failed here is not an `assert` statement at all: it is a bare `raise
   AssertionError(...)` inside a stub class the test defines, reached because head swallowed the
   error. The JUnit message says so — *"getresponse() must not be reached after ECONNRESET"*.
   So `False`, the constant that carried the publication, has nothing to do with the failure.

The first defect is one v3 knew it had. The second is new, and it is the deeper one: **the rule
is stated about "the value the failing assertion pins", and the implementation approximates that
with "every value any assertion in the test pins".** On this test the approximation is not close.

## Not fixed, and not resumed

The owner's rule for this window was explicit: *if a publication appears again, stop at once and
root-cause; do not fix and do not resume.* Both halves are honoured. The 7 unrun controls stay
unrun, $16.93 stays unspent, and the two candidate narrowings — a generic-constant exclusion,
and pinning only the constants of the assertion that actually failed — are described here and
implemented nowhere.

## What this does and does not say about D-128

- It does **not** retract D-128. On this same population v3 drawers both `ac3ac6c9` receipts,
  which `v2` published; the corpus replay's 55 → 19 and 27 → 14 stand.
- It **does** retract any reading of D-128 as sufficient. **One wrong publication in 36 controls
  under v3** is the measurement, and it is not a rate anyone should quote: with one error in 36
  the honest reading is "somewhere near 3%, with an interval far too wide to act on".
- The bias note from the first run still applies and still cuts the same way: this population is
  cold code the product mostly says nothing about, which biases the measured rate **downward**.
