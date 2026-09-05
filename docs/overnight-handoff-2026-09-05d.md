# Handoff — 2026-09-05d (`7c09c75` → `8c83d89`)

**Spend $3.460400 of $20; cumulative $55.686937 of $90.** Remote writes: push to `main` only.
Docker Desktop was restarted, so the `/Users` bind-mount hang is gone and everything owed ran.
**D-138** moved every execution path — generated test, controller mounts, both differential
worktrees, gate tree — to `<tempdir>/attest-work-<pid>-<token>/`; only bundle, ledger, receipt,
candidates, cache and key stay in `<repo>/.attest`. RED: `tests/test_workdir.py`, 3 of 8 fail on
the old implementation. Session roots are **not** cleaned at exit (deliberate: `binding_pilot`
reads a previous process's output), so a 68-review run leaves ~80 MB for the OS to reclaim.

## 1. The independent null sample — it published, and the publication is real (D-139)

[Report](acceptance/2026-09-05-g-null-001a-independent.md) §§6–9. $0.880000 of $6.00. Same
68-control manifest, fresh log. **54 of 68 reviewed, 18 reproductions attempted, 6 controls the
policy answered, 1 publication, 0 wrong publications, no bound** (3/6 = 50% is not one).

**`more-itertools f4f2cfec9d` (2019) is a true positive.** Its `try: iterable[:0] / except
TypeError` guard is escaped by a **plain `dict` on Python 3.12**, where `slice` became hashable:
`divide(3, {…})` returns partitions on base and raises `KeyError` on head — shown by an
[independent probe](acceptance/evidence/2026-09-05d-divide-probe.py) with no product code in it,
on four input types and on none of nine ordinary ones. The bundle verifies offline with its seal
and the code is still at that project's tip. **Root cause is the control definition, not
certification.** Not fixed, not resumed. Separately: `informative_controls` called the
*publishing* control uninformative, so the driver now also reports `answered_controls`.

## 2. Forward pairs — the first value-class recall number, n = 11 (D-140)

[Report](acceptance/2026-09-05-forward-pair-reviews.md). $2.580400 of $11.00. Every row `fwd`.

| dir | repo | head | cand | answered | budget-refused | host | cert | pub | value cert/drawer |
|---|---|---|---|---|---|---|---|---|---|
| `fwd` | `attrs` | `e048efcb39` | 2 | 0 | 0 | 1 | 0 | 0 | 0 / 0 |
| `fwd` | `attrs` | `7c85d68de2` | 1 | 1 | 0 | 0 | 0 | 0 | 0 / 0 |
| `fwd` | `click` | `0585f456ba` | 10 | 9 | 0 | 0 | 0 | 0 | 0 / 0 |
| `fwd` | `click` | `cd4674a6de` | 42 | 4 | **25** | 1 | 0 | 0 | **0 / 1** |
| `fwd` | `click` | `19fd4d6e18` | 7 | 7 | 0 | 0 | 0 | 0 | 0 / 0 |
| `fwd` | `itsdangerous` | `3703fbdedd` | 7 | 5 | 0 | 0 | **1** | **1** | 0 / 0 |
| `fwd` | `more-itertools` | `d63a26e56e` | 1 | 1 | 0 | 0 | 0 | 0 | 0 / 0 |
| `fwd` | `more-itertools` | `2deea20ead` | 1 | 1 | 0 | 0 | **1** | **1** | 0 / 0 |
| `fwd` | `more-itertools` | `71b76842d3` | 1 | 1 | 0 | 0 | **1** | **1** | 0 / 0 |
| `fwd` | `more-itertools` | `390a3db74c` | 2 | 2 | 0 | 0 | 0 | 0 | 0 / 0 |
| `fwd` | `packaging` | `527be81862` | 1 | 0 | 0 | 1 | 0 | 0 | 0 / 0 |
| | **11 pairs** | | **75** | **31** | **25** | **3** | **3** | **3** | **0 / 1** |

**Value class 0 of 1, n = 11** — upper bound 95%, no rate estimable; the finding is that
value-class candidates are *rare* in natural defect-introducing commits. The one was drawered by
**clause (c) on a *forward* pair**, the side D-135 exonerated it on. Two of the three
publications are the exact defect the later repair fixed. **The wall is generation**: 20 of the
31 answers are `unfaithful generated test: fails on base as well`, because a forward diff — unlike
a reversed one — does not hand the proposer the defect in its own text. README carries the
number with its `n`.

## 3. The registry witness — designed, measured, not built

[`design/gate-reachability-registry.md`](design/gate-reachability-registry.md), 2 pages: a
`through_registry` grade, four adapters, the pytest one recommended **disabled**, and
`attest 2878d4012e` walked through argparse. **Ceiling, measured free**
([scanner](../scripts/corpus/registry_ceiling.py), an over-count, validated against that positive
control): **0 of 224** stratum-v2 new-code candidates, **1 of 53** replay bundles — structural,
since the `us-stock-helper` and `corum` trees register nothing of any of the four shapes.
**The 10.7% ceiling does not move; the design recommends keeping §7.**

## 4. Not done, and why

- **The last 14 controls** and 3 image-bootstrap DEFERs — blocked on item 1, not money (~$0.30).
- **Pair 4's 25 budget-refused candidates** — that pair at `--budget 3.00` is ~$2 and would say
  whether anything hides there; at $1.00 the number measures the budget as much as the product.
- **The registry witness is not implemented** and **the corpus was not extended** — both by
  instruction; the first is also the design's own recommendation.
- **No GitHub-runner `gates` workflow** for this tip.

## 5. For the owner — three items

1. **What is a control, now that one was a real defect?** (a) exclude `f4f2cfec9d` with its row
   labelled and resume the last 14; (b) require a control to be unreachable under the current
   interpreter's semantics; (c) accept a real base rate and bound only *wrong* publications.
   **Default: (a)** — the only one that yields an independent bound this month.
2. **Clause (c) drawered a value regression on a forward pair.** **Default: leave the rule alone
   and note the case** — one candidate cannot move a policy, and weakening (c) is what D-132 and
   D-134 exist to prevent.
3. **`more-itertools` has a live defect and this project holds the reproduction.** Reporting it
   upstream is a call about this project's public posture, not an agent's.

## 6. Gates at this tip

`ruff check .` clean; `mypy` clean over 84 source files; **`pytest --cov=src/attest`: 1,864
tests, all passed, none skipped, none failed**, coverage **92.70%** against the 90% floor — the
previous tip's 1,856 plus `test_workdir.py`'s 8. **Zero skips is how we know the container
backend is back**: `test_linux_isolation.py`'s 7 tests skip themselves when docker is
unavailable, and they did not. *(An earlier run this window failed 1 and errored 3 in
`test_m01_offline_measurement_probe.py` — that module's own **clean-tree guard** firing on
uncommitted `src/` changes, not a regression; at the committed tip it passes 8 of 8.)*
