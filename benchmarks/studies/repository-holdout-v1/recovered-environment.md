# Reconstructed exact-version development environment

Baseline `d4ff7a8c152411be8d51248374efd08533586675`; owner instruction: continue.
One bounded experiment on the first frozen development case, keras/8. No new case,
held-out access, paid/model call, product/default change or execution-policy relaxation.
The earlier historical-oracle records remain immutable.

Before execution, commit the existing driver's `--recovered-dependencies` arm and this
protocol. Original requirements, source SHAs, fixed oracle overlay, original pytest node
and configuration remain unchanged. This arm supplies missing originals and an explicit
build toolchain; it is not a claim of bit-for-bit original environment reconstruction.

## Inputs and build

- NumPy source: already recovered official `numpy-1.19.0rc2.tar.gz`, SHA-256
  `39814c52f65c89385028da97da574d5e2a74de5c52d6273cae755982c91597bc`.
- SciPy: preflight found the pinned `scipy==1.5.0rc1` also absent at its PyPI endpoint.
  Recover only `scipy-1.5.0rc1-cp37-cp37m-manylinux1_x86_64.whl` from the official
  `https://github.com/scipy/scipy/releases/tag/v1.5.0rc1`, release asset ID 21216994,
  size 25,864,062. Save official metadata, downloaded SHA-256, and wheel METADATA/tag;
  the old asset has no API digest, so do not call this an independently checksum-signed
  binary. No third-party replacement or package version change.
- Keep both inputs under `.attest/corpora/recovered-dependencies-keras8/`, with a hashed
  manifest. The driver verifies both hashes before building and binds that manifest.
- Use official `python:3.7.3` full image for its compiler toolchain, linux/amd64; resolve
  and bind its digest. This deliberately differs from the earlier slim image. Record
  Python, GCC, OS packages and installed distributions. No host compiler/install.
- Keep pip 20.1.1, setuptools 46.4.0 and wheel 0.34.2; add Cython 0.29.19, satisfying
  recovered NumPy's declared `Cython>=0.29.14`. Build NumPy with two build jobs and
  no isolated dependency resolver; retain the resulting wheel checksum and build log.
- Install the locally built NumPy wheel, then install the unchanged requirements with
  the verified SciPy archive available via `--find-links`. Run pip check and verify
  each exact recorded requirement against installed metadata before test execution.
- Pull deadline 300 s, build deadline 1800 s; one build attempt. No apt/source-mirror
  fallback, additional pin repair, replacement BLAS selection or runtime relaxation if
  this arm fails. Record the operational blocker and stop.

## Oracle and interpretation

Only after a successful locked install, use unchanged Controller/ContainerAdapter and
the original pytest node/configuration for three fixed/buggy repeats, as defined in
historical-oracle.md. Preserve its 120 s, 2 GiB, network-none, non-root, read-only,
NPROC=0 and default pid cap. Stop after the first non-discriminating pair; no xdist,
fixture, skip, thread/process or source repair based on outcomes. Print the recorded
build environment before Keras import so an import failure retains provenance.

The compiled NumPy wheel may differ from an original binary's compiler/BLAS choices.
Even successful pairs establish only this arm's oracle feasibility. No semantic
qualification, receipt, product recall or safety guarantee follows. One independent
review plus script lint and artifact checks; no product RED/full product gate.
