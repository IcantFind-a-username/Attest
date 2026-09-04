# Handoff — 2026-09-05 (`3e6ae31` → `PENDING`): v4, and the value class goes quiet

**Window spend $PENDING of $5; cumulative $PENDING of $90.** Remote writes: PENDING.
Gates at the tip: PENDING.

## 1. `attest.intent.v4` (D-132) — v2, v3, v4 in three columns

[Report](acceptance/2026-09-05-intent-v4-replay.md), [data](acceptance/evidence/2026-09-05-intent-v4-replay.json), **$0.00, no model call.**
57 replayable receipts, one observation, three rules. (a) the pinned set is the assertion that
*failed*, located in the JUnit longrepr; (b) a generic constant is not a specification; (c) any
test, docstring, docs, changelog or inline-comment change in the same diff touching the anchored
symbol is intent. Publish only when **base specifies · head still specifies · the diff says
nothing**.

| | v2 | v3 | **v4** |
|---|---|---|---|
| certifying receipts (57) | 57 | 21 | **9** |
| — the value class (48) | 48 | 12 | **0** |
| — crash (7) + rejection (2) | 9 | 9 | **9** |
| publications over 135 reviews | 28 | 15 | **6** |
| **control publications** | 2 | 1 | **0** |

The v2 column reproduces the ledger on **69 of 69** rows written under today's family rule.
Each clause asked alone over the 48 value receipts: **(a) 32, (b) 2, (c) 42**; over the 12 v3
certified: **(a) 12, (b) 0, (c) 8**. **Both live wrong publications are stopped and each by (c)
alone** — `jinja ac3ac6c9` (comment inside the changed function, plus `CHANGES.rst`) and
`urllib3 c7b9adcb` (the comment above the widened condition).

**The value class certifies nothing on this corpus. That is the decision's cost and it is
large** — the product's main class, switched off on the evidence we have. The publishing branch
exists and is tested; no real receipt here reaches it.

## 2. `G-NULL-001a` — PENDING

## 3. The two shadow findings: **both false** (owner instruction 3)

[Report](acceptance/2026-09-05-shadow-adjudication.md), $0.00, no model. At the reviewed head
`7245680bf493`, four exhaustive word-boundary greps over the whole worktree:

- `institutional_flow_reading` — **no references.** The three near-hits are
  `AnalysisService._institutional_flow_reading` (`services/analysis_api/src/us_stock_helper_analysis_api/service.py:147, :216`),
  a *different, new* private method, and a test named after it
  (`services/analysis_api/tests/test_analysis_service.py:369`).
- `FACTOR_INSTITUTIONAL_FLOW`, `INSTITUTIONAL_FLOW_ABSTENTION_VERSION` — **no references.**
- `FactorSnapshot.institutional_flow` — **no such field.** `FactorSnapshot` at head has
  `symbol, as_of, macro, geopolitics, fundamentals`
  (`services/information_layer/information_layer/factors/provider.py:48`), and
  `PublicFactorProvider.snapshot` (`:89`) constructs exactly those.
- The 24 surviving `institutional_flow` mentions all belong to other objects, each defined and
  populated in the same commit: `DecisionInputs`/`FeatureSet` (`analysis_core/us_stock_helper_core/scoring.py:285`,
  `decision_engine/decision_engine/engine.py:151`), the evidence provider's own source field
  (`analysis_api/.../evidence_provider.py:113, :124, :127`), the gateway
  (`analysis_api/.../gateway_provider.py:145`, `__main__.py:26`), a comment
  (`information_layer/factors/base.py:34`), and tests.

**One line for you: the commit deleted the function, its constants, its export, the
`FactorSnapshot` field and every call site in the same diff — there is nothing dangling, so
both of the surviving shadow findings are false, and v4 clause (c) drawers them both.**
The README empirical table now carries this row.

## 4. Green as an author-visible channel (D-133) — PENDING

## 5. Not done, and why

PENDING

## 6. For the owner — PENDING
