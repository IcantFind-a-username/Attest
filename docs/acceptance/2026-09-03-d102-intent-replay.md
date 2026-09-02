# D-102 intent discriminator: replay on the real bundles (owner decision 1, 2026-09-03)

Date: 2026-09-03. No model call; every reproduction re-executed through
`linux-container-v1` from this checkout with `scripts/corpus/intent_replay.py`. Input: the
generated tests of every receipt the E-02 held-out run published (5 defects, 7 candidates,
[held-out report](2026-09-03-e02-heldout.md)) and of the one E-01 natural-null publication
(`3a32c92`, candidate `7ecf2fb275`, [natural-null report](2026-09-03-e01-natural-null.md)).
Result files: `.attest/corpora/swebench/results/intent-replay.json` (all eight) and
`intent-replay-natural-null.json` (the `3a32c92` row re-run after the verdict wording was
made author-safe; same verdict). Evidence level: **mechanism replay on the eight real
receipts**, not a new population.

## The RED the owner named

- the `3a32c92` receipt goes to the drawer: **yes** — outcome `deferred`, evidence class
  `behavior_change`, reason `behavior change confirmed, intent unknown` (行为变化已证实，意图未知);
- the five held-out real regressions still publish: **yes** — all 7 candidates on the 5
  defects reproduce as `regression_reproduced`, head FAIL 3/3, base PASS 3/3, bound.

## Table

| case | candidate | outcome | evidence class | new rejection | failure origin in the anchored file | rejected inputs | witnesses |
|---|---|---|---|---|---|---|---|
| psf__requests-1142 | f9d26dc62d | reproduced | regression_reproduced | no | NameError from an expression at models.py:278 (unchanged line; a caught compatibility probe) | – | – |
| psf__requests-1921 | d4503dddb0 | reproduced | regression_reproduced | no | none (the test asserts) | – | – |
| psf__requests-5414 | b4a6e83afe | reproduced | regression_reproduced | no | none (the test asserts) | – | – |
| pylint-dev__pylint-4551 | 0f8c700ba4 | reproduced | regression_reproduced | no | none (the test asserts) | – | – |
| pylint-dev__pylint-4604 | 034c8cce0a | reproduced | regression_reproduced | no | none (the test asserts) | – | – |
| pylint-dev__pylint-4604 | a1933d1ec3 | reproduced | regression_reproduced | no | none (the test asserts) | – | – |
| pylint-dev__pylint-4604 | a3c6946d1d | reproduced | regression_reproduced | no | none (the test asserts) | – | – |
| us-stock-helper `3a32c92` | 7ecf2fb275 | **deferred** | **behavior_change** | **yes** | `ValueError` from the `raise` at patterns_shapes.py:349, a changed line, on every head run | `买入价曾经历史新高`, `本次形态与`, `相关，仅作历史信息呈现` | **0 of 3** in the base tree's tests, fixtures or docs |

Reading: the discriminator separates the one wrong publication from the seven right ones
by structure, not by wording — the head failure of `3a32c92` is an exception raised by a
`raise` statement the diff added, and the phrase the generated test called legitimate
copy exists nowhere in the base tree's tests, fixtures or documentation. Every real
regression fails in the test's own assertion (or, for requests-1142, records only a caught
`NameError` on an unchanged line), so none is reclassified.

## What the rule is (D-102)

1. During each head run the tracer records the first frame of the anchored file each
   exception passed through (line, function, exception type, bounded message, bounded
   string locals).
2. If, on every head run, an exception originated from a `raise` or `assert` statement on
   a changed line of the anchored file, the differential is a **behavior change**: head
   rejects an input the base accepted.
3. The rejected inputs are the generated test's string literals that reached the raising
   frame (present in the exception message or in a string local). The receipt publishes —
   as a `behavior_change` receipt, worded as what it proves — only when every identified
   input occurs verbatim in a witness file of the **base** tree (tests, fixtures, examples,
   documentation). Otherwise: drawer, label "behavior change confirmed, intent unknown".
4. The receipt binds the intent observation (`intent_policy_version`, `intent_digest`,
   `intent.json` in the bundle); `attest verify --bundle` recomputes the digest and
   re-judges the verdict, so a bundle whose observation lost its witnesses is rejected.

## Unit and end-to-end RED (all pass; see the D-102 entry for the files)

- pure: the `3a32c92` observation → drawer with the label; the same observation with every
  input witnessed → publishable; a partial witness → drawer; no identified input → drawer;
  a regression or a crash on a changed line → regression class;
- executor (planted guard on an existing constructor): fabricated input → `deferred`
  `behavior_change` with the label; the base tree's own test builds the phrase →
  `reproduced` `behavior_change` with the witness path; the planted regression and an
  `IndexError` crash on a changed line → `regression_reproduced`;
- CI: the fabricated case posts no review and the run status shows
  `behavior change, intent unknown` without the candidate's file, line or input; the
  witnessed case publishes `Behavior change (intent to confirm): …` with
  `Verified behavior change: …` and the witness path, its bundle verifies offline, and a
  digest-consistent copy of the bundle whose `intent.json` lost its witnesses is rejected
  by `verify_bundle` ("intent observation forbids publication").

## Caveats

- A witness is verbatim presence in a witness file; presence as a negative example is not
  distinguished (mitigated by requiring every identified input to be witnessed).
- Only string literals of the test are identified as rejected inputs; a rejection of a
  number, an object or a constructed value stays in the drawer.
- A rejection raised by an unchanged helper that a changed line calls is a regression
  under this rule (the `raise` is not on a changed line) — the residual RISK-INTENT-01.
- Eight receipts, one repository per corpus; E-04 measures the drawer rate on live traffic.
