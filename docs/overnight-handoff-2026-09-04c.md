# Handoff — 2026-09-04c (`9308e17` → `b91d045`, plus this line): v3 landed, and a control published under it

**Window spend $1.074700 of $35; cumulative $48.912326 of $90.** Remote writes: **none**.
Gates at the tip: `ruff` clean, `mypy` clean over 81 files, `git diff --check` clean, and
**`pytest` exit 0 with zero failures over the whole suite minus `tests/execution/test_isolation.py`**
— `tests/benchmark` and the container-backed `tests/execution/test_linux_isolation.py` included —
run exclusively on a clean tree. The `test_m01_offline_measurement_probe` errors of the last two
windows do not appear: they are the clean-tree guard, and the tree was clean.

## 1. `attest.intent.v3` (D-128) — old vs new, on every receipt the corpus holds

A value mismatch publishes only when the base tree **specifies** every value the assertion pins
(a base test asserts it, or a docstring or docs write it down) **and** this change leaves those
specifications standing. Deterministic; no model. [Report](acceptance/2026-09-04-intent-v3-replay.md),
[data](acceptance/evidence/2026-09-04-intent-v3-replay.json), $0.00.

| | under v2 | **under v3** |
|---|---|---|
| certified receipts (55 replayable of 59) | 55 | **19** |
| — of which the value class (46) | 46 | **10** |
| — crash (7) and rejection (2) | 9 | **9**, unchanged |
| publications over 125 reviews | 27 | **14** |
| **control publications** | 1 | **0** |

Drawer reasons for the 36: 19 unspecified value, **16 pin no value at all**, 1 specification the
change rewrote. That third of the cost is one shape — an assertion that compares against a name
or a computed value rather than a literal — and the suite produced two more instances of it on
the spot (the monorepo helper-import fixture and the numpy container fixture, both recorded in
the tests rather than worked around). **The recall cost is the decision.** The old replay reproduces the ledger on
59 of the 59 rows written under D-125's family rule. Four of the ten survivors rest only on
generic constants (`None`, `0`, `2`, `True`) — stated as v3's weakest point, and §2 is that
weakness happening.

## 2. `G-NULL-001a` resumed — and stopped again (D-131)

n, bound and spend in one sentence, as the gate requires: **36 further preregistered qualified
controls ran under v3 (51 of 58 total, 7 unrun), 1 wrong publication, $1.0747 of an $18
reservation; the zero-error bound does not apply and one error in thirty-six reads as roughly
3% with an interval far too wide to act on.** `G-NULL-001a` does not pass; `G-NULL-001` remains
unattempted. [Report](acceptance/2026-09-04-g-null-001a-resumed.md).

`urllib3 c7b9adcb` deliberately widens a tolerated-errno set and says so in the diff. **v3
classified it right — `value_mismatch: true` — and let it through on `pinned_values: ["False"]`,
because urllib3's tests assert `is False` somewhere.** Two compounding defects: a generic
constant is not a specification, and the pinned set is *every* `assert` in the test rather than
the assertion that failed (here a bare `raise AssertionError` in a stub, unrelated to `False`).
Per the owner's rule: stopped at once, root-caused, **not fixed and not resumed.**

## 3. The seven E-04 shadow findings, re-judged under v3 — two survive

Both pin only `None`, which is the §2 weakness again; both are the same change, split in two.

1. `us-stock-helper` · `information_layer/factors/unsupported.py:27` — the commit deletes
   `institutional_flow_reading` and its `FACTOR_INSTITUTIONAL_FLOW` abstention; it looks like a
   defect because any caller still importing that symbol fails at import time.
2. `us-stock-helper` · `information_layer/factors/unsupported.py:49` — the same deletion seen
   from the other end: `FactorSnapshot.institutional_flow` has no populator left, so a snapshot
   builder outside the diff raises `AttributeError` when it fills that field.

The five that no longer survive: `container_adapter.py` (pinned `'image'`/`13`),
`factors/provider.py`, `analysis_api/service.py`, `feeds/collector.py`,
`analysis_api/adviser_provider.py`.

## 4. Mainline revised (D-129)

Four speech levels, each owing its own evidence and each adjudicated **without a model** — red =
differential receipt; **gate** = an executable failure of new code on a witnessed reachable input
(N-01 promoted onto the mainline); yellow = model states premises, a checker verifies each, only
verified premises are said; green = a computable measure with ≥2 coordinates, the model called
once afterwards. One rule: **the LLM thinks; an algorithm decides whether it may speak.**
Condition 2 amended in place, because it had required a receipt for every finding and so made
three levels unshippable by definition. Integration is **a GitHub Action and a repository
Secret, and nothing else**; the product never touches, stores, transmits or logs a key;
`attest init` is optional and ordered last. Order: **v3 → green → gate → yellow**. `AGENTS.md`
§10 carries the compact copy.

## 5. The green level v0, offline (D-130)

Repeated implementation only. [Report](acceptance/2026-09-04-structural-offline.md), **$0.00,
zero model calls.** Real traffic (E-04 stratum v2, 100 units): 33 change Python, **8 speak, 12
findings — 24.2% of Python-touching units.** Null controls: **13 of 58, 22.4%** — and that is
not a false-publication rate, because duplication is a property of the code, not of the commit.
Five adjudicated by hand: **four clearly true, one overstated ("the same implementation" for two
env parsers differing only in a bound), none false.** The wording adjudicator drops a hedging
model's sentence and publishes the deterministic one; that is proven against a stub, never yet
against a model.

## 6. Failure copy and README (owner instruction 5)

A missing key now prints the repository's own secrets URL, `Name: ANTHROPIC_API_KEY` exactly,
and *"Nothing was sent anywhere… no key was read, stored or logged"*; a missing token names
`secrets.GITHUB_TOKEN` and `pull-requests: write`. The README's first screen is the complete
workflow file, copyable whole. RED: three tests in `tests/test_action_entrypoint.py`.

## 7. Not done, and why

- **The 7 remaining `G-NULL-001a` controls**, and **any fix to v3**: the owner's rule for this
  window forbids both once a second publication appeared.
- **`G-SHADOW-001` is not advanced.** The two surviving shadow findings are still unadjudicated
  by anyone independent of the product.
- **Green is not wired into publication**, and its one model call has never met a model.
- **No `G-SEC-002` work, no new-code pricing, no scheduler**, and no re-run of the 36 drawered
  receipts to see which were real defects — that needs adjudication, not replay.
- **The four v2 receipts whose observer inputs are not on this host** were skipped, not counted.

## 8. For the owner — three items

1. **Narrow v3, or stop publishing the value class entirely? (D-131)** Two shapes, neither
   touching alpha/LR/K/cap: (a) exclude generic constants (`None`/`True`/`False`/small ints) from
   the pinned set, so a receipt needs at least one distinctive value; (b) pin only the constants
   of the assertion that actually failed, read from the head runs' JUnit message. Neither
   addresses the third of the recall cost that pins *no* literal at all; that needs a separate
   answer and is not one of these two. **(a)+(b)
   together is the default recommendation**; both were implementable tonight and neither was
   implemented, because both move what publishes. **Until one lands, `G-NULL-001a` cannot resume
   and condition 4 cannot move.**
2. **Resume the 7 unrun controls only after that fix — yes?** Default **yes**: the population,
   cutoff, seed and quota are unchanged and $16.93 of the reservation is unspent, so the resumed
   run costs about $0.30.
3. **Proceed to wire green as an author-visible channel (mainline §1.3's next step) — yes?**
   Default **yes**, with the threshold question from §5 settled first on a slice not used by
   tonight's measurement.
