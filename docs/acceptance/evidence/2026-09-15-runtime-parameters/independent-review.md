# D-259 independent review — one bounded pass

Reviewed the working diff on `fix/runtime-parameter-binding` (HEAD during inspection
`652ff896d607d0843106691a7d2a00f8ca6b84e6`; task baseline
`f6900c4e410352b8536f13021a94fad167f4a0b2`). Read AGENTS.md and the frozen D-259
protocol. This reviewer owns this report and `reviewer/` only; implementation files
were not changed. No paid call, remote action, external corpus or full gate was run.

## Finding

**P2 — Population refusal omits the promised per-node report.**
`src/attest/review/contract_runtime.py:377-393` returns before constructing `nodes`
when any run skips or changes its parameter IDs. The protocol explicitly requires
reporting every node, including passing and refused ones. Raw JUnit is retained in
the encompassing driver record, but the interpreted verdict contains neither the
refused node identities nor the passing siblings. This also makes the per-node
results shape depend on whether the population passed admission.

Reproduced using the existing `parameter_changed_ids` and `parameter_skipped`
fixtures, existing shadow `measure`, and `LocalDevelopmentAdapter`:

```
PYTHONPATH="$PWD/src" .venv/bin/python .attest/runtime-parameter-work/reviewer/reproduce.py
```

Both cases completed four runs with `collected_count=2` in each run. The former
returned `defer: collected node identities differ`; the latter returned
`defer: nodes did not complete uniquely without skip or executor refusal`. Neither
verdict contains `nodes`. Full retained reproduction:
`.attest/runtime-parameter-work/reviewer/reproduction.json`.

Preserve fail-closed population admission, but report a per-run census/refusal
before the early return. Do not reinterpret a skipped or changed population as
admissible evidence. Add an assertion covering node retention on these existing
controls; the current parameter test checks `nodes` only for positive cases.

## Other inspection results and limits

No additional reproduced defect was found in the bounded pass. Node association
uses full identity sets and per-node original/observed parity; event order is not
used as identity. The single-node diagnostic API remains available; packet v2
is deliberately historical. Receipt eligibility remains false, with explicit
same-process shadow wording. Same-process forgery, hidden state and causal
sufficiency remain declared limitations, not new findings or approval blockers.
This review does not certify the implementation or claim empirical precision.

## Diff and reuse

Observed `git diff --stat` at review:

```
 scripts/corpus/runtime_contract_cases.py  |  61 ++++++----
 scripts/corpus/runtime_contract_shadow.py |   9 +-
 src/attest/review/_contract_observer.py   |  10 +-
 src/attest/review/contract_runtime.py     | 182 +++++++++++++++++++++---------
 tests/test_runtime_contract.py            |  55 ++++++++-
 5 files changed, 238 insertions(+), 79 deletions(-)
```

Reused: `build_case` (and its existing fixture git builder), `measure`/`run_site`,
`LocalDevelopmentAdapter`, the existing executor/controller path, and
`write_canonical_json`. Added only a narrow reviewer reproduction script, declared
before execution; no reusable utility or production implementation was added.
