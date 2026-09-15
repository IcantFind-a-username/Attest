# Original tests discriminate three repairs; paid eligibility remains open

E-02 prerequisite, measured driver `c25c7c0`. No product code, factory defaults,
certification or isolation policy changed. Model/API spend is $0; no push or
remote write occurred.

[Evidence manifest](../../benchmarks/studies/swebench-independent-v1/paired-oracle-evidence/manifest.json)
binds the safe execution summary, driver review, private semantic-review digests
and historical source inspection. Original patches, tests and full private
reviews remain in the ignored corpus/work directories.

The three runtime-ready scikit-learn cases each completed three paired original
test runs: repaired passed and baseline failed, with exactly the requested test
identity and zero errors/skips. These are 18 executions for three independent
cases, not 18 defects. The other three frozen Astropy cases remain runtime
unqualified and were not silently replaced.

Both sides use an exact frozen base export, its verified native support and the
same unchanged original test overlay. The repaired side adds the original Python
repair patch; repaired and test-file bytes match the upstream PR reference.
These are explicitly derived trees, not exact upstream repair checkouts. They
share base-built native artifacts and cannot be used as certification evidence.
They also do not satisfy the parent compatibility protocol's stronger requirement
for revision-specific generated artifacts on each distinct source revision. The
observed discrimination is retained as a diagnostic, not promoted to a qualified
paired witness under that protocol; no qualified-defect counter was incremented.
The human-oracle invocation retains OS isolation but is not the product's
generated-probe language-audit path.

One independent driver review found that counts and stable identities alone did
not bind the observed tests to the requested nodes. A synthetic unrelated JUnit
population reproduced the predicate gap. Before the committed driver ran, the
check was tightened to exact identities for the supported original module-level,
nonparameterized nodes. No behavior-dependent test or environment repair occurred.

## Product-blind semantic review

Two independent reviewers read original patches/tests and base source, without
seeing product outputs or paired execution outcomes. They agreed:

| Case | Semantic class | Natural forward pair established |
|---|---|---|
| scikit-learn-25232 | New capability | No |
| scikit-learn-25973 | Existing-contract defect | No |
| scikit-learn-26323 | Existing-contract defect; propagation wording has ambiguity | No |

The first case's old-side failure therefore does not establish a violated
existing contract. The two semantic defects still need their actual introducing
commits and qualifying parent/head executions. A successful repair test does not
provide that historical direction, and reversing the repair cannot substitute.
Private review/input artifacts remain outside product discovery.

## Historical direction check

Controller source inspection traced the two existing-contract defects to APIs
introduced with the relevant omission already present:

- SequentialFeatureSelector: `5bf37e8425719bd069919887966bfcb233747e66`,
  parent `ef3937bb98a9f3a66801c0471e446767a405c193`. The original feature loop
  repeatedly passes the iterable to cross-validation, whose wrapper materializes
  it. The parent package has no SequentialFeatureSelector declaration/reference.
- ColumnTransformer set_output: `2a6703d9e8d1e54d22dd07f2bfff3c92adecd758`,
  parent `93c7306836aef3cb62e3cc25efeeae1a8dc8bbde`. The original propagation
  omits the separate remainder; the parent package has no set_output definition.

These identified API introductions do not supply a previously working invocation
for the original test. They are not admitted as natural regression pairs. This is
static history evidence, not execution on the historical parents, and does not
claim an exhaustive proof that no other historical pair could exist. New-code
defect evaluation would require its own approved evidence-class protocol; it is
not silently substituted for the current regression study.

No qualified natural-forward defect/control population or paid product result is
claimed. The study minimum, independent controls, fixed-code gate and free paid-
workflow artifact smoke remain prerequisites. This report establishes test
discrimination and semantic triage only; recall and precision remain unmeasured.
