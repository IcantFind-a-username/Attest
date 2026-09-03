# What the last three gates cost, at the price this window measured

**This is a §5 decision paper. Nothing here was run.** It prices `G-SEC-002`, `G-NULL-001`
and E-04's preregistered minimum against the unit price the real-traffic corpus actually
measured, and lays out three ways forward. The choice is the owner's.

## 1. The measured unit price

From 43 real reviews at K = 4, `--budget 0.60`, containers, proposals `claude-sonnet-5` and
reproduction generation `claude-opus-5` ([corpus report](2026-09-03-real-traffic-corpus.md)):

| shape | measured mean |
|---|---|
| any review in the corpus (43) | **$0.2177** |
| a control (24) | $0.1397 |
| a control that changes source Python (5 refactor) | $0.3427 |
| a defect pair (19) | $0.3136 |

Spend scales with the number of eligible candidates, which scales with the size of the
reviewed diff. Every figure below uses **$0.2177** as the central price and the
control/refactor pair ($0.1397 / $0.3427) as the low and high bounds.

**Cap headroom after this window: $13.53 of $45.**

## 2. `G-SEC-002` — nine-plus fixture classes and an external observer

**API cost: $0.00, at any sample size.** `scripts/release/redteam.py` makes no model call: each
attack fixture is dispatched into `linux-container-v1` directly, and the positive control is a
pre-written regression, not a generated one. Four classes cost $0 on the runner this window and
five more would cost $0 too.

What the gate actually asks for that money cannot buy:

| requirement | state | what it needs |
|---|---|---|
| secret, `/proc`, home/git, filesystem, raw network, DNS/IPv6, native syscall, fork/thread bomb, exec, daemon, resource, namespace, result-spoof fixtures | 4 of 13 dispatched | ~9 more fixtures, one commit each |
| **a sandbox-external supervisor or kernel observation proving OS denial** | **absent** — the matrix reads the guard's own in-process markers | an out-of-container observer (seccomp/audit/eBPF or a supervising process on the runner) and a way to bind its verdict into the record |
| isolated canary CI environment with no real secret | present (`workflow_dispatch`, `red-team.yml`) | — |

**This gate is engineering, not spend.** It is the only one of the three that the $45 cap does
not constrain at all.

## 3. `G-NULL-001` — 600 adjudicated null candidates, 30 repositories, ≥381 null PRs

| driver | number | at $0.1397 | **at $0.2177** | at $0.3427 |
|---|---|---|---|---|
| ≥381 independent adjudicated null PRs | 381 reviews | $53.23 | **$82.94** | $130.57 |
| ≥600 adjudicated null candidates | not binding — the corpus produced 2.9 eligible candidates per review, so 381 reviews yield ≈1,100 | — | — | — |
| ≥30 repositories | **not a money problem** | — | — | — |

Two things the price table cannot fix:

- **The 381 is a statistical floor, not a budget choice.** With zero errors, the 95% upper
  bound is ≈3/n, so a ≤1% bound needs **n ≥ 300 PRs** whatever they cost. Any amendment that
  cuts the population below ~300 also has to move the ≤1% bound, and then the gate is a
  different gate.
- **30 repositories do not exist.** This account has three Python repositories with enough
  history to draw from, and this window used all three. The repo-cluster analysis the gate
  requires cannot be run on three clusters. Reaching 30 means reviewing repositories the owner
  does not own, which mainline §3's authorization does not cover.
- **Adjudication is the hidden cost.** 600 candidates must be adjudicated *product-blind*.
  That is human or agent labour, not API spend, and this window showed why it matters: two of
  24 controls were not defect-free, and only reading the code revealed it.

## 4. E-04 — 100 prospective units and 100 adjudicated opportunities

| driver | number | at $0.1397 | **at $0.2177** | at $0.3427 |
|---|---|---|---|---|
| 100 prospective units | 100 reviews | $13.97 | **$21.77** | $34.27 |

- **$21.77 does not fit the $13.53 of headroom.** Sixty units do ($13.06); one hundred need the
  cap raised to about $55.
- **The real constraint is calendar, not money.** A unit is one non-merge commit pushed after
  the protocol freeze. E-04 v1 saw **2 units in a whole window**. At that rate 100 units is
  months of ordinary traffic; the only honest accelerants are more repositories under the
  authorization or a longer observation period.
- E-04 v1 also spent its whole $0.25 per-unit budget on one change unit of a 23-file commit.
  At $0.60 and D-117's plan order this is better, but the corpus just showed that at $0.60 the
  budget is still the **largest single reason** a candidate never certifies (39 of 75
  reproduction failures were `BudgetExceeded`). A per-unit budget below ~$0.60 measures the
  budget rather than the product.

## 5. Three options

| | what it is | API cost | what it buys | what it costs you |
|---|---|---|---|---|
| **A — run the gates as written** | 13 `G-SEC-002` fixtures + external supervisor; 381 null PRs across 30 repositories; 100 E-04 units | **≈$105** ($67–$165), cap raised from $45 to ~$150 | the gates as preregistered | `G-NULL-001` is **impossible as written**: 30 repositories do not exist under the authorization, so the money buys a gate that still cannot pass |
| **B — amend the gates to an affordable sample** | `G-NULL-001` → 300 PRs across the repositories that exist (the statistical floor for ≤1%); E-04 → 50 units | **≈$76** ($65 + $11), cap raised to ~$110 | a real ≤1% null bound; a halved E-04 | the repo-cluster analysis the gate demands is gone (3 clusters, not 30), and E-04's interval roughly doubles. Both are amendments to preregistered criteria and must be recorded as such before any run |
| **C — phase them (recommended)** | **Now:** `G-SEC-002` fixtures + supervisor ($0) and E-04 to the units traffic actually produces. **Later:** `G-NULL-001`, once a population exists | **≈$22** for E-04 at 100 units; $0 for `G-SEC-002`; cap raised from $45 to ~$55 | the two gates that are limited by work and calendar rather than by population, at a cost the current cap nearly covers | `G-NULL-001` stays open, and with it mainline §1 condition 4. Nothing is claimed that is not measured |

**C is the recommendation**, for one reason: `G-SEC-002` costs no API money at all and E-04 is
within a small cap raise, while `G-NULL-001` is blocked on a population that no amount of
spending creates. Buying A or B first spends the budget on the one gate whose binding
constraint is not the budget.

## 6. What would change these numbers

- A per-review budget below $0.60 lowers every figure roughly linearly and raises the
  `BudgetExceeded` share; a budget above it does the reverse. The corpus measured $0.60 only.
- A cheaper generation model changes the reproduction stage, which is where the money goes.
  D-115 chose `claude-opus-5` on n = 1 evidence; the corpus did not re-test that choice.
- Prompt caching already reads ~75% of proposal tokens from cache in these runs. There is not
  another factor of two there.
