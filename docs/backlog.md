# Backlog

Findings that did not earn a fix, one line each: `file:line — what, and why it
was not fixed now`.

Per D-049, a self-review defect earns a commit only when it can be reproduced.
Everything else lands here: unreproduced "could in principle" hardening, and
every finding from a second review round. Nothing here is a promise to act —
this is the drawer, and items leave it only when a task is scoped to them or a
reproduction turns one into a real defect.

<!-- entries below, newest first -->

- F redefined once (D-064) and measured once; **not measured again in this task, by design.**
  At the anchor-line unit the graded values are directionally suggestive on two of four
  fields — defect lines were touched more recently (median 65 vs 109 days since last change)
  and by a larger share of repair-worded commits (mean 0.30 vs 0.14) — while commit count and
  distinct authors have identical medians and the distributions overlap heavily throughout.
  At the candidate unit, which is what the product actually emits, the control arm produced
  1 candidate against 25, so no comparison exists there at all. This is neither a refutation
  nor grounds to price F. Pricing needs a control arm that produces candidates and a second
  corpus; both need their own owner-approved work order. A third or fourth slice of the same
  history was deliberately not attempted.
- The D-064 defect-line group may carry a recency advantage from corpus construction: a
  BugsInPy head sits at the bug-introducing commit, so the defect region was necessarily
  touched recently in that head's own history. Real pull requests also review recently
  changed code, so the analogy is not empty, but the size of that inflation is unmeasured and
  any future pricing argument has to bound it first.

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
