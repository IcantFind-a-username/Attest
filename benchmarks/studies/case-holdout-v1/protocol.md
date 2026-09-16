# Authorized case-held-out natural regression study

Owner authorization, 2026-09-16: “我都批准，这次长任务我都批准，快做”.
This approves the separate decision package committed at `2a15d6b`. Baseline
audit SHA: `2a15d6b9354b61b028b0799cdaa6158936fbdc36`; product SHA: `0b6d3b1`.
Neither previous failed population changes. No product/default/security change,
remote write, release or spend-cap increase is authorized by this protocol.

## Freeze before additional source or truth access

Reuse the five-column metadata projection of the already pinned SWE-bench Verified
revision `c104f840cc67f8b6eec6f759ebc8b2693d585d4a`. Require its recorded digest,
the immutable Parquet digest and the prior split digest; require exactly the same
500 identities, unique 40-character base SHAs and disjoint dev/held-out identities.
Do not read hidden Parquet columns during selection.

Only prior-held-out rows created on/after 2022-01-01 are candidates. Audit exact
instance IDs, base SHAs and repository/PR-ID aliases against all baseline tracked
files except the administrative 500-row split. Audit retained controller work
records and top-level corpus summaries too; never open project checkouts for this
audit. Any substantive or uncertain match excludes the case. All six earlier
SWE-bench cases are excluded explicitly. Save references and digests, not private
record contents. This is a scoped exposure audit, not a proof of universal novelty.

Previously encountered repositories are allowed. Order repositories by SHA-256 of
`attest-case-holdout-v1|<repo>`; take the first four with at least five eligible rows.
Within each, order by SHA-256 of `attest-case-holdout-v1|<repo>|<instance_id>` and take
five. Maximum 20; retain a shortfall without replacement. Commit the resulting
audit and selection before source/truth access. One independent freeze review
must clear concrete defects before qualification. This is case-held-out evidence,
not repository-held-out generalization or a 1.0 release result.

## Qualification, fixed environment and controls

Keep product source frozen. First establish a plausible natural introducing
parent/head pair by source history and unchanged original human tests. Two
product-blind semantic reviews must confirm existing-contract violation and
direction; reversal of a repair and addition of an API are ineligible. Retain
each exclusion. Bound history inspection to the first introducing change traced
from the original failing behavior; do not search until a product certifies.

Use the current product runtime and its isolation unchanged. No outcome-driven
test/environment repair, test rewriting, host fallback or admission relaxation.
Original human tests must pass on parent and fail on introducing head, under the
same command, exact test bytes and environment, with executed identities and no
errors/skips. Repeat each qualified pair three times. Runtime refusal stays in
the candidate denominator. Model inputs never receive oracle patches/tests,
hidden labels, problem statements or fix messages.

Before inspecting control changes, enumerate up to 256 non-merge ancestors of
each selected frozen base. Deduplicate exact commits per repository and order by
SHA-256 of `attest-case-holdout-v1|control|<repo>|<sha>`. Freeze that ordered list.
Inspect at most the first 20 per repository, in order. Admit only independent
natural documentation/test-only or semantic-preserving refactor changes with two
blind semantic reviews; retain every refusal, never backfill outside the list.
No model outcome informs control selection. Exclude any defect-pair SHA or
previously evaluated commit. Pair each admitted control with its real parent.

## Paid dispatch and stopping boundary

Target six independent defects plus six controls; minimum three plus three across
at least two repositories, with at least as many controls as defects. If fewer
qualify, report the full attrition and no paid dispatch. No automatic expansion.
Order qualified cases by their original frozen rank; take at most six, allocating
one per qualified repository first. Controls follow frozen rank in the same
repositories. Freeze exact units, scoring, versions, per-unit limits, p95 cost
reservation, fresh-cache policy and a total study cap within DEVSPEND headroom.
Prove every report input/artifact class with the same workflow's free smoke.
Existing paid opt-in then permits dispatch with precharge, per-call checkpoint
and spend ledger. Ambiguous calls remain charged/reserved pending reconciliation.

Report independent-case counts, semantic correctness, recall/precision where
defined, abstentions, gained/lost cases, cost, runtime/source-population attrition
and finite-control uncertainty. DEFER is not a true negative. Deliver the paid
report and stop if prerequisites are met; otherwise retain the bounded failure.
