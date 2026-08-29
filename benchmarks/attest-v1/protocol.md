# Attest v1 real-data pilot protocol

Protocol version: 1. This protocol and `manifest.json` are frozen before any
Attest review output is observed.

## Corpus and selection

The adapter reads metadata from the read-only BugsInPy checkout at commit
`316b95e2353ecda832bad9b42f86fa7c2fcec8ac`, whose origin is
`https://github.com/reproducing-research-projects/BugsInPy.git`. The repository
describes itself as “BugsInPy: A Database of Existing Bugs in Python Programs
to Enable Controlled Testing and Debugging Studies.” Its pinned tree does not
contain a LICENSE or COPYING file, so dataset provenance records
`license_status=UNSPECIFIED`; no SPDX identifier is inferred. No BugsInPy or
upstream project content is copied into this repository.

Selection uses seed `20260829` and a limit of 20 pairs. Candidates are sorted by
project and natural bug number, filtered, shuffled with Python's
`random.Random(seed)`, truncated, and finally sorted by opaque pair ID. Every
pair has one `historical_bug_replay` case and one `developer_fix_control` case.
Opaque IDs are the first 12 hexadecimal characters of SHA-256 domain inputs and
do not encode project, bug number, or role.

Candidates are excluded before selection when any of these conditions holds:

- the upstream project URL, full buggy/fixed commit, regression command, stored
  buggy/fixed output, patch, or Python hunk is missing;
- an artifact is binary, a symlink, escapes the pinned source, changes a
  non-Python file, renames a file, or changes more than 400 lines;
- the prepared upstream git cache does not contain both commits and a locally
  auditable LICENSE/LICENCE/COPYING at both commits with the same recognized
  MIT, Apache-2.0, or BSD-3-Clause terms.

All exclusions and reasons are retained in the manifest. Not being selected by
the seeded limit is not an exclusion.

## Generic evaluation interface

`manifest.json` conforms to the generic Task 2 benchmark schema. BugsInPy is an
import adapter only. A later evaluator consumes opaque cases, roles, commit
IDs, hash-addressed patch/test descriptors, changed locations, runtime argv,
and hidden truth without branching on `provenance.kind`.

Third-party materialization is caller-owned and lives outside this repository.
Each runtime row names a relative prepared checkout and an argv array. Default
validation is offline and never clones, fetches, invokes a provider, reads API
credentials, calls `gh`, or executes upstream `setup.sh`. A caller may prepare
an environment independently and map each opaque source ID to an interpreter;
container orchestration, if used, must likewise be explicit and external.

## Differential oracle

For every materialized pair, verify patch/test SHA-256 values and exact checkout
commits first. Then run the fixed command three consecutive times and require
PASS each time. Run the buggy command three consecutive times and require FAIL
with one normalized failure signature each time. Timeout, fixed failure,
buggy pass, flaky status, dependency/setup error, inconsistent signature, or
integrity drift excludes the pair; none is scored as a silent negative.

Commands run without a shell, with explicit cwd and a small explicit
environment, a finite timeout, bounded combined output, deterministic Python
hash seed, and a caller-provided interpreter.

## Freeze and scoring

`preregistration.sha256` is the lowercase SHA-256 of the exact `protocol.md`
bytes, one NUL byte, and the exact `manifest.json` bytes. Attest results do not
enter either hashed artifact. Matching and aggregate metrics use the generic
Task 2 interfaces and remain outside this import/validation task.
