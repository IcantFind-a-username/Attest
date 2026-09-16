# Source layout repair of the frozen runtime qualification

This is a separately recorded infrastructure repair under the owner's request to
fix the evaluation blockers. Preserve remainder-safe-link-runtime/result.json;
its twelve failures are not invalidated or relabelled. The generic fixture passed,
six Django revisions failed at import because their version query starts a child
process, and six Matplotlib revisions were refused before transfer because the
source-root reader missed lib/. No original defect test or model call ran.

Command: swebench_source_runtime.py --study remainder-source-layout. Fresh output:
.attest/corpora/remainder-source-layout-runtime. Use the same twelve frozen
revisions and archived wheels, compiler/runtime images, dependencies, source-link
validation and import assertions from safe-link-source-runtime.md. No resampling,
rebuild of project wheels, oracle modification or additional paid authority.

The product's existing conventional src/ discovery also recognizes existing lib/
at a project root. Each wheel must map all discovered packages to one unique
source root; ambiguous roots refuse. Transfer compares wheel contents against that
root's original bytes, places permitted native/version additions under that root,
and refuses unsafe or symlinked root prefixes before writing. Existing standalone
module bytes may be compared but never generated or replaced. Source import
assertions continue to require the mounted tree, not the installed wheel.

One readiness attempt per revision, with the original generic native fixture first.
Retain every failure and the complete population. This is collection/infrastructure
repair before any original behavioral outcome, not test selection or a search for
certification. Default intent and subprocess/network isolation are unchanged.
The Django process restriction remains a known unsupported-runtime possibility;
this arm neither suppresses the query nor enables a child-process profile.

Readiness is not defect qualification or product performance. Original unchanged
human tests, controls, minimum independent population, the free artifact smoke and
paid protocol/cap requirements still apply. No fee is incurred by this run.
