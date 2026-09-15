# Compatible builds: six of six wheels built

E-02 prerequisite, D-271. Baseline `eb238c0`; measured driver `40308c5`, on
`chore/swebench-compatible-build`. **Six completed builds succeeded; no runtime
execution, qualified defect or qualified control exists yet. Model/API spend: $0.**

The owner authorized a uniform compatibility experiment on the same six frozen
cases. Python 3.10 is common to their declared CI/classifier support. A separate
compiler-bearing builder and date-bounded direct/build dependencies overcome the
first errors observed by D-270. No project source repair was made.

| Repository | Cases | Compatible wheel builds |
|---|---|---|
| Astropy | 14369, 13236, 13398 | 3/3 |
| scikit-learn | 25232, 25973, 26323 | 3/3 |

The original default-runtime **0/6 build result remains valid and separate**.
Compatible 6/6 is build feasibility, not Attest detection or runtime success. No
precision, recall or false-positive-rate estimate follows from these builds.

## Evidence and review

[Frozen protocol](../../benchmarks/studies/swebench-independent-v1/compatible-runtime.md),
[all six records](../../benchmarks/studies/swebench-independent-v1/compatible-build-evidence/result.json),
[resolved isolated dependencies](../../benchmarks/studies/swebench-independent-v1/compatible-build-evidence/isolated-dependencies.json),
[manifest](../../benchmarks/studies/swebench-independent-v1/compatible-build-evidence/manifest.json).
Each record binds the revision, constraints, Dockerfile, image, wheel, build log
and isolated dependency metadata. Raw wheels and logs remain in the ignored corpus
directory. The compiler builder is digest-pinned; no host credentials, sockets,
SSH forwarding or secrets were supplied to the source build.

One independent review found two evidence defects: outer `pip freeze` omitted
isolated build dependencies, and manifest schema errors could abort later rows.
[The review](../../benchmarks/studies/swebench-independent-v1/compatible-build-evidence/independent-review.md)
and [resolutions](../../benchmarks/studies/swebench-independent-v1/compatible-build-evidence/review-resolution.md)
are retained. The initial first-case invocation was canceled before a behavioral
outcome; its log explicitly records cancellation. There are **six completed
attempts plus one interrupted attempt**, not six invocations in total. The
correction changed instrumentation and refusal handling, not dependencies or
selection. The interrupted artifacts remain intact.

All exported hashes, wheel presence and isolated metadata were checked. Ruff and
`git diff --check` pass. Product source and tests are unchanged from baseline,
with source tree `d62ecadbdb5e9c70eed119007b7cb89df5d8481a`; no new full product gate
is claimed for this diagnostic-only work. No paid calls, push or remote writes.

## Limits and next step

These are assisted environments on Linux aarch64. Dependency upper bounds use
case creation timestamps; they are not full historical transitive locks. For
example, newer unbounded transitive dependencies appear in the retained metadata.
Astropy retains the existing product's SCM fallback version `0.0.1`, so these are
not historical release binaries. No claim depends on build timing or cache speed.

Next, freeze and validate a revision-specific generated-file transfer using a
generic compiled fixture, then run source-mounted import checks with the existing
secretless container adapter. Preserve every tracked source byte and bind each
revision to its own generated artifacts. Installed-wheel import alone cannot
qualify source-mounted product execution. This runtime path has not yet been
implemented or accepted by the build result.

After runtime qualification, original paired human tests, forward-direction
eligibility and independently judged controls remain required. The paid study's
minimum and approved cap remain unchanged. The final paid report is unfinished;
the long task continues toward those prerequisites without spending prematurely.
