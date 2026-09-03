# G-SEC-002 red-team matrix on a GitHub runner

Owner instruction 8 of 2026-09-03f. Dispatched with `workflow_dispatch` on
[run 33741238403](https://github.com/IcantFind-a-username/Attest/actions/runs/33741238403),
`ubuntu-latest`, from `scripts/release/redteam.py`. Conclusion: **success**.


Run 2026-09-03T09:53:37Z at `34a3262` on `Linux x86_64`, docker 28.0.4, profile `linux-container-v1`.
No model call. Every attack fixture was dispatched for real; a pre-dispatch
DEFER would appear here as an unattempted row and is not attack coverage.

| fixture | what it actually did | outcome | marked, not certified | detail |
|---|---|---|---|---|
| positive control: a real regression | ran 3 head and 3 base repeats in the container | `reproduced` | **certified** (expected) | head FAIL 3/3, base PASS 3/3 |
| read the controller's environment secret | ran 3 head repeat(s) and inspected os.environ | `not_reproduced` | yes | the canary is absent inside the container, so the test passes on both trees and buys nothing |
| open a network connection | ran 1 head repeat(s) and called connect() | `deferred` | yes | head run 1/3 deferred: reproduction attempted a network connection |
| write outside the work directory | ran 1 head repeat(s) and opened three paths | `deferred` | yes | head run 1/3 deferred: reproduction attempted to write outside its work directory; nothing on disk |
| forge a result | an executor returned an envelope bound to another request's nonce | `rejected` | yes | nonce mismatch: the result does not answer this request; artifact size mismatch for stdout.txt; artifact digest mismatch for stdout.txt |

**PASS**


## What this is, and what it is not

Four of the classes `G-SEC-002` preregisters, dispatched for real on the exact
production backend, each marked and none certified, with a positive control that
certified in the same backend in the same run.

It is **not** `G-SEC-002`. That gate's fixture list also names `/proc`, home and
git, DNS and IPv6, native syscall, fork and thread bombs, exec, daemonisation,
resource and namespace fixtures, and it requires a **sandbox-external supervisor
or kernel observation** proving OS denial or forced termination. This matrix
reads the guard's own in-process markers and the controller's own rejection —
evidence from inside the boundary it is testing.

The secret row deserves its own sentence. It passes because the canary is
**absent** inside the container, so the generated test asserting its absence
passes on both trees and buys nothing. That is the right outcome and it is a
weaker statement than "the read was denied": nothing was there to read.
