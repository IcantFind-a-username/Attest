# `G-NULL-001a`, the independent population: built, then run — and it published on control 54

**Owner instruction 1 of 2026-09-05c (build, D-136) and instruction 2 of 2026-09-05d (the run).**
[Population](../../benchmarks/attest-v2/runs/2026-09-05-g-null-001a-independent-population.json).
§§1–5 are the 2026-09-05c attempt, which executed nothing
([result](evidence/2026-09-05-g-null-001a-independent.json), $1.075100 of $4.00). **§§6–9 are the
2026-09-05d run, which is the one that carries a result**
([result](evidence/2026-09-05d-g-null-001a-independent.json), $0.880000 of $6.00, $5.12 released).

**Headline: the run stopped at control 54 of 68 because a control published, and the publication
is a true positive on a live defect in `more-itertools` — not a false publication.** Under the
owner's standing rule it was neither fixed nor resumed. §7 is the root cause and §8 is what a
bound can and cannot say.

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

---

# The 2026-09-05d run

**Owner instruction 2 of 2026-09-05d.** Same 68-control manifest, not re-sampled and not touched.
Fresh driver log, so nothing was resumed: every control was bought again under one policy
version (`attest.intent.v4.1`) and one working-directory design (D-138). Reservation $6.00,
**spent $0.880000**, $5.120000 released.
[Log-derived result](evidence/2026-09-05d-g-null-001a-independent.json).

**Not "from scratch" in the sense of buying every token again, and the report says so.** The
proposal cache (R-02) is keyed by an immutable digest of the prompt, so the 45 controls the
2026-09-05c attempt had already sampled **replayed** their proposals instead of buying them. What
this run bought that the last one could not is the part that matters: reproductions that
**execute**.

## 6. What the run produced

| | |
|---|---|
| controls reviewed | **54 of 68** — the run stopped at the 54th |
| controls that produced any candidate | 10 |
| eligible candidates | 18 |
| reproductions attempted | 18 |
| controls the **policy** answered (§8) | **6** |
| controls `informative_controls` counts (§8) | **0** |
| **publications** | **1** — `more-itertools f4f2cfec9d`, §7 |
| **wrong publications** | **0** (§7: the publication is a true positive) |
| spend | $0.880000 |

The nine controls that reached a reproduction, with what stopped each:

| repo | control | age | cand | att | what the verification said |
|---|---|---|---|---|---|
| `attrs` | `1046c75480` | 1,072 d | 3 | 2 | **infrastructure** — `isolation backend unavailable: environment bootstrap failed (python 3.12)` |
| `attrs` | `38b299d4a4` | 1,742 d | 1 | 1 | **infrastructure** — `collection deferred` |
| `click` | `fde47b4b4f` | 665 d | 2 | 2 | intent: *intent stated in the change itself*; unfaithful test (fails on base too) |
| `itsdangerous` | `7f4dcf83a0` | 872 d | 3 | 2 | intent: *intent stated in the change itself* ×2 |
| `jinja` | `fed1b24d5f` | 1,989 d | 1 | 1 | intent: *intent stated in the change itself* |
| `jinja` | `9dae67bcc8` | 1,979 d | 4 | 4 | unfaithful ×4 — passed on head, base never executed |
| `more-itertools` | `5ace912b3c` | 3,207 d | 1 | 1 | **infrastructure** — `isolation backend unavailable (python 3.9)` |
| `more-itertools` | `fc929be9e1` | 2,479 d | 1 | 1 | intent: *value change confirmed, intent unknown* — generic constant |
| **`more-itertools`** | **`f4f2cfec9d`** | **2,442 d** | 4 | 4 | **1 certified and published**, 3 unfaithful — §7 |

**The host fault of §4 is gone.** A Docker Desktop restart cleared it; reproductions execute, and
D-138 moved every working directory out of `/Users` so the class of fault cannot block execution
from that direction again. Three of the eighteen attempts still DEFERred on infrastructure, but
on a *different* cause — the container image bootstrap for a project declaring Python 3.9 or
pinning its own Dockerfile — and that is the ordinary backlog, not a host outage.

## 7. The stop: `more-itertools f4f2cfec9d`, and why it is a true positive

The driver stops the moment a control publishes (`RISK-CERT-01`). It fired on the 54th control
and the run was **not resumed and not fixed**, per the owner's standing rule.

**The control.** `f4f2cfec9d`, 29 Dec 2019, *"In `divide`: avoid tuple conversion if possible"*.
It qualified: 2,442 days old, and **its added lines are untouched at the default-branch tip
today** — `divide` still carries them, 6.7 years on. The diff:

```python
-    seq = tuple(iterable)
+    try:
+        iterable[:0]
+    except TypeError:
+        seq = tuple(iterable)
+    else:
+        seq = iterable
```

**The receipt.** `a665516a07…` for candidate `79f0b29318`, `regression_reproduced`,
`head_fail_base_pass`, head FAIL 3/3 and base PASS 3/3 in `linux-container-v1`, under
`attest.intent.v4.1`. The bundle **verifies offline with its seal**:

```
accepted: receipt a665516a077c7ff5ae0128cd31429e34e4fa18dd8af7d536f06f8ed49940c195
for 79f0b29318 (linux-container-v1); seal verified
```

**The claim is true, and a plain `dict` is enough to show it.** The guard catches `TypeError`
only. Any object whose `__getitem__` raises something else for a slice escapes it, and the base
revision — which only ever called `tuple(iterable)` — handled all of them. An [independent probe](evidence/2026-09-05d-divide-probe.py)
(no product code: `base_divide` and `head_divide` transcribed straight from the two revisions)
over thirteen ordinary input types:

| input | base | head |
|---|---|---|
| `list`, `tuple`, `str`, `range`, generator, `deque`, `array`, `set`, `StringIO` | ok | ok |
| **`dict`** | `[[0,1,2],[3,4],[5,6]]` | **`KeyError: slice(None, 0, None)`** |
| **`OrderedDict`** | ok | **`KeyError`** |
| a mapping whose `__getitem__` raises `KeyError` | ok | **`KeyError`** |
| a legacy sequence-protocol iterable | ok | **`IndexError`** |

**And there is a second finding inside the first: the defect was not reachable when it was
written.** `slice` objects became hashable in **Python 3.12**; before that `{}[:0]` raised
`TypeError` — which the guard catches — and the code was correct. On Python 3.12 the same
expression raises `KeyError`, and a six-year-old line became a live regression without anyone
touching it. This run is on Python 3.12.2.

**So the root cause is not in the certification path.** Nothing in the rule misfired: the
differential is real, the binding holds, the intent observer saw a crash rather than a value
change and correctly declined to drawer it. **The root cause is the control definition.**
"at least six months old, and no later commit touched the added lines" is a proxy for "carries no
defect", and this commit is the counterexample: an obscure regression that nobody hit stays
untouched forever, and a language change can make an old line newly wrong.

That is the second time this corpus has produced a true positive on a commit it filed as a
control (2026-09-03g, `Attest 506aae1a13`), and the first time on a **public** repository the
project does not own.

## 8. What a bound can say, and the denominator problem it exposed

**Nothing useful, and the reason is worth more than the number.**

`informative_controls`, as D-136's driver defines it, counts a control with `attempted > 0` and
**no verification line at all**. On this run that count is **0** — including the control that
*published*, because three of its four candidates were drawered and each wrote a line. **A
definition that calls a publishing control uninformative is degenerate**, and this run is what
made that visible; the 2026-09-05c attempt could not, because it executed nothing.

The driver therefore now also reports `answered_controls`: `attempted > 0` and **no
infrastructure** defer, with the infrastructure prefixes written into the driver
(`isolation backend unavailable`, `collection deferred`, `executor failure`,
`process containment unavailable`, `shared verification deadline`, `budget`, `could not create`,
`unsupported anchor language`). Everything else — an intent drawer, a reproduction refuted on
base, a candidate that did not reproduce — is **the policy answering**, and answering is what a
null study measures. Both numbers are reported; neither replaces the other; the strict one is
kept because it is the more conservative denominator and its degeneracy is now on the record.

On this run: **6 policy-answered controls, 1 publication, 0 wrong publications.** Rule of three
gives a 95% upper bound of **3/6 = 50%**, which is no bound at all. **`G-NULL-001a` has no
independent bound, and this run does not give it one** — 54 of 68 controls, stopped early, and
only 6 of them ever put the rule in a position to answer.

The first population's 5.2% on 58 controls still stands as the only bound, with its caveat
unchanged: it was taken on the controls the rule was revised against.

## 9. What is owed

1. **The owner's call on the control definition** (handoff item 1). Three readings, and this
   report does not choose between them: exclude `f4f2cfec9d` with its row labelled and resume
   (the 2026-09-03g precedent); tighten the definition so a control must also be *unreachable* by
   the current interpreter's semantics (hard, and probably circular); or accept that a null
   study's controls carry a real base rate of true defects and report the bound as a bound on
   *wrong* publications only, adjudicating each one.
2. **The 14 unreached controls**, and the 3 that DEFERred on the image bootstrap. About $0.30 at
   this run's measured $0.0163 per control.
3. **An upstream report to `more-itertools`** is a judgment call for the owner, not the agent:
   the defect is live at their tip, and the reproduction is in the bundle.
