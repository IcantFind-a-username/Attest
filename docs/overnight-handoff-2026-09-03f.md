# Handoff — 2026-09-03, sixth window (`ff242ae` → `bf1f679`, plus this line): the generation wall came down, and the family policy held

Status: **the three reproductions that had ever really failed now all certify.** Two of them
publish. The third is the first receipt this product has produced on a real third-party
repository — and it published nothing, because nine eligible candidates put the C-05 family
threshold at 90. All nine `G-RELEASE-001` drills pass; four `G-SEC-002` fixture classes are
marked on the production backend on a GitHub runner. **Four of mainline §1's six conditions
still do not hold, so L-01 stays open and nothing was tagged.**

## 1. The three paid runs (proposals `claude-sonnet-5`, reproduction `claude-opus-5`, all at `--budget 0.60` — **not** the $0.25 default)

| case | pair | backend | cand. | elig. | **certified** | **published** | receipt | spend |
|---|---|---|---|---|---|---|---|---|
| Attest PR #8 | `445c5a1` → `e0867eb` | host adapter | 1 | 1 | **1** | **1** | `088cb98040f5` | $0.033891 |
| `pytest-dev__pytest-10051` | SWE-bench | `linux-container-v1` | 1 | 1 | **1** | **1** | accepted | $0.051904 |
| **`us-stock-helper` receipt pilot** | **`d7be758` → `8ed7811`** | `linux-container-v1` | 12 | 9 | **1** | **0** | `c229fb6992bb`, seal verified | $0.437427 |

Plus $0.019138 on a first PR #8 attempt killed at 10 minutes while `docker build` waited on a
`python:3.13-slim` pull this host cannot complete. **Window $0.542360 of $1.10 reserved;
cumulative $21.371668 of $30.** [Full report](acceptance/2026-09-03-d114-selfcontained-reproductions.md).

The pilot pair is the D-116 construction (head = the repairing commit's parent, base = the
repairing commit), qualified free of charge before the run: 4 of the fix's 5 own tests fail on
head, all 5 pass on base. Nothing published because the family threshold is `9/0.1 = 90` and
the receipt's e-value is below it — the multiplicity policy doing its job. **The certified
claim is an assertion about a disclosed `method_version` string, not the behavioural
regression**, which is close to what V-02 exists to exclude; the two candidates that named the
real regression produced tests that fail on base as well.

## 2. Mainline §1, condition by condition ([full reading](acceptance/2026-09-03-mainline-six-conditions.md))

| # | condition | verdict | why |
|---|---|---|---|
| 1 | outside repo installs, adds the Action, receives comments | **no** | nine outside-repository runs, all local `attest review`; **no outside repository has ever received a comment** |
| 2 | every author-visible finding carries a verifiable receipt | **yes** | receipt-only path since C-02; three receipts this window; the verifier now *drilled* to reject four kinds of wrong bundle |
| 3 | head code cannot read secrets, reach the network, or forge a result | **no** | 4 fixture classes pass on the production backend; `G-SEC-002` names nine-plus and demands an external observer |
| 4 | silent on every control, a stated share of defects certified | **no** | 39 controls are synthetic; the one natural null is 20 commits in 1 repo against `G-NULL-001`'s 600 across 30 |
| 5 | one prospective shadow with no false publication | **no** | E-04 v1 saw 2 units, 0 eligible; the preregistered minimum is 100/100 |
| 6 | the L-01 exit list is done | **yes** | every document, and all nine drills with negative controls |

**No `v0.1.0-pilot.2`.** `v0.1.0-pilot.1` remains the install ref (D-119).

## 3. The drills and the red-team matrix

Nine drills, **56 checks, all passing**, each with a negative control, one commit per drill
([record](acceptance/2026-09-03-release-drills-all-nine.md)). The revoked-credential drill
found a real defect: a provider outage message echoing the credential it rejected reached the
author-visible notes unredacted. Fixed.

`G-SEC-002` matrix on `ubuntu-latest`, docker 28.0.4, `workflow_dispatch`
[run 33741238403](https://github.com/IcantFind-a-username/Attest/actions/runs/33741238403),
conclusion success ([report](acceptance/2026-09-03-redteam-matrix.md)):

| fixture | outcome | marked, not certified |
|---|---|---|
| positive control: a real regression | `reproduced` | certified, as it must be |
| read the controller's environment secret | `not_reproduced` | yes (the canary is *absent*, which is weaker than "denied") |
| open a network connection | `deferred` | yes |
| write outside the work directory | `deferred` | yes, nothing on disk |
| forge a result (another request's nonce) | `rejected` | yes, mismatch named |

## 4. What this window did not do, and why

- **No tag.** Four conditions fail; the tag was conditional on them.
- **`G-SEC-002` is not green** — four classes of nine-plus, observed from inside the boundary.
  An external supervisor and the remaining fixtures are a separate piece of work.
- **The `collect-only` gate runs inside the container, not before it.** The instruction asked
  for it outside; collecting imports the reviewed revision, and a host-side collect would run
  head code outside the sandbox. The half that matters holds: a file that does not collect
  never reaches a behavioural run, and the test-module rejection executes nothing at all
  (D-114 records the deviation).
- **The real-traffic plan was not run.** It is §5 decision C and it is the owner's to approve.
- **Drills 3–5 landed in one commit and were split retroactively** before the push, so the
  history has one commit per drill as asked.
- **The default $0.25 budget was not measured.** All three runs used $0.60. At the default,
  two generation attempts at the generation model's price reserve about $0.18, so a review
  that spends much on discovery may not afford one — the pilot run exhausted $0.60 with six
  reproductions unattempted.

## 5. For the owner — three questions, defaults in brackets

1. **Approve the real-traffic corpus?** 20 defect pairs and 50 controls across three
   repositories ([plan](corpus/real-traffic-plan.md)). **Central estimate $8.40, $10.90 with a
   margin, against $8.628332 of headroom** — so it needs the cap raised from $30 to about $35
   (option A), or a cut to 12 defects and 30 controls at about $5.00 (option C). Option B,
   running at the $0.25 default for ~$4.50, measures the budget rather than the product. [A]
2. **Install the Action on `us-stock-helper` and let one pull request receive a comment?**
   It is the only thing standing between the evidence and mainline §1 condition 1, and it is a
   write to a repository the owner owns. [yes]
3. **Is a `method_version` assertion a receipt you want published?** The one real-traffic
   receipt certifies "head discloses v1 where base discloses v2" — true, differential,
   inside the diff, and about a version string. Tightening V-02 to reject it would also reject
   some real behaviour changes. [no — leave it, and report the class]
