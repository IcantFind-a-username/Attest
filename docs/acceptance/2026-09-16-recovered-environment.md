# Original dependencies install; historical oracle blocked at worker startup

E-02 preparation, D-264; 2026-09-16. Baseline `d4ff7a8`, preregistration `561ebc6`,
measured driver `32d5b987005f1d5a01d52f96d4dc38da35eaf51b`, branch
`chore/build-recovered-environment`. One bounded experiment on frozen development case
keras/8; product source and the frozen population are unchanged.

## Result

**The reconstructed environment installs all 42 original exact dependency pins.**
NumPy 1.19.0rc2 builds from the previously verified official source archive; pip uses
the recovered official SciPy 1.5.0rc1 wheel. The installed-metadata check and `pip check`
both pass. This removes the previously observed dependency-availability/install blocker.

**The oracle remains unqualified.** The first fixed/buggy pair starts pytest, but both
jobs exit 3 during pytest-xdist worker creation with
`BlockingIOError: [Errno 11] Resource temporarily unavailable`. Original `pytest.ini`
requests two workers; the unchanged container adapter sets `RLIMIT_NPROC=0`. Both logs
show the same `xdist -> execnet -> subprocess.Popen` failure before the target test runs.
Keras imports from the exported source tree before that failure.

| Unit | Result |
|---|---:|
| Independent development cases attempted | 1 |
| Dependency-image build attempts / successful builds | 1 / 1 |
| Fixed/buggy execution jobs dispatched | 2 |
| Completed target tests / usable JUnit results | 0 / 0 |
| Discriminating pairs / qualified defects | 0 / 0 |
| Product evaluations / receipts | 0 / 0 |

Both envelopes are protocol-accepted, but neither meets the oracle pass/fail predicate.
Protocol acceptance is not test success. The driver stops after this first non-discriminating
pair as preregistered; repeats two and three are not run. There is no recall, precision,
false-positive-rate or safety estimate. No other development or held-out case was accessed.

## Environment and provenance

The [protocol](../../benchmarks/studies/repository-holdout-v1/recovered-environment.md)
and driver were committed before the build. The original requirements, fixed/buggy SHAs,
test overlay digest, pytest node/configuration and isolation limits match the earlier
[historical attempt](2026-09-16-historical-oracle.md), whose failed records remain intact.

The official full `python:3.7.3` image replaces the earlier slim image for its compiler:

- Base image: `sha256:9e0b4f32487ca1863b45383420b8db77990debae748e2e875d2f86fa9510d4a5`.
- Built image: `sha256:869b6deb283abd536330a54cec36779b955c4fb0af8dafec98c0917f472bdb09`.
- Python 3.7.3, GCC 6.3.0; linux/amd64 on the existing arm64 Docker host.
- Bootstrap: pip 20.1.1, setuptools 46.4.0, wheel 0.34.2, Cython 0.29.19.
- Built NumPy wheel SHA-256:
  `121981baae779d0ae55ac3c96e46f0de450abe6ebe5f4fad0fff952daf02c8bf`.

The [dependency manifest](../../benchmarks/studies/repository-holdout-v1/recovered-environment-evidence/dependencies.json)
binds both recovered inputs. NumPy matches its published release checksum. SciPy comes
from its [official release asset](https://github.com/scipy/scipy/releases/tag/v1.5.0rc1),
asset 21216994; local SHA-256 is
`1f402f14e726d41fd34e30b6c54daac36ac84ee64c4a430ed4b5ec016705e053`.
The old SciPy API metadata has no asset digest; this is recorded provenance, not an
independent signature. The build log confirms processing the local SciPy wheel.

The compiled NumPy wheel, installed distributions and compiler/OS inventory were exported
with `docker create`/`docker cp` without starting an additional container, then that temporary
container was removed. The binary remains in the ignored run directory; its checksum and
environment records are committed. No host package installation occurred. Dependency builds
had network access without supplied credentials; the two oracle jobs used network-none,
non-root, read-only containers with the existing limits. Neither isolation nor pytest
configuration was relaxed after observing the result.

Exact installed versions do not prove identical historical binaries, BLAS choices or CPU
behavior. Remaining index downloads are version-pinned, not a hash-locked wheelhouse.
`image.build_elapsed_s=0` is an inherited constructor default, not a measured build time;
this report draws no timing conclusion from it.

## Review, validation and consequence

One [independent review](../../benchmarks/studies/repository-holdout-v1/recovered-environment-evidence/independent-review.md)
covered `d4ff7a8..32d5b98` and input provenance, finding no blocking defect. It did not
execute or independently validate the later run. The controller checked the actual run's
stage/artifact hashes, envelopes, error traces and zero-result accounting afterward.
Script Ruff, AST equivalence of the original oracle loop, immutable product/population
checks, evidence links and `git diff --check` pass. No product RED or full product gate
was run for this measurement-only script extension.

[Validation and artifact digests](../../benchmarks/studies/repository-holdout-v1/recovered-environment-evidence/validation.json)
bind the measured SHA, protocol, environment and raw records. Public projections redact
local repository/home paths and normalize rendered whitespace; original files are retained
unchanged under `.attest/corpora/historical-oracle-keras8-recovered-r1/`.

Next prerequisite: a separately preregistered serial-launch compatibility experiment,
preserving test/assertion bytes, fixtures, dependency image and containment, could check
whether worker startup is the only execution blocker. That would be a changed test-launch
configuration, not a successful replay of this original configuration. Do not run it as
an outcome-driven repair of r1 or count it as product evidence. Runtime, semantic and
control qualification still precede any paid product study; G-CORPUS-001 remains open.

Attest model/API spend **$0**. No push, remote write, product/default change or release.
Rollback is to stop using the opt-in measurement arm; preserve all old and new evidence.
