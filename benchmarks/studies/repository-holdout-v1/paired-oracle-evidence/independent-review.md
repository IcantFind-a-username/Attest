# Independent E-02 diagnostic review

Reviewed baseline `b70afb3` through `8eb5d6325c432a89c382ad88c61cb41e797b0d73`
on `chore/heldout-oracle-qualification`. Read-only code/helper and in-progress result
metadata review; no measurement execution, restart, network, paid call or product edit.

## Finding

- **Low — malformed JUnit leaves the per-job summary incomplete**
  (`scripts/corpus/heldout_paired_oracle.py:185`, checkpoint at 204–215).
  A nonempty malformed XML artifact makes `ET.fromstring` raise before the job's
  envelope, artifact hashes and complete status are recorded. The outer handler marks
  the candidate unqualified but leaves its attempted job at `started`. The Controller
  has already persisted raw artifacts and its envelope, so this cannot create a false
  witness, but violates the protocol's summary audit sequence for this failure case.
  Record outcome metadata before parsing; preserve parse failure as an explicit job
  outcome. This path was established by code inspection, not by replaying the study;
  the sampled in-progress metadata did not contain this failure.

## Assessment

No blocking finding in the observed diagnostic. The implementation requires accepted
execution, nonempty paired JUnit identities, fixed success, buggy failure, no errors or
skips, and stable buggy failure identities across three pairs. It stops after a failed
pair and leaves qualified defect/control totals at zero. A paired witness explicitly
requires later semantic review and controls, and cannot become a recall claim here.

The protocol was committed at `636385c`, before the driver commit. Exported original
tests stay in a dedicated ignored corpus subtree; no product discovery, prompt or
cache route was introduced. Revisions, test/metadata hashes, runtime-result hash,
image digest, script/protocol hashes and Controller request/envelopes bind provenance.
The existing adapter enforces secretless container environment and read-only source;
the bootstrap checks project imports originate in the mounted tree. The archive
timeout preserves existing callers' default behavior. Observed incomplete result
metadata correctly rejected collection/configuration failures and missing JUnit.

## Limits and scope

The run was still in progress when inspected. This review does not validate final
counts, every artifact digest, original hidden test semantics, corpus direction,
security platform acceptance or E-02 completion. No full pytest/Ruff/mypy was run by
the reviewer; the controller owns final artifact/gate validation. No retry or repair
of oracle outcomes is authorized by this report.

`git diff b70afb3 8eb5d63 --stat`: 3 files changed, 277 insertions, 3 deletions
(paired protocol +40; driver +234; archive helper 6 changed lines).

Reused inspected inventory: `validation_junit_counts`, `sha256_bytes`,
`write_canonical_json`, `archive`, `Controller`, `ContainerAdapter`, `project_roots`.
No new tools or alternative utility implementations. Reviewer writes only this
ignored report; no tracked diff.
