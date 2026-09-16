# Authorized safe-link repair qualification

Owner request following the D-281 terminal report: fix the engineering failures,
including safe in-tree relative links, then continue actual evaluation. This is a
new qualification record over the same immutable twelve natural revisions and
six case identities; no new sampling, no relabeling of D-281, no hidden failures.

Reuse cases.json and its bound qualification record exactly. Use
swebench_compatible_build.py --study remainder-safe-links; fresh output is
.attest/corpora/remainder-safe-link-build. Before execution, commit this protocol
and driver. The shared archive helper validates all member paths/types and link
resolution before extraction; only relative links resolving within the original
archive to existing objects are allowed. Reject escapes, dangling links, cycles,
absolute targets and descendants beneath links. Preserve original link text,
file bytes and executable bit. Write regular files before creating links. No
project code runs on the host, and no link is replaced with guessed contents.

All other build choices remain those in compatible-runtime.md: exact compiler
image, Python 3.10, creation-date constraints, implicit backend handling, original
requirements, one 900-second attempt per revision and full failure retention.
No dependency repair after build results, new sample, paid call or source patch.
Record the archive helper digest along with driver, protocol, revision and image.

Validate adversarial fixtures and independently review the exporter before real
exports. First verify exports of all twelve immutable revisions; then assess
builds, source-mounted runtime and original tests. Later steps must retain link
validation instead of reintroducing unconditional rejection. Paid minimum, cap,
truth separation, free smoke and model checkpoint requirements are unchanged.
A successful export/build is not a product recall or certification result.
