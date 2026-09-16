# Independent setup-declaration review

Baseline: 71ebd55; branch fix/setup-version-declaration; reviewed uncommitted implementation.
Scope: container_images.py, swebench_source_runtime.py, test_setup_version_declaration.py,
and setup-declaration-runtime.md. One bounded review pass; source unchanged.

## Finding

- **P2 — same-statement alias rebinding passes the import guard**, `src/attest/execution/container_images.py:284`.
  `from setuptools import setup, find_packages as setup` followed by the direct call
  `setup(use_scm_version={'write_to':'pkg/_version.py'})` returns `pkg/_version.py`.
  The binding is actually find_packages, but the guard exempts the entire accepted
  ImportFrom statement. This contradicts the protocol's no-rebinding requirement
  and permits an otherwise unproven wheel Python file through the version-path exception.
  Check aliases within the accepted import as well; add this input to the rejection table.
  Reproduction used mocked Path.stat/read_text against the actual helper; no setup
  source or corpus was executed. Observed return: `'pkg/_version.py'`.

## Other checks and limits

Default opt-in behavior remains unchanged. Static AST parsing does not execute setup
source. Wheel revision/digest, original source retention, and collision/link validation
remain in the existing transfer path. The protocol correctly limits this to metadata
and readiness, not behavioral certification or recall. No other concrete finding.
Controller owns full/focused gates; review did not run Docker, corpus code, paid calls,
or remote actions. API spend: none.

## Diff and tool reuse

Reviewed tracked diff --stat: scripts/corpus/swebench_source_runtime.py 19 lines changed;
src/attest/execution/container_images.py 57 lines changed; total 69 insertions, 7 deletions.
Two new untracked source artifacts were also reviewed (test and protocol above).
Reviewer output: this one new report only.
Reused actual `_setup_version_path`; inspected existing declared_version_file and
apply_wheel/link/collision checks. No new repository tools or duplicate helpers.
