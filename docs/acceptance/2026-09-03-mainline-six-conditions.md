# Mainline §1, condition by condition: is the product complete?

Owner instruction 9 of 2026-09-03f. Six conditions, each answered **holds / does not hold**
with the evidence that decides it. Nothing here is a plan; it is a reading of what exists at
this commit.

**Answer: four of the six do not hold. L-01 is not complete and no `v0.1.0-pilot.2` was
tagged.**

| # | condition | verdict |
|---|---|---|
| 1 | an outside repository installs from a stable ref, adds the Action, and receives PR comments | **does not hold** |
| 2 | every author-visible finding carries a differential receipt an offline verifier accepts | **holds** |
| 3 | head code cannot read secrets, reach the network, or forge a result | **does not hold** (four fixture classes pass; the preregistered list is longer) |
| 4 | on a held-out corpus: silent on every control, a stated share of eligible defects certified | **does not hold** |
| 5 | one prospective shadow run with no false publication | **does not hold** |
| 6 | the roadmap's L-01 exit list is done | **holds** |

---

## 1. An outside Python repository can install from a stable ref, add the Action, and receive PR comments — **does not hold**

What exists: the quickstart has been executed **verbatim from a fresh clone at
`v0.1.0-pilot.1`** against an outside repository (`IcantFind-a-username/us-stock-helper`) on
nine commits across three sessions, and every run ended in a receipt-backed output or a
documented silence with no third outcome
([pilot](2026-09-03-l01-private-pilot.md), [receipt pilot](2026-09-03-l01-receipt-pilot.md),
[this window](2026-09-03-d114-selfcontained-reproductions.md)). The Action itself has run on
a GitHub-hosted runner and posted a real comment (D-108,
[report](2026-09-03-first-runner-review.md)).

What is missing, and it is the whole second half of the sentence: **no outside repository has
ever had the Action installed, and no outside repository has ever received a comment.** Every
outside-repository run has been a local `attest review` with no GitHub write; the only
repository whose pull requests the Action has commented on is Attest's own.

## 2. Every author-visible finding carries a differential receipt an offline verifier accepts — **holds**

Structurally: C-02 deleted the S/T direct-surface path, so CI and GitHub presentation consume
`CertifiedFinding` only, and publication is `select_for_publication` over accepted receipts
(`G-CERT-001`). Empirically, this window: three receipts, each `head FAIL 3/3, base PASS 3/3`,
each accepted by `attest verify`, one of them with `--require-seal` in place.

The verifier's teeth are now drilled rather than asserted: the verifier-failure drill shows it
**rejects** a bundle with no manifest, one whose run records were removed, one whose recorded
run outcomes were rewritten, and one whose test was swapped for a passing one, and refuses a
copy outright when the seal is required and the controller key is absent
([drills](2026-09-03-release-drills-all-nine.md)).

One caveat, stated rather than rounded off: the **local** CLI prints an "unverified
candidates" drawer that carries no receipt. It is labelled as not being a finding, and the
Action never shows it. That is a deliberate local-only affordance, not a receipt-free
publication.

## 3. Head code cannot read secrets, reach the network, or forge a result — **does not hold**

What holds, on the exact production backend (`linux-container-v1`) on a GitHub runner:
the [red-team matrix](2026-09-03-redteam-matrix.md) dispatched four attack fixtures for real
and every one was marked and none certified — head code reading the controller's environment,
head code opening a socket, head code writing outside its work directory, and an executor
returning a result bound to another request's nonce. A positive control certified in the same
backend in the same run, so the refusals are not the refusals of a machine where nothing
works.

Why that is not the condition: `G-SEC-002` preregisters a longer fixture list — `/proc`,
home/git, DNS and IPv6, native syscall, fork and thread bombs, exec, daemonisation, resource
exhaustion and namespace fixtures — and requires a **sandbox-external supervisor or kernel
observation** proving OS denial or forced termination, not the in-process markers this matrix
reads. Four classes of nine-plus, observed from inside, is real evidence and is not the gate.

## 4. Silent on every control, a stated non-trivial share of eligible defects certified — **does not hold**

What exists: **0 false publications on 39 synthetic controls** and **certified on 5 of the 10
held-out defects whose environment built (5 of all 29)**, one pass, K=4, containers
([held-out report](2026-09-03-e02-heldout.md)); the supplementary run after the bootstrap fix
certified findings on 10 of the 19 environments that had failed.

Why that is not the condition: the controls are **synthetic** (test-only and docs-only commits
built from the same instances), and `G-NULL-001` asks for at least 600 adjudicated null
candidates across at least 30 repositories. The natural-null study that exists is **20 commits
in one repository** and produced one publication, since reclassified to the drawer by D-102
([E-01](2026-09-03-e01-natural-null.md), [replay](2026-09-03-d102-intent-replay.md)). No
share has been stated for a natural population, because none has been measured.

## 5. One prospective shadow run with no false publication — **does not hold**

E-04 stratum v1 ran: **2 prospective units, 22 candidates, 0 eligible, 0 reproductions, 0
shadow findings** ([report](2026-09-03-e04-prospective-v1.md)). Zero false publications out of
zero publications is a mechanism check, not a population estimate, and D-103's own
preregistration sets the minimum at 100 adjudicated shadow findings and 100 drawn silent
units. `G-SHADOW-001` is open on n, not on wiring.

## 6. The roadmap's L-01 exit list is done — **holds**

| item | where |
|---|---|
| stable install ref | `docs/operations/install-ref.md`, tag `v0.1.0-pilot.1` |
| quickstart | `docs/operations/quickstart.md`, executed verbatim on an outside repository |
| base-owned policy docs | `docs/operations/base-policy.md` |
| executor support matrix | `docs/operations/support-matrix.md` |
| privacy and retention | `docs/operations/privacy-and-retention.md`, approved (D-107) |
| failure-mode copy | `docs/operations/failure-modes.md` |
| kill switch | drilled, with a negative control |
| rollback | drilled, with a negative control |
| private pilot on one outside repository | `us-stock-helper`, nine commits |

All nine `G-RELEASE-001` operational drills are implemented and pass — 56 checks, each with a
negative control ([record](2026-09-03-release-drills-all-nine.md)). This is the one condition
that changed from "not done" to "done" in this window.

---

## What this means

L-01 stays open. The two conditions that are only a matter of *doing the thing* are 1 (install
the Action on an outside repository and let it comment) and 3 (finish `G-SEC-002`'s fixture
list with an external observer). Conditions 4 and 5 are population problems: they need runs on
a scale nobody has authorised yet, which is what
[the real-traffic plan](../corpus/real-traffic-plan.md) is for — and even that plan is far
below `G-NULL-001`'s 600 candidates and 30 repositories.

No tag was cut. `v0.1.0-pilot.1` remains the install ref.
