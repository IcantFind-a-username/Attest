# Every evidence bundle on this host, re-verified — 44 of 86, and two disjoint causes

**D-124**, owner instruction 1 of 2026-09-04. `scripts/corpus/reverify_bundles.py` walks every
`.attest/evidence/<task>/<candidate>/` directory under the workspace and one named extra root,
asks the shipped offline verifier (`attest.review.evidence.verify_bundle`, the same function
behind `attest verify --bundle`), and writes an `unverifiable_v1.json` marker beside each bundle
it rejects. **Nothing was deleted.** No model call, no execution: git and disk only, $0.00.

Full machine-readable result: [`evidence/2026-09-04-bundle-reverification.json`](evidence/2026-09-04-bundle-reverification.json).

## 1. The count

| | n |
|---|---|
| bundles found | **86** |
| verified | **44** |
| unverifiable | **42** |
| marked `unverifiable_v1` | 40 (the 2 outside the workspace are reported, not written to) |

Bundles produced by the test suite in pytest temporary directories are not in scope: they are
fixtures, deleted between runs. The 86 are the real ones — the SWE-bench cases, the three
real-traffic clones, the two pilots, and two in `~/Documents/stock_trader` reached read-only
with `--root`.

## 2. Two causes, and only one of them is a product defect

| n | reasons the verifier gave | dates | cause |
|---|---|---|---|
| 13 | provenance digest · fresh state · executor profile · executor backend | 2026-09-02 | schema drift |
| 17 | provenance digest · fresh state | 2026-09-03 | schema drift |
| 8 | provenance digest | 2026-09-03 | schema drift |
| **4** | **test bytes do not match `receipt.test_digest`** | 2026-09-03 – 2026-09-04 | **D-124** |

**The 38 are schema drift, not forgery.** They were written before V-03 added `fresh_state`,
before X-01 gave a run its executor identity, and before the receipt body reached its current
shape; the provenance digest is computed over that body, so it moved when the body did. This is
`INV-VERSION-001`, the trade D-121 already documents and partly paid down for intent policies.
It is worth saying plainly: **the product's headline claim decays every time the receipt schema
moves, and 38 of 86 bundles on this host are already past that line.**

**The 4 are the defect.** In each one the bundle's `test_repro.py` is not the test the runs
executed — the root cause is in [D-124](../../DECISIONS.md): the D-114 collection loop replaces
the generated test, and the bundle was written from the first generation instead of the one that
ran. In one of the four the first generation was the empty string, so the bundle's test file is a
single newline; in the other three it is a plausible test nobody executed.

| bundle | corpus row | outcome at the time | bundle bytes |
|---|---|---|---|
| `us-stock-helper` `75ce7a3425` (task `20260903-193007`) | `d11` (defect pair) | **published** | 2,364 (a different test) |
| `us-stock-helper` `1d0af73c3e` (task `20260903-193901`) | `c02` (refactor control) | certified, below family threshold | 1,804 (a different test) |
| `Attest` `b89a422892` (task `20260904-004449`) | `d03` at `--budget 1.20` ([budget wall](2026-09-04-budget-wall.md)) | certified, below family threshold | 1,913 (a different test) |
| `Corum` `a8a27ddfd7` (task `20260904-004851`) | `d18` ([numpy re-run](2026-09-04-numpy-under-the-thread-cap.md)) | certified, below family threshold | 1 (`b"\n"`) |

**One of the four was published.** The 2026-09-04 handoff reported three cases; the fourth was
created after it was written, by the `Corum` re-run of the same night. That is the erratum.

The executed test bytes were never lost — they are still on disk under
`.attest/repro/<task>/<candidate>/head-1/test_repro.py`, and they hash to the receipt's
`test_digest`. The bundles are **not** repaired with them: rewriting a sealed bundle after the
fact is the forgery the seal exists to prevent. They stay marked.

## 3. What the marker is

`unverifiable_v1.json` sits **beside** `manifest.json` and is deliberately not listed in it, so
the bundle's own digests remain exactly what was written. It records the verifier's reasons
verbatim, the family, the commit of the verifier that judged it, and — for the four — both the
receipt's `test_digest` and the digest of the bytes actually in the bundle.

## 4. What this does not say

- It is not an authenticity audit. A bundle that verifies proves internal consistency and a
  controller seal, not that the runs happened as described on a machine nobody controlled.
- The 38 schema-drift bundles are not evidence that their runs were wrong; they are evidence
  that the project has changed the receipt schema three times and did not carry the old ones
  forward. D-121 did that for intent policies only.
- The verifier used here runs from the workspace's current commit. A bundle's verdict is a
  verdict *under that code*, which is the whole point of the schema-drift row.
