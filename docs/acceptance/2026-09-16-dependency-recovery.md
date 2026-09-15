# Original NumPy source archive recovered

E-02 preparation, D-263; 2026-09-16. Baseline `4558bff`, protocol `e180107`,
branch `chore/recover-numpy-archive`. Owner-directed continuation, no product change.

**Recovered:** `numpy-1.19.0rc2.tar.gz`, 6,768,712 bytes, from the
[official NumPy release](https://github.com/numpy/numpy/releases/tag/v1.19.0rc2).
The downloaded bytes match the release body's SHA-256 exactly:

```text
39814c52f65c89385028da97da574d5e2a74de5c52d6273cae755982c91597bc
```

The tar member `numpy-1.19.0rc2/PKG-INFO` reports name `numpy`, version `1.19.0rc2`.
It was read as metadata, without extracting or executing the archive. The ignored local
artifact is `.attest/corpora/numpy-1.19.0rc2-recovery/numpy-1.19.0rc2.tar.gz`.

The previous PyPI 404 and installation failure remain valid historical observations.
They do not imply absence from the separate official GitHub release archive, which
retains the source distribution. This result resolves source-archive availability only.
No binary wheel was recovered and no installation, source build, oracle test, receipt
or product evaluation occurred. The original dependency pin remains unchanged.

## Provenance and checks

The [protocol](../../benchmarks/studies/repository-holdout-v1/dependency-recovery.md) was
committed before download. Existing `gh` read-only commands obtained official release
metadata and its named asset; shared SHA-256/JSON helpers and Python tar/email readers
verified bytes and metadata. No measurement script or product helper was added.

[Source projection](../../benchmarks/studies/repository-holdout-v1/dependency-recovery-evidence/source.json)
records release/asset IDs, URL, times and the published checksum; the complete raw API
response stays beside the ignored archive and its digest is retained.
[Recovery record](../../benchmarks/studies/repository-holdout-v1/dependency-recovery-evidence/recovery.json)
binds the protocol, commands, archive and PKG-INFO. Matching the official release's
currently published checksum is not an independent signature or environment-equivalence proof.

One [independent provenance review](../../benchmarks/studies/repository-holdout-v1/dependency-recovery-evidence/independent-review.md)
and final [artifact checks](../../benchmarks/studies/repository-holdout-v1/dependency-recovery-evidence/validation.json)
cover this recovery. No product behavior changed; no RED or full product gate was run.

Next prerequisite: qualify installation of the recovered original source, or recover a
binary matching an official checksum, under a separate fixed build protocol. Compiler,
BLAS, remaining dependencies and execution restrictions must be recorded; source recovery
does not silently qualify a different numerical environment. The keras/8 environment
attempt remains unqualified until an actual paired oracle run succeeds.

No held-out or other development-case input was read. Attest model/API spend **$0**;
no remote write, push, default/policy change or product promotion. The browser was used
read-only and closed afterward; its update notice did not cause an upgrade.
