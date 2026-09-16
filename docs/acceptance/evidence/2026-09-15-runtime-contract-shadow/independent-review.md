# D-258 independent review — one bounded pass

Reviewed working-tree versions of `contract_runtime.py`, `_contract_observer.py`,
`runtime_contract_shadow.py`, `runtime_contract_cases.py`, and `test_runtime_contract.py`
on `feature/runtime-contract-shadow`, HEAD `89723b029ee4f843017b682c212297417ce51816`,
against baseline `9458278479447e668e7b3e7e51bade35e5c83831` and the frozen protocol.
No source edits, paid calls, remote actions, full gate, or second review pass.

## Findings

### P2 — Concrete input types collapse during pair comparison

Location: `src/attest/review/contract_runtime.py:302-304`, with untagged primitive
snapshots from `_contract_observer.py:28-35`.

Python structural equality treats `True == 1 == 1.0`. Consequently, comparing the
snapshot dictionaries with `!=` does not enforce identical concrete inputs, receiver
state, or expectations. This produces an ordinary false shadow binding without forging
any observations.

Reproduced using the existing fixture builder, `measure`, `execute_repro`, and local
adapter. The assertion is unchanged: `assert parse(VALUE) == "bool"`. Base sets
`VALUE = True`; head sets `VALUE = 1`. Base `parse` returns `type(value).__name__`;
head appends an empty string to that expression, preserving function behavior for every
input. All four original/overlay runs finish normally. The driver returns
`status="binding_observed"`, although the failure comes from changed input. The actual
packets contain base `args.items=[true]` and head `args.items=[1]`.

Suggested resolution: compare recursively typed snapshot values (including numeric
kinds), or use an existing serialization facility that preserves these type distinctions.
Apply the same exactness to returned/left consistency. Add the changed-input case.

### P2 — Impossible binding-field shapes are admitted as observations

Location: `src/attest/review/contract_runtime.py:217-225`.

The host checks field presence but never validates snapshot shapes. In particular,
`args=null` and `kwargs=null` cannot be emitted by the recorder's successful snapshot of
`*args` and `**kwargs`. Replacing all six binding fields with JSON null in both observed
packets still returns `status="binding_observed"`. This lets malformed/incomplete
packets supply binding despite the protocol's explicit malformed-record refusal rule.

Reproduced by taking the real completed runs above, replacing only packet fields
`args`, `kwargs`, `receiver`, `expected`, `returned`, and `left` with null, retaining
source/site/callee identities, Boolean flags, outcomes and expected test digests, then
calling `interpret_pair`. No execution result or source identity was fabricated.

Suggested resolution: validate the bounded snapshot grammar and the distinct required
argument, keyword, and receiver shapes before admitting an event; reject missing/null
argument containers. This is ordinary format validation, not a demand for a new trust
boundary or protection against an in-process forger.

## Reproduction and validation

- Acceptance command: `PYTHONPATH=$PWD/src .venv/bin/python -m pytest tests/test_runtime_contract.py -q -p no:cacheprovider` — passed, 13 tests.
- Reproduction script: `.attest/runtime-shadow-work/reviewer/reproduce.py`.
- Reproduction command: `PYTHONPATH=$PWD/src .venv/bin/python .attest/runtime-shadow-work/reviewer/reproduce.py`.
- Retained original/overlay trees and protocol outputs:
  `.attest/runtime-shadow-work/reviewer/fixtures/type-runs/`.
- Both reproductions print `binding_observed`, `receipt_eligible=false`, and
  `trust="same-process-shadow"`.
- The reproduction script allocates fresh paths; its existing output directory must not
  be reused for another run. The controller can translate these cases into focused tests.

## Limits and scope observations

Covered ordinary fixture retention, discovery/instrumentation, snapshots, packet parsing,
original/overlay outcomes, and source/environment consistency by code inspection and the
focused suite. Empty selected input remains explicit, unsupported assertions remain
refusals, and multiple runtime observations refuse. These observations are not an
exhaustive unsupported-construct or adversarial matrix. Same-process forgery, hidden
function/global state, and stronger causal proof remain declared promotion limitations;
no production certificate or security-boundary defect is claimed here. Final container
measurements, fixes, and the final integration gate are controller-owned.

## Diff and tool reuse

`git diff 9458278 --stat` at review time:

```
 .../2026-09-15-runtime-contract-shadow/protocol.md |  65 +++++
 scripts/corpus/runtime_contract_cases.py           |  50 ++++
 scripts/corpus/runtime_contract_shadow.py          | 249 +++++++++++++++++
 src/attest/review/_contract_observer.py            | 144 ++++++++++
 src/attest/review/contract_runtime.py              | 310 +++++++++++++++++++++
 5 files changed, 818 insertions(+)
```

The 132-line `tests/test_runtime_contract.py` was untracked and is not included in that
Git stat. Reviewer writes are only this report and the authorized ignored reproduction
subdirectory. Reused inventory: fixture `build_case`/`_git`; AST index and `_owners`
through discovery; existing `measure`/`run_site`, `execute_repro`, Controller and local
adapter; existing source digests and canonical persistence in the driver. Added no
production/shared utility. The reproduction script is a bounded test harness only.
