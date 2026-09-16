# Independent one-pass review

Baseline: f95c7a6b96ce79d98ff7855ae64b137d3d586290.
Branch: fix/controlled-probe-pytest-options.
Reviewed the uncommitted executor and test diff. No reproduced defects or blocking findings.

The override is in the actual argv before request issuance; the recorded command template incorporates it. The explicit environment still disables plugin autoload and does not inherit PYTEST_ADDOPTS. Rootdir, confcutdir, conftest discovery, the tracing plugin, and containment checks remain unchanged. Both generated probes and in-tree gate controls use the override consistently. This is a deliberate compatibility change: all project addopts, including warning flags and import-mode flags, are ignored. Other ini settings (including filterwarnings) still apply; this does not promise compatibility with every plugin-dependent repository.

Independent validation: `PYTHONPATH=src TMPDIR=/private/tmp .venv/bin/python -m pytest tests/test_executor.py -q -k 'controlled_probe_owns_pytest_arguments or warning or honours_the_conftest' --basetemp=<temporary_root> exited 0, seven selected cases passed. These cover five argument-control cases, project conftest fixtures, and the existing warning-escalation differential regression. No full gate or external corpus was run by this reviewer.

Reviewed diff --stat: src/attest/review/executor.py | 4 +++-; tests/test_executor.py | 34 ++++++++++++++++++++++++++++++++++; 2 files changed, 37 insertions(+), 1 deletion(-).

Reuse: existing execute_repro, execute_differential, fixtures, controller/request identity, and evidence command-template verification; none of the inventoried serialization/statistics utilities were needed. New tools: none. Paid/remote actions: none. Only reviewer-owned review.md was written.
