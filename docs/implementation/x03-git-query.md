# X-03: approved experimental fixed Git query

Owner approval on 2026-09-16 selected the bounded contract recorded below. This
permission is for implementation and evaluation, not evidence that the profile is
safe or ready. Keep process-free execution and default intent v5.1 unchanged.
No API cap increase, release, push or writes to third-party repositories.

## Contract

Allow only the literal shell query `git log --pretty=format:%ct --quiet -1 HEAD`,
with controller-owned executable paths, digests, arguments, environment and cwd.
The shell and Git process chain has at most two new processes, depth two, no
additional descendants, five-second CPU/wall limits, 128 MiB child memory and
16 KiB captured output. Source and root stay read-only, network disabled, no
controller credentials exposed, fresh scratch. Bind every child and actual
execution policy in the receipt. No repository-configurable relaxation.

An OS-enforced boundary must constrain direct native syscalls too. A Python
allowlist, model approval or an after-the-fact child marker is insufficient.
Missing capability refuses. Default profile remains process-free; the new
profile cannot be enabled until X-03's escape tests, independent review and
integration gates pass. No corpus source patch or fake subprocess result.

## First bounded step

Before implementation, run the committed x03_platform_preflight.py once using
the already pinned runtime image. It reads the Linux/kernel architecture and
probes seccomp notification sizing, Landlock ABI and child ptrace availability
inside the existing non-root, capability-free, network-free Docker boundary.
It executes only a trusted synthetic probe, not project code. Its result is
platform feasibility, not security acceptance or product performance.

Study existing syscall-supervisor implementations before building a new one.
Sandlock (https://github.com/multikernel/sandlock) is a dependency candidate only,
not yet selected or trusted. Its documented process tracking and argument freeze
may help implement the approved contract; pin and inspect source and prove the
escape matrix before depending on it. Do not weaken host policy to make it run.
Any dependency checkout must live under this worktree's ignored .attest/corpora/.

Primary references:
- Linux seccomp: https://www.kernel.org/doc/html/next/userspace-api/seccomp_filter.html
- User notification limitations: https://man7.org/linux/man-pages/man2/seccomp_unotify.2.html
- Docker boundary: https://docs.docker.com/engine/security/seccomp/
- Existing work order: agent-work-orders.md, X-03.

The approved paid objective remains unchanged. All twelve frozen revisions have
built, but none has completed original defect qualification. Runtime readiness,
matched filenames or a passing synthetic probe must not be counted as recall.
