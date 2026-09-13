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

## 1a. The same forty under D-235

**Replayed on 2026-09-13 from the committed ledgers of both dispatches, under the probe-hygiene rules and the warning rule (D-235).** A case whose certifying probe would now be refused before execution -- its setup reached for the interpreter or replaced part of the tree -- loses its receipt: what the next probe would have found cannot be known offline and is not guessed. The table in §1 is what the run showed; this is what the same ledgers say now. The denominator is forty either way.

| | before | after D-235 |
|---|---|---|
| certified | **10** | **9** |
| point estimate | 25.0% | **22.5%** |
| Wilson 95% | [14.2%, 40.2%] | **[12.3%, 37.5%]** |

| case | before | after | why |
|---|---|---|---|
| `packaging-none_guard-13--forward` | certified | **no receipt: withdrawn under D-235** | probe setup assigns an attribute of the imported name _manylinux (_manylinux._glibc_version_string = lambda: None); replacing part of the tree before the call records the replacement, not the code (D-235) |

Over the run's **44 verification rows**: **2** probes would be refused before execution (attribute of an imported name 1, os.environ write 1), **0** differentials rest on a warning, **6** rows carry no test source to read the setup from (recordings that died before pytest reported) and are counted as unchanged. Classes after: 16 no receipt, 14 value class, 9 certified, 1 no receipt: withdrawn under D-235 ([evidence](evidence/2026-09-13-d235-replay.json)).

## 1b. The eight environment cases, re-run after D-236

**Run [`34699714069`](https://github.com/IcantFind-a-username/Attest/actions/runs/34699714069), `mutation-recall.yml` with `only` naming the 8 cases below, code from `main` after D-236 and D-237, $0.6082.** The denominator is forty; a case not named keeps its class from the original run and the D-235 replay. **6 of 8 cases now record a probe on the merge base** (none did before).

| | before | after the re-run |
|---|---|---|
| certified | **9** | **10** |
| point estimate | 22.5% | **25.0%** |
| Wilson 95% | [12.3%, 37.5%] | **[14.2%, 40.2%]** |

| case | before | after | recordings | verifications | lines | why now | spend |
|---|---|---|---|---|---|---|---|
| `urllib3-boundary-07--forward` | no receipt | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0814 |
| `itsdangerous-guard_raise-01--forward` | no receipt | **no receipt** | 0 | 2 | none | working tree is dirty; differential evidence requires immutable revisions | $0.0252 |
| `urllib3-guard_raise-03--forward` | no receipt | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0769 |
| `attrs-none_guard-14--forward` | no receipt | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0565 |
| `urllib3-guard_raise-04--forward` | no receipt | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0749 |
| `urllib3-none_guard-15--forward` | no receipt | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0766 |
| `click-none_guard-15--forward` | no receipt | **no receipt** | 0 | 1 | none | after 1 probe(s), probe generation failed: ProbeRefused: probe setup assigns an attribute of the imported name sys (sys.stdin = _fake_stdin); replacing part of  | $0.1533 |
| `urllib3-none_guard-18--forward` | no receipt | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the failing assertion pins only a generic constant, which almost any tree asserts somewhere and which therefore  | $0.0635 |

## 1c. The forty under the probe search v2 (D-238)

**Run [`34700357580`](https://github.com/IcantFind-a-username/Attest/actions/runs/34700357580), `mutation-recall.yml` over all 40 cases, code from `main` after D-236, D-237 and D-238, $2.7448.** The denominator is forty; a case not run keeps its latest class. **32 of 40 cases record a probe on the merge base** (34 did before). Cases newly certified: **1** (`jinja-boundary-09--forward`); cases that lost a receipt: **1** (`python-dotenv-guard_raise-04--forward`). Cases, never candidates: an extra receipt inside a case already certified counts for nothing here.

| | before | after the re-run |
|---|---|---|
| certified | **10** | **10** |
| point estimate | 25.0% | **25.0%** |
| Wilson 95% | [14.2%, 40.2%] | **[14.2%, 40.2%]** |

| case | before | after | recordings | verifications | lines | why now | spend |
|---|---|---|---|---|---|---|---|
| `attrs-boundary-09--forward` | no receipt | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 3 recorded nothing usable on the merge base -- probe did not execute src/attr/_compat.py on base, so it recorde | $0.0522 |
| `click-boundary-07--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0666 |
| `itsdangerous-boundary-07--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0571 |
| `jinja-boundary-09--forward` | value class | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0585 |
| `more-itertools-boundary-08--forward` | no receipt | **no receipt** | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0817 |
| `packaging-boundary-08--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0440 |
| `python-dotenv-boundary-06--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0543 |
| `urllib3-boundary-07--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0830 |
| `attrs-guard_raise-03--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0848 |
| `click-boundary-10--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0754 |
| `itsdangerous-guard_raise-01--forward` | no receipt | **no receipt** | 0 | 1 | none | working tree is dirty; differential evidence requires immutable revisions | $0.0254 |
| `jinja-boundary-12--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0726 |
| `more-itertools-boundary-10--forward` | no receipt | **no receipt** | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0777 |
| `packaging-boundary-11--forward` | no receipt | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0971 |
| `python-dotenv-boundary-08--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0392 |
| `urllib3-guard_raise-03--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0733 |
| `attrs-none_guard-14--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0739 |
| `click-guard_raise-03--forward` | no receipt | **no receipt** | 0 | 1 | impact 1 | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.1194 |
| `itsdangerous-guard_raise-04--forward` | no receipt | **no receipt** | 0 | 1 | none | after 1 probe(s), probe generation failed: BadRequestError: Error code: 400 - {'type': 'error', 'error': {'type': 'invalid_request_error', 'message': 'Invalid r | $0.0620 |
| `jinja-guard_raise-01--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0520 |
| `more-itertools-guard_raise-04--forward` | no receipt | **no receipt** | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0661 |
| `packaging-guard_raise-01--forward` | value class | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0864 |
| `python-dotenv-guard_raise-01--forward` | certified | **certified** | 2 | 2 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.1131 |
| `urllib3-guard_raise-04--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0767 |
| `attrs-none_guard-15--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0367 |
| `click-guard_raise-05--forward` | value class | **value class** | 1 | 1 | impact 1, value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.1075 |
| `itsdangerous-guard_raise-05--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0577 |
| `jinja-none_guard-13--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0629 |
| `more-itertools-guard_raise-05--forward` | no receipt | **no receipt** | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0688 |
| `packaging-guard_raise-06--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0546 |
| `python-dotenv-guard_raise-02--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0456 |
| `urllib3-none_guard-15--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0766 |
| `attrs-none_guard-17--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0507 |
| `click-none_guard-15--forward` | no receipt | **no receipt** | 0 | 1 | none | generation failed: ProbeRefused: probe setup writes os.environ (os.environ['PAGER'] = 'definitely_not_a_real_pager_xyz123'); the code under review must read the | $0.0940 |
| `itsdangerous-guard_raise-06--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0597 |
| `jinja-none_guard-14--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0716 |
| `more-itertools-none_guard-17--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0679 |
| `packaging-none_guard-13--forward` | no receipt: withdrawn under D-235 | **no receipt** | 0 | 1 | none | after 1 probe(s), probe generation failed: ProbeRefused: probe setup writes os.environ (os.environ.pop("CS_GNU_LIBC_VERSION", None)); the code under review must | $0.0835 |
| `python-dotenv-guard_raise-04--forward` | certified | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0506 |
| `urllib3-none_guard-18--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the failing assertion pins only a generic constant, which almost any tree asserts somewhere and which therefore  | $0.0641 |

## 1d. The forty under D-240 — aborted by the provider, not a measurement

**Run [`34709160655`](https://github.com/IcantFind-a-username/Attest/actions/runs/34709160655), `mutation-recall.yml` over all forty, code from `main` after D-240 (the moved-conditions block and `attest.intent.v5.1`), $0.9271.** After 14 cases the model provider began answering every call with `invalid_request_error: Your credit balance is too low to access the Anthropic API`; 130 discovery samples failed, 26 of 40 cases recorded *all provider samples failed or were malformed* and never reached a probe, and the run ended green because a refused sample is a recorded outcome. **This is not a measurement of D-240** and its two receipts are not counted anywhere; the trials, lines and ledgers are kept under [`evidence/2026-09-13-mutation-recall/search-v3-aborted/`](evidence/2026-09-13-mutation-recall/search-v3-aborted/) as the record of what was bought. The re-run waits for the account's credit, into a new trials file.

Two things the aborted run did establish, both free. The 14 cases that ran before the balance gave out show the D-240 code path working end to end (7 value-class drawers, 2 receipts, no crash). And D-239's `workspace_status` row named the dirty file of `itsdangerous-guard_raise-01` on its first paid run: ` M src/itsdangerous/signer.py`, the anchored file itself — the project sets `[tool.ruff] fix = true`, the injected mutation left an import unused, and tier-0's `ruff check` rewrote the file before the verification looked at it. Fixed as D-242 (`--no-fix`); the case is a miss on every run so far and needs the re-run to count.

## 1e. The forty under D-240, re-run after the credit top-up

**Run [`34711985142`](https://github.com/IcantFind-a-username/Attest/actions/runs/34711985142), `mutation-recall.yml` over all 40 cases, code from `main` after D-240, D-241 and D-242, $2.7521.** The denominator is forty; a case not run keeps its latest class. **31 of 40 cases record a probe on the merge base** (32 did before). Cases newly certified: **4** (`packaging-guard_raise-01--forward`, `python-dotenv-guard_raise-04--forward`, `urllib3-guard_raise-04--forward`, `urllib3-none_guard-15--forward`); cases that lost a receipt: **2** (`jinja-boundary-09--forward`, `more-itertools-none_guard-17--forward`). Cases, never candidates: an extra receipt inside a case already certified counts for nothing here.

| | before | after the re-run |
|---|---|---|
| certified | **10** | **12** |
| point estimate | 25.0% | **30.0%** |
| Wilson 95% | [14.2%, 40.2%] | **[18.1%, 45.4%]** |

| case | before | after | recordings | verifications | lines | why now | spend |
|---|---|---|---|---|---|---|---|
| `attrs-boundary-09--forward` | no receipt | **no receipt** | 1 | 1 | none | binding: the reproduction exercises none of the changed lines of src/attr/_compat.py | $0.0562 |
| `click-boundary-07--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0665 |
| `itsdangerous-boundary-07--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0597 |
| `jinja-boundary-09--forward` | certified | **no reproduction attempted** | 0 | 0 | none |  | $0.0083 |
| `more-itertools-boundary-08--forward` | no receipt | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0883 |
| `packaging-boundary-08--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0447 |
| `python-dotenv-boundary-06--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0569 |
| `urllib3-boundary-07--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0836 |
| `attrs-guard_raise-03--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0849 |
| `click-boundary-10--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0787 |
| `itsdangerous-guard_raise-01--forward` | no receipt | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0568 |
| `jinja-boundary-12--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0722 |
| `more-itertools-boundary-10--forward` | no receipt | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 1 reached the changed lines and observed no difference; 2 could not be executed on the head revision -- on the  | $0.0901 |
| `packaging-boundary-11--forward` | no receipt | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0947 |
| `python-dotenv-boundary-08--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0396 |
| `urllib3-guard_raise-03--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0788 |
| `attrs-none_guard-14--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0745 |
| `click-guard_raise-03--forward` | no receipt | **no receipt** | 0 | 1 | impact 1 | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.1208 |
| `itsdangerous-guard_raise-04--forward` | no receipt | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 3 reached the changed lines and observed no difference | $0.0882 |
| `jinja-guard_raise-01--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0525 |
| `more-itertools-guard_raise-04--forward` | no receipt | **no receipt** | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0619 |
| `packaging-guard_raise-01--forward` | no receipt | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0687 |
| `python-dotenv-guard_raise-01--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0700 |
| `urllib3-guard_raise-04--forward` | value class | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0784 |
| `attrs-none_guard-15--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0361 |
| `click-guard_raise-05--forward` | value class | **value class** | 1 | 1 | impact 1, value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0970 |
| `itsdangerous-guard_raise-05--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0575 |
| `jinja-none_guard-13--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0598 |
| `more-itertools-guard_raise-05--forward` | no receipt | **no receipt** | 1 | 1 | none | intent: value change confirmed, no symbol to specify: this change touches no function or class of the anchored file, so no test, docstring or document can speci | $0.0701 |
| `packaging-guard_raise-06--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0561 |
| `python-dotenv-guard_raise-02--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base tes | $0.0462 |
| `urllib3-none_guard-15--forward` | value class | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0778 |
| `attrs-none_guard-17--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0491 |
| `click-none_guard-15--forward` | no receipt | **no receipt** | 0 | 1 | none | generation failed: ProbeRefused: probe setup assigns an attribute of the imported name tui (tui.isatty = lambda stream: True); replacing part of the tree before | $0.0932 |
| `itsdangerous-guard_raise-06--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0594 |
| `jinja-none_guard-14--forward` | certified | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0702 |
| `more-itertools-none_guard-17--forward` | certified | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 2 reached the changed lines and observed no difference; 1 recorded nothing usable on the merge base -- probe ob | $0.0853 |
| `packaging-none_guard-13--forward` | no receipt | **no receipt** | 0 | 1 | none | 3 probes tried and none produced a differential: 2 did not reach the changed lines; 1 reached the changed lines and observed no difference | $0.1053 |
| `python-dotenv-guard_raise-04--forward` | value class | **certified** | 1 | 1 | red 1 | head FAIL 3/3, base PASS 3/3 | $0.0493 |
| `urllib3-none_guard-18--forward` | value class | **value class** | 1 | 1 | value 1 | intent: value change confirmed, intent unknown: the failing assertion pins only a generic constant, which almost any tree asserts somewhere and which therefore  | $0.0649 |

**Two dispatches, one trials file.** The first dispatch (run `34711985142`, cap $3.50) ran 37 cases for $2.5326 and the cap refused the last three by name -- `packaging-none_guard-13`, `python-dotenv-guard_raise-04`, `urllib3-none_guard-18` -- because a case starts only if its $1.00 maximum still fits; the follow-up run [`34712819526`](https://github.com/IcantFind-a-username/Attest/actions/runs/34712819526) ran exactly those three with `only` for $0.2195. The table above merges the two: 40 of 40 run, no case re-drawn or retried.

**What moved it.** Of the four cases newly certified, three are D-240 (b): the replay pinned an exception type name and a base test expects it from the touched symbol -- `packaging-guard_raise-01` (`ELFInvalid`, `tests/test_elffile.py`), `urllib3-guard_raise-04` (`ValueError`, `test/with_dummyserver/test_connection.py`), `urllib3-none_guard-15` (`TypeError`, `test/test_collections.py`); the two urllib3 cases had never recorded a probe before D-236, so the offline census of 2026-09-13 (at most 2 of 40) could not see them. `python-dotenv-guard_raise-04` came back under the prose rule (`ValueError` in `CHANGELOG.md`), the same way it had certified on the original run. Of the two lost, `jinja-boundary-09` proposed no eligible candidate this time and `more-itertools-none_guard-17`'s three probes saw no difference -- discovery and search variance, both. The boundary class is still **1 of 13**: the moved-conditions block (D-240 a) named the boundary and the probes did not certify on it; the value class holds 16 of 40.

## 1f. Did the probes try the boundary? Read from the D-240 run's ledgers, free

The owner's question after §1e: the boundary class is still 1 of 13 after the moved-conditions
block named the boundary to every probe -- did the model *try* the boundary value? A boundary
swap (`>=` to `>`) changes the two revisions' behaviour on exactly one input, the one that sits on
the boundary; so a probe whose head observation differs from its base observation has hit it, and a
probe that "reached the changed lines and observed no difference" has not. Read from the 13
boundary cases' `probe_observation` and `verification` rows of run 34711985142:

| | cases |
|---|---|
| a probe made the two revisions differ (the boundary was hit) | **9 of 13** |
| of those, certified | 1 (`itsdangerous-boundary-07`) |
| of those, the value class -- hit, and the base tree pins no value for it | **7** |
| of those, unbound -- the probe compared a module-level constant computed at import | 1 (`attrs-boundary-09`) |
| no probe made the revisions differ | 3 (`more-itertools-boundary-08`, `more-itertools-boundary-10`, `packaging-boundary-11`) |
| no eligible candidate proposed | 1 (`jinja-boundary-09`) |

**The search is not the wall on this class either.** Nine of thirteen probes found the input on
which the mutation changes behaviour; seven of the nine were then drawered because the value they
observed -- `pb.format_eta()`, `_parse_musl_version(output)`, `list(parse_stream(stream))`,
`(len(c), sorted(c.keys()))`, a chunk list, a variables list -- is one no base test asserts about
the touched symbol. That is the same rule that holds 16 of 40 overall (D-127, D-174, D-240 b), and
D-240 (b) cannot reach it: a boundary swap does not raise, so no `pytest.raises` specifies its
value. The three misses are the search's; the attrs case is a binding question (the probe read
`PY_3_13_PLUS`, a constant evaluated at import, so the changed line ran at import and not under the
probe). No model was called for this table.

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

