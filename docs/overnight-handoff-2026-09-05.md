# Handoff — 2026-09-05 (`3e6ae31` → `3ae715f, plus this line`): v4 lands, and the value class goes quiet

**Window spend $0.577415 of $5; cumulative $49.489741 of $90.** Remote writes: **push to `main`,
and the one authorized throwaway pull request ([#9](https://github.com/IcantFind-a-username/Attest/pull/9),
closed unmerged, branch deleted)** — nothing else. Gates at the tip: `ruff` clean, `mypy` clean
over 81 files, `git diff --check` clean, **`pytest` exit 0 with zero failures and zero errors**
over the whole suite minus `tests/execution/test_isolation.py`, run exclusively on a clean tree;
and the **GitHub-runner `gates` workflow passed on every pushed commit of this window** — runs
33913070680, 33918844790 and 33918847885, all `success`, the last of them on the tip this
handoff names.

## 1. `attest.intent.v4` (D-132) — v2, v3, v4 in three columns

[Report](acceptance/2026-09-05-intent-v4-replay.md), [data](acceptance/evidence/2026-09-05-intent-v4-replay.json),
**$0.00, no model call.** 57 replayable receipts, one observation, three rules. **(a)** the
pinned set is the assertion that *failed*, located in the JUnit longrepr; **(b)** a generic
constant is not a specification; **(c)** any test, docstring, docs, changelog or inline-comment
change in the same diff touching the anchored symbol is intent. Publish only when **base
specifies · head still specifies · the diff says nothing**.

| | v2 | v3 | **v4** |
|---|---|---|---|
| certifying receipts (57) | 57 | 21 | **9** |
| — the value class (48) | 48 | 12 | **0** |
| — crash (7) + rejection (2) | 9 | 9 | **9** |
| publications over 135 reviews | 28 | 15 | **6** |
| **control publications** | 2 | 1 | **0** |

The v2 column reproduces the ledger on **69 of 69** rows written under today's family rule. Each
clause alone over the 48 value receipts: **(a) 32, (b) 2, (c) 42**; over the 12 v3 certified:
**(a) 12, (b) 0, (c) 8**. **Both live wrong publications are stopped, and each by (c) alone** —
`jinja ac3ac6c9` and `urllib3 c7b9adcb`.

**The value class certifies nothing on this corpus. That is the cost and it is the decision.**
Three fixtures in this repository stopped certifying the moment (b) landed, including the frozen
M-01 cassette, which needed a new frozen artifact (`m01-mixed-5-v2.json`, `3 → 7`) to keep
measuring what it measures. In every case the fixture moved and the rule did not.

## 2. `G-NULL-001a` finished — 58 of 58, and it still does not pass

[Report](acceptance/2026-09-05-g-null-001a-final.md). The last 7 controls ran under v4: **12
candidates, 0 receipts, 0 publications, $0.508300.**

**Final n and bound: under v4, n = 7 with 0 wrong publications — a rule-of-three 95% upper bound
of ~43%, which is not a bound anyone can act on.** The other 51 ran under v2 (15) and v3 (36)
and produced the two wrong publications, so **`G-NULL-001a` does not pass** and `G-NULL-001`
is unattempted. What can be said: the population is exhausted, and every control receipt it ever
produced is drawered by v4 in the replay. **Over the $0.30 reservation by $0.208300**: one
control (a 400-line test migration) cost $0.4045 alone, twelve times the population mean — a
mean is the wrong basis when one unit can exceed the whole reservation.

## 3. The two shadow findings: **both false**

[Report](acceptance/2026-09-05-shadow-adjudication.md), $0.00, no model. At the reviewed head
`7245680bf493`, four exhaustive word-boundary greps over the whole worktree:

- `institutional_flow_reading` — **no references.** The three near-hits are
  `AnalysisService._institutional_flow_reading`
  (`services/analysis_api/src/us_stock_helper_analysis_api/service.py:147`, `:216`), a
  *different, new* private method, and a test named after it
  (`services/analysis_api/tests/test_analysis_service.py:369`).
- `FACTOR_INSTITUTIONAL_FLOW`, `INSTITUTIONAL_FLOW_ABSTENTION_VERSION` — **no references.**
- `FactorSnapshot.institutional_flow` — **no such field.** `FactorSnapshot` has `symbol, as_of,
  macro, geopolitics, fundamentals` (`information_layer/factors/provider.py:48`) and
  `PublicFactorProvider.snapshot` (`:89`) passes exactly those.
- The surviving `institutional_flow` mentions belong to other objects, each defined and populated
  in the same commit: `evidence_provider.py:113/:124/:127`, `gateway_provider.py:145`,
  `service.py:234`, `__main__.py:26`, `analysis_core/…/scoring.py:285`,
  `decision_engine/…/engine.py:151`, a comment at `factors/base.py:34`, and tests.

**The single line you asked for: the commit deleted the function, its constants, its export, the
`FactorSnapshot` field and every call site in the same diff — nothing dangles, so both surviving
shadow findings are false, and v4 clause (c) drawers them both.** In the README table.

## 4. Green is author-visible, and its adjudicator has met a model (D-133)

[Report](acceptance/2026-09-05-green-channel.md), **$0.069115**.

- **Adjudicator vs. the real default model, before anything shipped**: 10 findings, model told
  nothing about the rule. **7 published, 3 dropped (all for `likely`), every published sentence
  named a coordinate — 0 coordinate-free prose admitted.** Nothing failed to be stopped, so
  nothing was repaired; a denylist's blind spot was closed anyway (`describe` now refuses prose
  naming no coordinate), and re-measured: 10 asked, 6 dropped, **0 coordinate-free admitted, 0
  refused for the new rule.** Across 20 calls the coordinate rule never fired — a guard, not a
  measured fix.
- **The channel**: ≤ 2 notes per pull request, marked `structural`, own section, claim line
  coordinates-and-measure only, model advice a separate labelled paragraph.
- **One real comment** on [#9](https://github.com/IcantFind-a-username/Attest/pull/9) (closed,
  branch deleted): inline comment anchored at `_green_probe.py:19`, `Category: structural`, "no
  receipt backs it"; summary carries green in its own section and red still says it verified
  nothing. **The probe found a wiring defect**: the model's sentence was dropped and *nothing
  recorded why*, against D-130's stated property. `run_ci` now writes a `structural_note` ledger
  row (`advice_published`, `refusal`) per note. Comment bodies verbatim in the report §4.

## 5. Not done, and why

- **The other 51 `G-NULL-001a` controls were not re-run under v4** (~$1.70). The instruction
  named the remaining 7; re-running the rest is what turns n = 7 into n = 58 and is owner item 1.
- **Clause (c) is not narrowed.** It matches a symbol name as a word, so `readings`, `decision`,
  `snapshot`, `_reason`, `main` match prose about something else; an unknown fraction of the 42
  corpus hits is false. Over-drawering is the safe direction and narrowing moves what publishes,
  so it is reported, not tuned.
- **The 48 value receipts are not adjudicated.** "Certifies under v3, not under v4" says nothing
  about which were real defects; only `jinja` and `urllib3` carry certain labels, and v4 gets
  both right.
- **No `G-SEC-002`, no gate level, no yellow, no new-code pricing, no scheduler.** `G-SHADOW-001`
  is advanced but not satisfied — the adjudicator in §3 is this project.
- **The four v2 receipts whose observer inputs are not on this host** were skipped, not counted.

## 6. For the owner — three items

1. **Re-run the other 51 `G-NULL-001a` controls under v4, ~$1.70 — yes?** Default **yes**. It is
   the only way to state a usable bound: n = 58 with 0 wrong publications gives a 95% upper bound
   of ~5%, against tonight's ~43%. Population, cutoff, seed and quota unchanged; the same stop
   rule applies.
2. **Narrow clause (c) so a generic symbol name is not intent — yes?** Default **yes**, by the
   same logic as clause (b): require the named symbol to be distinctive (a length floor plus a
   common-word exclusion, or a backticked/dotted mention). It moves what publishes, so it is
   yours; today (c) drawers 42 of 48 and an unknown share of that is vocabulary.
3. **Adjudicate the 48 drawered value receipts by hand — yes?** Default **yes**, on a sample of
   ~12. It is free of API spend and it is the only measurement that can say whether v4 is right
   or merely silent. Without it "0 of 48" is a fact about the rule and not about defects.
