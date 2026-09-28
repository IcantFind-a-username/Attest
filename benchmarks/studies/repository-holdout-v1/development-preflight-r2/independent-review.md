# E-02 development prerequisite census — independent review

One bounded review pass, 2026-09-16. Baseline `1bc7b680e2790e6ef83b5de410c2e4270a961f45`; reviewed repaired script/protocol at `04a25542f5d3e384530d6a5dce32c11c9d9385bc` on `chore/qualify-dev-environment`, plus the resulting `development-preflight-r2` artifacts. Reviewer owns only this file.

## Findings and resolution

- **P2, resolved — initial script lines 68–71:** parsing every non-comment requirements line as PEP 508 rejected the editable Keras VCS requirement in keras/30, stopping r1 before any census. The controller reported this during the same review pass. The preserved `development-preflight-r1/invalid.json` records the failure and partial metadata exposure. The repair at lines 68–78 extracts only the preregistered TensorFlow pin, still validates it with `Requirement`, and keeps full requirements hashes. All five cases remain in r2. No behavioral outcome was used to choose a retry.
- **No unresolved concrete findings** in the bounded script, protocol, manifest or r2 artifact review.

## Evidence checked

- Script lines 43–64 constrain selection to the frozen five development Keras candidates and read the three declared inputs from the pinned corpus commit. No held-out source, oracle or bug-report path was read by the reviewer; no additional corpus paths were inspected.
- R2 contains keras/8, keras/40, keras/30, keras/34, keras/11 in frozen order, each with three input digests. Metadata digests and recorded Python versions agree with the frozen manifest. Script/protocol/manifest digests and both raw PyPI response digests agree with their actual files. Source retrieval is bound by the script's `git show <recorded-sha>:<path>` and frozen metadata digest check; requirements/oracle bytes were not independently reread from the corpus by the reviewer.
- The current `AVAILABLE_PYTHONS` is 3.13, 3.12, 3.11, 3.10. All five recorded interpreters are 3.7.3. Four groups are Python-plus-exact-requirements-hash signatures, not four independent observations or qualified runnable environments.
- Stored official PyPI JSON for TensorFlow 1.13.2 has 15 distributions; 1.15.0 has 11. Every projected filename/type/digest/requires_python/yanked value matches the raw response. All are wheels with exact historical CPython ABIs (cp27 or cp33–cp37); none can intersect cp310–cp313 or an ABI3 tag. No source distributions occur. All requires_python fields are null and all yanked flags false, so the script's lack of filtering those fields does not change this census.
- Denominators are five development candidates, four manifest signatures, and two release metadata responses. R2 reports five unsupported recorded interpreters, zero release metadata errors, and zero project executions/product evaluations. These support a prerequisite blocker only; they establish neither recall, defect correctness, installability, nor impossibility of a separately authorized historical environment or port. Protocol lines 21–35 and the artifact interpretation retain these limits and leave E-02 acceptance open.

## Validation and changes

`.venv/bin/python -m ruff check scripts/corpus/development_preflight.py`: passed. Local JSON/hash/projection checks using the existing shared digest and packaging wheel parser: passed. These were artifact consistency checks, not a census rerun; no corpus execution, package installation, network call, paid/model call or remote write occurred in the review. Full pytest is outside this metadata-only review's prescribed validation scope.

`git diff --stat 1bc7b680e2790e6ef83b5de410c2e4270a961f45..04a2554`:

```text
 .../development-preflight-r1/invalid.json          |   1 +
 .../repository-holdout-v1/development-preflight.md |  43 +++++
 scripts/corpus/development_preflight.py            | 196 +++++++++++++++++++++
 3 files changed, 240 insertions(+)
```

At review time r2 outputs were untracked and inspected as produced evidence. The reviewer changed only this review document. Reused tools: `sha256_bytes`, existing `AVAILABLE_PYTHONS`, and `packaging.utils.parse_wheel_filename`; the measured script also reuses shared atomic/canonical JSON writers and `Requirement`/`cpython_tags`. New utilities: none. No second independent review requested.
