# Separate independent SWE-bench study: six candidates frozen

E-02 preparation, D-269. Owner approved the D-268 proposal with “允许”. Baseline `4697d98`;
metadata protocol `2b3beff`, fetch driver `4b58b3d`, candidate freeze `8ad0236`, immutable-source
verification driver `df70991`. All commits are local. Actual model/API spend **$0**.
The old 20-case pool and its failures remain unchanged and separately reported.

| Repository | Contemporary prior-heldout pool | Frozen instance IDs |
|---|---:|---|
| astropy/astropy | 13 | 14369, 13236, 13398 |
| scikit-learn/scikit-learn | 7 | 25232, 25973, 26323 |

The [protocol](../../benchmarks/studies/swebench-independent-v1/protocol.md) fixes a
2022-or-later stratum before fetching new data. Each repository contributes its first three
under the declared hash ordering. All six were held out in the original split; none is new
development data. No runtime, oracle, gold patch or product outcome selected these instances.
This is a small exploratory contemporary study, not the 120+120/20-repository acceptance gate.

## Independence and provenance

The [single independent review](../../benchmarks/studies/swebench-independent-v1/independent-review.md)
recomputed all selections and checked baseline references, including sklearn/underscore
aliases missing from the driver's generated aliases. Earlier selected-repository mentions
were administrative exclusions/split entries. A packaging test mentioning scikit-learn is
requirement-name normalization metadata, not scikit-learn source evaluation. The clone audit
reconciles all 23 existing origin records and finds neither selected repository. This is
absence of substantive exposure in the stated audit, not a claim about pretrained models,
removed clones, unrecorded access or all prior human knowledge.

Dataset-server responses initially had an unproven link to the recorded dataset revision.
After review, the controller downloaded the Parquet at immutable revision
`c104f840cc67f8b6eec6f759ebc8b2693d585d4a` and read only the five metadata columns. All
500 projected rows exactly match the metadata used to freeze the sample. The original server
record remains unchanged; [the additional check](../../benchmarks/studies/swebench-independent-v1/pinned-metadata-check.json)
binds the Parquet digest, projection and tool version. Raw data stays ignored with mode 0600;
hidden columns were not exposed to the model or inspected as source. The supplemental pinned
check was controller-validated after the one review; no second review pass is claimed.

[Validation and artifact hashes](../../benchmarks/studies/swebench-independent-v1/validation.json)
cover split, metadata, scripts, protocol versions, clone audit and pinned-source check. Ruff
and diff checks pass. No product source/tests changed and no full product gate was rerun.
No selected project source was accessed or executed in this freeze task. The original
protocol digest binds its committed pre-fetch version; the later provenance verification is
an explicit append-only section, not an altered sample rule.

## Next step and spend

Qualified defects and controls are still **zero**: these six rows are candidates. Qualify
runtime and original hidden tests, resolve natural forward pairs and eligible evidence class,
and freeze at least equal reasonable-change controls with independent semantic review before
paying. Repair reversal is not natural forward performance; D-135 still applies. Target six
plus six; preregistered minimum three defects plus three controls across two repositories.
If that minimum cannot be qualified/funded, report the shortfall without paid dispatch or
silent replacements. The full paid protocol and same-workflow free artifact smoke remain due.

Owner approval permits this separate study and eventual paid evaluation within existing
DEVSPEND headroom, not a cap increase or a release. No paid reservation is created here.
The final paid report ends the round; do not tune on it or begin another study afterward.
