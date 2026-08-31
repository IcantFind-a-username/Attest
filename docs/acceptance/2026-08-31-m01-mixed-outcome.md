# M-01 mixed-outcome offline acceptance — 2026-08-31

Status: **Task 4 PASS; M-01 / `G-MEASURE-001` awaits Task 5 dual-Python closure.**

## Binding and protocol

- Baseline: `0e58cd61a1a63c51a329d5c1a5509181be32adfa`.
- Implementation: `b6caad7249dd32100cd6d96ae038bcdbfdc636c6`; clean source tree.
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

Task 5 must still run the exact final branch on Python 3.11 and 3.12, complete the full
coverage/static/integrity Gates, update the roadmap, and seal the final M-01 acceptance.
