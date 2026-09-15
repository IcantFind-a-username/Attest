# First historical development oracle: dependency bootstrap blocked

E-02 preparation, D-262; owner-directed continuation, 2026-09-16.
Baseline `00b95f6bf3b51d76c6fd6650937366b949cbf9ae`; branch
`chore/keras-historical-oracle`; final driver `5058843`.

## Result

**One independent development case attempted; zero oracle tests executed.** The first
frozen case, keras/8, reached dependency installation in its historical amd64 Python
3.7.3 image. Installation stopped at the exact recorded requirement
`numpy==1.19.0rc2`: pip could not find a matching distribution. A subsequent read of the
[official release metadata endpoint](https://pypi.org/pypi/numpy/1.19.0rc2/json) returned
HTTP 404 ([record](../../benchmarks/studies/repository-holdout-v1/historical-oracle-evidence/numpy-release-check.json)).
This establishes the observed installation-source blocker, not that every historical
archive lacks the original artifact or that a port could never work.

The historical Python image successfully ran the pinned bootstrap installation; its
digest is recorded. The full dependency image did not build. Neither the fixed nor
buggy oracle ran; CPU, pytest-xdist and process-policy compatibility remain untested.
No defect was qualified, no receipt was issued, and no recall/FPR conclusion follows.

## Three retained attempts, one case

| Attempt | Driver | Observed stage and result | Interpretation |
|---|---|---|---|
| r1 | `95e5e45` | Docker exit 125: unsupported progress flag | Invocation failure; no dependency installation |
| r2 | `e314439` | Legacy builder exit 1 at ENV: missing image content digest | Builder failure; no RUN instruction executed |
| r3 | `5058843` | BuildKit runs bootstrap tools, then pip exits 1 at NumPy pin | Historical dependency bootstrap failure |

The [protocol](../../benchmarks/studies/repository-holdout-v1/historical-oracle.md) and
driver were committed before running. Both invocation repairs are visible amendments;
no behavioral outcome existed when they were made. R3 was the declared final attempt.
No package version, oracle, source revision, timeout or isolation limit was relaxed.
The three attempts are not three independent cases.

## Pair and execution preparation

The fixed revision is `d78c982b326adeed6ac25200dc6892ff8f518ca6`; buggy revision is
`87540a2a2f42e00c4a2ca7ca35d19f96e62e6cb0`. Both were fetched into the existing approved
development clone and exported. The fixed test file was copied unchanged onto both
exports and bound separately by SHA-256. The same original pytest node/configuration
would have run against both; both exports retain `-n 2`. No test execution reached that
configuration, and the existing NPROC=0 policy was not relaxed to accommodate it.

The same requirement bytes were used in all three build contexts. The image uses the
official Python digest `sha256:baf4188f0b50c6383fedd55cdb79f511bfabee23068dcf26f209426f4bf540ab`,
with linux/amd64 on the aarch64 Docker host. Bootstrap tools were preregistered separately
as pip 20.1.1, setuptools 46.4.0 and wheel 0.34.2. The build had network access for package
retrieval and no supplied host credentials or secret mounts. Dependency build code ran
inside Docker; reviewed Keras source and pytest did not run on the host or in test jobs.

Product execution/certification code, interpreter matrix and defaults are unchanged.
The driver reuses the existing archive, Controller/ContainerAdapter, JUnit reader and
shared artifact helpers. No new execution backend or product command was introduced.
Other development cases and all held-out cases were not attempted or replaced.

## Review and evidence

One [independent review](../../benchmarks/studies/repository-holdout-v1/historical-oracle-evidence/independent-review.md)
covered r1 and identified the unsupported flag. It did not review r2/r3 or final code;
the controller validated those repairs and artifacts without a second review pass.
No statement here treats that review as independent validation of an unexecuted oracle
or a security gate. Final script Ruff and artifact/diff checks pass; no product RED or
full product gate was run for this experiment.

[Evidence](../../benchmarks/studies/repository-holdout-v1/historical-oracle-evidence/validation.json)
contains raw-record/log digests, redacted projections, build logs and Dockerfiles for
all three attempts. Source exports and original records remain untouched in the ignored
corpus work directories; committed projections replace machine-local root/home paths.
Rendered build logs normalize line endings and trim trailing whitespace; original hashes
always refer to the untouched raw logs.

## Consequence

The next prerequisite is recovery and verification of the original missing dependency
artifact, if available from an authoritative archive. Do not silently install NumPy
1.19.0 instead and call that the recorded environment. If recovery is infeasible,
retain this case as environment-unqualified and preregister any different development
population separately; do not overwrite the frozen split or consume its held-out cases
as replacements. Model discovery spend remains premature while the oracle cannot run.

Attest model/API spend **$0**. No push, remote write, publication or product promotion.
G-CORPUS-001 and semantic qualification remain open. Reversal needs only disabling this
research driver; preserve the measured failure records and original frozen population.
