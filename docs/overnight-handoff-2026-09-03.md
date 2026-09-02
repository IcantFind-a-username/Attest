# Overnight handoff — 2026-09-03 (window from `316a84f`)

Status: **mainline X-01 → X-02 → V-03 done with the five fixes, items 6-11 and the cost
work; held-out and natural null measured; the natural null published once, so every paid
run is stopped and the owner's discriminator decision gates the next paid run.**

## Steps (one commit each unless noted)

| step | commit | RED |
|---|---|---|
| DEVSPEND trial rows (owner answer 1; pushed) | `cca77d4` | — |
| step 0: tracer confined to the reproduction window | `8c3513e` | tracer absent at import, present in the test |
| X-01: nonced, content-addressed controller/executor protocol | `4788d1d` | envelope answering another nonce rejected |
| fix 1: thinking off for structured calls; no-text reported honestly | `cf1d60d` | thinking-only response → `generation_no_text` |
| fix 3: tree import roots first; shadowed anchor named | `e59aab8` | same-name installed copy: head executes > 0 lines |
| fix 2: no-text vs true abstention counted apart; D-082 recomputed | `db6d66f` | notes carry both counts |
| fix 4: signatures + nearest test module helpers (+ amendment `0c6d012`) | `4cebf25` | context shows `__init__` signature, fixture, helper |
| fix 5: `attest review` runs the differential stage; 40-hex ids | `505023b` | short base id → published receipt with full ids |
| attempt cache bound to model/call parameters | `d03687c` | — |
| tests directories on the reproduction import path | `8e94b42` | helpers importable by module name certify |
| item 6: run status on every run | `ac3343c` | silent CI comment shows counts + reasons |
| item 9: `attest stats --drawer` | `0753874` | unverified candidate visible with its reason |
| item 10: wording without statistical terms | `c4bd53d` | display only |
| item 11: TypeScript executor decision package | `c72bec5` | docs |
| instruction 3: prompt caching, staggered fan-out, cache pricing | `c17c46e` | 2nd sample `cache_read_input_tokens` > 0; cheaper (real API) |
| instruction 4: `package-cache` strategy (comparison only) | `2931753` | — |
| X-02: linux-container-v1 + environment bootstrap (item 8) | `6a89d83` | real-container RED suite |
| V-03: fresh state, controller seal, `attest verify --bundle` | `c638714` | stale run record rejected offline |
| item 7: finding presented as its runnable test | `fdff273` | comment's test+command fail on head, pass on base |
| L-01 owner-free parts: kill switch + operations docs | `c991e1d` | base disabled, head re-enabled → zero calls |
| image rule: `requires-python` lower bound (E-01 bootstrap) | `8b93b75` | — |
| image rule: scm pretend version, nested projects best-effort (held-out bootstrap) | `874e270` | Dockerfile text under test |
| held-out + natural-null reports, D-100/D-101, spend, README numbers | `e505291` | docs |

Gates (detached worktree, `pytest --cov` + ruff + mypy): step 0 793 s / 91.59 %; X-01 909 s /
91.81 %; fixes tip 926 s / 92.14 %; items tip 932 s / 91.89 %; cache tip 947 s / 91.79 %;
X-02..item 7 tip (`fdff273`) 1093 s / 91.45 % (the machine was running the held-out
containers alongside); `8b93b75`: 1083 s / 91.55 %; reports tip `e505291`: 1067 s / 91.55 %. The
15-minute target holds on an idle machine (step 0) and not under the container runs.

## Held-out (E-02, step 13) — one pass, 68/69, stopped by the E-01 rule

| population | n | candidates | eligible | certified | published | samples | truncated | boundary hits | cache read share | spend |
|---|---|---|---|---|---|---|---|---|---|---|
| defects | 29 | 67 | 62 | 7 | 7 | 116 | 0 | 0 | 75 % | $1.2309 |
| controls | 39 | 12 | 6 | 0 | 0 | 164 | 0 | 0 | 72 % | $0.5590 |

Certified on 5/29 defects (all published), 0/39 control false publications, precision of
the published set 5/5 cases, recall 5/29 (on the 11 defects whose environment built: 5/11).
Silence on 24/29: 45 reproductions `environment bootstrap failed` (all 14 pytest and 4
pylint cases — fixed in `874e270`, not re-run), 4 unfaithful tests, 1 collection failure.
Truncation 0/280, diff-boundary hits 0 → the proposal bound stays at 3,200. G-SEM-002 binding
pilot (no model call): 18/18 adversarial tests rejected, 5/5 real reproductions bound.
Report: [docs/acceptance/2026-09-03-e02-heldout.md](acceptance/2026-09-03-e02-heldout.md).

## Natural null (E-01, step 14) — 1/20 published

| class | commits | eligible candidates | verifications | published |
|---|---|---|---|---|
| refactor / test-only | 7 | 9 | 9 | 0 |
| docs-only | 6 | 0 | 0 | 0 |
| feature | 7 | 31 | 31 | **1** (`3a32c92`) |

The publication is a valid, sealed, line-bound receipt (head FAIL 3/3, base PASS 3/3 in the
container) for an *intended* new rejection: the commit adds a banned-verb guard to an
existing constructor and the generated test feeds it a phrase containing the banned verb
verbatim, calling it legitimate copy. The receipt proves "head rejects an input base
accepted"; the published words claimed a defect. Root cause: the regression-only
differential kernel cannot tell an intended rejection on an existing definition from a
regression (D-100, register row `RISK-INTENT-01`). Per the owner's rule every paid run
stopped; nothing was re-run. 25 of 40 verified candidates on the feature commits were cut
by the $0.25 per-PR budget. Report:
[docs/acceptance/2026-09-03-e01-natural-null.md](acceptance/2026-09-03-e01-natural-null.md).

## Trial A/B (paid check a) and the dev slice (paid check b)

Trial B (revert `3f6b67b`): 3 certified, 1 published — the exact defect the revert
reintroduced, receipt-backed; trial A (revert `375ab52`): silent, the generated test was
unfaithful. Dev slice after fixes 1-5: 6 certified on 5/8 defects, 5 published, 0/8 control
publications, 0 no-text samples. Instruction 3 RED on a real call: samples 2-4 read 3,901
cached tokens, review $0.0248 vs $0.0439. Instruction 4: `r01` 4 certified at $0.06/PR vs
`package-cache` 2 certified at $0.22/PR — `r01` stays the default.

## Spend

| item | spent | reserved |
|---|---|---|
| paid check (a) trial A/B | $0.4073 | $1.00 |
| paid check (b) dev slice | $0.8511 | $1.20 |
| instruction 3 RED (real API) | $0.0455 | — |
| instruction 4 comparison | $2.2399 | $2.50 |
| X-02 container smoke | $0.0239 | — |
| E-02 held-out | $1.7899 | $6.00 |
| E-01 natural null | $1.5280 | $1.90 |
| G-SEM-002 binding pilot | $0.00 | — |
| **window** | **$6.8857** | cap $12 |
| **cumulative** | **$18.8723** | cap $23.50 / $30 |

## Questions for the owner (yes/no, default in brackets)

1. Adopt discriminator (a) for `RISK-INTENT-01` — a `new_rejection` result class (head
   failure is an exception raised from a changed line) that goes to the drawer with a
   question to the author unless the rejected input is a literal present in the reviewed
   tree — instead of (b) publishing such receipts under an exact-wording evidence class? [yes]
2. Lift the stop for one bounded re-run: the 18 bootstrap-failed held-out defects from a
   checkout at `874e270` or later (`heldout_run.py run --defects-only --only …`, ≈ $0.60),
   the E-01 corpus untouched? [yes]
3. Keep `r01` as the default context strategy after the instruction-4 comparison? [yes]
