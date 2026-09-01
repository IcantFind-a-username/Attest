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
- D-059 left the process-audit window opening at `pytest_runtest_call`, so an event raised
  while the generated test module is imported is recorded but not adjudicated; widening it
  to collection start would keep the D-057 bootstrap carve-out and still adjudicate
  import-time reviewed code, and needs its own owner decision.
- The D-059 wave-4 replay lost 15/23 candidates to the per-case product budget
  (`--budget-usd 0.16`), not to any guard; a rerun with a per-case budget above ~$0.20
  would measure how many of those reach a differential.
