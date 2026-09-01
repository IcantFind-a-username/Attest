# Real-data evaluation status

> **Historical evidence, not the current roadmap.** This is the overnight operator report
> as written on 2026-08-30. Current architecture, work order, status, and claim rules live in
> [`architecture/target-algorithm.md`](architecture/target-algorithm.md),
> [`roadmap.md`](roadmap.md), and
> [`acceptance/evolution-gates.md`](acceptance/evolution-gates.md). The original observations
> below are preserved; the audit errata are authoritative for their interpretation.

## Audit errata — 2026-08-30

- The feature branch was later merged to `main`; the branch/head and pending-merge lines
  below are historical.
- “761 tests passing” was a timestamped run, not a durable gate. A fresh audit reproduced
  one date-sensitive acceptance failure because the test hard-coded 2026-08-29 while the
  implementation used the current clock. M-03 owns the deterministic fix.
- The 0/296 constructed-null observation was produced mainly on pre-D-029/D-030 code,
  included infrastructure abstentions, and expanded after earlier looks. The comparable
  current-code post-fix observation was much smaller. It is not a natural-PR guarantee or an
  e-process proof.
- The ten repeats were one diff and all stayed in a structurally forced no-V drawer. They
  show one-case operational consistency, not independent/general decision stability or a
  learned Core effect.
- The receipt contains 9 accepted pairs from one project and a missing-test-shaped oracle.
  The committed excluded rows do not retain the run evidence claimed below; the receipt is
  hash-consistent but not independent execution authenticity or semantic truth.
- The reported control/replay counts explicitly described below sum to nine, not ten. The
  five replay attempts all DEFERred with no finding, so finding precision and recall were
  not estimated; the defensible operational statement is surfaced delivery 0/5 with the
  recorded abstention reasons.
- Later per-candidate replay withdrew the report's containment-vs-shelling attribution.
  All four retained generated tests were in-process. For the two candidates with exact
  diagnostic replays, the first child-process audit event came from old pytest bootstrap via
  Python 3.8 `platform.uname()` calling `uname -p`, before Black's tested API ran. The other
  two old candidate reasons remain unrecoverable; see D-057 and `overnight-handoff.md`.
- The 11.5–33% scheduling saving is a synthetic mechanism result with assumed outcomes and
  cross-task pooled ordering. It is not a production or within-PR Core result.
- The two Phase-3 runs are integration smoke repetitions on planted fixtures, not independent
  statistical replications.

Date: 2026-08-30 (overnight autonomous run)
Branch: `feature/real-data-evaluation`
Head: `c9aa966` — all eight plan tasks complete

## Where things stand

Every task in `docs/superpowers/plans/2026-08-29-real-data-evaluation.md` is
implemented, tested, and pushed. The full decision trail for the night is
D-020 through D-037 in DECISIONS.md; the spend trail is DEVSPEND.md
($3.59 of the $10 cap). Gates at head: 761 tests passing, coverage above the
90% floor, ruff and mypy clean.

| Task | Outcome |
|---|---|
| 4 | Differential V: head FAIL x3 + base PASS x3 in isolated worktrees; evidence classes recorded; two adversarial-review defects (rename false positive, base-imports-head) found and fixed two-way (D-020/022/029/030) |
| 5 | Replay runner, generic `evaluate_project` API, hashed artifact store, deterministic reports (D-025) |
| 6 | Ten-repeat stability + three-arm comparison CLIs, receipt-disciplined (operational vs accuracy split) |
| 7 | `live-local` with paid opt-in, atomic checkpoint machine, `--resume` that never repeats a paid call, per-source interpreter mapping, calibration report gated on the receipt |
| 8 | Null grids, monitor-policy simulations, two-ledger V-only model with VOI scheduling (11.5–33% verification-budget saving vs FCFS) — all recommendation_only (D-034) |

## Measurements now on record

- Null false-confirmation rate of differential V: **0/296**, Wilson upper
  0.0128, clearing the e-value ceiling D-026 derived (D-027/031; three limits
  stated in the entry).
- Ten live repeats of one diff: **10/10 identical decisions** while candidate
  counts, votes, and prose varied (D-035).
- Phase-3 GitHub Action acceptance passed twice on private scratch
  repositories, three arms each (docs/acceptance/phase-3.md).
- Corpus receipt issued: **9/20 pairs validated** (all black), 11 excluded
  with run evidence; the missing-test caveat is D-036 and gates any accuracy
  claim.
- First live corpus pilot: controls 4/4 silent, replays 0/5 surfaced, all
  safe defers — precision held at zero recall; the blockers are reproduction
  GENERATION robustness and containment-vs-shelling-tests, not the gate
  (D-037).

## Claims retracted overnight (do not re-assert)

- The wealth process is not an e-process; error control = cap arithmetic +
  differential-V reliability (D-026; README updated).
- "Arms statistically indistinguishable at high correlation" — wrong test on
  paired data; withdrawn (D-023 restated; McNemar p=3.7e-9).
- "The discount is priced against correlation itself" — the fairness control
  had only run where the gate silenced the discounted arm; withdrawn.
- "gamma=RHO is where D-007's assumption holds" — the sweep axis was clone
  rate, not correlation; no clone rate makes the schedule the true LR.

## Owner decisions pending (ground rule 8)

The list below is the historical pending list at report time. Merge-to-main has since
occurred; current decision points are in `docs/roadmap.md`.

1. Price (or keep unpriced) the `new_code_candidate` class — the adoption
   ceiling; discriminator and fabrication guard are in place and tested.
2. BugsInPy oracle rule: all nine validated buggy-FAILs are missing-test
   signatures; tighten (empties the corpus) or permit declared test-file
   transplant (D-036).
3. Merge to main so `uses: <owner>/attest@main` resolves (the documented
   install path is currently a dead pointer).
4. Whether corpus labels count toward the 500-label recalibration line.
5. `gh auth refresh -s delete_repo` to clean up three retained scratch repos.
6. Next paid measurements: null rate on real PRs; full 9-pair live-local run
   via the new Task 7 CLI (`--python source-ace4efb05d87=<corpus venv>`).

## Verify before trusting

```bash
git log --oneline fd359bc..c9aa966
.venv/bin/pytest
.venv/bin/ruff check .
.venv/bin/mypy src/attest
.venv/bin/python scripts/benchmark.py validate --manifest benchmarks/attest-v1/manifest.json --offline
```

The corpus cache (interpreters, venvs, checkouts, isolation wrapper) lives at
`/Users/franz/Documents/attest-corpus-cache` with its own RUNLOG.md.
