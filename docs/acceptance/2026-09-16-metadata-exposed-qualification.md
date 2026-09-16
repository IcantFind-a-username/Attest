# Metadata-exposed evaluation qualification — 2026-09-16

## Outcome

The owner-approved new sampling rule was executed. Nineteen cases across four
repositories were frozen before truth access and independently reviewed. Two
natural introducing pairs received independent source-level agreement; both
failed the unchanged product's container build before human-test execution.
**No paid review ran, and no new recall or precision estimate exists.**

The study's minimum remains three qualified natural regressions plus three
controls across at least two repositories. It is unmet for two independent
reasons: only two source pairs agree, and neither has an executed witness.
No population replacement, weaker minimum, repair reversal or paid retry occurred.

## Evidence funnel

| Stage | Count | Interpretation |
|---|---:|---|
| Frozen cases | 19 across 4 repositories | Astropy 5, Django 5, scikit-learn 4, Matplotlib 5 |
| Agreed source-plausible natural pairs | 2 across 2 repositories | Not yet parent PASS / head FAIL witnesses |
| Default product image attempts / refusals | 2 / 2 | Installation fails before execution |
| Original human tests executed | 0 | No paired witness or behavioral verdict |
| Frozen control changes reviewed twice | 80 | Twenty per repository |
| Agreed preliminary semantic controls | 17 | Not runtime-qualified true negatives |
| Control-review disagreements | 3 | Remain outside agreed set |
| Qualified defects / controls | 0 / 0 | Paid dispatch ineligible |
| Paid reviews / model API spend | 0 / $0 | Existing cap and settled total unchanged |

All nineteen cases and eighty controls remain in the artifacts. Refusal or
unresolved provenance does not prove a candidate is not a defect. The history
inspection was bounded; some reviews stopped without finding an introduction.
No third review was sought to manufacture another agreement.

## Concrete runtime failures

The exact runtime driver revision is
`e3b8e0eca358904938da7d1d4a044f9c15c3f0d5`.
Product source tree `d62ecadbdb5e9c70eed119007b7cb89df5d8481a` is unchanged from
the previously gated `0b6d3b1`. Both attempts selected the product's primary
Python 3.12 fallback, without interpreter or dependency overrides.

- **astropy-14309:** introducing head `2a0c5c6f5b982a76615c544854cd6e7d35c67c7f`,
  parent `469a39d3637376ab1613f8b2fc949233fce94aee`. A flattened conditional
  accesses a missing positional argument where the parent returned a falsey
  result. Build fails because `astropy/wcs/setup_package.py` imports
  `setuptools.dep_util`, unavailable in the resolved build environment.
- **scikit-learn-25931:** head `416898b7f41257e5367dc65b5ec82670c1575ef8`,
  parent `c592361e536fbc84c59935b7b4c659e8ab38737c`. Feature-name checks add a
  warning during an existing DataFrame fit path. Build fails with setuptools'
  multiple-top-level-package discovery error for the historical source tree.

These causes come from retained BuildKit logs, retrieved read-only after the
attempts. Retrieval was not a build retry. They establish failure of these exact
runtime attempts, not impossibility of building the projects under another
properly specified environment. No recipe, source, original test or product
admission policy was changed to qualify a case.

## Scope, checks and artifacts

This is **metadata-exposed, previously unevaluated within audited records**.
Historical screening loaded dataset records before reading installation
manifests; universal lack of hidden-column exposure is not asserted. Neither
unseen-repository generalization nor a release-quality result follows.

One independent freeze review cleared the recorded exposure exceptions and
selection. Two independent product-blind semantic/history reviews examined all
nineteen cases; two control reviews examined the eighty frozen changes. Their
private reports are digest-bound. All admitted control diffs were inspected;
other changes may remain conservatively unresolved, not known defective.
Exact parent relationships and source-pair/control overlap were checked.

- [Protocol](../../benchmarks/studies/metadata-exposed-v1/protocol.md) and
  [freeze review](../../benchmarks/studies/metadata-exposed-v1/independent-review.md).
- [All semantic decisions and agreed pairs](../../benchmarks/studies/metadata-exposed-v1/qualification-candidates.json).
- [All control decisions](../../benchmarks/studies/metadata-exposed-v1/control-semantic-summary.json).
- [Manifest, raw-record digests, environment and archived log digests](../../benchmarks/studies/metadata-exposed-v1/qualification-evidence/manifest.json).
- [Runtime observations](../../benchmarks/studies/metadata-exposed-v1/qualification-evidence/runtime.json).

Modified measurement scripts pass Ruff and `git diff --check`; artifact digests
are recomputed before commit. No product source/tests changed, so the fixed-HEAD
2,563-pass gate was not rerun or claimed as a new gate for these documents.
No push, publication, provider call, paid reservation, cap increase or default
intent-rule change occurred. Historical studies and failed runs remain intact.

## Architectural implication and stopping boundary

Paying for candidate generation cannot repair an unavailable execution
environment or supply the missing third semantic witness. The evidence points
to reproducible historical build environments as a separate engineering need;
that work must retain fail-closed isolation and revision-specific native
artifacts, and these inspected cases would be development inputs thereafter.
Build compatibility alone still would not satisfy this study's sample minimum.

This bounded study stops at its recorded shortfall. The requested paid real-
performance report remains unfinished; nothing here is a substitute for it.
Further sampling would require a separately specified population rather than
continuing until enough cases pass. No additional study is launched by this report.
