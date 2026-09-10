# The held-out re-measurement: the derived probe did not move recall

**Owner instruction of 2026-09-10**, grading [D-206](../../DECISIONS.md) on the population
[D-208](../../DECISIONS.md) built the harness for, and recorded as D-211. Run
[`34478078680`](https://github.com/IcantFind-a-username/Attest/actions/runs/34478078680) at
`a1f74dc`, `ubuntu-latest`, 2h57m56s.

**The one sentence.** All **39** cases ran for the first time, and the crash-class recall is
**2 of 31 — 6.5%, Wilson 95% [1.8%, 20.7%]**, against the 2026-09-12 baseline of 2 of 28 — 7.1%,
Wilson 95% [2.0%, 22.6%]. The numerator did not move, the denominator grew by three, and
**`source: "derived"` appears zero times in the whole run**: D-206's mechanism was reached on 2 of
25 candidates that got as far as a probe observation, produced 5 derived probes, and every one of
them was screened out. **The lower bound (1.8%) is below the baseline point estimate (7.1%), so
this is not a release.**

## 1. Two denominators, and they are not the same number

`heldout_compare.py` is denominated in **cases run**; `heldout_v2.py table` is denominated in the
**crash class**, which is what `G-RECALL-002` is stated over. Both are reported because the first
is the only one under which the two runs cover different numbers of cases.

| denominator | 2026-09-12 baseline | **this run** |
|---|---|---|
| **cases run** (`heldout_compare.py`) | 2 of 35 — 5.7%, Wilson 95% [1.6%, 18.6%] | **2 of 39 — 5.1%, Wilson 95% [1.4%, 16.9%]** |
| **crash class** (`heldout_v2.py table`, `G-RECALL-002`) | 2 of 28 — 7.1%, Wilson 95% [2.0%, 22.6%] | **2 of 31 — 6.5%, Wilson 95% [1.8%, 20.7%]** |
| value class, excluded (D-158) | 7 | **8** |
| refused before any evidence | 0 | **0** |
| spend | $4.138447 | **$5.044872** |

The crash denominator grew from 28 to 31 because the baseline's $5.00 cap stopped it before four
cases and this run's $6.50 cap did not: `sympy__sympy-24443`, `pydata__xarray-7393`,
`sympy__sympy-24539` and `sympy__sympy-24562` are bought here for the first time. Three landed in
the crash class and one in the value class; **none certified.**

The population is the *same 39 instances*, restored from the 2026-09-12 probe evidence rather than
re-screened (D-208), so every difference below is the product's and not the corpus's. The runner's
own `table` output agrees with the figures recomputed here.

## 2. The class migration, case by case

**5 of the 35 cases run in both** changed class. The other 30 did not.

| case | 2026-09-12 | this run | |
|---|---|---|---|
| `pallets__flask-5014` | probe recorded nothing | **surfaced** | **NEW RECEIPT** (`120827ef00`) |
| `pytest-dev__pytest-10356` | **surfaced** | intent clause | **LOST** |
| `pylint-dev__pylint-6903` | intent clause | unfaithful generated test | — |
| `pytest-dev__pytest-10051` | unfaithful generated test | unfaithful generated test | — |
| `sympy__sympy-23413` | intent clause | unfaithful generated test | — |

**The two receipts are not the same two receipts.** `psf__requests-5414` certified in both runs —
though under a different candidate id (`520c57974d` then, `edbff84c95` now). The second receipt
moved: `pytest-dev__pytest-10356` had it and lost it, `pallets__flask-5014` did not have it and
gained it. At the shipped `K=5` the numerator is **2 in both runs and stable in only one of its
two members**. That is the same instability the 2026-09-10 factory measurement recorded (D-185's
window: three receipts before and after, but not the same three), now seen on the held-out corpus.
**One receipt of two moving between runs of an identical population is not evidence that D-206
gained a case**; a single flip is inside the run-to-run variance this corpus has already shown.

## 3. Where the receipts are lost — before and after

| category | 2026-09-12, 56 attempts | **this run, 67 attempts** | **this run, the 35 shared cases only, 60 attempts** |
|---|---|---|---|
| **the generated probe does not collect** | **17** | **21** | **20** |
| **the process guard** (child process + thread) | **17** (12 + 5) | **18** (13 + 5) | **18** (13 + 5) |
| **the intent clause** | **13** | **14** | **12** |
| unfaithful generated test | 3 | 8 | 4 |
| verification deadline exceeded after 900s | 0 | 2 | 2 |
| probe observation not stable on base | 1 | 1 | 1 |
| binding / changed lines not executed | 1 | 1 | 1 |
| probe recorded no observation on base | 2 | 0 | 0 |
| **reproduced** | **2** | **2** | **2** |

**The three categories the instruction asks about did not fall.** On the like-for-like column —
the 35 cases both runs bought — the probe-does-not-collect loss went **17 → 20**, the process guard
**17 → 18**, and the intent clause **13 → 12**. None of these movements is large against its
denominator, and the attempt counts themselves differ (56 vs 60) because the number of candidates
proposed is not deterministic. **No category was closed.**

`probe recorded no observation on base` fell 2 → 0, and one of those two cases
(`pallets__flask-5014`) is the new receipt. That is the only category that moved in D-206's
declared direction, and it is 2 attempts wide.

## 4. What D-206 actually did, measured from the ledger

The `attest.probe-observation.v2` row D-206 added carries `source`, `origin` and `screened`, so
the mechanism can be counted rather than argued.

| | |
|---|---|
| `probe_observation` rows, all `attest.probe-observation.v2` | **25** |
| rows with `source: "model"` | **25** |
| rows with `source: "derived"` | **0** |
| candidates for which any derived probe existed | **2** of 25 (`screened` = 1 and 4) |
| derived probes produced in the whole run | **5** |
| derived probes chosen | **0** — all 5 screened out |
| verification reasons naming a derived probe | **0** |

`derived_probes` defaults to `True` (`src/attest/review/config.py:69`) and was on. The mechanism
was therefore not disabled; it **found nothing to derive on 23 of 25 candidates**, and on the 2
where it did derive, every derived call produced an identical observation on head — which is
exactly the screening rule D-206 wrote, working as specified and buying nothing.

D-206 said in its own text that it claimed no recall number and that whether it moves 2 of 28 is a
paid measurement nobody had run. **It has now been run, and the answer is that it does not.**

**What this run cannot say.** The artifact carries each case's `ledger.jsonl` but not its
worktree, so *why* derivation returned nothing on those 23 candidates — an anchor that is not a
module-level function, no test calling it with literal arguments, or an unreadable tree — is not
recoverable from this evidence. It is free to measure offline and is the first item in §7.

## 5. Cost, and the cap

| | |
|---|---|
| reserved (DEVSPEND.md, owner authorisation 2026-09-10) | **$6.50** |
| **actual** | **$5.044872** |
| released | $1.455128 |
| cases run | **39 of 39** |
| **did the cap bind?** | **No.** No case was refused; the run log carries no `cumulative cap` line and every planned case was bought |
| largest single review | $0.4130 (`pydata__xarray-6992`, 10 candidates) |
| mean per case | $0.1294 |
| model | `claude-sonnet-5`, `--k 5 --budget 1.00` (factory) |
| GitHub Actions minutes | $0.00 — the repository is public |

The baseline's $5.00 cap **did** bind and left 4 cases unbought; this one did not. The complete
denominator is the one thing the extra $0.91 bought.

## 6. What this run does not measure

- **No control arm.** Every one of the 39 rows has `control: null`. This run is recall-only and
  says **nothing** about false publications; the standing control evidence (68 independent nulls +
  40 held-out controls, 0 false publications, at `K=4`) is untouched and unextended by it.
- **Precision is undefined** (`INV-CERT-001` §8). Two receipts on a corpus reversed by
  construction is a detection count, not a precision figure.
- **The value class is not a value-class recall figure** (D-158). Its 8 cases are excluded from
  the denominator, not scored.
- **Nothing was published anywhere.** The driver constructs a loopback client, so no comment,
  review or status reached any repository.

## 7. The gap, and three concrete next steps

`G-RECALL-002` asks for ≥70%. The interval's **upper** bound is 20.7%. The gate fails by a margin
no sample size on this population will close, and D-206 did not narrow it.

The instruction's expectation was 14–18% (4–5 of 28) from the derived probe alone. The measured
result is **6.5% (2 of 31)**, and the mechanism was chosen **0 times** — so the shortfall is not a
weaker-than-hoped effect, it is **no effect**, and the reason is upstream of the screening rule:
derivation produced a candidate probe for only 2 of 25 candidates.

Three next steps, in the order the evidence supports:

1. **Measure why derivation returns nothing — free, offline, no model, no execution.** Rebuild the
   39 case trees (the `build` stage is free and took 15s on the runner) and run `probe_sources` +
   `derive_probes` against each candidate anchor recorded in the ledgers, counting the refusal
   reason: anchor not inside a module-level function, no test call resolving to the changed
   definition through `attest.review.binding`, or no call whose arguments are all literals. D-206
   restricted itself to module-level functions because *"a method needs a receiver and a receiver
   is an object the test built"*; on a corpus of `sympy`, `xarray` and `sphinx` that restriction
   may be excluding most of the population, and this measurement decides it before any code moves.

   **Done, 2026-09-11 (D-212), and it decided against the route.** Fully relaxed, a derived
   probe exists for **5 of 39 cases**; only the method relaxation contributes. **25 of 39 cases
   have no test call site at all** for what their diff changed. The rule is not broken — it
   scores 22 of 200 (11%) on this repository — the supply is not there.
   [Report](2026-09-10-probe-reach.md).
2. **The intent clause's evidence source** — the instruction's own preferred direction, and the
   category is 14 of 67 attempts here (12 of 60 on the shared cases), 8 of which are the value
   class D-158 already excludes. The live question is what may count as the base tree stating an
   intended value; today it is base tests, fixtures and documentation (D-102). Widening it is an
   evidence-class change and therefore an **owner decision under §16** — it must be a preregistered
   discriminator with its own control arm, not a threshold nudge.
3. **The probe-collection loss is still the largest single category and it grew** — 17 → 20 on the
   like-for-like column, 21 of 67 overall. D-206 addressed it by not asking a model at all; that
   route reached 2 candidates. The other route is the model probe's own import shape, which is
   D-114's territory and has never been measured as a distinct failure population.

**Not recommended here, and named so it is not done quietly:** the 18 process-guard losses.
D-207 measured that the base-side split recovers nothing, and relaxing the guard generally is the
isolation profile — an owner decision under §16.

## 8. Verdict

**Do not release v0.2.0.** The condition was a Wilson lower bound above 7.1%; the measured lower
bound is **1.8%**. Recall is statistically indistinguishable from the baseline and its point
estimate is slightly lower on a larger denominator. `G-RECALL-002` stays at **2 of 31 — 6.5%,
Wilson 95% [1.8%, 20.7%]**, superseding 2 of 28 as the current figure over the same population,
now complete.

**README is not updated for a recall improvement**, because there is none; the figure it carries
is restated in §1 of this report with both denominators and this date.

## 9. Artifacts

| | |
|---|---|
| per-case run summary | [`evidence/2026-09-10-heldout-supported-run.json`](evidence/2026-09-10-heldout-supported-run.json) — 39 rows |
| the population, unchanged | [`evidence/2026-09-12-heldout-supported-probe.json`](evidence/2026-09-12-heldout-supported-probe.json) |
| the baseline this is compared to | [`evidence/2026-09-12-heldout-supported-run.json`](evidence/2026-09-12-heldout-supported-run.json), [report](2026-09-12-heldout-supported.md) |
| run | [`34478078680`](https://github.com/IcantFind-a-username/Attest/actions/runs/34478078680), code `a1f74dc` |

The corpus itself, its `cases/*/repo/.attest/ledger.jsonl` and the run logs are the run's
artifact, retained 30 days; they are not committed (`AGENTS.md` §7).

## 10. Per case

| case | class | cand | attempts | certified | first failure | spend |
|---|---|---|---|---|---|---|
| `mwaskom__seaborn-3069` | crash class, no receipt | 3 | 3 | 0 | other x3 | $0.2666 |
| `pallets__flask-5014` | crash class, certified | 1 | 1 | 1 | — | $0.0652 |
| `psf__requests-5414` | crash class, certified | 1 | 1 | 1 | — | $0.0707 |
| `pydata__xarray-4687` | crash class, no receipt | 2 | 2 | 0 | collection failure x2 | $0.1937 |
| `pylint-dev__pylint-4661` | crash class, no receipt | 1 | 1 | 0 | collection failure x1 | $0.0535 |
| `pytest-dev__pytest-10051` | crash class, no receipt | 1 | 1 | 0 | unfaithful test x1 | $0.0707 |
| `sphinx-doc__sphinx-10435` | crash class, no receipt | 3 | 3 | 0 | other x3 | $0.2579 |
| `sympy__sympy-22914` | crash class, no receipt | 1 | 1 | 0 | changed lines not executed x1 | $0.0472 |
| `mwaskom__seaborn-3187` | crash class, no receipt | 2 | 2 | 0 | other x2 | $0.1343 |
| `psf__requests-6028` | crash class, no receipt | 1 | 1 | 0 | unfaithful test x1 | $0.0559 |
| `pydata__xarray-6461` | crash class, no receipt | 2 | 2 | 0 | collection failure x2 | $0.2014 |
| `pylint-dev__pylint-6528` | crash class, no receipt | 1 | 1 | 0 | other x1 | $0.0954 |
| `pytest-dev__pytest-10356` | crash class, no receipt | 2 | 2 | 0 | other x2 | $0.1588 |
| `sphinx-doc__sphinx-10449` | crash class, no receipt | 2 | 2 | 0 | other x2 | $0.1718 |
| `sympy__sympy-23262` | value class | 4 | 4 | 0 | behavior change, intent unknown x2, timeout x2 | $0.1106 |
| `pydata__xarray-6599` | crash class, no receipt | 1 | 1 | 0 | collection failure x1 | $0.0886 |
| `pylint-dev__pylint-6903` | crash class, no receipt | 1 | 1 | 0 | unfaithful test x1 | $0.0662 |
| `sphinx-doc__sphinx-10466` | value class | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0621 |
| `sympy__sympy-23413` | crash class, no receipt | 1 | 1 | 0 | unfaithful test x1 | $0.0899 |
| `pydata__xarray-6721` | crash class, no receipt | 1 | 1 | 0 | collection failure x1 | $0.1073 |
| `pylint-dev__pylint-7080` | value class | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0525 |
| `sphinx-doc__sphinx-10614` | crash class, no receipt | 2 | 2 | 0 | other x2 | $0.2445 |
| `sympy__sympy-23534` | value class | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0733 |
| `pydata__xarray-6744` | crash class, no receipt | 5 | 3 | 0 | collection failure x3 | $0.1742 |
| `pylint-dev__pylint-7277` | value class | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0701 |
| `sphinx-doc__sphinx-11445` | crash class, no receipt | 3 | 3 | 0 | other x3 | $0.1514 |
| `sympy__sympy-23824` | value class | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0992 |
| `pydata__xarray-6938` | crash class, no receipt | 5 | 4 | 0 | collection failure x4 | $0.3229 |
| `pylint-dev__pylint-8898` | value class | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0718 |
| `sphinx-doc__sphinx-11510` | crash class, no receipt | 1 | 1 | 0 | other x1 | $0.0937 |
| `sympy__sympy-23950` | crash class, no receipt | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0392 |
| `pydata__xarray-6992` | crash class, no receipt | 10 | 4 | 0 | collection failure x4 | $0.4130 |
| `sphinx-doc__sphinx-9711` | crash class, no receipt | 2 | 2 | 0 | other x2 | $0.0946 |
| `sympy__sympy-24213` | crash class, no receipt | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0758 |
| `pydata__xarray-7229` | crash class, no receipt | 2 | 2 | 0 | collection failure x2 | $0.2453 |
| `sympy__sympy-24443` **(new)** | crash class, no receipt | 8 | 3 | 0 | other x1, unfaithful test x2 | $0.1749 |
| `pydata__xarray-7393` **(new)** | crash class, no receipt | 1 | 1 | 0 | collection failure x1 | $0.0777 |
| `sympy__sympy-24539` **(new)** | value class | 1 | 1 | 0 | behavior change, intent unknown x1 | $0.0695 |
| `sympy__sympy-24562` **(new)** | crash class, no receipt | 2 | 2 | 0 | unfaithful test x2 | $0.1334 |
