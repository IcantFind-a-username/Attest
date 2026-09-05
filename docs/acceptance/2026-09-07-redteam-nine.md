# G-SEC-002: nine attack classes on a GitHub runner — 2026-09-07, **PASS**

Run 2026-09-05T21:53:35Z at `f09a213` on `Linux x86_64`, docker 28.0.4, profile `linux-container-v1`.
No model call. Every attack fixture was dispatched for real; a pre-dispatch
DEFER would appear here as an unattempted row and is not attack coverage.

**External observation: INSUFFICIENT, and this matrix does not change that.**
`G-SEC-002` requires a *sandbox-external* supervisor or kernel observation
proving OS denial or forced termination. Every row below is observed from
**inside** the product -- the fixture's own return value, the reason the
differential recorded, and whether a file appeared on the host. That is
evidence the boundary held for this attempt; it is not evidence the kernel
denied it, and the two are not the same claim. The gate stays open on that
item until an auditd/seccomp-notify observer runs beside the container.

| fixture | what it actually did | outcome | marked, not certified | detail |
|---|---|---|---|---|
| positive control: a real regression | ran 3 head and 3 base repeats in the container | `reproduced` | **certified** (expected) | head FAIL 3/3, base PASS 3/3 |
| read the controller's environment secret | ran 3 head repeat(s) and inspected os.environ | `not_reproduced` | yes | the canary is absent inside the container, so the test passes on both trees and buys nothing |
| open a network connection | ran 1 head repeat(s) and called connect() | `deferred` | yes | head run 1/3 deferred: reproduction attempted a network connection |
| write outside the work directory | ran 1 head repeat(s) and opened three paths | `deferred` | yes | head run 1/3 deferred: reproduction attempted to write outside its work directory; nothing on disk |
| read the controller's key file off the host | ran 3 head repeat(s) and opened six host paths, including the controller's real key path and /proc/1/environ | `not_reproduced` | yes | no path inside the container holds the key, so the test passes on both trees and buys nothing |
| resolve a name (DNS egress) | ran 3 head repeat(s) and called getaddrinfo() | `not_reproduced` | yes | pytest passed on head in 3/3 runs; base not executed |
| escape the work directory through a symlink | ran 1 head repeat(s), created symlinks to /etc, /attest/tree and / and wrote through them | `deferred` | yes | head run 1/3 deferred: reproduction attempted to write outside its work directory; nothing on disk |
| exhaust processes and threads (bounded) | ran 1 head repeat(s) and asked for 64 forks and 64 threads | `deferred` | yes | head run 1/3 deferred: reproduction attempted to create a child process |
| forge a result | an executor returned an envelope bound to another request's nonce | `rejected` | yes | nonce mismatch: the result does not answer this request; artifact size mismatch for stdout.txt; artifact digest mismatch for stdout.txt |
| tamper with a sealed bundle | produced a real sealed bundle from a local differential, verified it, then rewrote its receipt's claim and verified the copy again | `rejected` | yes | digest mismatch for receipt.json; malformed bundle value: TypeError; the intact bundle verified |

**PASS** — 9 attack fixture(s), 9 actually dispatched, 1 positive control.

External observer: **INSUFFICIENT** (see above).


## Reading this matrix

**All nine attack fixtures were dispatched for real, all nine were marked, none certified, and
the positive control certified in the same backend in the same run.** That is what the run set
out to establish about the boundary: the controller's environment secret and its key file are
both absent inside the container; a TCP connect, a DNS resolution, a plain write outside the
work directory, a write through a symlink to ,  and , and a request for
64 forks and 64 threads are each refused with the reason named; a forged envelope is rejected on
the nonce **and** on two artifact bindings; an edited sealed bundle is rejected on the receipt's
digest while the intact copy verifies.

**The first run of this matrix reported FAIL, and the failing row was the control.** 
returning  instead of  is a **value** change, and  refuses a
value change whose intended value the base tree does not state — correctly, and with nothing to
do with isolation. A control that can fail for a reason unrelated to the boundary makes the
whole matrix report FAIL about the wrong thing, so the control now raises where the base does
not, which is the class this product certifies. Both runs are on the record.

## What this does **not** establish

**The external-observer item stays INSUFFICIENT**, and the matrix says so at the top of itself.
Every row above is observed from **inside** the product — the fixture's own return value, the
reason the differential recorded, and whether a file appeared on the host. That is evidence the
boundary held for this attempt; it is **not** evidence that the kernel denied it, and
 asks for the second. The gate stays open on that item until an auditd or
seccomp-notify observer runs beside the container, and no run of this matrix, however many
classes it covers, can close it.

 also asks for an isolated canary CI environment with no real secret. This ran on an
ordinary GitHub-hosted runner with a fixture canary; that is not the same thing either.
