# Real-data evaluation handoff

Date: 2026-08-29  
Branch: `feature/real-data-evaluation`  
Reviewed code baseline: `0e2172d`

## Outcome so far

This branch builds the measurement boundary needed to evaluate Attest on real
developer bug/fix history without inventing labels. It does **not** yet establish
that Attest is accurate: the frozen pilot is metadata-only and no upstream
prepared environment has produced a scorable validation receipt.

Completed and independently reviewed work:

| Task | Outcome | Commits |
|---|---|---|
| 1 | CI verifies only drawer candidates and preserves terminal decisions | `26b0b94` |
| 2 | Strict schema, real placement join, one-to-one matcher, Wilson metrics | `7a91b8f`, `d86024f`, `421a668` |
| 3 | BugsInPy metadata adapter, offline oracle validator, receipt binding, isolation probe, exact license templates | `1a8bffd`, `a6327d7`, `5326155`, `0e2172d` |
| Plan | Generic API, differential V, stability/baseline experiments, live evaluation | `deae203`, `ac7facf`, `ca06233` |

Frozen pilot facts:

- BugsInPy source commit: `316b95e2353ecda832bad9b42f86fa7c2fcec8ac`
- 20 pairs / 40 paired cases / 4 projects
- 38 eligible pairs; 463 explicit exclusions
- Projects: black 10, fastapi 7, cookiecutter 2, PySnooper 1
- Preregistration digest: `564a87586782db4100ae7a4bceeeaef59cd6e987e53818bcbed007581358965b`
- Current status: `not_executed`, `unscorable`, receipt `null`

The validator is deliberately fail-closed. A scorable receipt is derived from
canonical validation-result bytes, bound to the manifest digest, and issued
only by the built-in subprocess runner after its versioned, hashed wrapper
actually blocks a live socket probe. Synthetic runners can test state handling
but cannot sign scorable evidence.

## What remains

Follow `docs/superpowers/plans/2026-08-29-real-data-evaluation.md` from Task 4:

1. Differential product verification: head FAIL + base PASS is the only
   positive V; fail/fail and infrastructure failures DEFER.
2. Safe `a/` and `b/` anchor fallback, honest terminal copy, and a hard-budget
   proposer-output fix.
3. Generic `evaluate_project` / `evaluate_projects` Python API and deterministic
   artifacts.
4. One-diff, ten-repeat stability experiment followed by Attest / bare-prompt /
   Ruff head-to-head comparison.
5. Materialize the frozen real environments, run the repeated differential
   oracle, and only then run replay/live evaluation.
6. Produce a calibration decision packet. Do not change factory alpha or S/T/V
   constants below 500 global labels or without explicit owner approval.

## Measurement findings already reproduced

- Current product V is single-sided: any generated pytest assertion failure on
  head is treated as reproduced. This is the highest-priority correctness gap.
- `a/pkg.py` and `b/pkg.py` model anchors are currently rejected when the real
  diff path is `pkg.py`; use exact-path-first fallback to avoid breaking real
  top-level `a/` or `b/` directories.
- The default five 2,000-token output reservations cause pre-call budget DEFER
  at an ASCII diff boundary of 44,158 characters.
- Product-created candidates cannot reach the `certified-false` threshold under
  factory constants, so that terminal wording is misleading.
- A 20-seed x 2,000-task null grid produced 0 wrong certifications at alpha
  0.05, 3 across 80,000 tasks at alpha 0.1, and 544 across 80,000 tasks at alpha
  0.2. Do not loosen alpha to make S/T reach the gate.
- Monitor alarms in that grid occurred in 12 of 40 runs and were all
  spend-share drift. A high-error canary run had no alarm, so generic
  alarm-triggered braking is neither sensitive nor specific enough for
  production.

The externally produced `judges.py`, `run_engine.py`, `verdicts.json`, and
`engine_results.json` were referenced through an abbreviated `/tmp/...` path
but were not visible in this workspace. Treat their exact LR figures as
owner-provided measurements until the files are copied to a stable absolute
path and independently hashed/replayed.

## Resume commands

```bash
git switch feature/real-data-evaluation
git status --short
sed -n '1,240p' AGENTS.md
sed -n '1,520p' docs/superpowers/plans/2026-08-29-real-data-evaluation.md
sed -n '1,240p' .superpowers/sdd/2026-08-29-real-data-evaluation/progress.md
sed -n '1,220p' .superpowers/sdd/2026-08-29-real-data-evaluation/task-4-brief.md
```

Fresh verification before claiming the branch green:

```bash
.venv/bin/pytest --cov=src/attest --cov-report=term-missing
.venv/bin/pytest -q tests/test_allocation.py tests/test_betting.py tests/test_engine_default.py tests/test_exploration.py tests/test_monitor.py tests/test_regression_pins.py tests/test_tables.py --cov=attest.core --cov-report=term-missing --cov-fail-under=99
.venv/bin/ruff check .
.venv/bin/mypy src/attest
```

Default offline corpus validation is expected to exit 3 because no prepared
environment/receipt exists; that is a correct unscorable result, not a failing
test or a completed evaluation.

## Handoff verification

Fresh local commands run immediately before the handoff documentation commit:

- Full suite: `390 passed in 53.23s`, total coverage `92.18%`.
- Core gate: `60 passed`, core coverage `99.77%`.
- Ruff: `All checks passed!`.
- Mypy: `Success: no issues found in 38 source files`.
