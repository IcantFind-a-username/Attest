# Recovered environment: independent review

Reviewed once: `d4ff7a8..32d5b98`, branch `chore/build-recovered-environment`.
Scope: the existing historical-oracle driver's recovered-dependencies arm and its
committed protocol/provenance manifest. No product implementation changed.

## Findings

No concrete blocking defect found in the scoped change. No repair requested.

- `scripts/corpus/historical_oracle.py:178`: both retained archives match committed
  byte lengths and SHA-256 values; the driver verifies them before copying into its
  fresh build context and records the manifest digest.
- `benchmarks/studies/repository-holdout-v1/recovered-environment-evidence/dependencies.json:1`:
  NumPy's local archive digest matches the checksum in retained official release metadata;
  PKG-INFO says numpy 1.19.0rc2. SciPy's raw release metadata digest, release/asset IDs,
  official URL, size, METADATA digest, version 1.5.0rc1 and cp37/cp37m/manylinux1_x86_64
  wheel tag all match. SciPy has no API asset digest; the protocol accurately limits its
  authenticity claim. Manifest SHA-256:
  `b22dbc16dec1c0d670f20bcd5c5903c89cd32f8411ac8b4c88ba8724f178ec65`.
- `scripts/corpus/historical_oracle.py:197`: the pinned development requirements contain
  exact version requirements, including the original NumPy/SciPy prereleases. They are
  copied unchanged and checked against installed distribution metadata before execution;
  pip check additionally rejects incompatible dependencies. Cython 0.29.19 meets the
  recovered NumPy source's declared >=0.29.14 build requirement.
- `scripts/corpus/historical_oracle.py:220`: the selected full Python image is resolved
  and built by digest. Tool versions, compiler/OS package inventory, built wheel checksum,
  image identity and installed distribution list are retained by the intended build/run.
  The new output prefix records environment details before Keras import.
- `scripts/corpus/historical_oracle.py:267`: source SHAs, fixed oracle overlay, argv,
  Controller/ContainerAdapter, limits and outcome predicates are unchanged. Success still
  requires three accepted fixed/buggy pairs, exact one-test pass/fail counts and matching
  exit codes; the first non-discriminating pair stops. Missing/invalid JUnit cannot match.
  Build failure stays blocked with zero product evaluations and receipt eligibility false.

## Validation and limits

Read-only checks: `git diff d4ff7a8..32d5b98`, `git diff --check d4ff7a8..32d5b98`
(clean), original keras/8 requirements at the frozen metadata SHA, retained official
release JSON, SHA-256 comparisons and tar/zip metadata reads without extraction/import.
No corpus code, build, oracle, paid call, network access or remote write was performed.
No held-out source or case contents were read. This review does not establish installability,
oracle feasibility, semantic truth, product recall, a security gate, or bit-for-bit rebuilds.

The remaining package downloads are version-pinned rather than a hash-locked wheelhouse;
`--find-links` makes the verified SciPy archive available but does not prohibit index
candidates of the same version. Consequently the present protocol supports an exact-version
reconstruction claim, not a claim that every installed binary is an original historical
artifact. The recorded compiler/BLAS distinction and unsigned SciPy limitation remain material.

Reviewed diff --stat: 3 files changed, 129 insertions(+), 7 deletions(-): script 78+/7-,
protocol 50+, manifest 1+. Reviewer writes only this ignored report.
Reused tool inventory: `sha256_bytes` for local validation; reviewed reuse of `_atomic_write`,
`write_canonical_json`, `validation_junit_counts`, and existing `archive`.
New helpers/tools: none. Review cost: no paid calls. Full product gates not run under the
protocol's diagnostic-only scope; controller owns script lint and eventual build evidence.
