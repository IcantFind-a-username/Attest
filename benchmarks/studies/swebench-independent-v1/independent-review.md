# Independent metadata/split review

Reviewed baseline 4697d98, driver 4b58b3d, freeze 8ad0236. One read-only pass; no project source, gold/test/problem data, project execution, network or paid calls. Tracked files unchanged.

## Findings

- Low — `scripts/corpus/freeze_swebench_independent.py:78`: generated aliases omit `sklearn` and `scikit_learn`. The independent baseline audit explicitly included these spellings and found no substantive selected-repository exposure; therefore this does not invalidate these six selections. Retain the supplemental audit with the freeze rather than claiming the generated alias list was exhaustive.
- Limitation — `scripts/corpus/freeze_swebench_independent.py:51`: dataset-server pages are not requested at an immutable revision. Matching API head revisions before/after establishes observed head stability, not proof that the dataset-server cache represented that SHA. Projected metadata bytes and hashes support local replay of the actual freeze. Do not claim cryptographically established page-to-revision provenance.

## Independent results

Recomputed metadata identity set against baseline old split: all 500 identities match. Record matches metadata-access.json; metadata, driver, protocol and split SHA-256 bindings match. All selected rows are old held_out, created_at >= 2022-01-01 UTC, and first three under the specified SHA-256 ordering:

- astropy/astropy: pool 13; astropy__astropy-14369, astropy__astropy-13236, astropy__astropy-13398.
- scikit-learn/scikit-learn: pool 7; scikit-learn__scikit-learn-25232, scikit-learn__scikit-learn-25973, scikit-learn__scikit-learn-26323.

Baseline case-insensitive searches of tracked docs/benchmarks/scripts/DECISIONS covered astropy, scikit.learn and sklearn (including underscore variant). Astropy references are split membership, explicit not-built pilot exclusions (2026-09-02-e02-pilot.md:13-15), and explicit not-cloned/not-probed heldout records (2026-09-12-heldout-supported.md:31,218-219). Scikit-learn has these same administrative references plus two packaging forward-pair artifacts whose matching node is a requirement-name normalization parameter (`scikit-learn==1.0.1-scikit_learn==1.0.1`). That is packaging test metadata, not scikit-learn source investigation. No substantive prior exposure found within this audit scope.

Independently enumerated existing corpus .git metadata and read origin identity only: all 23 entries match clone-audit.json; no selected repository origin is present. No project tree file inspected. Absence cannot rule out removed clones, unrecorded earlier access, external human knowledge, or pretrained-model exposure.

Protocol correctly preserves the prior denominator, limits claims to exploratory contemporary sampling, prohibits product tuning, requires later direction/class qualification, paired hidden witnesses, blind semantic review and natural controls. Freeze is not a recall, precision, independence-from-pretraining, runtime eligibility or release result. Qualification and controls remain outstanding.

## Validation and tools

Read-only Python assertions passed for all metadata checks; git baseline alias searches and origin-metadata reconciliation passed. No full product gates claimed. Reused `attest.benchmark.artifacts.sha256_bytes`; no new reusable tools introduced. Standard json/datetime and read-only git used for independent verification.

Diff --stat: tracked diff empty; one private review report added. No code changes, commits, remote writes or spend. Review supports selected-repository eligibility under the declared scoped audit, subject to the recorded provenance limitation and preserving this alias supplement.
