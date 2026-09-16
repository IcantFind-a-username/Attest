# Authorized final remainder qualification study

Owner authorization, 2026-09-16: “我授权补样”, approving the separate remainder
proposal. Audit baseline ea73b72d4cde9086018183b633a8daebcde431b3. Product source
remains at gated f2560ce (source tree 3b45dcf49d5f3e540658c26c8b299ca34d1dd516),
default v5.1. Prior studies and their failed qualification results remain intact.

## Selection before new source or truth

Reuse the pinned SWE-bench Verified five-column metadata, revision
c104f840cc67f8b6eec6f759ebc8b2693d585d4a, Parquet checksum, prior split and date
cutoff. Admit only rows previously marked metadata-eligible in the committed
metadata-exposed-v1 freeze, excluding all its selected identities and every earlier
selected identity. This bounds the pool to at most 58 remaining rows from Django
and Matplotlib. Require prior inventory bytes to match the audit-baseline commit.
No new repository, date relaxation or replacement outside that pool.

Re-audit exact case IDs, base SHAs and repository/PR aliases against all tracked
baseline files except the original split, plus controller work records and corpus
summaries. Enumerate the existing WORK_DIRS and every non-symlink .attest/*-work
folder recursively for JSON/JSONL/Markdown/log records, and every top-level corpus
result.json/manifest.json/summary.json. Bound each record to 16 MB; uncertain
provenance refuses. Save paths and digests, not private contents. This is a scoped
record audit, not proof that shared repository source was never seen.

Only the case-holdout and metadata-exposed full freeze inventories, and the already
validated installation-only screen rows, may count as administrative references.
Previously selected identities remain excluded even when references are otherwise
administrative. Any other tracked/private-record match excludes. A later natural
parent/head matching any previously inspected/evaluated control or defect commit
also refuses during qualification, without replacement.

Freeze ALL surviving identities in SHA-256 order of
`attest-remainder-v1|repo|instance_id`. No repository quota or per-repository truncation.
Commit selection driver before invocation; commit the manifest before new source
or hidden-column access. One independent freeze review must clear concrete errors
first. Retain exclusions and shortfalls; no second batch or outcome-driven backfill.

## Qualification and fixed compatibility boundary

Use bounded source-history search inherited from case-holdout-v1: the first plausible
introducing change traced from the original failing behavior, not a search for a
product success. Require two product-blind semantic reviews, natural parent/head
and existing-contract violation; API introduction and reversed repair do not qualify.
Deduplicate natural pairs and same semantic defects across case identities.

Use the existing Python 3.10 compatibility recipe uniformly, with its recorded
compiler image and slim runtime digest: direct/build requirements and pip, pytest,
setuptools, wheel and numpy get creation-date latest_before upper bounds; original
requirement constraints remain binding. This is not an exact historical or full
transitive lock. Where pyproject declares no build-system requirements, let pip use
its existing implicit backend; do not invent a project-specific backend or pin.
Build each natural revision separately. Pure-Python wheels need no native addition;
native wheels use the existing strict transfer, preserving original source bytes.
Use declared runtime/test dependencies, not case-specific dependency repair.
Retain resolved freezes and require identical parent/head dependencies. One build
attempt per revision, 900 seconds; one runtime readiness check. No outcome-driven
fallback, alternate recipe, source repair or isolation relaxation. Tracked symlink
exports remain refused; known Matplotlib compatibility risk is retained, not hidden.

Original human tests must run unchanged on both natural revisions, three paired
parent PASS/head FAIL repeats, with exact identities, no errors/skips and recorded
fresh source-mounted execution. The full original test context may be overlaid
identically for oracle qualification only. Use the original project runner/node
format with existing secretless ContainerAdapter/Controller; unsupported node or
runner shapes refuse instead of being rewritten after results. Freeze the concrete
oracle invocation adapter before its first execution; no test search or repair.
No oracle overlay, patch, labels or problem statement goes to product review.

Before control-diff inspection, enumerate at most 256 nonmerge ancestors per selected
base, deduplicate per repository, and freeze SHA-256 order of
`attest-remainder-v1|control|repo|sha`. Inspect at most 20 per repo. Two blind reviews
must agree on natural documentation/test-only or semantic-preserving changes.
Exclude prior evaluated/inspected controls and defect-pair SHAs, retain all refusals;
do not replenish. Runtime failures stay in candidate/control attrition.

## Paid dispatch and stopping

Target six defects/six controls; minimum three/three across two repositories,
controls at least as numerous as defects. Below minimum: terminal qualification
report, no paid dispatch and no further expansion. Qualified cases follow frozen
rank, one per repository first, at most six. Freeze exact units, scoring, versions,
per-unit limits, cache policy and study cap before any model output. Product inputs
are fresh natural source trees without oracle overlays or hidden truth.

The same workflow must first demonstrate every report input class for free:
trials, lines, ledgers and logs, with nonempty-input assertions. Existing paid opt-in
and DEVSPEND's cumulative cap apply; no increase. Use p95 reservations, hard total
limits, durable precharge/checkpoints, per-call ledger and reconciliation. Refuse
if remaining funds cannot cover the preregistered minimum. No smaller substitute.

Report metadata-exposed case results, not untouched-repository generalization or
release readiness: independent counts, correctness, abstention, intervals where
defined, case-level gains/losses, attrition and exact fees. Finite control silence
is not universal zero FPR. Stop after the paid report, or the terminal qualification
shortfall. No new default, statistical policy, release, push or third-party writes.

## Visible provenance correction after independent freeze review

The initial producer included its active output directory in the input audit. Its
`freeze.log` was empty when hashed, then received the producer's final status line.
The original freeze remains unchanged. Exclude only `remainder-freeze-work` (this
freeze task's outputs) from future input enumeration; all prior work directories
remain inputs. `freeze-provenance.json` records the original digest, the retained
output digest and an explicitly reconstructed empty snapshot, not a contemporaneous
capture. The independent review reproduced no selection discrepancy. This correction
does not resample, read new source/truth, or qualify a defect.
