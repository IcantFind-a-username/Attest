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

Every row names what changing it does **and the ledger field that shows the effect**, so a
change can be checked rather than believed. Fields are in `.attest/ledger.jsonl` unless the
cell says otherwise.

| key | factory default | meaning | what changing it does | where you see it |
|---|---|---|---|---|
| `enabled` | `true` | the kill switch. See [`kill-switch-and-rollback.md`](kill-switch-and-rollback.md) | `false` stops every review into this branch before any model call or head-code execution | no ledger rows at all; the pull request shows `disabled by the base policy (.attest.toml enabled = false)` |
| `budget_usd` | `1.00` | hard model spend cap for one review. A cap, not a price: measured reviews average $0.22, the largest measured $1.03 ([quickstart](quickstart.md)). Raised from `0.25` on 2026-09-04 (D-126) | lowering it below **$0.54 makes discovery impossible at `k_samples = 5`** — five samples reserve $0.16 of output alone against a 30% share, so the review defers before reading anything (measured 2026-09-09). Raising it buys **discovery**, and D-166 measured that four times the budget moved no verdict | `review_run.spend_usd`; `proposal_coverage.budget_limited`; a `DEFER: budget: …` naming the share |
| `k_samples` | `5` | proposal samples per change unit | more samples raise cluster sizes (and so the ranking) and multiply the discovery reservation linearly; `4` is what every corpus measurement in this repository was run at | `review_run.provider_samples` (one entry per sample); `proposal_coverage.units_read` |
| `max_findings` | `3` | hard cap on author-visible **red** findings in one pull request, across inline and summary. The effective cap is `min(3, max_findings)` | it truncates the **display**, not the search: a unit whose bar was cleared was still searched, which is why the pull-request bound is `min(1, U·alpha)` and not `hard_cap·alpha` (D-174) | `publication_policy.hard_cap`, `.published`, and a `beyond the hard author-visible cap` entry in `.suppressed` |
| `alpha` | `0.1` | the **per-unit family cap**: a certified finding publishes at priority score ≥ `m_u/alpha` for the `m_u` eligible candidates in its own changed file. **A factory constant; changing it is an owner decision, not a repository setting** (AGENTS §16). It is *not* a proven error rate — D-174 measured the score's minimum at 2.000, so it is not an e-value | a value that makes the gate unreachable refuses the run instead of relaxing it | `publication_policy.alpha`, `.unit_thresholds`, `.pr_error_bound`, `.e_value_validity` |
| `auto_tighten_alpha` | `true` | tighten, never loosen, the threshold, from the ledger's own precision labels | protected by D-048 together with `PRECISION_TARGET`, `PRECISION_WINDOW` and `ALPHA_FLOOR`; none is a repository setting | `alpha` kind rows in the ledger, with `label_count` |
| `model` | `claude-sonnet-5` (`default_model` in the shipped pricing table) | the model that proposes candidates. A model absent from the pricing table is an error, so spend is always priced | **protected in CI**: the Action input or the factory default wins over the base file, because the provider is built before the policy is read | `review_run.model` |
| `generation_model` | `claude-opus-5` | the model that writes the reproduction probe. Proposals rank; the reproduction is the evidence, so the roles are set apart (D-115) | also protected in CI. On the one comparable case, opus turned zero receipts into two; n = 1 | `review_run.generation_model` |
| `tier0_commands` | `["ruff"]` | cheap pre-checks run before any paid generation | signals near an anchor feed ranking only; they never publish | `identifier_check` rows |
| `context_strategy` | `"r01"` | planner retrieval strategy | `"package-cache"` additionally sends the anchored module's **whole package and its tests directory** (≤ 120,000 chars) to every proposal sample and to generation — a much larger slice of the repository. See [`privacy-and-retention.md`](privacy-and-retention.md) | `review_plan.units[].context_chars` and `.context`; the cache token counts in `review_run.provider_samples` |
| `verification_cap_per_unit` | `3` | how many candidates of one **changed file** may buy a reproduction. Candidates rank by cluster size, then a static credibility score, then finding id (D-168) | raising it buys more reproductions inside one file and fewer across the change. It **cannot** make anything publish that would not have: the family denominator `m_u` is every eligible candidate either way. The offline replay over 28 recorded reviews cut reproductions 168→79 and spend $10.27→$5.24 while keeping **all 3** receipts | a `ranked below verification cap` drawer class in the ledger and under `--explain`; `review_plan`/`verification` row counts |
| `repro_concurrency` | `2` | how many candidates' reproductions may run at once. The three runs *inside* one candidate stay serial — a concurrent repeat is a different experiment | `1` restores the strictly serial path. At `2` a lower-ranked candidate may hold the last of the budget when a higher-ranked one asks, which weakens D-111's best-first tail | the ledger's bytes are identical either way (D-157); `verification.elapsed_s` is what moves |
| `daily_budget_usd` | `0.0` | a second ceiling, over a rolling 24 hours for the whole repository | `0.0` is **off**, which is the shipped default — a ceiling nobody chose is a silence nobody can explain (D-161). Set it and an afternoon of pull requests cannot cost an unbounded amount | a `DEFER: budget: …` naming the daily cap; `review_run.spend_usd` summed over the window by `attest stats --since` |

## Constants that are not policy keys

These ship with the product and a repository cannot change them. They are listed because
they bound what the keys above can do.

| constant | value | what it bounds | where you see it |
|---|---|---|---|
| `PROPOSAL_SHARE` | `0.3` | discovery may reserve at most 30% of one review's budget, **including the first change unit** (D-168 removed D-111's exemption) | the `DEFER: budget: …` names the share and the budget |
| `PROPOSER_MAX_OUTPUT_TOKENS` | `3200` | the per-sample output bound the reservation is priced at. It overstates a real proposal by about **3×**, so the ceiling bites earlier than actual spend suggests | `review_run.provider_samples[].output_tokens` against the reservation in the DEFER |
| `MAX_UNIT_CHARS` | `30,000` | how much diff + context is packed into one proposal unit. A single file's block larger than this becomes its own unit and may exceed it | `review_plan.units[].diff_chars`, `.context_chars` |
| `MAX_GENERATION_CONTEXT_CHARS` | `20,000` | the retrieved context sent with a probe generation | truncated with `[context truncated]` |
| `MAX_CONTEXT_LINES` | `200` | the head-source window around an anchor sent with a probe | — |
| `verification-timeout` (Action input) | `600` s | the **shared** deadline for the whole differential stage, not per candidate | `verification.reason` = `shared verification deadline exceeded` |
| `IMAGE_BUILD_TIMEOUT_S` | `1800` s, further clamped to the remaining verification budget | the reproduction image build. The clamp exists so a long build cannot succeed and then leave every candidate deferring on a deadline it already spent | `image_cache.build_elapsed_s`; `executor_backend.reason` |
| red hard cap | `min(3, max_findings)` | author-visible red findings per pull request | `publication_policy.hard_cap` |
| green cap | **2** per pull request | author-visible green notes | `structural_note` rows; the comment section |
| yellow cap | **2** per pull request, **shared across every yellow class** | author-visible yellow notes | the yellow section of the comment |
| `probe_generation` | `true` | the reproduction's assertion is **recorded from the merge base**, not written by a model. `false` restores the D-114 path and is the reversal | `verification.mode`; the receipt's probe policy version |
| `gate_shadow` | `false` | the gate level. On, it asks the gate question of new-code candidates and writes to the ledger and `.attest/shadow/gate/` **and nothing else** — it reaches no author-visible surface either way | `gate_shadow` rows |

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
