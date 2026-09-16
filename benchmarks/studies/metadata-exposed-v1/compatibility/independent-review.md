# Independent pre-execution review

Reviewed `4df5ef8..dc2d0ad`, branch `chore/natural-pair-compatibility`. No Docker build, corpus code execution, network request or paid API call performed. Only this review file is owned/written.

## Finding

**P2 — Validate the complete ordered build manifest before trusting its cutoff and output path.** `scripts/corpus/swebench_compatible_build.py:50-56` validates only an unordered set of `(source_case, side, base_commit, repo)`. `created_at` subsequently controls resolution at line 98; `instance_id` controls a filesystem path at line 81. Neither is bound to the reviewed source record, and parent/head order is not checked. Exact pure-data reproduction: load committed cases and qualification JSON; construct the same `expected` set; change `cases[0]['created_at']` to `2099-01-01T00:00:00Z` and `cases[0]['instance_id']` to `../outside-work`; the unchanged admission predicate still returns True. No source files were mutated. This admits an unapproved cutoff and output directory outside the dedicated work directory if that manifest drifts. Derive/compare complete ordered entries, including `instance_id == source_case + '-' + side` and the frozen original-case date, checking qualification's freeze digest against freeze bytes. Current committed entries themselves are correct.

## Checked evidence

- Qualification digest matches `cases.json`; qualification's freeze digest matches current `freeze.json`.
- Exactly four revisions match the two reviewed pairs. Astropy: parent `469a39d3637376ab1613f8b2fc949233fce94aee`, head `2a0c5c6f5b982a76615c544854cd6e7d35c67c7f`. Scikit-learn: parent `c592361e536fbc84c59935b7b4c659e8ab38737c`, head `416898b7f41257e5367dc65b5ec82670c1575ef8`.
- Cutoffs match selected frozen original cases: `2023-01-23T22:34:01Z` and `2023-03-22T00:34:47Z`, respectively, same date on both sides.
- Default six-case input/path and Python 3.10 recipe remain; new study uses separate output. Existing D-276 files are untouched.
- Tracked symlinks refused by ls-tree before archive; independent revision directories/tags/image IDs and artifact digests retain native-artifact identity.
- Docker config top-level keys are only `cliPluginsExtraDirs`; generated Dockerfile does not pass host environment or sockets into build. No new paid/default/product/security-policy changes.
- Existing failure handling retains build logs; timeout log exists but does not get a digest (pre-existing behavior, not a new adapter finding).

## Diff and reuse

`git diff --stat 4df5ef8..HEAD`: 3 files, 84 insertions, 13 deletions: cases.json (+1), compatible-runtime.md (+42), swebench_compatible_build.py (+54/-13).

Implementation reuses `sha256_bytes`, `write_canonical_json`, `archive`, `direct_dependencies`, `_fetch`, `latest_before`, and existing container-image helpers. No replacement serialization/digest/archive/dependency tools introduced. Review used built-in pure JSON/hash checks; no new tool implementation or measurement script added.
