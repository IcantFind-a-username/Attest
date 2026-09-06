# Base-owned review policy (L-01)

The review policy is owned by the **base branch** of the pull request, never by its head.
This is what makes the kill switch, the budget and the evidence threshold un-forgeable by a
contributor: CI resolves the merge-base, reads `.attest.toml` from that commit, and records
the source it used in the task and in every receipt. A head checkout's `.attest.toml` is
never consulted.

| where the review runs | which file decides |
|---|---|
| CI on a pull request | `.attest.toml` at the resolved merge-base of base and head |
| CI when the base commit has no `.attest.toml` | factory defaults below |
| local `attest review` | the working tree's `.attest.toml`, merged over the factory defaults |

An unknown key is ignored; an invalid value is an error before any model call or head-code
execution, not a silent fallback.

## Keys

| key | factory default | meaning |
|---|---|---|
| `enabled` | `true` | `false` stops every review of a pull request into this branch before any model call or head-code execution, with the status `disabled by the base policy (.attest.toml enabled = false)`. See [`kill-switch-and-rollback.md`](kill-switch-and-rollback.md). |
| `budget_usd` | `1.00` | hard model spend cap for one review. Reaching it is an explicit `DEFER: budget: …`, never a truncated answer. A cap, not a price: measured reviews average $0.22 and the largest measured spent $1.03 — see [`quickstart.md`](quickstart.md). Raised from `0.25` on 2026-09-04 (D-126). |
| `k_samples` | `5` | proposal samples per change unit. |
| `max_findings` | `3` | hard cap on author-visible findings in one pull request, across inline and summary. |
| `alpha` | `0.1` | the evidence threshold. **A factory statistical constant: changing it is an owner decision, not a repository setting.** A value that makes the gate unreachable refuses the run instead of relaxing it. |
| `auto_tighten_alpha` | `true` | tighten, never loosen, the threshold for multiplicity within one pull request. |
| `model` | `default_model` in the shipped pricing table | the model that proposes candidates. A model absent from the pricing table is an error, so spend is always priced. |
| `generation_model` | `generation_model` in the shipped pricing table | the model that writes the reproduction. Proposals rank; the reproduction is the evidence, so the two roles are set apart. |
| `tier0_commands` | `["ruff"]` | cheap pre-checks run before any paid generation. |
| `context_strategy` | `"r01"` | planner retrieval strategy. |
| `verification_cap_per_unit` | `3` | how many candidates of one **changed file** may buy a reproduction. Candidates are ranked by cluster size, then by a static credibility score computed from the head tree, then by finding id; the rest are recorded as `ranked below verification cap` in the ledger and under `--explain`. Raising it buys more reproductions inside one file and fewer across the change; it cannot make anything publish that would not have published, because the family denominator is unchanged (D-168). |
| `repro_concurrency` | `2` | how many candidates' reproductions may run at once. The three runs *inside* one candidate stay serial; `1` restores the strictly serial path, and the ledger's bytes are identical either way (D-157). |
| `daily_budget_usd` | `0.0` | a second ceiling, over a rolling 24 hours for the whole repository. `0.0` is off, which is the shipped default — a ceiling nobody chose is a silence nobody can explain (D-161). |

## What a repository setting can never do

- it cannot lower the certification bar: a finding still needs a receipt whose test fails on
  head and passes on the merge base, in isolation, repeated, and offline-verifiable;
- it cannot make head code trusted: isolation, the fork gate and the containment guards are
  not policy keys;
- it cannot publish an uncertified candidate: `max_findings` and `alpha` can only reduce what
  is published, never add to it;
- it cannot be set by the pull request being reviewed. Both model keys are protected in CI:
  the Action input or the factory default wins over anything the base file says, because the
  provider is built before the policy is read.

## Example

```toml
# .attest.toml on the base branch
enabled = true
budget_usd = 1.00
k_samples = 4
max_findings = 3
```

## Checking which policy a run used

`attest stats` and the run's ledger row name the policy source (`base:.attest.toml`, the
working tree's file, or the factory defaults) and the digest that went into the receipt. If
the source is not the one you expect, the merge-base did not resolve — see
`merge-base unavailable` in [`failure-modes.md`](failure-modes.md).
