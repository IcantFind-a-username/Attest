# Frozen held-out oracle qualification: no eligible witness

E-02 prerequisite, D-268. Baseline `b70afb3`, measured driver `8eb5d63`, branch
`chore/heldout-oracle-qualification`. Protocol `636385c` was committed before reading
selected original oracle metadata. Actual model/API spend **$0**; no paid review or remote
write, no product/default change. This is a qualification result, not product recall.

All 20 frozen candidate rows remain in the result. Thirteen retain their prior runtime
refusal. All seven runtime-success cases receive one fixed/buggy pair: **14 terminal jobs**,
all exit 4 during collection/configuration. Zero pairs distinguish the defect. The
preregistered stop-after-first-invalid-pair rule prevents later repeats or repairs.

| Case | Failure on both fixed and buggy side |
|---|---|
| HTTPie 2, 3 | `pkg_resources` missing |
| HTTPie 1 | duplicate `pytest.fixture` application to `httpbin_ca_bundle` |
| HTTPie 5 | `requests.compat.is_py26` cannot be imported |
| HTTPie 4 | `requests.compat.is_windows` cannot be imported |
| thefuck 20, 21 | `imp` missing during conftest import |

These errors do not establish whether the historical defect itself reproduces. Four cases
produce collection-error JUnit on each side; three produce no JUnit. Neither absence nor
collection failure is a defect witness. Prior package-level import success did not exercise
these test dependencies and submodules. No candidate enters the recall denominator.

## Evidence and implementation

[Protocol](../../benchmarks/studies/repository-holdout-v1/paired-oracle.md),
[all rows](../../benchmarks/studies/repository-holdout-v1/paired-oracle-evidence/result.json),
[manifest and execution hashes](../../benchmarks/studies/repository-holdout-v1/paired-oracle-evidence/manifest.json).
Original commands, test-file hashes, fixed/buggy SHAs and image identities are bound.
Hidden test bytes and raw test logs remain in the ignored `.attest/corpora/heldout-paired-oracle/`
directory. They were never routed into product prompts, source changes or proposal caches.
The same preflight head image runs both sides, with source-origin checks and unchanged
original test/configuration files except the declared fixed-test overlay on buggy. This is
product-runtime qualification, not exact historical-environment reconstruction.

The existing archive helper gains an optional timeout; old callers retain its default.
The diagnostic uses 60 s archive/extraction deadlines and rejects inherited runtime
constraint/interpreter overrides. Execution uses existing Controller and ContainerAdapter
under `linux-container-v1`, with fresh jobs and the preregistered limits. No new isolation
profile, network permission or dependency pin was introduced.

The [single review](../../benchmarks/studies/repository-holdout-v1/paired-oracle-evidence/independent-review.md)
found one low-severity audit defect: malformed JUnit could leave the summary job marked
started after execution. Repair `ffa1ae5` checkpoints the terminal envelope and artifact
hashes before parsing. A malformed-XML injection through the actual checkpoint/parser source
block confirms rejection after durable checkpointing. None of the measured jobs hit this
path; all 14 terminal records were independently checked by the controller. No outcome was
rerun, and the measured driver digest remains `8eb5d63` rather than the repair's digest.

Script Ruff and diff checks pass; source/tests are unchanged. No full product gate was rerun
for these diagnostic scripts. Environment continues D-267's host and image identities; the
manifest retains exact per-run request/envelope/artifact digests. Reviewer inspected the
code and in-progress metadata; final completeness and raw-artifact checks were controller work.

## Paid-evaluation blocker and proposed owner decision

**Named blocker: no qualified independent defects or matched controls in the frozen pool.**
The 20 candidates now have zero qualifying paired witnesses under this protocol. Forward
change direction, semantic adjudication and controls also remain unqualified. Paying for
model discovery cannot repair this missing truth denominator; it would buy execution/coverage
observations, not the requested defensible independent recall estimate.

Proposed decision: authorize a **separate E-02 study using SWE-bench Verified**, already a
permitted corpus, with a fresh repository-exposure audit and a committed split/protocol before
source exploration. Keep all 20 failed candidates and this report visible as the original
study; do not replace them inside its denominator. Qualify runtime, original test evidence,
forward direction and reasonable-change controls before model dispatch. Record every refusal;
no result-driven replacements. Keep the same approved total spend cap and pay only if its
remaining headroom covers the new preregistered minimum. If no eligible independent pool or
fundable minimum exists, report that shortfall without dispatch. No new product surface or
work-order series, default change, release or push is proposed.

This decision is needed because AGENTS §16 reserves outcome-dependent sample/exclusion/retry
changes to the owner. The current failed pool is not silently exchanged for an easier one.
The final paid report is still outstanding; this is not the completed long-task outcome.
