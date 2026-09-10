# The process guard on the merge base: scoped, and the answer is no

**Owner instruction, 2026-09-14: scope this, do not implement it.** The scoping produced a
result that removes the item rather than sizing it, so this document is the finding and not a
plan.

## What was proposed

The 2026-09-12 held-out measurement lost **17 of 56** verification attempts to
`reproduction attempted to create a child process` (12) or `… a thread` (5). Every one was a
**probe run on the merge base**: `seaborn`, `sphinx` and several others spawn a thread during
an ordinary import, and the containment that exists to stop *head* code from doing it refused
the recording. The proposal wrote itself: the base revision is the one the defect was fixed
in, there is nothing untrusted to contain there, so relax the thread and child-process guard
on the base side and recover those 17.

## Why it buys nothing

**The import that trips the guard on base trips it on head too.**

A differential runs the same file against both revisions. The thread is spawned by importing
the project, and both revisions import the project. Relaxing the base side does not produce a
receipt; it moves the deferral from

    probe deferred on base: reproduction attempted to create a thread

to

    head run 1/3 deferred: reproduction attempted to create a thread

Measured rather than argued. A two-revision fixture whose module spawns a thread at import
time, with the change in the function under test:

| run | outcome | reason |
|---|---|---|
| the differential as it stands | `DEFERRED` | `probe deferred on base: reproduction attempted to create a thread` |
| the same probe body against the **head** worktree, directly | `deferred` | `reproduction attempted to create a thread` |

Head runs recorded: 0. Base runs recorded: 0. There is no revision on which that tree's import
completes under the guard, so no relaxation of one side changes any verdict.

## What the real question is, and whose it is

The finding is not about `base` versus `head`. It is that **the guard refuses an ordinary
import**, and it does so on every revision of every project whose package starts a thread or a
subprocess at import time. That is a property of the isolation profile, not of the recorder.

Changing it is an owner decision under `AGENTS.md` §16 (production isolation backend /
controlled-subprocess profile), and the options are not equivalent:

1. **Allow thread creation, keep the child-process and network refusals.** A thread is inside
   the same address space and the same `RLIMIT_NPROC` containment; it cannot outlive the run
   or reach the network, which the two guards that would remain still refuse. This is the
   narrowest change and it covers the 5 thread cases directly, plus an unknown share of the 12
   child-process ones that are really thread pools.
2. **Allow a child process during the import phase only, then re-arm.** Covers more, and needs
   a phase boundary the sandbox does not currently have -- the guard is a `sys.addaudithook`
   with no notion of "still importing". Larger, and the boundary itself becomes something an
   attacker aims at.
3. **Leave it.** The 17 stay refused, and every one of them is a project whose *whole
   repository* Attest cannot review, on any pull request, ever -- not a case it declines once.

Nothing here recommends one. What this document establishes is that **the base-side split is
not among the options**, and that a window spent implementing it would have produced no
receipts and a false explanation for why.

## What was changed instead

Nothing in the isolation profile. The two mechanical losses the same measurement named were
addressed where they are actually decidable, in the probe pipeline (D-206): probes derived
from the repository's own tests, and a static refusal of a probe that imports nothing the tree
defines.

**Trace:** D-198 (the backlog line this answers), D-206; the 2026-09-12 held-out report;
`AGENTS.md` §16; `INV-SEC-001`.
