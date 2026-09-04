# The 48 drawered value receipts, adjudicated by hand: 12 of them, one line each

**Owner instruction 3 of 2026-09-05 (owner item 3 of the previous handoff).** **$0.00, no model
call, no execution** — the diffs, the generated reproductions and the ledger rows this host
already holds. Sample drawn from
[`evidence/2026-09-05-intent-v41-replay.json`](evidence/2026-09-05-intent-v41-replay.json).

## Why this exists

Under `attest.intent.v4`/`v4.1` the value class certifies **0 of 48**. That is a fact about the
rule. It says nothing about whether the 48 were defects, and "0 of 48" is only good news if the
48 were intended changes. Nobody had looked.

## How the 12 were drawn

Stratified, deterministic, fixed before any diff was read: order each stratum by
`sha256("adjudication/2026-09-05\n<task>/<candidate>")`, take the first *n* not already taken.

| stratum | asked for | pool | drawn |
|---|---|---|---|
| drawered by **(c) alone** — the clause under review | 6 | 14 | 6 |
| drawered by **(a)** and not by (c) | 3 | 4 | 3 |
| **v3 drawered it too** — so v4 is not the reason | 3 | 36 | 3 |

The 12 receipts sit on **8 distinct pairs**; four pairs contributed two receipts each.

## The one thing that decided every verdict: which way the pair was reviewed

Five of the twelve receipts sit on pairs where **`head` is `base`'s parent** — the review runs a
commit *backwards*. That is how an injected regression is made: take a `fix:` commit, call it
`base`, call its parent `head`, and the "change" under review is that fix undone. **The diff then
carries the fix's own docstring, tests and changelog with it**, because those went in with the
code. The column is in the table and it explains the result better than any clause does.

## The table

`verdict` is mine, from the diff and the reproduction. **`v4.1 right?`** asks only whether the
drawer decision matches the verdict — drawering an intended change is right, drawering a real
defect is a miss.

| # | stratum | receipt | pair | what the diff changed | what the generated test asserted | verdict | v4.1 right? |
|---|---|---|---|---|---|---|---|
| 1 | (c) | `us-stock-helper 75ce7a3425` `feeds/nasdaq.py` | **reversed** | `fix: stamp nasdaq halts at the halt time, not midnight`, **undone**: `_parse_eastern_stamp`, the 14 docstring lines explaining why `<pubDate>` is unusable, and 52 test lines all come out together | a 19:50 ET halt is stamped 23:50 UTC, not midnight, and survives the 6-hour lookback | **real defect** | **no** |
| 2 | (c) | `attest 0ab1e8313a` `execution/container_images.py` | forward | wraps the image build so `TimeoutExpired` becomes a typed `BootstrapFailed`; adds 24 test lines | the raw `subprocess.TimeoutExpired` propagates out of `ensure_image` | intended | yes |
| 3 | (c) | `us-stock-helper 240836f2e0` `patterns_shapes.py` | forward | drops the shared cursor so each pattern episode resolves independently; 12 new docstring lines stating the replay invariant, 223 new test lines | no two emitted double-bottom signals overlap in bar range | intended | yes |
| 4 | (c) | `attest 0e910940fa` `execution/container_images.py` | forward | same pair as #2 | `ensure_image` does **not** convert the timeout into `BootstrapFailed` | intended | yes |
| 5 | (c) | `us-stock-helper 1d0af73c3e` `scripts/smoke_live.py` | forward | rewrites the reporting contract — "response text, exception text, credentials … never reach stdout, stderr, or the JSON report" — in the module docstring and in 941 lines of its own tests | a `KeyError` raised inside the runner propagates instead of becoming `stage-failed` | intended | yes |
| 6 | (c) | `us-stock-helper 67dae52f8e` `patterns_shapes.py` | forward | same pair as #3 | no resolved head-and-shoulders triple reuses a peak | intended | yes |
| 7 | (a) | `attest 2878d4012e` `scripts/corpus/heldout_run.py` | forward | adds `--cap` and reads each case's results file: `json.loads(result_path.read_text())`, unguarded | `cmd_run` survives a truncated results file and still runs the next case | **real defect** (new code) | **no** |
| 8 | (a) | `corum c25c7fbb4c` `src/corum/models.py` | **reversed** | `fix: reject unrepresentable numeric metadata`, **undone**: an overflowing `Fraction` stops raising `ValueError` and becomes `finite = True`; 44 test lines come out with it | `Reviewer(cost=Fraction(10**400))` raises `ValueError` naming `Reviewer.cost` | **real defect** | **no** |
| 9 | (a) | `corum 7c88ff3d94` `src/corum/models.py` | **reversed** | same pair as #8 | the same, without the `float()` precondition | **real defect** | **no** |
| 10 | v3 | `us-stock-helper 16cab71ac4` `analysis_api/service.py` | forward | `fix: serve factor and adviser prose in chinese` — translates the degradation messages; 124 new test lines | the failure message is the English sentence | intended | yes |
| 11 | v3 | `us-stock-helper c5b90ad887` `scripts/local_runtime_support.py` | **reversed** | `fix: remember what each feed already published across restarts`, **undone**: the coordinator-state module, its 123 test lines, the env var, the README line and the plan document all come out | `build_component_environment` still sets `ANALYSIS_API_COORDINATOR_STATE` | **real defect** | **no** |
| 12 | v3 | `us-stock-helper 2a2e79e265` `analysis_api/adviser_provider.py` | forward | same pair as #10 | `NO_DECISION_REASON` is stable English text | intended | yes |

## The count

**v4.1 is right on 7 of 12.** And the split is almost perfectly along one line that has nothing to
do with the clauses:

| | receipts | verdict | v4.1 right |
|---|---|---|---|
| **forward** pairs (7 of 8 pairs' receipts) | 8 | 7 intended, 1 real defect | **7 of 8** |
| **reversed** pairs (3 pairs) | 4 | 4 real defects | **0 of 4** |

**Every forward-in-time change in this sample that v4.1 drawered was in fact intended, and v4.1
got all seven right.** Ten reproductions restate a value an author deliberately moved — a typed
exception, a replay invariant, a redaction contract, two translations, a deleted feature. On real
changes, "0 of 48" is mostly the rule working.

**Every reversed pair was a real defect and v4.1 missed all four.** Two ways, and they are
different problems:

- **#1 and #11 are clause (c) doing exactly what it says, on a diff it cannot read correctly.**
  Undoing a `fix:` commit removes the fix's docstring, its tests and its changelog entry in the
  same diff, because they arrived in that commit. Clause (c) sees a change that states its own
  intent, and it is not wrong about the diff — it is wrong about which direction time runs.
  **Every injected-regression corpus is built this way, so clause (c) will miss on all of them,
  and no narrowing of (c) can fix it.** It is a limit on what the clause can know.
- **#8 and #9 are clause (a), and (c) never even fired.** The reproduction is
  `pytest.raises(ValueError)`; there is no pinned value at all, so nothing could have been
  specified. Note also that this pair *did* move 44 lines of its own tests and clause (c) still
  missed it: the anchored symbol is the private helper `_require_non_negative_real`, and the
  tests name `Reviewer` and `cost`, never the helper. **(c) sees a symbol's name, not its
  callers.**
- **#7 costs nothing this product could have delivered.** The defect is in code the diff *added*;
  the base "passes" only because the base never read the file. Differential V cannot honestly
  certify a new-code defect at all, so this receipt was never publishable on other grounds.

## What this does and does not license saying

- **It does not license "v4.1 has 58% precision" or any rate.** n = 12, three unequal strata, and
  the sample is dominated by one property — pair direction — that is a property of the corpus, not
  of production traffic.
- **It does license one sentence about production**: *on changes that move forward in time, which
  is what a pull request is, every drawered receipt in this sample was a deliberate change.* That
  is the case the product actually meets, and it is the case v4.1 is right about.
- **It also licenses one warning**: *any future measurement of the value class on an injected
  regression corpus will understate it*, because clause (c) reads a reversed fix as an intentional
  removal. A corpus of real pull requests with adjudicated labels is the only way to measure this
  class, and this repository does not have one.

## Limits

- **The verdicts are mine and they are not blind.** I read the commit subject, which on 7 of the
  8 pairs announces the change in words, and I read the pair direction, which decided five of the
  twelve. A blind adjudication would be a different, better measurement and needs a second reader.
- **Nothing here is evidence about the classes v4 does not touch** — the crash and rejection
  receipts, which are the 9 that still certify.
