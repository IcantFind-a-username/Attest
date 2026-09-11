# The held-out re-run: the environment gave three receipts, the search gave none

**Owner instruction of 2026-09-11**, §16 item 3: one paid held-out re-run, and only one. Run
[`34530619773`](https://github.com/IcantFind-a-username/Attest/actions/runs/34530619773) at
`6edb092` on `ubuntu-latest`, **3h33m17s**, `--k 5 --budget 1.00`, containers, local review
path only — no GitHub client is constructed, so no publication surface exists. This run alone
sets `contained_attempt_voids: false` (D-217); the product default does not move.

**$5.028893 of the $6.00 cap.** Why the cap is $6.00 and not the authorised $6.50 is in §5;
it is not a detail, because **the cap bound and four cases went unbought.**

## 1. The two lines the instruction asks for, and they are not the same line

This window changed two different kinds of thing, and reporting them together would let an
environment fix read as a reviewer improvement.

> **Measurement repair. 11 of the 18** cases whose probe never executed on the merge base on
> 2026-09-10 executed one this time. (17 of the 18 were bought; the 18th,
> `pydata__xarray-7393`, is one of the four the cap refused.) Over the whole corpus: **20 of
> 39 cases had a probe execute on base before, 29 of 35 now.**
> *This is D-214's era pins and font-cache warm, and D-217's contained attempts.*

> **Capability gain. Zero.** The search (D-216) bought **12 probes beyond the first** across 9
> cases. Three of them certified — and all three were **additional candidates inside cases
> that their own first probe had already certified**. It added **no certified case**. The one
> `did not reach the changed lines` verdict it was built to repair was handed to a second and
> a third probe, and **neither reached them either** (`pylint-dev__pylint-6528`, still
> `unbound`).

> **Under the shipped default.** **One of the five certified cases** — `sphinx-doc__sphinx-10435`,
> all three of its receipts — carries `contained_attempts: ["subprocess.Popen: 'git'"]` and
> would therefore be **void** under `contained_attempt_voids=True`, which is what every
> repository gets today. Counted from the field, not re-run: crash-class recall would be
> **4 of 25** rather than 5 of 25.

## 2. The table, with both denominators

| denominator | 2026-09-10 | **this run** |
|---|---|---|
| **cases run** (`heldout_compare.py`) | 2 of 39 — 5.1%, Wilson 95% [1.4%, 16.9%] | **5 of 35 — 14.3%, Wilson 95% [6.3%, 29.4%]** |
| **crash class** (`heldout_v2.py table`, `G-RECALL-002`) | 2 of 31 — 6.5%, Wilson 95% [1.8%, 20.7%] | **5 of 25 — 20.0%, Wilson 95% [8.9%, 39.1%]** |
| the same, with the contained-attempt case removed | — | 4 of 25 — 16.0%, Wilson 95% [6.4%, 34.7%] |
| value class, excluded (D-158) | 8 | 10 |
| cases not bought (the cap) | 0 | **4** |
| spend | $5.044872 of $6.50 | **$5.028893 of $6.00** |

**The crash denominator fell from 31 to 25 and that is not a improvement.** Four cases were
never bought — `sympy__sympy-24443` is named by the run log's refusal line, and
`pydata__xarray-7393`, `sympy__sympy-24539` and `sympy__sympy-24562` follow it — and two more
cases moved into the value class, which D-158 excludes. **A recall rate over a denominator
that shrank for reasons unrelated to the reviewer is a number to read carefully**, which is
why the cases-run row above is reported beside it: on that denominator nothing was dropped and
the movement is 5.1% → 14.3%.

## 3. Where the 18 went

| case | 2026-09-10 | this run | |
|---|---|---|---|
| `pydata__xarray-6599` | probe does not collect | **surfaced** | **NEW RECEIPT** |
| `pydata__xarray-6938` | probe does not collect | **surfaced** | **NEW RECEIPT** (3 candidates) |
| `sphinx-doc__sphinx-10435` | process guard: child process | **surfaced** | **NEW RECEIPT** (3 candidates, all contained) |
| `pydata__xarray-4687` | probe does not collect | binding | reached the code, missed the changed lines |
| `pydata__xarray-6461` | probe does not collect | intent clause | |
| `pydata__xarray-6744` | probe does not collect | intent clause | |
| `pydata__xarray-6992` | probe does not collect | intent clause | |
| `pydata__xarray-7229` | probe does not collect | intent clause | |
| `pydata__xarray-6721` | probe does not collect | probe recorded nothing | |
| `sphinx-doc__sphinx-10449` | process guard: child process | binding | |
| `sphinx-doc__sphinx-9711` | process guard: child process | intent clause | |
| `mwaskom__seaborn-3069` | process guard: thread | probe generation refused | the font-cache warm cleared the thread; the model's probe then would not parse |
| `mwaskom__seaborn-3187` | process guard: thread | probe does not collect | same: the thread is gone, the collection is not |
| `sphinx-doc__sphinx-10614`, `-11445`, `-11510` | process guard: child process | probe does not collect | the guard is gone; these trees still do not collect |
| `pylint-dev__pylint-4661` | probe does not collect | probe does not collect | the era pin did not fix this one |
| `pydata__xarray-7393` | probe does not collect | **not bought** | the cap |

**Nine of the eleven repaired cases did not certify.** They moved from *the probe never ran* to
*the probe ran and the adjudicators said no* — which is the whole point of the repair and is
also the reason the recall movement is smaller than the repair. The loss moved from the
environment to the intent clause: **12 → 19** cases end there.

## 4. What the search actually did

`attest.probe-observation.v3` makes this countable rather than arguable.

| | |
|---|---|
| probe observations recorded | **43** (25 on 2026-09-10) |
| `attempt_index` 1 / 2 / 3 | **31 / 8 / 4** |
| `feedback_kind` on the probes it bought | `no-difference` 8, `unrecorded` 3, `did-not-reach` 1 |
| probes bought after feedback that then certified | **3** — all inside `pydata__xarray-6938` and `sphinx-doc__sphinx-10435`, both already certified by their first probe |
| **certified cases the search added** | **0** |
| `did not reach` verdicts a later probe corrected | **0 of 1** |

The one case where the feedback loop had the shape it was designed for —
`pylint-dev__pylint-6528`, a first probe that did not reach the changed lines — bought two more
probes and ended `unbound` anyway. **On this corpus the search is not what is missing.**

It is also not free: the run took **3h33m** against 2h58m, for the same population minus four
cases, and that is the recording phase roughly doubling as predicted.

## 5. The cap, which is a finding

The owner's authorisation reserved **$6.50** against a stated cumulative of **$101.538013**.
That arithmetic did not include the self-reviews the work order's own *one pull request per
step* rule buys: this repository reviews its own pull requests, and this window's nine review
runs cost **$2.124361**.

| | |
|---|---|
| cumulative before the window | $101.538013 |
| self-reviews, 9 runs across PRs #35–#38 | $2.124361 |
| cumulative before the paid run | $103.662374 |
| headroom to the **$110 hard cap** | $6.337626 |
| held back for this window's last pull request | ~$0.35 |
| **cap dispatched with** | **$6.00** |
| **spent** | **$5.028893** |

**And it bound.** The run stopped at
`unit sympy__sympy-24443: skipped: cumulative cap: $5.0289 spent, reserving $1.0000 for this
unit would project $6.0289 past the $6.00 cap`, and three further cases went unattempted. At
$6.50 the reservation rule would have allowed one more case and probably not all four. The
four are named rather than dropped, and the denominators above say so.

## 6. What this run does not measure

- **No control arm.** Every row has `control: null`. This is recall-only and says **nothing**
  about false publications. The standing control evidence — 68 independent nulls + 40 held-out
  controls, 0 false publications, at K=4 — is untouched and unextended by it. *No sign of a
  false positive was seen, and with no control arm that is all that can be said.*
- **Precision is undefined** (`INV-CERT-001` §8). Five receipts on a corpus reversed by
  construction is a detection count.
- **`contained_attempt_voids=false` is not the product's setting** and this run does not make
  it one. One of the five certified cases depends on it.
- **Nothing was published anywhere.** The driver constructs a loopback client.
- **The README is not updated.** The owner's rule conditions that on the *capability-gain*
  line's Wilson lower bound exceeding 7.1%, and that line is zero. The README therefore still
  says 6.5% while this run measures 20.0%, and reconciling the two is owner decision (4).

## 7. Artifacts

| | |
|---|---|
| per-case results | [`evidence/2026-09-11-heldout-after-search.json`](evidence/2026-09-11-heldout-after-search.json) — 35 cases |
| the run | [`34530619773`](https://github.com/IcantFind-a-username/Attest/actions/runs/34530619773) |
| the baseline it is compared against | [`34478078680`](https://github.com/IcantFind-a-username/Attest/actions/runs/34478078680), [report](2026-09-10-heldout-remeasurement.md) |
| the shadow census taken beside it | [2026-09-11-value-note-shadow.md](2026-09-11-value-note-shadow.md) |
