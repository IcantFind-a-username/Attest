# numpy imports again: three environment variables, and `Corum` goes from 0 of 4 to 4 of 4

**Owner instruction 4 of 2026-09-04.** The 2026-09-03 corpus lost every `Corum` candidate to
the same environmental failure: numpy could not be imported inside `linux-container-v1`, so
each candidate deferred at collection before any evidence was bought. This is the fix, its
reproduction, and the re-run.

## 1. The failure, reproduced with the backend's own flags

`linux-container-v1` sets **`RLIMIT_NPROC = 0`** inside the container (a launcher does it
before `exec`), which is the containment the language guard's kernel-containment check
depends on. OpenBLAS, which numpy links, asks the kernel for one thread per core at import:

```
OpenBLAS blas_thread_init: pthread_create failed for thread 1 of 12: Resource temporarily unavailable
OpenBLAS blas_thread_init: ensure that your address space and process count limits are big enough (ulimit -a)
OpenBLAS blas_thread_init: or set a smaller OPENBLAS_NUM_THREADS to fit into what you have available
OpenBLAS blas_thread_init: RLIMIT_NPROC 0 current, 0 max
```

`import numpy` then dies. It is not a timeout and it is not the generated test's fault.

Reproduced directly against the `Corum` image with the adapter's exact flags — `--network
none --read-only --user 65534 --cap-drop ALL --security-opt no-new-privileges --pids-limit 16`
plus the `RLIMIT_NPROC = 0` launcher — and repaired by the three variables alone:

| environment | `import numpy` | `import scipy` | `import corum` |
|---|---|---|---|
| as shipped | **fails**, `blas_thread_init` | not reached | not reached |
| `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1` | **ok** (2.5.2) | **ok** | **ok** |

## 2. The fix

Three variables in `_reproduction_environment`, the explicit secret-free job environment the
request names. **The thread limit is not raised.** Raising `RLIMIT_NPROC` would relax the
boundary that `INV-SEC-001` and the guard's own containment check stand on; telling a BLAS to
want one thread relaxes nothing and asks the kernel for nothing. Of the two options the owner
offered, this is the one that keeps the boundary.

The variables change the job's `environment_digest`, so receipts written before this change
keep their own recorded digest and still verify from their own bundles; new receipts record
the new one.

## 3. The re-run: `Corum`, four pairs, `--budget 0.60` (non-default), `linux-container-v1`

| pair | head | eligible | verifications | reproduced | receipts | **published** | spend |
|---|---|---|---|---|---|---|---|
| `d17` | `6eba742235` | 2 | 2 | 1 | 1 | **1** | $0.1831 |
| `d18` | `ba8fddb952` | 4 | 4 | 4 | 4 | **1** (3 suppressed as the same defect) | $0.1418 |
| `d19` | `515998fac1` | 1 | 1 | 1 | 1 | **1** | $0.0343 |
| `d20` | `5be583d614` | 1 | 1 | 1 | 1 | **1** | $0.0454 |
| **total** | | 8 | 8 | **7** | **7** | **4** | **$0.4046** |

Against the same four pairs on 2026-09-03: **9 verifications, 0 reproduced, 0 receipts,
0 published, $0.5622** — every one lost at collection to the numpy import.

**0 of 4 pairs to 4 of 4, and cheaper**, because a run that fails at collection still pays for
the generation that produced the test. Every run went through `linux-container-v1`. No
`blas_thread_init` line appears anywhere in the new ledger.

## 4. What this does not establish

- **It is not a recall measurement.** Four defect pairs in one repository, chosen because they
  failed environmentally, are the most favourable possible sample: they were *known* to be
  blocked by one cause, and that cause was removed. `G-RECALL-002` is untouched.
- **It is not a null result.** No control was run; `Corum`'s controls do not qualify under the
  2026-09-04 rule (D-122) and neither does anything else this account owns.
- **The fixture test did not run to completion on this host.**
  `tests/execution/test_linux_isolation.py::test_a_project_that_imports_numpy_runs_inside_the_container`
  is committed as the docker-gated regression guard, and its image (a tree declaring numpy)
  did not finish building here inside the window. The fix's evidence is §1's direct container
  reproduction and §3's end-to-end re-run, not a green fixture — stated plainly rather than
  implied.

## Correction, 2026-09-04 (D-124)

One of the seven receipts — `Corum` `a8a27ddfd7` on `d18`, certified and suppressed below the
family threshold — has an evidence bundle that does not verify offline: its `test_repro.py` is a
single newline, the first generation's empty output, while the receipt names the test that ran
([re-verification](2026-09-04-bundle-reverification.md)). Under the fix it would have been
refused. The corrected count is **6 verifiable receipts, not 7**; **all four published receipts
verify**, so `0 of 4 pairs → 4 of 4` and `0 → 4 published` are unchanged.
