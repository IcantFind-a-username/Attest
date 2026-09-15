# Independent review: held-out runtime preflight

Reviewed commit `91214dd` against `6e03952`, exactly one read-only pass. Scope: the new driver and protocol, with inspection of their existing archive, package-stub, backend, image-builder, executor and container-adapter dependencies. No measurement was executed, restarted or modified. No paid calls or network runs.

## Findings

- **P2 — prohibited environment overrides remain live and unrecorded**, `scripts/corpus/product_runtime_preflight.py:128` (also the executor call at line 160). The protocol at lines 18–19 excludes constraints/interpreter overrides, but the driver inherits both `ATTEST_PIP_CONSTRAINT` and `ATTEST_PROJECT_PYTHON`. `ensure_image` calls `era_constraints()` when no explicit constraints are passed (`src/attest/execution/container_images.py:490`), which reads the environment-selected file and incorporates its contents into the image. `execute_repro` reads the interpreter override at line 1807 before execution. Thus this committed driver does not enforce its promised treatment; an inherited constraints variable changes the dependency resolution without a corresponding field in the diagnostic record. Reject nonempty overrides before preparation and record that prerequisite. This is confirmed by the call chain, not evidence that either variable was set in the active run; controller-side launch evidence can establish whether that run was affected.
- **P2 — archive preparation is not time-bounded**, `scripts/corpus/product_runtime_preflight.py:121`. The reused `runtime_contract_shadow.archive` invokes both `git archive` and `tar` without a timeout (helper lines 58–59), with the archive captured entirely in memory. Clone and fetch have timeouts, but a stuck export/extractor never reaches the refusal handler, so this supposedly bounded diagnostic can stop advancing permanently with only a started row and no remaining rows. Reuse the existing archive helper with an optional bounded timeout (preserving existing callers), or document and enforce a controller deadline with an explicit incomplete result. No stalled subprocess was induced during this read-only pass.

## Checks and limits

- Controller follow-up states launch-tool metadata confirms both override variables absent and existing rows report Python 3.12 primary selection. Therefore the first finding is a reusable-driver enforcement limitation, not observed invalidation of this run. The controller also reports no archive stall so far; the second finding concerns bounded failure handling, not an observed failed measurement. These statements were supplied by the controller, not independently re-executed by the reviewer.
- Actual product source diff is empty. The driver calls the unchanged production backend selector, rejects absent/non-container adapters, and passes the selected adapter into the existing collect-only executor with the declared limits.
- No oracle/gold-content lookup, outcome-based retry, pin insertion, paid call, certification call or publication path was found in the scoped driver. It reads the frozen candidate manifest and package/runtime source as declared.
- Container execution uses the existing explicit request environment and isolated mounts; the driver adds no credential mount or build secret. This inspection is not an independent security acceptance test of the pre-existing builder/backend.
- Success requires nonempty packages, exit zero, one collected stub and initialized network guard. Qualification/control/paid-review counters remain zero; successful import is not presented as defect qualification or recall.
- Image records include cache reuse and image identity. Script, protocol and population digests are recorded. The source Git tree identity describes committed source; no general dirty-source assertion is added by this driver.
- Docker setup happens before the initial durable result, so a setup failure needs controller-side recording. Final twenty-row artifacts and actual execution outcomes were not reviewed because the measurement was running.
- Validation was static diff and helper inspection only; no tests, subprocess fault injection or empirical measurement was run by the reviewer.

## Required completion metadata

`git diff 6e03952..91214dd --stat -- scripts/corpus/product_runtime_preflight.py benchmarks/studies/repository-holdout-v1/product-runtime-preflight.md`: **2 files changed, 229 insertions** (driver 185; protocol 44).

Reused inventory inspected: `sha256_bytes`, `write_canonical_json`, `archive`, `stub_packages`, `probe_stub_source`, `select_backend`, `execute_repro`; execution environment containment was followed through the existing adapter. No new tools added. Reviewer wrote only this report.
