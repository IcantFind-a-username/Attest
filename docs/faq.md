# FAQ — why it said nothing, and what to do about it

Most of the time attest is silent. That is the design, not a fault: it publishes only claims
backed by a reproduction it can verify offline, and it says so when it cannot. This page is
what to read when the silence is the thing you want explained.

## Why was my pull request silent?

Every review ends with one accounting line naming what happened:

```text
read 3/13 units, candidates 27, drawer 27 (no-reproduction-bought 14, budget-exhausted 8,
probe-deferred 5); verified 0, discarded 0; spend $0.9061 of $1.00; 194.3s.
```

Run `attest review --explain` (or read the run status on the pull-request comment) for one line
per silent candidate: its coordinate, the class of reason it is in the drawer for, and what it
cost. `attest review --json` gives the same thing to a machine.

### The drawer reasons, one by one

| reason class | what actually happened | what you can do |
|---|---|---|
| **no reproduction bought** | the candidate was never ranked high enough for the budget to reach it — **or it was never eligible for a reproduction at all**, which on the 2026-09-07 corpus was 163 of the 167 in this class (new code, or a non-Python anchor) | raise `budget-usd`, but read *"Should I raise the budget?"* below first |
| **ranked below verification cap** | the ranking *reached* this candidate and declined to buy it: a review verifies at most `verification_cap_per_unit` candidates per changed file, and this one was below that line by cluster size and static credibility | raise `verification_cap_per_unit` in `.attest.toml` if you want more reproductions inside one file. It cannot change what publishes, only what is tried |
| **budget-exhausted** | generation for this candidate would have exceeded the per-review budget | the same answer |
| **intent stated in the change itself** | the diff's own docstring, test or changelog says the behaviour was meant to change, so the "regression" is a feature | nothing — this is the level working |
| **value change / constant change, intent unknown** | head returns a different value from base, and the base tree does not say what that value should be | write a test or a docstring that pins the intended value; the clause reads the base tree |
| **behavior change, intent unknown** | head rejects an input base accepted, with no base-tree witness that the input was ever valid | as above |
| **probe deferred / refused / no observation** | the reproduction *probe* could not be recorded on the merge base — the base tree would not build, the call would not run, or the observation was not stable across repeats | usually an environment problem; check the run status for the bootstrap line |
| **probe replay failed on base** | the recorded observation did not replay identically, so the reproduction is not a differential | the function is probably non-deterministic; attest cannot certify those |
| **generation failed** | the model could not produce a test that collects | nothing you can do; it is recorded, not hidden |
| **unfaithful generated test** | the test failed on the *merge base* too, so it proves nothing about the change | nothing; the run refused it, which is the point |
| **not reproduced on head** | the test passed on head — the candidate was **refuted**, not merely unproven | nothing; this is a real answer |
| **isolation backend unavailable / collection deferred / executor failure** | docker was missing, the image would not build, or pytest would not collect | see [`support-matrix.md`](operations/support-matrix.md) |
| **shared verification deadline** | the stage ran out of wall clock before reaching this candidate | raise `verification-timeout` |
| **ineligible** | the anchored file is not Python, or the candidate is new code with no merge base (that is the gate level's business, and it is in shadow) | nothing |

## Should I raise the budget?

Probably not, and there is a measurement rather than an opinion behind that. The 17 commits
whose candidates died with the budget gone were re-reviewed at four times the budget
([report](acceptance/2026-09-07-budget-rerun.md)):

- spend **$1.64 → $10.32**, candidates **105 → 331**, and **not one verdict moved**;
- candidates refused *for budget* went **up**, 40 → 44.

Raising the budget raises discovery, and discovery re-starves the budget. Raise it when you have
a specific pull request whose accounting line says `budget-exhausted` on a candidate you have a
reason to care about — not as a standing setting.

The knobs, in `.attest.toml` or as Action inputs:

```toml
budget_usd = 1.00        # per review; over it, an explicit DEFER, never a truncated answer
daily_budget_usd = 0.0   # per repository per rolling 24h; 0.0 is off
repro_concurrency = 2    # candidates whose reproductions may overlap; 1 restores serial
verification_timeout = 600
```

## How do I read a receipt?

A `[red]` line ends with `receipt <12 hex>`. That names an **evidence bundle** written under
`.attest/evidence/<task>/<candidate>/`, and the bundle — not this process — is the thing you
should believe. It contains:

| file | what it is |
|---|---|
| `receipt.json` | the claim, the two commit ids, the policy, and the digest of every run |
| `test_repro.py` | the exact test that ran, byte for byte |
| `runs/head-1..3/`, `runs/base-1..3/` | stdout, stderr, JUnit XML and a record per run |
| `manifest.json` | a SHA-256 of every file above |
| `task.json`, `policy.json`, `subject.json` | what was being reviewed, under which policy |
| `intent.json`, `binding.json` | why the failure counts as a regression, and that a changed line ran |

The evidence block under the comment carries the `pytest` command; you can run it yourself.

## How do I verify a bundle offline?

```bash
attest verify --bundle .attest/evidence/<task>/<candidate>
```

It recomputes every digest and every binding **from the files alone** — no repository access, no
network, no model, no subprocess. Any byte that disagrees with a recorded digest, any run that
disagrees with its siblings, and any receipt field that disagrees with the recomputed evidence
is a rejection with the reason named. A receipt that will not verify offline is not evidence,
and attest refuses its own output on that test before publishing it (D-124).

To sweep every bundle on a host:

```bash
python scripts/corpus/reverify_bundles.py --json report.json
```

## It said nothing at all — not even a silence line

Then one of four unsupported scenarios applies, and the one line you got names which:

- **no Python source** in the repository;
- **an unparsable dependency lock file**, so the reproduction environment cannot be built;
- **docker unavailable**, and head code runs only inside a container;
- **pytest could not be provided** in the built image — and since D-175 this line is decided by
  the build step that *actually* failed, so a project whose own `pip install` fails now gets
  `environment bootstrap failed …` instead, which is a different problem with a different fix.

All four exit **0**: an unsupported repository is not a failed review. A repository with **no
test suite** is *not* in this list — attest installs pytest itself and writes the test it runs.

## The silence line said something other than "nothing met an adjudicator's bar"

There are three verdicts, and which one you got is the whole message:

| line | what it means |
|---|---|
| `nothing met an adjudicator's bar` | every candidate was judged and none cleared its level's bar. **Still an abstention** |
| `the budget ceiling was reached; N candidate(s) were not verified` | the money ran out. Raise `budget-usd`; the units it never read were **not** reviewed |
| `executor unavailable: <reason>; N candidate(s) not verified` | **nothing was judged.** The host could not run the reproduction executor at all — most often because the job runs as root, which the containment guard refuses (D-177) |

## Does a silence mean my change is fine?

**No.** A silence is an abstention. Red speaks on 0 of 40 recent real commits, and not one of
those 40 is known to contain a defect, so that 0 is not a precision number and not a clean bill
of health. See the known limitations in the [README](../README.md).

## Where does my API key go?

Into your own runner's environment, and from there to the model provider. attest never stores,
transmits or logs it; the ledger redacts anything whose name looks like a credential. Fork pull
requests are refused before any credential is introduced.
