# Independent archive provenance review

Scope: one review pass of the bounded NumPy source archive recovery for the frozen
keras/8 development prerequisite. Baseline `4558bff9ef5396ebc7318d65b3f0216f1dbeb088`;
reviewed protocol commit `e1801072879f0de4a6121ec4e06840a535354247` on
`chore/recover-numpy-archive`. Reviewed the protocol, source/recovery evidence JSON,
saved release JSON and named local archive. No other corpus inputs were read.

## Findings

No correctness or provenance-consistency findings (no severity-ranked defects).
The local source distribution matches the checksum in the saved official release
body and committed protocol. This establishes the bounded recovery claim only.
The saved release metadata is not an independently signed historical provenance
record; the evidence explicitly retains that limitation.

## Validation

- Shared `attest.benchmark.artifacts.sha256_bytes` independently reproduced archive
  SHA-256 `39814c52f65c89385028da97da574d5e2a74de5c52d6273cae755982c91597bc`.
- Local length and official asset size agree at 6,768,712 bytes; release ID
  `27080520`, asset ID `21236670`, asset URL/name and saved metadata fields agree.
- Raw release JSON digest and committed protocol digest match recovery evidence;
  the release body checksum line names the exact archive.
- Python `tarfile` read only the regular-file member
  `numpy-1.19.0rc2/PKG-INFO`; `email.parser.BytesParser` confirmed package `numpy`,
  version `1.19.0rc2`, and the recorded PKG-INFO digest.
- Validation command: `PYTHONPATH=src .venv/bin/python -` with assertions comparing
  these existing fields, then `git diff --check`; both passed.
- Claims explicitly exclude binary recovery, original build-environment equivalence,
  installability, reproduction, certification and performance. Product evaluations
  and oracle tests remain zero in the supplied evidence.

No archive extraction, package import, installation, build, test, network call,
paid model call or remote write was performed during this review. Validation ran
the repository's digest helper and standard-library metadata parsers only.

## Change report

`git diff --stat` was empty at review start (the source/recovery evidence directory
was untracked). Reviewer wrote only this ignored review note; no tracked code change.
Reused inventory tool: `sha256_bytes`. New tools: none. Standard-library tar/email
readers supplied metadata inspection. No second independent review was conducted.
