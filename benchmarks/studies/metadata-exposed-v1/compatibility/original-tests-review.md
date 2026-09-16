# Independent review — original-human-test driver

Reviewed baseline `4be26b55ae32f82db32887d6679613108c53a6ce`, branch `chore/natural-pair-original-tests`, working diff for `scripts/corpus/natural_pair_original_tests.py` and `benchmarks/studies/metadata-exposed-v1/compatibility/original-tests.md`.

## Findings

No reproduced blocking findings in this bounded pass. This is a pre-execution code/protocol review, not evidence that the original test runs or yields a differential.

- Frozen natural-case admission delegates to `natural_cases`; raw terminal runtime result is bound to the committed manifest, its population and build-record digests, and complete ordered revision identities. Each runtime dependency freeze is checked against its committed raw digest before pair equality. Original payload and manifest bind the test provenance to the freeze.
- One original module-level node is selected; the complete test module comes from its original base plus only the test patch. The production patch supplies an anchor path and is not applied. Each natural revision receives its own digest-checked wheel and image.
- Acceptance requires exact JUnit identity/counts, one collected test and zero skips/xfails, expected exit/outcome, initialized network guard, fresh artifacts, mounted-anchor execution, no anchor import mismatch, unchanged original test bytes, and three paired repeats. Existing executor enforces the guarded container path. A mismatched pair stops the case after retaining both results.
- scikit-learn remains represented as runtime-unqualified. Only a development witness count can increase; product evaluations and paid qualified counts remain zero. Raw execution details remain under the private output root and protocol forbids committing oracle source/full traces.

## Checks and limits

` .venv/bin/python -m ruff check scripts/corpus/natural_pair_original_tests.py` passed.
Pure read-only checks using `PYTHONPATH=src:scripts/corpus` confirmed raw runtime digest binding and ordered revision identities; inspected original payload node and patch file headers against the admission shape. An initial import check without PYTHONPATH failed to import `attest`; corrected environment passed. No containers, original tests, full suite, model/API calls, remote mutations, or product-source edits were performed.

Diff stat: 2 files changed, 334 insertions: protocol 55, driver 279.

Reused tools inspected: `natural_cases`, `archive`, `apply_wheel`, `execute_repro`, `ContainerAdapter`, `sha256_bytes`, `validation_junit_counts`, `write_canonical_json`, and dataclass `asdict`. Review's pure checks reused `natural_cases` and `sha256_bytes`. New tools: none. Only reviewer-owned output: this review report.
