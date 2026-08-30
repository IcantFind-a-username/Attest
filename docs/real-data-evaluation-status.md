# Real-data evaluation status

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
