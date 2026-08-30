# M-02 validation-receipt acceptance — 2026-08-30

Status: **BLOCKED BY EVIDENCE for M-02** — **PASS** `G-MEASURE-002` and
`G-CODE-002`; **FAIL** `G-CODE-001`.

This report records M-02 from baseline
`bcfd9d8624a03858ea5aa71fff84412e6efa6606` on branch
`feature/m02-validation-receipts`. The acceptance-record/implementation SHA is the local
commit containing this file. M-02 remains unchecked in the roadmap because one required
full-suite gate is not green; this report does not reinterpret that failure as a pass.

## Scope and provenance

- isolated worktree: `Attest-m02-validation-receipts`;
- baseline and merge base: `bcfd9d8624a03858ea5aa71fff84412e6efa6606`;
- Python: 3.12.2; interpreter SHA-256:
  `6d291d209a33ee4eb44514781fe42437b2cfd2ed5853e0804c1258da017c2f1f`;
- pytest 9.1.1, ruff 0.16.5, mypy 2.3.1;
- OS: Darwin 25.5.0 arm64;
- `pyproject.toml` SHA-256:
  `536e1090f0179026922f130c32365f6b1091995698594680e58c7adca5653927`;
- v2 protocol SHA-256:
  `dd775e605ce11ca9038954f83ea54ecc07b587bf5f84775b752772e5dcdfa0e9`;
- provider/model/prompt/pricing: N/A — no provider call or empirical study;
- API spend: $0.00; remote writes: none;
- lockfile change: none — M-03 owns toolchain locking;
- executor: local test process with explicit fixture-owned interpreter and isolation
  adapter; no production corpus validation receipt is claimed by this construction run.

The evidence population is constructed unit/adversarial fixtures, not sampled repositories
or PRs. Statistical population, strata, intervals, cluster count, stopping rule, and pricing
snapshot are therefore N/A. The guard-removal set contains 56 selected adversarial tests;
it is code-path evidence, not an algorithm-quality estimate.

## Gate matrix

| Gate / criterion | Result | Evidence |
|---|---|---|
| `G-MEASURE-002`: validated requires complete bounded evidence | PASS | exactly one attempt with ordered fixed 1..3 PASS then buggy 1..3 stable FAIL; missing/interleaved/retried evidence fails closed |
| included and excluded attempts remain auditable | PASS | execution and preflight exclusions retain typed attempts; all-excluded bundles receive authenticated empty allowlists but remain unscorable |
| all eight run artifact classes are content-addressed | PASS | stdout, JUnit, test, command, interpreter, environment, source, and executor records bind exact bytes, sizes, kinds, and digests |
| integrity / provenance / semantic-policy authority are separate | PASS | `ValidationVerification` reports independent checks; only verifier-minted, immutable capabilities can authorize report scoring |
| minimal manual status rows cannot authorize | PASS | `{pair_id,status}` and raw/hand-built v2 objects are rejected without complete offline-verified evidence |
| v1 compatibility is historical only | PASS | frozen v1 files are unchanged and load only as `historical_integrity_only` |
| exact fail-closed paths | PASS | unknown versions/fields, forged envelopes, missing artifacts, size violations, path escapes, symlinks, and digest/semantic mutations report field/artifact paths |
| `G-CODE-002` field/guard mutation proof | PASS | 56 selected adversarial tests pass, covering run/attempt/artifact fields, provenance, exclusions, capability mutation, bounds, and issuer/verifier symmetry |
| coverage >= 90% | PASS | 92.02% total coverage with the known date-literal test deselected |
| `G-CODE-001` full suite | FAIL | 870 of 871 collected tests pass; one M-03-owned date-literal assertion fails |

## RED observations and GREEN evidence

The pre-implementation/review RED phase produced real failures for:

- `test_validation_v2_rejects_validated_row_without_six_runs`;
- stdout and JUnit tampering under unchanged summaries;
- inconsistent runner/profile and interpreter references;
- missing and unauthorized provenance envelopes;
- exclusions without real attempts/runs;
- post-verification capability mutation;
- oversized evidence, large bounded JUnit, dependency-output truncation, redacted
  environment hashes, symlinked parents, and planted atomic-write temporary symlinks.

Each RED was followed by a minimal implementation change and a focused GREEN regression.
The resulting protocol introduces `ValidationAttempt`, `ValidationRun`,
`ValidationResultV2`, `ValidationReceiptV2`, canonical JSON, authenticated provenance, and
protocol-level byte ceilings. Stdout/JUnit remain bounded content rather than summary-only
claims: compact classification/digest markers retain as much redacted raw tail as fits.

## Commands and results

```text
.venv/bin/pytest tests/benchmark/test_corpus.py tests/benchmark/test_artifacts.py tests/benchmark/test_report.py -q
PASS — 203 collected tests

.venv/bin/pytest tests/benchmark -q
PASS — 494 collected tests

.venv/bin/pytest tests/benchmark/test_corpus.py tests/benchmark/test_artifacts.py tests/benchmark/test_report.py -q -k <G-CODE-002 mutation selection>
PASS — 56 selected adversarial tests

.venv/bin/pytest -q
FAIL — 870 passed, 1 failed of 871 collected

.venv/bin/pytest --cov=src/attest --cov-report=term-missing --cov-fail-under=90 -q -k 'not test_spend_insertion_is_idempotent_by_run_id_and_updates_total'
PASS — 92.02% total coverage; 870 tests run

.venv/bin/ruff check .
PASS — All checks passed

.venv/bin/mypy src/attest
PASS — no issues in 46 source files

git diff --check
PASS
```

The sole full-suite failure is
`tests/test_phase3_acceptance.py::test_spend_insertion_is_idempotent_by_run_id_and_updates_total`
at line 712. It expects the literal date `2026-08-29`, while the implementation correctly
uses the current date (`2026-08-30` during this run). The same baseline failure is assigned
to M-03's injected-clock work. M-02 did not modify that test or its implementation.

## Immutable history and artifact inventory

The historical v1 files have no diff and retain these SHA-256 digests:

- `benchmarks/attest-v1/receipt.json`:
  `e8cabb89471bb369a93ce82399a342eaddbf7ed8994d5420aef66256d013ce40`;
- `benchmarks/attest-v1/validation-results.json`:
  `e90b2acfb9753db196cd7d2cf999dc2fa24bbd91bb84d908b476682c1b441288`;
- `benchmarks/attest-v1/protocol.md`:
  `2a6019533a1c01abbf905e57b0b15017b806aeeee6028e496b0149a4a1f2246c`.

The versioned construction artifacts are `benchmarks/attest-v2/protocol.md` and its README;
`tests/benchmark/_validation_v2.py` builds isolated canonical fixture bundles whose sealed
artifact manifests content-address every emitted file. No fixture overwrites a historical
receipt.

## Independent review

An implementation-independent reviewer performed repeated read-only adversarial passes.
Resolved findings covered authority-capability mutation, exact command/source/environment
bindings, stable raw/persisted failure signatures, exclusion reason/chronology, path and
symlink containment, atomic no-follow writes, byte ceilings, bounded stdout/JUnit symmetry,
all-excluded provenance, and redaction/hash symmetry. Final verdict: **P0 none, P1 none,
P2 none; APPROVE local commit**.

## Permitted conclusion and non-claims

The implementation satisfies the M-02 receipt-evidence and authority contract and its
field-level adversarial gate. It may be described as passing `G-MEASURE-002` and
`G-CODE-002` on the stated local environment.

M-02 is not accepted complete because `G-CODE-001` is not green. This report makes no
algorithm-quality, population, recall, precision, security-certification, Core, live-run,
paid-study, pilot, release, or remote-action claim. It does not implement or accept M-01,
M-03, C-01, V-01, or Core.
