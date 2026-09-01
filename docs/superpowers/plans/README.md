# Archived implementation plans

The plans in this directory are completed historical construction records. They preserve
the requirements agents followed at the time, including unchecked boxes, old paths, and
assumptions later disproved. They are not a backlog.

| Plan | Historical outcome | Current replacement |
|---|---|---|
| `2026-08-29-phase-3-action.md` | GitHub Action, CI coordinator, generated-test executor, and planted-fixture smoke implemented; later evolved to differential execution | `../../roadmap.md`, work orders C-*, V-*, X-* |
| `2026-08-29-real-data-evaluation.md` | all eight historical tasks implemented and merged; later audit found measurement, receipt, safety, and recall gaps | `../../roadmap.md`, work orders M-* through E-* |

Rules:

- do not execute tasks from an archived plan;
- do not “finish” its checkboxes or repair old branch/path/test-count statements;
- when investigating provenance, pair the plan with implementing commits, `DECISIONS.md`,
  and dated acceptance/status evidence;
- when old behavior conflicts with the target architecture, the conflict is a known gap,
  not authority to preserve it;
- new executable plans belong in
  [`../../implementation/agent-work-orders.md`](../../implementation/agent-work-orders.md)
  and the roadmap.
