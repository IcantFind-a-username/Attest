# Natural-pair source runtime — 2026-09-16

## Result

**Astropy's parent and introducing head both execute successfully from mounted
source.** The generic native-extension fixture passes first. Both scikit-learn
revision records remain build-unqualified and are not retried. API spend is **$0**.

| Source case | Parent | Introducing head | Independent cases |
|---|---|---|---:|
| astropy-14309 | Runtime ready | Runtime ready | 1 |
| scikit-learn-25931 | Build unqualified | Build unqualified | 1 |

Each Astropy execution collects one test, exits zero, skips/xfails zero and uses
`linux-container-v1` with the network guard. The test asserts imports originate
under `/attest/tree/`; the fixture additionally calls its native function. Parent
and head runtime dependency freeze bytes match. This is **one runtime-ready source
case, not two defects**. Original-test witnesses, qualified defects and qualified
controls remain zero; product precision, recall and FPR are not measured.

## Method and evidence

Driver/protocol committed before execution at
`d7526adb3fdd708d49c179e7d8d36e73a8f8c2fc`, on
`chore/natural-pair-source-runtime`. The product source tree is identical to gated
`f2560ce` (2,568 tests, 93.42% certification/execution coverage). The measurement
adapter received one independent review with no concrete findings, and pure input
checks plus Ruff/diff checks pass. Its default six-case inputs still satisfy the
strengthened identity checks. No product source changes occurred in this step.

The adapter reuses the existing runtime, native fixture, canonical artifact and
wheel-transfer helpers. It binds the complete ordered four-row population to the
reviewed qualification and original freeze, and matches committed build records.
Each successful revision receives its own digest-bound wheel; original source
bytes are preserved. Failed builds remain in the original population. No new
serialization, statistics, isolation or certification mechanism was introduced.

Python 3.10 runtime image, builder, dependency freezes, per-side transfers, exact
commands and execution observations are retained. This is a compatibility recipe,
not an exact historical environment. Dependency fetching occurs during image
construction; execution is secretless and network-disabled. Project addopts are
cleared by the separately gated controller fix; conftest and other ini settings
remain active. No outcome-based retries, source patches, paid calls, reservations,
push, release, default intent or statistical-policy changes.

- [Frozen protocol](../../benchmarks/studies/metadata-exposed-v1/compatibility/source-runtime.md).
- [Independent review](../../benchmarks/studies/metadata-exposed-v1/compatibility/source-runtime-review.md).
- [All four terminal records](../../benchmarks/studies/metadata-exposed-v1/compatibility/source-runtime-evidence/result.json).
- [Manifest, raw/archived digests and logs](../../benchmarks/studies/metadata-exposed-v1/compatibility/source-runtime-evidence/manifest.json).

## Next boundary

The bounded runtime task ends here. Next is a separately frozen original-test
witness: identical original human test bytes on the natural parent/head, with
source origins, test identities and repeated outcomes checked. This must not use a
repair overlay as a substitute for natural regression direction. Independent
controls and the unchanged minimum of three defects across two repositories still
stand between this result and paid evaluation. D-276's shortfall is not amended by
this development diagnostic. Reverting the adapter commit restores the old
measurement interface; retained evidence and product defaults remain intact.
