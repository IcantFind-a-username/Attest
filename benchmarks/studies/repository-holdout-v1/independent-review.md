# Independent repository-freeze review

Scope: one bounded data/document review of `repository-holdout-v1`, baseline
`58b3a6ca9c7bbc965004c7e74d207bce448c1d82`, freeze
`a3e62f9206629d0656ece192e16307c568d4a41a`, branch
`chore/freeze-repository-holdout`. No implementation changes or second review.

## Finding

**P2 — Ambiguous historical exclusion is classified as administrative exposure.**
`benchmarks/studies/repository-holdout-v1/exposure-audit-classified.json:1` marks
`tqdm` eligible with `administrative-only-in-declared-audit`, although its historical
`tqdm/9` exclusion is `missing_regression_test`. At historical importer commit
`1a8bffd345f1e3c1c4184fc845d928e38bb7df23`, `src/attest/benchmark/corpus.py:452`
raises that reason before patch access, but lines 476, 479, 483 and 485 also raise
the same reason after patch/test bytes are read at lines 464 and 472. Therefore the
reason alone does not establish the amendment's pre-patch condition. The frozen
five contain no such ambiguity. Preserve the existing audit; append a correction
classifying this unselected repository as unknown/excluded unless independent,
authorized evidence establishes the early branch. Removing tqdm from eligibility
was independently recomputed and leaves the five selected repositories, their
roles and all selected IDs unchanged. No extra unselected bug metadata was read.

## Verification evidence

- Shared `sha256_bytes` and `canonical_json_bytes`, invoked with
  `PYTHONPATH=src .venv/bin/python`, verified the protocol digest and all four JSON
  artifacts' canonical bytes. The initial attempt without PYTHONPATH failed to
  import Attest; the corrected invocation passed. Python was 3.12.2.
- Immutable `git show` at corpus revision
  `316b95e2353ecda832bad9b42f86fa7c2fcec8ac` verified all 25 selected `bug.info`
  byte hashes, buggy/fixed revision strings, nonidentical full 40-character SHAs,
  and all 17 normalized `project.info` hashes. Corpus HEAD matches the pin.
- Recomputed ascending SHA-256 order matches development Keras
  `8,40,30,34,11`; held-out spaCy `9,2,8,1,7`, Ansible `13,6,4,14,16`, HTTPie
  `2,1,5,4,3`, and thefuck `20,21,3,10,6`. Recomputed each project's exclusion
  counts and remaining ID list against the immutable baseline manifest.
- All 783 recorded baseline document digests match the declared stripped-byte
  normalization. A separate case-insensitive Git text search for the selected
  project names/aliases finds only the historical manifest in the baseline
  document/benchmark/script scope. Selected aliases do not overlap each other,
  historical manifest sources/cases, or recorded clone origins. Stored identity
  records group HTTPie's old slug with `httpie/cli` and report all five as non-forks.
- `metadata-access.json` discloses all selected metadata paths plus the Luigi
  format probe. The original mention-only audit and visible amendment remain
  committed before the freeze. `git diff --check baseline a3e62f9` passed.

## Claim limits and disposition

The selected pool is suitable for the stated candidate freeze, subject to the
append-only audit correction above. It is not a qualified evaluation population:
25 candidate defects, zero qualified defects, zero qualified controls, zero product
evaluations, dispatch disabled. The protocol correctly requires later independent
truth, faithful base/head construction, environment qualification, at least as
many qualified controls as defects, and reporting failures/abstentions. Metadata
SHAs are exact recorded identifiers; upstream object existence and ancestry were
not verified by reading held-out repositories. Four held-out repositories are not
20 statistically independent repositories, and no precision/recall/FPR result
or zero-FPR guarantee follows from this freeze.

Historical license/metadata exclusions precede gold patch and oracle reads for
the selected five in the inspected importer; this establishes that code-path
ordering, not absolute absence of undocumented human/model/source exposure.
Stored fork metadata was checked for internal consistency, not refreshed remotely.
This review read no held-out project source, gold patches, oracle scripts or bug
reports, ran no project code or model calls, and made no remote writes. Spend: $0.
Full product gates were not run, as this preparation changes no product behavior.

## Diff and reuse

Reviewed diff `git diff --stat baseline a3e62f9`: five files, 84 insertions.
Reviewer-owned output: this file only. Reused shared canonical JSON/digest helpers,
Git immutable tree/show/grep metadata and the historical importer. No new tools,
serialization/statistical helpers or product code. No review findings were fixed
by the reviewer; the controller owns the append-only correction and disposition.
