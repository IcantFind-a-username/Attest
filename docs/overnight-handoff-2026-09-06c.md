# Handoff — 2026-09-06c (`e8468ba` → `5595477`, plus this document)

**Spend $8.36 of $28; cumulative $68.67 of $90.** Remote writes: pushes to `main`, and one
throwaway pull request ([#11](https://github.com/IcantFind-a-username/Attest/pull/11)), **closed
unmerged, branch deleted**. Ten owner instructions; **nine done, one partly** (§9). Two real
defects found and fixed, one of them by the work itself.

## 1. The four-level table, 40 real commits — the window's deliverable

[Table, all 40 rows](acceptance/2026-09-06c-four-levels.md) · data
[attest](acceptance/evidence/2026-09-06c-four-levels-attest.json) ·
[us-stock-helper](acceptance/evidence/2026-09-06c-four-levels-us-stock-helper.json) ·
[corum](acceptance/evidence/2026-09-06c-four-levels-corum.json)

| level | spoke on | speech rate |
|---|---|---|
| **red** | 0 of 40 | 0% |
| **yellow (a)** | 0 of 40 (**1** of 10 more on `corum`) | 0% |
| **yellow (b)** | 0 of 40 | 0% |
| **green** | **8 of 40**, three of them the same duplicated `git` helper | **20%** |
| **gate** (shadow) | 61 new-code candidates, 15 admissible, **3 `through_caller`** | — |
| **every level silent** | 32 of 40 | 80% |

`$2.03` for 40 reviews, **$0.051 a commit**, at the `budget-usd 0.25` this repository's Action
uses. Of **141 candidates**, 87 were never ranked high enough to buy a reproduction and 40 died
with the budget gone, so **11 reached a verdict any adjudicator is responsible for**. On this
traffic the binding constraint is the budget, not the adjudicators.

**Spot checks, 3 per level** (§4 of the report): green 3 of 3 correct, one of them redundant;
yellow (a)'s single note **every clause true and the author had already fixed the caller**; red
0 of 40 so the three checked are from PR #11 and the forward pairs; gate 3 of 3 correct, and 3
of its 9 enter through a *test* rather than production code — recorded as an open question.

## 2. Held-out, old and new — the intent rule is the wall

[Report](acceptance/2026-09-06c-heldout-probe.md). First held-out number under the current
policy; `v0.1` condition 4 and `G-RECALL-002` have waited for it since 2026-09-03.

| | old (legacy generator) | **new (probe + record/replay)** |
|---|---|---|
| defect cases | 29 | **28 of 29** |
| — **built** | 10 | **28** |
| — **certified** | 5 | **4** |
| — **published** | 7 | **4** |
| controls / **false publications** | 39 / **0** | 40 / **0** |
| **drawer** | 61 | **62** |
| — **unrecordable** (probe refused) | — | **10** |

**All four cases the old column published and the new one does not were lost to one clause** —
*value change confirmed, intent unknown*. D-140 measured that clause at 0 of 1 on forward pairs;
here it is **4 of 8 on a held-out slice of known defects**, the largest number this project has
on it. Unfaithful reproductions fell 9 → 3, not to 0: what remains is a different failure the
same word covers (a test referencing a symbol absent from head).

## 3. The 15 value-class drawers, adjudicated — **0 / 15 / 0**

[Adjudication](acceptance/2026-09-06c-value-class-adjudication.md), free.
**0 真缺陷 / 15 有意变更 / 0 无法判断**, so the ≥ 8 threshold for an analysis page is not met.
All fifteen sit on two `click` commits, ten on one function, and every one is documented in that
commit's own `CHANGES.rst`. **Do not change `attest.intent.v4.1` on this evidence** — n is two
commits, both unusually loud, and the discriminating case (a quiet value change that says
nothing) is absent from all eleven pairs. The held-out number in §2 is the one that bites.

## 4. Yellow (a): three conditions, all silent — and yellow (b): 13 hypotheses, 0 survived

[Conditions](acceptance/2026-09-06c-yellow-conditions.md) ·
[nullability](acceptance/2026-09-06c-yellow-b-nullability.md)

- **a1** signature ∧ untested caller (D-145, kept); **a2** new raise ∨ moved return annotation ∧
  untested caller; **a3** added required parameter ∧ a statically broken call. **Each fires on
  0 of 11 forward and 0 of 68 controls**, so all three clear the 3% ceiling by never firing.
  D-143's five disjunction firings were adjudicated one by one: **0 of 7 notes carried both
  halves**, which is why no fourth condition was written from them.
- **Yellow (b)** costs `$0.1034` for 79 units: **13 hypotheses, 0 survived all three premises**,
  11 dying on premise (i) because the corpus carries no type annotations at all. Its binding
  constraint is annotation coverage, not the model. It ships because it cannot speak without
  three verified readings; it is **not** claimed to work.

## 5. The gate level's cumulative shadow

[Report](acceptance/2026-09-06c-gate-shadow.md), all 90 candidates with three coordinates each.
**9 `through_caller` of 314 new-code candidates cumulatively (2.9%), 0 `direct`** — the
2026-09-05 "0 of 224" is retired: that run executed no reproduction, so no grade could be taken.
Recorded in `evolution-gates.md` beside `G-NEWCODE-001`'s own text.

## 6. The four levels in one comment

[As posted](acceptance/evidence/2026-09-06c-pr11-comment.md). One throwaway pull request with a
constructed two-file diff produced, on a GitHub runner, `$0.1210`:

```
[red]    scripts/corpus/four_levels.py:212 — `_latest_task` now requires a `ledger_name`
         argument but its only known caller … (receipt e89b0fe548b6)
[red]    src/attest/review/impact.py:492 — Removing the `len(parts) > 1` guard … IndexError.
         (receipt c8e0ac213e2d)
[yellow] scripts/corpus/four_levels.py:212 — `_latest_task` gained a required parameter;
         1 call site(s) pass fewer than 2 positional argument(s) — four_levels.py:202
[green]  Structural (no defect claimed): four_levels.py:49-55 `git` and
         nullability_scan.py:64-70 `git` … similarity 0.978
```

Three levels in one comment, each anchored on a line the diff changed. **A screenshot could not
be captured** — the browser pane rendered the page blank below the fold — so the comment is
recorded verbatim instead, which is durable where a screenshot is not.

## 7. Three defects found, two fixed

- **D-149.** D-142's level marker had been made mandatory in the **delivery journal's** integrity
  check, retroactively invalidating every pre-D-142 row — and the failure was `attest review`
  **aborting at startup**, because the alpha projection reconciles the journal before a candidate
  is read. Found by the held-out re-run: 14 of the first 19 cases crashed on their own ledgers.
- **D-154, recorded and not fixed.** A review killed between its last settlement and its
  finalization leaves the repository unreviewable — the same shape as D-149, a journal problem
  aborting a review instead of degrading the one projection that reads it.
- **`ReplayProvider` counted yellow (b)'s call as a proposal**, breaking the stability resume
  invariant. Replay now answers the nullability question with the empty hypothesis list — the
  level is silent, which is what it is on any failure — rather than raising, which the checkpoint
  machinery would read as an ambiguous cost.

## 8. Gates

`ruff` clean; `mypy` clean over 88 source files. The `gates` workflow **failed on a runner at
`61835fa`** — five report tests carried D-152's replaced prose, and the local suite had been
killed before reaching them; fixed at `5595477`, whose runner result is the one to read. Coverage
was 93.12% against the 90% floor in that same failing run, so the floor is not at risk. New
tests: `test_nullability.py` (6), `test_local_report.py` (4), `test_delivery_journal_history.py`
(3), 5 in `test_impact_scope.py`. All fail on the previous implementations.

## 9. What was not done, and why

- **One held-out defect case, `pytest-8399`, cannot be run at all** — and finding out why is the
  window's third defect (**D-154**). The stall watchdog killed it between its last delivery
  settlement and its journal finalization, so every subsequent `attest review` of that repository
  **aborts at startup** reconciling the torn journal. Recorded, not fixed: the narrow fix weakens
  a tamper-evidence property and choosing which torn journals are excusable is a design decision.
  The held-out n is reported as **28 of 29** rather than assumed.
- **No screenshot of the pull-request comment** (§6): the browser pane would not render it.
- **`$1.4490` was spent twice on the held-out slice** — one pass abandoned to D-149 (a product
  defect, and finding it was worth the money) and one to an **operator error**: the source tree
  was edited while a run was importing it. The third pass pins the product code to a git worktree,
  and that is the standing fix.
- **The v0.1 gap list had no two-hour code item.** The one item under an hour is the version bump,
  which the same instruction defers ([re-read](acceptance/2026-09-06c-v01-tag-readiness.md)).

## 10. For the owner — three items

1. **The value-class clause now has a real recall number and it is expensive: 4 of 8 held-out
   defects.** §3's hand adjudication says the clause is right 15 of 15 where a diff states its
   intent; §2 says it costs four publications where the defect is known and the diff says
   nothing. **Default: do nothing this window and decide on a discriminator, not a threshold** —
   the two populations disagree because they are different questions, and lowering the bar would
   move both.
2. **Three of the gate's nine `through_caller` observations enter through the change's own new
   test.** The grade does not distinguish that from a production caller, and the through-caller
   rule exists precisely so that *something the change did not add* depends on the new code.
   **Default: add `site.is_test` to the grade and re-report; it takes the count from 9 to 6.**
3. **Yellow (b) costs one model call on every review and has never produced a sentence.**
   $0.005 a review, 0 of 79 units, 13 of 13 hypotheses void. **Default: keep it for one more
   population — the corpus that defeated it has no type annotations and the owner's own
   repositories do** — or switch it off, which is one line in `run_ci` and `cmd_review`.
