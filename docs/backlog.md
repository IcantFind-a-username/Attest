# Backlog

Findings that did not earn a fix, one line each: `file:line — what, and why it
was not fixed now`.

Per D-049, a self-review defect earns a commit only when it can be reproduced.
Everything else lands here: unreproduced "could in principle" hardening, and
every finding from a second review round. Nothing here is a promise to act —
this is the drawer, and items leave it only when a task is scoped to them or a
reproduction turns one into a real defect.

<!-- entries below, newest first -->

- **The pricing layer will not be activated under foreseeable evidence, and F is not the
  reason.** Resolved by `7eaa366` (D-065). Crossing the surfacing threshold with a fourth
  channel capped at `c` needs `S·T ≥ 10/c`; at the owner's `c = 1.2` that is 8.334, and the
  observed maximum `S·T` over every candidate this project has recorded is **3.0**, with
  `T = 1.0` on all 26 and `S ≤ 3.0`. The reachable ceiling of 9 that makes 1.2 sufficient
  has never been approached in a real run. Closing a factor-of-2.8 gap means moving a cap or
  an alpha, which `AGENTS.md` §16 reserves to the owner. Nothing here is a request to move
  one. Two facts are worth carrying forward if the question reopens: a *flat* cap cannot
  discriminate at all, because its crossing set is exactly `{S·T ≥ 10/c}`, a function of S
  and T that carries no F information; and at `c = 1.2` the answer is invariant to how F is
  graded, since any multiplier bounded by 1.2 still needs `S·T ≥ 8.334`.

- **F does not discriminate at the candidate unit on the population available.** Resolved by
  `7eaa366` (D-065); this supersedes the prerequisite recorded in the D-064 entry below.
  A control arm that emits candidates was not needed after all: splitting the 26 recorded
  candidates by whether the anchor lands on the corpus's labelled defect region gives 20
  against 5 within the same reviewed revisions. The two fields D-064 called directionally
  suggestive do not carry to this unit (repair share inverts, 0.042 vs 0.200 by mean;
  days-since-last-change disagrees by median and mean), the two that were flat separate only
  weakly, and the percentile bands do not separate the groups. F is also near-constant inside
  a single review — repair share takes one distinct value in six of the seven multi-candidate
  cases — which is decisive, because re-ordering candidates within one review is the only
  thing a priced F would do. **This is not a refutation of F:** n = 5 on the non-defect side,
  and four of those five anchor in `tests/test_black.py`, which BugsInPy cannot label because
  its `bug_patch.txt` carries source hunks only. That group is unlabelable, not verified
  clean. A second corpus, or any corpus whose control arm emits candidates, would still be a
  better test — and still needs its own owner-approved work order.

- `src/attest/review/history.py:112` — the graded F observation replaced `git blame -L` with
  `git log -L`, which walks line history rather than reading one blame record. Measured at
  ~0.1 s per candidate on this repository and on the black corpus checkouts, and it fails
  open at a 15 s timeout, so no defect is reproduced here. The worst case on a very large
  history is unmeasured; if a review ever spends real time in the history phase, cap the
  traversal with `--max-count` before touching the timeout.

- F redefined once (D-064) and measured once; **not measured again in this task, by design.**
  At the anchor-line unit the graded values are directionally suggestive on two of four
  fields — defect lines were touched more recently (median 65 vs 109 days since last change)
  and by a larger share of repair-worded commits (mean 0.30 vs 0.14) — while commit count and
  distinct authors have identical medians and the distributions overlap heavily throughout.
  At the candidate unit, which is what the product actually emits, the control arm produced
  1 candidate against 25, so no comparison exists there at all. This is neither a refutation
  nor grounds to price F. ~~Pricing needs a control arm that produces candidates and a second
  corpus; both need their own owner-approved work order.~~ **Superseded by `7eaa366`
  (D-065)**, which obtained the candidate-unit comparison from a different split of the same
  26 candidates rather than from a new control arm; see the two entries above for what it
  found. A third or fourth slice of the same history was deliberately not attempted.
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
