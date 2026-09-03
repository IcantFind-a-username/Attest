# Real-traffic corpus: 20 defect pairs and 50 controls from the owner's repositories

**Status: approved as option A and RUN on 2026-09-03 (owner decision 1 of 2026-09-03g).**
43 of the 70 cases ran; the [result](../acceptance/2026-09-03-real-traffic-corpus.md) supersedes
every estimate below. **This file is kept as the frozen population it was**, including two
selection defects it turned out to have — control #3 (`445c5a1`) is a planted regression from
the 2026-09-03d Action drill rather than traffic, and the control strata classify commits by
what they are *about* rather than by any evidence that they are defect-free. §6's price model
was about half the measured one.

## 1. Why this population and not another

Every recall number this project has is from SWE-bench Verified, a constructed corpus. The
one real-traffic receipt it has produced (2026-09-03, `us-stock-helper` `d7be758` →
`8ed7811`) came from a population of **one pair**. This plan is the smallest population that
could say anything about real traffic: 20 defect pairs across three repositories, and 50
controls from the same repositories built the same way.

## 2. How each pair is built (D-116)

For a repairing commit `F`: **head = `F^`, base = `F`**. The head has the defect, the base
has the fix; the reviewed diff is the fix, reversed. A pair enters the run only when `F`'s
**own human-written tests discriminate it** — copied onto both sides and executed there, at
least one test fails on head and passes on base. That check is free, runs before any paid
call, and any pair that fails it is dropped and reported as dropped, not replaced.

## 3. Selection rule, frozen with this file

Mechanical, applied to every `fix:`-prefixed non-merge commit in each repository:

1. it **modifies** at least one pre-existing non-test `.py` file (the only shape D-102's
   regression-only kernel can certify);
2. it ships at least one `test_*.py` of its own (so the discrimination check in §2 has
   something to run);
3. newest first by commit date, until the repository's quota is full:
   **Attest 8, `us-stock-helper` 8, `Corum` 4**. Those quotas are what the repositories have:
   100, 61 and 4 commits pass filters 1–2 respectively, and `Corum` is the whole of its
   eligible history.

Controls are stratified rather than taken newest-first, because a docs-only commit is silent
for free and 43 of them would prove nothing: **20 refactor** (they modify source Python and
are the only controls that can reach a reproduction), **15 test-only**, **15 docs-only**,
round-robined across the three repositories, newest first inside each.

**Disclosure:** eight of the twenty defect pairs are Attest's own commits, and the newest of
them were written in the same session that wrote this plan. The product reviewing its own
repairs is a real conflict of interest; it is disclosed here, the per-repository results are
reported separately, and the headline number is the two outside repositories.

## 4. The 20 defect pairs

| # | repo | fix commit (base) | head = fix^ | one line |
|---|---|---|---|---|
| 1 | `Attest` | `b764cfb926` | `04a86b25a4` | fix(review): a provider error never carries a credential into visible text |
| 2 | `Attest` | `241bb6fa67` | `9b610f6a5a` | fix(review): the discovery share bounds breadth, not the first unit |
| 3 | `Attest` | `61d9695453` | `ad4c5fe1e3` | fix(execution): cap an image build at the verification budget, reuse by image id |
| 4 | `Attest` | `d62bcd6327` | `e0867eb188` | fix: an unattempted certification names the profile the runs actually used |
| 5 | `Attest` | `34affaf7a6` | `e002bd6679` | fix: every way the environment bootstrap fails is typed, and the image probe is bounded |
| 6 | `Attest` | `9df938f8aa` | `260e8d9c51` | fix: an image build that times out is a typed bootstrap failure, not a traceback |
| 7 | `Attest` | `3ace7e52d0` | `17d5c770c7` | fix: the CLI help must point an operator at the offline bundle verifier |
| 8 | `Attest` | `0fee3a95e5` | `7c8de5c624` | fix: E-04 preflight — selection must precede its own outcome, not every outcome |
| 9 | `us-stock-helper` | `ff77bf4d14` | `4aa74209ad` | fix(market_gateway): capital_flow/institutional_holdings 乱序行不再静默重排，改为显式报错 |
| 10 | `us-stock-helper` | `30c49d7e56` | `6c724c1e19` | fix(market_gateway): K线跨页/跨行乱序不再静默重排，改为显式报错 |
| 11 | `us-stock-helper` | `3f6b67b0b6` | `fa85b21778` | fix: stamp nasdaq halts at the halt time, not midnight |
| 12 | `us-stock-helper` | `ead0bd75d4` | `07a6946b7f` | fix: stop republishing multi-party filings as fake revisions |
| 13 | `us-stock-helper` | `4ef2226bcf` | `801fb292ce` | fix: remember what each feed already published across restarts |
| 14 | `us-stock-helper` | `4b1ad18ab9` | `381c0a051c` | fix(analysis_core): use fsum in moving_average_series to kill sum() order noise |
| 15 | `us-stock-helper` | `2d4a0d8ab0` | `8ed78113d1` | fix: serve the ma5 break rule, not a stale touch-bar number |
| 16 | `us-stock-helper` | `8ed78113d1` | `d7be758c2f` | fix: only in-force confirmed patterns vote in the score |
| 17 | `Corum` | `f84fbb4699` | `6eba742235` | fix: make dependence shrinkage evidence-aware |
| 18 | `Corum` | `c12fc13559` | `ba8fddb952` | fix: reject unrepresentable numeric metadata |
| 19 | `Corum` | `ba8fddb952` | `515998fac1` | fix: handle overflowing real validation |
| 20 | `Corum` | `515998fac1` | `5be583d614` | fix: validate consensus numeric metadata |

## 5. The 50 controls

| # | repo | commit | stratum | one line |
|---|---|---|---|---|
| 1 | `Attest` | `0d0e098b46` | refactor | test: the M-01 probe follows TMPDIR instead of a macOS path |
| 2 | `us-stock-helper` | `ab02a62ac1` | refactor | test: verify sectioned snapshots across live watchlist |
| 3 | `Attest` | `445c5a1e28` | refactor | refactor: simplify path normalisation in the benchmark matcher |
| 4 | `us-stock-helper` | `1b8cc4aab1` | refactor | test: assert the copy the product actually ships |
| 5 | `Attest` | `506aae1a13` | refactor | docs: supplementary held-out run (owner decision 2), erratum, spend, and the ... |
| 6 | `us-stock-helper` | `45674d5636` | refactor | test: prove the real market mobile slice |
| 7 | `Attest` | `50c21d2ab6` | refactor | docs: E-04 stratum v1 result, D-103, and the supplementary held-out run's fix... |
| 8 | `Attest` | `7838294beb` | refactor | style: lint the corpus drivers |
| 9 | `Attest` | `a1624d2813` | refactor | chore: pilot builds without a host virtualenv; reserve the held-out and natur... |
| 10 | `Attest` | `c17c46ef5b` | refactor | perf: cache the shared prompt prefix, stagger the fan-out on the first token,... |
| 11 | `Attest` | `c4bd53df8e` | refactor | refactor: user-facing wording without statistical terms |
| 12 | `Attest` | `8c3513eb9d` | refactor | perf: confine the V-02 line tracer to the reproduction window |
| 13 | `Attest` | `47229a86cd` | refactor | chore: M-01 probe and its tests follow the product's publication policy |
| 14 | `Attest` | `3cbe421854` | refactor | chore: let the M-01 probe's aggregate restate the run's own counts |
| 15 | `Attest` | `859c3b4534` | refactor | chore: make the M-01 probe's product guard follow the family policy |
| 16 | `Attest` | `e23e333692` | refactor | chore: report pilot certification per defect and per candidate |
| 17 | `Attest` | `5520d61bf7` | refactor | chore: choose the pilot interpreter from the project's declared Python support |
| 18 | `Attest` | `07e48fdd43` | refactor | chore: give pilot pytest trees a version that satisfies their own minversion |
| 19 | `Attest` | `1a4d96553f` | refactor | chore: restore tracked files after the pilot's editable install |
| 20 | `Attest` | `9320cd579d` | refactor | chore: commit pytest's generated version file into pilot cases |
| 21 | `Attest` | `9b610f6a5a` | test-only | test: the M-01 probe runs under the interpreter running the gate |
| 22 | `Corum` | `80ee1b3957` | test-only | test: lock convergence resolution gate |
| 23 | `us-stock-helper` | `58bf76382b` | test-only | test: pin agency positive attribution and 13g amendment forms |
| 24 | `Attest` | `67703a6d6c` | test-only | ci: review Attest's own pull requests, same-repository branches only |
| 25 | `Corum` | `6d03f4cf18` | test-only | test: lock JudgeBench external value gate |
| 26 | `us-stock-helper` | `facf699a45` | test-only | test: pin a generated, byte-equal v2/v3 snapshot contract across languages |
| 27 | `Attest` | `495966ecd3` | test-only | style: lint the probe test |
| 28 | `Corum` | `bcbf287cce` | test-only | test: lock pair-block value gate |
| 29 | `us-stock-helper` | `d1fd50f8b9` | test-only | test: execute analysis_api's documented test command verbatim |
| 30 | `Attest` | `2fc523b5a4` | test-only | test: count same-defect certified findings once under the family policy |
| 31 | `us-stock-helper` | `e953086c14` | test-only | test: pin gateway macd/rsi series to an independent reference |
| 32 | `Attest` | `98465a7277` | test-only | style: wrap the sample observation expectation |
| 33 | `us-stock-helper` | `96487d9014` | test-only | test: pin the adviser cap across languages |
| 34 | `Attest` | `2a94a94126` | test-only | test: expect the exact-node collection run in case artifacts |
| 35 | `us-stock-helper` | `034b650a1c` | test-only | test: guard live candle semantic validation |
| 36 | `Attest` | `04a86b25a4` | docs-only | docs: three certified receipts, one of them on real traffic |
| 37 | `Corum` | `666ceafb21` | docs-only | docs: record convergence resolution gate result |
| 38 | `us-stock-helper` | `8687625471` | docs-only | docs: log the commit-authorship verification lesson from tonight's slip |
| 39 | `Attest` | `4c8947e837` | docs-only | docs: reserve the two paid items of this window |
| 40 | `Corum` | `044edd5c29` | docs-only | docs: register convergence resolution gate |
| 41 | `us-stock-helper` | `34b01ce946` | docs-only | docs: 补充全新容器门禁前置步骤经验教训（pytest/npm ci） |
| 42 | `Attest` | `2bba19a553` | docs-only | docs: record D-114..D-117 and the policy surface they change |
| 43 | `Corum` | `b34e0896c3` | docs-only | docs: record daily use acquisition block |
| 44 | `us-stock-helper` | `9a68477722` | docs-only | docs: verify dual-entry fix in production and refresh Task 7 closeout |
| 45 | `Attest` | `ff242aefd0` | docs-only | docs: the handoff names its own end SHA |
| 46 | `Corum` | `c85a8200f7` | docs-only | docs: register daily use value gate |
| 47 | `us-stock-helper` | `aa2a4cff8c` | docs-only | docs: log nasdaq halt-timestamp fix in adapters progress ledger |
| 48 | `Attest` | `730ca9212d` | docs-only | docs: the window-end gates, on the runner and on the host |
| 49 | `Corum` | `29dbc129d1` | docs-only | docs: record JudgeBench external gate result |
| 50 | `us-stock-helper` | `fa85b21778` | docs-only | docs: hand the branch over to a sonnet-tier agent |

## 6. What it costs, on this window's own measurements

Three real reviews at `--budget 0.60`, proposals on the default model and the reproduction
generated by `generation_model`:

| shape | observed spend |
|---|---|
| 1 change unit, 1 candidate (Attest PR #8) | $0.0339 |
| 1 change unit, 1 candidate (`pytest-10051`) | $0.0519 |
| 3 change units, 12 candidates, 9 eligible (`us-stock-helper`) | $0.4374 |

Spend scales with candidates, and candidates scale with the size of the reviewed diff. The
defect pairs here are ordinary `fix:` commits — most touch one to three files — with a tail
of large ones.

| population | n | assumed mean | subtotal |
|---|---|---|---|
| defect pairs | 20 | $0.18 | $3.60 |
| refactor controls | 20 | $0.15 | $3.00 |
| test-only controls | 15 | $0.08 | $1.20 |
| docs-only controls | 15 | $0.04 | $0.60 |
| **central estimate** | **70** | | **$8.40** |
| **with a 30% margin for the large-diff tail** | | | **$10.90** |

**Headroom: $8.628332 of the $30 cap remains.** The central estimate fits it with $0.23 to
spare; the margin does not. Three ways forward, and the choice is the owner's:

| | what it costs | what it buys |
|---|---|---|
| **A** raise the cap to $35 and run all 70 at `--budget 0.60` | ~$8.40, up to $10.90 | the whole population, at the budget that actually reaches the reproduction stage |
| **B** run all 70 at the product default `$0.25` | ~$4.50 | a measurement of the **default budget**, not of generation: on this window's evidence six of nine reproductions on a 12-candidate review stopped at `BudgetExceeded` before generating anything |
| **C** cut to 12 defects + 30 controls at `--budget 0.60` | ~$5.00 | fits the existing cap; n = 12 defects is barely more than the 3 this window ran |

**A is the recommendation.** B measures the wrong thing and C is close to what already
exists. The run driver would enforce a hard cumulative `--cap` (the one added after the
2026-09-03 held-out run overspent its reservation by $0.29) so that the estimate cannot be
exceeded without stopping.

## 7. What this population can and cannot support

It can support: a false-publication count on 50 real controls from three real repositories,
and a certified count on 20 real defect pairs whose defect is established independently of
the product by the repairing commit's own tests.

It cannot support: a recall *rate* generalising beyond these three repositories, a
comparison with the SWE-bench numbers (different construction, different truth), or any
claim about repositories the owner does not own. Eight of the twenty defect pairs are the
product's own repository, and those are reported apart.
