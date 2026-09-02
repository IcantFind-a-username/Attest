# Failure-mode copy (L-01)

What the author sees, in the order they are likely to meet it. Every line below is the
literal text or its stable prefix; the statistical vocabulary never appears.

| situation | what is shown | what to do |
|---|---|---|
| review finished, something verified | `Verified findings (each backed by a reproduction receipt):` then per finding the claim, `Finding ID`, `Verified: the generated test failed on head in 3/3 runs and passed on the merge base in 3/3 runs.`, the test, the command, the logs, the bundle path | run the command yourself; `attest verify --bundle … --require-seal` |
| review finished, nothing verified | `No finding was verified by a reproduction; abstained.` plus a collapsed `Run status` | read the status: candidates, eligible, attempts, and each failure category |
| fork pull request | `fork pull requests are skipped before model or head-code execution` | expected; open the pull request from a branch of the repository |
| model credential missing or revoked | the Action exits before any head code runs: `trusted pull requests require both action credentials` | fix the secret; nothing was executed |
| budget exhausted | `DEFER: budget: …` | raise `budget-usd` on the Action or wait for the next push |
| merge-base unavailable | `merge-base unavailable: fetch the base branch history (fetch-depth 0)` | set `fetch-depth: 0` in the checkout step |
| isolation backend unavailable (CI) | `isolation backend unavailable: …` in every reproduction's status line | the runner has no Docker; production never falls back |
| environment bootstrap failed | `environment bootstrap failed (python 3.x, roots […]): …` | the project's manifests do not install on a slim image; see the build log tail in the status |
| the generated test was unfaithful | `unfaithful test` in the run status | nothing to do: the product declined to speak |
| no text returned by the model | `no text returned` | a provider-side failure the product records honestly; rerun later |
| head code tried to reach the network, spawn, thread, or write outside its directory | `reproduction attempted …` | the reproduction is refused and marked; the product stays silent on that candidate |
| head moved before publication | `workspace HEAD drifted from the reviewed head before publication` | push again; the review is bound to one head |
| repository disabled | `disabled by the base policy (.attest.toml enabled = false)` | intended; see the kill switch |
