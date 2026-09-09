# The score bar is removed — where its 35 suppressions came from, and what the new rule publishes

**Owner instruction, phase 1 of the 2026-09-13 window.** Two questions, in order.

1. *What population was each of the 35 bar-suppressed receipts drawn from?* The owner's
   precondition: **the control side must be 0.**
2. If it is, replay every recorded ledger under the new rule and count what each population
   gains. **A control review gaining a publication reverts the change.**

Free: 129 ledgers, 609 `publication_policy` rows, no model call, no execution, **$0.00**. Data:
[`evidence/2026-09-13-suppression-sources.json`](evidence/2026-09-13-suppression-sources.json),
[`evidence/2026-09-13-publication-rule-replay.json`](evidence/2026-09-13-publication-rule-replay.json).
Scripts: [`suppression_sources.py`](../../scripts/acceptance/suppression_sources.py),
[`publication_rule_replay.py`](../../scripts/acceptance/publication_rule_replay.py).

## 0. The answer in one paragraph

**As the ledgers were written, the control side is 2. Under the intent policy the product
runs today, it is 0** — both control-side receipts are re-judged `behavior_change`, "the
change states its own intent", and never become receipts at all. The owner was shown both
readings and decided on the second ([D-199](../../DECISIONS.md)). The new rule then publishes
**25 findings that the bar had hidden, over 17 of 90 replayable selections, removing none** —
and of those 25, **6 survive today's intent policy: 1 on a defect review, 5 on neither, and
0 on a control.**

## 1. The 35, by the population their review was drawn from

Each suppressing review is resolved to the `(head_sha, merge_base_sha)` pair its own
`task.json` records, and that pair is matched — **on both shas** — against the committed run
plans. Matching on the head alone is not enough: `9b610f6a` is the head of a defect row *and*
of a control row in the same plan, and only the base separates them. All 35 resolve; none is
left unclassified.

| population | suppressions | reviews |
|---|---|---|
| **defect** — a case built to contain a known regression | **13** | 7 |
| **control** — a case the plan filed as defect-free | **2** | 2 |
| **neither** — real recent commits, no defect and no control label | **20** | 8 |

### 1.1 Defect reviews — 13 suppressions over 7 reviews

| review (task) | candidate | score | bar `m_u/α` | `m_u` | case |
|---|---|---|---|---|---|
| `20260903-011606-ab8fcc37` | `f118070241` | 58.97 | 60.0 | 6 | `trial-b`, a planted revert of a real fix |
| `20260903-170105-9b14404e` | `58a3076775` | 58.97 | 90.0 | 9 | `d16` us-stock-helper |
| `20260903-193354-4c8189d3` | `c5b90ad887` | 60.00 | 80.0 | 8 | `d13` us-stock-helper |
| `20260903-193709-f014bd70` | `058f573208` | 40.00 | 70.0 | 7 | `d05` Attest |
| `20260903-193709-f014bd70` | `103aa42a3c` | 52.78 | 70.0 | 7 | `d05` Attest |
| `20260903-193709-f014bd70` | `6cce86432e` | 52.78 | 70.0 | 7 | `d05` Attest |
| `20260903-193709-f014bd70` | `a47e7a8fa9` | 60.00 | 70.0 | 7 | `d05` Attest |
| `20260903-193709-f014bd70` | `db100c9818` | 60.00 | 70.0 | 7 | `d05` Attest |
| `20260904-004116-2cadd8db` | `8f3851fe4b` | 40.00 | 80.0 | 8 | `d02` Attest, budget wall |
| `20260904-004449-4e7f19c6` | `b89a422892` | 52.78 | 140.0 | 14 | `d03` Attest, budget wall |
| `20260904-004449-4e7f19c6` | `d2c15a3f07` | 40.00 | 140.0 | 14 | `d03` Attest, budget wall |
| `20260904-004449-4e7f19c6` | `dad85d4e84` | 52.78 | 140.0 | 14 | `d03` Attest, budget wall |
| `20260904-005029-9b14404e` | `3bba2f62e6` | 40.00 | 90.0 | 9 | `d16` us-stock-helper, budget wall |

### 1.2 Control reviews — 2 suppressions over 2 reviews

| review (task) | candidate | score | bar `m_u/α` | `m_u` | case |
|---|---|---|---|---|---|
| `20260903-193901-ee27b253` | `1d0af73c3e` | 40.00 | 100.0 | 10 | `c02` us-stock-helper, `population: control` |
| `20260903-194031-f10f0463` | `33aa333ec0` | 40.00 | 50.0 | 5 | `c04` us-stock-helper, `population: control` |

Both are corroborated independently: the `m_u` values 10 and 5 are exactly the `m` column the
[2026-09-03 real-traffic report](2026-09-03-real-traffic-corpus.md) prints for `c02` and `c04`,
and that report's per-case table already records "certified, below family threshold" = 1 for
`c04`. This is not an inference from a sha match alone.

**What they actually claim, read.** `33aa333ec0`'s generated test asserts
`set(indicators) == {"ma5", "rsi", "macd", "volatility", "magicNine"}` — that is, it asserts the
**absence** of the `ma10`/`ma20`/`ma60` keys the commit exists to add. `1d0af73c3e` is the same
family. Both are the value class: an intended change of a returned value, which is
[the backlog's oldest open P0](../backlog.md).

**And neither is a control by the definition the project now uses.** `c02` changes 1,073 lines
of `scripts/smoke_live.py` and `c04` 108 lines of `indicators.py` and 73 of `snapshot.py`; both
were filed as controls because their *subject lines* begin `test:`. The 2026-09-03 report had
already named this defect for `c03` and `c05`, both of which published and were both adjudicated
**true positives**, and had already concluded that **none of its 24 controls is a control under
the D-122 rule** and that the population "cannot support a false-publication rate". These two
rows are that same corpus-design defect, one gate later.

### 1.3 Neither — 20 suppressions over 8 reviews

Fourteen are E-04 stratum-v2 units (real recent commits, stratum `fix`, no defect planted and no
control label) and six are 2026-09-06 four-levels units on Attest's own recent commits. The
E-04 stratum-v2 report's own arithmetic agrees: it recorded **21 accepted receipts and 7 shadow
findings**, and 21 − 7 = the 14 counted here.

## 2. The same 35, re-judged under the intent policy in force

The 35 are ledger rows written under intent policies **v1 through v4.1**. The product ships
v4.2. The [2026-09-05 v4.1 replay](evidence/2026-09-05-intent-v41-replay.json) re-judged every
receipt then on disk, and six of the 35 (the 2026-09-06 four-levels rows) were certified *live*
under v4.1 and need no re-judgement.

| population | as recorded | re-judged under intent v4.1 |
|---|---|---|
| defect | 13 | 2 still certify, 9 drawered, 2 not re-judged |
| **control** | **2** | **0 still certify — both drawered** |
| neither | 20 | 3 + 6 live, 11 drawered |

Both control-side verdicts read *"intent stated in the change itself: the same change also
updates a test, a docstring, documentation, a changelog entry or an inline comment about the
symbol under test"*. That replay's own aggregate says the same thing at population scale:
**`control_certifying` goes 4 → 2 → 0 across v2 → v3 → v4, and `control_review_published`
2 → 1 → 0.**

**The limit of that zero, stated.** Its denominator is **4 control receipts**, and **no
designated control arm has ever run under v4.x product code** — D-196 declined the K=5 red
control arm (126 controls, ≈$126) for budget. So the claim this report supports is *"no control
receipt survives the current intent clause, over the four that exist"*, not *"the control
false-publication rate under the new rule is zero"*. The first prospective test of the new rule
is phase 2's shadow run.

## 3. The new rule, replayed over every ledger

`select_for_publication` is asked twice per recorded row: once under the rule the row's own
`schema_version` names — which must reproduce the row's `published` list exactly — and once
under `attest.publication-policy.v4`.

| | |
|---|---|
| ledgers carrying `publication_policy` rows | **129** |
| `publication_policy` rows | **609** |
| rows carrying a certified set | 91 |
| **rows whose own-version replay reproduces their record** | **90 of 91** |
| rows excluded because the replay disagreed with the record | **0** |
| rows excluded as unreplayable | 1 |

The one exclusion is `20260907-123203-4561687e` — the copy of the runner's ledger from the
external `us-stock-helper #5` receipt, which has no `candidates.jsonl` beside it on this host.
It recorded `published: ["34a9299741"]` and `suppressed: []`, so **the new rule changes nothing
for it** whatever the reconstruction would have said; it is excluded to keep the replay's
"reproduces its own record" property literal rather than to hide a disagreement.

### 3.1 What changes, by population

| population | published, added | published, removed | added, restricted to receipts today's intent policy keeps |
|---|---|---|---|
| defect | **+11** | −0 | **+1** |
| **control** | **+2** | **−0** | **+0** |
| neither | **+12** | −0 | **+5** |
| **total** | **+25** | **−0** | **+6** |

**The owner's stop condition, read against the frame the decision was taken in: `+0` on the
control side.** In the as-recorded frame it is `+2`, and both are the two receipts of §1.2 that
the current intent discriminator drawers.

Twenty-five publications from thirty-five suppressions, not thirty-five: **the hard cap and the
same-defect rule absorb the other ten**, which is the first time in this project's record that
the cap has bound anything at all — the census found it had suppressed **0 of 574** rows.

### 3.2 Every changed selection, with its candidate ids

| population | review (task) | added | case |
|---|---|---|---|
| control | `20260903-193901-ee27b253` | `1d0af73c3e` | `c02` |
| control | `20260903-194031-f10f0463` | `33aa333ec0` | `c04` |
| defect | `20260903-011606-ab8fcc37` | `f118070241` | `trial-b` |
| defect | `20260903-170105-9b14404e` | `58a3076775` | `d16` |
| defect | `20260903-193354-4c8189d3` | `c5b90ad887` | `d13` |
| defect | `20260903-193709-f014bd70` | `103aa42a3c`, `a47e7a8fa9`, `db100c9818` | `d05` |
| defect | `20260904-004116-2cadd8db` | `8f3851fe4b` | `d02` |
| defect | `20260904-004449-4e7f19c6` | `b89a422892`, `d2c15a3f07`, `dad85d4e84` | `d03` |
| defect | `20260904-005029-9b14404e` | `3bba2f62e6` | `d16` |
| neither | `20260904-032523-0a07b6d6` | `240836f2e0` | E-04 v2 `us-stock-helper@d7be758` |
| neither | `20260904-033730-0a07b6d6` | `240836f2e0`, `2c982b3cf3`, `3a3b414a24` | E-04 v2 `us-stock-helper@d7be758` |
| neither | `20260904-034615-e10d6055` | `27dd3692d7`, `33243bfa2e` | E-04 v2 `us-stock-helper@d921058` |
| neither | `20260904-040004-18b67397` | `1cf3efe423`, `bb40cb1629` | E-04 v2 `Attest@34affaf` |
| neither | `20260904-040545-c9785a66` | `0ab1e8313a` | E-04 v2 `Attest@9df938f` |
| neither | `20260906-024251-d6495f25` | `0561204f7d` | four-levels `attest@eede421` |
| neither | `20260906-045706-d6495f25` | `14b3a1e026` | four-levels `attest@eede421` |
| neither | `20260906-051043-1b830447` | `250c5e3d67` | four-levels `attest@c88f67e` |

Note `20260903-193709-f014bd70` (`d05`): five receipts were suppressed and **three** publish —
the other two are the same defect as one that did, and the cap does not bind at three.

### 3.3 The cross-check nobody planned

These numbers are **identical, candidate id for candidate id, to the baseline
[D-182](../../DECISIONS.md) filed and declined on 2026-09-10**: the same 17 selections, the same
25 added ids, the same 0 removed. That baseline was computed by a different script
(`scripts/acceptance/ledger_replay.py`) under a differently-worded rule — *V ∧ intent ∧ per-unit
top 3*. The two rules are not the same rule; on this data they select the same set, because no
review ever had more than three clusters inside one change unit. Two independent
implementations reaching the same 25 ids is the strongest evidence available that the
reconstruction in §3 is faithful.

## 4. What changed in the code

| | |
|---|---|
| `PUBLICATION_POLICY_SCHEMA_VERSION` | `attest.publication-policy.v3` → **`v4`** |
| the rule | a certified finding publishes subject to **same-defect clustering and `hard_cap`** only |
| `unit_thresholds`, `family_threshold` | **still computed and still recorded**; no longer applied |
| new ledger field | `score_bar_applied: false` |
| `pr_error_bound` under v4 | **`1.0`**, and `e_value_validity` reads `not-applied` |
| historical rows | replay under the rule their own `schema_version` names (`score_bar_applies`) |
| **unchanged** | `alpha`, every likelihood ratio, `k_samples`, `hard_cap`, the supported interpreter range, the isolation backend |

**`pr_error_bound` is the honest casualty.** D-174 established that the PR-level bound is
`min(1, U·α)` — a union over the units a bar was applied in. With no bar there is no rejection
rule for a union to be taken over, so v4 records `1.0` and `not-applied` rather than a number
computed from a rule that is not in force. **The product no longer offers a per-unit multiplicity
cap of any kind.** What it offers instead is the receipt: an accepted certification and a
reproduction that fails on head, passes on base, in isolation, repeated, with changed lines
executed and a bundle that verifies offline.

**An unknown schema version fails closed** — it applies the bar. Applying a bar can only
withhold a claim, never manufacture one.

## 5. The arithmetic ceiling, which is why the bar had to go

Recorded in `docs/mainline.md` §5 decision A. `S` caps at 3.0, `T` at 3.0, `V` is 20.0, so a
certified finding could score 180. **It never has**: across all 2,589 recorded `review` rows the
channels bought are `("S",)` and nothing else — `T` has never fired, not under the corpus
drivers and not on the shipped external receipt. So the reachable ceiling was
`S_CAP × V_CAP = 60.0` against a bar of `10·m_u`, and

> a change unit holding **7 or more** eligible candidates could not publish a receipt at all.

Not improbably — arithmetically, whatever the evidence showed. **29 of the 35** suppressions were
held back by a bar above 60.

## 6. What this report does not say

- **That any of the 25 is right.** A reproduction proves a differential and the intent
  discriminator has run; nothing here adjudicates whether the author should have been told. Six
  of the 25 survive today's intent policy and nineteen do not, and that is the whole of what is
  known about their quality.
- **That the control false-publication rate is zero under the new rule.** §2 states the
  denominator: four control receipts, no control arm under v4.x code.
- **That anything statistical is left.** It is not. §4 says so plainly.
