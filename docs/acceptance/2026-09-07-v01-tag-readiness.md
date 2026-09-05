# The `v0.1` conditions, re-read — 2026-09-07

Previous read: [2026-09-06c](2026-09-06c-v01-tag-readiness.md). Mainline §1 states **seven**
conditions; earlier handoffs have sometimes said "six", which is condition 6 (the L-01 exit
list) being counted as part of the release mechanics rather than as a product condition. All
seven are read below.

## The seven conditions

| # | condition (mainline §1) | 2026-09-06c | **now** | what moved |
|---|---|---|---|---|
| 1 | an outside repository installs from a stable ref, adds the Action, receives PR comments | holds | **holds** | unchanged. It is still met by a `DEFER`; no receipt-backed comment has reached an outside repository |
| 2 | every author-visible finding carries its level's evidence form and was admitted by that level's non-model adjudicator | holds, four levels | **holds, five classes** | yellow (b)'s exception-propagation class is author-visible and its adjudicator is `ast` alone (D-164) |
| 3 | head code cannot read secrets, reach the network, or forge a result | **does not hold** — 4 of 13 fixture classes | **does not hold, and it moved the most** — **9 of 13** classes dispatched and marked on a GitHub runner, positive control certified in the same run ([matrix](2026-09-07-redteam-nine.md)) | five classes added; **the external observer is still absent**, and no number of classes replaces it |
| 4 | held-out corpus: silent on every control, a stated non-trivial share of eligible defects certified | does not hold | **does not hold, and the denominator is now stated** | D-158: the held-out slice reports **crash/exception recall only — 4 of 16, not 4 of 28**. Controls: 0 false publications on 40. The share the owner must state is still unstated |
| 5 | one prospective shadow run with no false publication | does not hold | **does not hold** | unchanged. This window's 17 + 13 shadow reviews are of commits that existed before the protocol, so they are not prospective |
| 6 | the L-01 exit list is done | holds, its gate does not | **holds, and its release mechanics are now done too** | packaging metadata, a gated wheel in CI, a tag workflow, `install-ref` in `action.yml`, and the version bumped in one place |
| 7 | every author-visible line obeys the output contract | holds for all four | **holds** | unchanged; the unsupported-scenario lines and the budget-stopped silence line are contract lines too (D-159, D-161) |

**Five of seven hold. The tag is blocked on 3, 4 and 5** — the same three as the last three
reads. Condition 3 moved from *4 of 13* to *9 of 13*; conditions 4 and 5 did not move, and 4's
change is that its number is now honestly denominated rather than larger.

## Why `v0.1.0-rc.1` is nonetheless tagged, and what it is not

The owner's instruction for this window is explicit: tag an **internal trial ref**, marked *"内部
试用，非公开发布"* — internal trial, not a public release — and bump the version with it. That is
a different object from `v0.1.0`:

- it is a **release candidate**, and the three failing conditions are named in this file, in the
  CHANGELOG entry and in the tag's own message;
- **nothing is published to PyPI.** The release workflow attaches a wheel and an sdist to the
  GitHub Release and stops. The name `attest` on a public index is not claimed by an experiment;
- the previous read refused to bump the version because *"a tree that says `0.1.0` while
  conditions 3, 4 and 5 fail is a tree that lies about itself."* `0.1.0rc1` does not say
  `0.1.0`. A release candidate is exactly the object whose conditions are not all met, and
  saying so in the version string is the honest form.

## What would move each remaining condition

1. **Condition 3** needs the four remaining fixture classes (`/proc`, home/git, native syscall,
   namespace) and — the hard part — a **sandbox-external supervisor or kernel observation**
   proving OS denial, plus an isolated canary environment with no real secret. Days of work, and
   the only remaining condition that is a safety claim rather than a measurement.
2. **Condition 4** needs the owner to state the share. The number exists and is denominated.
3. **Condition 5** needs calendar time: a prospective window cannot be assembled from history.
   The protocol is written and the cost is ~$10–20 for 100 units.
4. **Condition 1's honest form** needs one paid review on a pair known to certify, in an outside
   repository, and a remote write.
