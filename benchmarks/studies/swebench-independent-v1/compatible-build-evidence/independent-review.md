# Independent compatibility-build review

Reviewed commit `7e37a41a10e3a0e5247c510a5562ee3219071c6f`, limited to the driver and its protocol. Read-only inspection of reused helpers; no corpus problem, gold, patch or test data read. No Docker execution, network calls, model calls, paid work or product changes.

## Findings

1. **Medium — actual build dependency environment is not retained** (`scripts/corpus/swebench_compatible_build.py:88–90`). `pip wheel` creates its isolated environment for the declared backend; the following `python -m pip freeze` runs in the outer image interpreter, after that temporary environment is removed. Consequently `/builder-freeze.txt` does not describe the backend dependencies used to produce the wheel. This directly misses protocol step 2's resolved-environment promise. Reproduction by command/dataflow inspection: wheel uses default build isolation, freeze is a separate Docker RUN in the outer interpreter, and no command captures the isolated environment. Retain the actual build environment/package resolution or explicitly narrow the protocol and report to the outer environment; the latter cannot support an exact dependency replay claim.

2. **Medium — a preparation schema failure aborts the six-case accounting** (`scripts/corpus/swebench_compatible_build.py:66,108`). TOML with no `build-system` or no `requires` raises `KeyError`; a malformed build requirement container can raise `TypeError`. Neither is caught by the per-case handler, so the final record stays `started` and later cases receive no row, despite the stated requirement to keep every failure in the six-case denominator. This is established directly from the unconditional dictionary indexing and the exception tuple; no claim is made that the selected corpus currently contains such a manifest. Validate the shape explicitly and record preparation refusal while continuing all six, or prepopulate all six rows so an abort remains explicit.

## Other checks and limits

- Exact requested revision is passed to the reused git-archive helper. Population bytes, protocol, driver, constraints and Dockerfile are hashed; base image resolves to a digest and successful images have an ID.
- Source build is inside Docker; the generated Dockerfile and build invocation forward no secret, SSH, host socket or host environment argument. Controller environment inheritance alone is not evidence of passing credentials into the build. Build context contains the prepared tree and local run artifacts, not the controller config directory. Symlinks are refused before build.
- Declared requirement expressions remain in the original tree. Upper constraints are explicitly partial and do not claim a historical transitive lock. No outcome-driven dependency retry exists.
- A 900-second client build timeout is specified. Preparation metadata calls have individual helper timeouts but no total preparation deadline. A subprocess timeout alone is not evidence that remote builder work has stopped.
- Wheel hashes and outer freeze are retained inside successful images, not exported into the host result artifact. Consumers must preserve/access those images. Timed-out logs exist but receive no digest because hashing is after subprocess completion.
- Counting correctly makes no claim of qualified defects/controls from a successful wheel build. No empirical feasibility result was generated during review.

Validation: `.venv/bin/python -m ruff check scripts/corpus/swebench_compatible_build.py` — passed. Static review only; no runtime/security gate claimed.

Review-only diff: one new ignored report file, `.attest/repository-freeze-work/compatible-build-review.md`; implementation diff is empty. Reused tools: inspected `archive`, `direct_dependencies`, `_fetch`, `latest_before`, `discover_roots` and `scm_pretend_version`; confirmed driver reuse of `sha256_bytes` and `write_canonical_json`. New tools: none.
