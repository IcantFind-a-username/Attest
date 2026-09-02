# Backlog

Findings that did not earn a fix, one line each: `file:line — what, and why it
was not fixed now`.

Per D-049, a self-review defect earns a commit only when it can be reproduced.
Everything else lands here: unreproduced "could in principle" hardening, and
every finding from a second review round. Nothing here is a promise to act —
this is the drawer, and items leave it only when a task is scoped to them or a
reproduction turns one into a real defect.

<!-- entries below, newest first -->

- `src/attest/review/history.py:1` — call-graph reachability and test-blind-spot slices were
  intentionally excluded from the first F-channel scope; either slice needs an independently
  preregistered owner work order before implementation or measurement.
- `src/attest/review/executor.py:52` — the process audit spans trusted pytest bootstrap and
  reviewed code: exact replays for `01dd26db09` and `ffe9efc79f` first marked Python 3.8
  `platform.uname()` invoking `uname -p`, not Black behavior. Separating attribution without
  weakening containment requires an owner decision and likely the X-02/X-03 execution-profile
  boundary; no allowlist, activation-timing change, or runner-policy change was retained.
- `src/attest/review/ledger.py:80` — shared `ci_final` validation preserves `ValueError`
  behavior but changed several message strings; no repository caller depends on them, and
  the later-round compatibility concern is deferred under D-049 rather than opening another
  repair loop.
- 2026-09-02 (C-03 gate): `tests/benchmark/test_m01_offline_measurement_probe.py` — three module-fixture errors (`source import or clean-tree guard failed`) only when the whole suite runs from the repository root; the file passes alone, inside `tests/benchmark`, and with `--cov=src/attest`. The C-04 full run (`71b99aa`), executed with no other pytest process alive, passed all of them; the two earlier runs overlapped concurrent pytest invocations in the same checkout, so concurrent runs are the leading suspect. Keep full-suite gates exclusive.
- 2026-09-02 (R-01 trial): with planner context 3 of 20 proposal samples stopped at the 2,400-token output bound (2 of 20 without context); the truncated samples are voided whole. If the E-02 pilot table shows parse/truncation as the largest candidates→eligible loss, R-02 pulls forward per `mainline.md` §2; otherwise consider a per-unit bound that scales with context length under D-051.
- 2026-09-02 (E-02 pilot): pytest's own repository is runner-is-subject — the reviewed pytest becomes the test runner from the tree, so the interpreter must satisfy the *reviewed* pytest (no `imp` on 3.12) and generated files (`_pytest/_version.py`) must be committed; an executor profile that pins the runner separately (X-01/X-02) would remove this coupling.
- 2026-09-02 (E-02 pilot): on CPython 3.8 `platform.system()` shells out to `uname -p` and trips the process guard at collection for any project that reads `platform` at import (requests, pylint); 3.9+ computes it lazily. Same root as D-057; the controlled-subprocess profile (X-03) is the owner-gated fix, the pilot pins 3.9+ meanwhile.
- 2026-09-02 (E-02 pilot): with planner context 10/32 proposal samples stopped at 2,400 output tokens, two cases losing all four samples; the generator returned `{}` twice on two cases. Both are precommitted-recovery (R-02) shapes; measure them on the dev-slice re-run before touching D-051/D-056 bounds.
- 2026-09-02 (V-02): the settrace-based line tracer roughly doubles wall time of the full test suite (12 → 36 min) because every guarded pytest run now traces; scope the tracer to the anchored file's frames only at the `call` event (already) and consider `sys.monitoring` (3.12+) for the executor profile that X-02 introduces.
