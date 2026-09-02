# Handoff — 2026-09-03, second window (from `104ed35`): owner decisions 1-3

Status: **decision 1 landed (D-102) and replayed on the real receipts; the stop is lifted;
the supplementary held-out run of the 19 bootstrap-failed defects ran from a fixed checkout
and is tabulated apart from the one-time table; E-04's collector and protocol v1 landed and
its first stratum ran; `r01` and the 3,200 bound stay.**

## Commits (one step each)

| step | commit | RED |
|---|---|---|
| D-102 intent discriminator: `behavior_change` class, base-tree witness, drawer label, receipt v4, offline re-judgement; README numbers; held-out erratum | `19920c6` | real bundles: `3a32c92` → drawer, 7/7 held-out candidates stay regression; suite: planted guard silent + labelled, witnessed variant publishes, verifier rejects a bundle that lost its witnesses |
| E-04 collector, fail-closed preflight, protocol v1 frozen | `5fc03fa` | every refusal by reason; shadow on/off identity at zero cost |
| E-04 stratum v1 result, D-103; `heldout_run.py --code` semantics | `50c21d2` | docs |
| D-104 shadow guard: dotted names from the tree roots | `69921e0` | stdlib `logging` beside `pkg/logging.py` is not a shadow; fix-3 REDs still pass |
| supplementary held-out table, D-101 amendment, spend, this handoff | `506aae1` | docs |
| D-049 review pass: five reproduced fail-open/crash paths in the discriminator fixed (D-102 amendment) | (below) | observer REDs for F1-F5; executor REDs for a handled raise and a surrogate message; replay v2: same eight verdicts |

Gates: full `pytest --cov` + Ruff + Mypy + `git diff --check` on the working tree after D-102
(1 real failure fixed — the benchmark status map made total over the new class; the M-01 probe
failures were its clean-tree guard on the dirty tree and pass on the committed tree); the
detached-worktree gate on `69921e0` is recorded at the end of this file.

## Decision 1 — the discriminator (D-102)

Rule as implemented: on every head run the tracer records the first frame of the anchored file
each exception passes through; an exception from a `raise`/`assert` statement on a changed
line is a **behavior change**. Its rejected inputs are the generated test's string literals
that reached the raising frame. The receipt publishes as `behavior_change`, worded as what it
proves and asking the author to confirm, only when every such input occurs verbatim in the
**base** tree's tests, fixtures, examples or documentation; otherwise the differential DEFERs
into the drawer as "behavior change confirmed, intent unknown" (行为变化已证实，意图未知) and buys
nothing. The status shows only the label; the ledger and bundle keep the observation. Report:
[`docs/acceptance/2026-09-03-d102-intent-replay.md`](acceptance/2026-09-03-d102-intent-replay.md).

| replay (container, no model call) | outcome |
|---|---|
| `3a32c92` / `7ecf2fb275` (E-01 publication) | `deferred`, `behavior_change`, `ValueError` from the `raise` at patterns_shapes.py:349, 3 rejected inputs, **0 witnesses** → drawer |
| 7 held-out candidates on 5 defects (requests 1142, 1921, 5414; pylint 4551, 4604 ×3) | all `regression_reproduced`, unchanged |

**D-049 review pass (one bounded pass, findings fixed only where reproduced):** F1 the
tracer's 32-record cap could evict the rejecting raise (now 256 distinct records, duplicates
suppressed, a `truncated` flag that DEFERs); F2 an unparsable anchored file classified every
raise as a crash (now DEFERs when an origin lies on a changed line); F3 substring matching
made a dictionary key inside a message an "input" and `requirements.txt` a witness (now:
equality with a local or quoted in the message; witnesses must quote the literal; data files
count only inside test/fixture/example/doc directories); F4 a raise the changed code handled
itself decided the class (now the tracer records escape, and the raise must agree with the
JUnit failure type or a test-level failure); F5 a lone surrogate in a message crashed the
hook (replaced before writing). Replay v2 on the eight real receipts: same verdicts.

Residual (`RISK-INTENT-01`): a rejection raised by an unchanged helper called from a changed
line is still a regression; inputs built by the test at run time (f-strings, concatenation)
are not identified and such receipts stay in the drawer; a literal present in base tests as a
negative example is not distinguished (mitigated by requiring every identified input to be
witnessed and quoted).

## Decision 2 — the supplementary held-out run (19 cases, `.heldout-rerun`)

Product code `5fc03fa` from a detached worktree (`--code`), pilot script from the primary
checkout (the strict ledger refuses a symlinked corpus; two attempts failed before any model
call and the driver's `--code` semantics were fixed in `50c21d2`). Results `*.heldout-rerun.json`,
tabulated apart from the one-time table and never merged into it (different code, not
pre-registered). Report section: [held-out report](acceptance/2026-09-03-e02-heldout.md) §
"Supplementary run after the bootstrap fix".

| population | n | candidates | eligible | certified | published | samples | truncated | boundary hits | cache read share | spend |
|---|---|---|---|---|---|---|---|---|---|---|
| defects (supplementary) | 19 | 50 | 45 | 12 | 11 | 76 | 0 | 0 | 75% | $0.8913 |

per defect: certified on 10/19 (pylint 4/4, pytest 6/15), published on 10/19; environment
bootstrap failures **0/19** (the `874e270` rule built every image); silence 9/19 — 24 unfaithful
reproductions, 2 unbound (one of them the D-104 false positive on `pytest-dev__pytest-10051`,
the stdlib `logging` package reported as a shadow of `src/_pytest/logging.py`; the other,
`pytest-5787`, exercised none of the changed lines), 2 collection failures, 2 new-code
candidates (typed abstention), 1 generation cut by the $0.25 per-PR budget; one certified
candidate on `pytest-5631` suppressed as the same defect as a published one; no candidate was
classified as a behavior change. Truncation 0/76, diff-boundary hits 0.

| case | candidates | eligible | certified | published | failures | spend |
|---|---|---|---|---|---|---|
| pylint-dev__pylint-6903 | 1 | 1 | 1 | 1 | - | $0.0217 |
| pylint-dev__pylint-7080 | 1 | 1 | 1 | 1 | - | $0.0126 |
| pylint-dev__pylint-7277 | 1 | 1 | 1 | 1 | - | $0.0189 |
| pylint-dev__pylint-8898 | 1 | 1 | 1 | 1 | - | $0.0181 |
| pytest-dev__pytest-10051 | 1 | 1 | 0 | 0 | unbound: stdlib `logging` reported as a shadow (D-104) | $0.0193 |
| pytest-dev__pytest-10356 | 3 | 3 | 2 | 2 | unfaithful 1 | $0.0709 |
| pytest-dev__pytest-5262 | 1 | 1 | 1 | 1 | - | $0.0162 |
| pytest-dev__pytest-5631 | 2 | 2 | 2 | 1 | 1 suppressed: same defect | $0.0285 |
| pytest-dev__pytest-5787 | 10 | 9 | 0 | 0 | unfaithful 8, unbound 1 | $0.1646 |
| pytest-dev__pytest-5840 | 9 | 8 | 0 | 0 | unfaithful 6, new-code 1, budget 1 | $0.1780 |
| pytest-dev__pytest-6197 | 5 | 2 | 0 | 0 | unfaithful 1, new-code 1 | $0.0523 |
| pytest-dev__pytest-7205 | 1 | 1 | 0 | 0 | unfaithful 1 | $0.0119 |
| pytest-dev__pytest-7324 | 2 | 2 | 1 | 1 | unfaithful 1 | $0.0328 |
| pytest-dev__pytest-7432 | 2 | 2 | 0 | 0 | unfaithful 2 | $0.0505 |
| pytest-dev__pytest-7490 | 4 | 4 | 0 | 0 | unfaithful 4 | $0.0635 |
| pytest-dev__pytest-7521 | 1 | 1 | 1 | 1 | - | $0.0201 |
| pytest-dev__pytest-7571 | 2 | 2 | 0 | 0 | collection 1, unfaithful 1 | $0.0428 |
| pytest-dev__pytest-7982 | 1 | 1 | 1 | 1 | - | $0.0189 |
| pytest-dev__pytest-8399 | 2 | 2 | 0 | 0 | unfaithful 1, collection 1 | $0.0497 |

Spend **$0.8913 against the $0.60 reservation** (over by $0.2913): the pytest cases carried
2-10 candidates each at the $0.25 per-PR budget and the driver had no cumulative cap; `--cap`
was added afterwards. The window cap ($3) holds.

## Decision 3

`r01` stays the default context strategy (`config.py`); the proposal bound stays 3,200
(0 truncation, 0 boundary hits on the held-out pass). No code change was needed.

## E-04 (mainline step 15), first stratum

Collector, preflight and protocol v1 (D-103) landed; the only prospective traffic in the
authorized population was Attest's own two commits: 22 candidates, 0 eligible (10 Markdown
anchors, 12 new-code), 0 reproductions, **0 shadow findings**, $0.1694. The 23-file commit had
1 of its 13 change units read at the $0.25 per-unit budget — budget-bound silence, the E-01
mechanism again. Report:
[`docs/acceptance/2026-09-03-e04-prospective-v1.md`](acceptance/2026-09-03-e04-prospective-v1.md).

## Errata found this window

- Held-out report: bootstrap-failed defects are **19** (15 pytest + 4 pylint), not 18; built
  **10**, certified on **5/10**, not 5/11 (erratum section in the report; D-101 amended). The
  owner's "5/11 (建成)" therefore reads 5/10 in the README.
- Natural null: the plan, the ledger and the report count **20** commits (1 publication); the
  owner's message said 1/19. The README says 1 of 20.

## Spend

| item | reserved | spent |
|---|---|---|
| supplementary held-out run (19 defects) | $0.60 | $0.8913 (over by $0.2913) |
| E-04 stratum v1 | $2.00 | $0.169422 |
| D-102 replay, D-104 | — | $0.00 |
| **window** (cap $3) | | **$1.0607**; cumulative $19.932974 of $30 |

## Questions for the owner (yes/no, default in brackets)

1. E-04 next stratum: raise the per-unit budget for large commits (or order source units
   before documentation) so more than one change unit is read? [yes — order source first,
   keep $0.25]
2. Re-run `pytest-dev__pytest-10051` (and any other case DEFERred by the D-104 false positive)
   under `69921e0` as a second supplementary row, ≈ $0.05? [yes]
3. Adjudication for E-04's two units and future strata needs a product-blind reviewer; name
   one, or accept `INSUFFICIENT` until the pilot? [accept]
