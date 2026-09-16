# Owner decision: a separate case-held-out regression study

**Status: proposed, not authorized or executed.** This is one bounded decision
package under AGENTS §10, not a new implementation order or a replacement of
either failed frozen population. Product baseline: `0b6d3b1`.

## Evidence and blocked measurement

The local code gate passes: 2,563 tests, no failures/errors/skips, 93.42%
certification/execution coverage. The six-case SWE-bench study still has zero
qualified natural-forward defects and zero controls. Three cases cannot execute
under the current product pytest arguments. Among the three runtime-ready cases,
one adds a capability and two have no qualified previously-working parent/head
pair. Therefore the requested independent paid regression evaluation cannot be
taken using the current qualified population. Paying for those rows would not
produce that measurement. See the [evidence](../acceptance/2026-09-16-swebench-original-oracles.md).

## One yes/no decision

**Approve a separate study of unused cases from previously encountered repositories?**
Recommendation: yes, with the limits below. If not approved, stop at this report;
do not change the old sample, reduce its minimum or buy an ineligible evaluation.

- Source is the already pinned SWE-bench Verified dataset. Use its prior-held-out
  split and contemporary date rule (created at or after 2022-01-01). Exclude every
  case with recorded development, execution, semantic review or uncertain exposure,
  including all six current cases. Retain the audit and all exclusions. Repository
  exposure alone would no longer exclude an otherwise unused case: report this
  as **case-held-out, not repository-held-out** evidence. It cannot establish
  generalization to wholly unseen repositories or a 1.0 release gate.
- Before reading additional project source or hidden truth, commit the audit,
  selection and protocol. Order eligible repositories by SHA-256 of
  `attest-case-holdout-v1|<repo>`, take the first four with at least five eligible
  cases, then take five cases per repository ordered by the same seed plus
  `|<instance_id>`. Maximum 20 candidates; retain any shortfall, no backfilling
  after outcomes. No new dataset or external local checkout is introduced.
- Qualify natural introducing parent/head pairs with unchanged human tests and
  two product-blind semantic reviews. A repair reversal or new capability is
  ineligible. Preserve all runtime refusals and semantic exclusions. Use the
  current product runtime; no outcome-driven environment or product repairs.
- Freeze a deterministic natural-change control protocol before control source
  inspection. Keep the existing minimum of three independent defects plus three
  controls across at least two repositories, target six plus six. No paid run
  below the minimum; no unbounded sample expansion if qualification fails.
- Freeze product code/defaults, exact scoring, budgets and cache state. Complete
  the same-workflow free artifact smoke before paid execution. Existing paid
  opt-in applies only within DEVSPEND's reconciled remaining cap; no cap increase.
  Preserve receipts, abstentions, semantic outcomes, gained/lost cases and costs.
  Produce the paid report and stop if all prerequisites can be met.

This decision is needed because AGENTS §16 reserves “outcome-dependent
sample/exclusion/retry changes” to the owner. The proposal changes the exclusion
rule for a **new** study after the earlier populations failed; it does not silently
amend either old preregistration. No permission to modify certification, isolation,
publication policy, product defaults or remote repositories is requested.

## Owner authorization — 2026-09-16

The owner explicitly approved this package and continued long-task execution:
“我都批准，这次长任务我都批准，快做”. The original proposed-state text above
is retained as history. Execution now follows
[the committed study protocol](../../benchmarks/studies/case-holdout-v1/protocol.md),
within the existing spend cap and report-then-stop boundary. No repeat approval
is needed for steps inside that scope.
