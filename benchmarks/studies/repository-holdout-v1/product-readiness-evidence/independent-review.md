# Independent product-path smoke artifact review

Scope: one read-only pass over measured SHA `19bb9c4`, baseline `3d91427`, branch
`chore/product-path-readiness`; committed preregistration, unchanged
`scripts/corpus/frozen_e2e.py`, two p1 raw records, previous selection records,
and controller's `offline-verification.json`. No source execution, network, model calls,
target mutation, or held-out evaluation performed by this reviewer.

## Findings

No concrete severity-ranked defect found in the committed preregistration or observed
execution records. This is an artifact consistency review, not a product security review.
The final result report was not yet present and is outside this pass.

## Verified observations and reporting limits

- Selection exactly matches first qualifying rows in recorded file order:
  `forty-f2-S.jsonl` zero-based row 2, `itsdangerous-boundary-07--forward`;
  `controls-f3-S.jsonl` row 1, `mahmoud/boltons#481`.
  These outcome-selected fixtures cannot support independent precision/recall/FPR claims.
- Driver is unchanged against baseline. `review()` constructs `FrozenProvider` and passes
  it to `run_review`; settings are arm S, intent v5.1, K=5, simulated budget $1,
  value notes enabled, gate notes/shadow disabled, and auto-tightening disabled.
  They do not establish factory configuration equivalence.
- itsdangerous: base `672971d66a2ef9f85151e53283113f33d642dabd`, head
  `05063143a050ce49fee05b8c7f3681895547b921`; 5 proposal calls, 1 served frozen
  probe, 1 actual differential, 1 accepted receipt and publication `ddb02ec1f9`.
  Elapsed 10.1s; simulated charge $0.032519.
- boltons: base `8bb31ba90e574daddbf0d7a2dc658398dc141e38`, head
  `1216b467c10b852d08aa6895c80b6b9ec8f990d8`; 5 proposal calls, 5 probe calls,
  4 served frozen probes. Five verification rows mean FOUR actual differentials and
  ONE generation refusal with empty run evidence. Another candidate was below the
  verification cap and never executed. Four differentials were deferred for intended
  behavior changes; no receipt/publication. Elapsed 19.0s; simulated charge $0.126263.
- Each actual differential has 3 probe, 1 screen, 1 collect, 3 head and 3 base records.
  Executed cases' certification rows report `linux-container-v1`. The boltons
  `local_development_best_effort` row belongs to the skipped below-cap candidate;
  it is not evidence of an executed fallback. Both protocol-refusal counters are zero;
  that counter specifically tests unsafe-name refusal and is not a general refusal count.
- Fidelity matches recorded eligible `(unit, symbol, cluster_size)` tuples (1 and 6
  respectively), not original natural-language discovery or all original candidates.
  Frozen provider provenance remains necessary even where probe rows say source=model.
- Controller retained an `AcceptedReceipt` verification with `require_seal=true`,
  receipt digest `a7751952932aa1a552337b1d5352566f903fcf21f1e6cc05be0a13b0eeb533e8`,
  manifest digest `663c46883253dd9431141ceb95ce1a904fcde4a82fa137f40be39dcc9376fc6a`.
  Reviewer inspected this result but did not independently rerun its cryptographic check.
- Actual model API spend is $0; frozen charges total $0.158782 and are simulated only.
  Silent selected control is smoke behavior, not a correctness or FPR estimate.

## Changes and reuse

Reviewed implementation diff stat: 1 file changed, 36 insertions (preregistration only).
Reviewer owns only this ignored review artifact; tracked diff added by reviewer: zero.
Reused existing driver/provider and retained offline-verifier result for interpretation.
No new shared tools or helpers introduced; ad-hoc JSON inspection only, no new measurement.
