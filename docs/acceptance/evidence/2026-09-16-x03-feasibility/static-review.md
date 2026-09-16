# X-03 prototype: single independent static security review

Reviewed baseline: `11400e8640410e90b7dd9c9e59a65b17386dbd41`, branch
`feature/git-query-profile`. Scope: `scripts/corpus/git_query_supervisor.c` and
`scripts/corpus/x03_supervisor_trial.py`, against `docs/implementation/x03-git-query.md`.
This is experimental feasibility code, not an admitted product execution profile.

## Findings

### High — child creation does not reject the untraced-clone flag

Location: `scripts/corpus/git_query_supervisor.c:231-246`, `:365-375`.

The clone predicate rejects only shared file tables and thread-group creation.
It does not reject `CLONE_UNTRACED`, whose purpose is to prevent a tracer from
forcing tracing on the newly created child. All admission, child limits, counting,
and later executable checks depend on receiving a ptrace child event. There is
no independent enforcement that every successful child-creation syscall produces
one registered child: the pending reservation is simply cleared at syscall exit
(`:268-270`). This leaves a concrete missing validation branch for an untraced
child, including its subsequent executable, descendants and output. The outer
Docker limits are broader than the promised child-chain contract.

Runtime status: **unverified**. No native bypass or adversarial container was run.
Whether the exact runtime independently rejects this flag was not established;
the prototype must not rely on an unrecorded outer-filter assumption.

Suggested fail-closed change: admit only an explicit set of clone flags that
preserves supervision, reject every other flag, and verify successful creation
against a registered event. A non-executing predicate unit test can cover
`CLONE_UNTRACED` and unknown bits without creating any child.

### Medium — environment check admits deletion and duplicate entries

Location: `scripts/corpus/git_query_supervisor.c:121-134`.

The function checks whether each observed entry is present in the trusted
environment (or is an allowed PWD), but never checks whether all required trusted
entries occur exactly once. Any nonempty subset passes; duplicate matching
entries pass as well. Thus controller-owned PATH, HOME, locale and other required
settings are not an exact contract. An omitted HOME or PATH can change ordinary
shell/Git lookup or configuration behavior even though executable hashing still
constrains the eventual executable. The current protocol does not record the
actual accepted environment either; no receipt completeness is claimed here.

Runtime status: **unverified**; directly visible predicate mismatch.
Suggested non-executing test: feed exact, missing-required, duplicate, unknown,
and PWD-adjusted vectors into the validator. Require exact unique entries with
an explicit optional-PWD rule.

### Medium — driver timeout has no daemon-side cleanup or failure checkpoint

Location: `scripts/corpus/x03_supervisor_trial.py:69-85`.

`subprocess.run(..., timeout=30)` bounds the Docker client, but the container is
not identified by a retained name/id and there is no cleanup `finally` block.
Killing the client after a timeout does not itself establish daemon-side
termination. `--rm` removes a container after termination; it is not a deadline.
The exception also occurs before writing that case's stdout/stderr or result
checkpoint. This makes a timed-out feasibility attempt both potentially live
and absent from the durable case record. Similar cleanup concerns apply to the
short trusted digest container, though its workload is much simpler.

Runtime status: **unverified**; no timeout experiment was run.
Suggested change: retain a unique container identity, stop/remove in `finally`,
and checkpoint timeout plus available bounded output before propagating failure.
A fake command-runner test can verify cleanup ordering without Docker execution.

## Additional limitations, not reproduced findings

- `PTRACE_GET_SYSCALL_INFO.arch` is never validated (`:223-230`); syscall numbers
  are interpreted using the supervisor's compile-time ABI. Bind and reject
  unsupported ABIs explicitly before any portability/admission claim. An
  alternative-ABI bypass on the pinned image was not established.
- The exec-event placement checks the installed image before its user code runs;
  it is a stronger ordering than inspecting mutable arguments before exec.
  Hashing `/proc/<pid>/exe`, exact argument vectors, event-held new children,
  ptrace/process-memory exclusions, and separate hex-encoded child streams are
  useful controls. Static review alone does not validate cross-process FD/memory
  closure, resource enforcement or complete trusted-output integrity.
- Receipt/adapter integration and a full escape matrix remain absent as already
  acknowledged. Root exit zero in the retained synthetic literal-query case is
  not Git success: its Python probe ignores Git's exit code, and the fixture has
  no Git repository. That record supports only the stated chain feasibility.

## Evidence and scope accounting

Inspected source, approved work order, AGENTS.md, DEVSPEND.md and the existing
`.attest/x03-supervisor-trial-r2/result.json`. No trial was rerun. One read-only
Docker context metadata command was issued; no container/image operation, native
reproduction, corpus execution, paid call or remote write was performed.
All findings above are static and explicitly unverified at runtime.

Native security verification was **not completed**. Product admission remains
blocked pending valid independent security evidence and the required integration
gates. This report completes only the requested resumed static review pass.

`git diff --stat`: empty for tracked files. Only this ignored report was added;
no source or tracked artifact changed. No reusable utility was reimplemented.
The driver already reuses `sha256_bytes` and `write_canonical_json` from the
provided inventory. This review adds no tool or measurement script.
