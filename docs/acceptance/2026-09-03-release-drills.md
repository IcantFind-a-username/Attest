# G-RELEASE-001 operational drills (kill switch, rollback)

Run 2026-09-03T04:31:56Z at `b58ffb7` by `scripts/release/drill.py`. Offline: no model call,
no credential, no network. Seven of the nine named drills are not implemented.

| drill | check | result | detail |
|---|---|---|---|
| kill switch | base policy owns the switch; the head cannot flip it | pass | resolved enabled=False from base:.attest.toml |
| kill switch | review defers | pass | disabled by the base policy (.attest.toml enabled = false) |
| kill switch | no model call | pass | 0 call(s) |
| kill switch | nothing spent | pass | $0.000000 |
| kill switch | no candidate reached ranking | pass | 0 result(s) |
| kill switch | no evidence bundle written | pass | .attest/evidence is empty |
| kill switch | negative control: the switch on lets the review run | pass | 5 call(s), deferred=None |
| rollback | a review of a real regression writes an evidence bundle | pass | 1 bundle(s); deferred=None |
| rollback | the bundle verifies offline as written | pass | AcceptedReceipt |
| rollback | an unknown bundle schema version is rejected, not misread | pass | BundleRejection |
| rollback | negative control: a flipped byte is rejected | pass | BundleRejection |
| rollback | the documented oldest rollback target resolves | pass | v0.1.0-pilot.1 -> eedb656ccdd689b67b372c0596a1b473bcb6363f |

