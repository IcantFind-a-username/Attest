# The derived probe cannot reach these projects, and the relaxations do not save it

**Owner instruction of 2026-09-10**, deciding whether D-206's route is worth further
development before any of it is built. Recorded as D-212. Run
[`34505755646`](https://github.com/IcantFind-a-username/Attest/actions/runs/34505755646) at
`282d39e`, `ubuntu-latest`. **Free by construction:** no model, no execution, no docker, no
secret, read-only permissions, **$0.00**, no DEVSPEND reservation because there is no spend.

**The one sentence, which is the question that was asked.** Relaxing all three rules —
methods on a literal receiver, locals assigned a literal, parametrized literal argument sets —
takes the held-out corpus from **2 of 39 cases to 5 of 39**. That is single digits, so **this
route does not work on projects that look like these**, and the effort belongs on the intent
clause instead.

## 1. The answer, and the ladder

39 cases, 55 changed definitions, 2310 call sites in the test trees.

| rule | sites | anchors | **cases with ≥1 derivable** |
|---|---|---|---|
| `current` (the product today) | 1980 | 2 of 55 | **2 of 39** |
| `+method` | 1987 | 5 of 55 | **5 of 39** |
| `+local` | 1980 | 2 of 55 | **2 of 39** |
| `+parametrize` | 1980 | 2 of 55 | **2 of 39** |
| **all relaxations** | 1987 | 5 of 55 | **5 of 39** |

The site column is large and means less than it looks: 1980 sites sit on **2** changed
definitions, because a sympy utility is called from everywhere. **A probe is per candidate, so
one admitted site is all an anchor needs** — the anchor and case columns are the ones that
decide anything.

**Only `+method` moves anything at all.** `+local` adds one anchor and no case; `+parametrize`
adds none. The three cases `+method` gains are `pytest-dev__pytest-10051`,
`pydata__xarray-6992` and `sympy__sympy-24539`.

## 2. Why the refusals happen

| reason a call site is refused now | sites |
|---|---|
| **derivable now** | **1980** |
| non-literal argument: local variable | 194 |
| **method (not derived in this version)** | **122** |
| non-literal argument: constructed object | 8 |
| non-literal argument: fixture parameter | 3 |
| non-literal argument: other expression | 3 |

And at the anchor level, which is where the population is actually lost:

| | anchors, of 55 |
|---|---|
| **no call site in the test tree at all** | **19** |
| **the changed line is not inside any `def`** | **14** |
| definition absent or ambiguous | 5 |
| in a nested function | 2 |

**25 of the 39 cases have zero test call sites** for anything the diff changed. That is the
finding, and no rule about arguments touches it: before literals or receivers or `parametrize`
are argued about, two thirds of the corpus offers **nothing to derive from**. A gold patch
in SWE-bench Verified frequently changes a method body, a module-level constant, or a branch
inside a function that the project's tests reach only indirectly.

## 3. The harness is validated against the paid run, not merely asserted

This is an offline prediction of what a paid run did, so it can be checked against that run.

| | offline prediction | D-211's paid run (`34478078680`) |
|---|---|---|
| cases where a derived probe exists | `sympy__sympy-23534`, `pylint-dev__pylint-7277` | `sympy__sympy-23534`, `pylint-dev__pylint-7277` |
| derived probes produced | 5 | 5 (`screened` 4 and 1) |

**Exact agreement, case for case and probe for probe.** The offline measurement reproduces the
paid run's ledger without spending anything, which is what licenses using it to decide.

## 4. The control: the rule is not broken, and that is the point

The same script, the same rules, on a repository whose tests were written by the people who
wrote the rules. 200 module-level functions sampled **round robin across files** (path order
would sample only the alphabetically-early modules).

| rule | sites | anchors | files with ≥1 |
|---|---|---|---|
| `current` | 103 | **22 of 200** | 17 of 80 |
| `+method` | 103 | 22 | 17 of 80 |
| `+local` | 114 | 23 | 17 of 80 |
| `+parametrize` | 105 | 23 | 18 of 80 |
| **all relaxations** | 116 | **24 of 200** | 18 of 80 |

**11% of this repository's module-level functions are derivable today** and `derive_probes`
returns 62 probes over the sample. So the mechanism works where the tests call module-level
functions with literals — which is what this project's own tests do and what `sympy`,
`xarray`, `sphinx` and `pylint` largely do not.

**And the relaxations barely help here either**: 22 anchors to 24. That is the result which
generalises. The relaxations were the hypothesis, and they are refuted on both corpora.

Two supporting observations, both free:

- The **changed-function arm** — anchoring on what recent commits actually touched rather than
  on every definition — found **20 anchors, 9 test call sites, 0 derivable** when run on a
  development host. A spot check of one module's 96 local-variable refusals found **93 are
  locals assigned from a call, not a literal**, which is why `+local` is nearly flat on real
  code.
- **That arm measured nothing on the runner and its printed zero is void.** `actions/checkout@v4`
  clones shallow, so `git log -40` has no parent to diff against and it reported 0 anchors —
  which reads exactly like "nothing is derivable". The workflow now checks out full history and
  the driver **refuses and says so** rather than printing a zero it did not earn. **The runner's
  changed-function table from run `34505755646` is not evidence and is not quoted above.**

## 5. What is claimed, and what is not

**Claimed.** On this corpus, with these rules and three named relaxations counted generously,
a derived probe exists for 5 of 39 cases.

**Not claimed.**

- **Not that 5 of 39 would become 5 receipts.** A derived probe still has to survive screening
  and then certify; D-211 showed all 5 that existed were screened out. This measures *supply*,
  which is the thing that was unknown; it is an upper bound on what the route could pay.
- **Not that the relaxations are impossible.** They are counted here, not built. Each column
  takes the permissive answer wherever proving the strict one needs machinery that does not
  exist — `+method` in particular assumes attribute-call binding succeeds, which is precisely
  what D-206 avoided. **The real numbers can only be lower than these.**
- **Not a recall number.** `G-RECALL-002` stands at 2 of 31 — 6.5%, Wilson 95% [1.8%, 20.7%]
  (D-211), untouched by this.
- **Not that SWE-bench Verified is representative** of the repositories the product ships to.
  It is the held-out corpus this project committed to, and it is eight large, mature projects.

## 6. The decision this supports

**Stop developing the derived probe.** The generous ceiling is 5 of 39 cases, only `+method`
contributes, and the same relaxations move this repository's friendly code from 22 to 24
anchors of 200. The cost of the three relaxations is real — attribute-call binding is the
largest of them — and the measured supply does not pay for it.

**The reason is not that the rule is badly written.** It scores 11% on a repository whose tests
suit it. It is that 25 of 39 cases in the held-out corpus have **no test call site at all** for
what their diff changed, and a rule about arguments cannot reach a call that does not exist.

**Where the effort goes instead:** the intent clause, 14 of 67 verification attempts in D-211's
run. Its evidence source is an owner decision under `AGENTS.md` §16 and needs a preregistered
discriminator with its own control arm — not a threshold nudge.

## 7. Artifacts

| | |
|---|---|
| corpus measurement | [`evidence/2026-09-11-probe-reach-corpus.json`](evidence/2026-09-11-probe-reach-corpus.json) — 39 units |
| control, ceiling arm | [`evidence/2026-09-11-probe-reach-self-ceiling.json`](evidence/2026-09-11-probe-reach-self-ceiling.json) — 200 anchors |
| driver | [`scripts/corpus/probe_reach.py`](../../scripts/corpus/probe_reach.py), [`tests/test_probe_reach.py`](../../tests/test_probe_reach.py) |
| workflow | [`.github/workflows/probe-reach.yml`](../../.github/workflows/probe-reach.yml) |
| the run it predicts | [`34478078680`](https://github.com/IcantFind-a-username/Attest/actions/runs/34478078680), [report](2026-09-10-heldout-remeasurement.md) |

**Cost: $0.00.** Free by construction — the driver calls no model, executes nothing and opens
no socket; the runner minutes are free on a public repository.
