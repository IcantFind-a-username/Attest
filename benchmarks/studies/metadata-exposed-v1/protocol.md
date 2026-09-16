# Metadata-exposed study: frozen selection protocol

Owner approved the exact decision package with “允许” on 2026-09-16.
Audit baseline: 1a3fbb9bb6011051532bf52437ce020fc9aeb6dd.
Product source remains at gated 0b6d3b180897126b8bbb7ed65f1d4831102ac697.
The prior studies, failures and denominators remain unchanged.

## Selection before truth access

Reuse the pinned five-column metadata, Parquet digest and prior held-out split
from case-holdout-v1. Only cases created on/after 2022-01-01 are candidates.
Audit exact IDs, base SHAs and repository/PR aliases against tracked files at the
audit baseline, prior controller records, case-holdout-work records and top-level
corpus summaries. Exclude uncertain matches and every prior selected identity.
Permit exactly two known administrative reference types:

1. The preceding case-holdout-v1/freeze.json metadata inventory. Its selected
   identities are still excluded. Inventory inclusion alone did not access truth.
2. An exact matching screen row in the historical heldout-supported-probe.json,
   with only the documented identity/declaration fields and no matching probe
   section reference. Its producer heldout_v2.cmd_screen reads only setup.py,
   setup.cfg and pyproject.toml after loading dataset records. Hidden columns may
   have been loaded then; this is not an untouched holdout. All other references
   continue to exclude the case.

Order repositories by SHA-256 of attest-metadata-exposed-v1|<repo>; first four
with at least three eligible cases. Order each repository's cases by SHA-256 of
attest-metadata-exposed-v1|<repo>|<instance_id>; take up to five. Maximum twenty,
no backfill or second batch. Commit driver before execution and freeze before
new source/truth access. One independent freeze review must clear errors first.
Report as metadata-exposed, previously unevaluated within the audited records.

## Qualification and dispatch

Inherit case-holdout-v1's bounded introducing-history search, two product-blind
semantic reviews, unchanged original tests, three repeated parent PASS / head
FAIL witnesses under identical execution, no errors/skips or repair reversal.
Deduplicate exact natural pairs and semantic defects. Keep every runtime refusal.
No outcome-driven source/test/environment repair or isolation relaxation.
Controls use up to 256 nonmerge ancestors per selected base, union per repository,
ordered by SHA-256 of attest-metadata-exposed-v1|control|<repo>|<sha>. Freeze before
diff inspection; inspect at most twenty per repository, no backfill. Two blind
reviews must agree; exclude defect-pair or previously evaluated SHAs.

Target six defects and six controls, minimum three plus three across two
repositories, controls at least as numerous as defects. Below minimum: retain
shortfall, no paid dispatch. Qualified rows follow frozen rank, one per eligible
repository first. Freeze exact paid units, scoring and budget before execution.
The same-workflow free artifact smoke must cover every report input class.
Paid opt-in is already granted, within DEVSPEND's existing headroom only, with
p95 reservations, hard remaining-budget control, precharge, durable per-call
checkpoints and reconciliation. No default changes, push, release or cap increase.
Report independent counts, correctness, abstention, intervals, gained/lost lists,
attrition and costs. Finite silence is not universal zero FPR. Stop after report.
