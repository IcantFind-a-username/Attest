# Frozen held-out product runtime preflight

E-02 prerequisite, D-267. Baseline `6e03952`; protocol and driver committed at
`91214dd` before execution. All 20 frozen held-out heads were attempted once, in order.
Actual model/API spend: **$0**. Product source, defaults and certification are unchanged.

| Repository | Import / collection success | Build refusal | Harness symlink refusal |
|---|---:|---:|---:|
| spaCy | 0 | 5 | 0 |
| Ansible | 0 | 0 | 5 |
| HTTPie | 5 | 0 | 0 |
| thefuck | 2 | 3 | 0 |
| Total | 7 | 8 | 5 |

Successful IDs: HTTPie 2, 1, 5, 4, 3; thefuck 20, 21. Each success ran the unchanged
product's collect-only executor in `linux-container-v1`, imported the discovered package,
collected one diagnostic node, exited zero and initialized its network guard. Two successful
rows reused images; five built images. Head source was exported separately for each case.

All eight build refusals stop at project installation under product-selected Python 3.12.
Retained log tails identify the Docker step, but do not establish the underlying dependency
or compiler cause. Ansible's five refusals happen before export because this diagnostic
rejects symlinks; they establish no product incompatibility. No case was replaced, retried
or omitted. The 300 s build budget does not establish what a longer budget would do.

## Evidence and validation

[Protocol](../../benchmarks/studies/repository-holdout-v1/product-runtime-preflight.md),
[all rows](../../benchmarks/studies/repository-holdout-v1/product-runtime-evidence/result.json),
and [manifest](../../benchmarks/studies/repository-holdout-v1/product-runtime-evidence/manifest.json)
bind population, script, protocol, source tree and successful image identities. Raw artifacts
remain under `.attest/corpora/repository-holdout-runtime/`; public path prefixes are redacted.
Package import does not prove every submodule or regression test can run. No oracle assertion,
paid discovery, receipt or publication was attempted.

The [single independent review](../../benchmarks/studies/repository-holdout-v1/product-runtime-evidence/independent-review.md)
found two reusable-driver limitations: inherited constraint/interpreter overrides are not
explicitly rejected, and the shared archive helper has no subprocess timeout. A separate
controller check of the tool-launch environment found both override variables absent;
all 20 rows completed without an archive stall. These are retained limitations, not observed
result invalidations. The reviewer inspected code during execution; the controller checked
final nonempty and complete artifacts afterward. Address the limitations before unattended
reuse. No running driver was edited and no outcomes were retried.

Script Ruff and `git diff --check` pass. Source and tests are unchanged from baseline.
Host: CPython 3.12.2, Ruff 0.16.5, Docker 27.5.1 / buildx 0.20.1 on arm64. Successful
execution records identify container CPython 3.12.14 and image digest. No full product gate
was rerun for this diagnostic-only task.

## Next prerequisite

This is **7 runtime successes out of 20 attempts**, not recall, precision, seven validated
defects or seven independent repositories. Qualified defects and controls remain zero.
Held-out heads have now been exposed to runtime qualification with product source frozen;
no rule development used their outcomes. Paired oracle validation, direction/class validity,
blind semantic labels, reasonable-change controls and a feasible paid protocol remain
prerequisites. Keep failed/unqualified rows visible in the final sampling flow; do not
silently treat only successful rows as the original population.

The long task continues toward its final paid evaluation report, after which it stops.
