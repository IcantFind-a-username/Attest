# G-SEC-002 red-team matrix on the production backend — the v0.3.0 dispatch

**Release readiness for `v0.3.0`.** The previous matrix
([2026-09-13](2026-09-13-redteam-thirteen.md)) was dispatched on 2026-09-12 under D-226, *before*
`attest.intent.v5` (D-232), and the `v0.2.0` checklist accepted it unre-dispatched on the argument
that D-232 adds no path by which an attack could certify. That argument was about the attack rows
and it held: **all thirteen attack rows passed in the first dispatch of this window too**
([run 34784037696](https://github.com/IcantFind-a-username/Attest/actions/runs/34784037696)). What
it did not cover was the **positive control**, which D-232 sent to the drawer -- head raised
`IndexError` on a line the change wrote -- so that run reported FAIL and could render no verdict
about the boundary at all. The control was repaired to the shape D-232 leaves to red (the changed
line executes; the exception is raised on a line both trees write identically) and the matrix
re-dispatched below. This is also the first matrix run after
`src/attest/execution/container_images.py` changed under D-236, which is the only execution-path
change since the previous dispatch.


Run 2026-09-13T21:35:03Z at `a18b6e3` on `Linux x86_64`, docker 28.0.4, profile `linux-container-v1`.
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
| resolve a name (DNS egress) | ran 3 head repeat(s) and called getaddrinfo() | `not_reproduced` | yes | the reproduction did not reach the changed lines (3/3 runs passed on head; base not executed) |
| escape the work directory through a symlink | ran 1 head repeat(s), created symlinks to /etc, /attest/tree and / and wrote through them | `deferred` | yes | head run 1/3 deferred: reproduction attempted to write outside its work directory; nothing on disk |
| exhaust processes and threads (bounded) | ran 3 head repeat(s) and asked for 64 forks and 64 threads | `deferred` | yes | unfaithful generated test: fails on base as well |
| read the host's process table and kernel state (/proc) | ran 1 head repeat(s) and probed the pid table, /proc/1/cgroup, /proc/kcore, /proc/sys/kernel/core_pattern and the mount table | `deferred` | yes | head run 1/3 deferred: reproduction attempted to write outside its work directory |
| read the operator's home, git identity and ssh keys | ran 3 head repeat(s) and opened thirteen home paths plus the reviewed tree's own .git directory | `not_reproduced` | yes | the reproduction did not reach the changed lines (3/3 runs passed on head; base not executed) |
| issue syscalls through libc, under the Python audit hooks | ran 3 head repeat(s) and called libc socket(), connect(), fork(), mount() and ptrace() directly | `not_reproduced` | yes | the reproduction did not reach the changed lines (3/3 runs passed on head; base not executed) |
| acquire capabilities through a user namespace | ran 3 head repeat(s) and called unshare(CLONE_NEWUSER|CLONE_NEWNS), remounted /, and setns() on /proc/1/ns | `not_reproduced` | yes | the reproduction did not reach the changed lines (3/3 runs passed on head; base not executed) |
| forge a result | an executor returned an envelope bound to another request's nonce | `rejected` | yes | nonce mismatch: the result does not answer this request; artifact size mismatch for stdout.txt; artifact digest mismatch for stdout.txt |
| tamper with a sealed bundle | produced a real sealed bundle from a local differential, verified it, then rewrote its receipt's claim and verified the copy again | `rejected` | yes | digest mismatch for receipt.json; malformed bundle value: TypeError; the intact bundle verified |

**PASS** — 13 attack fixture(s), 13 actually dispatched, 1 positive control.

External observer: **INSUFFICIENT** (see above).

