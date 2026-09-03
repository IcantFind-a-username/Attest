# The real-traffic corpus — 43 reviews on three real repositories, and why the run stopped

**Owner decision 1 of 2026-09-03g** (option A of [the plan](../corpus/real-traffic-plan.md),
mainline §5 decision C). Proposals `claude-sonnet-5`, reproduction generation `claude-opus-5`,
K = 4, **`--budget 0.60` per review — not the shipped $0.25 default**, `linux-container-v1`,
local review only, no GitHub write. Driver: `scripts/corpus/real_traffic.py`, product code
frozen at `fc2014f`.

**Headline.** 19 of 20 defect pairs qualified and ran; **6 produced at least one certified
receipt and 4 published**. 24 controls ran and **one published — adjudicated a real defect,
so the false-publication count is 0**. The run **stopped twice under the RISK-CERT-01 stop
rule** and both stops were the corpus's fault, not the kernel's (§4). 26 controls never ran:
the plan's cost model was about half the true price (§5).

## 1. The population that ran

| | planned | qualified (D-116) | run | not run |
|---|---|---|---|---|
| defect pairs | 20 | **19** (`d14` dropped: no test of the fix discriminates) | 19 | 0 |
| controls | 50 | — | 24 | 26 (23 `Attest`, budget + stop rule) |

The D-116 discrimination check is free and ran before any paid call: the repairing commit's
own test files were copied onto head (`F^`) and base (`F`) and executed there, and a pair
entered the run only when a **named test node** failed on head and was then seen *passing* on
base. That is node-level, not file-level: three `Corum` pairs would have been dropped by a
file-level rule because one unrelated test fails on both sides.

## 2. The table

| # | repo | SHA | m | certified | published | certified, below family threshold | backend | spend | still a control (2026-09-04 rule) |
|---|---|---|---|---|---|---|---|---|---|
| c01 (refactor) | Attest | `0d0e098b46` | 0 | 0 | 0 | 0 | — | $0.039151 | **no** — age, not on the tip's history |
| c02 (refactor) | us-stock-helper | `ab02a62ac1` | 10 | 1 | 0 | 1 | linux-container-v1 | $0.412134 | **no** — age, lines touched since |
| c03 (**mis-stratified**) | Attest | `445c5a1e28` | 1 | 1 | 1 | 0 | linux-container-v1 | $0.048866 | **no** — age, not on the tip's history |
| c04 (refactor) | us-stock-helper | `1b8cc4aab1` | 5 | 1 | 0 | 1 | linux-container-v1 | $0.405849 | **no** — age, lines touched since |
| c05 (refactor) | Attest | `506aae1a13` | 5 | 1 | 1 | 0 | linux-container-v1 | $0.416048 | **no** — age |
| c06 (refactor) | us-stock-helper | `45674d5636` | 3 | 0 | 0 | 0 | linux-container-v1 | $0.440228 | **no** — age, lines touched since |
| c22 (test-only) | Corum | `80ee1b3957` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.265066 | **no** — age, not on the tip's history |
| c23 (test-only) | us-stock-helper | `58bf76382b` | 0 | 0 | 0 | 0 | — | $0.000000 | **no** — age |
| c25 (test-only) | Corum | `6d03f4cf18` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.185380 | **no** — age |
| c26 (test-only) | us-stock-helper | `facf699a45` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.067311 | **no** — age, lines touched since |
| c28 (test-only) | Corum | `bcbf287cce` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.155759 | **no** — age |
| c29 (test-only) | us-stock-helper | `d1fd50f8b9` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.000000 | **no** — age |
| c31 (test-only) | us-stock-helper | `e953086c14` | 0 | 0 | 0 | 0 | — | $0.000000 | **no** — age |
| c33 (test-only) | us-stock-helper | `96487d9014` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.000000 | **no** — age, lines touched since |
| c35 (test-only) | us-stock-helper | `034b650a1c` | 9 | 0 | 0 | 0 | linux-container-v1 | $0.404390 | **no** — age |
| c37 (docs-only) | Corum | `666ceafb21` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.108051 | **no** — age, not on the tip's history |
| c38 (docs-only) | us-stock-helper | `8687625471` | 0 | 0 | 0 | 0 | — | $0.005305 | **no** — age, not on the tip's history |
| c40 (docs-only) | Corum | `044edd5c29` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.161750 | **no** — age, not on the tip's history |
| c41 (docs-only) | us-stock-helper | `34b01ce946` | 0 | 0 | 0 | 0 | — | $0.005345 | **no** — age, not on the tip's history |
| c43 (docs-only) | Corum | `b34e0896c3` | 0 | 0 | 0 | 0 | — | $0.018281 | **no** — age, not on the tip's history |
| c44 (docs-only) | us-stock-helper | `9a68477722` | 0 | 0 | 0 | 0 | — | $0.021322 | **no** — age, not on the tip's history |
| c46 (docs-only) | Corum | `c85a8200f7` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.076397 | **no** — age, not on the tip's history |
| c47 (docs-only) | us-stock-helper | `aa2a4cff8c` | 0 | 0 | 0 | 0 | — | $0.000000 | **no** — age, not on the tip's history |
| c49 (docs-only) | Corum | `29dbc129d1` | 0 | 0 | 0 | 0 | local_development_best_effort | $0.165697 | **no** — age |
| c50 (docs-only) | us-stock-helper | `fa85b21778` | 0 | 0 | 0 | 0 | — | $0.000000 | **no** — age |
| d01 (defect) | Attest | `04a86b25a4` | 8 | 0 | 0 | 0 | linux-container-v1 | $0.439458 | — |
| d02 (defect) | Attest | `9b610f6a5a` | 8 | 0 | 0 | 0 | linux-container-v1 | $0.450488 | — |
| d03 (defect) | Attest | `ad4c5fe1e3` | 14 | 0 | 0 | 0 | linux-container-v1 | $0.451644 | — |
| d04 (defect) | Attest | `e0867eb188` | 3 | 0 | 0 | 0 | linux-container-v1 | $0.576727 | — |
| d05 (defect) | Attest | `e002bd6679` | 7 | 5 | 0 | 5 | linux-container-v1 | $0.412410 | — |
| d06 (defect) | Attest | `260e8d9c51` | 1 | 1 | 1 | 0 | linux-container-v1 | $0.084120 | — |
| d07 (defect) | Attest | `17d5c770c7` | 1 | 0 | 0 | 0 | linux-container-v1 | $0.115604 | — |
| d08 (defect) | Attest | `7c8de5c624` | 8 | 0 | 0 | 0 | linux-container-v1 | $0.381701 | — |
| d09 (defect) | us-stock-helper | `4aa74209ad` | 3 | 3 | 2 | 0 | linux-container-v1 | $0.293391 | — |
| d10 (defect) | us-stock-helper | `6c724c1e19` | 2 | 1 | 1 | 0 | linux-container-v1 | $0.203562 | — |
| d11 (defect) | us-stock-helper | `fa85b21778` | 4 | 4 | 2 | 0 | linux-container-v1 | $0.380718 | — |
| d12 (defect) | us-stock-helper | `07a6946b7f` | 5 | 0 | 0 | 0 | linux-container-v1 | $0.433821 | — |
| d13 (defect) | us-stock-helper | `801fb292ce` | 8 | 1 | 0 | 1 | linux-container-v1 | $0.427183 | — |
| d14 (defect) | us-stock-helper | `381c0a051c` | — | — | — | — | — | dropped: not qualified | — |
| d15 (defect) | us-stock-helper | `8ed78113d1` | 3 | 0 | 0 | 0 | linux-container-v1 | $0.304462 | — |
| d16 (defect) | us-stock-helper | `d7be758c2f` | 9 | 0 | 0 | 0 | linux-container-v1 | $0.440577 | — |
| d17 (defect) | Corum | `6eba742235` | 2 | 0 | 0 | 0 | linux-container-v1 | $0.259564 | — |
| d18 (defect) | Corum | `ba8fddb952` | 4 | 0 | 0 | 0 | linux-container-v1 | $0.113446 | — |
| d19 (defect) | Corum | `515998fac1` | 1 | 0 | 0 | 0 | linux-container-v1 | $0.065960 | — |
| d20 (defect) | Corum | `5be583d614` | 1 | 0 | 0 | 0 | linux-container-v1 | $0.123258 | — |

**None of the 24 controls is a control under the 2026-09-04 rule** (`G-NULL-001` amendment,
D-122): a control must be at least six months old and no later commit on the branch tip may
touch a line it added. **The age check alone drops all 25 rows** — the oldest control commit in
this corpus is 41 days, and the three repositories' whole histories are 6 days (`Attest`),
7 days (`Corum`) and 6 weeks (`us-stock-helper`). The "lines touched since" and "not on the
tip's history" notes are the *second* check, run against each clone's own tip and reported for
information: 9 of the 25 would have passed it, 5 fail it outright, and for 11 it is undefined
because the commit sits on an unmerged branch or is newer than the clone. Requalified by
[`scripts/corpus/qualify_controls.py`](../../scripts/corpus/qualify_controls.py), no model call.

43 reviewed (mis-stratified rows excluded); eligible 124; certified 18; published 7; certified-but-below-threshold 8; spend $9.311558 (mis-stratified spend excluded)

## 3. What the numbers say, by population

| population | n | eligible `m` | certified | published | certified, below family threshold | spend | mean |
|---|---|---|---|---|---|---|---|
| **defect pairs** | 19 | 92 | **15** | **6** | 6 | $5.9581 | $0.3136 |
| — `Attest` (self-review, disclosed conflict) | 8 | 50 | 6 | 1 | 5 | $2.9122 | $0.3640 |
| — **`us-stock-helper` (outside)** | 7 | 34 | **9** | **5** | 1 | $2.4837 | $0.3548 |
| — `Corum` (outside) | 4 | 8 | 0 | 0 | 0 | $0.5622 | $0.1406 |
| **controls** | 24 | 32 | 3 | **1** | 2 | $3.3535 | $0.1397 |
| — refactor | 5 | 23 | 3 | 1 | 2 | $1.7134 | $0.3427 |
| — test-only | 9 | 9 | 0 | 0 | 0 | $1.0779 | $0.1198 |
| — docs-only | 10 | 0 | 0 | 0 | 0 | $0.5621 | $0.0562 |
| mis-stratified (`c03`, §4) | 1 | 1 | 1 | 1 | 0 | $0.0489 | — |

**Per pair, not per receipt:** 6 of 19 defect pairs certified something (32%), 4 of 19
published (21%). On the outside repository that can run its own tests in the container,
`us-stock-helper`, it is **4 of 7 certified and 3 of 7 published**.

**`Corum` is 0 of 4 for an environmental reason, not a detection failure.** numpy cannot be
imported inside `linux-container-v1`: the sandbox's thread cap makes OpenBLAS's
`pthread_create` fail for 12 threads and the import dies at 0.72 s, so every candidate DEFERs
at the collection gate. The proposals were right — on `d17` the top candidate names the exact
regression the repairing commit fixed — and nothing downstream could ever run. Backlogged.

## 4. Two stops under RISK-CERT-01, and what caused them

The driver stops the moment a control publishes. It fired twice, both on `Attest`.

**`c03` — `445c5a1`, "refactor: simplify path normalisation in the benchmark matcher".** This
is the planted regression from the 2026-09-03d Action drill: it deletes the backslash
normalisation in the benchmark matcher, and its commit message calls that a redundant-replace
cleanup **on purpose**. The receipt (head FAIL 3/3, base PASS 3/3, a Windows-style path the
base matches and the head does not) is a **true positive on a known planted defect**. Root
cause: the plan's control filter reads commit subjects and walks every ref, so a throwaway
drill branch entered the control population. Fixed in the driver — a commit reachable only
from a `throwaway/` branch is a drill, not traffic — and the case is excluded from the control
denominator with its row labelled rather than hidden.

**`c05` — `506aae1a13`, "docs: supplementary held-out run …".** A docs commit that also added
`--cap` to `scripts/corpus/heldout_run.py`, including
`spent += float(json.loads(result_path.read_text()).get("spend_usd", 0.0))` with no exception
handling. The published claim is that a truncated results file crashes the whole run and loses
every remaining case. It is **correct**: the base revision has no such call and passes, the
head revision crashes, and the receipt re-runs. This is a **true positive on a commit the plan
filed as a control**.

**So: 0 false publications in 24 controls — and a corpus-design defect that matters more than
the number.** The control strata are defined by what a commit *is about* (refactor, test-only,
docs-only), not by any evidence that it is defect-free. `c05` shows that a `docs:` commit can
add unguarded new code, and the product found it. **This population cannot support a
false-publication rate**, and neither can `G-NULL-001` if its controls are selected the same
way. A null population needs controls established defect-free by something other than their
subject line.

Per the mainline §4 stop rule the run stopped, was root-caused, and the selection defect was
fixed. Nothing was re-run: neither publication is a false publication, so the count that must
be zero already is.

## 5. What a review costs, measured

| population | plan's assumed mean | **measured mean** | ratio |
|---|---|---|---|
| defect pair | $0.18 | **$0.3136** | 1.7× |
| refactor control | $0.15 | **$0.3427** | 2.3× |
| test-only control | $0.08 | **$0.1198** | 1.5× |
| docs-only control | $0.04 | **$0.0562** | 1.4× |

The whole 70-case population at the measured prices is **$16.0**, not the plan's $8.40. That
is why 26 controls did not run: 43 reviews at $0.60 each cost **$9.80** of ledger-recorded
spend, and the window's cap is $14.

**The budget is the dominant reason a candidate does not certify.** Of 75 reproduction
failures across the run:

| reason | n |
|---|---|
| **`BudgetExceeded` on the second generation attempt** | **39** |
| collection failure (syntax, import, or the numpy thread cap) | 20 |
| unfaithful test (fails on base as well, or passes on head) | 13 |
| changed lines not executed (V-02 binding) | 1 |
| other (new-code candidate, thread guard, malformed generator output) | 2 |

At `--budget 0.60`, a review with eight or more candidates spends its discovery share and then
cannot afford a second generation attempt for most of them. This is a measurement of the
**budget**, not of the model — and it is the same wall the 2026-09-03f pilot hit at the same
budget.

## 6. D-120 on real traffic

The `d7be758` pair (`d16`) is the case whose single receipt last window certified a
`method_version` string. Under D-120 it now DEFERs:

```
verification: d977a95f1e: intent: constant change confirmed, intent unknown:
every literal the failing assertion rests on is a constant this change replaced
(常量改动已证实，意图未知)
```

That is the reclassification the owner asked for, observed in the run rather than argued
offline. One `behavior_change` receipt was accepted elsewhere in the corpus (`Attest`), under
D-102's witness rule.

## 7. What this corpus cannot support

- **No recall rate.** 19 pairs across three repositories, one run each, and 8 of the 19 are
  the product's own repository. The `Attest` rows are reported apart and are a disclosed
  conflict of interest.
- **No false-publication rate**, for the reason in §4: the controls are not known to be
  defect-free.
- **No comparison with the SWE-bench numbers** — different construction, different truth.
- **`Corum` contributes nothing about detection**, only about the sandbox.
- Every number here is at `--budget 0.60`. **The shipped default is $0.25 and was not
  measured.**
