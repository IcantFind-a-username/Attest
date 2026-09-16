# Source-only runtime repair on the unchanged frozen population

This optional diagnostic arm continues the owner's authorized infrastructure repair.
The prior layout arm remains intact: all twelve readiness attempts failed, and no
original behavioral test or product evaluation took place. It is not invalidated.

Use swebench_source_runtime.py --study remainder-source-only, once, with fresh
.attest/corpora/remainder-source-only-runtime output. Reuse exactly cases.json,
its twelve revisions, archived wheels and bound build records. Keep the pinned
images, dependency constraints, extras, source links, source roots and execution
boundary from source-layout-runtime.md. No source patch, interpreter change,
resampling, subprocess permission, paid call or project-wheel rebuild.

Original source is authoritative. Never replace its bytes with differing wheel
bytes; record both digests and the omission instead. Root wheel *-nspkg.pth hooks
are omitted, recorded by digest, and never transferred or executed. Other unknown
generated Python/files remain refused. Transfer only the already permitted native
artifacts and declared generated version file when absent from original source.
Validate the complete wheel and collision/link graph before writing additions.

Build the same dependency wheelhouse, remove the exact project wheel, and install
only the resulting dependency wheels into the runtime. Check the recorded runtime
freeze does not contain the project's distribution. This prevents a preinstalled
project or its namespace hook from shadowing mounted source. A package requiring
installed project metadata can still fail; do not add per-case fallback behavior.
Keep the source-origin assertions and all existing readiness requirements.

Run the generic native fixture under this same source-only mode first. Refuse all
corpus execution if it fails. Record all twelve case outcomes, with no replacement
or retries after behavioral outcomes. Parent/head dependency equality and unchanged
original human tests are still separate qualification requirements. Import success
is neither defect qualification nor recall. Django's process query remains an
unsupported operation until the separately approved profile passes its own gates.
