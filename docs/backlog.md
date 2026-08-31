# Backlog

Findings that did not earn a fix, one line each: `file:line — what, and why it
was not fixed now`.

Per D-049, a self-review defect earns a commit only when it can be reproduced.
Everything else lands here: unreproduced "could in principle" hardening, and
every finding from a second review round. Nothing here is a promise to act —
this is the drawer, and items leave it only when a task is scoped to them or a
reproduction turns one into a real defect.

<!-- entries below, newest first -->

- `src/attest/review/executor.py:46` — Wave 4's in-process generation instruction did
  not solve D-037(c): all four schema-valid reproductions in the bounded retest still
  attempted child processes under the unchanged container guard. A deterministic,
  project-aware synchronous adapter (rather than prompt wording or weaker isolation) needs
  an owner-approved design before another paid run.
- `src/attest/review/ledger.py:80` — shared `ci_final` validation preserves `ValueError`
  behavior but changed several message strings; no repository caller depends on them, and
  the later-round compatibility concern is deferred under D-049 rather than opening another
  repair loop.
