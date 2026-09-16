# D-257 user-directed contract context correctness
Baseline: 5dc801e9d0a7872228c298ad7d0422e64a70ac19; branch fix/contract-context.
Scope: reproduce implicit-context attribution errors, refuse unsupported local context,
free synthetic/product replay, one independent boundary review, full gate.
No paid calls, remote changes, default intent changes, selection fix or release.
Dependencies: D-255 report/manifests; D-256 final gate at a7d51cc (source tree unchanged at baseline).
Root owns src/attest/review/{contracts,contract_context}.py, tests/test_contract_context.py,
scripts/corpus/{binding_cases,context_cases,frozen_e2e}.py, task evidence and final docs.
Reviewer owns only .attest/context-work/review.md and reviewer fixture directory.
Baseline targeted suite: 90 passed (tests/test_contract_binding.py, test_contract_probes.py).
RED: module_autouse reader admitted True and kernel accepted a declared reasonable change;
original test node passes on both revisions. Pre-fix driver v2 has 5 such cases of 6;
ancestor conftest is an execution refusal, not a false positive.
Gates: G-CODE-001; no kernel schema or evidence pricing changes. INV-CERT-001,
INV-TRUTH-001 and exact claim binding remain mandatory.
