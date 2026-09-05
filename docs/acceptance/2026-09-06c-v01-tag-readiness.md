# The `v0.1` gap list, re-read — 2026-09-06c

Owner instruction 10 of this window: **anything on the `v0.1` gap list that is code and can be
finished in two hours, do; list the rest. Do not bump the version.**

Previous read: [2026-09-06b](2026-09-06b-v01-tag-readiness.md).

## 1. The seven conditions

| # | condition (mainline §1) | 2026-09-06b | **now** | what moved |
|---|---|---|---|---|
| 1 | an outside repository installs from a stable ref, adds the Action, receives PR comments | holds | **holds** | unchanged |
| 2 | every author-visible finding carries its level's evidence form and was admitted by that level's non-model adjudicator | holds, over three levels | **holds, over four** | yellow (b) is author-visible (D-151) and its adjudicator is `ast` and `git`; a model proposes and decides nothing |
| 3 | head code cannot read secrets, reach the network, or forge a result | does not hold | **does not hold** | unchanged: 4 of `G-SEC-002`'s 13 fixture classes, all observed from inside the sandbox |
| 4 | held-out corpus: silent on every control, a stated non-trivial share of eligible defects certified | does not hold | **does not hold** | the held-out slice was re-run under the probe generator this window ([report](2026-09-06c-heldout-probe.md)) — the first number under the current policy — and it is not a *pass*, only a number |
| 5 | one prospective shadow run with no false publication | does not hold | **does not hold** | unchanged. 40 commits of owner traffic were reviewed in shadow this window with 0 publications, but they existed before the protocol was written, so they are not prospective |
| 6 | the L-01 exit list is done | holds, its gate does not | **holds, its gate does not** | unchanged |
| 7 | every author-visible line obeys the output contract | holds for all three | **holds for all four, and now in the terminal too** | D-152 makes `attest review` print the same contract lines the comment does |

**Four of seven hold. The tag is blocked on 3, 4 and 5**, in that order of difficulty — the same
three as the last two reads, and none of them is a documentation problem.

## 2. What this window finished, from the previous list

- **Item 4, "no `gates` workflow run on a GitHub runner at this tip"** — done and free: the
  workflow ran on a runner at `61835fa` and at `975ff76`. It is now a routine of every push.
- **Item 8, "the probe generator has one measured population"** — **substantially closed.** It
  now has three: the 11 forward pairs (2026-09-06b), the **69-case held-out slice** and **50
  commits of ordinary owner traffic**, all under one implementation. Its effect on the null
  population is still unmeasured, and D-144 closed that population, so it will stay unmeasured
  unless a new one is built.
- **Item 7, "the gate level is built and unshipped"** — unchanged in status, but it now has
  **9 observations at the publishing grade out of 314 new-code candidates** rather than 0
  ([report](2026-09-06c-gate-shadow.md)).

## 3. What is left — the same list, re-ordered by what blocks the tag

1. **`G-SEC-002`: 9 of 13 fixture classes, and an external observer.** Missing: `/proc`,
   home/git, DNS/IPv6, native syscall, fork/thread bomb, exec, daemonisation, resource
   exhaustion, namespace — plus a **sandbox-external supervisor or kernel observation** proving
   OS denial, which does not exist in any form, plus an isolated canary CI environment with no
   real secret. *Code and infrastructure; days, not two hours.* **Still the largest single gap,
   and the only one that is a safety claim rather than a measurement.**
2. **Condition 4 is a number, not a pass.** The held-out slice now has a figure under the
   current policy. What condition 4 asks for is *silent on every control* **and** *a stated
   non-trivial share of eligible defects certified*; the report says which half holds.
   *No further work is defined until the owner states the share.*
3. **Condition 5 needs a genuinely prospective window.** It cannot be assembled from history.
   Calendar time plus ~$10–20 for 100 units; the protocol is written. *Paid run plus waiting.*
4. **A receipt-backed comment has never reached an outside repository.** Condition 1 is met by a
   `DEFER`. *One paid review on a pair known to certify, plus a remote write.*
5. **Release mechanics, the mechanical half.** `pyproject.toml` `0.0.1` → the tag; a default ref
   in `action.yml`; every `@v0.1.0-pilot.1` mention moved. **Free, one commit — and it stays
   here**, because a tree that says `0.1.0` while conditions 3, 4 and 5 fail is a tree that lies
   about itself. The owner's instruction not to bump says the same thing.
6. **Two open questions this window recorded and did not fix**, both one-line changes that
   would be wrong to make inside a measurement:
   - a probe can construct a state the program cannot reach, and no adjudicator checks it
     ([§4](2026-09-06c-value-class-adjudication.md));
   - the gate's `through_caller` grade does not distinguish a production caller from the change's
     own new test, and 3 of its 9 observations enter through a test
     ([§3](2026-09-06c-gate-shadow.md)).

## 4. Nothing on this list was a two-hour code item

The instruction's condition was "code, and finishable in two hours". Item 5 is code and is under
an hour, and it is the one item explicitly deferred by the same instruction. Items 1, 3 and 4
are days, calendar time, and a remote write to somebody else's repository respectively. Item 6 is
two one-line changes whose *measurement* is the work, not the edit.
