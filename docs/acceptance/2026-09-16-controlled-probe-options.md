# Controlled probe pytest options — 2026-09-16

## Result and scope

At `f2560ce15d69506861c20ae9b104554d5d4ef789`, **2,568 tests pass, zero fail or skip**;
certification/execution coverage is **93.42%**. Ruff, mypy and diff checks pass.
This fixes the argument-parsing obstruction found in D-272; it does not establish
any historical runtime success, defect witness or recall gain. API spend is **$0**.

Baseline `f95c7a6`; branch `fix/controlled-probe-pytest-options`. Changed files:
`src/attest/review/executor.py` and `tests/test_executor.py`. The controller adds
`-o addopts=` to the exact recorded pytest command. Project addopts can otherwise
require a disabled plugin, deselect the requested node, collect without execution,
or explicitly load another plugin. The request/evidence command binding includes
the override. Rootdir, confcutdir, conftest, trace plugin, secretless environment,
plugin-autoload prohibition and container isolation remain unchanged. Default
intent remains v5.1; no statistical or publication policy changes.

## Evidence and compatibility

Four focused cases failed on the baseline and passed after the fix. A fifth case
covers explicit plugin loading. The adjacent executor, execution, certification
and wheel-overlay suites pass; independent review's seven selected tests also
cover conftest fixtures and the existing warning-escalation regression. The first
attempt without PYTHONPATH failed during setup and is retained separately; it is
not counted as a behavioral RED.

The one independent review found no reproduced defect. **Compatibility cost:**
all project addopts are ignored, including `-W` and `--import-mode`; other ini
settings such as `filterwarnings` still apply. This does not promise arbitrary
plugin-dependent project compatibility. It preserves controller ownership of
probe execution rather than importing the repository's complete test CLI policy.

The full gate ran once on the fixed product source/tests and fixed HEAD, with
Python 3.12.2 on macOS arm64 and Docker available, using an authorized system
temporary directory. All 20 M-01 repeat records bind one SHA and source digest.
This is not the final two-Python release gate. During the wait, a separate
measurement adapter was prepared without changing product source/tests or HEAD;
this gate is not evidence that the adapter or its corpus execution succeeds.

## Artifacts and next step

[Manifest](evidence/2026-09-16-controlled-probe-options/manifest.json),
[run and environment identity](evidence/2026-09-16-controlled-probe-options/run-record.json),
[full log](evidence/2026-09-16-controlled-probe-options/full.log), and
[independent review](evidence/2026-09-16-controlled-probe-options/review.md)
retain commands, lock identity, raw/archived digests, RED/GREEN and compatibility limits.
No paid calls, reservations, push or release. Rollback is a local revert of
`f2560ce`, restoring project addopts and the known pre-execution failures.

Next: commit the independently reviewed natural-pair runtime adapter, then run it
once against D-277's frozen four build records. Runtime readiness remains distinct
from unchanged-original-test witnesses and product performance. The independent
paid population still lacks its preregistered minimum; this fix does not lower it.
