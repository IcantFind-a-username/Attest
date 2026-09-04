# The two surviving E-04 shadow findings, adjudicated by static search: **both are false** (owner instruction 3)

The two findings that survived the v3 re-judging ([handoff
2026-09-04c §3](../overnight-handoff-2026-09-04c.md)) are the only shadow output this project
has ever carried far enough to be worth checking. They are checked here by exhaustive static
search, offline, **$0.00**, no model.

## The claim, and the revision it is about

Both receipts anchor on `services/information_layer/information_layer/factors/unsupported.py`
in `us-stock-helper`, task `20260904-041419-54f57b04`, base `7ddc5a4e1986` → head
`7245680bf493` (*"feat: wire institutional-capital factor from gateway participation and
holdings data"*, 16 files, +1188 −91). The head commit deletes `institutional_flow_reading`,
`FACTOR_INSTITUTIONAL_FLOW`, `INSTITUTIONAL_FLOW_ABSTENTION_VERSION` and
`_INSTITUTIONAL_FLOW_DETAIL` from that module. The two findings say, from two ends:

1. `unsupported.py:27` — a caller still importing `institutional_flow_reading` fails at import
   time;
2. `unsupported.py:49` — `FactorSnapshot.institutional_flow` has no populator left, so a
   snapshot builder outside the diff raises `AttributeError`.

## The search, at head `7245680bf493`

Four exhaustive greps over the whole worktree (excluding `.git`), word-boundary anchored:

| what | pattern | references |
|---|---|---|
| the deleted function | `(^\|[^A-Za-z0-9_])institutional_flow_reading([^A-Za-z0-9_]\|$)` | **none** |
| the deleted constants | `FACTOR_INSTITUTIONAL_FLOW\|INSTITUTIONAL_FLOW_ABSTENTION_VERSION` | **none** |
| the attribute | `\.institutional_flow([^A-Za-z0-9_]\|$)` | 6, **none on a `FactorSnapshot`** |
| the keyword | `(^\|[^A-Za-z0-9_])institutional_flow[ ]*=` | 18, **none on a `FactorSnapshot`** |

`FactorSnapshot` at head has exactly five fields — `symbol`, `as_of`, `macro`, `geopolitics`,
`fundamentals` — and `PublicFactorProvider.snapshot` constructs it with those five and no more
(`factors/provider.py:48` and `:89`). Every surviving `institutional_flow` reference belongs to
a different object, and each is defined and populated inside the same commit:

| file:line | what it actually is |
|---|---|
| `analysis_api/src/us_stock_helper_analysis_api/service.py:147, :216` | `AnalysisService._institutional_flow_reading`, a **new private method** of the analysis service — a different symbol, not the deleted module function |
| `analysis_api/src/us_stock_helper_analysis_api/service.py:234` | `DecisionInputs(institutional_flow=institutional.value …)` — the new provider's value, not a snapshot field |
| `analysis_api/src/us_stock_helper_analysis_api/evidence_provider.py:113, :124, :127` | `institutional_flow: InstitutionalFlowSource`, a field of the **evidence provider** |
| `analysis_api/src/us_stock_helper_analysis_api/gateway_provider.py:145` | `institutional_flow_inputs_for`, new |
| `analysis_api/src/us_stock_helper_analysis_api/__main__.py:26` | wiring `GatewayInstitutionalFlowProvider` |
| `analysis_core/us_stock_helper_core/scoring.py:285` | `FeatureSet(institutional_flow=context.institutional_flow)` — a scoring context |
| `decision_engine/decision_engine/engine.py:151` | `institutional_flow=inputs.institutional_flow` — `DecisionInputs` |
| `information_layer/factors/base.py:34` | a comment about `DecisionInputs.institutional_flow` |
| tests in `analysis_core`, `decision_engine`, `analysis_api`, and `apps/mobile` | all constructing `DecisionInputs`/`FeatureSet`/i18n copy |

## Verdict

**No reference to either deleted name survives, and no `FactorSnapshot.institutional_flow`
exists to access.** The commit removed the function, its constants, its export in
`factors/__init__.py`, the `FactorSnapshot` field, and every call site — in the same diff, and
it says so in the module docstring it rewrote. **Both findings are false positives.**

They are also exactly what D-132 clause (c) is for: the same diff rewrites
`unsupported.py`'s module docstring to explain the removal and deletes the tests that named
`institutional_flow_reading`, and the v4 replay drawers both receipts on that evidence.

## Limits

- Static search finds textual references, not dynamic ones. A `getattr(snapshot,
  "institutional_flow")` built from a string, or an out-of-repository consumer, would not
  appear. Nothing of that shape was found either, and this repository is a monorepo carrying
  its own consumers.
- This adjudicates two findings. It says nothing about the five that v3 already drawered, and
  nothing about a shadow *rate*.
- The adjudicator is this project. `G-SHADOW-001` still asks for someone independent of the
  product, and this does not satisfy it.
