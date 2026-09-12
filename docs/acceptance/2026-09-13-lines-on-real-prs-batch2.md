# Lines on real pull requests, batch 2 — twenty merged pull requests of five libraries the probe kept

**Work order PR 2 of the 2026-09-13 release window.** One paid run on the declared CI platform, the local review path — no GitHub client, nothing written to any repository — with `value_notes_visible` and `gate_notes_visible` on, `per_pr_budget_usd` $1.00, K=5, `linux-container-v1`, under the code of `release/batch2`: D-232 (`attest.intent.v5`, the frame rule), D-233 and D-234 in force for the first time on traffic the product had never seen. The population is the five of eight candidate libraries whose free evaluability probe passed ([protocol](../../benchmarks/studies/e05-external-v2/protocol.md)); four merged pull requests each. The ledgers came back, so every drawer observation is read to its reason.

- **run C (five libraries)** — run [`34660287636`](https://github.com/IcantFind-a-username/Attest/actions/runs/34660287636), study `e05-external-v2`: 20 units run, 6 with at least one line, 7 lines (value 5, red 2), 12 drawer observations, $2.2804.

**Wrong = 0 is the owner's to establish, not this report's.** Every line below has three empty columns.

## 1. Every line, verbatim — the owner fills the last three columns

| # | run | pull request | level | the line, as it would have been shown | what stands behind it | useful | true but useless | wrong |
|---|---|---|---|---|---|---|---|---|
| 1 | run C (five libraries) | `pallets/werkzeug#3268` | value | [yellow] src/werkzeug/testapp.py:19 — for importlib.import_module("werkzeug.testapp"), the merge base returned <module 'werkzeug.testapp' from '/attest/tree/src/werkzeug/testapp.py'> and head raises DeprecationWarning (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 1bd48ba8a4c6 | note 1bd48ba8a4c6 — `importlib.import_module("werkzeug.testapp")`; base value: <module 'werkzeug.testapp' from '/attest/tree/src/werkzeug/testapp.py'>; head exception: DeprecationWarning; 3/3 head, 3/3 base; drawer: intent: behavior change confirmed, intent unknown: head raises DeprecationWarning from a call or expression on a changed line; the rejected input is not in the base tree's tests, fixtures or documentation (行为变化已证实，意图未知) | | | |
| 2 | run C (five libraries) | `psf/requests#7505` | value | [yellow] src/requests/models.py:238 — for RequestEncodingMixin._encode_params(proxy), the merge base raised TypeError and head returns <test_repro.test_attest_probe.<locals>.ReadProxy object at 0x7fb1ea6cfcb0> (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 8505f39303a8 | note 8505f39303a8 — `RequestEncodingMixin._encode_params(proxy)`; base exception: TypeError; head value: <test_repro.test_attest_probe.<locals>.ReadProxy object at 0x7fb1ea6cfcb0>; 3/3 head, 3/3 base; drawer: intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base test asserts it and no docstring or documentation writes it down (返回值变化已证实，意图未知) | | | |
| 3 | run C (five libraries) | `python-jsonschema/jsonschema#1300` | value | [yellow] jsonschema/exceptions.py:511 — for exceptions.best_match([parent]), the merge base raised AttributeError and head raises IndexError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 48521e761d5c | note 48521e761d5c — `exceptions.best_match([parent])`; base exception: AttributeError; head exception: IndexError; 3/3 head, 3/3 base; drawer: intent: behavior change confirmed, intent unknown: head raises IndexError from a call or expression on a changed line; no rejected input could be identified from the test's literals (行为变化已证实，意图未知) | | | |
| 4 | run C (five libraries) | `pallets/werkzeug#3267` | value | [yellow] src/werkzeug/datastructures/cache_control.py:143 — for _CacheControl.from_header("max-age=60").to_header(), the merge base returned 'max-age=60' and head raises TypeError (3/3 and 3/3 runs each side); no base test, docstring or changelog pins either — note 031d036d5740 | note 031d036d5740 — `_CacheControl.from_header("max-age=60").to_header()`; base value: 'max-age=60'; head exception: TypeError; 3/3 head, 3/3 base; drawer: intent: behavior change confirmed, intent unknown: head raises TypeError from a call or expression on a changed line; the rejected input is not in the base tree's tests, fixtures or documentation (行为变化已证实，意图未知) | | | |
| 5 | run C (five libraries) | `pallets/werkzeug#3266` | red | [red] src/werkzeug/wrappers/response.py:132 — behavior change (intent to confirm): `autocorrect_location_header` class attribute default changed from `False` to `None`, but the code that checks it (`if self.autocorrect_location_header:`) still works only because `None` is falsy; however the type annotation `: None = None` incorrectly forbids assigning `True`/`False` per type checkers while the runtime code path relies on truthy/falsy semantics, and any subclass or user code setting `autocorrect_location_header = True` (a documented pattern, e.g. removed test `LocalResponse`) is now undocumented/untyped and will trigger a DeprecationWarning even though the feature is still functionally required for absolute redirect URLs. — receipt e212fca4e572 | receipt e212fca4e572, behavior_change | | | |
| 6 | run C (five libraries) | `pallets/werkzeug#3266` | red | [red] src/werkzeug/wrappers/response.py:488 — behavior change (intent to confirm): The deprecation warning is only emitted when `autocorrect_location_header` is truthy inside `get_wsgi_headers`, but since the class default is now `None` (falsy) instead of `False`, any code path or third-party subclass that never sets this attribute will never see the deprecation warning even though the docstring says the feature itself is deprecated for 3.3 removal, creating an inconsistent deprecation signal only surfacing for opt-in users. — receipt 8e5cf74f6155 | receipt 8e5cf74f6155, behavior_change | | | |
| 7 | run C (five libraries) | `python-jsonschema/jsonschema#1416` | value | [yellow] jsonschema/validators.py:1227 — for resolver.resolve_remote(uri), base and head mappings of 1 first differ at index 0 (3/3 and 3/3 runs): base 'foo': 'patched-module-level' → head 'foo': 'real'; nothing in the base tree pins it — note 0a62a2045088 | note 0a62a2045088 — `resolver.resolve_remote(uri)`; base value: {'foo': 'patched-module-level'}; head value: {'foo': 'real'}; 3/3 head, 3/3 base; drawer: intent: value change confirmed, intent unknown: the base tree does not specify the value this assertion pins about the symbol this change touched -- no base test asserts it and no docstring or documentation writes it down (返回值变化已证实，意图未知) | | | |

## 2. One row per pull request

### run C (five libraries)

| pull request | cand | elig | att | cert | drawers | red | value | gate | yellow (a) | units read | spend |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `hukkin/tomli-w#79` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0118 |
| `pallets/markupsafe#499` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0063 |
| `pallets/werkzeug#3268` | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 | 0 | 1 of 1 | $0.0694 |
| `psf/requests#7505` | 6 | 4 | 3 | 0 | 1 | 0 | 1 | 0 | 0 | 1 of 1 | $0.2350 |
| `python-jsonschema/jsonschema#1300` | 4 | 4 | 3 | 0 | 3 | 0 | 1 | 0 | 0 | 2 of 2 | $0.2585 |
| `hukkin/tomli-w#65` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0071 |
| `pallets/markupsafe#497` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0063 |
| `pallets/werkzeug#3267` | 16 | 10 | 3 | 0 | 3 | 0 | 1 | 0 | 0 | 1 of 8 (budget-limited) | $0.2348 |
| `psf/requests#7502` | 2 | 2 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.1564 |
| `python-jsonschema/jsonschema#1482` | 11 | 3 | 3 | 0 | 2 | 0 | 0 | 0 | 0 | 1 of 1 | $0.2127 |
| `hukkin/tomli-w#70` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0067 |
| `pallets/markupsafe#496` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 3 (budget-limited) | $0.0091 |
| `pallets/werkzeug#3266` | 6 | 6 | 6 | 3 | 0 | 2 | 0 | 0 | 0 | 2 of 2 | $0.5148 |
| `psf/requests#7497` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 3 of 3 | $0.0610 |
| `python-jsonschema/jsonschema#1444` | 1 | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0830 |
| `hukkin/tomli-w#69` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0112 |
| `pallets/markupsafe#469` | 1 | 1 | 1 | 0 | 1 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0501 |
| `pallets/werkzeug#3255` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0142 |
| `psf/requests#7498` | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 of 1 | $0.0142 |
| `python-jsonschema/jsonschema#1416` | 4 | 3 | 3 | 0 | 1 | 0 | 1 | 0 | 0 | 1 of 1 | $0.3179 |


## 3. Where every drawer observation went, read from the ledger

A drawer observation is a `verification` row of evidence class `behavior_change` whose outcome is not `reproduced`: the differential was real and the intent clause would not publish it. D-218 writes a value note only for the two drawers whose intent is *unreadable* (`value change confirmed, intent unknown` and `behavior change confirmed, intent unknown`); the drawer `intent stated in the change itself` means the author already said what they meant, and D-218 deliberately writes nothing for it. A written note is then shown only when it is not anchored inside `tests/`, is the first for its `(path, expression)`, and the contract admits the line (D-222).

| run | pull request | candidate | drawer | fate | detail |
|---|---|---|---|---|---|
| run C (five libraries) | `pallets/werkzeug#3268` | `e792cbfd8b` | behavior change confirmed, intent unknown | shown as a line |  |
| run C (five libraries) | `psf/requests#7505` | `1d7dd099fd` | value change confirmed, intent unknown | shown as a line |  |
| run C (five libraries) | `python-jsonschema/jsonschema#1300` | `9f9a94eff2` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run C (five libraries) | `python-jsonschema/jsonschema#1300` | `61c38381f7` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run C (five libraries) | `python-jsonschema/jsonschema#1300` | `a20fa46cdd` | behavior change confirmed, intent unknown | shown as a line |  |
| run C (five libraries) | `pallets/werkzeug#3267` | `48ffe16bbf` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run C (five libraries) | `pallets/werkzeug#3267` | `8fd3e6fe2c` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run C (five libraries) | `pallets/werkzeug#3267` | `5de9efe53c` | behavior change confirmed, intent unknown | shown as a line |  |
| run C (five libraries) | `python-jsonschema/jsonschema#1482` | `1e32db8ffb` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run C (five libraries) | `python-jsonschema/jsonschema#1482` | `4bebbe80ab` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run C (five libraries) | `pallets/markupsafe#469` | `b04c09f137` | intent stated in the change itself | note not written: drawer excluded by D-218 (intent stated / constant / unanchored) | intent stated in the change itself |
| run C (five libraries) | `python-jsonschema/jsonschema#1416` | `700d314598` | value change confirmed, intent unknown | shown as a line |  |

Fates, counted:

- run C (five libraries): **7** — note not written: drawer excluded by D-218 (intent stated / constant / unanchored)
- run C (five libraries): **5** — shown as a line

## 4. The run, in one column

| | run C (five libraries) |
|---|---|
| units run | 20 |
| candidates | 52 |
| eligible | 35 |
| reproductions attempted | 26 |
| certified | 3 |
| drawer observations | 12 |
| pull requests with a line | 6 |
| lines | 7 |
| spend | $2.2804 |

