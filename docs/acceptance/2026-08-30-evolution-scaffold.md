# Evolution scaffold acceptance — 2026-08-30

Status: **PASS for `G-DOC-001` / F-00**

This report accepts the documentation and construction scaffold implemented by
`e52a43b` (`docs: define evidence scheduler evolution`) from baseline
`c94578803b9324e55ef248eb1d29ffe596c85dbb`. The acceptance-record commit is the commit
containing this file.

It does not pass `G-CODE-001`, implement the target algorithm, activate Core, authorize a
paid study, or authorize any remote/pilot/release action.

## Scope and environment

- branch: `feature/evidence-scheduler-roadmap`;
- implementation SHA: `e52a43b`;
- baseline: `main@c945788`;
- Python: 3.11.5;
- pytest: 9.1.1;
- ruff: 0.16.5;
- mypy: 2.3.1;
- provider/model/prompt/executor: N/A — documentation-only;
- spend: $0.00 for this work order;
- remote mutations: none.

The repository checkout had no local `.venv`; static and test commands used the existing
external project audit environment at `../work/attest-audit.87a8GQ/venv`. This is execution
provenance, not a supported environment declaration. M-03 owns the future lock/toolchain.

## `G-DOC-001` criteria matrix

| Criterion | Result | Evidence |
|---|---|---|
| one normative owner per fact class | PASS | `docs/README.md` maps rules, architecture, order/status, implementation method, thresholds, decisions, evidence, spend, and operational guides |
| honest current/target/historical boundary | PASS | README limitations, historical banners, archived completed plans, D-037 erratum |
| current product wealth not described as an e-process | PASS | README and package description use evidence-first/differential language; D-026 remains historical evidence |
| Core authority is unambiguous | PASS | Core is a task/PR-local action scheduler only; certification and speech authority remain independent |
| stable traceability | PASS | 16 `INV-*`, 13 `GAP-*`, 30 work orders, 29 `G-*`, and 13 `RISK-*`; no duplicate, undefined, or unreferenced ID |
| roadmap/work-order agreement | PASS | all 30 roadmap IDs have exactly one detailed work-order section |
| construction readiness | PASS | all 30 work orders contain dependency, concrete file/interface, RED, GREEN, acceptance, rollback, boundary, and focused-test fields |
| quantitative threshold ownership | PASS | active target/roadmap/work-order documents reference acceptance Gate IDs rather than redefining thresholds |
| relative Markdown links | PASS | zero missing relative links in the repository Markdown set |
| metadata and whitespace | PASS | `pyproject.toml` parses; `git diff --check` is clean |
| independent review | PASS | separate reviews covered information architecture, work-order executability, statistical/security Gates, authority/links, and final whole-tree consistency; final review reported no unresolved P0/P1/P2 |

## Commands and results

```text
scaffold link/ID/work-order-field/TOML validator
PASS — 16 invariants, 29 Gates, 13 gaps, 30 work orders; zero missing links,
       undefined IDs, unreferenced definitions, roadmap mismatches, or field failures

git diff --check
PASS

../work/attest-audit.87a8GQ/venv/bin/ruff check .
PASS — All checks passed

../work/attest-audit.87a8GQ/venv/bin/mypy src/attest
PASS — no issues in 46 source files

../work/attest-audit.87a8GQ/venv/bin/pytest
FAIL — 760 passed, 1 failed in 184.92s
```

The one failing test is
`tests/test_phase3_acceptance.py::test_spend_insertion_is_idempotent_by_run_id_and_updates_total`.
It expects a literal `2026-08-29`, while the implementation records the current date
(`2026-08-30` during this run). The same failure existed before the final documentation
edits and is explicitly assigned to M-03's injected-clock work. It prevents a
`G-CODE-001` claim and cannot be used to mark a code work order complete; it does not fail
the documentation-only `G-DOC-001` criteria.

## Review findings resolved

The final review cycle required and verified fixes for:

- task-scoped discovery versus same-task candidate-scoped evidence actions and rejection of
  cross-PR candidate/reservation/budget/observation transfer;
- V-03/X-01 provenance order and X-02's actual-dispatch OS-boundary evidence;
- independent, product-blind truth ascertainment, design-weighted silent sampling, resolved
  denominators, and zero/undefined-denominator `INSUFFICIENT` behavior;
- PR-cluster/event/power floors for scheduler benefit and monitor intervention;
- S-04 audit isolation and the permanent absence of scheduler certification/speech authority;
- model/version/role routing-cell safety without averaging away excluded/insufficient cells;
- C-05/V-02/X-03 decision-package stages before owner-selected implementation;
- L-01 component-gate entry versus `G-RELEASE-001` operational exit;
- a non-pricing N-01 new-code evidence-contract decision packet;
- complete RED/GREEN/rollback/boundary/test targets for every work order.

## Permitted conclusion

The repository now contains a coherent, reviewable construction authority for evolving
Attest into an evidence-first LLM project evaluator. F-00 is complete, and M-01, M-02, and
M-03 are the first unblocked implementation work orders subject to file ownership.

No algorithm-quality, recall, precision, security-boundary, scheduler-benefit, new-code,
pilot, or release claim follows from this documentation acceptance.
