# X-03 fixed-query feasibility: incomplete security qualification

This dated report closes only the bounded feasibility phase. It does not admit an
execution profile, finish X-03, or complete the authorized paid evaluation.

## Scope and evidence

The owner approved the default-off contract in
[the work order](../implementation/x03-git-query.md). Baseline was `223e681`;
prototype code and committed measurement driver were `11400e8640410e90b7dd9c9e59a65b17386dbd41`
on `feature/git-query-profile`. No product adapter or receipt changes were made.
The existing process-free default and intent v5.1 remain unchanged.

- [Platform probe](evidence/2026-09-16-x03-feasibility/platform.json): child ptrace
  available; Landlock unavailable on the measured Linux/aarch64 host.
- [First trial](evidence/2026-09-16-x03-feasibility/trial-r1.json): all four probes
  refused, including the intended query, because early child stops were mishandled.
- [Second trial](evidence/2026-09-16-x03-feasibility/trial-r2.json): one intended
  Python-to-shell-to-Git chain completed; three other synthetic probes refused.
  Image, executable, source and driver digests are in the record. Git itself exited
  128 because the fixture had no Git repository; Python ignored that status.
  This establishes process-chain feasibility only, not a successful metadata query,
  Django import, isolation acceptance, or product performance.

## Independent review and open defects

The [single static review](evidence/2026-09-16-x03-feasibility/static-review.md)
identified three unresolved defects: incomplete process-creation flag validation,
environment subsets/duplicates admitted, and missing daemon-side cleanup and durable
checkpoint on driver timeout. These are static findings, not runtime-verified escapes.
An attempted native security reproduction was rejected by automatic safety review.
It was not retried through another route; that required security evidence is missing.
The review therefore did not pass the security boundary.

Before admission, resolve the identified defects with focused tests, complete the
required supported security validation, bind child execution evidence in the adapter
and receipt, and pass X-03 integration gates. Unsupported ABI handling and complete
FD/memory/output/resource isolation also remain unvalidated. Predicate-only and fake
runner tests can address validation and cleanup without executing a native escape.

## Bounded handoff

The phase produced its feasibility measurement and reached the repository's bounded
review/repair stop condition. No further prototype growth is included in this phase.
There is no final full gate or product admission claim for this branch. Its artifacts
must not be used to qualify corpus cases or authorize paid dispatch. The separate
compatibility gate on `223e681` was still running when this report was written.

Model/API spend: $0. No reservation, paid study, push, release, or third-party write.
The paid objective and existing development cap remain unchanged. No recall or false
positive estimate can be calculated from these four synthetic execution checks.
