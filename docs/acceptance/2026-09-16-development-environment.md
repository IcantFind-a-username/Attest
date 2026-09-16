# Development sample environment prerequisite

Owner-directed continuation of E-02 preparation; D-261, 2026-09-16.
Baseline `1bc7b680e2790e6ef83b5de410c2e4270a961f45`, branch
`chore/qualify-dev-environment`. Measurement script/protocol: `04a2554`.

## Result

**All five frozen development candidates record Python 3.7.3, outside the current
product interpreter matrix (3.10–3.13).** Their exact TensorFlow pins have no compatible
CPython wheel tags for those product versions in the inspected official release records,
and neither release supplies a source distribution. The recorded environments cannot be
faithfully selected through the current product matrix. No installation or test execution
was attempted; this is a metadata prerequisite result, not a product failure or recall score.

| Development case | Recorded Python | TensorFlow pin | Paired oracle execution |
|---|---|---|---|
| keras/8 | 3.7.3 | 1.15.0 | Not attempted: environment prerequisite |
| keras/40 | 3.7.3 | 1.15.0 | Not attempted: environment prerequisite |
| keras/30 | 3.7.3 | 1.13.2 | Not attempted: environment prerequisite |
| keras/34 | 3.7.3 | 1.13.2 | Not attempted: environment prerequisite |
| keras/11 | 3.7.3 | 1.15.0 | Not attempted: environment prerequisite |

There are four Python-plus-requirements-hash groups, because keras/8 and keras/11 share
the same recorded requirements. These are manifest signatures, not four independent
experiments. Qualified defects and controls remain **0/0**; project executions and product
evaluations are **0**. All five remain development candidates. All 20 held-out candidates
remain untouched by this phase; no sample was replaced.

## Evidence and collection repair

The [preregistered preflight](../../benchmarks/studies/repository-holdout-v1/development-preflight.md)
reads exactly the five development candidates' pinned `bug.info`, `requirements.txt` and
`run_test.sh`. Oracle argv are recorded but not executed. The prior frozen split is unchanged.
The script was committed before execution and imports the product's `AVAILABLE_PYTHONS`
directly, reusing existing JSON/digest and packaging parsers.

Run **r1 is invalid**, not a zero-result census: generic requirement parsing stopped on
keras/30's editable VCS install line. Its [failure record](../../benchmarks/studies/repository-holdout-v1/development-preflight-r1/invalid.json)
preserves the partial metadata access and failure. The visible collection repair narrows
parsing to the preregistered dependency; it does not drop a candidate or alter a test outcome.
The earlier two line-length lint failures were corrected before the successful r2 run.

Run **r2 completed**, with five input rows and zero release metadata errors. The official
[TensorFlow 1.13.2](https://pypi.org/pypi/tensorflow/1.13.2/json) and
[TensorFlow 1.15.0](https://pypi.org/pypi/tensorflow/1.15.0/json) snapshots contain 15 and 11
distributions respectively. They are all historical ABI-specific wheels, with none for
CPython 3.10–3.13 and no source distributions. This does not establish whether a separate
historical Python 3.7 environment, source build or port could work; other dependencies
and full installation are unqualified. Package yanking/requirements fields are retained.

The [r2 result](../../benchmarks/studies/repository-holdout-v1/development-preflight-r2/preflight.json)
binds the script, protocol, frozen manifest, corpus revision, metadata inputs and raw PyPI
responses. Raw responses are committed compressed; the
[archive map](../../benchmarks/studies/repository-holdout-v1/development-preflight-r2/response-archive.json)
maps logical filenames to gzip files, with compressed and decompressed hashes. Original
uncompressed copies also remain in the ignored task workspace. No evidence was overwritten.

## Checks, limits and next step

One [independent review](../../benchmarks/studies/repository-holdout-v1/development-preflight-r2/independent-review.md)
verified the repaired extraction, denominators, official response projections, wheel tags
and hashes; no unresolved findings. Script Ruff, final artifact/hash checks and
`git diff --check` pass. [Validation manifest](../../benchmarks/studies/repository-holdout-v1/development-preflight-r2/validation.json).
No product behavior changed, so no RED/full product gate was run or claimed.

The named blocker is **historical environment outside the product support matrix**.
The next bounded step is to qualify a separate historical oracle environment for the
development slice, then determine whether these defects can support any faithful product
comparison. It must retain exact pins, isolated execution, case order and all failed
attempts; changing the product's supported interpreter matrix is a separate implementation
decision. Paying for discovery before resolving this blocker would not provide the missing
execution evidence. Do not substitute held-out cases to obtain a working development set.

This small candidate pool does not meet G-CORPUS-001's required 120 independent regressions,
120 controls and 20 repositories, nor its blind semantic review requirements. It is an
early preparation step. No precision/FPR/recall or 1.0 release-readiness claim follows.

Attest model/API spend **$0**. No project execution, paid provider call, remote write,
push, default change or certification change. Rollback: retain the evidence and disable
further preflight use; no receipt/schema migration is needed.
