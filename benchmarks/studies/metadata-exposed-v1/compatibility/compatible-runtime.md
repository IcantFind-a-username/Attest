# Authorized natural-pair build compatibility diagnostic

Owner approval “允许” follows the proposal to address historical build compatibility.
Baseline 4df5ef8458fae0900545037bbac7cf52bc0d51f9. This is a separate free development
diagnostic, not a retry that changes D-276 or its held-out qualification result.
The two already inspected semantic pairs are now development inputs for this work.
No additional sample, paid call, product default or isolation policy is authorized here.

## Four immutable builds

Use cases.json, bound to the independently reviewed natural-pair record. Build each
parent and head separately, in frozen pair order, parent then head. Do not share
native artifacts across revisions. Verify every identity against that pair record.

Reuse the existing swebench_compatible_build.py algorithm with --study natural-pairs:
compiler-bearing python:3.10-bookworm, resolved image digest retained; direct/build
package names plus pip/setuptools/wheel/pytest/numpy get PyPI latest_before upper
bounds at the original SWE-bench case creation timestamp. That date is the same
for both sides, not the introducing commit date. This is a compatibility recipe,
not reconstruction of an exact historical environment or a complete transitive lock.
Original requirement constraints and markers remain binding; no unpinned fallback,
per-case pins, source changes or outcome-driven retry. Missing build metadata refuses.
Python 3.10 is the existing diagnostic's fixed interpreter, not a claim that every
historical revision declared support for it.

Reject tracked symlinks before archive extraction. Builder receives only exported
source and constraints, with no credentials, SSH or host sockets. Dependency download
is allowed during image build. One attempt per revision, up to 900 seconds. Preserve
all failures, resolved outer and isolated build metadata, logs, image and wheel digests.
Commit driver/protocol before invocation and obtain one independent review of the
new study adapter before execution. Do not rerun the already completed six-case study.

## Boundaries

The first deliverable is the four-build feasibility record. A wheel build is neither
a source-mounted import nor an original-test witness, receipt, precision or recall.
Only if builds succeed may a separately frozen runtime step reuse the existing
reviewed wheel-transfer tool, preserving tracked bytes and revision identity.
Original paired human tests and independent controls still remain requirements.
No favorable build can supply D-276's missing third defect or amend its sample floor.
No paid dispatch follows from this diagnostic. Existing paid opt-in/cap remain valid
for a qualified, preregistered evaluation, whose report is still the long-task objective.
