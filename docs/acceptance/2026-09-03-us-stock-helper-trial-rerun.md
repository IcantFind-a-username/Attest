# Paid check (a): us-stock-helper trial A/B re-run after owner fixes 1-5

Date: 2026-09-03. Corpus: `.attest/corpora/us-stock-helper/` cloned from the owner's GitHub
(`feature/iphone-demo` at `9fc9408`, the default branch, which contains both fixes; `main` on
the remote does not). Heads: `trial-a` = revert of the source change of `375ab52` (tests
kept, `259f7ee`); `trial-b` = revert of the source change of `3f6b67b` (tests and docs kept,
`07485be`). Base: `feature/iphone-demo`. Runner: `attest review --base feature/iphone-demo
--k 4 --budget 1.0` with the local differential stage (fix 5), default model
`claude-sonnet-5`, `ATTEST_PROJECT_PYTHON` = the operator's service virtualenv (CPython
3.11.5 with the eight service packages installed editable from the operator's own checkout —
fix 3 makes the corpus tree's `services/*/src` win over those installs, and every head run
recorded executed changed lines). Evidence level: two cases, developer-directed; not a
recall or precision estimate.

## Trial B — revert 3f6b67b (nasdaq halt timestamps): published with a receipt

| item | result |
|---|---|
| candidates | 6 (4/4 samples intact, 0 no-text, 0 abstentions) |
| eligible | 6 (regression) |
| certified | 3 (`9ed6a71d7b`, `52403c1e42`, `f118070241`) |
| published | 1 — `9ed6a71d7b` `nasdaq.py:50`: published_at/updated_at fall back to the RSS `<pubDate>` (midnight ET), backdating halts; head FAIL 3/3, base PASS 3/3, `test_repro.py::test_nasdaq_halt_published_at_uses_halt_time_not_midnight_pubdate`, receipt `ae420a7074c9…` |
| suppressed | `52403c1e42` same defect as the published finding; `f118070241` below the family threshold (m=6, m/α=60; its e-value 58) |
| unfaithful | 3 (`b5344879c3`, `7392f309ff`, `6ed066d6b8`: fail on base as well) |
| said the wrong thing? | no: the published claim is exactly the defect 3f6b67b fixed; the generated test asserts the halt time (not midnight) like the project's own `test_the_event_timestamp_is_the_halt_time_not_midnight` |
| spend / time | $0.2261 / 83.8 s |

This is the first receipt-backed publication from `attest review` (owner fix 5's RED).

## Trial A — revert 375ab52 (breadth conclusion sample wording): correct candidate, no receipt

Five runs, each after a code change (never a retry on the same code):

| run | what changed | outcome | spend |
|---|---|---|---|
| 1 | fixes 1-5 | 1 candidate (4/4 samples, the 375ab52 defect); generated test imported `test_analysis_service` by module name → `ModuleNotFoundError` on both trees (unfaithful) | $0.0757 |
| 2 | projects' `tests/` directories on the import path; generator told helpers are importable | test imports and constructs correctly (`MarketBriefUniverseConfig(breadth_symbols=…)`, `OHLCVBar(timestamp=…)`), asserts `entry["available"] is True` with a 3-symbol universe → False on both trees | $0.0249 |
| 3 | nearest test module = the one named after the anchored file (`test_market_brief.py`) | same shape; the helpers section had been truncated at the 12,000-char bound | $0.0246 |
| 4 | context bound 20,000; helpers ranked by use; helper classes included; sections reordered | test now uses `UniverseProvider`, `_breadth_bars`, `_brief_with_universe`, `_driver` like the project's tests, 1-of-2 symbols → `available` False on both trees | $0.0276 |
| 5 | two representative tests shown | same, 4-of-5 symbols → `available` False on both trees | $0.0284 |

Every run: candidate correct (the sample-size wording defect), eligible, generated, executed
on head with changed lines traced (executed lines > 0), never published. The remaining gap is
semantic: the breadth driver reports `available` only above a minimum universe the model does
not infer (the project's own regression test uses 60 configured / 57 eligible symbols); a
sixth run on unchanged code would be an outcome-aware retry and was not made. Silence, with
the reason `unfaithful test` in the run status (item 6).

## Spend

Trial A $0.1812 (five runs) + trial B $0.2261 = $0.4073 of the $1.00 reservation; settled in
`DEVSPEND.md`.

## What the two cases say about the five fixes

- fix 1: 12/12 proposal samples and 7/7 generations returned text (the 2026-09-02 trials had
  8/8 generations without text);
- fix 3: `services/*/src` and the flat `information_layer` layout both imported from the
  corpus tree with the operator's editable installs present; executed changed lines were
  recorded on every head run;
- fix 4: constructor and helper usage is correct from run 2 on; the residual failure is a
  behavioural threshold, not an API guess;
- fix 5: `attest review` published a receipt-backed finding on trial B and reported its own
  silence on trial A.
