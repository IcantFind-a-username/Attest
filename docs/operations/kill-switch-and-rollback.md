# Kill switch and rollback (L-01)

## Kill switch

`.attest.toml` on the **base** branch of a pull request owns the review policy. Commit:

```toml
enabled = false
```

and every review of a pull request into that branch stops before any model call or any
head-code execution, posting `disabled by the base policy (.attest.toml enabled = false)` as
the final status. The head of a pull request cannot flip it: CI reads the policy at the
resolved merge-base and never the head checkout's file. The local `attest review` honours
the same key from the working tree's file.

Turning it back on is the same one-line commit with `enabled = true` (or deleting the key).
No secret, workflow or deploy changes.

## Rollback

The Action is pinned by ref in the consuming workflow (`uses: IcantFind-a-username/Attest@<ref>`).
Rolling back is changing that ref to the previous release ref and merging; nothing else is
stateful on the GitHub side. Evidence bundles, ledgers and receipts written by a later
version stay readable: bundle, run-record, receipt and seal schemas are versioned and the
verifier rejects rather than misreads an unknown version.

Rollback never lowers the trust bar: a prior ref that lacked the container backend or the
seal is not a valid rollback target for a production pilot; the release note names the
oldest ref that is.

## What a pilot operator checks after either action

- `attest stats` in the reviewed repository: the last run's `defer` row names the switch;
- the pull-request status comment shows the reason verbatim;
- no new evidence bundles or spend rows appear while disabled.
