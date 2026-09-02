# E-04 prospective shadow, stratum v1 (mainline §2 step 15): the owner's repositories after the freeze

Date: 2026-09-03. Protocol `attest.e04-prospective.v1`, frozen `2026-09-02T21:43:17+00:00`
(digest `af8aff9c1c8047b36dc639b8f9c9b3472c5a5e47c318f16a204ecf7f00b4b73e`; files under
[`benchmarks/studies/e04-prospective-v1/`](../../benchmarks/studies/e04-prospective-v1/)).
Population: every non-merge commit pushed after the freeze to the four repositories the
authorization names (Attest, us-stock-helper, Corum, IcantFind-a-username — all under the
owner's account, mainline §3). Collector: the local review path from the primary checkout at
`5fc03fa`, K = 4, $0.25 per unit, `r01`, proposal bound 3,200, containers when a reproduction
runs. Evidence level: **prospective shadow observation, n = 2 units, one repository** — the
first stratum, not `G-SHADOW-001`'s n (500 PRs, 30 repositories); every number below is a
count on those two commits. Status: **`INSUFFICIENT`** for every utility claim by design;
**0 shadow findings, 0 wrong**.

## Traffic

Between the freeze and the run, three of the four repositories had no push. Attest had two
commits — this window's own work — and both were recorded before either was reviewed
(`sample.jsonl`; silent-audit probability 1.0, so both are drawn for adjudication):

| unit | stratum | files | change units planned | units proposed on | candidates | eligible | reproductions | would publish | spend | latency |
|---|---|---|---|---|---|---|---|---|---|---|
| `19920c6` D-102 discriminator | feature | 23 | 13 | **1** (the documentation unit; the $0.25 per-unit budget was spent by its K = 4 samples) | 10, all anchored in `.md` files → `non_python` | 0 | 0 | none | $0.0816 | 20.7 s |
| `5fc03fa` E-04 collector | feature | 8 | 3 | 1 (`scripts/…/prospective_shadow.py` + the study files) | 12, all `new_code` (the anchored file is new) | 0 | 0 | none | $0.0878 | 26.2 s |

Report (`report.json`): units 2/2 run, shadow findings 0, PR-any-shadow-finding rate 0/2,
wrong 0, behavior changes verified 0, intent unknown 0, deferred 0, cost $0.1694 total
(p50 $0.0816), latency p50 20.7 s / p95 26.2 s; eligible detection `INSUFFICIENT` (2 silent
units drawn, 0 resolved; 0 confirmed opportunities of the 100 preregistered); semantic
precision has nothing to adjudicate.

## What the two units show

- **Safety:** nothing would have reached an author; the D-102 discriminator had nothing to
  decide because no reproduction ran.
- **Budget-bound silence, again.** On a 23-file commit the planner made 13 change units and
  the $0.25 per-unit budget funded the K = 4 proposal samples of the first unit only — the
  documentation unit, by path order — so 12 units (every Python change of the commit) were
  never read. The same mechanism cut 25 of 40 verified candidates on E-01 (natural-null
  report). The silence on `19920c6` is therefore not evidence about the product's judgement
  of the Python change; it is evidence that a $0.25 per-PR budget reads one change unit of a
  large commit. The per-PR budget and the unit order are a policy question for the owner
  (§5 C): a higher per-unit budget for E-04's next stratum, or a planner order that reads
  source units before documentation.
- **Reflexivity.** Stratum v1's traffic is Attest's own commits, written by the agent that
  built the discriminator. That is the only prospective traffic the authorization covers in
  this window; it is recorded, not hidden, and the stratum makes no claim beyond its counts.

## Traffic recorded after the run

Four more Attest commits arrived in the same window after the two units ran (`50c21d2`,
`69921e0`, `506aae1`, `7c8de5c`: docs, a fix, docs, a fix). They are recorded in `sample.jsonl`
(units sampled 6, units run 2) and not run: the owner's answer on the per-unit budget and unit
order (question 1) decides the next stratum's rule, and the protocol forbids changing it inside
stratum v1. Recording traffic after earlier outcomes is allowed by the preflight; an outcome
recorded before its own unit's selection is not.

## Adjudication

Both units are drawn for the silent audit (probability 1.0) and remain `unresolved`: the
product-blind reviewer the protocol requires cannot be the agent that wrote the commits.
`adjudication.jsonl` is empty; the report says `INSUFFICIENT` and will until a reviewer
labels them.

## Spend

$0.169422 of the $2.00 reservation (DEVSPEND.md); $1.830578 released.

## Caveats

- n = 2, one repository, the agent's own commits; a mechanism run of the collector on real
  prospective traffic, not a population estimate.
- Both units' recorded `executor_profile` is the development default because no
  reproduction ran; the container would have been selected at the first eligible candidate.
- The next stratum needs new traffic and the owner's answer on the per-unit budget; the
  protocol forbids changing K, budget or order inside stratum v1.

## Owner answers, 2026-09-03 (second window) — what stratum v2 will be

**Question 1 — budget-bound units.** Answered: **order source units before documentation
units and keep the $0.25 per-unit budget.** Implemented in the planner (`_unit_order`: a
`.py` path ranks before any other, alphabetical within each rank), so the budget reaches code
before prose on a large commit. Only a Python file can carry an anchored, reproducible
finding, so no eligible candidate is traded away by the reordering. A budget-bound run now
says so in the run status and in the silence receipt: `read N of M units, budget-limited`,
with the omitted units and the call that would have exceeded the budget. Stratum v1's numbers
stand as recorded — this is a **product-code change, so the next units run under a new
stratum (v2)**, per D-103's reversal clause; nothing inside v1 is re-run or excluded.

**Question 3 — adjudication.** Answered: **accept `INSUFFICIENT`.** The two v1 units and every
future drawn silent unit stay `unresolved` until a product-blind reviewer labels them; the
report keeps saying `INSUFFICIENT` for precision and eligible detection, and this does not
block the mainline. The agent that wrote the commits is not an admissible reviewer and does
not become one by being the only one available.

