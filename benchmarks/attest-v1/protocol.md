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
  auditable LICENSE/LICENCE/COPYING at both commits with the same recognized,
  complete MIT, BSD-2-Clause, or BSD-3-Clause terms. Recognition requires the
  full grant, conditions, warranty disclaimer, and liability disclaimer after
  whitespace normalization. Each supported template is detected independently
  and an SPDX id is returned only when exactly one matches. Multiple supported
  templates, a complete unsupported template, or appended license terms fail
  closed rather than being reduced to one SPDX id.

`bug_patch.txt` is a source patch and upstream fixes commonly add their
regression test in the same commit. Patch integrity therefore means byte-for-
byte equality after newline and volatile `index`-line normalization with
`git diff --no-ext-diff --no-color BUGGY FIXED -- PATH...`, where `PATH...` is
the unique safe Python path set declared by the patch itself. Direction is
always buggy to fixed; reversing either commit fails validation. Unified-diff
hunks are walked with separate old/new cursors. Only `-` and `+` lines create
changed ranges; context is not counted. Old/new ranges remain distinct, while
the size filter counts each contiguous edit group as the larger of its removed
or added side so replacement lines are not double-counted.

All exclusions and reasons are retained in the manifest. Not being selected by
the seeded limit is not an exclusion.

## Generic evaluation interface

`manifest.json` conforms to the generic Task 2 benchmark schema. BugsInPy is an
import adapter only. A later evaluator consumes opaque cases, roles, commit
IDs, hash-addressed patch/test descriptors, changed locations, runtime argv,
and hidden truth without branching on `provenance.kind`.

Third-party materialization is caller-owned and lives outside this repository.
Each runtime row names a pair- and role-specific relative prepared checkout and
a typed command (`python` or an explicitly mapped tool plus arguments). Bare
`python`, `python3`, `pytest`, and `tox` are never resolved through `PATH`.
Default validation is offline and never clones, fetches, invokes a provider,
reads API credentials, calls `gh`, or executes upstream `setup.sh`. A caller
may prepare an environment independently and map each opaque source ID to an
absolute interpreter/tool. Prepared execution additionally requires an
explicit sandbox/container wrapper contract: an absolute wrapper executable,
its exact SHA-256, and capability version `attest.network-deny.v1`. Before any
test, the runner opens a loopback listening socket and attempts to connect to
it through the same wrapper and owned process-session boundary. A successful
connection, missing/unknown capability, wrapper drift, probe timeout, or broken
wrapper fails closed. A caller boolean and environment proxy variables are not
isolation evidence.

## Differential oracle

For every materialized pair, verify patch/test SHA-256 values, clean worktrees,
exact checkout roots and HEAD commits, buggy-to-fixed patch equivalence, and
the descriptor command/cwd binding first. Then run the fixed command three consecutive times and require
PASS each time. Run the buggy command three consecutive times and require FAIL
with one normalized failure signature each time. Timeout, fixed failure,
buggy pass, flaky status, dependency/setup error, inconsistent signature, or
integrity drift excludes the pair; none is scored as a silent negative.

Commands run without a shell, with explicit cwd and a small explicit
environment, a finite timeout, continuously drained bounded combined output,
deterministic Python hash seed, and a caller-provided interpreter/tool map.
Each invocation owns a fresh process group/session so timeout cleanup kills its
descendants without polling unrelated PIDs.

Validation reports `command_success` independently from `corpus_valid`.
Without a prepared root the command is `not_executed`, unscorable, and exits
nonzero; it is never described as successful validation. Only a validated
subset executed by the built-in runner after its owned-boundary isolation
probe produces a receipt containing the exact manifest SHA-256, the sorted allowlist
of validated pair IDs, and the SHA-256 of a canonical validation-results JSON
artifact. The loader must consume both files, verify the exact results bytes
and manifest digest, require one result row for every manifest pair, derive the
allowlist solely from `status=validated` rows, and compare that derivation with
the receipt. Downstream evaluators must use only this derived allowlist and
refuse pair IDs absent from it.

## Freeze and scoring

`preregistration.sha256` is the lowercase SHA-256 of the exact `protocol.md`
bytes, one NUL byte, and the exact `manifest.json` bytes. Attest results do not
enter either hashed artifact. Matching and aggregate metrics use the generic
Task 2 interfaces and remain outside this import/validation task.
