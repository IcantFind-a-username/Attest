# Phase 1 in the container, 2026-09-15 — the full gate closed, D-249's receipts, and {frozen, contract} probe × {v5.1, v6} with kernel receipts

**Owner instruction of 2026-09-15 ("继续保持不付费、不推送、默认 v5.1 …").** No model call, no paid
run, nothing pushed; `INTENT_POLICY_VERSION` is still `attest.intent.v5.1` and no product caller
names another. Every execution is the product's own path on `linux-container-v1` --
`execute_differential`, then `attempt_certification`, which validates the receipt in the kernel,
writes the evidence bundle and verifies it offline with its seal. A case is **certified** here only
when that returns `accepted`. Driver: `scripts/corpus/container_pairing.py` (D-253), run id `r2`.
Records (append-only JSONL, one line per execution):
[`evidence/2026-09-15-container-pairing/`](evidence/2026-09-15-container-pairing/). Bundles:
`.attest/corpora/container-pairing/r2/` (gitignored; each record names its receipt digest and
bundle path). **Status: measurement; no gate is claimed by it.**

## 0. The answers

| asked | result |
|---|---|
| restore container execution | **done.** Every `docker build` had hung on `docker-credential-desktop get` (BuildKit asking the macOS credential helper for registry credentials, which never answered). The harness runs docker with `DOCKER_CONFIG` pointing at a config with no `credsStore`; the operator's `~/.docker` is untouched, and `docker run` keeps the adapter's credential-free environment. A two-line build takes 3 s |
| the full gate under Docker | **passes** on `f655afc`: 2,396 tests, 0 failed, 0 skipped; kernel and execution coverage **93.33%** (floor 90%) ([log](evidence/2026-09-15-container-pairing/full-gate-f655afc.log)). The nine host failures of the previous window were the missing daemon. Re-run on the D-253 tree `48ab23a`: **passes**, 2,402 tests, 93.34% (§6) |
| D-249's actual new receipts | **+3, −0.** On arm C's frozen probes, v5.1 certifies **16 of 40** against arm C's recorded 13; the three gained are exactly the `more_itertools/more.py` cases, and a counterfactual re-judgement of each receipt's own observation under the pre-D-249 symbol rule returns *no symbol to specify* for all three (§1) |
| contract probes, by a fixed rule, for the five cases | **4 of 5 constructible, 20 probes; 1 not constructible** (`attrs-guard_raise-03`: its input is a class the test defines in its own body). 2 further contract sites of `packaging-guard_raise-06` are not constructible (fixtures) (§2) |
| the 2×2 pairing, and what each new certification depends on | **+3 correct certifications, −0**: `packaging-boundary-08`, `packaging-guard_raise-06`, `urllib3-none_guard-18` certify **only** as contract probe × v6 -- each needs *both* the contract probe and v6's admission. Frozen × v6 gains nothing over frozen × v5.1 (16 = 16); contract × v5.1 certifies nothing (§3) |
| the acceptance path and its false-positive counterexamples | the three acceptance paths are traced contract by contract (§3b). The counterexamples -- the same probe on a head that also removes the test the admitted contract stands on -- **certify 0 of 12**; one of them (`packaging-guard_raise-06`) is refused *only* by D-253's standing-at-head binding and **would have published under D-252** (§4) |
| controls | the four real-PR value lines that carry their probe: **0 of 8** executions certify, the differential holds on all four, all four stay yellow under both policies (§5) |

Correct means the receipt's failure is the planted defect's own effect, read per receipt in §1 and
§3b. **The forty re-read under the harness: frozen × v5.1 = 16 of 40 (40.0%); with the three
contract-probe cases certified under v6, 19 of 40 (47.5%).** The second figure is **not a product
measurement**: no shipped path writes a contract probe (§7).

## 1. D-249's receipts, on the frozen probes

Arm C's frozen probe was replayed for every case that has one (33 of 40; 7 have none: the probe
never made the revisions differ), under v5.1 and under v6: 66 executions, 32 accepted bundles, all
re-verified offline with their seal.

| | v5.1 | v6 |
|---|---:|---:|
| certified | 16 | 16 |
| gained against arm C's recorded 13 | 3 | 3 |
| lost against arm C's recorded 13 | 0 | 0 |
| gained / lost against v5.1 | — | 0 / 0 |

| gained receipt | probe | the merge base | head | specification | receipt | before D-249 |
|---|---|---|---|---|---|---|
| `more-itertools-boundary-08` | `p[2:5:0]` | raised `ValueError` | raises `RuntimeError` | `ValueError` in `more_itertools/more.py` (the symbols' own docstrings) | `e8fd13123394` | *no symbol to specify* |
| `more-itertools-guard_raise-04` | `mi.first([])` | raised `ValueError` | returns the `_marker` sentinel | the same | `da780aaa0236` | *no symbol to specify* |
| `more-itertools-guard_raise-05` | `mi.last([])` | raised `ValueError` | returns the `_marker` sentinel | the same | `e9b3e47af6e6` | *no symbol to specify* |

Each is the planted defect's own effect: the `step > 0` → `>=` swap lets a zero step through the
guard that raised `ValueError('slice step cannot be zero')`; the two deleted `if default is
_marker: raise ValueError(...)` guards let the sentinel escape. `more-itertools-boundary-10` is
anchored by D-249 as well and stays unspecified (nothing pins `len(p._cache)`).

## 2. The contract probes, and the rule that made them

The rule was fixed in the driver's docstring before any probe ran and applied to every contract the
v6 pairing found: the call is the contract's own call (the side of its `==`/`is` whose callee is
the touched symbol; for an expected exception, the first call inside the `with raises(...)` that
resolves to the caller the contract names); every free name is bound only from the test's own
source (a parametrize row, an import of a non-test module, an earlier assignment in the function,
a module-level assignment); a fixture, a name the test module defines, or an import of a test
module makes the contract not constructible; one probe per row, in (file, line, row) order; the
product's own `hygiene_refusal` and import check apply. Per case, **the first probe in that order
whose differential held decides**, under both policies -- the product's screening rule, decided
before any intent rule reads the result. Every other probe is recorded and counted nowhere.

| case | contract sites | probes | not constructible, and why | differentials held | decisive probe |
|---|---:|---:|---|---:|---|
| `attrs-guard_raise-03` | 1 | 0 | `C` -- a class the test defines inside its body | — | — |
| `packaging-boundary-08` | 5 rows | 5 | — | 3 | row 0: `_parse_musl_version(output)`, `output = MUSL_AMD64` |
| `packaging-guard_raise-06` | 9 | 7 | 2 fixtures (`direct_url_dict`, `url`) | 1 | `DirectUrl.from_dict({... 'hashes': {'md5': 123 ...}})` |
| `python-dotenv-boundary-08` | 6 rows | 6 | — | 4 | row 0: `list(parse_variables(''))` |
| `urllib3-none_guard-18` | 2 | 2 | — | 2 | `PoolManager()._proxy_requires_url_absolute_form(Url('http://example.com'))` |

**One derivation is kept as the record of a mistake**: run `r1` chose, for `attrs`, the side of the
assertion whose callee merely lived in the anchored module (`_Attributes(...)`), not the touched
symbol. `r2` applies the finder's own test; `r1`'s file stays beside it.

## 3. The 2×2, case by case

### 3a. The grid

| case | frozen × v5.1 | frozen × v6 | contract × v5.1 | contract × v6 | the new certification depends on |
|---|---|---|---|---|---|
| `packaging-boundary-08` | drawer | drawer | drawer | **certified** `497e3ba2dd22` | both: the contract probe, and v6 admitting its contract |
| `packaging-guard_raise-06` | drawer | drawer | drawer | **certified** `18855a0a8ab9` | both |
| `urllib3-none_guard-18` | drawer (generic `False`) | drawer | drawer (generic `False`) | **certified** `cea1c0be4cd4` | both |
| `python-dotenv-boundary-08` | drawer | drawer | drawer (pins nothing) | drawer (pins nothing) | — |
| `attrs-guard_raise-03` | drawer | drawer | not constructible | not constructible | — |

Why neither change alone suffices, read from the records: the **frozen probes** use inputs no
contract states (`Version 1.2.3` where the row says `1.2.2`; `ArchiveInfo._from_dict` where the
test enters through `DirectUrl.from_dict`; a `PoolManager` and URL built in setup), so v6 refuses
them for input or entry; the **contract probes under v5.1** pin a value the literal rule cannot see
(an object repr, an exception expected through a caller, a generic `False`).

Three further contract probes certify under v6 and are counted nowhere (not decisive):
`packaging-boundary-08` rows 1 and 2, and `urllib3-none_guard-18`'s second assertion.

### 3b. The acceptance paths

Each admitted contract, from the receipt's own intent record:

| case | admitted contract | input (probe = source) | derived value = pinned | entry | stands at head |
|---|---|---|---|---|---|
| `packaging-boundary-08` | `parametrize_row`, `tests/test_musllinux.py:57` | `'musl libc (x86_64)\nVersion 1.2.2\n'` | `_MuslVersion(major=1, minor=2)` -- a `NamedTuple` of the tree | `_parse_musl_version` | yes |
| `packaging-guard_raise-06` | `caller_raises`, `tests/test_direct_url.py:95` | the dict literal of the test | `'DirectUrlValidationError'` | `ArchiveInfo._from_dict` ← `DirectUrl.from_dict`, the probe's own entry | yes |
| `urllib3-none_guard-18` | `bound_assertion`, `test/test_poolmanager.py:423` | `urllib3.poolmanager.PoolManager() :: urllib3.util.url.Url('http://example.com')` | `False` (generic, covered by the contract) | `PoolManager._proxy_requires_url_absolute_form` | yes |

And the planted defects: `len(lines) < 2` → `<=` makes the two-line x86_64 output return `None`
where the row states `_MuslVersion(1, 2)`; the deleted hashes guard lets `DirectUrl.from_dict`
accept an integer hash the test expects it to refuse; the deleted `if self.proxy is None: return
False` makes a proxy-less `PoolManager` claim absolute-form URLs. **Each is the defect, not an
intended change.** The other rows of the same tables were refused in the same records for another
input (the i386 row derives the same `_MuslVersion(1, 2)` and is refused for its input).

`python-dotenv-boundary-08` shows two limits of v6, reported rather than tuned: the decisive row
(`''`) pins `[]`, which the value rule does not count as a pinned value; the `${a}` row's expected
`[Variable(name="a", default=None)]` is a plain class, not a `NamedTuple` or `@dataclass`, so v6
cannot derive it.

## 4. The counterexamples: an intended change the contract no longer stands on

For every contract probe v6 certified (six, the three decisive and the three counted nowhere), a
head was built mechanically: the mutation commit, plus the removal of every test function holding
an admitted contract's site -- *this change alters the behaviour and drops the test that pinned
it*, which must not publish. Twelve executions:

| counterexample | v5.1 | v6 | what refused it under v6 | under D-252 (no standing binding) |
|---|---|---|---|---|
| `packaging-boundary-08` ×3 | drawer | drawer | D-132 (c): the removed test names `_parse_musl_version` | drawer |
| `packaging-guard_raise-06` | drawer | drawer | **D-253: the contract no longer stands at head** -- the removed test names only `DirectUrl.from_dict`, so D-132 (c) reads no intent | **publishes** |
| `urllib3-none_guard-18` ×2 | drawer | drawer | D-132 (c): the removed test names the symbol | drawer |

**0 of 12 certify.** The D-252 column re-judges each record's own observation with every fully
bound contract admitted regardless of head: the caller-contract counterexample is the false
publication the standing binding exists to stop, and the unit tests pin the same shape
(`tests/test_intent_v6.py::test_a_change_that_removes_the_contract_at_head_is_not_specified_by_it`).

## 5. The controls

The real-PR value lines whose note carries its probe (D-241), on the pull requests' own base and
head: `mahmoud/boltons#467` ×3 and `Delgan/loguru#1508`. **All four differentials hold, 0 of 8
executions certify, all stay yellow under both policies; v6 finds no contract on any.** The other
twelve value lines are not replayable (eight rejection rows the value rule never reads, four notes
before D-241 without their probe), as the offline pairing already recorded.

## 6. What D-253 changed in the code, and the gate on it

- `execute_differential(..., intent_policy=INTENT_POLICY_VERSION)` and
  `certification_policy(..., intent_policy_version=INTENT_POLICY_VERSION)`: a harness can name v6
  and get a v6 receipt validated against a v6 policy. **No product caller passes either.**
- v6's contract reader: a contract is admitted only while it **stands at head**
  (`ContractRecord.standing_at_head`); arguments bind as literals, **name chains** (the probe side
  now as the source side) and **constructions of imported callees** (`pkg.mod.Url('…')`); a method
  call's **receiver construction** is part of its input, so `Grid(width=5).cell(p)` and
  `Grid(width=2).cell(p)` are different inputs even when they return the same value -- D-252
  compared arguments alone and would have admitted that. Six REDs, each failing on the D-252
  source (`tests/test_intent_v6.py`, now 17 tests).
- **The full gate on the D-253 tree `48ab23a` passes under Docker**: 2,402 tests, 0 failed, 0 skipped,
  kernel and execution coverage **93.34%**
  ([log](evidence/2026-09-15-container-pairing/full-gate-48ab23a.log)); ruff, mypy and
  `git diff --check` clean.

## 7. What is and is not claimed

- **+6 correct certifications on the forty, −0**: 3 from D-249 under the shipped rule, 3 from
  contract probe × v6. The first three are a product change already on this branch; the second
  three need a probe **no shipped path writes** and a rule **no shipped path selects**.
- **Not a recall figure.** The forty is a diagnostic set -- seven model runs and this replay; the contract probes
  were derived *from the base tests themselves*, which is exactly the information a product search
  would have to find. What the three cases show is that when a probe uses a contract's own input
  and entry, v6 turns the contract into a correct receipt, and that its bindings refuse every
  mis-association this run constructed.
- **Zero false publications on 20 executions that could have produced one** (12 counterexamples,
  8 controls) is a count, not a rate; one of the twelve needed D-253 to stay zero.
- Remaining blockers are in the handoff: the product search does not propose contract probes; v6
  cannot derive plain classes or read an empty container as pinned; a contract whose input is a
  fixture or a class defined in the test is not constructible; the credential-helper hang is a host
  configuration the harness works around, not repairs.
