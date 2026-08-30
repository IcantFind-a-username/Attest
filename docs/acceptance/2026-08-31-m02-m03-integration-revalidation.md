# M-02/M-03 integration revalidation — 2026-08-31

Status: **PASS M-02** — `G-MEASURE-002`, `G-CODE-001`, and `G-CODE-002`;
**PASS M-03 integration regression** — `G-MEASURE-003` and `G-CODE-001`.

This is a superseding integration observation, not a rewrite of either historical report.
The original M-02 report remains visibly **BLOCKED BY EVIDENCE** for its branch-local
`G-CODE-001` failure, and the prior M-03 evidence remains immutable. The integration Gate
below is new evidence from the accepted implementation object.

Phase 0 remains open on M-01/G-MEASURE-001. This report does not accept M-01, C-01, Core,
or any later work order.

## Exact implementation and scope

- branch: `feature/phase0-m02-m03-integration`;
- implementation SHA: `14a57fb3eeaf7c38f136a5e82151f8d3c738af5b`;
- parent SHA: `856aba3f55ae26db15a9ded9da5f52b3bf1d3bf0`;
- tree SHA: `1253ba9ae9918a875c6d0ea5653191396ff244d4`;
- changed tracked files: 21;
- implementation binary diff SHA-256:
  `ac27c811c1e49ed9669032b75b1d2299a7215ef6448d012dfa5f840e50dd39de`;
- both Gate checkouts were clean and detached before and after their runs;
- no paid call, provider-network call, remote mutation, pricing change, statistical
  constant change, M-01 implementation, C-01 implementation, or Core change occurred.

The full immutable evidence bundle is
[`evidence/2026-08-31-phase0-m02-m03-integration-14a57fb3eeaf7c38f136a5e82151f8d3c738af5b/`](evidence/2026-08-31-phase0-m02-m03-integration-14a57fb3eeaf7c38f136a5e82151f8d3c738af5b/).
Its final `ARTIFACTS.sha256` covers the other 89 files and has SHA-256
`a3d52f8752f893a8ff959cde1c73f28e5dedf5d1eefc3746ab1f426f7e4345c9`.

## Integrated authority contract

M-02 and M-03 now coexist without upgrading historical evidence or weakening paid-call
accounting:

- `ValidationReceiptV2` retains complete fixed/buggy run evidence plus distinct integrity,
  authenticated-provenance, and semantic-policy decisions;
- only an exact verifier-minted current capability can authorize a pure reducer over
  already-existing trusted evidence;
- public `validate_corpus` and the `validate` CLI produce unsigned/hash-bound diagnostics
  and never mint current authority;
- `verify-validation` is the only supported Phase 0 CLI reachability for a current V2 HMAC
  bundle, and it executes no project/provider code;
- replay, comparison, and live execution accept only exact historical V1 or no receipt;
  V1 remains `historical_integrity_only` and always withholds accuracy;
- symmetric V2 authority is rejected before project runner, provider, checkpoint, state,
  or output side effects. A supported current-V2 production execution workflow waits for
  X-01/V-03 or a public-key protocol;
- exact manifest bytes, typed semantics, receipt digest, truth, roles, commits, request
  policy, and predeclaration are joined fail closed without Python-subclass equality
  escape hatches;
- M-03 immutable paid-call roles, request/artifact/spend reconciliation, ambiguous-cost
  retention, checkpoint recovery, and report authority remain enforced.

## Versioned compatibility and migration

The integration makes the following current writer versions explicit:

| Artifact | Current writer | Retained older form |
|---|---:|---|
| comparison checkpoint/predeclaration | 6 | v5 retained, rejected for current resume/replay |
| comparison report | 4 | v3 historical only |
| calibration report | 4 | v3 historical only |
| live predeclaration/per-case checkpoint | 5 | v4 historical only, rejected for current resume |
| stability predeclaration | 5 | v4 historical only, rejected for current resume |
| stability report | 4 | v4 remains current because its payload shape did not change |
| evaluation binding | 2 | v1 historical only |
| benchmark report | 3 | unchanged |
| validation receipt V1/V2 | 1/2 | unchanged; V1 never regains scoring authority |

Unknown versions and semantic fields fail closed. No old checkpoint, receipt, result,
protocol, BLOCKED report, INVALIDATED report, or M-03 evidence blob was rewritten.

## Gate matrix

Both exact environments used fresh detached checkouts and fresh venvs, installed offline
from the same wheelhouse and `requirements-toolchain.lock`.

| Gate | Python 3.11.5 | Python 3.12.8 |
|---|---:|---:|
| implementation/parent/tree provenance | PASS | PASS |
| v1 receipt/results/protocol original hashes | PASS | PASS |
| clean locked install, freeze, runtime identity | PASS | PASS |
| M-02 focused corpus/artifact/report | PASS | PASS |
| `G-CODE-002` mutation/guard-removal | PASS | PASS |
| M-03 role/checkpoint/live/stability/comparison | PASS | PASS |
| all benchmark tests | PASS | PASS |
| full pytest | PASS | PASS |
| total source coverage | 91.28% PASS | 91.28% PASS |
| `attest.core` coverage | 428/429 statements covered, ≥99% PASS | 428/429 statements covered, ≥99% PASS |
| Ruff 0.16.5 | PASS | PASS |
| Mypy 2.3.1 | PASS, 47 files | PASS, 47 files |
| `pip check` | PASS | PASS |
| diff check / final clean detached checkout | PASS | PASS |

Lock SHA-256:
`76908dd8dc527b59e95ab856cf67656946a4c1bf8eecbb0d95430a2161341c11`.
Wheelhouse inventory SHA-256:
`65e07106d4b90c72b204012a1bbec7cf78f6866c815312cbb9db620a3131c325`.
The exact commands, raw logs, `.exit` files, freezes, runtime identities, and clean-state
records are inside the evidence bundle. Test counts are observations, not Gate constants.

The frozen historical V1 artifacts remain byte-identical:

- `receipt.json`:
  `e8cabb89471bb369a93ce82399a342eaddbf7ed8994d5420aef66256d013ce40`;
- `validation-results.json`:
  `e90b2acfb9753db196cd7d2cf999dc2fa24bbd91bb84d908b476682c1b441288`;
- `protocol.md`:
  `2a6019533a1c01abbf905e57b0b15017b806aeeee6028e496b0149a4a1f2246c`.

## Independent review

Three final read-only reviews rebound their conclusions to the exact implementation SHA,
parent, tree, file count, and binary diff digest above:

- contract: P0=0, P1=0, P2=0;
- security: P0=0, P1=0;
- manifest/receipt: P0=0, P1=0.

The last exact-type review separately confirmed P0=0/P1=0 for manifest digest, nested
truth, live receipt digest, and comparison role joins. Reviewers made no checkout changes.

## Permitted conclusion and handoff

The integrated implementation satisfies M-02's receipt-evidence/authority contract and
the required portable/adversarial code Gates while retaining M-03's crash-safe role/cost
authority. M-02 may now be checked complete in the roadmap.

This conclusion is about deterministic fixture, protocol, and boundary evidence. It makes
no provider-quality, production-security, recall, precision, comparison-winner, release,
or paid-study claim.

One inherited comparison weakness is intentionally not half-fixed here: a caller can
rewrite `ArmRun` outcome fields and coordinated aggregates because no versioned
authoritative arm-outcome artifact exists yet. That exact RED and ownership transfer to
M-01/G-MEASURE-001. Therefore this report does not accept comparison accuracy quality and
Phase 0 does not exit until M-01 passes.
