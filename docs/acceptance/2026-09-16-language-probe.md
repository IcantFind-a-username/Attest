# P-01, 2026-09-16 — how much of Attest is bound to Python? A Go differential, measured

**Owner decision of 2026-09-16 (path B: a language-neutral evidence kernel, Python as the first
adapter).** This is a bounded probe, not a port. It changes nothing under `src/`, calls no model,
buys nothing, and pushes nothing. Instrument: `scripts/probe/go_execution_probe.py`. Record:
[`evidence/2026-09-16-language-probe/go-probe-p01.json`](evidence/2026-09-16-language-probe/go-probe-p01.json).

## 0. The answer

**A real Go differential runs through the product's own `Controller` and `ContainerAdapter`,
with six recorded workarounds, none of which is deep.** A two-revision Go module whose head
introduces an off-by-one: the module's own test **passes 3 of 3 on the parent and fails 3 of 3 on
the head**, in a read-only, network-none container, with the request minted and decoded by the
product's own execution protocol.

What that shows and does not show: the *execution* layer is close to language-neutral. The
*reading* layer -- what a probe is, where a failure came from, what the base tree specifies --
is Python source analysis and does not transfer at all.

## 1. The boundary, measured

| layer | lines | state |
|---|---:|---|
| certification kernel (`attest/certification/`) | 1,737 | **language-neutral**: imports only `hashlib`, `json`, `dataclasses`, `enum`, `re` |
| execution protocol and controller (`attest/execution/`) | 2,213 | **neutral by design** (image, argv, mounts, artifacts); six Python assumptions in the container adapter, listed below |
| modules that parse Python source (16 files, `import ast`) | 14,527 | **language-bound**: the intent observer, the contract reader and context screen, the tree index, the planner, impact, structural, tier0, eligibility |
| further modules naming pytest, junit or pip (14 files) | 10,765 | **language-bound** in part: the executor's probe rendering, junit parsing, image building, support detection |

About 25,000 of 58,600 lines are bound to Python by inspection; 3,950 lines are proven neutral by
this probe; the rest is orchestration this probe did not exercise.

## 2. The six workarounds the probe needed

Each is small, and each is in the container adapter rather than in the kernel:

1. **The isolation launcher is Python.** `NPROC_LAUNCHER_ARGV` is `python3 -I -c …`, prepended to
   every job, so every image must ship a Python interpreter whatever the repository is written in.
   One line of `sh` gives the same guarantee.
2. **A job reports through artifacts, not stdout.** `ExecutionResultEnvelope` carries no output, so
   each language needs its own report file and parser. Python writes `junit.xml`; the probe
   redirects `go test -json`.
3. **Interpreter identity runs `python3 -c` in the image.** A non-Python image has no answer; the
   probe uses the image id.
4. **`CONTAINER_PATH` is written for a Python image.** The Go toolchain lives at
   `/usr/local/go/bin`, so `PATH` had to be overridden through the request.
5. **The scratch and `/tmp` mounts are not executable.** An interpreted test never runs a file it
   just built; a compiled one always does. The probe adds `exec` to both.
6. **The isolation profile assumes a job that never forks.** `RLIMIT_NPROC` near zero and
   `DEFAULT_PIDS_LIMIT = 16`. A compiled language forks a compiler, and the Go runtime creates an
   OS thread per core: both bounds had to be raised (probe: no `RLIMIT_NPROC`, pid limit 256).

Findings 1 and 4 to 6 are one refactor: an **execution profile per language**, carrying the
launcher, the path, the process budget and the mount flags. Finding 2 is the adapter seam that
has to exist anyway. Finding 3 is two lines.

## 3. What a second language still needs, beyond this probe

The probe ran a test that already existed. A review needs four more things, and only the first is
mechanical:

- **build and run**: an image recipe and a test invocation per language, with a report parser.
- **failure origin**: today a Python tracer records where an exception was raised and which lines
  ran. Go has no equivalent hook; panics and `t.Fatalf` locations come out of the report text.
- **the probe**: the model writes a snippet that calls the changed symbol and records a value.
  For Python that is a rendered `pytest` file; for Go it is a generated test file in the module.
- **what the base tree specifies**: the whole intent rule reads Python syntax. A Go equivalent is
  a new reader, not a port.

## 4. What this decides

Path B is **structurally possible**: the kernel and the protocol are already neutral, and the
container layer is neutral after one refactor. It is **not cheap**: the reading layer, which is
where the last month of work went, does not transfer.

The honest ordering that follows: the language-neutral parts (differential execution, receipts,
offline verification) are the asset; the Python reading layer is one instance of an adapter, and
its depth should be treated as a cost, not a direction.

No recall figure, no product change, no default change follows from this probe.
