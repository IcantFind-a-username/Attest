# e05-external-v3 — the third batch: merged pull requests of libraries the product has never seen

Study ID: `attest.e05-external.v3`. Ordered by owner instruction 2 of 2026-09-14: *"a third
batch; the owner adjudicates, written the same way as the first two batches; libraries outside
the thirteen already reviewed; $4 may be spent."* The owner writes the adjudication before
reading the agent's opinion of any line.

## 1. What this study asks, and what it cannot

v1 (D-230) and v2 put the product's lines in front of 44 merged pull requests of thirteen
libraries; after the rules that followed (D-232 to D-235) seven lines stand, all pending
adjudication as of the freeze, and none red. This study asks the same question of a third
population under the code of 0.3.0 (D-236 to D-244): what lines would an author have been shown,
and what stands behind each. It is the third population the README's adjudicated numbers are
drawn from, and the first reviewed with the value line carrying how its call was built (D-241).

**It is not a precision measurement**: every line goes into a table with three empty columns the
owner fills by hand. **It is not a recall measurement**: no defect is known. **It is not
prospective**: every unit was merged before the freeze, and every sample row says so.

## 2. The population, decided by a probe that runs before the freeze

Eight candidates in the recorded order (`candidates.json`), none of them among the thirteen of v1
and v2, none in the SWE-bench held-out slice or the mutation corpus, none a dependency of the
reproduction image itself: `python-babel/babel`, `pyparsing/pyparsing`, `dateutil/dateutil`,
`Delgan/loguru`, `mahmoud/boltons`, `tkem/cachetools`, `marshmallow-code/marshmallow`,
`jmespath/jmespath.py`. Before anything else, the free evaluability probe
(`scripts/corpus/e05_probe.py`) clones each without a credential, builds the product's
reproduction image for its default-branch tip and collects a stub that imports its top-level
package inside that image. **The population is the first six candidates whose probe passes**;
if fewer pass, the population is what passes. The probe ran once (run `34715274804`, dispatched on
the study branch before anything was selected; `probe.json`): **seven of eight passed, so the
population is the first six**, and the seventh is recorded and not in it. No outcome of any unit
existed when it ran.

| candidate | probe | why |
|---|---|---|
| `python-babel/babel` | **kept** | builds (Python 3.13) and imports |
| `pyparsing/pyparsing` | **kept** | builds (3.13) and imports |
| `dateutil/dateutil` | excluded | its classifiers stop at 3.12, so the image is built on 3.12, and the pytest the image installs for it carries an assertion rewriter that does `import imp` -- removed in 3.12 (`ModuleNotFoundError: No module named 'imp'`); collection fails before any test, and the reproduction collects the same way |
| `Delgan/loguru` | **kept** | builds (3.13) and imports |
| `mahmoud/boltons` | **kept** | builds (3.13) and imports |
| `tkem/cachetools` | **kept** | builds (3.13) and imports |
| `marshmallow-code/marshmallow` | **kept** | builds (3.13) and imports |
| `jmespath/jmespath.py` | passed, not kept | builds (3.13) and imports; the seventh to pass, and the rule keeps six |

**Twenty-four units.** Four per kept library, six libraries; the rule stands and the count is
what it produces.

## 3. The unit and the selection, fixed before the first run

The unit is v1's: head = the pull request's merge commit, base = its first parent. Selection is
v2's: **per repository, the four most recently merged pull requests** by `merged_at` descending
that changed at least one Python file of the package itself and whose diff does not exceed 2,000
changed lines; the walk is recorded in `selection.json`; round-robin across repositories in name
order; nothing excluded after selection, nothing re-sampled, nothing retried; `gh api` read-only
throughout and nothing written to any repository.

The walk runs after the freeze (the preflight refuses a unit recorded before `freeze_at`), on
2026-09-12 (host clock, UTC), against read-only local clones, and is recorded in `selection.json`: babel 4 kept of 6 walked (2 changed no package source), pyparsing 4 of 4, loguru
4 of 4, boltons 4 of 4, cachetools 4 of 35 (26 changed no package source -- release, CI and
documentation traffic -- and 5 merge commits do not resolve in the clone, each named), marshmallow
4 of 9 (5 changed no package source). `sample.jsonl` carries the 24 units, every row
`prospective: false`.

## 4. Configuration

`per_pr_budget_usd = 1.00`, `k_samples = 5`, `linux-container-v1`, context strategy r01,
`value_notes_visible` and `gate_notes_visible` on, `contained_attempt_voids` at the product
default. **The code is `main` after D-240 (`attest.intent.v5.1`), D-241, D-242, D-243 and D-244**,
at the SHA the run records. **Cost cap $3.70** for the run and $0.30 for the smoke, the owner's
$4.00 in all. Under D-244 a unit is admitted at the recent forty cases' p95 spend, not at its
$1.00 ceiling; the ceiling still binds what a unit may spend.

**The smoke**, as v1's and v2's: one unit under `--limit 1 --unit-budget 0.30` into
`trials-smoke.jsonl`, proving the artifact carries a ledger and a lines file (AGENTS.md §9); not a
measurement.

## 5. What the run records, and what a pass means

As v1 and v2: `trials.jsonl`, `lines-trials.jsonl`, the clones' ledgers with hidden paths, and
`selection.json`. There is no pass; the deliverable is the table with three empty columns in the
dated report, and the owner's adjudication of it -- written before the agent's reading of any
line, so that the two can be compared.
