# Development spend ledger

Hard cap: $10 API spend for all development including dogfood (handoff guardrail 4).

## API spend (counts against the $10 cap)

| date | item | cost |
|---|---|---|
| 2026-08-29 | pygments live review, K=5 failed on schema 400s (unbilled, reservations cancelled) | $0.00 |
| 2026-08-29 | pygments live review, K=5 (surfaced the RawTokenFormatter crash; 11.1s) | $0.0402 |
| 2026-08-29 | corum live review, K=5 (negative control; drawer candidate refuted via verify; 20.4s) | $0.1124 |
| 2026-08-30 | live key validation smoke test (15 in / 4 out, default model) | $0.0001 |
| 2026-08-30 | differential-V live validation: regression review K=5 (7.4s, 2 drawer candidates) | $0.0281 |
| 2026-08-30 | differential-V live validation: 2 differential verifications, both head FAIL 3/3 + base PASS 3/3 | $0.0091 |
| 2026-08-30 | negative control review K=5 on a semantics-preserving refactor (0 candidates, 3.8s) | $0.0119 |
| 2026-08-30 | adversarial fabricated-finding verification (not reproduced; wealth 2.95 -> 1.48) | $0.0018 |
| 2026-08-30 | new-code discriminator live check: review K=5 (7.2s, 1 drawer candidate) | $0.0259 |
| 2026-08-30 | new-code discriminator live check: differential run classified new_code_candidate | $0.0035 |
| 2026-08-30 | differential-V null-rate measurement, 12 clean-refactor trials (0 false confirmations) | $0.0446 |
| 2026-08-30 | differential-V null-rate measurement, 40 clean-refactor trials (0 false confirmations) | $0.1510 |
| 2026-08-30 | dogfood on a real third-party project: 617 added lines, 0 candidates, 20.4s | $0.2352 |
| 2026-08-30 | rename-refactor null trials targeting the certification defect (0 false confirmations) | $0.0434 |
| 2026-08-30 | differential-V null-rate measurement, 296 trials (0 false confirmations; interval clears the ceiling) | $1.1474 |
| 2026-08-30 | post-fix null trials, 45 runs including rename refactors (0 false confirmations) | $0.2335 |
| 2026-08-30 | post-fix recovery check: real regression in a root-conftest project now certifies | $0.0019 |
| 2026-08-30 | ten-repeat live stability measurement on one preregistered diff (10/10 stable decisions) | $0.2841 |
| 2026-08-30 | first live evaluation pilot on receipt-validated corpus pairs, 3 rounds / 10 case-runs (0 false positives, 0 surfaced, all safe defers) | $1.0592 |
| 2026-09-01 | wave 3 operational-only live observation, 2 historical V1-validated pairs / 4 cases (accuracy withheld) | $0.330626 |
| 2026-09-01 | wave 4 bounded-generation retest, same 2 historical V1-validated pairs / 4 cases (accuracy withheld) | $0.433304 |
| 2026-09-01 | wave 5 history counterfactual, 9 V1-historical pairs / 18 cases (accuracy withheld; F unpriced) | $1.576220 |
| 2026-09-02 | R-01 discovery trial, arm diff-only: 5 SWE-bench Verified dev regression PRs, K=4, 20 proposal samples (7 candidates) | $0.2575 |
| 2026-09-02 | R-01 discovery trial, arm no-context repeat (planner v1 retrieved nothing on body-only diffs): same 5 PRs, K=4 (7 candidates) | $0.2581 |
| 2026-09-02 | R-01 discovery trial, arm planner context: same 5 PRs, K=4 (6 candidates, garbage claim gone, 3/20 samples truncated) | $0.3566 |
| 2026-08-29 | phase-3 acceptance run 33267601438 (https://github.com/IcantFind-a-username/attest-phase3-20260829-181131-683ce1) | $0.0242 |
| 2026-08-29 | phase-3 acceptance run 33267602736 (https://github.com/IcantFind-a-username/attest-phase3-20260829-181131-683ce1) | $0.0115 |
| 2026-08-29 | phase-3 acceptance run 33268274146 (https://github.com/IcantFind-a-username/attest-phase3-20260829-182623-6ffc59) | $0.0230 |
| 2026-08-29 | phase-3 acceptance run 33268276734 (https://github.com/IcantFind-a-username/attest-phase3-20260829-182623-6ffc59) | $0.0115 |
| 2026-08-29 | phase-3 acceptance run 33268280907 (https://github.com/IcantFind-a-username/attest-phase3-20260829-182623-6ffc59) | $0.0271 |
| 2026-08-29 | phase-3 acceptance run 33268345406 (https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c) | $0.0220 |
| 2026-08-29 | phase-3 acceptance run 33268347262 (https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c) | $0.0132 |
| 2026-08-29 | phase-3 acceptance run 33268350447 (https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c) | $0.0272 |

**Total API spend: $6.805350 of $10.00.** (33 entries; every phase-3 acceptance workflow run is auto-logged individually by scripts/acceptance/phase3.py.)

## Reservations (pre-charged against the cap; settled into the table above on completion)

| date | item | reserved | settled |
|---|---|---|---|
| 2026-09-02 | E-02 pilot (mainline §2 step 7): up to 8 dev-slice regression PRs + 8 controls (test-only and docs-only from the same repositories), full product path K=4 with verification; sample sized to the remaining cap; raised from $2.20 after environment retries consumed the first tranche | $3.00 | pending |
| 2026-09-02 | R-01 discovery trial: 5 SWE-bench Verified dev-slice regression PRs × 3 arms (diff-only, no-context repeat, planner context), K=4, discovery only, no verification | $1.00 | $0.872200 (3 rows below); $0.127800 released |

## Session-subscription compute (does NOT count against the cap; recorded for transparency)

Dogfood proposer samples and verification workflows ran as harness subagents on
the operator's session (D-013). Itemized subagent tokens:

| item | tokens |
|---|---|
| Corum recon (calibration/dependence port survey) | 63,712 |
| Phase-0 verify workflow (9 agents) | 653,570 |
| Phase-1 verify workflow (21 agents) | 1,415,028 |
| Dogfood samples: pygments K=5 | 302,888 |
| Dogfood samples: corum-code K=5 | 426,471 |
| Dogfood samples: attest-self K=5 | 611,387 |

## What the dogfood reviews would have cost on the product path (estimates)

Per the in-repo ledgers (preflight-estimated, mock token counts for outputs):
pygments review ~$0.012; corum-code review ~$0.016; corum-docs review $0.000
(budget-deferred before any call); attest-self review ~$0.27 (run at
--budget 0.5). All within the $0.25 default per-PR budget except attest-self,
which used the budget knob explicitly.
