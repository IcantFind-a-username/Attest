# Checkpoint — 2026-09-07 p2/p3/p6 (`00b8bb3` → `3781d7d`)

Phases **2, 3 (except the two measurements 1.1 carries), and 6** are done. Free work
only; **$0.00 spent in this checkpoint**. 1.1 is still running in the background.

| item | decision | what it is | RED |
|---|---|---|---|
| 2.1 | **D-158** | held-out reports **crash/exception recall only — 4 of 16, not 4 of 28**; the value class comes from forward pairs only, with D-135's reversed-pair effect named. README's held-out row split in two. `attest.intent.v4.1` untouched | n/a (a caliber rule; the 12/4/12 split is recomputable from the results on disk) |
| 3.1 | **D-160** | green tells the same pair once: the `structural_note` row carries a fingerprint over both coordinates **and the source of both spans** | `test_green_dedup.py`, 5 |
| 3.2 | D-156 (p0) | image key covers lock files; `image_cache` ledger row records reuse | `test_image_cache.py`, 8 |
| 3.3 | **D-159** | four unsupported scenarios → one fixed `[silent]` line, exit 0 | `test_unsupported.py`, 10 |
| 3.4 | **D-161** | `daily_budget_usd` (rolling 24h, default off) + the silence line names *N candidates not verified* | `test_cost_guardrails.py`, 10 |
| 3.5 | D-157 (p0) | `repro_concurrency` 2; ledger bytes identical serial vs parallel | `test_repro_concurrency.py`, 4 |
| 3.6 | **D-162** | interpreter matrix **3.10–3.13**, primary 3.12; lock files count as declarations. Support matrix synced | `test_python_matrix.py`, 12 |
| 6.1–6.3 | **D-163** | `review --json`, `stats --json`, and a cost column in `--explain` | `test_machine_output.py`, 6 |

**Two corrections worth carrying forward.**

1. **3.3's first cut was wrong and the tests found it.** A pre-flight refusing a repository
   that *declares* no pytest fired on **37 of this product's own tests**, and every one was a
   legitimate review: Attest installs pytest into the image and writes the test it runs, so a
   repository with no test suite is supported. "No pytest" now means *pytest could not be
   provided in the built image* and is recognised from the bootstrap's own reason.
2. **3.5 weakens D-111's tail, and that is stated rather than hidden.** With two reproductions
   in flight the ranking still governs dispatch, but a lower-ranked candidate may hold the last
   of the budget. `tests/test_ci_flow.py`'s D-111 test is pinned at `repro_concurrency=1`.
   `Budget.reserve/settle/cancel` now hold a lock — a raced read-modify-write loses a
   reservation, and a lost reservation is spend above the cap.

**D-162 costs something, named now rather than discovered later:** held-out SWE-bench cases
that only install on 3.9 will no longer bootstrap. That is the price of a declared range.

**Not done here:** 2.2 (yellow (a) trigger counts on the $1.00 table) and 3.2/3.5's measured
numbers — both need 1.1's log, which is still being written.

**Next:** phase 7 (packaging + release workflow), phase 4 (nine-class security fixtures on a
runner), phase 5 (yellow (b) class 2), phase 8 (docs), phase 9 (backlog + rc tag).
