# Remainder adapter independent review

Reviewed 2026-09-16 at `38ffd11b40f50afaaac23d3737a47ef4546dea23`.
Scope: committed remainder qualification reconciliation and uncommitted compatible
build adapter diff; source reviews were in progress. No new corpus source, oracle
payload or product result was inspected. No builds, paid calls or remote writes.

## Finding

- **Medium — current inspected but refused defect pairs can enter controls**
  (`scripts/corpus/remainder_qualification.py:150`, consumed at lines 156–168).
  The `defects` exclusion set is made only from accepted `pairs`. A pair inspected
  by a semantic reviewer but refused because the two reviewers disagree is absent
  from this set. If its parent/head also appears in an agreed control row and is
  absent from historical `prior`, the code sets `source_admitted=True`.
  This conflicts with the protocol's exclusion of defect-pair SHAs; refusal must
  not erase inspection provenance. Build a separate current inspected-pair SHA
  set from both semantic reviews, retaining valid nonempty parent/head identities
  irrespective of acceptance, and use it in control overlap checks. Keep the
  accepted `pairs` list unchanged. This is a static branch reproduction, not a
  claim that a particular live control currently overlaps.

## Checks and limits

- Ordered identity equality binds every frozen case row and every inspected
  control row in both reviews; freeze/protocol and control inventory digests bind
  inputs, and pending/not_reviewed classes refuse. No hardcoded case-count shortcut.
- Historical accepted pairs and inspected control heads are gathered from prior
  study artifacts. Existing known semantic/control review folders additionally
  contribute cited commit prefixes, including refused pairs. This review did not
  independently prove that those folders exhaust every historical source record.
- Natural defect pairs require an exact single-parent relationship. Semantic
  deduplication and runtime qualification are explicitly pending; output counts
  remain zero. Build success makes no product qualification claim.
- Existing SWE-bench and natural-pair branches preserve their previous defaults
  and population checks. Remainder uses a dedicated fresh output directory and
  a digest-pinned compiler image; cases reuse `natural_cases` identity, order,
  side, creation-time and digest checks.
- Absent/empty build requirements use the original pip invocation without adding
  a backend. Declared requirements retain nonempty isolated metadata enforcement;
  legacy builds retain verbose logs and outer freezes and may retain an empty
  isolated archive. Date upper bounds, original requirements, symlink refusal,
  build timeout and one attempt per revision remain in place.
- No execution isolation adapter was changed. This review does not certify the
  existing builder as the later secretless runtime boundary.
- Read-only schema check: both current control review files had 40 rows and no
  null parent identities. No source/oracle content was printed. No live source
  reconciler execution or measurement was performed.

## Completion

Owned file: this private report only. Diff stat: one added report file; tracked
implementation diff belongs to the controller. Reused helpers inspected:
`sha256_bytes`, `write_canonical_json`, `natural_cases`, `archive`,
`direct_dependencies`, `latest_before`. Added tools: none.
