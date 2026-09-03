# G-RELEASE-001 operational drills

Run 2026-09-03T09:19:47Z at `3fcd232` by `scripts/release/drill.py`. Offline: no model call,
no real credential, no network beyond loopback. All nine named drills run.

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
| revoked credential | the review defers with a stated reason, it does not raise | pass | all provider samples failed or were malformed |
| revoked credential | the credential was actually used | pass | 2 call(s) |
| revoked credential | nothing is published | pass | 0 published |
| revoked credential | no evidence bundle is written | pass | 0 |
| revoked credential | no head code is executed | pass | .attest/repro does not exist |
| revoked credential | the credential value is in neither the ledger nor the author-visible text | pass | redacted |
| revoked credential | negative control: a working credential reaches a receipt | pass | 1 certified, 1 bundle(s) |
| GitHub outage | the run does not raise on an outage | pass | task 20260903-171915-3d3857ee |
| GitHub outage | no delivery is recorded as settled | pass | 2 event(s), 0 settled |
| GitHub outage | the receipt it earned is still on disk | pass | 1 bundle(s) |
| GitHub outage | the ledger names the outage | pass | delivery failure recorded |
| GitHub outage | an outage present at the start buys nothing | pass | 0 model call(s); deferred='GitHub comment: GitHub API request failed with HTTP 503' |
| GitHub outage | negative control: a reachable GitHub is written to | pass | 4 write(s) |
| executor unavailable | production has no backend and does not invent one | pass | profile=linux-container-v1; isolation backend unavailable: docker not found |
| executor unavailable | a local review says in as many words that there is no OS boundary | pass | docker not found; development host adapter (no OS boundary) |
| executor unavailable | the run does not raise | pass | task 20260903-171925-7dd9e526 |
| executor unavailable | nothing is surfaced | pass | 0 surfaced |
| executor unavailable | no evidence bundle is written | pass | 0 |
| executor unavailable | the deferral names the executor, not the finding | pass | isolation backend unavailable: docker not found |
| executor unavailable | negative control: with an executor the same change certifies | pass | 1 certified |
| budget exhaustion | the review defers on budget | pass | budget: call 'sample-0' estimated $0.0331; projected total $0.0331 exceeds budget $0.00 |
| budget exhaustion | no call was made | pass | 0 call(s) |
| budget exhaustion | nothing was spent | pass | $0.000000 |
| budget exhaustion | nothing is published | pass | 0 published |
| budget exhaustion | no evidence bundle is written | pass | 0 |
| budget exhaustion | the reason names the limit it hit | pass | budget: call 'sample-0' estimated $0.0331; projected total $0.0331 exceeds budget $0.00 |
| budget exhaustion | negative control: the default budget reaches a receipt | pass | 1 certified at $0.000540 |
| superseded pull request | evidence is refused when the workspace head is not the reviewed head | pass | workspace HEAD does not match the reviewed head |
| superseded pull request | the reason names the mismatch | pass | workspace HEAD does not match the reviewed head |
| superseded pull request | a dirty working tree buys no evidence either | pass | working tree is dirty; differential evidence requires immutable revisions |
| superseded pull request | negative control: the reviewed head reproduces | pass | head FAIL 3/3, base PASS 3/3 |
| malicious same-repository change | nothing is certified | pass | 0 certified |
| malicious same-repository change | nothing is published | pass | 0 published |
| malicious same-repository change | no evidence bundle is written | pass | 0 |
| malicious same-repository change | the run is marked, and the mark names what head code reached for | pass | head run 1/3 deferred: reproduction attempted a network connection |
| malicious same-repository change | head code did not write outside its work directory | pass | /Users/franz/.attest-drill-escape absent |
| malicious same-repository change | negative control: the benign version of the same change certifies | pass | 1 certified |
| verifier failure | a review of a real regression writes a bundle to verify | pass | 1 bundle(s); deferred=None |
| verifier failure | the intact bundle is accepted | pass | AcceptedReceipt |
| verifier failure | rejected: a bundle with no manifest | pass | BundleRejection |
| verifier failure | rejected: a bundle whose run records were removed | pass | BundleRejection |
| verifier failure | rejected: a receipt whose run outcomes were rewritten | pass | BundleRejection |
| verifier failure | rejected: a bundle whose test was swapped for a passing one | pass | BundleRejection |
| verifier failure | a copied bundle is refused when the seal is required and no key is present | pass | BundleRejection |

