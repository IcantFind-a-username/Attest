# Original oracle input freeze

E-02 prerequisite, baseline `4c3b4fa`. The source-mounted compatibility experiment
has three runtime-ready scikit-learn rows; Astropy's three rows remain explicitly
unqualified. The product source/defaults are unchanged. This step prepares the
original human oracle inputs, not product proposals, detection results or controls.

Before opening hidden values, commit the reader. Require the existing immutable
Parquet digest to match D-269's pinned metadata check, and require the completed
runtime record to contain all six original IDs/revisions. Only select rows whose
runtime_ready field is true; retain the other IDs as not accessed. Read original
patch, test_patch, FAIL_TO_PASS and PASS_TO_PASS alongside identity columns.
Filter to selected IDs in Arrow; do not expose other cases or problem statements.

Save selected original rows in a fresh ignored oracle-only directory, mode 0700,
with files mode 0600. Public metadata contains identities, digests and node counts,
not patch/test contents or issue text. Product discovery may not read this directory.
One independent reader/provenance review and static/artifact checks are required.
No paid call, project code execution, patch application or product change here.

The next qualification must use unchanged original test nodes and identical test
bytes on both sides. A repair that changes native source needs its own freshly
built fixed artifacts; never reuse buggy native output on the repaired side.
Prefer an exact upstream repair revision and verify it against the frozen patch.
An oracle witness establishes repair discrimination only: natural forward-pair
direction, blind semantic review and independent controls remain separate gates.
No replay or model trial is authorized by a nonempty node list alone.
