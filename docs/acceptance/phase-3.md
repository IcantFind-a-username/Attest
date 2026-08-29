# Phase 3 acceptance

Acceptance passed against a retained private scratch repository.

- Repository: https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c
- Regression PR (existing guard deleted): https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c/pull/1
- Negative-control PR (semantics-preserving refactor): https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c/pull/2
- New-code PR (defective helper absent from base): https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c/pull/3
- Regression sticky latency (job start to comment): 9.000s
- Control sticky latency (job start to comment): 9.000s
- New-code sticky latency (job start to comment): 12.000s
- Development API spend: $0.0624

## Workflow runs

- Run 33268345406: https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c/actions/runs/33268345406 (runner queue 3.000s)
- Run 33268347262: https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c/actions/runs/33268347262 (runner queue 3.000s)
- Run 33268350447: https://github.com/IcantFind-a-username/attest-phase3-20260829-182756-f2446c/actions/runs/33268350447 (runner queue 2.000s)

## What each arm shows

- **Regression PR**: the reviewed diff deletes an empty-input guard from a function that already exists on base, so the generated reproduction fails on head and passes on base. That is the only pattern differential evidence certifies, and it produced a verified inline finding whose verification row records evidence class `regression_reproduced`.
- **Negative-control PR**: a semantics-preserving refactor produced zero finding comments.
- **New-code PR**: the reviewed diff adds a defective helper that exists nowhere on base. attest posted zero finding comments and recorded a verification row with evidence class `new_code_candidate`, left deferred. The defect is recognised and written down, not missed -- and deliberately not priced, because certifying a defect in newly added code needs a likelihood ratio that has not been introduced. Silence on new code is the designed behaviour and the honest limit of what this evidence can buy.

All three sticky comments met the 60-second job-start limit, and the downloaded ledger artifacts accounted for review, verification, and comment events on every arm.
