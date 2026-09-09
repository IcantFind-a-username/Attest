# E-04 shadow, stratum v3 — the unit is a pull request, and the rule is the one that just changed

Study ID: `attest.e04-prospective.v3`. Gate: `G-SHADOW-001`, third stratum. Ordered by the owner
as phase 2 of the 2026-09-13 instruction: *"count the recent reviewable pull requests of your own
live repositories … run a prospective shadow review, write no remote comment, zero false
publications is the only pass, one line of result per pull request."*

## 1. What is new here, and it is two things

**The unit is a pull request.** Strata v1 and v2 reviewed a *commit* against its parent. This
stratum reviews `head = refs/pull/N/head` against `base = merge-base(head, the base branch)` —
which is the pair the shipped Action actually reviews, and which for a multi-commit pull request
is a strictly larger diff than any of its commits.

**The publication rule is D-199's.** The `m_u/α` score bar was removed on 2026-09-13, hours
before this stratum ran. A replay said the change publishes +25 and withdraws 0 over history,
with the control side at +0 under the intent policy in force — but a replay is history, and its
control denominator is four receipts. **This is the first population of any size that the new
rule has faced, and that is what the money buys.**

## 2. What this stratum is, and what it is not

**It is not prospective, with exactly one exception, and the exception is labelled.** Every
pull request in the population existed before this protocol was frozen — except
`IcantFind-a-username/Attest#19`, which is the pull request of the task that froze it. That
single unit is genuinely prospective and is **reported apart**, never averaged in. `G-SHADOW-001`
asks for a prospective run; **this stratum supplies one unit of one, and volume on 30-odd real
pull requests the product had never seen.** No claim from it may say otherwise.

**Nothing is published.** The local review path only; no GitHub client is constructed, so no
comment, review or status can be written to any repository. The one exception is again
`Attest#19`, whose review the repository's own workflow runs on the runner in the ordinary way —
that one *can* write, it did, and what it wrote is in the report verbatim.

**It is not a precision measurement and it is not a recall measurement.** It is a
false-publication count over a population with no known planted defects, plus the four levels'
output on each unit. The audit that `G-SHADOW-001` demands — two-expert product-blind
adjudication of at least 100 findings and 200 sampled silences — is not performed and is not
affordable; §5 says which of the gate's pass conditions this stratum can and cannot reach.

## 3. Selection, fixed before the first run

1. **Population**: the six repositories in `authorization.json` — every repository under the
   owner's account that is Python-primary *and* has at least one pull request. A repository with
   no pull request cannot contribute a unit; a repository whose primary language the product does
   not support would contribute only abstentions, and `Sovereign-Founder-OS` (Rust, 64 pull
   requests) is excluded for that reason and named here so the exclusion is visible.
2. **Unit**: every pull request in those repositories, any state, newest first by creation time
   **within** a repository, **round-robin across** repositories in name order. A cost cap
   therefore removes units evenly instead of removing whole repositories off the end of the
   alphabet.
3. **The drill exclusion, declared before any unit ran.** A pull request whose title contains
   `THROWAWAY`, `DO NOT MERGE` or `Throwaway` is one of this project's own drills and carries a
   deliberately planted defect. Such a unit is **recorded with its reason and excluded from the
   false-publication denominator**, because a publication on a planted defect is a true positive
   by construction and counting it as a false publication would flatter the product in the other
   direction. Nothing else is excluded, and **no unit is excluded after its outcome is known**.
4. **Nothing is re-sampled and nothing is retried.** A unit that cannot run records its DEFER or
   refusal reason and stays in the table.

## 4. Configuration

`per_pr_budget_usd = 1.00`, `k_samples = 5` (the shipped factory value, D-183),
`executor_profile = linux-container-v1`, context strategy r01. **Cost cap $6.00**, held by the
driver as a hard cumulative cap that reserves each unit's `$1.00` maximum before starting it, so
the cap refuses a unit by name rather than discovering the overrun afterwards. The owner's stop
rule: **stop immediately at $6.00.**

## 5. What a pass means, and what it cannot mean

**The owner's condition for this phase: zero false publications.** A false publication is an
author-visible finding on a unit that carries no defect of the kind the finding claims, on any
unit outside the drill exclusion.

`G-SHADOW-001`'s own design asks for 500 pull requests across 30 repositories, at least 100
adjudicated shadow findings, at least 200 adjudicated silent units, a design-weighted detection
estimator, and semantic precision with a 90% lower bound. **This stratum reaches none of those
numbers and cannot**: the owner's entire account holds fewer than 40 pull requests across six
supported repositories. The gate's verdict is recorded against its own design, and the owner's
condition is recorded separately against this population. Reporting one as the other would be
the exact failure `INV-CLAIM-001` exists to prevent.
