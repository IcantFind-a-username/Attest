# Independent single-pass review — remainder original tests

Baseline: eeb587c; branch: fix/remainder-original-tests; reviewed uncommitted diff.
Scope: scripts/corpus/natural_pair_original_tests.py, tests/test_original_test_overlay.py,
benchmarks/studies/remainder-v1/compatibility/original-tests.md.

## Findings

No concrete correctness or security defect found in this bounded pass. No second review round performed.

The adapter retains twelve frozen ordered revisions and six pair rows; the frozen runtime
record marks only the six Matplotlib revisions ready. Django pairs remain runtime_unqualified.
Raw runtime/build/oracle identities and dependency freezes are bound before execution;
remainder transfer reproduces the readiness source prefix and checks every recomputed transfer
field. The existing archive/link validator and source-only wheel transfer retain source bytes;
the new overlay rejects target/ancestor symlinks and parent traversal before writing oracle bytes.
Original module bytes and node, guarded executor, three fixed repeats, strict JUnit/outcome checks,
and zero product-evaluation/qualification counters retain the existing witness semantics.
The production repair patch is read only to obtain the anchor path and is never applied.

## Validation and limits

PYTHONPATH=src /Users/franz/Desktop/Attest/.venv/bin/python -m pytest -q tests/test_original_test_overlay.py:
4 passed on Python 3.12.2. Static inspection included natural_cases, archive/validate_source_links,
apply_wheel and the readiness transfer recipe. No Docker runs, corpus execution, native escape
reproductions, model/API calls, remote writes or paid spend. Full integration gates remain the
controller's responsibility; this review is not empirical witness qualification.

## Size and reuse

Tracked git diff --stat: scripts/corpus/natural_pair_original_tests.py | 90 lines, 63 insertions,
27 deletions. Untracked proposed additions: tests/test_original_test_overlay.py 35 lines;
benchmarks/studies/remainder-v1/compatibility/original-tests.md 40 lines.
Reused inventory: sha256_bytes/write_canonical_json, validation_junit_counts, natural_cases,
archive/validate_source_links, apply_wheel, declared_version_file and execute_repro.
New implementation helper: overlay_original_test, the scoped safe-write boundary declared in
brief; no new serializer, atomic-write, digest, metric or matching utility. Reviewer added no tools.
