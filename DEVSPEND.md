# Development spend ledger

Hard cap: $30 API spend for all development including dogfood (handoff guardrail 4);
raised from $10 by the owner on 2026-09-02.

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
| 2026-09-02 | C-05 verification re-run: 8 regression PRs + 8 controls, K=4 with verification, no retries; 4 certified on 4 defects, 0 control publications | $1.170900 |
| 2026-09-02 | D-078 step c: dev-slice re-run, 8 regression PRs + 8 controls, K=4 with verification, no retries; 5 certified, 0 control publications | $1.107200 |
| 2026-09-02 | D-078 step a: three regeneration passes over the 6 eligible-uncertified candidates (6 + 3 + 3 generations with differential execution; two passes interpreter-blocked), 5/6 faithful on the final pass | $0.397800 |
| 2026-09-02 | E-02 pilot: 25 product tasks over 8 dev-slice regression PRs + 8 controls (retries on interpreter/tree problems included), K=4 with verification; 2 certified, 0 control publications (ledger-recorded; mid-verification generation of stopped tasks not recorded) | $1.860100 |
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
| 2026-09-02 | us-stock-helper trial A (revert 375ab52, market_brief sample wording): review K=4 $0.0746 (1 candidate, drawer); local differential drives with default model 2x $0.0848 (generator hit max_tokens with a thinking-only response both times); 1 diagnostic generator call $0.0424; 4 haiku-4-5 generator drives $0.0390 (all unfaithful) | $0.325598 |
| 2026-09-02 | us-stock-helper trial B (revert 3f6b67b, nasdaq halt timestamps): review K=4 $0.1208 (2 candidates, drawer); local differential drive with default model $0.1621 (same thinking-only generator failure, 2 candidates x 2 attempts); 2 haiku-4-5 generator drives $0.0369 (all unfaithful) | $0.319734 |
| 2026-09-03 | paid check (a): us-stock-helper trial A (5 runs across fixes: $0.0757 + $0.0249 + $0.0246 + $0.0276 + $0.0284) and trial B ($0.2261), `attest review --k 4` with the local differential stage; B published one receipt-backed finding, A stayed silent (unfaithful test) | $0.407300 |
| 2026-09-03 | paid check (b): dev-slice re-run after fixes 1-5, 8 regressions ($0.7127) + 8 controls ($0.1384), K=4, code `c2814b8`; 6 certified on 5/8 defects, 5 published, 0 control publications, 0 no-text samples | $0.851100 |
| 2026-09-03 | owner instruction 3 RED: psf__requests-1766 with prompt caching, K=4; samples 1-3 read 3,901 cached tokens each, review $0.0248 (was $0.0439), 1 verified and published | $0.045458 |
| 2026-09-03 | owner instruction 4: dev-slice comparison, arm r01 8 PRs $0.4862 (4 certified) and arm package-cache 8 PRs $1.7537 (2 certified), K=4, code `2931753` | $2.239900 |
| 2026-09-03 | X-02 container smoke, psf__requests-1766 through linux-container-v1 (three attempts: bootstrap DEFER $0, nproc-race DEFER $0.0202, certified and published $0.0037) | $0.023912 |

**Total API spend: $15.554352 of $30.00.** (44 entries; every phase-3 acceptance workflow run is auto-logged individually by scripts/acceptance/phase3.py.)

## Reservations (pre-charged against the cap; settled into the table above on completion)

| date | item | reserved | settled |
|---|---|---|---|
| 2026-09-02 | C-05 verification: dev-slice re-run 8 regressions + 8 controls, K=4, full product path with the family policy and the 3,200 proposal bound | $2.50 | $1.170900 (row below); $1.329100 released |
| 2026-09-02 | D-078 step a: regenerate reproductions for the 6 eligible-uncertified dev-slice candidates with generator context, differential execution only, no publication | $0.50 | $0.397800 (row below); $0.102200 released |
| 2026-09-02 | D-078 step c: re-run the dev slice 8 regressions + 8 controls, K=4, full product path | $2.50 | $1.107200 (row below); $1.392800 released |
| 2026-09-02 | E-02 pilot (mainline §2 step 7): up to 8 dev-slice regression PRs + 8 controls (test-only and docs-only from the same repositories), full product path K=4 with verification; sample sized to the remaining cap; raised from $2.20 after environment retries consumed the first tranche | $3.00 | $1.860100 (row below); $1.139900 released |
| 2026-09-02 | R-01 discovery trial: 5 SWE-bench Verified dev-slice regression PRs × 3 arms (diff-only, no-context repeat, planner context), K=4, discovery only, no verification | $1.00 | $0.872200 (3 rows below); $0.127800 released |
| 2026-09-03 | paid check (a): us-stock-helper trial A/B re-run after owner fixes 1-5 (revert 375ab52 and 3f6b67b source changes as head, fixed main as base; `attest review --k 4` with the local differential stage) | $1.00 | $0.407300 (row below); $0.592700 released |
| 2026-09-03 | paid check (b): dev-slice re-run 8 regressions + 8 controls, K=4, full product path, table with no-text and true-abstention columns | $1.20 | $0.851100 (row below); $0.348900 released |
| 2026-09-03 | owner instruction 3 RED: one dev-slice regression PR (psf__requests-1766) re-run with prompt caching and first-token-staggered fan-out, K=4, to observe cache_read_input_tokens > 0 on the second sample and lower spend than the same case in paid check (b) ($0.0619) | $0.10 | $0.045458 (row below); $0.054542 released |
| 2026-09-03 | owner instruction 4: R-01 cache-variant comparison on the dev slice, existing R-01 context vs the package-plus-tests shared block, 8 regressions each arm, K=4 | $2.50 | $2.239900 (row below); $0.260100 released |
| 2026-09-03 | X-02 container smoke: one certified dev-slice regression (psf__requests-1766) through the linux-container-v1 backend, K=4; must match the C-05 re-run report | $0.10 | $0.023912 (row below); $0.076088 released |
| 2026-09-03 | E-02 held-out (mainline §2 step 13): held-out slice of the committed split, feasible repositories, ≤ 40 defects and ≤ 40 controls (29 + 40 planned), K=4, one run each through linux-container-v1; samples not inspected before the run | $6.00 | pending |
| 2026-09-03 | E-01 natural null (mainline §2 step 14): 20 real us-stock-helper commits with no known defect, full flow, expected zero publications; sized to the window and cumulative caps | $1.90 | pending |

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
