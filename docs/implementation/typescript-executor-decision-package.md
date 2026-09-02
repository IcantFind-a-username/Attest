# Decision package — a TypeScript executor (vitest/jest differential reproduction)

Status: proposal only (owner instruction 2, item 11, 2026-09-03). Not implemented in this
window; the work-order number is the owner's to assign. Proposed placement: after L-01.

## What it would be

A second evidence executor that reproduces a claimed regression in a TypeScript or
JavaScript repository the same way the Python executor does today: one generated test file,
run against the head and the merge-base trees N times each, head must fail and base must
pass, every run recorded and content-addressed, and the receipt bound to the exact test
bytes, the selected test id and the executed changed lines.

## Minimal contract (the part that must hold for a receipt to mean the same thing)

| Python executor today | TypeScript executor |
|---|---|
| one module-level pytest function in `test_repro.py` | one `test()`/`it()` in `repro.test.ts` at the tree root |
| `pytest --collect-only` must find exactly one node | `vitest list` / `jest --listTests` + a dry run must find exactly one test id |
| JUnit XML per run, `failures > 0, errors == 0` on head, all pass on base | JUnit reporter per run (`vitest --reporter=junit`, `jest-junit`); the same failure/error split |
| guard: no network, no subprocess, no threads (language hooks) + OS boundary (X-02) | no language-level guard exists that is worth trusting; the OS boundary (X-02's container, `--network none`, read-only root) is the only guard; Node worker threads must be disabled (`--pool=forks --poolOptions.forks.singleFork`, `--runInBand`) |
| changed-line binding via `sys.settrace` inside the test protocol | V8 coverage (`NODE_V8_COVERAGE` or `c8`) restricted to the anchored file, taken per run; binding policy `changed-line-coverage.v1` unchanged |
| interpreter identity: path + version | Node version + package manager + lockfile digest |

## What is shared with X-01 (no new protocol)

The request/result protocol is language-neutral: content-addressed inputs (the test file,
the guard, a runner config), an argv template with the three mounts, an explicit
environment, bounded artifacts (`junit.xml`, `stdout.txt`, `stderr.txt`, `executed-lines`,
`import-origin`), the nonce and the request digest. A TypeScript adapter implements the same
`ExecutorAdapter` interface and produces the same `ExecutionResultEnvelope`; the controller,
the certification kernel, the bundle writer and the offline verifier do not change. What
changes per language is the *job*: how the test is written, how one test id is selected, how
coverage is taken, and the image (a Node image instead of a Python one).

## Owner decisions needed

1. Which runner is in scope first: vitest, jest, or both (recommendation: vitest first;
   jest via `jest-junit` second).
2. Whether TypeScript compilation errors on head count as a reproduction (recommendation:
   no — a type error is a build failure, DEFER as `environment`, never evidence).
3. Whether the corpus for its acceptance is the owner's own TypeScript repositories or a
   public one (there is no SWE-bench-Verified equivalent with hidden tests for TypeScript).

## Estimated effort

- adapter + job construction + coverage binding: 2-3 days;
- eligibility (which changed files are TypeScript, which runner the repository uses):
  1 day;
- a red-team pass on the Node guard-less model inside the container: 1 day;
- a 10-case pilot on owner repositories: 1 day plus model spend (~$1).

Total: about one week of agent work after L-01, no owner decision on statistics (the factory
alpha, LR and K are unchanged), one `§16` decision on the runner scope.
