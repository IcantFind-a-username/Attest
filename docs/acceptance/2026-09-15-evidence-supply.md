# The evidence-supply audit over the forty, 2026-09-15 — what the base trees hold about each mutated symbol, and what the libraries' own tests say

**Phase 0 of [the contract-evidence plan](../design/contract-evidence-plan.md), on the owner's "开始"
of 2026-09-15 (decision A of its §8).** Everything here is free: `ast` and `git` over the forty case
trees rebuilt under `.attest/corpora/mutations-v1-recall/` from clones of the eight libraries at the
tips `sample.jsonl` records, arm C's ledgers
([`evidence/2026-09-14-probe-arms/arm-C/`](evidence/2026-09-14-probe-arms/arm-C/)) read as they
are, and each library's own test suite run in its own venv on the development host (macOS, Python
3.12.2, `pip install -e .[tests]` plus the PEP 735 groups and the extras `scripts/corpus/mutate.py`
names). **No model call, no container, $0.00.** Code: `main@a66324b` plus the two fixes of this
branch, D-249 (`c66e14b`) and D-250 (`777da08`); the instrument is
`scripts/corpus/evidence_supply.py`, added by the commit that adds this report. The facts are in
[`evidence/2026-09-15-evidence-supply/`](evidence/2026-09-15-evidence-supply/) (`static.json`,
`dynamic.json`, `summary.json`, `table.md`). **Status: measurement; no gate applies** —
`G-RECALL-002`'s population is the held-out corpus, not this one, and nothing here is a recall
figure.

Reproduce:

```bash
.venv/bin/python scripts/corpus/mutation_recall.py build      # the forty from the clones
.venv/bin/python scripts/corpus/evidence_supply.py static
.venv/bin/python scripts/corpus/evidence_supply.py dynamic --timeout 600
.venv/bin/python scripts/corpus/evidence_supply.py report
```

## 0. The three numbers the plan's exit condition asked for

The plan (§5, Phase 0) said: if the cases whose tree holds an admissible specification the
product cannot read today, plus D-249's recoveries, number fewer than eight, contracts cannot lift
arm C's 13 of 40 to 20 and Phase 2 changes shape. Read off the 27 cases arm C did not certify:

| | cases | which |
|---|---:|---|
| **(b) the tree holds an admissible contract the chain cannot use today** | **9** | 3 blocked by the symbol bound (D-249: `more-itertools-boundary-08`, `-guard_raise-04`, `-guard_raise-05`); 3 whose expected side is an object the literal matcher cannot see (`packaging-boundary-08`, `python-dotenv-boundary-08`, `urllib3-none_guard-18`); 3 whose exception is expected by a base test that names only the public caller or a helper, never the touched symbol (`attrs-guard_raise-03`, `itsdangerous-guard_raise-01`, `packaging-guard_raise-06`) |
| **the tree's own tests hold a discriminating input the search never tried** | **5** | `itsdangerous-guard_raise-04`, `click-none_guard-15`, `more-itertools-none_guard-17`, `packaging-none_guard-13` (three probes, no differential) and `jinja-none_guard-13` (a differential on an unspecifiable value while 206 of the library's tests fail on head) |
| **nothing in the tests that name the symbol, nor in a docstring or changelog, specifies the outcome** | **13** | 7 where no base test names a touched symbol at all, 4 where the naming tests pass on the mutant, 2 the audit could not decide (click's naming file is a typing fixture that does not collect) |

**9 ≥ 8: the plan's Phase 1 keeps its shape.** What that does and does not mean is §5.

And the column D-231 said was missing — **whether a library's own tests catch each planted
defect**, measured here on the test files that name a touched symbol, head against base:

| own tests (files naming a touched symbol) | of 40 | of the 13 certified | of the 27 not certified |
|---|---:|---:|---:|
| catch the mutant (fail on head, pass on base) | **21** | 7 | **14** |
| pass on the mutant | 7 | 3 | 4 |
| no test names a touched symbol | 9 | 2 | 7 |
| inconclusive (the naming file fails to collect on both revisions) | 3 | 1 | 2 |

So the reviewer certified **5 defects the tests naming the symbol do not catch**
(`itsdangerous-boundary-07`, `jinja-boundary-09`, `python-dotenv-guard_raise-01`,
`jinja-none_guard-14`, `python-dotenv-guard_raise-04`) — the "new diagnostic capability" column
the review asked to keep apart — and **missed 14 that the library's own tests would have caught**.
The full suites were not run (only the files naming a touched symbol), so *catch* is a lower bound
and *pass* an upper bound on the library's own detection.

### 0b. The three lists aligned, and why "13 − 7" is not "5"

*Added 2026-09-15 on the owner's instruction, after the own-tests pass was re-run at node level.*

| list | n | cases |
|---|---:|---|
| certified by arm C | 13 | `attrs-none_guard-14`, `attrs-none_guard-15`, `attrs-none_guard-17`, `itsdangerous-boundary-07`, `itsdangerous-guard_raise-05`, `itsdangerous-guard_raise-06`, `jinja-boundary-09`, `jinja-none_guard-14`, `packaging-guard_raise-01`, `python-dotenv-guard_raise-01`, `python-dotenv-guard_raise-04`, `urllib3-guard_raise-04`, `urllib3-none_guard-15` |
| caught by the library's own tests naming a touched symbol | 21 | the 14 misses named in §0 and §3, plus the 7 below |
| **intersection** | **7** | `packaging-guard_raise-01`, `urllib3-guard_raise-04`, `attrs-none_guard-15`, `itsdangerous-guard_raise-05`, `urllib3-none_guard-15`, `attrs-none_guard-17`, `itsdangerous-guard_raise-06` |
| certified, not caught: 13 − 7 | **6** | own tests **pass** on the mutant: `itsdangerous-boundary-07`, `jinja-boundary-09`, `python-dotenv-guard_raise-01` · **no test names** a touched symbol: `jinja-none_guard-14`, `python-dotenv-guard_raise-04` · **inconclusive**: `attrs-none_guard-14` (the only naming file is `bench/test_benchmarks.py`, which fails to collect on both revisions) |
| caught, not certified: 21 − 7 | **14** | the misses of §0's second table |

**"13 − 7 = 6" counts every certified case the naming tests did not catch; "5" counted only
those where the own-tests column gave a reading.** The sixth, `attrs-none_guard-14`, is neither
caught nor known to pass: its naming file does not collect, so the column says nothing about it.
The honest sentence is *5 certified defects the naming tests demonstrably do not catch, and a
sixth the column cannot read*.

**Node-level confirmation.** The own-tests pass was re-run so that a *detecting* node is one and
the same test id that **passed on base and failed on head** -- not merely absent or skipped on
base -- under the same venv, interpreter (CPython 3.12.2 for all eight libraries), working
directory and command on both revisions. `dynamic.json` carries, per case, every detecting node
with its base and head status (`detecting_nodes`), the head failures it excluded because base
did not pass them (`excluded_nodes`: dummy-server proxy tests, a typing fixture, a benchmark
module -- environmental on both sides), and the environment record. Under this stricter
reading the 21 stand: no case's detecting set changed.

## 1. D-249 — the symbol bound, replayed statically

`symbol_ranges` returned `None` for a file of more than 200 definitions and `anchored_symbols`
then anchored nothing; `more_itertools/more.py` holds 225. Re-judged on the rebuilt trees with arm
C's own recordings (the probe, the pinned value, the base observation) and the repaired observer:

| case | pinned | anchored before → after | specified now, by | own tests |
|---|---|---|---|---|
| `more-itertools-boundary-08` | `'ValueError'` (base raised on `p[2:5:0]`, head `RuntimeError`) | `[]` → `_get_slice`, `peekable` | yes — `more_itertools/more.py` (the symbols' own docstrings quote ``ValueError``); D-240 (b)'s `raises` names it too | catch (1: `PeekableTests::test_slicing_error`) |
| `more-itertools-boundary-10` | `0, 1, 2, 3, 4, 6` | `[]` → `_get_slice`, `peekable` | no | pass |
| `more-itertools-guard_raise-04` | `'ValueError'` (`mi.first([])`) | `[]` → `first`, `last` | yes — `more_itertools/more.py` | catch (1: `FirstTests::test_empty`) |
| `more-itertools-guard_raise-05` | `'ValueError'` (`mi.last([])`) | `[]` → `last`, `nth_or_last` | yes — `more_itertools/more.py` | catch (2) |

**3 of the 4 are specified by the shipped rule once the symbol is anchored**: on the recordings
arm C already made, the class moves from *no symbol to specify* to a value regression the rule
publishes. The static reading applies `find_specifications` — the observer's own function — to the
same tree, pinned set and symbols; it does not re-run the differential, so it is a class, not a
receipt, until the paid re-run of Phase 1. Over the **95** verification rows of the three real-PR
batches the *no symbol* label never appears: nothing on recorded real traffic moves.

## 2. D-250 — the classifier, recounted

With the mutation's site required of an accepted receipt (its verification anchors the mutated
file and the mutation's line lies inside the hunk the binding read), every recorded run of the
forty re-reads unchanged: the original (10 of 40), rerun-env (1 of 8), D-238 (10), D-240 (12),
D-245 (11), arms A/B/C (12 / 14 / 13). **0 receipts elsewhere.** Whether a receipt's failure names
the planted *mechanism* is not a location and stays a human column; on the forty every certified
receipt's failure is the deleted guard's own exception, the removed `None` guard's crash, or the
boundary's own value, read from the ledgers by hand.

## 3. Every case not certified by arm C, with what its tree holds

*symbols* is what D-249 anchors; *tree* is what the base tree holds **about those symbols** — tests
naming them, distinctive literal assertions, object-valued expected sides (a capitalised
constructor on the compared side, or such a row in a `parametrize` table), `raises`, a docstring
Raises section, changelog paragraphs; *own tests* is §0's column; *reading* is by hand, from the
facts. The mechanical version of every column is in `table.md`.

| case | stratum | arm C | symbols (defs in file) | tree | own tests | reading |
|---|---|---|---|---|---|---|
| `attrs-boundary-09` | boundary | no receipt | — (9) | no test names the module-level constant | no naming test | `sys.version_info >= (3, 13)` → `>`: not a crash site (D-231); no probe executes the constant |
| `click-boundary-07` | boundary | value | `ProgressBar`, `format_eta` (48) | 3 naming tests; no value asserted; changelog names the symbol | inconclusive | `format_eta()` at `t == 0`: nothing pins `'01:01:01'` |
| `python-dotenv-boundary-06` | boundary | value | `parse_binding` (24) | 0 naming tests | no naming test | nothing specifies `'#novalue'` at the boundary |
| `urllib3-boundary-07` | boundary | value | `RecentlyUsedContainer.__setitem__` (47) | 0 naming tests; changelog names it | no naming test | nothing specifies the keys at `maxsize` |
| `attrs-guard_raise-03` | guard_raise | value | `_transform_attrs` (122) | 7 naming tests expect `ValueError`, not `UnannotatedAttributeError`; that exception is expected in `tests/test_annotations.py` and `tests/test_next_gen.py` **through `@attr.s(auto_attribs=True)`**, which never names the private symbol | **catch (7)** | **a contract about the public caller** — the association rule stops at the symbol the probe called |
| `click-boundary-10` | boundary | value | `ProgressBar.update` (48) | 5 naming tests; literals `20`, `3`, `5`, `'20/20'` | inconclusive | pins `1` only; a (symbol, input, relation) contract would not exclude it by value |
| `itsdangerous-guard_raise-01` | guard_raise | value | `Signer.__init__` (19) | `test_invalid_separator` expects `ValueError` **through the `make_signer` helper**; the rule sees only `BadTimeSignature` | **catch (3)** | **a contract reached through a helper** |
| `jinja-boundary-12` | boundary | value | `TemplateStream._buffered_generator` (78) | 0 naming tests; changelog names it | no naming test | nothing specifies the chunk size at the boundary |
| `more-itertools-boundary-08` | boundary | no receipt | `_get_slice`, `peekable` (225) | docstrings quote ``ValueError``; `raises(ValueError)` | **catch (1)** | **D-249; specified once anchored** |
| `more-itertools-boundary-10` | boundary | no receipt | `_get_slice`, `peekable` (225) | 19 naming tests; nothing pins the cache length | pass | D-249 anchors it; nothing specifies `len(p._cache)` |
| `packaging-boundary-11` | boundary | no receipt | `BoundaryVersion.__lt__` (45) | 3 naming tests; 2,367 collected tests pass on the mutant | pass | a silent mutant: three probes reached the line and saw no difference, and so do the tests |
| `python-dotenv-boundary-08` | boundary | value | `parse_variables` (16) | `parametrize` table of 6 rows, 5 of them object-valued (`[Variable(name="a", default=None)]`) | **catch (4)** | **an object-valued table the literal matcher cannot read**; the probe's `${FOO}` is the table's `${a}` |
| `urllib3-guard_raise-03` | guard_raise | value | `RequestMethods.request_encode_body` (6) | 4 naming tests; none expects `TypeError` | pass | a deleted guard nothing tests |
| `click-guard_raise-03` | guard_raise | no receipt | `open_stream` (50) | 0 naming tests | no naming test | `'a' in mode` under `atomic`: nothing tests it, no probe found it |
| `itsdangerous-guard_raise-04` | guard_raise | no receipt | `TimestampSigner.unsign` (12) | `test_malformed_timestamp` fails on head | **catch (1)** | **the tree's own test is the input the search never tried** (arm B found it with `max_age=10`) |
| `jinja-guard_raise-01` | guard_raise | value | `Bucket.write_bytecode` (31) | 2 naming tests expect `Error`, not `TypeError` | pass | a deleted guard nothing tests |
| `more-itertools-guard_raise-04` | guard_raise | no receipt | `first`, `last` (225) | docstring: *raise ``ValueError``*; `raises(ValueError)` | **catch (1)** | **D-249; specified once anchored** |
| `click-guard_raise-05` | guard_raise | value | `open_stream` (50) | 0 naming tests | no naming test | `'w' not in mode` under `atomic`: nothing tests it |
| `jinja-none_guard-13` | none_guard | value | `generate` (126) | 4 naming tests | **catch (206)** | the probe pinned the compiled source of a template, which nothing asserts, while 206 of 208 tests fail on head: **the search chose an unspecifiable observation of a defect the whole suite states** |
| `more-itertools-guard_raise-05` | guard_raise | no receipt | `last`, `nth_or_last` (225) | docstring; `raises(ValueError)` | **catch (2)** | **D-249; specified once anchored** |
| `packaging-guard_raise-06` | guard_raise | value | `ArchiveInfo._from_dict` (26) | `test_validate_archive_info_hashes` expects `DirectUrlValidationError` **through `DirectUrl.from_dict`**; the naming tests expect `PylockValidationError` | **catch (1)** | **a contract about the public caller** |
| `python-dotenv-guard_raise-02` | guard_raise | value | `_walk_to_root` (21) | 0 naming tests | no naming test | a deleted guard nothing tests |
| `click-none_guard-15` | none_guard | no receipt | `_pager_contextmanager` (48) | 2 naming tests | **catch (5)** | the probe was refused (it assigned `sys.stdin`, D-235); the tree's tests reach the pager without doing that |
| `more-itertools-none_guard-17` | none_guard | no receipt | `pairwise`, `repeatfunc` (70) | 6 naming tests | **catch (1)** | search variance (arm A certified it); the tree's test is the input |
| `packaging-none_guard-13` | none_guard | no receipt | `_get_glibc_version` (13) | 5 naming tests | **catch (2)** | two probes missed the changed lines; the tree's tests hit them |
| `urllib3-none_guard-18` | none_guard | value | `PoolManager._proxy_requires_url_absolute_form` (21) | `test/test_poolmanager.py` asserts `False` about the symbol — a generic constant the rule discards; 8 object-valued table rows | **catch (1)** | **generic by value, a contract by (symbol, input, relation)** |

The certified thirteen, for the same column: own tests catch 7 (`packaging-guard_raise-01`,
`urllib3-guard_raise-04`, `attrs-none_guard-15`, `itsdangerous-guard_raise-05`,
`urllib3-none_guard-15`, `attrs-none_guard-17`, `itsdangerous-guard_raise-06`), pass 3, no naming
test 2, inconclusive 1 (`attrs-none_guard-14`: the naming file is `bench/test_benchmarks.py`, which
does not collect).

## 4. The other columns, in one line each

- **Docstring Raises sections:** 0 of 40 symbols carry one (`:raises X:` or a *Raises* section).
  The source the plan's §4.1 named is empty on this corpus.
- **Changelog paragraphs naming the symbol:** present for 19 cases, and in none of them is the
  pinned value quoted — the rule already reads them, and they never decide.
- **Object-valued expected sides** (a constructor on the compared side, or in a `parametrize`
  row): 14 cases hold at least one; 4 of them are misses whose own tests catch the mutant.
- **Association through a caller or helper:** in 3 of the 6 *deleted guard* misses the base
  tests expect exactly the deleted guard's exception, in a scope that names the public caller or a
  fixture/helper and never the touched symbol.
- **The search:** in 5 misses the base tree's own tests hold a discriminating input and three
  probes did not find one; in `jinja-none_guard-13` the probe found one and pinned an
  unspecifiable value.

## 5. What is and is not claimed

- **Not a recall figure, and not a promise of one.** 9 of the 27 misses hold an admissible
  contract the chain cannot use today; that is the plan's exit-condition number, measured
  statically and by the libraries' own tests. Turning any of the 9 into a receipt needs the
  Phase 1 mechanisms (D-249 is in; object-valued specifications and association through callers
  are `attest.intent.v6`, decision B) and the paid re-run, under `AGENTS.md` §9's ±2 jitter.
- **The own-tests column ran the files that name a touched symbol, not the full suites**, so 21
  is a lower bound on what the libraries would catch and 7 an upper bound on silent mutants.
  Three cases are inconclusive because the only naming file is a typing fixture or a benchmark
  that does not collect.
- **The forty is a diagnostic set.** It has been run seven times; nothing measured on it again
  is a validation of the plan (Phase 3 needs a new population).
- **Own-test detection is not the product's job on natural traffic**: a merged pull request's CI
  has run head's tests. The column measures which planted defects the *tree already states*, and
  keeps "the tests would have caught it" apart from "the reviewer found it" — 5 certified
  defects fall in the second column alone.
- Nothing here changes a rule, a version, a cap or a price. The two code changes are D-249 (a
  bound that had become a verdict) and D-250 (a classifier that never asked where the receipt
  sat); both are recorded, tested and reversible.
