# Independent static review: source-mounted runtime

Baseline e400ef2; branch chore/swebench-compatible-runtime. One bounded static pass over the two new scripts, transfer tests, protocol and generic native fixture, plus referenced repository helpers. No corpus source/test/problem/gold reads, builds, test execution, network or model calls.

## Findings

1. **P2 — Refusal stage is lost in the retained result.** `scripts/corpus/swebench_source_runtime.py:228-235` wraps transfer, constraints and image construction in one call and records every exception as the same `status="refused"`, with only an exception string. A timeout from an image build and another subprocess timeout cannot be counted reliably by stage. This contradicts `source-runtime.md`'s explicit requirement to distinguish image refusal, transfer refusal and execution failure. Record a structured stage before each transition (or propagate a typed stage) and retain it on refusal. The fixture path at lines 186-212 additionally lets build/transfer exceptions escape with only the initial `status="started"` result; record a terminal fixture refusal and reason before stopping the six cases.

2. **P2 — Archive path collisions are detected after writes begin.** `scripts/corpus/wheel_overlay.py:58-65` admits both `pkg/a.so` and `pkg/a.so/b.so` as absent native additions. During the write loop the first file is created and the second then raises from parent creation. An existing source directory named `pkg/a.so` similarly reaches `open("xb")` only after earlier additions have been written. Consequently the advertised check-entire-archive-before-writing boundary does not hold for file/directory collisions, and tests only cover semantic refusal classes. Preflight target types and ancestor/descendant collisions for every planned addition before the first write, with a parameterized regression asserting no additions remain after either conflict. This is diagnostic partial state, not an identified certification bypass.

## Positive checks and limits

Revision equality and recorded wheel digest are checked before transfer. Source overlap bytes and post-transfer original-file digests are retained; unsafe archive names and symlinks fail closed. Runtime image uses the selected digest and the existing guarded container executor, without changing product/kernel defaults. The fixture gates corpus execution. Qualified defect/control counters remain explicitly zero. Package origin checks witness top-level imports; they do not independently prove all native modules were exercised, and the protocol should retain that limited claim.

Implementation reuses canonical_json_bytes, sha256_bytes, write_canonical_json, archive, stub_packages, declared_version_file/discover_roots, era constraints helpers, execute_repro and ContainerAdapter/ContainerImage. New declared helpers are wheel transfer, runtime metadata constraints and diagnostic image build. This reviewer adds no tools or implementation helpers.

Diff --stat: ordinary git diff --stat is empty because the reviewed files are untracked; git diff --no-index /dev/null scripts/corpus/swebench_source_runtime.py reports 1 file changed, 243 insertions. Reviewer-owned addition: this report only. No implementation files changed.
