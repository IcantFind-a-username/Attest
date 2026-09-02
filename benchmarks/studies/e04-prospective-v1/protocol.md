# E-04 prospective natural-PR shadow, protocol v1

Study ID: `attest.e04-prospective.v1`. Gate: `G-SHADOW-001` (the first stratum; the gate's
full n is not reachable in one window and no claim beyond the observed stratum is made).

## Hypothesis and estimand

On natural changes the product has never seen, made after this protocol is frozen, the
shadow product path publishes nothing wrong: the PR-any-wrong-shadow-finding rate on the
authorized population, with every shadow finding adjudicated product-blind, and the
behavior-change drawer rate (D-102) on feature commits.

## Population and units

Every non-merge commit pushed after `freeze_at` to a repository the authorization names
(clones under `.attest/corpora/<name>/`), reviewed as head = the commit, base = its parent.
Strata by subject prefix: `docs`, `refactor` (chore/style/test/build/ci/perf), `feature`,
`fix`, `other`. No unit is excluded after it is recorded; a unit whose review cannot run is
recorded with its DEFER reason.

## Procedure

1. `freeze` writes the digest over this file, `preregistration.json` and
   `authorization.json`; the preflight refuses any later edit.
2. `select` records each prospective unit with its stratum, the inclusion probability and
   the seeded silent-audit draw **before** any review runs.
3. `run` reviews each recorded unit through the local review path (no GitHub client; the
   same verification stage CI uses, so the would-publish set equals what CI would post),
   K = `k_samples`, per-PR budget `per_pr_budget_usd`, containers; it records counts, the
   would-publish candidate ids, behavior-change outcomes, DEFER reason, cost and latency.
   Never a candidate's claim, file or line in the study bundle.
4. Truth: every shadow finding and every unit drawn for the silent audit is adjudicated
   product-blind (label `defect` / `not_defect` / `unresolved`, reviewer id, evidence
   independent of the product) into `adjudication.jsonl`. Unknown truth stays
   `unresolved`; eligible detection is `INSUFFICIENT` until the preregistered minimum
   (100 confirmed opportunities, 100 adjudicated findings) is met.

## Stops

`safety_stop_wrong_findings` wrong shadow findings; any receipt or security bypass; the
cost cap. A stop ends the stratum; nothing is re-run or excluded.

## Permitted claim

"Prospective shadow observation on the authorized population, stratum v1." No utility,
precision or production-performance claim.
