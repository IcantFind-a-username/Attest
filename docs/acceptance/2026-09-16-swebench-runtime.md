# Independent six-case default-runtime preflight: all builds refuse

E-02 prerequisite, D-270. Baseline2321d0d, measured protocol/driver4bd4bf6, branch
chore/swebench-runtime-qualification. All six frozen candidates attempted once in order.
**Zero successful builds, zero collection executions, actual model/API spend $0.**
No product/default/receipt/isolation change; no gold, test oracle or problem-text access.

| Repository and instances | Selected Python | Observed first build error |
|---|---|---|
| Astropy14369,13236,13398 | 3.12, primary fallback | `setuptools.dep_util` missing |
| scikit-learn25232,25973,26323 | 3.11, declared classifiers | `gcc` missing |

All failures occur at project installation, before the optional dependency roots or package
import stub. Existing BuildKit history was retrieved read-only for all six builds; no retry
or rebuild was used to diagnose them. These are observed first errors, not proof that fixing
them would suffice. The current builder uses a slim Python image and no compiler installation;
Astropy's selected source imports the missing build-helper module through extension_helpers.
The study does not establish historical compatibility or a working repair.

## Evidence and validation

[Protocol](../../benchmarks/studies/swebench-independent-v1/product-runtime-preflight.md),
[all rows](../../benchmarks/studies/swebench-independent-v1/runtime-evidence/result.json),
[build-log identities and diagnosis](../../benchmarks/studies/swebench-independent-v1/runtime-evidence/build-diagnosis.json),
[manifest](../../benchmarks/studies/swebench-independent-v1/runtime-evidence/manifest.json).
Raw logs remain in the ignored runtime directory. Public artifacts bind exact revisions,
product source tree, source listing hashes, script/protocol/population hashes and failure
records. No successful image or execution is fabricated for a failed build.

The existing preflight driver now selects this already-frozen study through a narrow CLI
option; its product builder, stub and executor are reused. Inherited runtime overrides are
rejected, archive/extraction calls have60s timeouts, builds have300s budgets. No version/pin,
Dockerfile, backend or host-fallback substitution occurred. A budgeted build failure does
not establish failure under every possible environment.

[One independent script review](../../benchmarks/studies/swebench-independent-v1/runtime-evidence/independent-review.md)
found no concrete issue. It checked code and in-progress metadata; the controller separately
validated all six terminal records and retrieved final build logs. Ruff and diff checks pass;
source/tests are unchanged. No full product gate was rerun for the diagnostic script change.
Original study artifacts remain unchanged. Source/configuration was exposed for runtime
qualification only; no product tuning used it.

## Meaning and next decision package

These results measure default-runtime feasibility on six selected historical heads:
**0/6 run-ready**. They are neither zero recall nor zero false positives. No defect or
reasonable-change control is qualified, so the preregistered minimum3+3 across two
repositories cannot currently be met. Paying for discovery would not establish the missing
truth/control denominator. No paid reservation or dispatch occurred.

Proposed bounded next step: keep these six candidates and the original default-runtime
result; authorize a separate **build-environment compatibility experiment**, free first.
Use one precommitted rule across all six: choose within the already supported Python range
from project-owned build/CI declarations, freeze historical build dependencies from declared
requirements and commit-date metadata, and supply required compilers in a separate build
stage. Preserve the existing secretless runtime isolation and certification/default intent;
do not patch project behavior/tests, hand-pick cases or retry after behavioral outcomes.
Require exact dependency/image identities, one preregistered attempt, a tiny generic compiled
fixture, and the required independent security-boundary review before accepting a new path.
A successful experimental environment must be labeled separately from default performance;
it cannot erase0/6 or imply full-product independence from runtime-development exposure.

This is a decision package only, not implemented or dispatched. The frozen one-attempt,
no-override protocol and AGENTS §16's outcome-dependent retry boundary require approval
before that new experimental run. No further sample replacement is proposed. Paid evaluation
and the final report remain unfinished; if authorized preparation still cannot meet the
preregistered minimum within the existing cap, retain the shortfall and do not spend.
