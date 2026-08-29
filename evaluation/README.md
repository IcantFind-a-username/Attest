# evaluation/ — measuring the pipeline against real repositories

Offline harness. It clones nothing and calls no model API; point it at existing
clones of real projects and it mines their history for ground truth.

```
pip install -e ".[dev]"
PYTHONPATH=evaluation python -m realdata.evaluate \
    --repos ~/clones/pygments ~/clones/requests ... --out out/
PYTHONPATH=evaluation python -m realdata.e2e_oracle \
    --repo ~/clones/pygments --work out/e2e --venv .venv
```

`ruff` must be on `PATH` — the T-channel measurement is the product's own
`collect_signals`, and a missing linter silently yields zero signals (the harness
probes for that separately and reports `cases_ruff_failed`).

`--from-raw` re-summarizes an existing `out/raw.json` without re-measuring.

## Modules

| file | what it does |
|---|---|
| `realdata/corpus.py` | mines labeled cases from git history: a bug-fix commit applied backwards (positive, with the true bug lines) or a docs/refactor commit applied forwards (negative) |
| `realdata/measures.py` | per-case measurements — hunk-map fidelity against the real blob, anchor admissibility under the path spellings a model might emit, T-channel hit rates at true vs. background lines, budget preflight, exhaustive gate-state enumeration |
| `realdata/evaluate.py` | drives the corpus, aggregates, cluster-bootstraps the T-channel LR, writes `raw.json` + `summary.json` |
| `realdata/e2e_oracle.py` | real worktrees with a real bug put back, run through the real CLI with the proposer replayed from history |

## Outputs

`raw.json` holds one record per case (fidelity / anchor / tier0 / budget blocks)
plus the PR-shape sweep and the gate enumeration. `summary.json` is the aggregate
that the report quotes. Reports live in `docs/evaluation/`.

## Reading the numbers honestly

- The proposer is never called. Cases 1–4 and 6 of the report do not involve a
  model at all; case 5 replays an *oracle* proposal built from history, which
  measures the gate, not the model.
- "True bug lines" are the lines a later fix had to change — a superset of the
  defect itself, and the closest thing to ground truth history provides.
- T-channel rates depend on each repository's own ruff configuration; the pooled
  number hides real per-repo spread.
