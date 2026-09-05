# Handoff — 2026-09-05c (`a8b53aa` → `e3728a0`): three decisions landed, two measurements blocked by the host

**Window spend $1.663296 of $30; cumulative $52.226537 of $90.** Remote writes: **push to `main`
only**. Gates at the tip: `ruff check .` clean, `mypy` clean over 83 source files,
`git diff --check` clean; `pytest` result in §6.

**One fact governs half this handoff.** Since mid-window, **every Docker bind mount of a path
under `/Users/franz` hangs on this host** — `docker run --mount type=bind,src=/Users/franz/Documents/Attest/docs,dst=/x,readonly … true` does not return in 40 s, while the same command with
`src=/private/tmp` returns in **1.3 s** and runs the very reproduction that timed out in 0.23 s.
It is not this product (red's own differential path DEFERs identically), not load (it persists at
load average 6), and no container of any project holds such a mount. **The remedy is a Docker
Desktop restart, which would stop three containers belonging to other work on this machine, so I
did not do it.** Everything that needs to execute head code is blocked behind it.

## 1. The independent null population: n = 68 built, 0 informative controls run (D-136)

[Report](acceptance/2026-09-05-g-null-001a-independent.md), [data](acceptance/evidence/2026-09-05-g-null-001a-independent.json), **$1.075100 of $4.00.**

Same eight clones, same 2026-03-04 cutoff, same control definition; **shifted seed**, and all
**903** commits the first draw examined removed from the pool. **n = 68, overlap with the 58 = 0.**
The quota/attempt ladder is preregistered in the driver — (13,120) → (16,300) → (20,600) →
(25,900) — drawn once at the deepest rung, and the smallest rung reaching n ≥ 50 read back:
**(16, 300)**. At the first population's own setting a disjoint draw yields only n = 31.

| controls reviewed | eligible | reproductions attempted | **executed** | **informative controls** | publications |
|---|---|---|---|---|---|
| 45 of 68 | 13 | 13 | **0** | **0** | 0 |

**No bound, and none is claimed.** A control that cannot buy evidence cannot publish, so "0
publications" over 45 such controls says nothing. The driver's table now reads the run's own log
rather than the ledger and reports `informative_controls` beside `reviews`, because a `review_run`
ledger row carries no head sha and a ledger-only table cannot name the control a row is about.

## 2. The gate level, in shadow (D-137)

[Report](acceptance/2026-09-05-gate-shadow.md), **$0.588196 of $12.00.** `src/attest/review/gate_level.py`,
behind `ReviewConfig.gate_shadow`, **off** in the product. On, it writes `gate_shadow` ledger rows
and `.attest/shadow/gate/` records and reaches no comment, no summary, no `CertifiedFinding`, no
family selection, no calibration denominator. **`G-NEWCODE-001` now says in its own text that the
pilot precondition governs speech, not observation, and that shadow records count toward its 120
cases**; mainline §1.3 says the same and names the flag. That is **Read A with the carve-out**.

**Free, and it is the number the design said it owed** — over the 224 recorded new-code
candidates of E-04 stratum v2: **160 fully annotated, 80 admissible, 24 (10.7%) with a call site
outside the added lines.** 10.7% is the ceiling on what this level can ever publish about new
code in this traffic, and it cost $0.00.

**The live run bought 13 reproductions and executed none** — every one DEFERred at collection on
the host fault, at 60 s and again at 300 s. **Executed gate observations: 0.**

**The free replay over the 53 recorded receipt bundles is what carries a result:** 28 admissible,
20 through-caller, **4 would publish** — one finding under §5's per-PR cap, and it is the `corum`
overflowing-`Fraction` defect that rows 8 and 9 of the 2026-09-05b adjudication read by hand as
**real, and that clause (c) drawered.**

| clone | receipt | added line | exception | call site | verdict |
|---|---|---|---|---|---|
| `corum` | `c25c7fbb4c` (+3 more) | `src/corum/models.py:47` | `OverflowError` | `src/corum/models.py:87` | **would publish** |
| `attest` | `2878d4012e` | `scripts/corpus/heldout_run.py:128` | `JSONDecodeError` | **—** | drawer |

**`attest 2878d4012e` is in the table and goes to the drawer, and §7 is why.** `cmd_run` is
reached only through `argparse`'s `set_defaults(func=cmd_run)`, and §7 excludes a call reached
through a registry. **Two corrections to the instruction:** its pair is **not** in E-04 stratum
v2 (that stratum is the 40 newest `Attest` commits at its freeze; this commit is an hour older
than the oldest), so it ran as a named supplementary unit; and it is a **`regression`** candidate,
not `new_code`, so the live stage would never have reached it — the replay is the path that can
ask the gate question of a receipt red drawered.

## 3. Forward pairs: 11 distinct, of 2,005 commits (D-135)

[List and reasons](corpus/forward-pairs.md), [data](../benchmarks/attest-v2/runs/2026-09-05-forward-pairs.json), **$0.00.**

`scripts/corpus/forward_pairs.py`: take a repairing commit's own tests, find the first commit
behind it that fails them **whose own parent passes them**; that is `head`, its parent is `base`.
Both ends are probed. The subject line is not read — a commit that is not a repair produces no
boundary anyway, and reading subjects only lost the repairs whose authors did not write `fix`.

**13 resolutions over 11 distinct pairs** across `attrs` (2), `click` (2), `itsdangerous` (1),
`more-itertools` (4), `packaging` (1) — the full table is in the corpus document.
**The target was ≥ 15 and it was not met**: the eleven repositories were scanned to their limits
and the yield is **0.65%**. The dominant non-result — *no passing ancestor in the window*, 30% of
all commits — is the finding, not a defect: a fix's own test does not discriminate its defect on a
tree far enough back, because by then the code differs for unrelated reasons. **Zero pairs came
from this account's three repositories**, whose fixes repair defects born with the code they fix.

## 4. Not done, and why

- **The forward-pair reviews (instruction 4) did not run at all.** $0.00 of $12.00. A review whose
  reproduction cannot execute produces no value-class row, and the host fault means none can. The
  11 pairs are built and committed; the reviews are about $3.
- **The independent bound and the gate's executed observations** are owed for the same reason.
- **Fewer than 15 forward pairs.** §3; more scanning of these eleven repositories will not close
  it, another repository would.
- **The replay's control is not §3's control.** It executes nothing, so the record says
  `replayed from a recorded bundle; no §3 control was executed` rather than claiming one.
- **The gate's live wall clock was raised from red's 60 s to 300 s** for the retry, and every row
  says so. It changed nothing — the fault is not a timeout.

## 5. For the owner — three items

1. **Restart Docker Desktop, or tell me to.** It is the single blocker on the independent bound,
   the gate's executed observations and the forward-pair reviews — about **$4 of work** that is
   otherwise ready to run unattended. It would stop `onetap-ffmpeg9-verify`, `onetap-ci-timeline`
   and `onetap-private-trial-trial-1`, which is why I stopped instead.
2. **Does §7's registry exclusion stay?** It is what sends `attest 2878d4012e` — a real, unguarded
   `json.loads` on an added line — to the drawer, and `argparse`/decorator/plugin dispatch is how a
   great deal of Python is reached. **Default: keep it.** A reference in a dispatch table is not a
   witness that anything calls the code, and this level's whole claim is that something does. But
   the cost is now measured and named rather than assumed, and 10.7% is a small ceiling to shrink
   further.
3. **Is the forward-pair corpus worth extending?** 11 distinct pairs is a thin denominator for the
   first honest value-class recall number. **Default: run the 11 first** (~$3) and decide with the
   number in hand; a twelfth repository costs a clone and a night of free scanning.

## 6. The gates at this tip

`ruff check .` clean. `mypy` clean over **83** source files. `git diff --check` clean.
**`pytest --cov=src/attest` — 1,856 tests, all passed, no failure and no error**, coverage
**92.43%** against the 90% floor. Run twice, once over the whole suite and once with
`tests/execution/test_isolation.py` excluded: **both runs collected and passed the same 1,856
tests**, because that module skips itself at collection when the container backend is
unavailable — which, on this host tonight, it is (§0). **So the isolation tests did not run
here.** They ran on a GitHub runner two windows ago (run 33930801526) and they should be run
there again before this tip is trusted on that axis.

No GitHub-runner `gates` workflow was triggered for this tip; the only remote write this window
is the push of `main`.
