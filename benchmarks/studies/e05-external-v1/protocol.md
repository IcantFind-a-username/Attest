# e05-external-v1 — the two yellow lines on eight public repositories nobody here wrote

Study ID: `attest.e05-external.v1`. Ordered by owner authorisation 4 of the 2026-09-12 overnight
work order: *"e05-external-v1, 8 public libraries, the local review path, write to no
repository. Freeze the protocol before running."*

## 1. What this study asks, and what it cannot

E-04 stratum v3 put the value-class and gate yellow lines (D-222, D-223) in front of the
owner's own pull requests and produced **0 lines on 9 units** (D-225), with the ledgers that
would say why lost on the runner. This study asks the same question of traffic **the product
has never seen and this project does not own**: on the recent merged pull requests of eight
public Python libraries, what lines would an author have been shown, and what stands behind
each one. The eight are the `G-NULL-001a` clones — chosen in 2026-09-04 because they build
and import inside the product's container, and kept for that reason and no other.

**It is not a precision measurement.** Every line the run renders goes into a table with three
empty columns — *useful / true but useless / wrong* — that the owner fills by hand. Until
then the run says nothing about precision, and a line that carries no receipt says so in its
own evidence token. **It is not a recall measurement**: no defect was planted and none is
known. **It is not prospective**: every unit was merged before the freeze, and every sample
row says `prospective: false`.

## 2. The unit, fixed before the first run

- **Head** is the pull request's merge commit — what the target branch became when the pull
  request landed, a squash commit and a merge commit alike.
- **Base** is that commit's first parent: the target branch as it stood the moment before,
  which is `merge-base(head, target branch at merge time)`. The diff `base..head` is exactly
  what the pull request contributed and nothing that landed beside it.
- A pull request merged into a maintenance branch (`stable`, `3.1.x`) is a unit like any other;
  its merge commit is on that branch and the clone fetches every branch.

The shipped Action reviews `merge-base(base branch, head)..head` *before* a merge; this study
reviews the same change *after* it, from the merged side. The diff is the same set of changes
for a squash or fast-forward merge and the pull request's net contribution for a merge commit.

## 3. Selection, fixed before the first run

1. **Population**: the eight repositories in `authorization.json`, read-only clones under
   `.attest/corpora/<name>/` (AGENTS.md §7, D-070).
2. **Per repository, three units**: the three most recently merged pull requests by
   `merged_at` descending that **changed at least one Python file of the package itself** —
   a `.py` file outside `tests/`, `docs/`, `examples/` and packaging scaffolding — and whose
   diff does **not exceed 2,000 changed lines** (additions plus deletions, from the GitHub
   API's file list). A pull request that fails either rule is recorded in `selection.json`
   with its reason and the walk continues to the next.
3. **Order**: round-robin across repositories in name order, newest merged first within a
   repository, so the driver's cost cap removes units evenly rather than whole repositories
   off the end of the alphabet. **24 units.**
4. **Nothing is excluded after selection, nothing is re-sampled and nothing is retried.** A
   unit that cannot run records its DEFER or refusal reason and stays in the table.
5. `gh api` is read-only throughout. Nothing is written to any of the eight repositories,
   before, during or after the run.

## 4. Configuration

`per_pr_budget_usd = 1.00`, `k_samples = 5` (the shipped factory value, D-183),
`executor_profile = linux-container-v1`, context strategy r01, **`value_notes_visible` and
`gate_notes_visible` on** for every unit so every author-visible line is captured to the lines
file. `contained_attempt_voids` at the product default of the code that runs. **Cost cap
$4.80**, held by the driver as a hard cumulative cap that reserves each unit's `$1.00`
maximum before starting it (D-172); the owner's reservation for the main run is **$4.50** and
that is the number the dispatch passes, so the run cannot overshoot it and a unit the cap
refuses is named.

**The smoke, and why it is not a measurement.** AGENTS.md §9 requires one dispatch of the same
workflow to prove its artifact carries every class of path the report reads before a paid
dispatch. That dispatch runs **one unit** into `trials-smoke.jsonl` with the per-unit budget
lowered to **$0.30** by the driver's `--unit-budget`, because a $0.30 reservation cannot start a
$1.00 unit under the D-172 rule. The smoke's trial is not the unit's measurement: the same unit
is bought again at $1.00 in the main run, and only that trial counts.

## 5. What the run records

- `trials.jsonl`: one row per unit — candidates, eligible, attempted, certified, the
  would-publish ids, units read of planned, spend, elapsed, the executor profile.
- `lines-trials.jsonl`: every line the review would have put in front of an author, verbatim,
  rendered by the same functions `run_ci` renders with, with what stands behind each.
- the ledgers of the eight clones, uploaded with hidden paths (D-225), so every drawer
  observation that did **not** become a line can be read back to its reason.
- `selection.json`: the walk, every merged pull request looked at and why it was or was not kept.

## 6. What a pass means

There is no pass. The deliverable is the table in the dated report — every line with three
empty columns, one row per pull request with candidates, eligible, attempts, drawers, lines and
spend, the reason every drawer observation did not become a line, and the comparison against
the owner's own five pull requests reviewed the same night — and the owner's adjudication of it.
