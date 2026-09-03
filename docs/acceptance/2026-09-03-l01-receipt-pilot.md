# L-01 receipt pilot: three later-repaired `us-stock-helper` commits

Owner decision 2 of 2026-09-03: pick three commits a later `fix:` commit
repaired, review each with `head` = the buggy commit and `base` = its parent,
and try to produce the receipt-backed comment the six-silence pilot never did.
Budget $0.30.

**Result: no receipt. Two commits reviewed, the third stopped unrun on budget.
$0.2472 recorded plus $0.05 charged conservatively for an interrupted run.**

## How the commits were chosen

For every `fix:` commit in the repository, the lines it removes were blamed at
its parent to find the commit that introduced them, keeping only pairs whose
introducing commit **modified a pre-existing Python file** — a regression the
differential kernel can certify, rather than new code it must refuse (D-102).

| # | reviewed commit (the defect) | repaired later by | what the fix says was wrong |
|---|---|---|---|
| 1 | `d7be758` *keep resolved pattern episodes immutable under replay* | `2d4a0d8` | the served MA5 invalidation text quotes a level frozen at the touch bar while the detector compares against each later bar's own MA5 |
| 2 | `e17c686` *add patterns-shapes-v1 detection engine* (modifies the pre-existing `scoring.py`) | `8ed7811` | patterns that are not in force still voted in the score |
| 3 | `20c7260` *budget SHORT-horizon freshness against the bar interval* | `1906530` | a weekly bar shared the 5-day daily staleness budget, so it was stale-gated through the back half of every week |

## What happened

| commit | units | candidates | eligible | reproductions | certified | published | spend | wall |
|---|---|---|---|---|---|---|---|---|
| `d7be758` | **read 2 of 4, budget-limited** | 12 | 11 | 11 | 0 | 0 | $0.1741 | 56.5 s |
| `e17c686` | all | 1 | 1 | 1 | 0 | 0 | $0.0731 | 22.1 s |
| `20c7260` | — | — | — | — | — | — | ~$0.05 (unsettled) | stopped at ~15 s |

Both completed reviews ran through `linux-container-v1`; no image was built —
`us-stock-helper`'s manifest set is stable across these commits, so all three
trees address the same image, which was already on the host.

### Why nothing certified

Two distinct causes, and only one of them is about the tool's judgement.

**Unfaithful generated tests (3 of 11 executed reproductions).** Every
reproduction that actually ran reported `pytest passed on head in 3/3 runs;
base not executed`: the generated test does not fail on the buggy commit, so it
discriminates nothing and the differential never reaches the base side. This is
the kernel refusing to buy evidence it does not have, and it is correct.

**The per-review budget (9 of 11).** On `d7be758` the remaining nine
reproductions never generated a test at all — each stopped at
`BudgetExceeded: … projected total $0.263 exceeds budget $0.25` on its
*second* generation attempt. The proposal stage had already spent most of the
$0.25: 12 candidates from a 210-line change to a 938-line module, of which 11
were eligible. **The budget was exhausted by breadth, not by difficulty.**

The unit ordering fixed last window worked as intended: the two units the
budget could not reach were the two 1,832-line JSON contract fixtures, and the
Python source was read first. The silence names it — `read 2 of 4 units,
budget-limited` — and the drawer note lists both omitted units by path.

Half the proposal samples abstained outright (4 of 8 on `d7be758`, 7 of 8 on
`e17c686`, `output_tokens` 8–9), which is the model declining to invent a
finding and is the behaviour the null work asks for.

## Why the third commit was not run

$0.30 does not fund three reviews at the product's default $0.25 per-review
budget. After two reviews $0.0528 remained, which cannot buy a review — a third
would have been budget-bound before its first reproduction. The run was stopped
about 15 seconds in, with only a `review_plan` row settled; $0.05 is charged
against the cap for proposal samples that may have been in flight and billed
without a ledger row.

The two constraints in the owner's instruction — three commits, $0.30 — are not
jointly satisfiable at the default budget. That is the owner question below.

## What this pilot did and did not establish

Established: the differential kernel reaches **eligible, containerised
reproduction on real third-party regressions**, 12 of 13 candidates eligible
across the two commits, and refuses every one of them for a stated reason.
Nothing was published, and no silence was undocumented.

Not established: **a receipt.** The receipt-backed branch of the L-01 step-16
exit remains unexercised on real traffic, now across nine reviewed commits of
this repository (six in the 2026-09-03c pilot, two here, one stopped). Every
refusal so far has been either "no eligible candidate", "unfaithful test", or
"budget".

The recurring finding, now on a second population: **no generated reproduction
has ever been judged faithful on real traffic.** Six of six across four
populations, by three different reasons — three here (`pytest passed on head in
3/3 runs`), two elsewhere (`fails on base as well`, on the runner review and on
`pytest-10051`), one in the 2026-09-03c pilot (`references a symbol absent from
head`). n = 6 is small and these are not one failure mode; what they share is
the stage. That is the concentration to attack next, and it is a measurement
question — why does generation produce a test that does not discriminate the
two sides? — not a budget one.
