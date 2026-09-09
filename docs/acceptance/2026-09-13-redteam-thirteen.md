# G-SEC-002 red-team matrix on the production backend

Run 2026-09-09T21:43:56Z at `9657f40` on `Linux x86_64`, docker 28.0.4, profile `linux-container-v1`.
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
| read the host's process table and kernel state (/proc) | ran 1 head repeat(s) and probed the pid table, /proc/1/cgroup, /proc/kcore, /proc/sys/kernel/core_pattern and the mount table | `deferred` | yes | head run 1/3 deferred: reproduction attempted to write outside its work directory |
| read the operator's home, git identity and ssh keys | ran 3 head repeat(s) and opened thirteen home paths plus the reviewed tree's own .git directory | `not_reproduced` | yes | pytest passed on head in 3/3 runs; base not executed |
| issue syscalls through libc, under the Python audit hooks | ran 1 head repeat(s) and called libc socket(), connect(), fork(), mount() and ptrace() directly | `deferred` | yes | head run 1/3 deferred: reproduction attempted to create a child process |
| acquire capabilities through a user namespace | ran 1 head repeat(s) and called unshare(CLONE_NEWUSER|CLONE_NEWNS), remounted /, and setns() on /proc/1/ns | `deferred` | yes | head run 1/3 deferred: reproduction attempted to create a child process |
| forge a result | an executor returned an envelope bound to another request's nonce | `rejected` | yes | nonce mismatch: the result does not answer this request; artifact size mismatch for stdout.txt; artifact digest mismatch for stdout.txt |
| tamper with a sealed bundle | produced a real sealed bundle from a local differential, verified it, then rewrote its receipt's claim and verified the copy again | `rejected` | yes | digest mismatch for receipt.json; malformed bundle value: TypeError; the intact bundle verified |

**PASS** — 13 attack fixture(s), 13 actually dispatched, 1 positive control.

External observer: **INSUFFICIENT** (see above).


---

## What the four new rows add, and what they do not

**Owner instruction, phase 3 of the 2026-09-13 window.** `G-SEC-002` preregisters **thirteen**
attack classes and the matrix of 2026-09-03 dispatched **nine**. The four missing ones were
built and dispatched here; all four are `marked, not certified`, and the matrix reports
**PASS — 13 attack fixtures, 13 actually dispatched, 1 positive control** on the declared CI
platform (`Linux x86_64`, docker 28.0.4, `linux-container-v1`).

| class | attack surface | what the old matrix lacked | what the new fixture does |
|---|---|---|---|
| **`/proc`** | the host's process table and kernel state, visible through a shared or leaky `/proc` | the `keyfile` fixture opened `/proc/1/environ` looking for **one canary string**. That is a secret test that happens to touch `/proc`; it asks nothing about `/proc` itself | counts the visible pid table, reads `/proc/1/cgroup` for a host init, reads `/proc/kcore` (physical memory), **writes** `/proc/sys/kernel/core_pattern`, and looks for host paths in `/proc/self/mountinfo` |
| **home / git** | the operator's identity: `.gitconfig`, `.git-credentials`, ssh private keys, the `gh` token, and the reviewed tree's own `.git` | nothing. The `keyfile` fixture opens six paths, two of them under a home, and only for the canary | opens thirteen home paths across `/root`, `/home/runner`, `/github/home` and `~`, and separately asserts that `/attest/tree/.git` does not exist — a review reads a materialised tree, not a checkout |
| **native syscall** | everything under the Python audit hooks. `AGENTS.md` §4 says in its own words that the language-level process and network guards are *"best-effort containment, not a security boundary"* | nothing dispatched below Python. `socket`, `dns` and `processes` all go through the interpreter, so all three are consistent with a hook doing the refusing and the kernel doing nothing | `ctypes` into libc: `socket()`, `connect()`, `fork()`, `mount()` and `ptrace(PTRACE_ATTACH, 1)` |
| **namespace** | capability acquisition. A new user namespace hands out a full capability set inside it, and `setns` joins the host's | nothing | `unshare(CLONE_NEWUSER\|CLONE_NEWNS)`, a read-write `MS_REMOUNT` of `/`, `unshare(CLONE_NEWNET)`, and `setns()` on `/proc/1/ns/{net,mnt,pid}` |

### The one result that deserves a second look

**The `native` fixture was refused, and the reason it was refused is `reproduction attempted to
create a child process` — the product's own containment guard.** That is a genuine refusal and
the row is correctly marked. But it is *not* the answer the fixture was built to get: the
fixture goes under the Python audit hooks precisely to find out whether the **kernel** refuses,
and what actually happened is that the run deferred at its first repeat on a signal the product
raised. The same is true of `namespace`.

So the four new rows establish that **the boundary holds against these four classes on this
platform**, and they leave untouched the question of *which* boundary held — which is exactly
the `External observation: INSUFFICIENT` caveat already standing at the top of this matrix, now
applying to four more classes. The honest reading is in `SECURITY.md`.

**Nothing was skipped, nothing was xfailed, and no test was relaxed.** The matrix's verdict is a
conjunction over every attack row *and* the positive control certifying in the same backend in
the same run, so an undispatched fixture fails the matrix rather than passing it quietly.
