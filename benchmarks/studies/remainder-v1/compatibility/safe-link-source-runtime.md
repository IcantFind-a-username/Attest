# Frozen source-mounted runtime after safe-link builds

Use exactly the twelve cases.json revisions and the archived safe-link-build-evidence
result, with no replacement or rebuild. Command: swebench_source_runtime.py
--study remainder-safe-links. Output is fresh remainder-safe-link-runtime; one
attempt per built revision, prior build failures retained explicitly.

Reuse the existing source-mounted native fixture, dependency/extra discovery and
creation-date constraints. Runtime image is pinned to
python@sha256:68d914ec641a0b69267ce65184d000a2bc3a9ee2590ab702b82250ab2385735a.
No per-case dependency repair, alternative interpreter or source patch.

Export with the shared safe archive function, revalidate the same link graph before
wheel transfer, and preserve original source bytes and link targets. Wheel-generated
links remain forbidden. Any wheel addition below an actual symlink ancestor is
refused, including case-insensitive aliases. Existing tracked link payloads may
compare equal to a wheel's dereferenced regular-file bytes; do not replace the link.
Only the existing permitted native/version additions may be written.

For this new arm only, absence of native additions is allowed when the wheel's
unique WHEEL metadata explicitly declares Root-Is-Purelib: true. This allows pure
Python source packages without pretending to witness a native artifact. Non-pure
wheels without native artifacts still refuse. Historical arms are unchanged.

The generic native fixture must pass before corpus execution. Each corpus readiness
check remains the exact source-origin import probe through execute_repro and the
secretless ContainerAdapter, with one collected test, no skips/xfails, network guard
and exit zero. Retain separate image and dependency freezes for parent/head. Neither
import readiness nor wheel metadata certifies a defect or supplies product recall.
Original unchanged human-test pairs and controls remain separate prerequisites.
