# Handoff — 2026-09-05d (`7c09c75` → `4c34920`): the host is fixed, the working directory moved, and both measurements landed

**Window spend $3.460400 of $20; cumulative $55.686937 of $90.** Remote writes: **push to `main`
only** (not yet pushed at the time of writing; see §6). Gates at the tip: §6.

**The blocker is gone.** Docker Desktop was restarted; a bind mount of a path under
`/Users/franz` now returns in **0.5 s** where it hung indefinitely last window. Everything that
was owed ran.

## 1. The working directory left the repository tree (D-138)

`src/attest/review/workdir.py`. Every path the product **executes from** — the generated
`test_repro.py`, the controller's `inputs`/`outputs` mounts, both throwaway `git worktree` trees
of a differential, and the gate level's head-only tree — now lives under
`<tempdir>/attest-work-<pid>-<token>/<repo>-<digest>/`. **Only the durable record stays under
`<repo>/.attest`**: bundle, ledger, receipt, candidates, attempt cache, controller key.
`ATTEST_WORK_ROOT` overrides the parent. No isolation property changed: same read-only tree and
inputs mounts, same single writable outputs mount, same nonce, same digests.

**RED** is `tests/test_workdir.py`; three of its eight fail on the previous implementation,
including the strong form — *while a differential is in flight, every path git has registered as
a worktree of this repository is outside it* — and a full `run_ci` showing the bundle, ledger and
receipt still under `.attest` while the execution left nothing there.

**One thing regressed and is named in the decision:** `scripts/corpus/binding_pilot.py` read a
*previous* process's generated test out of `.attest/repro`; it now tries the legacy path and then
globs the session roots. **And one hygiene fact:** session roots are not removed at exit (the
pilot depends on that), so a 68-review run leaves ~80 MB under the system temporary directory for
the OS to reclaim. Deliberate, and a candidate for a small follow-up.

## 2. `G-NULL-001a` independent: it ran, it published on control 54, and the publication is real (D-139)

[Report](acceptance/2026-09-05-g-null-001a-independent.md) §§6–9, **$0.880000 of $6.00.**
Same 68-control manifest, not re-sampled; fresh log. (Proposals for the 45 controls the last
attempt had already sampled **replayed** from the R-02 cache; what this run bought is executions.)

| | |
|---|---|
| controls reviewed | **54 of 68**, then the stop |
| eligible candidates / reproductions attempted | 18 / 18 |
| controls the **policy** answered | **6** |
| `informative_controls` (D-136's strict count) | **0** |
| publications | **1** |
| **wrong publications** | **0** |
| bound | **none** — 3/6 = 50% is not a bound |

**The stop: `more-itertools f4f2cfec9d` (2019), and it is a true positive.** That commit replaced
`seq = tuple(iterable)` with a `try: iterable[:0] / except TypeError` probe. The guard catches
`TypeError` **only**, and on **Python 3.12 — where `slice` became hashable — a plain `dict`
escapes it**: `divide(3, {0: 0, …})` returns partitions on base and raises
`KeyError: slice(None, 0, None)` on head. An [independent probe](acceptance/evidence/2026-09-05d-divide-probe.py)
with no product code in it shows the difference on `dict`, `OrderedDict`, a `KeyError`-raising
mapping and a legacy sequence-protocol iterable, and **no** difference on nine ordinary types.
The receipt is `regression_reproduced`, head FAIL 3/3 / base PASS 3/3, and its bundle **verifies
offline with its seal**. The code is still at that project's default-branch tip.

**So the root cause is the control definition, not the certification path.** "Six months old and
untouched" is a proxy for "carries no defect", and this is its counterexample twice over: an
obscure regression nobody hit stays untouched forever, **and a language change can make a
six-year-old line newly wrong without anyone editing it.** Not fixed, not resumed, per the rule.

**The denominator was degenerate and this run is what showed it.** `informative_controls` counts
a control with **no verification line at all**, which is 0 here — *including the control that
published*, because three of its four candidates were drawered and each wrote a line. The driver
now also reports `answered_controls` (no *infrastructure* defer), with the infrastructure
prefixes written into the driver **before** the totals were read. Both are reported.

## 3. Forward pairs: 11 of 11 reviewed; the value class is 0 of 1 (D-140)

[Report](acceptance/2026-09-05-forward-pair-reviews.md), **$2.580400 of $11.00.**
Every row carries `fwd`.

| | n |
|---|---|
| pairs reviewed | **11 of 11** |
| candidates | 75 |
| — refused a reproduction by the review budget | **25** (all in one 42-candidate diff) |
| — blocked by the container image | 3 |
| — **answered about the code** | **31** |
| certified / published | **3 / 3** |
| **value class: certified / drawered** | **0 / 1** |

**The value class, `n = 11`, written as it is.** One value-class candidate in eleven forward
pairs — `click cd4674a6de`, `src/click/core.py:2660` — drawered by **clause (c)**, *intent
stated in the change itself*. `0 of 1` has a 95% upper bound of 95% and no recall rate follows.
What eleven forward pairs did show is that **value-class candidates are rare in natural
defect-introducing commits**: nine of the eleven produced only crash-shaped or unfaithful ones.

**Note where clause (c) fired: on a *forward* pair**, the side D-135 exonerated it on (7 of 8).
One case is a data point, not a refutation. It is item 2 below.

**The crash class published 3, and 2 of them are the defect the later repair fixed** —
`more-itertools product_index` with an iterator argument, and `random_product` with `repeat > 1`,
both named by their repairing commits' own subjects. The third (`itsdangerous 3703fbdedd`) is a
*different* real regression in the same commit: the Python-2 drop made `BadData.__str__` return
`self.message` uncoerced, so `str(BadData(b"…"))` raises on head.

**The wall on forward pairs is generation.** 20 of the 31 answered candidates failed as
`unfaithful generated test: fails on base as well`. A reversed diff **is** a repair and hands the
proposer the defect in its own text; a forward diff says nothing about being wrong. **That is the
measurement behind D-135's claim that every reversed-corpus recall figure is inflated.**

## 4. The registry witness: designed, measured, and not built

[`design/gate-reachability-registry.md`](design/gate-reachability-registry.md), ≤ 2 pages, **not
implemented and not asking to be**. A `through_registry` grade between `through_caller` and
`direct`, whose witness is (1) a registration outside the added lines, (2) a **public entry
point** the reproduction calls *without naming the new symbol*, and (3) the registration or
dispatch line **in the executed-lines trace**. Four adapters — argparse, click, Flask/FastAPI,
pytest fixture — each with its false-positive risk; the pytest one is specified and then
**recommended disabled**, because a crash inside a test tree is not a product defect.
§4 walks the owner's `attest 2878d4012e` case end to end and names the one place it would still
stop (§3's environment control wants a pre-existing test that names the caller, and that module
has none).

**The ceiling, measured free** ([`scripts/corpus/registry_ceiling.py`](../scripts/corpus/registry_ceiling.py),
name-based and therefore an over-count; it refuses to report unless it first finds the positive
control, and it does):

| population | rows | no call site today | scanned | **newly admitted** |
|---|---|---|---|---|
| E-04 stratum v2 new-code candidates | 224 | 200 | 194 | **0** |
| the 53 recorded receipt bundles | 53 | 25 | 1 | **1** — `attest 2878d4012e` |

**Zero of 224, structurally.** The 176 `us-stock-helper` and 26 `corum` candidates sit in head
trees with **no registration site of any of the four shapes** — their decorators are `@dataclass`
and `@property`. The 22 `attest` candidates sit in the only tree that registers anything, and
none of the 13 unwitnessed symbols is one of the registered ones. **The 10.7% ceiling does not
move.** The design's own recommendation: **keep §7**, revisit when a CLI- or web-shaped
repository enters the traffic, and if ever built, build argparse only and measure it first.

## 5. For the owner — three items

1. **What is a control, now that one was a real defect?** Three readings and this handoff picks
   none: (a) exclude `f4f2cfec9d` with its row labelled and resume the last 14 (~$0.30) — the
   2026-09-03g precedent; (b) tighten the definition so a control must also be unreachable under
   the current interpreter's semantics — hard, probably circular; (c) accept that controls carry
   a real base rate of true defects, and report the bound as a bound on *wrong* publications
   only, adjudicating each publication. **Default: (a)**, because it is the only one that gets
   `G-NULL-001a` an independent bound this month, and (c) is what the report already does in
   substance.
2. **Clause (c) drawered a value regression on a forward pair.** D-135's exoneration rests on 7
   of 8; this is one on the other side, and the value class is now `0 of 1` partly because of it.
   **Default: leave the rule alone and note the case.** One candidate cannot move a policy, and
   the alternative — weakening (c) — is what D-132 and D-134 were written to prevent.
3. **`more-itertools` has a live defect and this project holds the reproduction.** Reporting it
   upstream is a judgement call about this project's public posture, not an agent's to make.

## 6. Not done, and why

- **The last 14 controls** of the independent population, and the 3 that DEFERred on the image
  bootstrap. Blocked on item 1, not on money (~$0.30).
- **Pair 4's 25 budget-refused candidates.** A recall number taken at `--budget 1.00` on a
  42-candidate diff measures the budget as much as the product; re-running that one pair at
  `--budget 3.00` is ~$2 and would say whether anything is hiding there.
- **The registry witness is not implemented**, by instruction and by its own recommendation.
- **The corpus was not extended** past 11 forward pairs, by instruction.
- **Session working roots are not cleaned at exit** (§1), deliberately.
- **No GitHub-runner `gates` workflow** was triggered for this tip.

## 7. The gates at this tip

`ruff check .` clean. `mypy` clean over **84** source files. Full `pytest --cov=src/attest`: see
the note below. **The isolation tests ran this time** — the container backend is available on
this host again, which it was not last window.

*(An earlier full-suite run in this window failed 1 test and errored 3 in
`tests/benchmark/test_m01_offline_measurement_probe.py`. That is the M01 probe's own
**clean-tree guard** firing on uncommitted `src/` changes, not a regression: at the committed tip
that module passes 8 of 8.)*
