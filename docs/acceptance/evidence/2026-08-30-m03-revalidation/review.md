# Independent M-03 review

Reviewer role: independent of implementation; read-only review using local tests/fakes.

Final scope: `bcfd9d8624a03858ea5aa71fff84412e6efa6606..5e4234dc71959ac67093d3f56c301324ba1eaa73`

## Findings timeline

The reviewer repeatedly reproduced fail-open cases in intermediate commits: dispatch of a
new ordinal after a settled comparison; missing publication-time artifact verification;
model drift from frozen predeclaration; omission of an entire paid arm; rootless empty
measurement replacement; paid-trial/binding divergence; orphan call roots; invalid frozen
binding fields; and coordinated model metadata rewrite. Each was P1 and each intermediate
candidate was rejected until a regression test and fail-closed implementation existed.

## Final verification

- paid trial, checkpoint, artifact, spend row, reconciliation, and report form an exact
  bidirectional join;
- missing, duplicate, mismatched, orphan, whole-trial, and whole-arm evidence is rejected;
- call schema v3 and artifact/cost schema v2 bind the actual model and canonical complete
  predeclaration digest; coordinated model rewrite is rejected;
- full frozen binding fields and schemas are validated;
- `ambiguous_cost` never automatically retries and settlement/consumption replay is
  idempotent;
- live/comparison/stability crash recovery does not duplicate dispatch;
- Action uses CPython 3.12.8 and the exact complete lock;
- no factory statistical constant or other work order was included.

Final findings: P0=0, P1=0, P2=0.

Final judgment: M-03 PASS; `G-CODE-001` PASS; `G-MEASURE-003` PASS.
