# Independent case-held-out freeze review — 2026-09-16

Reviewed baseline `e90ce10af597f33378809aa90e3e153297e1a365`, branch
`chore/case-heldout-study`; audit baseline `2a15d6b9354b61b028b0799cdaa6158936fbdc36`.
Freeze SHA-256: `b65d227fcd124b0642f1556d345c94159cf87f992ccdcede050b24725ca05d53`.
Scope: one read-only static/metadata review; no source qualification, corpus execution,
provider calls, remote writes, secrets or new source/hidden-column inspection.

## Finding

**P2 — protocol declares a uniqueness invariant the pinned population does not satisfy.**
`benchmarks/studies/case-holdout-v1/protocol.md:14` requires unique 40-character
base SHAs, whereas `scripts/corpus/freeze_case_holdout.py:43–48` only checks format.
The pinned metadata has 500 unique instance IDs and 499 distinct base commits:
`django__django-15268` and `django__django-15278` share
`0ab58c120939093fea90822f376e1866fc714d1f`.
Reproduction: parse the existing five-column metadata JSON and group instance IDs by
`base_commit`; the above group has size two. Neither row is selected, so this does
not change the actual ten-case selection or require replacement. Repair the normative
wording to require unique instance IDs and valid immutable base SHAs; explicitly retain
shared-base metadata and enforce independence on qualified natural parent/head pairs.
Do not reject or substitute the original pinned dataset to make this check pass.
Freeze clearance is conditional on resolving this concrete document/code mismatch.

## Verified

- Recorded driver, protocol, metadata, split and immutable Parquet SHA-256 values match
  current bytes. Parquet was hashed only; no hidden columns were parsed or shown.
- Projection contains exactly instance_id, repo, base_commit, created_at and version.
- Split has 99 development and 401 held-out IDs, no overlap. All ten selected rows are
  prior-held-out and meet the contemporary date rule. All six former cases are absent.
- 130 contemporary held-out candidates, 38 eligible. Only astropy (10 eligible) and
  matplotlib (24) meet the five-case floor; scikit-learn has four. Hash ordering produces
  exactly the frozen ten rows. The twenty-case maximum is not backfilled.
- Independently repeated selected-row fixed-string baseline exposure searches returned
  no matches, with the administrative split excluded. All 1,197 retained record digests
  match. The scope is explicitly limited to recorded exposure; universal novelty is not
  claimed. No additional selected-case source or truth was accessed by this reviewer.
- The driver reuses `sha256_bytes` and `write_canonical_json`; it has no paid/execution
  dispatch path. No previous population is changed. Qualification counts stay zero.

## Handoff

`git diff --stat`: empty; zero tracked files changed by reviewer. Only this ignored
review artifact was written. Existing helper reuse: inspected canonical JSON/atomic
writer and SHA-256 helper calls; no helper implementations added. New tools: none.
Validation used static reading, Git fixed-string search, and standard-library read-only
metadata/hash assertions. No full pytest was run, as required by review scope.
