# Compatible source runtime: three of six import checks passed

E-02 prerequisite. Baseline `e400ef2`; product source is unchanged at tree
`d62ecadbdb5e9c70eed119007b7cb89df5d8481a`. No paid call, push or remote write.
Three scikit-learn cases pass a source-mounted import test under the existing
guarded executor. Three Astropy cases fail before a test body executes.
This is runtime feasibility, not defect recall or a product review.

## Retained runs

| Run | Driver | Astropy (3 cases) | scikit-learn (3 cases) |
|---|---|---|---|
| r1 | `44b38da` | Transfer refused: generated build input | Transfer refused: generated build input |
| r2 | `fa465be` | Pytest argument parsing failed | Runtime image build failed: test dependency needs compiler |
| r3 | `4c3b4fa` | Pytest argument parsing failed | 3 source-mounted import tests passed |

All six original IDs remain in every run. r1 executed no corpus tests; r2 invoked
the executor three times but executed no corpus test body; r3 invoked it six
times and executed three import tests. Each run first passed the same generic
native fixture. Repeats and generic fixtures are not independent defect/control
cases. Original default-runtime build failures remain separately recorded in
D-270, and D-271's six wheel builds remain build-only evidence.

The r3 success criterion requires one collected, unskipped test, exit zero,
active network guard, and imports under `/attest/tree`. Retained JUnit confirms
one passing test in each successful row. Astropy's unchanged configuration asks
for `--doctest-rst`, which the guarded invocation does not recognize with plugin
autoload disabled. There is no Astropy collection or behavior result.
The existing product `ReproSpec` carries only test code and `execute_repro` builds
the pytest arguments itself; this experiment has no supported per-case plugin
argument switch. The source-freeze and unchanged invocation constraints remain.

## Implementation and review

Wheel transfer checks revision/digest identity, rejects unsafe archive paths and
symlinks, checks all source overlaps, and preserves original source bytes. It
copies only absent native extensions and an explicitly declared version file.
Missing build-only headers/Cython inputs are recorded as omitted, not copied.
The final runtime image installs dependencies from wheels compiled in a separate
builder; the runtime gains no compiler or additional execution permission.

One independent review found missing refusal-stage records and a file/directory
collision that could leave partial transfer output. Both were fixed before r1.
The focused transfer/adjacent checks passed (12 tests). Boundary tests use
parameterized ZIP fixtures; their setup exceeds assertions because each refusal
requires a distinct archive shape and a check that no partial output remains.

The completed gate started at `fa465be` and is not a pass: 2,540 passed,
18 failed, five errors, zero skipped, 2,398.87 seconds. Certification/execution
coverage is 93.42%. The controller committed
diagnostic scripts while it ran: M01's 20 repeated measurements contain six rows
at `4c3b4fa` and fourteen at `98c32fa`. Its aggregator correctly rejects this
source-SHA mismatch, despite identical source-tree digests. Unchanged source and
tests are therefore insufficient to accept this whole run. This is a controller
verification error. Repository-only temporary-directory settings also placed
pytest caches and some fixture files outside the declared scratch directory:
13 of the other failures passed with the temporary pytest cache disabled, and
the remaining four passed when fixture directories were placed inside scratch.
No product code, test assertion or guard was changed. These are focused rechecks,
not a new complete gate. The remaining macOS outside-home check requires normal
system temporary storage, for which owner authorization has been requested under
AGENTS sections 7/16. A fixed-HEAD complete gate remains outstanding.
The earlier `44b38da` run was interrupted and is not a full gate either.

[Runtime records, review and checks](../../benchmarks/studies/swebench-independent-v1/source-runtime-evidence/manifest.json)
include the full failed gate and focused rechecks. Ruff and mypy pass; peripheral
coverage is informational and retained separately. No failure or interrupted run
was erased or relabelled as a pass.

## Limits and next step

This assisted Python 3.10/Linux aarch64 path has creation-date dependency upper
bounds, not a complete historical transitive lock. It has not been integrated
with the product's internal base/head worktree preparation. Three ready cases
come from one repository; zero qualified defects and zero qualified controls
exist at this stage. The independent paid study minimum is still unmet.

Original oracle inputs for these three rows were frozen by committed reader
`98c32fa`, independently reviewed, and verified for digests and private modes.
[Input provenance](../../benchmarks/studies/swebench-independent-v1/oracle-input-evidence/manifest.json)
contains safe metadata only. No hidden tests or repair patches enter product
prompts. The [original-test diagnostic](2026-09-16-swebench-original-oracles.md)
now discriminates the three patch overlays, while semantic triage identifies one
new capability and two existing-contract defects. Natural forward direction,
revision-specific paired artifacts, controls and product integration
remain separate prerequisites. No precision, recall, zero-FPR or release claim
follows from this report.
