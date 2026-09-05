# The E-02 held-out slice, re-run under the probe generator — 2026-09-06c

Owner instruction 2 of this window: **re-run the held-out slice on the probe path, under
`attest.intent.v4.1`, at `--budget 1.00`; give old and new columns for built, certified,
published, drawer and unrecordable; replace the README's numbers with the new ones and keep the
old ones on one line labelled "old generator".**

This is the number `v0.1` condition 4 and `G-RECALL-002` have been waiting for: **the first
held-out figure taken under the current policy.** The 5-of-29 the README carried predates intent
v3, v4 and v4.1, D-124's bundle integrity, D-138's working directory and D-146's generator.

**Spend `$3.0058` of a `$15.00` reservation**, plus **`$1.4490` abandoned over two false starts**
(§5). Population, cutoff and quota are the ones committed on 2026-09-03 and are **not**
re-sampled; results went to a fresh `.probe` suffix so the `.heldout` column survives untouched.
Local review only — no GitHub client is constructed, so no publication surface exists.
[Driver](../../scripts/corpus/heldout_run.py) · [plan](../../benchmarks/attest-v2/runs/2026-09-03-e02-heldout-plan.json).

## 1. The two columns

| | old (2026-09-03, legacy generator, `--budget 0.25`) | **new (probe + record/replay, `--budget 1.00`)** |
|---|---|---|
| defect cases run | 29 | **28 of 29** (§5) |
| — **built** (the environment ran a reproduction) | 10 | **28** |
| — **certified** (cases) | 5 | **4** |
| — **published** (findings) | 7 | **4** |
| control cases run | 39 | **40** |
| — **false publications** | **0** | **0** |
| **drawer** (verification verdicts that are not a receipt) | 61 | **62** |
| — **unrecordable** (the probe refused the recording) | — | **10** |
| spend | $1.7899 | **$3.0058** |

Drawer reasons, side by side:

| reason | old | **new** |
|---|---|---|
| the environment did not build | **49** | **0** |
| **`attest.intent.v4.1` refused the intent** | **0** | **24** |
| the test passed on head (no differential) | 1 | **17** |
| **unrecordable** — the probe refused the recording | — | **10** |
| host or collection deferred | 1 | 8 |
| unfaithful reproduction | **9** | **3** |
| other | 1 | 0 |

## 2. What the columns say, in order of how sure it is

**1. The environment is no longer the wall, and it was most of the old column.** 49 of the old
column's 61 drawer verdicts were `environment bootstrap failed`; the new column has **none**.
That is the 2026-09-03 bootstrap fix, not this window's work, and it means **the old column's
"5 of 29" was really "5 of the 10 whose environment built"** — the README always said so and the
comparison has to keep saying it. On a like-for-like basis the old column certified **5 of 10
built** and the new one **4 of 28 built**.

**2. `attest.intent.v4.1` is now the wall, and it costs four real defects.** 24 of 54 drawer
verdicts are intent refusals, and **all four cases the old column published and the new one does
not were lost to one clause** — *"value change confirmed, intent unknown: the base tree does not
specify the value this assertion pins"*:

| case | old | new | why |
|---|---|---|---|
| `psf__requests-1142` | published | **drawered** | value class, intent unknown |
| `psf__requests-1921` | published | **drawered** | value class, intent unknown |
| `pylint-dev__pylint-4551` | published | **drawered** | value class, intent unknown (8 candidates, 3 of them) |
| `pylint-dev__pylint-4604` | published | **drawered** | value class, intent unknown |

This is the same recall cost D-132/D-134 priced and D-140 measured at 0-of-1 on eleven forward
pairs, **now measured on a held-out slice of known defects where it is 4 of 8.** It is the
largest single number this project has on that clause.

**3. Three cases the old column could not reach are now published**, all `pytest`, all cases
whose environment had failed to build: `pytest-10051`, `pytest-6197`, `pytest-7324`. Their
receipts are ordinary regressions.

**4. Unfaithful reproductions fell 9 → 3, not 9 → 0.** The forward-pair run reported 20 → 0 and
that remains true of the class D-146 removed — *a model asserting a behaviour base does not
have*. The three that remain are a different failure the same word covers: *"it references a
symbol absent from head, so its head failure is a stale reference rather than a defect"*, which
the probe path can still produce because the model still chooses **what to call**.

**5. `probe refused` is a real and quantified recall cost: 10 of 62.** Some are the recording
refusing a value it could not reproduce three times; others are *"the probe observation is not
stable on base"* or *"the probe did not execute `pylint/constants.py` on base"*. Every one
of them is a candidate the old generator would have written a test for, and each is a case where
recording says *I cannot* rather than guessing.

**6. Zero false publications on 40 controls, as before.** The null side of condition 4 continues
to hold on this population; the recall side does not have a stated target to be measured against.

## 3. What this does and does not settle for `v0.1` condition 4

Condition 4 asks for **silent on every control** *and* **a stated non-trivial share of eligible
defects certified**. The first half holds: 0 of 40. The second half **has a number for the first
time under the current policy — 4 of 28 (14%), and every one of the 28 built — and no stated
target**, so it
cannot be scored. Naming the share is an owner decision, not a measurement.

## 4. The README's numbers

The measured table now carries the new column and keeps the old one on one line labelled
**old generator**, as instructed.

## 5. What was not run, and the two false starts, both on the record

**28 of 29 defects, and the missing one found a third defect.** `pytest-5840` and `pytest-8399`
were killed by the operator's stall watchdog after ten minutes; `pytest-5840` was re-queued and
ran. **`pytest-8399` cannot be re-run at all**, and the reason is worth more than the case:

```
ValueError: delivery journal requires one exact finalization
```

The kill landed **between that review's last delivery settlement and its journal finalization**,
so the ledger holds two intents, two settlements and no finalization — and every subsequent
`attest review` of that repository now **aborts at startup** reconciling it. The strictness is
correct: a torn journal *is* evidence that a run was interrupted. The response is not. It is the
same shape as **D-149** — a journal problem taking the whole review down instead of degrading the
one thing that depends on it — and it is recorded as **D-154** rather than fixed, because a
torn-journal recovery path touches the tamper-evidence design and inventing one at the end of a
window is how a rule ends up with a clause nobody measured.

**Two earlier passes were abandoned and their `$1.4490` is spent:**

- **Pass 1, `$0.6058`, 5 cases.** 14 of the first 19 crashed at startup on their own 2026-09-03
  ledgers — **D-149**, a real defect this run found and this window fixed.
- **Pass 2, `$0.8432`, 45 cases.** Killed by the operator: `impact.py` was edited while the run
  was importing it, so 24 later cases died on a transient `NameError`. **That is an operator
  error, not a product defect**, and the fix is the third pass's `--code /private/tmp/…`, which
  pins the product code to a git worktree at a fixed commit so the working tree can move under it.

Both passes' results were deleted rather than merged, so **every case in the reported column ran
under one implementation** — the project's standing rule, and the reason the money was spent
twice rather than the columns being mixed.
