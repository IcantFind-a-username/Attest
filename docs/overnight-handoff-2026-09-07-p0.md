# Checkpoint — 2026-09-07 p0 (`fbcbefa` → `52d3a2b`)

**Phase 0 done, plus the two engineering items phase 1 measures.**

- **0.1 D-154 fixed (D-155).** A torn delivery journal — attempts written, no
  finalization — is now **sealed** by a second terminator, `delivery_journal_abort`,
  appended by the next `attest review` before the alpha projection runs. It carries
  the same binding a finalization does (digest over the ordered attempts) plus a
  reason; **no existing row is edited**. What actually settled is still projected as
  a publication. RED: `tests/test_delivery_journal_abort.py`, 7 — including the
  end-to-end one (kill after the last settlement, then review again; on the previous
  implementation it raises `delivery journal requires one exact finalization`) and
  three tamper tests (forged digest, missing reason, edited sealed row).
- **0.2** `.github/workflows/pull-request.yml` reviews this repository at the
  action's own default **$1.00**, up from the pinned $0.25. `samples` untouched (K).
- **0.3 gates**: `ruff` clean, `mypy` clean over 88 files, full suite **1 failure +
  3 errors, all four in `tests/benchmark/test_m01_offline_measurement_probe.py` and
  all four caused by a dirty working tree** (that probe refuses to run against an
  unclean checkout by design). Re-verified at the clean tip below.
- **D-156, free, needed by 1.1.** Lock files (`poetry.lock`, `uv.lock`, `pdm.lock`,
  `Pipfile`, `Pipfile.lock`, `requirements.lock`) join the image tag digest, and the
  image now reports **reused or built**; the verification stage writes an
  `image_cache` ledger row. RED: `tests/execution/test_image_cache.py`, 8.
- **D-157, free, needed by 1.1.** `repro_concurrency` (default **2**): different
  candidates' reproductions overlap, the three runs inside one candidate stay
  serial. Each concurrent candidate journals into a `BufferedLedger` flushed in
  ranked order, so **the ledger bytes are identical serial or parallel** — that is
  the RED. `Budget.reserve/settle/cancel` now hold a lock, because a raced
  read-modify-write loses a reservation and a lost reservation is spend above the
  cap. D-111's *tail* genuinely weakens (a lower-ranked candidate may hold the last
  of the budget); `tests/test_ci_flow.py`'s D-111 test is pinned at
  `repro_concurrency=1`, which is the condition it is about. RED:
  `tests/test_repro_concurrency.py`, 4.

**Commits:** `5792afc` (D-154), `75e3571` (budget), `75cb9c8` (D-156), `42afd78`
(D-157), `52d3a2b` (DEVSPEND reservation).

**Spend so far: $0.00.** Reserved $10.00 for 1.1.

**Not done in this phase:** nothing.

**Next:** 1.1 launched in the background — the 17 budget-starved commits of the
40-row table (11 `attest`, 6 `us-stock-helper`) re-run at `--budget 1.00`, shadow,
`--code` pinned to the worktree at `42afd78`.
