# The first review this action ever ran on a GitHub-hosted runner

Owner decision 3 of 2026-09-03. Until `e0867eb` this repository had no
`.github/workflows/` at all: every gate in the project had only ever run on the
owner's machine, and the action it ships had never been executed by GitHub.
This is the record of the one run that changed that.

## What was run

| | |
|---|---|
| workflow | `.github/workflows/pull-request.yml`, event `pull_request`, `runs-on: ubuntu-latest` |
| action resolved as | `uses: ./` — the action as it stands in the pull request |
| pull request | [#8](https://github.com/IcantFind-a-username/Attest/pull/8), branch `throwaway/runner-check-2026-09-03`, head `445c5a1`, base `e0867eb` |
| run | [33715576314](https://github.com/IcantFind-a-username/Attest/actions/runs/33715576314) |
| inputs | `budget-usd: 0.25`, `samples: 4` |
| planted defect | `_normal_path` in `src/attest/benchmark/matcher.py` loses its backslash normalisation, so a truth defect recorded with a Windows-style path stops matching a prediction on the same file. `tests/benchmark/test_matcher.py` uses only forward slashes, so the repository's own suite stays green |

## Result

| | |
|---|---|
| conclusion | **success**; every step green, including the two `Post` cleanups |
| wall clock | **76 s** (job `04:35:04Z` → `04:36:20Z`); the status comment was posted at `04:35:38Z`, 34 s in |
| spend | **$0.0301** (`ci_final.spend_usd`; `review_run.spend_usd` $0.017778, model `claude-sonnet-5`) |
| backend | **`linux-container-v1`**, image `attest-repro:96b9871908772ebd`, built on the runner inside those 34 s |
| eligibility | 1 candidate, **eligible** — `definition _normal_path exists at the merge-base`, i.e. the discriminator saw pre-existing code, not new code |
| reproduction | attempted, 1 |
| outcome | **DEFER** — `unfaithful generated test: fails on base as well` |
| certified / published | 0 / 0 |
| comment | posted once and upserted (three `github_comment` rows, all `posted`) |

The comment, verbatim:

```
DEFER: verification deferred: unfaithful generated test: fails on base as well

Run status
- change units read: 1; candidates: 1; eligible: 1; reproductions attempted: 1; certified: 0; published: 0
- proposal prompt tokens: 5456; cache_read_input_tokens: 4086
- reproduction 1: unfaithful test — unfaithful generated test: fails on base as well
```

## What this proves, and what it does not

Proved, on GitHub's infrastructure rather than the owner's laptop: the workflow
triggers; the same-repository guard admits an owner branch; `actions/checkout`
at the head SHA satisfies the entrypoint's `HEAD` check; the toolchain lock
installs and `pip check` passes on a clean runner; the credentials reach only
the trusted step; **the container backend builds its image and runs the
reproduction on a runner**; the status comment is written with
`pull-requests: write` and the ledger uploads as an artifact. The whole path
costs about three cents and a minute and a quarter.

Not proved: **recall.** The planted regression was found, ranked and taken to
reproduction, and the generated test then failed on the base tree too, so it
bought nothing. A receipt-backed comment has still never been produced on a
runner. The fork path was not exercised either — no fork pull request was
opened, so the job-level guard and `scripts/action-gate.sh` were only exercised
in the affirmative.

## What the run found in the product

One defect, fixed in `d62bcd6`: the `certification` ledger row for a
not-attempted outcome reported `local_development_best_effort` while the runs
had executed under `linux-container-v1`. It buys nothing and overclaims
nothing, but it is the row an audit reads to learn where the code ran.

The pull request was closed without merging and the branch deleted; the
workflow file stays.
