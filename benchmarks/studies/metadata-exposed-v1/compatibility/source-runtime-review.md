# Independent source-runtime adapter review

Baseline: f2560ce; reviewed working diff in scripts/corpus/swebench_source_runtime.py and new benchmarks/studies/metadata-exposed-v1/compatibility/source-runtime.md. No implementation files or HEAD changed.

## Findings

No concrete defects found in the scoped adapter diff. This is source review and pure input validation, not evidence that the runtime succeeds.

The natural-pair branch reuses natural_cases to bind qualification and freeze bytes, requires the exact ordered case/revision population and committed build bytes, checks the population digest, retains failed builds as build_unqualified, runs the generic fixture before corpus execution, and sends only the two built Astropy wheels through the existing revision/digest-bound overlay and ContainerAdapter execution path. The overlay preserves original source bytes. Symlinks are rejected before export. The protocol keeps qualified defects/controls at zero and does not imply original-test or product success.

Default compatibility: pure validation of the existing six-case inputs passed the newly strengthened complete-status and ordered identity/revision checks. Default paths and fixture default remain intact.

## Validation

- Imported existing natural_cases and sha256_bytes; validated the actual committed natural population and build record: four ordered rows, statuses built/built/build_failed/build_failed, matching population digest.
- Validated the actual default six-case frozen population against its committed build record: complete, six ordered matching revisions, all built.
- `.venv/bin/python -m ruff check scripts/corpus/swebench_source_runtime.py`: passed.
- No builds, corpus execution, full tests, paid calls, remote writes, product scoring, or security-gate claims.

## Size and reuse

Reviewed tracked diff --stat: scripts/corpus/swebench_source_runtime.py | 94 lines changed, 66 insertions(+), 28 deletions(-). The protocol was new/untracked at review time and therefore absent from git diff --stat.

Reused inventory: natural_cases, sha256_bytes; inspected existing apply_wheel and retained archive/check_runtime/check_fixture reuse. No new tools or helpers introduced. Reviewer owns only this report.
