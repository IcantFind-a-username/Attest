# GitHub Action

> **Current prototype operational guide; non-normative.** The Action is experimental and is
> not an approved untrusted-code security boundary. Its same-repository path can execute head
> code in a runner that also receives credentials, and current language-level network/process
> guards are best-effort. The target controller/executor split and release gates are defined
> in [`architecture/target-algorithm.md`](architecture/target-algorithm.md) and
> [`acceptance/evolution-gates.md`](acceptance/evolution-gates.md). Do not infer production
> readiness from the historical Phase-3 planted-fixture smoke. Target behavior and release
> authority come only from the linked architecture/gates, not this usage guide.

Use the composite action from a `pull_request` workflow. The included
[`examples/pull-request.yml`](../examples/pull-request.yml) is a complete starting
point: it grants only read access to contents and pull-request write access, cancels
superseded runs for the same PR, and retains `.attest/ledger.jsonl` as evidence.

```yaml
- uses: IcantFind-a-username/Attest@v0.1.0-rc.1   # docs/operations/install-ref.md
  with:
    github-token: ${{ secrets.GITHUB_TOKEN }}
    model-api-key: ${{ secrets.ANTHROPIC_API_KEY }}
    budget-usd: "1.00"
    samples: "5"
    verification-timeout: "600"
```

The action installs attest from the action checkout into a temporary virtual environment
built with `python -m venv` and `pip`, pinned by `requirements-toolchain.lock`; it does
not install a published package. *(Corrected 2026-09-09: this said `uv`, which the action
does not use.)* `budget-usd`, `samples`, and
`verification-timeout` shown above are the defaults.

**Typical cost per review.** `budget-usd` is a hard cap, not a price. Measured over the
2026-09-03 real-traffic corpus (43 reviews), a review's mean spend was **$0.22**: about **$0.31**
on a pull request with real code changes, $0.12 on a test-only change and $0.06 on a
documentation-only one. The three largest changes ever measured spent **$0.91 on average, at
most $1.03**, with the cap set to $1.20. The default was raised from $0.25 to **$1.00** on
2026-09-04 (D-126) after two independent measurements showed reviews stopping at the budget
before they could generate a reproduction. Full table and sources:
[`operations/quickstart.md`](operations/quickstart.md).

Reproduction tests use the action interpreter by default. If the reviewed project
needs dependencies from its own prepared environment, set `ATTEST_PROJECT_PYTHON`
at the job level to that environment's absolute Python path (for example,
`${{ github.workspace }}/.venv/bin/python`) and ensure it includes pytest. The
executor still applies its process, network, time, memory, and output controls.

## Safety model

### Fork pull requests are not reviewed, and leave nothing behind

**A fork pull request is never reviewed and never receives a comment.** Two independent
gates enforce it, and this repository uses **no `pull_request_target` trigger anywhere** —
the trigger that would hand a fork's head code a privileged context:

1. the **workflow's own guard** —
   `if: github.event.pull_request.head.repo.full_name == github.repository` — so the job
   never starts, and no runner step with the secret in its environment is ever entered;
2. the action's **credential-free gate step** (`scripts/action-gate.sh`), which compares the
   head and destination repository names *before* any credential is introduced, writes
   `trusted=false`, and makes every later step conditional on it. `scripts/action-entrypoint.sh`
   refuses the same event again, in case the action is used without the workflow guard.

**What a skipped fork leaves behind is nothing that could read as "reviewed, no problems":**
no pull-request comment, no review, no check annotation, no ledger, no artifact. What it does
leave is one Actions **notice** in the run log —
`::notice title=attest::Fork pull request skipped before credentials or head-code execution` —
which names the skip. A reader who sees a green check on a fork pull request is seeing a job
that did not run, and there is no attest output on the pull request to suggest otherwise.

This keeps the trusted token and model key out of the fork path; the skip is intentional and
records no finding.

For the same-repository path, review and generated reproduction tests run against the
checked-out head. That code can mutate its ephemeral runner, so this current prototype is
safe to enable only for owner-controlled branches whose code is already trusted. A
same-repository contributor branch is still untrusted and must not be treated as protected
by this runner; production support requires the secretless OS boundary in the target
architecture.

The Python evidence executor blocks Python socket connections on a best-effort basis.
This is not global network isolation: hosted runners have no general network-off
switch, and non-Python processes or other mechanisms may still reach the network.

Generated-test errors, collection failures, and timeouts defer the candidate. They do
not count as a refutation and buy no verification evidence.

Fork support requires a later two-workflow design: an unprivileged job may inspect the
fork, while a separate `workflow_run` workflow handles privileged credentials and any
trusted follow-up. Do not add fork secrets or execute fork head code in this action.
