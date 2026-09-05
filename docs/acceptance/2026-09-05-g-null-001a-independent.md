# `G-NULL-001a`, the independent population: n = 68 built, 0 informative controls run

**Owner instruction 1 of 2026-09-05c. D-136.** Reservation $4.00, **spent $1.075100**, $2.9249
released. [Population](../../benchmarks/attest-v2/runs/2026-09-05-g-null-001a-independent-population.json),
[result](evidence/2026-09-05-g-null-001a-independent.json).

## 1. Why a second population at all

D-134's bound — 95% upper 5.2% on 58 controls with 0 wrong publications — rests on the
population **the last two intent revisions were written against**. `jinja ac3ac6c9` and
`urllib3 c7b9adcb` are both in it, and both are commits D-127 and D-132 were authored to
stop. A gate that a rule was tuned against measures the tuning, not the rule.

## 2. What was built

| | first population | **independent** |
|---|---|---|
| clones | the same eight | the same eight |
| cutoff | 2026-03-04 | 2026-03-04 |
| control definition | 2026-09-04 amendment | unchanged |
| seed | `g-null-001a/2026-09-04` | **`g-null-001a-independent/2026-09-05`** |
| pool | all pre-cutoff Python commits | the same, **minus the 903 commits the first draw examined** |
| quota / attempts | 13 / 120 | **16 / 300** (the ladder's second rung) |
| examined | 402 | **1,746** |
| **qualified (n)** | **58** | **68** |
| **overlap with the other** | — | **0** |

Per clone: `attrs` 16, `click` 16, `more-itertools` 16, `urllib3` 7, `jinja` 5, `packaging` 4,
`python-dotenv` 3, `itsdangerous` 1.

**The ladder is preregistered, not a knob.** At the first population's own setting the disjoint
draw yields n = 31 — the first draw had already taken the commits that qualify most easily, and
the binding constraint is qualification *attempts*, not quota. The driver carries a fixed ladder
`(13, 120) → (16, 300) → (20, 600) → (25, 900)`, draws **once** at the deepest rung and reads
back the smallest rung reaching n ≥ 50. Because the seeded order is fixed, a smaller rung's draw
is a prefix of a larger one's, so this is the draw and not an estimate of it. Sampling is free
and the rung settled before any paid call.

## 3. What the run produced, and why it is not a bound

| | |
|---|---|
| controls reviewed | **45 of 68** |
| eligible candidates | 13 |
| reproductions attempted | 13 |
| **reproductions that executed** | **0** |
| **informative controls** | **0** |
| publications | 0 |
| spend | $1.075100 |

All 13 attempts DEFERred: six on `isolation backend unavailable: environment bootstrap failed …
Docker`, seven on `collection deferred: reproduction timed out after 60s (after 2 generations)`.

**No bound is computed from this and none is claimed.** A control that cannot buy evidence
cannot publish, so "0 publications" over 45 such controls carries no information about wrong
publication. The result file reports `informative_controls` beside `reviews` for exactly this
reason, and the driver's table now reads the run's own log rather than the ledger — a
`review_run` ledger row carries no head sha, so a ledger-only table cannot say which control a
row is about.

## 4. The host fault, isolated

Every Docker bind mount of a path under `/Users/franz` hangs indefinitely:

```
docker run --rm --network none --read-only \
  --mount type=bind,src=/Users/franz/Documents/Attest/docs,dst=/x,readonly \
  --entrypoint /usr/bin/env python:3.12-slim true      # no return in 40 s
```

The same command with `src=/private/tmp` returns in **1.3 s**, and a container run against a
worktree placed under `/private/tmp` collects the very reproduction that timed out in **0.23 s**.
It is not this product: red's own differential path DEFERs identically, and the gate level's
does too. It is not load: it persists at load average 6. No container of any project on this
machine holds a `/Users/franz` mount, and Docker Desktop's settings store carries no
file-sharing entry to repair.

**The remedy is a Docker Desktop restart**, which would stop three containers belonging to other
work on this machine — one of them ten hours old. That is not an agent's call, so the run was
stopped rather than continued into more DEFERs.

## 5. What is owed

Resume on a host whose container backend works — the driver skips nothing and re-runs nothing:

```bash
.venv/bin/python scripts/corpus/null_study.py run --independent --budget 1.00 --cap 3.00 --log <log>
```

Then `table --independent --log <log>`. The remaining 23 controls plus a re-run of the 13
DEFERred ones is what the bound needs; at the measured $0.024 per control it is well inside a
$3 reservation.
