# e05-external-v2 — the second batch: twenty merged pull requests of five libraries the probe kept

Study ID: `attest.e05-external.v2`. Ordered by owner authorisation 2 of the 2026-09-13 window:
*"e05 batch 2, candidates werkzeug, markupsafe, requests, httpx, platformdirs, jsonschema, tomli-w,
anyio; run the free evaluability probe first, keep the first six that pass, four recent merged
pull requests each; freeze before any unit runs; the same gates as v1."*

## 1. What this study asks, and what it cannot

v1 ([`e05-external-v1`](../e05-external-v1/protocol.md), D-230) put the product's lines in
front of 24 merged pull requests of eight libraries it had never seen and produced six lines,
two of which the owner read as over-claims and three rules followed (D-232, D-233, D-234). This
study asks the same question of **twenty more pull requests of five more libraries**, under
those rules: what lines would an author have been shown, and what stands behind each. It is the
second population the README's adjudicated numbers are drawn from.

**It is not a precision measurement**: every line goes into a table with three empty columns
the owner fills by hand. **It is not a recall measurement**: no defect is known. **It is not
prospective**: every unit was merged before the freeze, and every sample row says so.

## 2. The population, decided by a probe that ran before the freeze

Eight candidates in the owner's order (`candidates.json`). Before anything else, the free
evaluability probe (`scripts/corpus/e05_probe.py`, the held-out corpus's probe of D-186/D-213)
cloned each without a credential, built the product's reproduction image for its default-branch
tip and collected a stub that imports its top-level package inside that image. **The
population is the first six candidates whose probe passes; five passed**, so it is five:

| candidate | probe | why |
|---|---|---|
| `pallets/werkzeug` | **kept** | builds and imports |
| `pallets/markupsafe` | **kept** | builds and imports |
| `psf/requests` | **kept** | builds and imports |
| `encode/httpx` | excluded | its pytest configuration names a `trio` warning filter the image does not carry (`PytestConfigWarning: Failed to import filter module 'trio'`); the reproduction collects the same way and would fail the same way |
| `tox-dev/platformdirs` | excluded | `ModuleNotFoundError: No module named 'platformdirs.version'` in the image -- a generated version module absent from the tree |
| `python-jsonschema/jsonschema` | **kept** | builds and imports |
| `hukkin/tomli-w` | **kept** | builds and imports |
| `agronholm/anyio` | excluded | its pytest configuration loads the `pytest_mock` plugin, which the image does not carry |

**Two dispatches, both recorded.** The first (run `34659453810`, `probe-run-1.json`) failed
`werkzeug` and `markupsafe` on the probe's own stub -- a tuple literal in an `assert`, which
pytest's assertion rewriter warns is always true and which a project with `filterwarnings =
error` refuses at collection -- and not on their trees. The stub was fixed to assert nothing a
rewriter calls trivially true and the probe re-run (run `34659752086`, `probe.json`); the three
exclusions are the same in both. Both files are committed. No outcome of any unit existed when
either ran.

**Twenty units, not twenty-four.** The owner's rule is four per kept library and the probe kept
five; the rule stands and the count is what it produces.

## 3. The unit and the selection, fixed before the first run

The unit is v1's: head = the pull request's merge commit, base = its first parent. Selection is
v1's with one number changed: **per repository, the four most recently merged pull requests** by
`merged_at` descending that changed at least one Python file of the package itself and whose
diff does not exceed 2,000 changed lines; the walk is recorded in `selection.json`; round-robin
across repositories in name order; nothing excluded after selection, nothing re-sampled, nothing
retried; `gh api` read-only throughout and nothing written to any repository.

## 4. Configuration

`per_pr_budget_usd = 1.00`, `k_samples = 5`, `linux-container-v1`, context strategy r01,
`value_notes_visible` and `gate_notes_visible` on, `contained_attempt_voids` at the product
default. **The code is `release/batch2`**, which carries D-232 (`attest.intent.v5`), D-233 and
D-234. **Cost cap $3.80**; the owner's reservation for the run is **$3.50** and that is the
number the dispatch passes as the driver's hard cumulative cap (D-172).

**The smoke**, as v1's: one unit under `--limit 1 --unit-budget 0.30` into `trials-smoke.jsonl`,
proving the artifact carries a ledger and a lines file (AGENTS.md §9); not a measurement.

## 5. What the run records, and what a pass means

As v1: `trials.jsonl`, `lines-trials.jsonl`, the clones' ledgers with hidden paths, and
`selection.json`. There is no pass; the deliverable is the table with three empty columns in the
dated report, and the owner's adjudication of it.
