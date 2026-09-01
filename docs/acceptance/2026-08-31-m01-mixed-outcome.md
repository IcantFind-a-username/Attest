# M-01 mixed-outcome offline acceptance — 2026-08-31

Status: **Task 4 PASS; Task 5 FAILED ENVIRONMENT (`ENOSPC`); M-01 /
`G-MEASURE-001` remains OPEN.**

## Binding and protocol

- Baseline: `0e58cd61a1a63c51a329d5c1a5509181be32adfa`.
- Implementation: `b6caad7249dd32100cd6d96ae038bcdbfdc636c6`; clean source tree.
- Final candidate: `5efe3d1c046fef04d197542cc8abe3f413a92d56`; clean source tree;
  `origin/main` `1f6f73eb72f5ed45b129c4d7ff937cc23b409e5c` is an ancestor.
- Probe SHA-256: `c73f57619d2d26d34ab49baac3b8f692c43cf211f8e84eb3638d5bd07e32d5dc`.
- Cassette SHA-256: `03837207dc3098226b594b55fcfc0c7328b84916fa9235e45cc83b03d46ce2e0`.
- Environment: Python 3.12.8, macOS 26.5.2 arm64; exact `env -i` allowlist.
- Design: one committed five-candidate mixed fixture; baseline repeat 0; current repeats
  0–19 exactly once; no replacement, retry, paid provider, or remote write.
- Raw bundle: [`evidence/2026-08-31-m01-offline-b6caad7249dd32100cd6d96ae038bcdbfdc636c6`](evidence/2026-08-31-m01-offline-b6caad7249dd32100cd6d96ae038bcdbfdc636c6).

## Result

| Check | Result |
|---|---|
| baseline legacy denominator | RC 1; stderr exactly `legacy_mixed_outcome_denominator` |
| current process outcomes | 20/20 RC 0; stdout/stderr empty |
| authoritative reducer | `semantic_n=1`; `operational_repeats=20` |
| mixed outcome | 5 candidates; 4 published; 1 unresolved; 1 partially deferred |
| isolation / semantic identity | 20 unique isolation digests; 1 semantic digest |
| aggregate receipt | SHA-256 `77899f8a69ce78c0d2d2b75c67554e48ff27595aa15f39bcc597a996391ccd9f` |

Each current file contains the original exact `MeasurementRecord` with repeat 0–19. The
committed aggregate command decoded all 20 and called `reduce_measurements` once. A fresh
`/private/tmp` aggregation was byte-identical to `aggregate.json`.

## Gates, review, and claims

- Fixed-SHA focused Gate: 228 passed; Ruff, mypy (49 source files), cassette checksum,
  and diff check passed.
- Independent implementation review and independent result review: P0/P1/P2 = 0/0/0.
- Offline verification: run `shasum -a 256 -c ARTIFACTS.sha256` inside the bundle.
- Permitted claim: on this constructed fixture, the current path retains four visible
  findings beside one unresolved candidate and reproduces the same semantic unit 20 times.
- Not claimed: public-data precision/recall, north-star architecture quality, production
  reliability, or host-wide network forensics. No paid call occurred.

## Task 5 final-candidate validation

The independent final review found one reproduced P1: a delivered non-`surface` placement
could enter benchmark predictions. Candidate `5efe3d1` requires the authoritative decision
action to be `surface` and reuses that authority for execution-measurement validation. The
same reviewer verified the counterexample plus normal inline/overflow paths and closed the
finding; final review status is P0=0/P1=0.

Fresh detached exact-SHA environments then each invoked full pytest exactly once. Python
3.11.5 reached 97% and Python 3.12.8 reached about 99%; both terminated with RC 120 when the
host data volume returned `ENOSPC`. Neither run emitted a final test count or usable total /
core coverage result, so `G-CODE-001` did not pass and M-01 cannot be accepted. No retry was
performed. Ruff, Mypy (49 files), `pip check`, diff/clean/provenance checks, and all three
frozen-v1 digests passed in both environments.

Raw Task 5 evidence is in
[`evidence/2026-08-31-m01-task5-5efe3d1`](evidence/2026-08-31-m01-task5-5efe3d1).
Its Python 3.11 and 3.12 manifests contain 121 and 49 verified entries; their manifest
SHA-256 values are respectively
`7b07e92e4f4a5c1eaba81a4d6e68a1b5b8b8543403d2a5bf169f7238b09da6f3` and
`7d0982bc9adbf9973055039035e0d56f36dae1f8fb848db039044457f42d60ba`.
The root manifest binds both inventories and its README; its SHA-256 is
`08fac53d75e55af2c4fbb010ae355c726e839abc41e25a56e6bf100336703f9f`.

## Bounded closeout

Implementation `dd37a8e` makes current benchmark readers strict and binds each delivered
finding/placement to one prior exact `ci_final` decision. Final candidate `5efe3d1` closes
the independent review's reproduced non-surface-delivery P1. The focused matrix, Ruff, and
Mypy passed, and final review has no unresolved P0/P1. D-049 nevertheless requires an honest
handoff: the one dual-Python full-Gate attempt per interpreter failed on host storage before
coverage could be measured. This report is therefore **not** `G-CODE-001` or final
`G-MEASURE-001` acceptance.
