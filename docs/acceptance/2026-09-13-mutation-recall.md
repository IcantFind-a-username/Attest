# mutations-v1-recall, 2026-09-13 — forty injected defects, and what red certified

**Work order PR 2 d of the 2026-09-13 window.** Runs [`34665205269`](https://github.com/IcantFind-a-username/Attest/actions/runs/34665205269) and [`34666234129`](https://github.com/IcantFind-a-username/Attest/actions/runs/34666234129) on the declared CI platform: forty forward cases of D-231's mutation corpus, five per library under seed 20260913, re-created on the runner from their recorded sites and reviewed through the local review path — no GitHub client, nothing written anywhere — at K=5, $1.00 per case, `linux-container-v1`, both yellow switches on, under the code of `release/batch2` (D-232, D-233, D-234). **The first recall figure on a corpus that is not reversed by construction.** Every case carries one injected defect; the denominator is forty whatever the cap or the runner did.

## 0. Two dispatches, and one case the driver cost

The first paid dispatch ran the frozen order's first **18** cases for $1.2906 and then died at the
19th: its checkout of the `itsdangerous` clone failed, the driver raised instead of skipping the
case by name, and the workflow step read as green because the driver's exit status was lost
behind `tee`. Both defects were fixed (the driver restores the tree and retries once, skips a case
that still cannot be checked out with git's own reason, and the step sets `pipefail`), the 18
recorded trials and lines were committed, and the second dispatch — from the branch, since the
workflow file already existed on `main` — continued the same frozen order from the 19th case
under the same $5.00 cap: **22 cases for $1.6336, 0 refused, 0 skipped**. No case was retried and
none re-drawn; the ledgers of both dispatches are committed under
[`evidence/2026-09-13-mutation-recall/`](evidence/2026-09-13-mutation-recall/).

**One case is a miss the driver caused, not the reviewer.** `itsdangerous-guard_raise-01--forward`,
the second case reviewed in the `itsdangerous` clone, was refused by the product as *working tree
is dirty; differential evidence requires immutable revisions* — the clone's tracked tree had been
left modified after the first case's review, the same state that broke the 19th case's checkout.
It is counted as *no receipt* and stays in the denominator; the number below is therefore a
lower bound on what a clean tree would have given by at most one case. What dirtied the tree is
recorded as open: the second dispatch's fresh clones saw no such refusal.

## 1. The number

| | |
|---|---|
| cases in the sample (the denominator) | **40** |
| cases run | **40** |
| **certified** (at least one accepted receipt) | **10** |
| point estimate | **25.0%** |
| Wilson 95% | **[14.2%, 40.2%]** |
| **sent to the drawer by D-232** (a rejection on a line the mutation wrote, or reached through one) | **0** |
| spend | $2.9242 |

Classes, counted:

- **16** — no receipt
- **14** — value class
- **10** — certified

## 2. By mutation class

| class | what was injected | cases | certified | D-232 drawer | value class | other |
|---|---|---|---|---|---|---|
| `guard_raise` | an `if …: raise …` validation deleted | 17 | 4 | 0 | 6 | 7 |
| `boundary` | a `<=`/`<` (or `>=`/`>`) boundary swapped | 13 | 1 | 0 | 7 | 5 |
| `none_guard` | an `if x is None: return …` guard deleted | 10 | 5 | 0 | 1 | 4 |

## 3. Every case

| case | library | class | site | verdict | cand | elig | att | lines | why | spend |
|---|---|---|---|---|---|---|---|---|---|---|
| `attrs-boundary-09--forward` | `attrs` | boundary | `src/attr/_compat.py:13` | **no receipt** | 1 | 1 | 1 | none | binding: the reproduction exercises none of the changed lines of src/attr/_compat.py | $0.0448 |
| `click-boundary-07--forward` | `click` | boundary | `src/click/_termui_impl.py:183` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0660 |
| `itsdangerous-boundary-07--forward` | `itsdangerous` | boundary | `src/itsdangerous/timed.py:141` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0567 |
| `jinja-boundary-09--forward` | `jinja` | boundary | `src/jinja2/debug.py:162` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0512 |
| `more-itertools-boundary-08--forward` | `more-itertools` | boundary | `more_itertools/more.py:453` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0837 |
| `packaging-boundary-08--forward` | `packaging` | boundary | `src/packaging/_musllinux.py:28` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0425 |
| `python-dotenv-boundary-06--forward` | `python-dotenv` | boundary | `src/dotenv/parser.py:164` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0539 |
| `urllib3-boundary-07--forward` | `urllib3` | boundary | `src/urllib3/_collections.py:114` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe deferred on base: missing or malformed JUnit evidence: Val | $0.0980 |
| `attrs-guard_raise-03--forward` | `attrs` | guard_raise | `src/attr/_make.py:423` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0824 |
| `click-boundary-10--forward` | `click` | boundary | `src/click/_termui_impl.py:339` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the failing assertion pins only a generic constant, which almost any tree asserts somewhere and which therefore  | $0.0739 |
| `itsdangerous-guard_raise-01--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/signer.py:146` | **no receipt** | 1 | 1 | 1 | none | working tree is dirty; differential evidence requires immutable revisions | $0.0240 |
| `jinja-boundary-12--forward` | `jinja` | boundary | `src/jinja2/environment.py:1637` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0709 |
| `more-itertools-boundary-10--forward` | `more-itertools` | boundary | `more_itertools/more.py:464` | **no receipt** | 1 | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0831 |
| `packaging-boundary-11--forward` | `packaging` | boundary | `src/packaging/_ranges.py:152` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0922 |
| `python-dotenv-boundary-08--forward` | `python-dotenv` | boundary | `src/dotenv/variables.py:85` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the failing assertion pins no value the base tree could have specified (返回值变化已证实，意图未知) | $0.0402 |
| `urllib3-guard_raise-03--forward` | `urllib3` | guard_raise | `src/urllib3/_request_methods.py:258` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe deferred on base: missing or malformed JUnit evidence: Val | $0.0925 |
| `attrs-none_guard-14--forward` | `attrs` | none_guard | `src/attr/_next_gen.py:424` | **no receipt** | 2 | 2 | 2 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe observation is not stable on base: the merge base returned | $0.1172 |
| `click-guard_raise-03--forward` | `click` | guard_raise | `src/click/_compat.py:400` | **no receipt** | 1 | 1 | 1 | impact 1 | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.1177 |
| `itsdangerous-guard_raise-04--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:134` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0825 |
| `jinja-guard_raise-01--forward` | `jinja` | guard_raise | `src/jinja2/bccache.py:84` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0519 |
| `more-itertools-guard_raise-04--forward` | `more-itertools` | guard_raise | `more_itertools/more.py:272` | **no receipt** | 1 | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0621 |
| `packaging-guard_raise-01--forward` | `packaging` | guard_raise | `src/packaging/_elffile.py:53` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0640 |
| `python-dotenv-guard_raise-01--forward` | `python-dotenv` | guard_raise | `src/dotenv/main.py:211` | **certified** | 3 | 3 | 3 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.1524 |
| `urllib3-guard_raise-04--forward` | `urllib3` | guard_raise | `src/urllib3/connection.py:269` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe deferred on base: missing or malformed JUnit evidence: Val | $0.0915 |
| `attrs-none_guard-15--forward` | `attrs` | none_guard | `src/attr/converters.py:37` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0367 |
| `click-guard_raise-05--forward` | `click` | guard_raise | `src/click/_compat.py:409` | **value class** | 2 | 2 | 2 | impact 1, value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.1765 |
| `itsdangerous-guard_raise-05--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:141` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0549 |
| `jinja-none_guard-13--forward` | `jinja` | none_guard | `src/jinja2/compiler.py:119` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0594 |
| `more-itertools-guard_raise-05--forward` | `more-itertools` | guard_raise | `more_itertools/more.py:297` | **no receipt** | 1 | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0666 |
| `packaging-guard_raise-06--forward` | `packaging` | guard_raise | `src/packaging/direct_url.py:182` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0547 |
| `python-dotenv-guard_raise-02--forward` | `python-dotenv` | guard_raise | `src/dotenv/main.py:323` | **value class** | 1 | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0520 |
| `urllib3-none_guard-15--forward` | `urllib3` | none_guard | `src/urllib3/_collections.py:486` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe deferred on base: missing or malformed JUnit evidence: Val | $0.0891 |
| `attrs-none_guard-17--forward` | `attrs` | none_guard | `src/attr/validators.py:206` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0541 |
| `click-none_guard-15--forward` | `click` | none_guard | `src/click/_termui_impl.py:484` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe observation is not stable on base: the merge base returned | $0.0981 |
| `itsdangerous-guard_raise-06--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:148` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0575 |
| `jinja-none_guard-14--forward` | `jinja` | none_guard | `src/jinja2/environment.py:100` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0765 |
| `more-itertools-none_guard-17--forward` | `more-itertools` | none_guard | `more_itertools/recipes.py:336` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0668 |
| `packaging-none_guard-13--forward` | `packaging` | none_guard | `src/packaging/_manylinux.py:178` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0603 |
| `python-dotenv-guard_raise-04--forward` | `python-dotenv` | guard_raise | `src/dotenv/parser.py:101` | **certified** | 1 | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0493 |
| `urllib3-none_guard-18--forward` | `urllib3` | none_guard | `src/urllib3/poolmanager.py:418` | **no receipt** | 1 | 1 | 1 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe deferred on base: missing or malformed JUnit evidence: Val | $0.0766 |

## 4. What is and is not claimed

- **Not natural traffic.** Three injection rules on lines the libraries' own tests reach (D-231); whether those tests catch each mutation was not measured.
- **Not comparable to the held-out figure** (5 of 25 on the reversed SWE-bench slice): a different population and a different direction. Two corpora, two denominators.
- **The D-232 count is the cost of the frame rule on this population**, stated beside the recall it leaves: a mutation that raises on the line it wrote is read as a behaviour change with unknown intent and shown as a yellow value line where the switch is on.
- **A case the cap refused or the runner could not build is a miss**, named in §3, and the denominator did not shrink.

