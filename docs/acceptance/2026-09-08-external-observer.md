# `G-SEC-002`'s external observer: the kernel's record, beside the harness's

**Owner instruction 3 of 2026-09-07.** Data:
[observer](evidence/2026-09-08-observer.json) ·
[arming and its control](evidence/2026-09-08-observer-arm.json) ·
[the matrix it observed](2026-09-08-redteam-observed.md) · driver
`scripts/release/observer.py` · GitHub runner, kernel `6.17.0-1022-azure`, run
`34014635971`. **$0.00** — no model call, no credential, no spend.

## The gap it addresses

Every row of the nine-class red-team matrix is observed **from inside the product**: the harness
dispatches an attack, the harness reads the result, and the harness writes down that the boundary
held. The 2026-09-07 matrix says so about itself, and the external-observer item stays
`INSUFFICIENT`. No number of additional attack classes changes that, because each new row is
observed the same way.

## What was built

The Linux kernel's audit subsystem records the syscalls the container's processes make; the
comparison then reads **the kernel's log**, not anything attest wrote. `attest` is not imported
by the observer, and the container's uid is written into it as a literal rather than read from
the module it observes.

The audit subsystem and **not** a seccomp `SCMP_ACT_LOG` profile, because handing `docker run` a
different security configuration measures a different container. An audit rule attaches to the
host kernel and changes nothing about the container: the product's argv is byte for byte what it
always is.

Three steps, because the privileges are opposite — audit rules need root and the matrix must not
have it:

```
sudo observer arm                       # install the rules, print an epoch mark
python scripts/release/redteam.py ...   # the matrix, unprivileged, under those rules
sudo observer collect --since <mark>    # read the kernel's log, compare, disarm
```

## The result

**945 kernel records at the container's uid**, across a run in which all nine attack fixtures
were dispatched for real and the matrix returned `PASS`:

| syscall | records | the fixture that asked for it |
|---|---|---|
| `openat` | **939** | every fixture; the reproduction reads its tree |
| `execve` | **4** | the container's own entry and the job's interpreter |
| `unlink` | **2** | the escape and symlink fixtures |
| **`socket`** | **0** | *open a network connection*, *resolve a name (DNS egress)* |
| **`connect`** | **0** | *open a network connection* |
| **`clone`** | **0** | *exhaust processes and threads (bounded)* |
| `unlinkat` | 0 | — |

**The kernel says no network syscall was made at the container's uid, and no process was
cloned.** The harness said those three fixtures were refused. Those are now two independent
statements that agree, and the second one is not the product's.

That is stronger than *"the connection failed"*: `--network none` would have made a `connect`
fail, and the guard inside the container refuses the attempt before the syscall is issued at all.
The kernel confirms the syscall was never made.

## The control, and why zero records used to mean nothing

The first two runs recorded **zero** records, which is equally consistent with *"the boundary
held"*, *"the rule set does not work"* and *"the container is not running at the uid the rule
filters on"*. Two things now separate them, and both are in the arming record:

- a **marker process** at the container's uid that makes a watched syscall (`execve /bin/true`),
  and a second rule on `execve` with **no uid filter** at all;
- the loaded rule list, read back from `auditctl -l`.

On this run the marker ran, both rules were loaded, 945 records came back under the uid-filtered
rule and 111 under the unfiltered control. A run that recorded neither would say the observer is
broken, which is also worth knowing and was not knowable before.

## Three things it took to get here, all on the record

1. **The matrix must not run as root.** The first attempt ran the whole thing under `sudo`, and
   the product's own containment guard refused every fixture — *"process containment unavailable
   for privileged POSIX user"*: `RLIMIT_NPROC = 0` does not bind a privileged uid. A matrix of
   refusals observed by a kernel that saw no container is evidence of nothing (run
   `34014105381`).
2. **`ausearch` reported `<no matches>` for a key the raw log carried 1,060 times.** The kernel
   was recording the whole time; the reader was not reading. `ausearch` is now out of the path
   entirely and `collect` parses `/var/log/audit/audit.log` itself — one fewer intermediary
   between the record and the comparison, which is the point of an external observer (runs
   `34014269289`, `34014406650`, `34014499400`).
3. **The control key is a prefix of the rule key.** `attest-observer` is a substring of
   `attest-observer-any`, so a substring match would have counted the control as the thing it
   controls. The reader matches the quoted `key="..."` field exactly.

## What this does not establish

- **It does not show that nothing else happened.** Audit records what its rules match, and the
  seven watched syscalls are a list someone chose. A syscall outside that list is invisible here.
- **It does not audit the runner.** The rules filter on the container's uid, so a host process
  doing anything at all is out of scope by construction.
- **It is one run of one matrix on one kernel.** `6.17.0-1022-azure`, `ubuntu-latest`, x86_64.
  The `b32` rule loaded but no 32-bit syscall was recorded, because nothing 32-bit ran.
- **It observes, it does not enforce.** Nothing here would have *stopped* an attack; it records
  what the enforcement did.

## `G-SEC-002` after this run

Condition 3 of the `v0.1` list reads *"head code cannot read secrets, reach the network, or forge
a result"*. The class coverage is unchanged at **9 of 13**. What changed is the part no number of
classes could move: **the external-observer item is no longer `INSUFFICIENT` for the network and
process-creation claims** — a record written by the kernel, outside the product, agrees with the
harness about them. The remaining four fixture classes, and observation of the claims this rule
set does not watch, are still outstanding.
