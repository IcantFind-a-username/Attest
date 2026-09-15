# Authorized compatibility experiment

Baseline: `eb238c01c6f4e721d8d78d6ff304f618469ed57f`. The owner authorized this
free experiment after D-270. The six frozen candidates and default-runtime 0/6
build result remain unchanged. No model calls, paid reservations, default policy
changes or certification changes are part of this experiment.

Use Python 3.10, the highest minor common to the read project CI/classifier
declarations. Build with the compiler-bearing `python:3.10-bookworm` image;
retain its resolved digest. All six use the same algorithm, in frozen order:

1. Export the exact frozen revision from its existing approved clone.
2. Read build-system requirements and existing direct-dependency extraction.
   For their package names plus pip, setuptools, wheel, pytest and numpy, use
   the existing PyPI `latest_before` rule at the case creation timestamp to
   write upper constraints. Original requirement specifiers/markers remain
   authoritative to pip; an empty intersection fails rather than relaxing pins.
   Unresolved metadata fails preparation. These are direct/build upper bounds,
   not a complete historical transitive lock. Retain resolved environment too.
3. Build one wheel with declared build isolation, no unpinned fallback, at most
   900 seconds per case. Source is copied into the builder without credentials,
   host sockets, secrets or SSH forwarding. Builders may fetch dependencies.
   Record logs, input SHA/digests, image identity and wheel digest. A build is
   not an execution witness, a qualified defect, or an Attest success.
4. After build feasibility, perform secretless runtime qualification using the
   existing container adapter. Installed-wheel import alone is insufficient:
   source-mounted checks need revision-specific generated artifacts. Original
   tracked bytes must remain unchanged; no native artifact may be reused across
   revisions. Freeze and review that transfer before its first execution.

No per-case source repairs or outcome-driven dependency retries. Keep every
failure in the six-case denominator. Default and compatible results are separate.
The paid-study minimum, semantic oracle and forward-direction requirements remain
unchanged. No paid dispatch follows from build success alone.

The first deliverable is the six-case build-feasibility record. This measurement
driver is committed before running; runtime integration is a subsequent bounded
step within the authorized compatibility work, not permission to bypass gates.

## Pre-outcome instrumentation correction

The first invocation at `7e37a41` was interrupted after starting the first build:
independent review found that outer `pip freeze` omitted isolated build versions.
Its directory is retained as `swebench-compatible-build-pre-review`. No behavioral
outcome or dependency change motivated this interruption. The corrected driver
retains isolated build metadata and verbose logs, exports wheel digests, and
records malformed case manifests without losing later rows. This is one bounded
review pass; original six-case ordering, dependencies and 900-second limit stand.
