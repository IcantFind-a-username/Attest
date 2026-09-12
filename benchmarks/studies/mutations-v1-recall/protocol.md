# mutations-v1-recall — red-level recall on forty injected defects, measured where the executor works

Study ID: `attest.mutations-v1-recall.v1`. Ordered by owner authorisation 2 of the 2026-09-13
window: *"a stratified random sample of 40 cases of the mutation corpus, forward direction only,
the held-out driver's settings, $5.00."*

## 1. What this study asks, and what it cannot

Every recall figure this project has published comes from SWE-bench Verified's held-out slice,
which is **reversed by construction** (D-158): the pull request under review repairs the defect,
and the generated reproduction is asked to fail on the fix. D-231 built a population that is not
reversed -- 122 crash mutations injected on lines each of eight public libraries' own tests
reach, each yielding a *forward* case whose head introduces the defect -- and reviewed none of it.
This study reviews a frozen sample of forty and asks: **of forty pull requests that each
introduce one crash, how many does red certify?**

It also asks the question D-232 raised in the same window. A mutation that raises on the line
it wrote -- a boundary swap that makes an index fall off the end, a guard deletion whose crash
lands on the mutated line itself -- is exactly the shape the frame rule now reads as a behaviour
change with unknown intent. The table reports how many of the forty D-232 sends to the drawer,
beside how many certify.

**It is not a precision figure**: every case carries a defect, so no line on it can be wrong
about that. **It is not natural traffic**: the defects are injected under three stated rules.
**It is not the whole corpus**: forty of 122, five per library, drawn under a recorded seed.

## 2. The unit, fixed before the first run

- **Base** is the library's default-branch tip as `mutations-v1` recorded it on 2026-09-12.
- **Head** is that tip with one recorded mutation applied as one commit, re-created on the runner
  from the site the sample records: kind, path, line, replacement text and span. The mutated
  bytes are therefore identical to the local corpus's; the commit sha is not, and is not claimed.
- Both revisions are the library's own tree; the mutation is a local commit pushed nowhere.

## 3. Selection, fixed before the first run

1. **Population**: the 122 forward cases of `.attest/corpora/mutations-v1/manifest.jsonl`
   (D-231), eight libraries.
2. **Sample**: per library, five cases drawn by `random.Random(f"{seed}:{library}").sample`
   over the library's forward cases sorted by instance id; seed `20260913`, written in the
   preregistration. Forty cases.
3. **Order**: round-robin across libraries in name order, so a cost cap removes cases evenly.
4. **Nothing is excluded after selection, nothing is re-sampled and nothing is retried.** A
   case the cap refuses, that fails to build on the runner, or that the product refuses is a
   miss, named in the table, and the denominator stays forty.
5. The sample is written by `scripts/corpus/mutation_recall.py sample` after the freeze and
   before any unit runs; `sample.jsonl` is committed.

## 4. Configuration

`per_pr_budget_usd = 1.00`, `k_samples = 5`, `executor_profile = linux-container-v1`, context
strategy r01, `value_notes_visible` and `gate_notes_visible` on, `contained_attempt_voids` at the
product default. **Cost cap $5.00**, held by the driver as a hard cumulative cap that reserves
each case's $1.00 maximum before starting it (D-172); a case the cap refuses is named.

**The smoke.** One case under `--limit 1 --unit-budget 0.30` into `trials-smoke.jsonl`, the
dispatch AGENTS.md §9 requires to prove the artifact carries a ledger and a lines file. Not a
measurement: the same case is bought again at $1.00 in the main run.

## 5. What the run records

- `trials.jsonl`: one row per case -- candidates, eligible, attempted, certified, would-publish
  ids, spend, elapsed.
- `lines-trials.jsonl`: every line the review would have shown, verbatim.
- the eight clones' ledgers, uploaded with hidden paths (D-225).
- `table.json`: each case's class from its own ledger, and the Wilson interval over forty.

## 6. What a pass means

There is no pass bar. `G-RECALL-002`'s 70% is a held-out gate and this is a different
population; the deliverable is the number with its interval, the D-232 count beside it, and the
per-class breakdown.
