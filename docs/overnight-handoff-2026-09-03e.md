# Handoff — 2026-09-03, fifth window (`e60e6ed` → see the last line): the population was wrong, and the model matters

Status: **the "generation wall" was mostly an artefact of how the pilot population was
chosen. Four of the six reproductions in the last §5 table ran against pairs with no
regression to find or none proposed. Of the two that remain, one certified twice under
`claude-opus-5` where `claude-sonnet-5` produced nothing** — the first receipt-backed
publication that case has ever produced. The repository's gates now run on a GitHub runner
and the kernel coverage floor is green there. Both ordered product changes landed with REDs.

## 1. The corrected §5 table

Method (no model call, no spend): run the **repairing commit's own human-written tests** on
the reviewed commit and on its parent. Full working: [classification
report](acceptance/2026-09-03-generation-classification.md).

| population | model | executed | old verdict | corrected |
|---|---|---|---|---|
| receipt pilot `d7be758` ×2 | `claude-sonnet-5` | 2 | unfaithful test | **no regression in the pair — correct silence** |
| receipt pilot `e17c686` ×1 | `claude-sonnet-5` | 1 | unfaithful test | **regression real, never proposed** — the run stopped at `read 2 of 4 units, budget-limited` and the two unread units are the two files that carry it; the verdict on the claim that *was* proposed is correct |
| 2026-09-03c pilot `f58bf64` ×1 | `claude-sonnet-5` | 1 | unfaithful test | no regression in the pair — correct silence |
| **runner review PR #8** | `claude-sonnet-5` | 1 | `fails on base as well` | **real failure** |
| **`pytest-dev__pytest-10051`** | `claude-sonnet-5` | 1 | `fails on base as well` | **real failure** |

`d7be758` was chosen by blaming the lines its fix removed, which finds the last commit to
*touch* a line, not the one that introduced the defect: `git blame` shows `d7be758` only
rewrote `touch_ma5` as `ma5[touch_index]`, and the defect came from `e17c686` two commits
earlier. From now on a receipt pilot pair is head = the repairing commit's **parent**, base =
the repairing commit (mainline §3's construction), and a pair counts only if the fix's own
tests discriminate it. D-109 and the pilot report carry errata.

**"Six of six" is retired. The generation question rests on two cases, and n = 2 is not a rate.**

## 2. The two real failures, classified — and what happens under another model

| case | model | backend | failure | class |
|---|---|---|---|---|
| Attest PR #8 | `claude-sonnet-5` | container (runner) | `NameError: TruthDefect is not defined` — the file has **no import statement at all** | environment / import |
| Attest PR #8 | **`claude-opus-5`** | host adapter | `ModuleNotFoundError: test_matcher` at collection — imports a helper from the repo's own `tests/`, unreachable from `.attest-repro/` | environment / import |
| `pytest-10051` | `claude-sonnet-5` | container | `assert 0 == 1` on both sides: logs at INFO without `caplog.set_level`, so the precondition fails and `clear()` — the anchored call — never runs | asserted behaviour base lacks |
| `pytest-10051` | **`claude-opus-5`** | container | **2 candidates, 2 eligible, 2 reproductions, 2 certified, 2 published**; head FAIL 3/3, base PASS 3/3, sealed bundles | — |

Neither surviving failure is "depends on a symbol only head has". All three failures are
**scaffolding**: the generated file does not stand alone, or never reaches the diff. The opus
import failure is D-089 working half way — that decision shows the generator the nearest test
module's helpers, and nothing tells it the file must be self-contained.

Spend: **$0.272332** of the $0.50 reserved (opus `pytest-10051` $0.193112, opus PR #8
$0.079220). Cumulative **$20.829308 of $30**. Window total **$0.272332** against the $2 cap.

## 3. The gates, on a GitHub runner

`.github/workflows/ci.yml`, push to `main`, `ubuntu-latest`, Python 3.12 from the lock, **no
deselection** (D-112).

| run | ruff / mypy / `diff --check` | pytest | kernel coverage |
|---|---|---|---|
| [33724403725](https://github.com/IcantFind-a-username/Attest/actions/runs/33724403725) | green | 5 failed, 1752 passed | **92.04%** ✅ (`container_adapter.py` 90%, locally 43%) |
| [33726031144](https://github.com/IcantFind-a-username/Attest/actions/runs/33726031144) | green | 1 failed, 1760 passed | **91.72%** ✅ |
| [33727445764](https://github.com/IcantFind-a-username/Attest/actions/runs/33727445764) | green | **1766 passed, 9 skipped, 0 failed** | **91.72%** ✅ |

**The third run is green end to end — ruff, mypy, `git diff --check`, 1,766 tests and the
coverage floor, in 20 minutes on `ubuntu-latest` with docker 28.0.4.** This is the first time
the repository's own gate has passed anywhere since the owner's docker VM lost registry egress.

On the owner's host the same suite is **exit 0** with the two host-condition deselections that
last window recorded (`test_linux_isolation.py`, which cannot pull a base image, and the replay
test that spawns `docker build`); ruff, mypy and `git diff --check` are clean. The M-01 probe
also fails on this host whenever a commit lands **while it is running** — it records the HEAD
tree at run time and the aggregate re-reads it — which is what produced the mid-window
`aggregate … mismatch` noise; run it with the tree quiet. The failures the runner found were
host assumptions the owner's machine hid, all now fixed: a hardcoded `.venv/bin/python` and a
hardcoded `/private/tmp` in the M-01 probe, a shallow tagless checkout, and — the important
one — the release drill catching that D-111's first form broke the product at its own
defaults.

## 4. The two ordered product changes

- **D-110.** The image build is capped at `min(1800 s, remaining verification budget)`, threaded
  from the stage that owns the deadline; an exhausted budget never reaches the daemon. Reuse is
  decided by `docker images --no-trunc --quiet <tag>` and the run is addressed by the **id** it
  returns, so neither the lookup nor the run depends on the `image inspect` path that answered
  *No such image* for tags the same daemon listed. Two REDs.
- **D-111.** Discovery may spend at most 60% of the review budget, and reproductions are bought
  in ranking order `(-wealth, finding_id)`. **Amended the same day:** as first written the share
  wrapped the whole proposal stage, and at the shipped defaults (K=5, $0.25) five samples reserve
  $0.16 at the proposal token bound before any diff is priced — every review DEFERred at
  `sample-4`. The share now binds every unit **after the first**. On the motivating case
  discovery still stops after one unit, and verification keeps ~$0.16 of $0.25 instead of $0.076.
  Two REDs plus one for the amendment.

## 5. What this window did not do, and why

- **No pilot was run.** Instruction 1d: the deliverable is the classification table, and no
  pilot before it.
- **No product code was changed for the measurement** — the fix the classification points to
  (one sentence in the generation prompt) is owner item 1, not a change made here.
- **The opus PR #8 run used the host adapter**, because this machine's docker still cannot pull
  a base image; a `docker pull python:3.13-slim` started this window never returned. The import
  failure is a property of the generated file, not of the backend, but the two PR #8 rows are
  not backend-comparable.
- **The two models were not run at the same per-review budget** ($0.60 opus vs $0.25 sonnet):
  at opus prices four samples do not fit the 60% share of $0.50. A budget cannot make a test
  faithful, but the comparison is not clean.
- **n = 2, one run per model.** A repeat would replay from the attempt cache and prove only
  determinism.
- **`e17c686`'s real regression was not re-attempted** with the units that carry it. That is a
  paid run and it belongs with owner item 1's fix, not before it.
- **Seven of the nine `G-RELEASE-001` drills, `G-SEC-002`, and the kill switch/rollback on the
  pilot repository** are still not started — unchanged from the last window.

## 6. For the owner — three yes/no questions, defaults in brackets

1. **Make the generated reproduction self-contained** — one sentence in the generation prompt
   ("the file must import only from the project's own packages; inline any helper you were
   shown"), a check that rejects an import of a test module, then re-run the two real cases?
   Three of three remaining failures across both models are this. [yes]
2. **Run the reproduction-generation call on `claude-opus-5`** in the next measurement, with
   proposals left on `claude-sonnet-5`? On the one comparable case this turned 0 receipts into
   2; it roughly doubles the cost of the generation stage and the evidence is n = 1. [yes]
3. **Make the 60% discovery share literal for the first unit too?** It would need the default
   per-review budget raised from $0.25 to roughly $0.70, on the sample estimates seen on real
   traffic — every consuming repository pays it. [no]
