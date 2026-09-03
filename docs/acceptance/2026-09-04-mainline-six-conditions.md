# Mainline §1, condition by condition — the second reading, and no tag

Owner instruction 6 of 2026-09-04b, re-checking [the 2026-09-03 reading](2026-09-03-mainline-six-conditions.md)
against what this window built and measured. Each condition is answered **holds / does not
hold** with the evidence that decides it, and the answer to "do we tag `v0.1.0-pilot.2`?"
follows mechanically: **all six must hold, and three do not.**

**Answer: three of six hold. `v0.1.0-pilot.2` was not tagged.**

| # | condition | 2026-09-03 | **now** |
|---|---|---|---|
| 1 | an outside repository installs from a stable ref, adds the Action, and receives PR comments | does not hold | **holds** |
| 2 | every author-visible finding carries a differential receipt an offline verifier accepts | holds | **holds** — and it did **not** hold when that was last claimed |
| 3 | head code cannot read secrets, reach the network, or forge a result | does not hold | **does not hold** (unchanged) |
| 4 | on a held-out corpus: silent on every control, a stated share of eligible defects certified | does not hold | **does not hold** |
| 5 | one prospective shadow run with no false publication | does not hold | **does not hold** |
| 6 | the roadmap's L-01 exit list is done | holds | **holds** |

---

## 1. An outside repository installs from a stable ref, adds the Action, and receives PR comments — **holds**

The `us-stock-helper` run of 2026-09-04
([report](2026-09-04-us-stock-helper-action-comment.md)): the Action installed at the immutable
tag `@v0.1.0-pilot.1`, a GitHub-hosted runner reached the model, built the production container
image, ran a reproduction inside it, and **posted an author-visible comment on a repository this
project does not develop in** — [PR #4](https://github.com/IcantFind-a-username/us-stock-helper/pull/4),
run [33749092145](https://github.com/IcantFind-a-username/us-stock-helper/actions/runs/33749092145),
$0.044403. That is the whole sentence, end to end, for the first time.

What the condition does **not** say, and so is not counted against it: the comment was a
`DEFER`, and the drill's planted regression was not caught. The condition is about the delivery
path; recall is conditions 4 and 5.

## 2. Every author-visible finding carries a receipt an offline verifier accepts — **holds, and the previous "holds" was wrong**

This is the condition this window was ordered to repair, and the repair is real, but the
honest form of the answer has two halves.

**It did not hold when the 2026-09-03 reading said it did.** Four evidence bundles on this host
carry a `test_repro.py` that is not the test the runs executed, and **one of them was
published** ([D-124](../../DECISIONS.md), [re-verification](2026-09-04-bundle-reverification.md)).
The kernel and the verifier were both correct throughout — the verifier rejects those bundles
the moment anyone asks it. Nobody asked. The previous reading checked the structure and three
hand-picked receipts, and a structural argument plus a spot check is not the condition.

**It holds now, and by construction rather than by argument.** Certification runs the shipped
offline verifier on its own bundle — digests, run records, bindings, intent and the controller
seal — before anything is author-visible, and a bundle that does not pass buys a DEFER instead
of a finding. The root cause (the D-114 collection loop replaced the test but the caller kept
the first one) is fixed at the source as well, so the two guards are belt and braces.

**Standing caveat, unchanged:** the *local* CLI prints an "unverified candidates" drawer that
carries no receipt. It is labelled as not a finding and the Action never shows it.

**Second standing caveat, now measured:** 38 further bundles on this host fail today's verifier
for **schema drift** — they predate V-03's `fresh_state`, X-01's executor identity, or the
current receipt body. That is `INV-VERSION-001`, the accepted trade, but it means the product's
headline claim decays every time the receipt schema moves, and 42 of 86 bundles on this host are
already past that line.

## 3. Head code cannot read secrets, reach the network, or forge a result — **does not hold**

Unchanged from 2026-09-03 and untouched by this window. `G-SEC-002` preregisters secret,
`/proc`, home/git, filesystem, raw-network, DNS/IPv6, native-syscall, fork/thread-bomb, exec,
daemon, resource and namespace fixtures **and a sandbox-external supervisor or kernel
observation** proving OS denial. What exists is four fixture classes observed from inside the
sandbox ([red-team matrix](2026-09-03-redteam-matrix.md)). Real evidence; not the gate.

## 4. Silent on every control, a stated share of eligible defects certified — **does not hold**

The condition names `G-RECALL-002` and `G-NULL-001`, and neither passes.

- **`G-NULL-001` is unpassed and was not attempted.** It needs at least 600 adjudicated null
  candidates across at least 30 repositories, and ≥300 reviews for its ≤1% bound whatever they
  cost. This window ran `G-NULL-001a` instead — a different, weaker gate whose claim must carry
  its own n and bound ([report](2026-09-04-g-null-001a.md)). Passing it is never a pass of
  `G-NULL-001`, and the gate file says so in those words.
- **`G-RECALL-002` needs point detection ≥70% with a 95% lower bound ≥50%** on the hidden
  semantic corpus. The measured figure is 5 of 29 held-out defects in one pass, with a
  supplementary 10 of 19 after the bootstrap fix ([held-out](2026-09-03-e02-heldout.md)).
- The control half is the strongest part and still not the condition: **0 false publications on
  39 synthetic controls**, and 0 on 24 real-traffic controls — but the real-traffic controls are
  not known to be defect-free (two of them carried real defects, D-122), and the synthetic ones
  are built from the same instances as the defects.

## 5. One prospective shadow run with no false publication — **does not hold**

E-04 has two strata and neither is a prospective run at scale.

- **Stratum v1 is prospective and tiny:** 2 units, 22 candidates, 0 eligible, 0 shadow findings
  ([report](2026-09-03-e04-prospective-v1.md)). Zero false publications out of zero
  publications is a mechanism check.
- **Stratum v2 is 100 units, is not prospective, and is not adjudicated.** All 100 units ran,
  none deferred, $11.089240: 495 candidates, 129 eligible, **21 accepted receipts and 7 shadow
  findings on 3 units** ([report](2026-09-04-e04-stratum-v2.md)). Its units already existed when
  its protocol was frozen; the preregistration, every sample row and the report all carry
  `prospective: false`. It buys volume on real recent changes the product had never seen — which
  is what the owner asked for and what v1's n = 2 could not give — and it does not buy the word
  "prospective".

  It also cannot yet say the run had **no false publication**, which is what the condition asks.
  All seven findings are `unresolved`: `G-SHADOW-001` requires a product-blind audit on evidence
  independent of the product, and the agent that produced them is neither blind nor independent.
  `safety_stop_reached: false` means "none has been adjudicated wrong", not "none is wrong".

`G-SHADOW-001` additionally asks for ≥500 PRs across ≥30 repositories and ≥100 adjudicated
shadow findings. Both strata together are 102 units across 4 repositories.

## 6. The roadmap's L-01 exit list is done — **holds**

Unchanged, and re-checked against this window's documentation changes: install ref, quickstart,
base-owned policy docs, executor support matrix, privacy and retention, failure-mode copy, kill
switch, rollback, and the private pilot on one outside repository are all in place, with all
nine `G-RELEASE-001` drills passing ([record](2026-09-03-release-drills-all-nine.md)). D-126
moved the default budget in `quickstart.md`, `base-policy.md` and `github-action.md` together,
and each now carries the measured cost per review rather than only the cap.

---

## The tag

**No `v0.1.0-pilot.2`.** Six conditions must hold; three do. The install ref remains
`v0.1.0-pilot.1`.

What separates the three that fail from a tag, stated so the next window does not have to
re-derive it:

| condition | what is missing | is it a matter of doing, or of scale? |
|---|---|---|
| 3 | the rest of `G-SEC-002`'s fixture list and an external observer proving OS denial | **doing** — engineering, no model spend |
| 4 | `G-NULL-001`'s 600 candidates / 30 repositories, and `G-RECALL-002`'s ≥70% detection | **scale**, and a recall problem the budget raise does not solve |
| 5 | a genuinely prospective run at `G-SHADOW-001`'s n | **scale, and calendar time** — prospective means waiting for traffic that does not exist yet |

Condition 5 is the one no amount of money buys in a night: a prospective stratum needs commits
that have not been written. The honest path is to freeze a stratum now and let it fill.
