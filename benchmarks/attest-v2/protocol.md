# Attest validation receipt protocol v2

Protocol version: `attest-validation-v2`.

This protocol governs corpus-validation authority, not product certification.
It does not reinterpret or replace the frozen `benchmarks/attest-v1` artifacts.

## Evidence contract

Every pair has exactly one bounded `ValidationAttempt` record. The v2 evidence
format deliberately forbids outcome-aware retries because a receipt assembled
after execution cannot prove that a larger retry budget was precommitted. A
`validated` result identifies its accepted execution attempt containing
three fixed PASS runs followed by three buggy FAIL runs with one stable failure
signature. An `excluded` result also retains its attempt; an execution-phase
exclusion contains at least one real run, while a preflight exclusion remains
explicitly typed and provenance-bound.

Each run content-addresses bounded stdout and JUnit plus its exact executed
command, validation test, interpreter, inherited execution environment,
repository source, and executor metadata. The command binds the declared
runtime/test descriptor and the executor binds the wrapper argv and isolation
capability.
Runner, isolation profile, interpreter, environment, command argv, and
per-revision source identity must be consistent under the declared oracle.
Unknown schema/protocol/enum/field values fail closed.

The protocol byte ceilings are fixed and are enforced before full offline
reads:

- each bounded stdout or JUnit artifact: 16,384 bytes;
- each other artifact: 1,048,576 bytes;
- the artifact manifest: 8,388,608 bytes;
- each validation receipt, validation-results document, or corpus manifest:
  8,388,608 bytes.

An issuer may select a smaller artifact bound, but never a larger one. A
truncated validation stdout retains a compact failure/dependency marker and as
much raw tail as fits. A truncated JUnit artifact likewise retains a compact
test/failure/error/skip-count and raw-content-digest marker followed by as much
raw XML tail as fits. The persisted bounded bytes, including these markers,
are themselves content-addressed.

## Authority contract

Canonical JSON is key-sorted, compact, ASCII-escaped UTF-8 with one trailing
newline. The receipt binds the exact manifest, validation-results bytes,
artifact manifest, protocol, and sorted validated-pair allowlist. A local
`hmac-sha256` provenance envelope authenticates that body under a caller-owned
key ID; the key is never stored in the evidence bundle.

Offline verification reports three independent decisions:

- `integrity`: canonical bytes and every declared digest/reference match;
- `authorized_provenance`: the envelope algorithm, key ID, payload digest, and
  authentication tag are authorized by the verifier;
- `semantic_policy`: attempts and raw artifacts satisfy the bounded
  fixed-PASS/buggy-FAIL or explicit-exclusion policy.

Only a v2 verification whose three decisions all PASS has
`current_scoring_authority`. An all-excluded run is still authenticated with
an empty validated-pair allowlist so its attempt evidence remains auditable,
but it covers no pair and is not scorable. V1 remains readable as
`historical_integrity_only`. Rewriting results and manifests together cannot
gain authority without an authorized envelope.

## Constructed fixture

`tests/benchmark/_validation_v2.py` creates the canonical v2 fixture used by
the M-02 unit, adversarial, report, and mutation tests. It writes real bounded
artifact bytes into a temporary content-addressed store and signs them with an
explicit test-only key. It is implementation evidence, not an empirical corpus
result, and it must never be copied over the frozen v1 receipt/results.
