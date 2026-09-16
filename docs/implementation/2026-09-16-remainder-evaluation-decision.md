# Decision: one final frozen remainder qualification batch

Status: proposed; not authorized or selected by this document.
Baseline: c67a9cf31bed8127e834bb3929876024957075af.

## Decision requested

**Authorize a separate evaluation using all remaining eligible cases in the
already pinned metadata pool? Recommended: yes, within the limits below.**
This changes the sample boundary. It does not request temporary-directory access,
another paid opt-in, a higher spend cap, a new default, push or release authority.
If declined, retain the named population blocker and make no paid calls.

D-280 established one development original-test witness. The other known source
pair remains unbuildable, so even repairing it cannot reach the existing minimum.
D-276 explicitly says “Maximum twenty, no backfill or second batch”; AGENTS §16
reserves “outcome-dependent sample/exclusion/retry changes” to the owner. This
proposal preserves D-276 as a failed study rather than silently enlarging it.

## Fixed scope if approved

- Use only the same pinned SWE-bench Verified metadata and existing held-out split.
  The prior freeze has 77 metadata-eligible rows, of which 19 were selected: at most
  58 remain (Django and Matplotlib), before a fresh exposure/overlap audit. This is
  metadata arithmetic, not a new qualification result. Do not add repositories,
  change the date cutoff or replenish cases lost in the audit.
- Before reading new source/truth, audit all subsequent study/control/probe records;
  exclude previously selected/evaluated/development cases, control overlap and
  uncertain provenance. Freeze **all** remaining eligible identities at once,
  ordered by SHA-256 of `attest-remainder-v1|repo|instance_id`. Commit the driver,
  exact manifest, compatibility recipe and protocol before qualification. No second
  batch or outcome-dependent replacement.
- Keep bounded history search, two product-blind semantic reviews, original-human-
  test natural parent PASS/head FAIL three times, unchanged test bytes, independent
  reasonable-change controls, and all failures/abstentions. Freeze compatibility
  rules before runs; no per-case dependency retries, isolation relaxation or source
  repair to produce a witness. Known Matplotlib export/build compatibility is a
  feasibility risk, not grounds to erase failed cases or promise success.
- Keep the target six defects/six controls and minimum three/three across two repos.
  Freeze exact ranked paid units and scoring before model output, with no oracle
  tests/overlays or hidden truth supplied to product review. Demonstrate the same
  workflow's complete artifact collection free before paid dispatch.
- Existing paid opt-in applies only within DEVSPEND's unchanged $150 cap and
  currently $4.542889 headroom. Use existing p95 reservations, hard cost limits,
  durable precharge/checkpoints and reconciliation. If the preregistered minimum
  cannot fit or qualify, report the shortfall; do not charge a smaller substitute.
- Report this as metadata-exposed case evaluation, not untouched repositories or
  a release gate. Keep prior studies and attrition separate, count independent cases,
  report intervals/abstention and finite control uncertainty. Stop after the paid
  report, or return the terminal qualification shortfall without another expansion.

No broader architecture or release decision is bundled here. Evidence:
[original-test witness](../acceptance/2026-09-16-natural-pair-original-tests.md),
[failed frozen study](../acceptance/2026-09-16-metadata-exposed-qualification.md),
[existing sampling restriction](../../benchmarks/studies/metadata-exposed-v1/protocol.md).
