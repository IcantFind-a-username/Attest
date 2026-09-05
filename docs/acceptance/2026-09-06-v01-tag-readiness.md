# What a `v0.1` tag still needs — 2026-09-06

Owner instruction 5 of this window: re-check mainline §1 condition by condition and **list**
what is missing before a `v0.1` tag. Nothing here is done, started, or scheduled; it is a
reading of the repository at `84c7598`. The previous reading is
[2026-09-03](2026-09-03-mainline-six-conditions.md), whose conditions 1 and 2 have both moved.

`v0.1.0-pilot.1` is the only tag this repository has. The list below is what stands between it
and a `v0.1.0`.

## 1. The conditions, re-checked

| # | condition (mainline §1) | 2026-09-03 | **now** | what moved |
|---|---|---|---|---|
| 1 | an outside repository installs from a stable ref, adds the Action, receives PR comments | does not hold | **holds** | 2026-09-04: `us-stock-helper`'s runner installed the Action at `@v0.1.0-pilot.1`, built the production image and posted an author-visible comment (a DEFER) |
| 2 | every author-visible finding carries its level's evidence form and was admitted by that level's non-model adjudicator | holds (receipt only) | **holds** | the condition was amended 2026-09-04c to cover four levels; the two that are author-visible — red (kernel + binding + intent v4.1) and green (the measure, D-133) — both have a non-model adjudicator |
| 3 | head code cannot read secrets, reach the network, or forge a result | does not hold | **does not hold** | unchanged: 4 fixture classes of `G-SEC-002`'s 13, observed from inside the sandbox |
| 4 | held-out corpus: silent on every control, a stated non-trivial share of eligible defects certified | does not hold | **does not hold** | the null side is now measured twice more (D-134's 5.2% at n=58, this window's 42.9% at n=68 independent) and neither is the gate; the recall side gained its first forward-pair number, 0 of 1 value-class at n=11 |
| 5 | one prospective shadow run with no false publication | does not hold | **does not hold** | E-04 stratum v2 ran 100 units and is **not prospective** by its own preregistration; its 2 surviving shadow findings were adjudicated **false** (2026-09-05) |
| 6 | the L-01 exit list is done | holds | **holds, and its gate does not** | the documents, drills and pilot are done; `G-RELEASE-001` requires the component gates, so 3, 4 and 5 block the exit rather than the list |
| 7 | **every author-visible line obeys the output contract** (new, D-142) | — | **holds for both author-visible levels** | red and green publish through the format adjudicator as of this window; gate and yellow have markers and no author-visible path |

**Four of seven hold. The tag is blocked on 3, 4 and 5, in that order of difficulty.**

## 2. The gap list, ordered — list only

1. **`G-SEC-002`: 9 of 13 fixture classes, and an external observer.** Dispatched today:
   secret, raw-network, filesystem, result-spoof — all four read from *inside* the sandbox.
   Missing: `/proc`, home/git, DNS/IPv6, native syscall, fork/thread bomb, exec,
   daemonisation, resource exhaustion, namespace. The gate also requires a **sandbox-external
   supervisor or kernel observation** proving OS denial, which does not exist in any form, and
   an isolated canary CI environment with no real secret. *No model spend; runner time,
   a fixture suite, and an observer design.* **This is the largest single gap.**
2. **Condition 4's control side has no gate-grade bound.** `G-NULL-001` asks ≤1% at 95%, which
   is n ≥ 300 reviews and about $65 at the measured unit price — more than the $34 left under
   the $90 cap. What exists: 5.2% at n = 58 (not independent of the rule) and 42.9% at n = 68
   (independent, but only 7 controls put the rule in a position to answer). **An owner decision
   on which claim `v0.1` makes, or a cap raise, comes before any further spending here.**
3. **Condition 4's recall side has no held-out number under the current policy.** The 5-of-29
   held-out figure predates intent v3/v4/v4.1, D-124 and D-138; the only number taken under the
   current rule is 0-of-1 value-class on 11 forward pairs. `G-RECALL-002` needs the held-out
   slice re-run, ~$10-15 at the measured price.
4. **Condition 5 needs a genuinely prospective window.** A prospective shadow run cannot be
   assembled from history; it needs units that did not exist when the protocol was frozen.
   Calendar time plus ~$10-20 for 100 units, and the protocol is already written.
5. **No `gates` workflow run on a GitHub runner at this tip.** The suite passes locally; the
   last runner-green record is from an older commit. *Free; one workflow dispatch.*
6. **A receipt-backed comment has never reached an outside repository.** Condition 1 is met by a
   DEFER comment. Nothing in §1 requires more, but a `v0.1` whose only external artifact is an
   abstention is a weak first impression. *One paid review on a pair known to certify.*
7. **Release mechanics that do not exist yet.** `pyproject.toml` still says `version = "0.0.1"`;
   there is no `CHANGELOG`; `action.yml` pins no default ref for the tag; the quickstart names
   `@v0.1.0-pilot.1` and every mention would move. *Free, mechanical, one commit.*
8. **Two levels are built and unshipped.** Gate is in shadow with **0 executed observations**
   (D-137) and a measured 10.7% ceiling; yellow (a) is measured offline (D-143) and not wired
   into the publication path. Neither blocks the tag under §1 — condition 2 is about the levels
   that *do* speak — but a tag that ships two silent levels should say so in its notes.

## 3. What is explicitly not on this list

Corpus extension, the registry witness (`G-NEWCODE-001` §7, whose design recommends keeping the
exclusion), the learned scheduler, the TypeScript executor, and any whole-repository scan. All
are off the mainline until after L-01 and none of them is a `v0.1` blocker.
