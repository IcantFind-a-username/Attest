# D-059 handoff — process-audit window and differential repeat semantics

- **Work order:** the two items D-057 left "awaiting owner direction on the runner/guard
  attribution boundary", both approved by the owner for this task.
- **Baseline:** `origin/main` @ `24da49d` (180 commits, clean tree).
- **Branch:** `feature/m01-audit-window-and-repeat-semantics`. Not pushed.
- **Gated SHA:** `0e95b04cadda14e0e07aceadb751a0969095c322` — the full gate below ran
  here; the only later commit adds this report's gate section and changes no code.
- **Diff against baseline:** 13 files, **+1256 / −38**, net **+1218** lines
  (of which this report and the two evidence artifacts are the large majority).
- **Decision:** D-059 (the highest existing entry was D-058 across both `- **D-NNN` and
  `### D-NNN —` formats; 59 entries scanned).

## Executive result

The first certified receipts this project has produced on real historical defects.

| | prior three rounds | this round |
|---|---|---|
| K (head deterministic fail + base pass) | 0, 0, 0 | **4** |
| child-process DEFERs | dominated every round | **0** |

Accuracy, precision and recall remain **not estimated**. K is an operational count of
differential receipts. No precision or recall statement may be derived from it.

## Wave 1 — the failing end-to-end test

`tests/test_corpus_certification_e2e.py` is the shape D-058 names as this repository's
highest-value test: a known historical defect, a known-correct reproduction, and the real
verification path. Nothing on the path under test is stubbed — the corpus project's own
Python 3.8.3 runs the real pytest, `execute_differential` builds real detached worktrees at
the pair's exact SHAs, and the containment guards, repeat semantics and evidence
classification all run for real. Only the generator is supplied, because the reproduction
content is an input to this test rather than the thing being measured (§3.1 real-boundary
fixture).

Pair: `pair-acc00ce9f068` / `case-c22190aa4fc9`, receipt-validated in
`benchmarks/attest-v1/validation-results.json`; black bug 17, fix commit "Fix handling of
empty files". Head `bbc09a4f013f2a584f143f3f5e3f76f6082367d4` indexes `src_txt[-1]`
unguarded, so `black.format_str("")` raises `IndexError`; base
`7fc6ce990669464f5172b63fafa3724f5f308be3` slices and returns `""`.

### Observed failure, verbatim

```text
        execution = verification.execution
>       assert [run.outcome for run in execution.head_runs] == [
            ExecutionOutcome.REPRODUCED
        ] * REPEATS, f"head runs: {[(r.outcome.value, r.reason) for r in execution.head_runs]}"
E       AssertionError: head runs: [('deferred', 'reproduction attempted to create a child process')]
E       assert [<ExecutionOu...: 'deferred'>] == [<ExecutionOu...'reproduced'>]
E
E         At index 0 diff: <ExecutionOutcome.DEFERRED: 'deferred'> != <ExecutionOutcome.REPRODUCED: 'reproduced'>
E         Right contains 2 more items, first extra item: <ExecutionOutcome.REPRODUCED: 'reproduced'>

tests/test_corpus_certification_e2e.py:180: AssertionError
=========================== short test summary info ============================
FAILED tests/test_corpus_certification_e2e.py::test_receipt_validated_regression_certifies_end_to_end
1 failed in 7.33s
```

One head run, deferred; head repeats 2/3 and every base run were skipped.

### Failure cause

Exactly the D-057 mechanism, now reproduced on a *different* pair and with a reproduction
known to be correct. The durable per-run process-audit evidence:

```text
event=subprocess.Popen
target='uname'
stack:
.../venvs/black/lib/python3.8/site-packages/_pytest/_py/path.py:31:<module>
<frozen importlib._bootstrap>:991:_find_and_load
<frozen importlib._bootstrap>:975:_find_and_load_unlocked
<frozen importlib._bootstrap>:671:_load_unlocked
<frozen importlib._bootstrap_external>:783:exec_module
<frozen importlib._bootstrap>:219:_call_with_frames_removed
.../python3.8/uuid.py:57:<module>
.../python3.8/platform.py:891:system
.../python3.8/platform.py:857:uname
.../python3.8/platform.py:613:_syscmd_uname
.../python3.8/subprocess.py:411:check_output
.../python3.8/subprocess.py:489:run
.../python3.8/subprocess.py:854:__init__
.../python3.8/subprocess.py:1580:_execute_child
```

The marker was interpreter-scoped, so it fired before any reviewed code ran and denied the
candidate. It was not distinguishing anything.

## Wave 2 — narrowing the adjudication window

The adjudication window opens when a test function starts executing and never closes again,
so teardown, `atexit` and every later test stay adjudicated. A tiny pytest plugin loaded
with `-p` from the guard site directory arms it at `pytest_runtest_call`.

Recording is unchanged in breadth: every process event still writes event, target, phase and
a bounded stack, now into a durable per-run `process-observed` file that covers both phases.
Only the *decision* narrowed. Fail-closed: a run that reaches a verdict without the window
ever opening is DEFERRED rather than trusted.

Unchanged, verified by the existing suite: the audited event set, `RLIMIT_NPROC`, timeouts
and resource limits, adjudication strength while reviewed code runs, D-017/D-042
containment, `G-SEC-002`/`G-SEC-003`. No allowlist. The pre-existing tests that assert a
reproduction spawning a child process, replacing the process, or starting a thread still
DEFER, including the `atexit` case that fires after the test body.

**Result: the wave-1 test turned green.** `1 passed in 6.53s`.

Two contracts this introduces are pinned portably in `tests/test_executor.py`: an event
before the test call is recorded with `phase=runner-bootstrap` and does not defer; a passing
run whose window never armed is refused.

## Wave 3 — repeat semantics

Measured on identical candidates, baseline `24da49d` versus this branch, real subprocesses
both times:

| candidate | before: head runs | before: base runs | after: head runs | after: base runs |
|---|---|---|---|---|
| syntax-error reproduction | **1** (`deferred`) | **0** | **3** (`deferred` ×3) | **3** (`deferred` ×3) |
| flaky reproduction | 3 (`reproduced`, `not_reproduced`, `reproduced`) | **0** | 3 (same) | **3** |

Reason strings, before → after:

- `head run 1/3 deferred: pytest collection/import/syntax or infrastructure failure (exit code 2, 0 failure(s), 1 error(s))`
  → `indeterminate on head in 3/3 runs; run 1/3: pytest collection/import/syntax or infrastructure failure (exit code 2, 0 failure(s), 1 error(s))`
- `flaky reproduction on head (2/3 runs failed)`
  → `unstable reproduction on head (2 failed, 1 passed, 0 indeterminate of 3 runs)`

Classification now reads all runs at once: head failing every repeat with base passing every
repeat is `REGRESSION_REPRODUCED`; head disagreeing with itself is unstable and uncertified;
head uniformly indeterminate is named as such rather than called unstable; head passing every
repeat is not reproduced; base failing too stays unfaithful. Each repeat's result is kept
independently in the per-run evidence. Certification still requires a deterministic head
failure across every repeat — the standard did not move. Only the shared deadline still cuts
a sequence short, and a truncated base can no longer be read as a clean base.

Cost: a differential now runs up to twice the wall time, because base always executes.

## Wave 4 — receipt-validated corpus rerun

Pre-declared before any call; scope fixed in advance, no outcome-dependent selection.

- Protocol: `scripts/benchmark.py live-local`, frozen `attest-v1` manifest
  (SHA-256 `8f9f90f1ff442d4639f6959faf7701d9e3d05c5863ed48ade6b02e595a8d72d9`).
- Scope: all 9 receipt-validated pairs, `historical_bug_replay` role — 9 cases.
- Config: alpha 0.1, K = 5 samples, differential repeats 3, `--budget-usd 0.16` per case,
  deadline 60 s, no tier-0 command.
- Run id `d059-wave4-replay-9b`; report digest
  `674873ba548da752be68bafcc513664da344803a03282992957262e8b6027da7`.
- Reserved $2.88; **settled $0.933454**, under the $1.44 mechanical maximum and the $1.50
  task cap.

The first attempt passed `--validation-receipt`; the harness excluded all 9 cases as
`pair_not_in_validation_receipt` and spent **$0.00**. The v1 receipt is
`historical_integrity_only` and can never carry scoring authority, which is why the prior
rounds also ran without it and withheld accuracy. The rerun follows that convention.

### N / M / K against the prior three rounds

| Measure | Round 1 (D-037 pilot) | Round 2 (wave 3, `50055e2`) | Round 3 (wave 4, `df40c03`) | **This round (D-059)** |
|---|---:|---:|---:|---:|
| cases | 10 case-runs | 4 | 4 | **9** |
| candidates N | not retained per candidate | 4 | 7 | **23** |
| reached differential execution M | not retained | 3 | 4 | **6** |
| certified K (head FAIL n/n + base PASS n/n) | 0 | 0 | 0 | **4** |
| surfaced findings | 0 | 0 | 0 | **4** |
| spend | $1.0592 | $0.330626 | $0.433304 | **$0.933454** |

K counts the **product's own** differential certificates, read from the per-candidate
durable records. The harness's `channel_outcomes` and `evidence_class_counts` report
`regression_reproduced: 3, unfaithful: 1` for the same four findings, and both numbers are
correct because they measure different things: those fields carry the **benchmark oracle's**
independent re-verification, which `runner.py` lets override the product's class per finding.
The oracle corroborated 3 of the 4 and refuted 1. Section "Reading the four certified
findings" below resolves that disagreement.

**Erratum.** An earlier revision of this report attributed the 3-vs-4 gap to the aggregate
layer keeping one class per case. That was wrong. The gap is product self-certification
versus independent oracle confirmation; no counter was truncating anything.

### DEFER / outcome reason distribution (23 candidates)

| count | reason |
|---:|---|
| 15 | generation failed: `BudgetExceeded` — the per-case product budget |
| 4 | **head FAIL 3/3, base PASS 3/3 (certified)** |
| 2 | unfaithful generated test: fails on base as well |
| 1 | generation failed: reproduction schema invalid |
| 1 | indeterminate on head 3/3 (pytest collection/import/syntax) |
| **0** | **reproduction attempted to create a child process** |

The reason that denied every candidate in the previous rounds is gone. The dominant
remaining loss is the per-case product budget at `--budget-usd 0.16`, an evaluation-harness
knob, not a product guard; it is in `docs/backlog.md`.

### stop_reason distribution

| role | end_turn | max_tokens |
|---|---:|---:|
| proposer | 39/45 | 6/45 |
| reproduction | 7/9 | 2/9 |
| benchmark oracle | 4/4 | 0/4 |

### Per case

| case | pair | candidates | surfaced | status | spend |
|---|---|---:|---:|---|---:|
| `case-1e2261dcc6e9` | `pair-662a533eb0f0` | 4 | 0 | deferred | $0.159406 |
| `case-2dad0cb4c5b5` | `pair-e6fd59112ec9` | 3 | 1 | deferred | $0.092228 |
| `case-3efff8123ae7` | `pair-169429c32175` | 4 | 0 | deferred | $0.102090 |
| `case-794b97290785` | `pair-e61fb0c608f2` | 1 | 0 | deferred | $0.090810 |
| `case-81039ffa0c1e` | `pair-53f336eb966b` | 2 | 0 | deferred | $0.089118 |
| `case-99a012693940` | `pair-8419788e183e` | 1 | 1 | completed | $0.053680 |
| `case-a8dfb35be49f` | `pair-d4c758e1cde3` | 1 | 0 | deferred | $0.158580 |
| `case-c22190aa4fc9` | `pair-acc00ce9f068` | 4 | 1 | deferred | $0.090360 |
| `case-c6f141a2be09` | `pair-dee2edc00ad8` | 3 | 1 | deferred | $0.097182 |

Three of the four surfacing cases carry task status `deferred` with a surfaced finding —
mixed outcomes preserved, as invariant 7 requires. A task DEFER did not erase a finding
already shown.

## Reading the four certified findings

A manual review of all four surfaced findings against the corpus's own `bug_patch.txt`.
This is human judgement on the claim text, not a metric.

| # | case / pair | claim, in one line | reverted hunk it names | verdict |
|---|---|---|---|---|
| 1 | `case-99a012693940` / bug 16 | the `try/except ValueError` guard for symlinks resolving outside root was removed, so traversal crashes instead of skipping | `gen_python_files_in_dir`, exactly that guard | **real** |
| 2 | `case-2dad0cb4c5b5` / bug 9 | `get_grammars` else-branch no longer returns `python_grammar_no_print_statement`, breaking Python-2 print-function parsing | `return [pygram.python_grammar]` vs the two-grammar list | **real** |
| 3 | `case-c22190aa4fc9` / bug 17 | the `if not lines:` guard was removed from `decode_bytes`, so `lines[0]` raises IndexError on an empty file | `decode_bytes`, exactly that guard | **real** |
| 4 | `case-c6f141a2be09` / bug 5 | the `no_commas` branch was removed, so a split single-argument `def` loses its trailing comma | `if original.is_import or no_commas:` — names the variable the fix introduces | **real** |

All four name the exact logic the reverted patch removes. Finding 4 names `no_commas` by
its identifier. This is not the certification mechanism blessing noise.

### The oracle's one refutation is a false negative

The benchmark oracle independently regenerated a reproduction for each surfaced finding.
It confirmed 1, 2 and 3 (`buggy_fail_fixed_pass`, 3/3 each) and refuted 4 as
`unfaithful` / `buggy_fail_fixed_fail`.

The refutation is an artifact of the oracle's own test, not evidence about the finding. Its
body opens with

```python
try:
    mode = black.Mode(line_length=88)
    formatted = black.format_str(src, mode=mode)
except AttributeError:
    formatted = black.format_str(src, line_length=88)
```

At this 2019-era revision `black.Mode` does not exist, and the fallback is also wrong for
that vintage — `format_str` takes `mode=black.FileMode()`, not `line_length=`. Both branches
raise on **both** revisions, which is exactly the `buggy_fail_fixed_fail` shape the oracle
reported. Replayed locally at the pair's two SHAs, with no paid call:

```text
head 1bbb01b854:  TypeError: format_str() got an unexpected keyword argument 'line_length'
base 9394de150e:  TypeError: format_str() got an unexpected keyword argument 'line_length'
```

The product's reproduction used the correct API for the revision and separates the two sides
cleanly:

```text
head 1bbb01b854                          base 9394de150e
def very_long_function_name_that_...(    def very_long_function_name_that_...(
    argument_name_that_is_long               argument_name_that_is_long,
) -> ReturnType:                         ) -> ReturnType:
    pass                                     pass
trailing comma present: False            trailing comma present: True
```

Finding 4 is real, and the product's certificate for it is sound.

### The location matcher is what is too strict

The run used `line_slack = 0`. Anchors against the labeled truth spans:

| finding | anchor | labeled truth span | matched |
|---|---|---|---|
| `fdbff9370c` | `black.py:735` | `735–735` | **yes** |
| `b1e7f57dc2` | `black.py:2949` | `2948–2948` | no — off by one line |
| `ed1d3ea89b` | `black.py:2495` | `2491–2493` | no — off by two lines |
| `20d686ba82` | `black.py:610` | `626–626` | no — names the *other* hunk of the same two-hunk fix |

One of four matched. The three misses are not wrong findings: two are off-by-one/two inside
the same edit, and the third correctly identifies `decode_bytes`, the first of bug 17's two
hunks, while the corpus labels only the second (`lib2to3_parse`, `src_txt[-1]`).

So the answer to "is the product working, or is it certifying noise?" is the first one. The
gap between K = 4 and matched = 1 is a **measurement** problem — anchor tolerance and
single-hunk truth labels — not a proposal-side or verification-side defect. Raising
`--line-slack` and labelling every hunk of a fix would be the cheap correction, and both are
measurement-only changes that touch no product behaviour. Neither is done here; both need
their own work order, because changing a matcher after seeing its results is exactly the
outcome-dependent move `AGENTS.md` §16 reserves for an owner decision.

None of this is a precision estimate. Four findings, no developer-fix controls in this run,
and accuracy formally withheld.

## The first certification receipt, in full

`case-99a012693940`, pair `pair-8419788e183e`, black BugsInPy bug 16.
Head `fb34c9e19589d05f92084a28940837151251ebd6`,
base `42a3fe53319a8c02858c2a96989ed1339f84515a`.
Finding `b1e7f57dc2`, anchored `black.py:2949`.

### Candidate, as proposed

> **claim:** Removing the try/except ValueError handling means that symlinks pointing
> outside the root directory (or other files whose resolved path cannot be made relative to
> root) will now raise an unhandled ValueError, crashing the entire directory traversal
> instead of being gracefully skipped.
>
> **anchor:** `black.py:2949`
>
> **failure_scenario:** Running black on a directory that contains a symlink pointing to a
> file outside the root directory (e.g., a symlink to /etc/passwd or a sibling directory)
> causes `child.resolve().relative_to(root)` to raise ValueError, which now propagates
> uncaught and crashes the file-discovery generator instead of reporting the symlink as
> ignored.
>
> **falsification_plan:** Create a directory with a symlink pointing outside of it, then call
> black.gen_python_files_in_dir on that directory and observe whether a ValueError is raised
> (crash) versus being caught and reported via report.path_ignored as before.

### Generated reproduction, as executed

```python
import os
import re
import tempfile
from pathlib import Path

import black


def test_gen_python_files_in_dir_skips_symlink_outside_root():
    include = re.compile(black.DEFAULT_INCLUDES)
    exclude = re.compile(black.DEFAULT_EXCLUDES)

    with tempfile.TemporaryDirectory() as outside_dir, tempfile.TemporaryDirectory() as root_dir:
        outside_path = Path(outside_dir) / "outside.py"
        outside_path.write_text("x = 1\n")

        root = Path(root_dir).resolve()

        # Create a normal python file inside root so we know traversal works.
        normal_file = root / "inside.py"
        normal_file.write_text("y = 2\n")

        # Create a symlink inside root pointing outside root.
        symlink_path = root / "link.py"
        try:
            symlink_path.symlink_to(outside_path)
        except (OSError, NotImplementedError):
            import pytest
            pytest.skip("symlinks not supported on this platform")

        report = black.Report()

        # This should NOT raise ValueError even though the symlink resolves
        # outside of `root`. A correct implementation gracefully skips it
        # (e.g. via try/except ValueError) instead of crashing the whole
        # traversal.
        try:
            result = list(black.gen_python_files_in_dir(root, root, include, exclude, report))
        except ValueError as exc:
            raise AssertionError(
                "gen_python_files_in_dir raised ValueError for a symlink pointing "
                "outside root instead of skipping it gracefully: " + str(exc)
            )

        result_names = {p.name for p in result}
        assert "inside.py" in result_names
        # The symlinked file, whose target lies outside root, must not be
        # yielded as a normal in-root python file.
        assert "link.py" not in result_names
```

### Execution, all six runs

| side | repeat | outcome | exit | network blocked | reason | elapsed |
|---|---:|---|---:|---|---|---:|
| head | 1 | reproduced | 1 | yes | pytest reported 1 failure(s) and 0 error(s) | 0.372367 s |
| head | 2 | reproduced | 1 | yes | pytest reported 1 failure(s) and 0 error(s) | 0.330898 s |
| head | 3 | reproduced | 1 | yes | pytest reported 1 failure(s) and 0 error(s) | 0.355609 s |
| base | 1 | not_reproduced | 0 | yes | pytest passed | 0.272211 s |
| base | 2 | not_reproduced | 0 | yes | pytest passed | 0.257004 s |
| base | 3 | not_reproduced | 0 | yes | pytest passed | 0.263467 s |

Head failure, as recorded:

```text
E               AssertionError: gen_python_files_in_dir raised ValueError for a symlink
                pointing outside root instead of skipping it gracefully:
                '/.../outside.py' does not start with '/.../tmpdw82worl'

.attest-repro/test_repro.py:40: AssertionError
FAILED .attest-repro/test_repro.py::test_gen_python_files_in_dir_skips_symlink_outside_root
1 failed in 0.15s
```

Outcome `reproduced`, evidence class `regression_reproduced`,
reason `head FAIL 3/3, base PASS 3/3`.

### Wealth, per channel

| channel | LR | detail |
|---|---:|---|
| S (proposer votes) | 2.9485 | 3 votes, correlation-discounted |
| T (static corroboration) | — | never purchased; no tier-0 command configured |
| V (reproduction) | 20.0 | `V_CAP`, reproduced |
| **wealth** | **58.9708** | threshold `1/alpha` = 10.0 → **surface, inline** |

`2.9485 × 20.0 = 58.9708` identifies S at 3 votes uniquely against the frozen vote schedule
`[1.0, 2.0, 2.639, 2.9485, 3.0, 3.0]`, and rules out any T purchase.

### What this receipt does and does not say

It says: on this pair, a generated reproduction failed deterministically on head across
three runs and passed deterministically on base across three runs, under the network and
process guards, at exact detached worktrees of both SHAs.

It does not say the finding is correct. The corpus location matcher returned
`matched: 0, defect_id: null` for this anchor. Per `INV-TRUTH-001` location overlap
establishes neither correctness nor detection, and accuracy is withheld for the whole run
(`validation_receipt_missing`). K is a count of differential receipts. It is not precision,
not recall, and nothing about precision or recall follows from it.

## Gates

Final full gate at `0e95b04`, clean tree, one supported Python:

```text
python -m pytest --cov=src/attest --cov-report=term-missing
  1619 passed, 1 skipped in 786.04s (0:13:06)
  Required test coverage of 90.0% reached. Total coverage: 92.36%
python -m coverage report --include='src/attest/benchmark/*' --fail-under=0   89% (informational)
python -m coverage report --include='src/attest/core/*'      --fail-under=0   99% (informational)
python -m ruff check .        All checks passed!
python -m mypy src/attest     Success: no issues found in 57 source files
git diff --check              clean
```

The one skip is `tests/test_corpus_certification_e2e.py`, which needs
`ATTEST_CORPUS_CACHE` to point at the prepared corpus environment; that environment is a
read-only local input and is not in the repository. It passes when the variable is set —
`1 passed in 13.53s` at this SHA.

Product-package coverage is **92.36 %**, above the unchanged 90 % floor and in line with the
~92 % D-058 recorded at baseline. No coverage threshold was changed and no filler test was
written. `src/attest/review/executor.py` itself sits at 88 %.

An earlier full-gate attempt reported two failures in `tests/benchmark/test_stability.py`
(`..._rejects_observation_spend_tampering`, `..._rejects_canonical_observation_latency_tampering`).
They were caused by this session editing `src/attest/review/executor.py` while that run was
in flight: `_code_sha256` digests every `.py` file under the package, so the resume binding
legitimately detected a changed code digest. Both pass in isolation and in the clean-tree
rerun above. Not a regression, and the tamper detection behaved correctly.

## Spend

- Pre-declared cap for this task: $1.50. Mechanical maximum of the declared scope: $1.44.
- First attempt (receipt-gated, all cases excluded before any call): **$0.00**.
- Wave-4 run `d059-wave4-replay-9b`: **$0.933454**, recorded in `DEVSPEND.md` immediately
  after the run.
- `DEVSPEND.md` total: **$6.866604 of $10.00** (31 entries).
- No other paid call was made. Waves 1–3 were entirely unpaid.

## Limits and next work

- The audit window opens at the test call, so an import-time event in the generated test
  module is recorded but not adjudicated. Attribution boundary, not a containment hole;
  `RLIMIT_NPROC` still refuses the process. Widening to collection needs an owner decision.
- 15 of 23 candidates were lost to the per-case product budget, not to any product
  behaviour. A rerun above ~$0.20 per case would measure how many reach a differential.
- Base always executing roughly doubles differential wall time. The 60 s shared deadline did
  not bind in this run (max case latency 53.4 s including generation), but it has less margin
  than before.
- Accuracy on this corpus still requires a scoring-authoritative receipt; the v1 receipt
  cannot provide one.

---

## Erratum, 2026-09-01 (appended; nothing above is rewritten)

Later work on the same branch changed two numbers this report published. Both originals
stand as observations; the corrections and their reasons follow.

**1. `differential_v.confirmed` read 3 of 4. With a working oracle reproduction it is 4 of 4.**
This report already identified the cause — the oracle's own test opened with
`black.Mode(line_length=88)` and fell back to `format_str(src, line_length=88)`, neither of
which exists at that revision, so it raised on both sides. D-061 replayed the same finding
through the product's own `execute_differential` at the pair's two SHAs, 3 repeats per side,
zero paid calls: the probing body gives head FAIL 3/3 and base FAIL 3/3
(`buggy_fail_fixed_fail` -> `unfaithful`); the API-correct body gives head FAIL 3/3 and base
PASS 3/3 (`buggy_fail_fixed_pass` -> `regression_reproduced`). The justification does not
depend on that outcome: a test that raises identically on both revisions has no
discriminating power whichever side is right. Evidence:
`docs/acceptance/evidence/2026-09-01-d060-oracle-api-replay/result.json`.

**2. `matched = 1` was measured at `line_slack = 0`. Under the rule pre-registered in D-062
it is 2 of 4 on these receipts, and 3 of 4 once correction 1 is applied.** The rule, its two
outcome-independent grounds and the expected counts were written and committed at `35ecaa5`
before `matcher.py` was touched; every declared number held. `20d686ba82` still does not
match at any tolerance below 16, and its case carries one head-side label against two
fix-side hunks, so it is now flagged `unlabelled_hunks_present` rather than counted as a
plain miss. Evidence:
`docs/acceptance/evidence/2026-09-01-d062-matcher-rescore/result.json`.

**Unchanged by both corrections:** K = 4, the four manual verdicts, N = 23, M = 6, the DEFER
distribution, the spend, and the withheld accuracy. `matched` remains a count of location
bindings; per `INV-TRUTH-001` precision and recall stay **not estimated** and none may be
derived from 1/4, 2/4 or 3/4.

**One number this report could not have printed, added by D-060.** Its
`evidence_class_counts` read `{regression_reproduced: 3, unfaithful: 1}` over 4 surfaced
findings. Rebuilt from the per-candidate records with the judge named:
product self-certification over all 23 candidates
`{indeterminate: 17, regression_reproduced: 4, unfaithful: 2}`; benchmark oracle over its 4
receipts `{regression_reproduced: 3, unfaithful: 1}`; `oracle_overturned_product: 1`, which
correction 1 above then takes to 0.
