# Recover the original NumPy archive — bounded E-02 preparation

Baseline `4558bff9ef5396ebc7318d65b3f0216f1dbeb088`; owner instruction: continue the
original dependency archive investigation. This task recovers the missing prerequisite
for the existing keras/8 development experiment; no new corpus or product trial.

Read-only investigation found the official release before download:
https://github.com/numpy/numpy/releases/tag/v1.19.0rc2 . Its release metadata lists
`numpy-1.19.0rc2.tar.gz` and publishes this SHA-256 in the release body:
`39814c52f65c89385028da97da574d5e2a74de5c52d6273cae755982c91597bc`.
PyPI's prior 404 remains a valid observation of that endpoint; it was never proof that
all historical archives were absent. Do not use a third-party repost as the authority.

After committing this protocol:

1. Save the official GitHub release metadata with
   `gh api repos/numpy/numpy/releases/tags/v1.19.0rc2`.
2. Download only the named official release asset with `gh release download v1.19.0rc2
   --repo numpy/numpy --pattern numpy-1.19.0rc2.tar.gz --dir <fresh recovery directory>`.
3. Use `sha256_bytes` from the existing artifact helpers to require exact equality with
   the checksum in both this protocol and the saved official release body. Record release
   and asset IDs, URL, metadata digest, package size/digest and fetch commands.
4. Inspect only archive metadata and PKG-INFO using Python's tar reader without extracting,
   importing, installing or executing it. Require package name numpy and version 1.19.0rc2.
   A matching name alone is insufficient; a digest mismatch refuses recovery.

The fresh location is `.attest/corpora/numpy-1.19.0rc2-recovery/` under this checkout.
No host package installation, compiler/backend change, dependency substitution, package
build, oracle execution, model call or remote write. Keep the source archive ignored;
commit safe source metadata, SHA-256 and verification evidence. Reuse shared artifact
helpers, no new measurement script or product helper. One independent provenance review.

Recovery means a local source distribution matching the official release's checksum.
It does not prove a matching binary wheel, the original compiler/BLAS environment,
installability, bug reproduction, certification or performance. Stop at that concrete
artifact or a named retrieval/provenance blocker. A later build needs its own fixed protocol.
