# Contract binding, 2026-09-15 — a contract is bound at its assertion's program point, or refused

**Owner instruction of 2026-09-15 ("下一轮只做契约绑定正确性 …").** No model call, no paid run,
nothing pushed; the factory configuration is unchanged (`contract_probes = False`,
`intent_policy = attest.intent.v5.1`). The product change is D-255, experimental
`attest.intent.v6.1`: `494758f`, `3c1a9ab`, `81da0bb`, `2bbce06` and `ba91320`, the last being
the code every result below ran on unless a row names another commit. The instruments are
`scripts/corpus/binding_cases.py`, `contract_search_diff.py`, `bundle_reverify.py` and
`frozen_e2e.py` at `1773794`. The records are in
[`evidence/2026-09-15-contract-binding/`](evidence/2026-09-15-contract-binding/)
([manifest](evidence/2026-09-15-contract-binding/manifest.json)).

**Status: correctness repair of an experimental rule.** It is not a recall measurement, it moves
no default, and no paid re-run follows from it. The full gate under Docker passes on
`ba91320`: 2,492 tests, 0 failed, 0 skipped, kernel and execution coverage 93.42%
([log](evidence/2026-09-15-contract-binding/full-gate-ba91320.log)).

## 0. The answers

| asked | result |
|---|---|
| RED for the three shapes, traced to the intent verdict and the kernel; reader and kernel reported separately | **before (`8f27dd2`, v6): the reader admitted and the kernel accepted in all three** (§1). After (`ba91320`, v6.1): the reader admits none, the kernel accepts none |
| do not call a local defect a final false positive | each accepted receipt claimed *the base tree specifies this value*, and in each that claim was false. Whether a red would have been wrong depends on the change's intent, which these synthetic cases do not fix (§1) |
| minimal repair: supported shapes, inputs bound at the assertion's program point, refuse with a reason what cannot be proven | **done** (§2). The rule reads statements at the test body's own level. Before the call, only the assignments in force and inert statements may stand. Everything else is refused with the line that caused it |
| no extension to unittest, fixtures, local classes or structured expectations | **none**. Each of those is refused, now with a stated reason |
| check `admitted` against the binding fields; the generator's flag is not evidence | **done**. Under v6.1 the kernel recomputes admission from the recorded fields, refuses a record whose flag, covered value or symbol disagrees, and adds covered values itself (§3) |
| state what offline verification verifies | it re-judges the **recorded observation, trusted as recorded**. It does not rebuild any binding from contract source, which the bundle does not carry. A test pins this (§3) |
| keep the three gains and the old counterexamples | **kept**. Replayed on the experimental arm under v6.1, the three gains publish through the same contract probes and none of the 10 affected forty cases changes stage. The 3 counterexample cases (6 variants) and 2 affected control pull requests stay at 0 red publications (§5) |
| selection regression: first contract differential not certifiable, model probe certifiable | **pinned as it behaves, not changed**: the model probe is never asked (§4). In the frozen corpora it hid no certifiable result |
| related tests, one gate, independent review of the certification boundary, replay only affected cases | related suites pass; the gate passes on `ba91320`; three review rounds (§6); 18 reviews replayed (§5) |

## 1. The three shapes, before and after

Each scenario is a two-revision repository. `trace` runs the product's own path on it:
`verify_candidate` (contract search when on, then the model probe, the 3×3 differential and the
intent observation), then `attempt_certification` (receipt and kernel validation).

| scenario | before, `8f27dd2`, v6: probe / reader admitted / kernel | after, `ba91320`, v6.1: probe / reader admitted / kernel | what the reader records after |
|---|---|---|---|
| name reassigned after the assertion: `text = "1,2"; assert norm(text) == Point(1, 2); text = "9,9"` | model / **yes** / **accepted** | model / no / not attempted | input `'1,2'` (the program point), not the probe's `'9,9'`; `input_bound` false |
| receiver state changed after construction: `g = Grid(width=2); g.cache = {}; assert g.cell(Point(1, 2)) == Point(2, 2)` | contract / **yes** / **accepted** | model / no / not attempted | `flow_bound` false: *line 6 touches 'g' between the binding in force and the assertion at line 7*; the search refuses the contract probe with the same line |
| unreachable assertion: `return` then `assert parse("5,6") == Point(5, 6)` | contract / **yes** / **accepted** | model / no / not attempted | `flow_bound` false: *line 5 returns before the assertion at line 6: no run reaches it* |
| legal contract, same shape as the first, on a change that breaks `"1,2"` | contract / no / not attempted | contract / **yes** / **accepted** | admitted at the program point; the kernel adds the value |

What each "accepted" actually was. In the first, the receipt said the base tests specify
`norm("9,9") == Point(1, 2)`; they state that for `"1,2"` only. In the second, the probe
omitted `g.cache = {}`, so it exercised a grid the test never checks; with the cache set, head
still returns `Point(2, 2)`. In the third, the base suite never runs the assertion. The kernel
accepted a specification that did not exist. That is a broken intent link, not by itself proof
that a red was false.

The pre-fix reader and generator also disagreed on the first shape: the generator bound the line
before the assertion, the reader the last assignment in the function. The same fault refused the
legal contract, the fourth row.

Separating the two halves: the reader fix alone, under v6's own kernel at `494758f`, refuses all
three ([after-494758f-v6.json](evidence/2026-09-15-contract-binding/after-494758f-v6.json)).
The kernel half is exercised by forged records (§3), which no honest observer writes.

## 2. The rule, and what it refuses

A contract's call has a **program point**: the statement of the test body's own level it belongs
to. For a caller contract, it is the first statement of a single-context `with raises(...)`
block at that level. For the model's replay test, it is the first statement of a `try`. The
input is bound from the plain `name = value` assignments before that point, the last one for
each name. An assignment after the assertion, or inside a branch, is never the input.

A contract is `flow_bound` only if all of these hold:

- **No early exit.** No statement before the point leaves the test: no `return`, no `raise`, no
  skip/fail/xfail/exit/importorskip call, no compound statement containing one, no `while` loop.
- **Only inert statements.** Every other statement before the point is either an assignment in
  force or inert. Inert means it contains no call, `await`, `yield`, assignment expression,
  attribute or item read, and no store or delete through an attribute or subscript. A def
  counts only without a decorator and with inert defaults and annotations. A class counts only
  with builtin bases the module does not rebind and an inert body.
- **Nothing it depends on is disturbed.** No statement before the point touches a local the
  call depends on, reads a mutable module-level value it depends on, or uses a fixture.
- **Dependencies are read in order.** An assignment in force reads its own dependencies from
  earlier lines. A module-level value the call depends on never names something the test
  rebinds.
- **No mutable value is handed to a call on the way.** This covers the assignments in force and
  the call's own arguments.
- **No name ambiguity.** No name the call depends on is a fixture, or an import, def or class
  rebound in the test. None is bound twice at module level, and there is no star import
  anywhere at module level.
- **A plain, unmarked test.** The test, its enclosing classes, the module and its parametrize
  rows carry no skip, skipif, xfail, usefixtures, indirect, `unittest` skip decorator or patch
  mark, however spelled or aliased. The test is not a generator.

The same rule binds the model's replay test in `probe_call`. A setup it cannot read binds no
input. It also decides the contract-probe generator's refusals, and the generator writes the
body's assignments in source order. A site whose call resolves only through a name out of force
at its point is still recognised, and is refused with its reason rather than dropped. Recursion
beyond the interpreter's depth is a refusal, not an exception.

**What the rule does not read**, stated, not tuned:

- autouse fixtures and `conftest.py`, of which `test_musllinux.py`'s `clear_lru_cache` is one
- `setup_method`, `setUp` and class-level hooks
- plugins, and state earlier tests leave behind
- code a test module runs at import

Each can change what a contract's call sees, and none is followed.

**What it costs in supply**, on the 74 recorded contract searches of the frozen end-to-end
records, rebuilt on their own base trees. The rebuild at `8f27dd2` reproduces every recorded
search exactly.

| population | probes built, `8f27dd2` | probes built, `ba91320` | searches changed |
|---|---:|---:|---:|
| the forty | 34 | 25 | 8 cases |
| counterexample variants | 27 | 25 | 3 of 6 |
| batch 3 controls | 12 | 0 | 2 pull requests |

The refusals name a fixture used first, a receiver used by an earlier assertion, a branch or
loop, a value handed to a constructor, or an earlier call. A second assertion on the same object,
after a first that called it, is now refused: the first call could have changed it. The three
gained contracts are still built: `test_musllinux.py:57`, `test_direct_url.py:95` and
`test_poolmanager.py:423`
([before](evidence/2026-09-15-contract-binding/searches-before-8f27dd2.jsonl),
[after](evidence/2026-09-15-contract-binding/searches-after-ba91320.jsonl)).

## 3. The kernel does not take the observer's word, and what verification means

Under v6.1, `contract_admissible` recomputes admission from the recorded fields. Every binding
must hold: `input_bound`, `evaluated` with a non-empty derived value, `path_bound`,
`standing_at_head` and `flow_bound`. The covered value must be the derived value itself or its
repr, and the kind must be known.

`contract_record_problem` refuses the whole observation when any of these holds:

- a record's `admitted` flag disagrees with that recomputation
- an admitted contract covers a value the failing assertion does not pin
- an admitted contract is about a symbol the change did not touch

The check runs before every other intent rule. The observer no longer merges contract values into
`value_specified`; the kernel adds what admissible contracts cover. Each forgery is a test in
`tests/test_contract_binding.py`: a false flag with each binding in turn, a true binding set with
a false flag, a covered value not pinned, and an untouched symbol.

**Offline verification**, stated precisely. `intent_reasons` rebuilds the observation from
`intent.json`, checks its digest and fields, and re-runs the rule on it. Under v6.1 that
catches a record that contradicts itself. It does **not** rebuild any binding from the contract's
source, because the bundle carries none. A record whose bindings were computed wrongly, but
agree with each other, verifies. The test
`::test_the_verifier_rejudges_the_record_and_does_not_rebuild_it_from_source` asserts both
halves.

**Compatibility.** A v6 record keeps its fields and its digest: the two new contract fields are
dropped from it, and the verifier requires each contract to carry exactly its version's fields.
All 109 evidence bundles under `.attest/corpora/` verify identically at `8f27dd2`, `494758f`,
`81da0bb`, `2bbce06` and `ba91320`. That is 48 accepted under v5.1 and 61 under v6.
A review configuration now accepts `v5.1` and `v6.1` only. v6, which trusted the flag, can no
longer be selected, and its receipts are still judged by its own rule (D-121).

## 4. The selection regression, diagnosed and left as it is

The search's strategy is *the first probe whose revisions differ decides*. With contract probes
on, `describe(1) == Label("1")` differs between base and head. A plain class cannot be
derived, so that differential cannot certify. The model probe `describe(9)` would certify
through the docstring's `'nine'`, but it is never asked.

| `first_contract_masks_model` | probe | model calls | kernel |
|---|---|---:|---|
| contract probes on | contract | 0 | not attempted (drawer) |
| contract probes off | model | 1 | **accepted** |

The result is identical before and after the fix, and it is pinned by
`::test_a_first_contract_differential_that_cannot_certify_masks_the_model_probe`. Nothing
retries on the certification result.

**Did it hide an earlier result?** In the frozen end-to-end records, the only case where the
search chose a contract probe that did not certify is `python-dotenv-boundary-08`. Its row
`''` pins `[]`, which is generic. The case's model probe `list(parse_variables('${FOO}'))` was
drawered in the shipped arm, and drawered again under v6 in the container pairing (run `r2`),
so nothing certifiable was hidden. The six counterexample variants choose a contract probe and
are meant to stay silent. The controls chose none. The frozen probes stop at the one each
recorded search ended on, so this covers these corpora only.

## 5. The affected cases, replayed

Run `b1` covers only the cases where D-255 can change something: those whose recorded contract
search or reader contracts are non-empty. It uses arm `E61` (`contract_probes = True`,
`attest.intent.v6.1`), `run_review` end to end on the same ledger-frozen proposals and probes as
D-254's runs, with driver `frozen_e2e.py` at `1773794` and product `src` at `ba91320`.

| forty case | shipped, `f2` S | experimental v6, `f2` E | **v6.1, `b1` E61** | E61's search |
|---|---|---|---|---|
| `packaging-boundary-08` | drawer | published | **published** | contract `test_musllinux.py:57#0` chosen, admitted, `flow_bound` |
| `packaging-guard_raise-06` | drawer | published | **published** | contract `test_direct_url.py:95#0` chosen, admitted, `flow_bound` |
| `urllib3-none_guard-18` | drawer | published | **published** | contract `test_poolmanager.py:423#0` chosen (`:424` now refused), admitted |
| `urllib3-none_guard-15` | published | published | **published** | 4 built, 12 refused, model probe |
| `python-dotenv-boundary-08` | drawer | drawer | drawer | contract chosen; pins a generic `[]` |
| `attrs-guard_raise-03` | drawer | drawer | drawer | 1 refused; model probe |
| `click-boundary-10` | drawer | drawer | drawer | 1 built, 2 refused; model probe |
| `jinja-guard_raise-01` | drawer | drawer | drawer | 1 refused; model probe |
| `packaging-boundary-11` | no probe | no probe | no probe | its one contract probe now refused |
| `packaging-none_guard-13` | no probe | no probe | no probe | its one contract probe now refused |

**None of the 10 changes stage against v6.** Against the shipped arm the three gains are kept
and none is lost. The four published receipts verify offline under v6.1, and each of the three
gains carries exactly one admitted, `flow_bound` contract
([bundles](evidence/2026-09-15-contract-binding/bundles-b1-E61.jsonl)). The other 30 of the forty
were not replayed: their searches built and refused nothing and their observations recorded no
contract, so neither the reader nor the kernel change can reach them. **No 40-case figure is
claimed from this run.**

**Counterexamples:** 3 independent cases, 6 variants, **0 red publications**. The search chose the
contract probe in 6 of 6. The one value note, on the `packaging-guard_raise-06` variant, is
identical to both earlier arms. **Controls:** the two pull requests whose search had built
probes, `boltons#481` and `boltons#434`, give **0 red publications and 0 value notes** with the
same verification outcomes as before, and the search now builds none. The other 22 controls built
no contract probe and were not replayed.

The frozen provider's replayed token figures, $0.34 over the ten, are not purchases.

## 6. The independent review, three rounds

The reviewer was a separate agent with read access and no edits. It was told the change's claims
and asked to break the certification boundary adversarially. Every finding below was reproduced
by running code.

1. **On `494758f` and `3c1a9ab`.** No fail-open in the kernel. Version sets and v5.1/v6 digests
   were sound, and the wide-scope fallback cannot bind or admit. The reader still admitted nine
   shapes:
   - a binding chain read after its dependency was rebound
   - a callee rebound in the test or at module level
   - aliases of a mutable module constant
   - module state changed through another name, or `globals()`
   - `patch.object`, mark aliases, per-row marks, an outer class's mark
   - fixture parameters and `indirect=`
   - match captures
   - a recursion crash on a 600-deep chain
   - shadowed names on the expected side

   Fixed in `81da0bb`.
2. **On `81da0bb`.** All nine closed. New:
   - a module constant naming a name the test shadows
   - bare decorators and annotations, class creation, attribute reads
   - unittest skip spellings and a patch imported under another name
   - a star import
   - the contract cap made unreachable by the recursion guard
   - exponential alias walking
   - a binding in force handing a mutable local to a call

   Fixed in `2bbce06`.
3. **On `2bbce06`.** All closed except a mutable module-level list handed to a call and a star
   import nested in a `try`, plus a low-risk builtin-named class base. Fixed in `ba91320`, which
   was not reviewed again. Its three rules have tests.

Two full gates were started on superseded commits and stopped when a review round reported.
Their partial logs are kept:
[81da0bb](evidence/2026-09-15-contract-binding/full-gate-81da0bb-stopped.log),
[2bbce06](evidence/2026-09-15-contract-binding/full-gate-2bbce06-stopped.log). The gate claimed is
the one on `ba91320`.

## 7. What is and is not claimed

- **Claimed:** on these scenarios and corpora, v6.1 refuses the three mis-bindings and every
  shape the review reproduced. It keeps the three contract gains, and the replayed
  counterexamples and controls stay silent. The kernel refuses self-inconsistent contract
  records. Old receipts verify unchanged.
- **Not claimed:** that the rule is complete. It reads one function and the module around it
  (§2 lists what it does not follow). The last fix commit was not re-reviewed. Offline
  verification does not rebuild bindings from source. Nothing here is a recall figure, a reason
  to switch the default, or a reason for a paid run.
- **Side effect to know:** arm `C51` (contract probes under v5.1) now screens fewer contract
  probes, because the generator's refusals are shared. `container_pairing.py` and
  `v6_pairing.py` still name v6 when run by hand. They call the observer directly, not through a
  review configuration, and are historical instruments.
