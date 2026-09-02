# Privacy and retention (L-01 draft — for the owner's approval before any pilot)

## What leaves the repository

- The model provider receives: the diff of the pull request, bounded read-only excerpts of
  the repository (definitions, callers, tests, signatures, the nearest test module's helpers)
  and, for reproduction, the anchored code on both sides. Under the `package-cache` strategy
  (not the default) it receives the anchored package and its tests directory.
- GitHub receives the status comment and inline comments: only verified findings (claim,
  location, the generated test, run summaries, logs bounded to 6,000 characters, bundle
  path) and the collapsed run status (counts and failure categories, never an unverified
  candidate's claim, file or line).
- Nothing else is sent anywhere. There is no telemetry.

## What stays local

Under `.attest/` in the reviewed repository (gitignored): the ledger, candidates, attempt
cache (model responses, bounded), reproduction work directories, evidence bundles and the
controller key. These contain repository source excerpts and model outputs; treat the
directory as source-equivalent.

## Retention (proposed defaults)

- evidence bundles of published findings: kept indefinitely (they are the certificate);
- reproduction work directories: removed after the run (worktrees) or safe to delete;
- attempt cache: safe to delete at any time; a deleted cache means a repeated run buys new
  samples;
- ledger: append-only; rotation is the operator's choice;
- controller key: rotate by deleting `.attest/controller.key`; earlier bundles then verify
  structurally but their seals report a different key id.

## Secrets

Model and GitHub credentials are read by the privileged controller only. Head code runs in a
container with `env -i` and exactly the request environment; the controller key is outside
every mount. `attest` never logs, commits or echoes credentials; ledger text is redacted for
known credential names.
