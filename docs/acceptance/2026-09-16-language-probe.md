# P-01 and P-02, 2026-09-16 — how much of Attest is bound to Python? Two Go probes, measured

**Owner decision of 2026-09-16 (path B: a language-neutral evidence kernel, Python as the first
adapter).** This is a bounded probe, not a port. It changes nothing under `src/`, calls no model,
buys nothing, and pushes nothing. Instruments: `scripts/probe/go_execution_probe.py` and `go_certification_probe.py`. Records:
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

## 4. P-02: the kernel accepts a Go regression on Go-derived evidence

The second probe (`scripts/probe/go_certification_probe.py`,
[record](evidence/2026-09-16-language-probe/go-probe-p02.json)) asks what the *kernel* demands.
A Go module whose head drops a length guard, a generated probe test in Go, three repeats per
revision, and then the kernel's own records filled from what Go reported:

| record | filled from | verdict |
|---|---|---|
| the differential | three repeats per side | parent passes 3/3, head fails 3/3 |
| `BindingObservation` | the changed line in the panic trace of every head run | bound |
| `IntentObservation` (`attest.intent.v5.1`, unchanged) | origin line 5 = the changed line, type `runtime error: slice bounds out of range`, the input `"ab"` witnessed in the repository's own base test | publishes |
| `CertificationReceipt` | the runs, digests and provenance digest | **`AcceptedReceipt`**, no rejection codes |

**The shipped kernel, the shipped binding policy and the shipped intent rule accepted a Go
regression with no change to any of them.** That is the strongest evidence so far that the
valuable half of this project is not Python-specific.

What the probe had to work out, each recorded rather than smoothed over:

- **A Go test must live inside its module**, so the probe cannot be an input mount the way the
  rendered `pytest` file is: the tree the container sees is a writable copy with the probe in it.
- **Coverage and the failure trace cannot come from one Go run**: `go test -coverprofile` writes
  nothing when the binary panics. The probe reads the executed changed line from the trace, which
  is stronger evidence than a counter, but it is a different mechanism from the Python tracer.
- **`origin_statement` names a Python statement kind** (`raise`, `assert`). Go has none, so the
  record says `other`; v5.1's frame rule accepts it, and the record carries less than Python's.
- **`exception_type` is a panic message, not a type name**, so D-235's warning rule
  (names ending in `Warning`) has no Go counterpart.
- **The run vocabulary is fixed** (`passed`/`failed`, one failure signature shared by every head
  run, `collected_count == 1`): Go's panic message needed its addresses stripped to be stable.

**One fail-open, worth naming.** The first version of the probe recovered the panic inside the
generated test, so no origin reached the report and the observation was left empty. An empty
`IntentObservation` under v5.1 has no rejection and no value mismatch, so no rule applies and
`intent_verdict` returns None: **it publishes**. The kernel is not wrong -- an observation is a
record of what was observed -- but it means the safety of a new adapter rests entirely on that
adapter filling the record honestly. A language adapter needs its own test that an unobserved
failure cannot certify.

## 5. What this decides

Path B is **structurally possible**: the kernel and the protocol are already neutral, and the
container layer is neutral after one refactor. It is **not cheap**: the reading layer, which is
where the last month of work went, does not transfer.

The honest ordering that follows: the language-neutral parts (differential execution, receipts,
offline verification) are the asset; the Python reading layer is one instance of an adapter, and
its depth should be treated as a cost, not a direction.

No recall figure, no product change, no default change follows from these probes. What they
settle is narrow and useful: the kernel, the binding policy and the intent rule are already
language-neutral, the container layer needs one refactor, and everything that reads source is a
per-language adapter that has to be written from scratch. The next decision is whether that
adapter is worth writing for a second language, and P-02's fail-open says the first thing it must
carry is its own proof that an unobserved failure cannot certify.
