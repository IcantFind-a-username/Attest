# Independent review: six frozen runtime preflight

Reviewed baseline 2321d0d through 4bd4bf6, one read-only pass. No concrete findings.

- Selected metadata translates all six instance_id/base_commit pairs faithfully, retaining repository and selected order; count guard expects two repositories and six cases. No replacement, outcome-dependent retry, gold patch, hidden test, issue text or fix-message access is introduced.
- Product src tree is identical at both commits: d62ecadbdb5e9c70eed119007b7cb89df5d8481a. The script calls existing project_python, select_backend(production=True, remaining_s=300), nonempty package import stub, and execute_repro collect_only with the declared limits. Container absence refuses; there is no host fallback.
- Nonempty ATTEST_PIP_CONSTRAINT and ATTEST_PROJECT_PYTHON values are refused before work. Existing archive helper receives timeout=60, bounding both git archive and tar. Private Docker config and actual product interpreter fallback are explicit protocol choices.
- Each attempted row is checkpointed before preparation, build and collection; caught failures retain the row and reason. Import success requires exit zero, exactly one collected node and initialized network guard. Qualified defect/control and paid-review counts stay zero. Source, population, script, protocol and available image/execution identities are recorded.
- Runtime snapshot during review remains started: first two Astropy rows refused at build, third preparing. This is not a final six-case result or a completed empirical gate. Controller must validate final six-row population and identities before reporting the measurement. A 300-second build refusal says nothing about a longer budget.

Validation: static diff, existing helper/source inspection, frozen selected metadata and in-progress result metadata; git diff --check passed. No project runtime code, external source files, network, paid calls, or measurements were executed by this reviewer. No product tests were run because this pass changes no product behavior. Generic pre-loop infrastructure errors can terminate before full row completion; started state must never be reported as a complete denominator.

Diff --stat reviewed: 2 files, 81 insertions(+), 19 deletions(-). Reviewer wrote only this ignored report.
Reused tools checked: canonical JSON/atomic writer and sha256_bytes; archive(timeout); stub_packages/probe_stub_source; select_backend; execute_repro. No new tools or implementations.
