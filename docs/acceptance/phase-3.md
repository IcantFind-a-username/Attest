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

All three sticky comments met the 60-second job-start limit, and the downloaded ledger artifacts accounted for review, verification, and comment events on every arm. Latencies are whole seconds because the GitHub API reports timestamps at second granularity.

## Independently reproduced

This body was written by `render_report` for the second passing run. An earlier
passing run against
[attest-phase3-20260829-182623-6ffc59](https://github.com/IcantFind-a-username/attest-phase3-20260829-182623-6ffc59)
(runs 33268274146 / 33268276734 / 33268280907, $0.0616) reached the same verdict
independently, so the acceptance has passed twice on separate scratch
repositories. The second run was started by a stray background invocation while
writing this report rather than deliberately; both are logged in DEVSPEND.md,
and both scratch repositories are retained because the available GitHub token
has no `delete_repo` scope, which is an owner decision to widen.

Comments the bot actually posted on the first passing run, read back from the
GitHub API rather than from the script:

- PR #1: `Review complete. Verified findings: sample/stats.py:6 - Removing the
  empty-list guard causes average([]) to raise ZeroDivisionError instead of
  returning 0.0 ... (wealth 60.0). Spend $0.0230; 13.0s.` - one inline review
  comment.
- PR #2: `Review complete. No findings cleared the evidence bar. Spend $0.0115;
  6.1s.` - zero inline review comments.
- PR #3: `DEFER: verification deferred: new-code candidate: reproduction fails
  on head and the symbol is absent on base; not priced` - zero inline review
  comments.

PR #3's wording is the first live confirmation that the widened head-side rule
works: before it, the identical situation was published to the developer as
`unfaithful generated test`.

## What the first attempt found
