# Independent metadata-exposed freeze review

Result: CLEAR for the bounded selection freeze. No blocking or nonblocking defect found.
Reviewed baseline `1a3fbb9bb6011051532bf52437ce020fc9aeb6dd`, committed driver/protocol
`508a446`, and freeze digest
`d03f220e8d41a156c24d47be4fc866dbd060c49b5fa4706efbb5851de69c48aa`.

## Evidence and exact scope

- Independently recomputed five input/file digests (driver, protocol, projected metadata,
  split, opaque Parquet bytes) and all 1,209 ignored-record digests; all match.
  Parquet was hashed as opaque bytes, never parsed. No hidden oracle columns or new
  external project source were read; no API, paid, remote mutation or driver rerun.
- Confirmed the complete 130-case contemporary held-out candidate inventory against
  projected metadata and split, and repeated baseline git grep for every candidate's
  exact instance, base SHA and repository/PR aliases. All tracked matches agree.
  Independently searched the frozen ignored records: every match set agrees.
  Six list-order differences reflect Path ordering versus string ordering only.
- Independently checked eligibility from recorded references and previous selections;
  both older selected lists remain excluded, with no previously selected case admitted.
  There are 77 eligible candidates; independent SHA-256 ordering produces the exact
  19 frozen selections: astropy 5, django 5, scikit-learn 4, matplotlib 5.
- Checked every permitted exception. Only the prior administrative inventory and exact
  schema-conforming installation-screen rows are allowed. Matching screen rows agree
  on identity/repository/base/date; no candidate alias occurs in the probe section.
  `scripts/corpus/heldout_v2.py:95-156` confirms screen reads only setup.py, setup.cfg,
  pyproject.toml. `_instances` at lines 72-78 loads complete dataset records first.
- No selected case has a known product run, probe, semantic review, development or
  previous-selection reference within the stipulated audit. Prior screen exposure is
  admitted intentionally; this is not an untouched holdout or proof of global absence
  of exposure. Audit coverage is the protocol's baseline tracked files and named local
  record directories/top-level corpus summaries; no broader claim is cleared.

Qualification, natural-control freezing, witnesses, semantic review, paid units and
execution are outside this review and remain their own gates. The 19 selected inputs
are not qualified defects/controls. Clearance permits the next authorized bounded
qualification step, not paid dispatch or release.

## Review mechanics

Read-only checks used `.venv/bin/python` with `PYTHONPATH=src` and `git grep`.
Initial check attempts needed the import path and match-set ordering corrected;
subsequent checks established the results above. No product edits or tests were needed.
Reused `attest.benchmark.artifacts.sha256_bytes`; no new tools introduced.
Owned output only: `.attest/metadata-exposed-work/freeze-review.md` (ignored).
Tracked diff --stat from this reviewer: empty.
