# What a `v0.1` tag still needs, re-read — 2026-09-06b

Owner instruction 4 of this window: **do the documentation items of the gap list outright, list
the code items and do not start them.** The previous reading is
[2026-09-06](2026-09-06-v01-tag-readiness.md); this one says what moved, what was finished here,
and what is left.

`v0.1.0-pilot.1` is still the only tag this repository has.

## 1. The seven conditions

| # | condition (mainline §1) | 2026-09-06 | **now** | what moved |
|---|---|---|---|---|
| 1 | an outside repository installs from a stable ref, adds the Action, receives PR comments | holds | **holds** | unchanged |
| 2 | every author-visible finding carries its level's evidence form and was admitted by that level's non-model adjudicator | holds | **holds, over three levels** | yellow (a) became author-visible (D-145) and its adjudicator — `ast` over the call graph, then the format adjudicator — has no model in it either |
| 3 | head code cannot read secrets, reach the network, or forge a result | does not hold | **does not hold** | unchanged: 4 fixture classes of `G-SEC-002`'s 13, all observed from inside the sandbox |
| 4 | held-out corpus: silent on every control, a stated non-trivial share of eligible defects certified | does not hold | **does not hold, and the null side is now closed rather than open** | D-144 closed `G-NULL-001a`'s independent population at **answered n = 7, 0 wrong, 1 true positive on a control**; D-134's 5.2% at n = 58 remains the only bound. The recall side gained a second forward-pair number under a new generator (D-146) and still has no held-out number under the current policy |
| 5 | one prospective shadow run with no false publication | does not hold | **does not hold** | unchanged |
| 6 | the L-01 exit list is done | holds, its gate does not | **holds, its gate does not** | the nine release drills now rehearse the product's default generator rather than the legacy one |
| 7 | every author-visible line obeys the output contract | holds for both author-visible levels | **holds for all three** | yellow (a) publishes through `claim_line` and is refused by the same adjudicator |

**Four of seven hold. The tag is blocked on 3, 4 and 5, in that order of difficulty** — the same
three as before, and none of them is a documentation problem.

## 2. What this window finished

Both were documentation items on the previous list.

- **Release mechanics, the documentation half (item 7).** [`CHANGELOG.md`](../../CHANGELOG.md)
  now exists: an `Unreleased` section covering everything since the pilot tag, and a
  `v0.1.0-pilot.1` section that says in as many words that a pilot tag is not a release. Every
  entry names what the change cost in recall or in trust, because in this project those are the
  same currency.
- **The two silent levels, said out loud (item 8).** It is now **one**. Yellow (a) is
  author-visible as of D-145; the gate level remains in shadow with 0 executed observations
  (D-137) and a measured 10.7% ceiling, and the changelog's *Known limits* section says so.

**The version string was deliberately not bumped.** `pyproject.toml` still reads
`version = "0.0.1"`, `action.yml` still pins no default ref, and the quickstart still names
`@v0.1.0-pilot.1`. Those four edits are one mechanical commit and they belong to the commit that
*cuts* the tag: a tree that says `0.1.0` while conditions 3, 4 and 5 fail is a tree that lies
about itself, and the lie would be indexed by anyone who cloned it. They stay on this list.

## 3. What is left — listed, not started

Ordered by what blocks the tag.

1. **`G-SEC-002`: 9 of 13 fixture classes, and an external observer.** Missing: `/proc`,
   home/git, DNS/IPv6, native syscall, fork/thread bomb, exec, daemonisation, resource
   exhaustion, namespace. The gate also requires a **sandbox-external supervisor or kernel
   observation** proving OS denial, which does not exist in any form, plus an isolated canary CI
   environment with no real secret. *Code and infrastructure; a fixture suite, an observer
   design, runner time, no model spend.* **Still the largest single gap.**
2. **Condition 4's recall side has no held-out number under the current policy.** The 5-of-29
   figure predates intent v3/v4/v4.1, D-124, D-138 and now D-146. `G-RECALL-002` needs the
   held-out slice re-run under the probe generator; ~$10–15 at the measured price. *Paid run.*
3. **Condition 5 needs a genuinely prospective window.** It cannot be assembled from history —
   it needs units that did not exist when the protocol was frozen. Calendar time plus ~$10–20
   for 100 units; the protocol is already written. *Paid run plus waiting.*
4. **No `gates` workflow run on a GitHub runner at this tip.** The suite passes locally at every
   tip; the last runner-green record is older. *Free; one workflow dispatch.*
5. **A receipt-backed comment has never reached an outside repository.** Condition 1 is met by a
   `DEFER`. Nothing in §1 requires more, and a `v0.1` whose only external artifact is an
   abstention is still a weak first impression. *One paid review on a pair known to certify,
   plus a remote write to a repository the owner owns.*
6. **Release mechanics, the mechanical half.** `pyproject.toml` `0.0.1` → the tag; a default ref
   in `action.yml`; every `@v0.1.0-pilot.1` mention moved. *Free, one commit, and it belongs to
   the tagging commit.*
7. **The gate level is built and unshipped.** Shadow, 0 executed observations, a 10.7% ceiling.
   It does not block the tag under §1 — condition 2 governs the levels that speak — and the
   changelog says a tag would ship it silent.
8. **The probe generator has one measured population.** D-146 was measured on the 11 forward
   pairs and nowhere else. Its effect on the null population, on the held-out slice and on
   ordinary shadow traffic is unmeasured, and a `v0.1` that claims anything about generation
   should say over what. *Paid runs; the drivers exist.*

## 4. What is explicitly not on this list

Corpus extension, the registry witness, the learned scheduler, the TypeScript executor, and any
whole-repository scan. All are off the mainline until after L-01, and none of them is a `v0.1`
blocker.
