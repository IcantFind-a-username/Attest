# Acceptance evidence

[`evolution-gates.md`](evolution-gates.md) is normative: it defines what must be measured
and what language a passing result permits. Other files in this directory are dated evidence
from particular code, configuration, fixtures, and environments. A report never changes a
gate.

## Existing reports

- [`2026-08-30-evolution-scaffold.md`](2026-08-30-evolution-scaffold.md) — F-00 /
  `G-DOC-001` construction-scaffold acceptance.
- [`2026-08-30-m02-validation-receipts.md`](2026-08-30-m02-validation-receipts.md) —
  M-02 receipt evidence/authority implementation; `G-MEASURE-002` and `G-CODE-002`
  pass, while the work order remains `BLOCKED BY EVIDENCE` on `G-CODE-001`.
- [`phase-3.md`](phase-3.md) — historical planted-fixture GitHub Action integration smoke.
  It predates the complete evidence-bundle and workflow-exit requirements.

## Required report structure

Every new report includes:

1. status (`PASS`, `FAIL`, `INSUFFICIENT`, or `INVALIDATED`) and exact Gate IDs;
2. code SHA/dirty state, policy/config, lock/interpreter/OS/executor digests;
3. provider/model/prompt/schema/tool versions and pricing snapshot when applicable;
4. preregistration/protocol/manifest and their digests;
5. population, unit, strata, inclusion/exclusion, n, cluster count, retries, stops, budget;
6. criteria-versus-result matrix;
7. raw numerator/denominator/point/interval and DEFER/missingness taxonomy;
8. finding-, PR-, opportunity-, cost-, latency-, and security-level results as applicable;
9. complete content-addressed artifact inventory and offline verification command;
10. every failed/retried/excluded arm, protocol deviation, and ambiguous cost;
11. permitted claims and explicit non-claims;
12. independent protocol/result reviewer findings and resolutions.

## Evidence rules

- Machine-readable `report.json` is authoritative over rounded prose.
- The artifact manifest is written last and is immutable after sealing.
- Corrections append an erratum or superseding report; they do not erase the original.
- Private source/hidden truth may remain access-controlled, but the committed/public manifest
  carries safe metadata and digests sufficient to identify missing evidence.
- A private URL alone is not a reproducible evidence bundle.
- A second run on the same planted fixture is a repeated integration smoke, not independent
  statistical replication.
- Failure to meet minimum n/events is `INSUFFICIENT`, not a pass or a discretionary extension.

Use the minimum bundle schema in `evolution-gates.md` as the starting directory layout.
