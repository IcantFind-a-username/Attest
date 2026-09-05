# Handoff — 2026-09-07 (`fbcbefa` → `af39a1c`, 39 commits, tag `v0.1.0-rc.1`)

**Spend $12.12 of $35; cumulative $80.33 of $110.** Remote writes: pushes to `main`, three
`workflow_dispatch` runs, one annotated tag. **No pull request was opened.** Nine phases
instructed; **eight complete, one partial** (§9).

## 1. Phase status

| phase | status | the one thing to know |
|---|---|---|
| **0** pre-fixes | **done** | D-154 closed by a **signed abort record** that seals a torn journal (D-155); repo workflow at the action's own `$1.00` |
| **1.1** budget re-run | **done** | **four times the budget moved no verdict at all** — the window's headline |
| **1.2** yellow (b) round 2 | **done** | annotation-independent premises: **still 0 of 79**; shelved into `limits` |
| **1.3** gate shadow, fix commits | **done** | 13 repairs → **3** new-code candidates, **0 admissible** |
| **2** caliber & rules | **done** | D-158: held-out reports **crash recall only, 4 of 16** |
| **3** pre-release engineering | **done** | six items, six decisions, 39 REDs |
| **4** nine-class security matrix | **done** | **PASS on a runner**; external observer stays INSUFFICIENT |
| **5** yellow (b) class 2 | **done** | exception propagation: free, deterministic, **0 of 79**, refusals informative |
| **6** CLI & observability | **done** | `review --json`, `stats --json`, cost column in `--explain` |
| **7** packaging & release | **done** | wheel gated in CI; tag attaches wheel + sdist; **no PyPI** |
| **8** documentation | **done** | README top, `faq.md`, `examples/`, quickstart run on a fresh clone |
| **9** backlog & tag | **done** | two closed, priorities on the rest; `v0.1.0-rc.1` tagged and its Release carries both artifacts |

## 2. `$0.25` against `$1.00`, on the 17 commits the budget starved

[Report](acceptance/2026-09-07-budget-rerun.md) · D-166 · **17 of 17 ran**

| | $0.25 | $1.00 |
|---|---|---|
| spend | $1.6352 | **$10.3202** (6.3×) |
| candidates | 105 | **331** (3.2×) |
| **red / yellow (a) / yellow (b) / green spoke on** | 0 / 0 / 0 / **8** of 17 | 0 / 0 / 0 / **8** of 17 |
| candidates refused **for budget** | 40 | **44** |
| median review elapsed | 29.6 s | **125.2 s** |
| total review elapsed | 554 s | 2,143 s |

**Not one verdict moved.** The 2026-09-06c sentence *"the binding constraint is the budget, not
the adjudicators"* is **retired**: raising the budget raises discovery, and discovery re-starves
the budget. Exactly one candidate reached an adjudicator that had not before — a *value change,
intent unknown* — and it was drawered. Both columns ran at `repro_concurrency = 2`, so **this
comparison does not isolate D-157 and no speed-up is claimed from it.**

**Yellow (a)'s three conditions each fire 0 of 17** on the `$1.00` table, as at `$0.25`.

## 3. Yellow (b), both classes

| | class 1 — null/Optional | class 2 — exception propagation |
|---|---|---|
| rule version | `v2`, annotation-independent (D-165) | new (D-164) |
| cost per review | **one model call** | **$0.00** |
| forward pairs | 0 of 11 | 0 of 11 |
| controls | 0 of 68 | 0 of 68 (noise **0%** vs the 3% ceiling) |
| hypotheses / notes | 15 / **0** | 198 changed functions / **0** |
| why | premise (i) fails first on **13 of 15**, and **10 of those** name a parameter with no annotation, no `None` default **and no `is None` test anywhere** — so the wall was **not only annotations** | 135 of 198 added **no call at all**; 43 called a name defined more than once |

**Class 1 is written into `limits` and shelved**, per instruction. Class 2 is a better negative —
*rare*, not *unverifiable* — and it is free, so the two are not in the same position. Neither is
claimed to work.

## 4. Gate pilot, cumulative (`G-NEWCODE-001`)

| population | candidates | `through_caller` | `through_test_caller` | `direct` |
|---|---|---|---|---|
| E-04 stratum v2 | 224 | 0 | 0 | 0 |
| 11 pairs + 40 owner + 10 `corum` | 90 | **6** | **3** | 0 |
| the 17 at `--budget 1.00` | 128 | **20** | 0 | 0 |
| **13 forward-pair fix commits** | **3** | 0 | 0 | 0 |
| **cumulative** | **445** | **26** (5.8%) | **3** | **0** |

`through_test_caller` is now its own grade and **never publishes** (D-166, owner item 2). The
128 and the 90 **overlap in population** — the sum counts observations, not distinct commits.
**A repair adds almost no new code the gate can see**: 13 repairs, 3 candidates, 0 admissible.

## 5. `G-SEC-002` — nine classes, PASS

[Matrix](acceptance/2026-09-07-redteam-nine.md), on a GitHub runner at `f09a213`. All nine
dispatched for real, all nine marked, none certified, control certified in the same run:
environment secret · **controller key file** · TCP connect · **DNS egress** · write escape ·
**symlink escape** · **bounded fork/thread exhaustion** · forged envelope · **tampered sealed
bundle**.

**The first run reported FAIL, and the failing row was the control** — `a + b` → `a - b` is a
*value* change the intent clause refuses, nothing to do with isolation. The control is now a
crash. **The external-observer item stays INSUFFICIENT** and the matrix says so about itself:
every row is observed from inside the product.

## 6. Image cache and concurrency

**22 lookups, 18 reused, 4 built** across the window's three paid runs. Builds: 16.0, 16.7,
18.1, 18.6 s — mean **17.3 s**; the cache saved **≈ 312 s over 18 reuses**, ~10% of 2,683 s of
review time on small projects. Within one repository 15 of 15 reused; across six repositories
3 of 7. `repro_concurrency` defaults to **2**, and the RED is that **the ledger's bytes are
identical serial or parallel**; `Budget.reserve/settle/cancel` now hold a lock, because a raced
read-modify-write loses a reservation and a lost reservation is spend above the cap.

## 7. The seven `v0.1` conditions

[Read](acceptance/2026-09-07-v01-tag-readiness.md). **Five of seven hold; blocked on 3, 4, 5.**

| # | now | moved this window |
|---|---|---|
| 1 install from a stable ref, receive comments | holds | — (still met by a `DEFER`) |
| 2 every finding carries its level's evidence form | holds, **five classes** | yellow (b) class 2 |
| 3 head code cannot read secrets / reach the network / forge | **fails** | **4 → 9 of 13 classes**; external observer still absent |
| 4 held-out: silent on controls, stated share certified | **fails** | denominator now honest: **4 of 16**, not 4 of 28 |
| 5 one prospective shadow run | **fails** | — (cannot be assembled from history) |
| 6 L-01 exit list | holds | release mechanics done |
| 7 output contract | holds | unsupported and budget-stopped lines are contract lines |

## 8. Gates

`ruff` (over the **whole tree** — a `ruff check .` failure on the runner is how four
over-length test lines were found), `mypy` over 91 files, **2,032 passed, 10 skipped, coverage
93.17%** against the 90% floor, wheel and sdist built and the built wheel's CLI run from a clean
environment — all on a GitHub runner at `f09a213`. The full suite also passed locally in an
isolated worktree.

`v0.1.0-rc.1` is tagged and its GitHub **prerelease** carries
`attest-0.1.0rc1-py3-none-any.whl` (531 KB) and `attest-0.1.0rc1.tar.gz` (2.0 MB). **Nothing was
published to PyPI.**

## 9. What was not done, and why

- **The `$0.25`/`$1.00` elapsed comparison does not isolate `repro_concurrency`.** Both columns
  ran at 2; the $0.25 column is 2026-09-06c's serial run and its per-unit wall clock was never
  recorded, only the review's own elapsed. A clean serial-vs-parallel A/B on one population was
  not run and is not claimed.
- **`us-stock-helper`'s half of the 1.1 run exceeded its cumulative cap by $0.62** ($4.12 of
  $3.50), and the window's reservation by $0.32. The driver's `--cap` gates *starting* a unit,
  not finishing it. Recorded in DEVSPEND and the backlog rather than quietly absorbed.
- **The M-01 offline probe broke two full-suite runs again** by digesting a tree the operator was
  editing. The standing local practice is now a separate `git worktree` at a fixed commit, which
  works; **the fix — the probe snapshotting the tree it digests — is not done** and the item is
  marked **P1**, having recurred in four consecutive windows.
- **No pull request was opened**, so no comment in this window reached an author-visible GitHub
  surface. Every paid run was shadow. The four-level comment already exists from 2026-09-06c.
- **The propagation level's callee resolution is by bare name**, and 43 of 198 changed functions
  voided on ambiguity. Resolving by import is in the backlog at **P2**, unbuilt: 43 of 198 is a
  reason to consider it, not evidence the answers would be right.
- **D-162 costs held-out coverage**, named rather than discovered later: cases that only install
  on Python 3.9 will no longer bootstrap.

## 10. For the owner — three items

1. **Four times the budget buys nothing, so the interesting knob is not the budget.** The
   binding constraint is now visibly **discovery breadth**: 331 candidates produced the same
   four verdicts as 105, and 167 of them were never ranked high enough to buy a reproduction.
   **Default: cap the proposal stage's share of the budget rather than the budget itself**, so a
   larger budget buys reproductions instead of candidates. That moves what gets bought and is
   therefore yours; nothing in this window's data argues for raising `budget_usd` again.
2. **Yellow (b)'s null/Optional class costs a model call on every review and has produced zero
   sentences on 79 units under two rule versions.** Its sibling class does the same job for
   `$0.00`. **Default: switch class 1 off** — one line in `run_ci` and `cmd_review` — and keep
   class 2, which is free. Keeping it costs ~$0.005 a review to preserve the option; the
   argument for keeping it is that the corpus that defeated it has no annotations and your own
   repositories do, and that argument is now two windows old and has not been tested on your
   repositories.
3. **`G-SEC-002` is 9 of 13 classes and 0 of 1 external observers, and only the second one
   matters now.** Every row of a passing matrix is observed from inside the product. The four
   remaining fixture classes are an afternoon; an auditd or seccomp-notify observer beside the
   container is days, and it is the only thing that turns *the boundary held for this attempt*
   into *the kernel denied it*. **Default: schedule the observer, not the four classes** —
   condition 3 does not move without it, and it is the last condition that is a safety claim
   rather than a measurement.
