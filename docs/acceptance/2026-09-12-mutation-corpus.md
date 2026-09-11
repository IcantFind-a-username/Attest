# mutations-v1 — a crash-mutation corpus over eight public clones, built for $0

**Work order PR 3 e of the 2026-09-12 overnight window.** For each of the eight `G-NULL-001a` clones at its default-branch tip, the library's **own** test suite ran under `coverage` on this host to find the lines its tests reach; three classes of crash mutation were then injected on covered lines of the package's own source, each as its own commit off the tip, and every mutation yields two cases in the `swebench_pilot` manifest shape — **forward** (base = the original, head = the mutation: the pull request that introduces the defect) and **fix** (base = the mutation, head = the original). **No review was bought and nothing here was reviewed.** The corpus lives under `.attest/corpora/mutations-v1/` and is not committed.

| | |
|---|---|
| libraries with cases | **8** of 8 |
| libraries skipped | **0** |
| mutations injected | **122** (guard_raise 44, boundary 42, none_guard 36) |
| cases | **244** (122 forward, 122 fix) |
| covered lines, all built libraries | 22552 in 137 package files |

## 1. Per library

| library | tip | covered files | covered lines | sites found (raise / boundary / None) | injected (raise / boundary / None) | cases | suite wall time |
|---|---|---|---|---|---|---|---|
| `attrs` | `8f767776326f` | 19 | 1865 | 6 / 13 / 5 | 6 / 6 / 5 | 34 | 17.1s |
| `click` | `6aabf099bfdd` | 17 | 4221 | 54 / 33 / 13 | 6 / 6 / 6 | 36 | 946.8s |
| `itsdangerous` | `672971d66a2e` | 8 | 415 | 6 / 2 / 1 | 6 / 2 / 1 | 18 | 8.4s |
| `jinja` | `5ef70112a1ff` | 25 | 5727 | 59 / 26 / 6 | 6 / 6 / 6 | 32 | 10.3s |
| `more-itertools` | `9ed3dbb0ae52` | 3 | 2215 | 53 / 130 / 9 | 6 / 6 / 6 | 36 | 78.2s |
| `packaging` | `10590c194edb` | 22 | 4381 | 77 / 90 / 47 | 6 / 6 / 6 | 36 | 226.6s |
| `python-dotenv` | `a00cb2eed070` | 8 | 471 | 4 / 4 / 0 | 4 / 4 / 0 | 16 | 4.2s |
| `urllib3` | `5f2a6a843d01` | 35 | 3257 | 76 / 41 / 21 | 6 / 6 / 6 | 36 | 80.7s |

## 3. The three classes, and the cap

- **guard_raise** — an `if …: raise …` validation deleted.
- **boundary** — a `<=`/`<` (or `>=`/`>`) boundary swapped.
- **none_guard** — an `if x is None: return …` guard deleted.
- At most **6 per class per library**, taken in `(file, line)` order among the sites the library's own tests reach; a site whose mutation does not parse is skipped. The cap is what makes the corpus a sample rather than an exhaustive walk, and the `sites found` column says how much was left.

## 4. What the corpus is for, and what it is not

- A **fix-direction** case is the shape the held-out slice already measures (a repairing commit's parent against the commit); a **forward** case is the shape E-04 reviews (a pull request introducing a change). Both directions of the same mutation let one defect be asked from both sides.
- **Not a recall figure.** Nothing here has been reviewed; a library's own tests may or may not catch each mutation (that was not measured — running every suite once per mutation is hours), so the corpus does not yet say which defects are *silent* in the library. That column is the first thing to add before any paid run over it.
- **A known limit of the boundary class.** The rule takes any `<`/`<=`/`>`/`>=` on a covered line, so compatibility modules contribute comparisons on `sys.version_info` (`attrs` `src/attr/_compat.py:11` is one), which are not the class the corpus is named for and whose mutation changes nothing on the interpreter that runs the tests. A later version should exclude comparisons whose operands are version tuples; the cases are listed rather than removed so the count is honest.
- **Not committed.** Manifests carry absolute host paths and real commit shas of worktrees under `.attest/`; the corpus is rebuilt by `scripts/corpus/mutate.py` from the same tips.

## 5. Every case

| case | library | class | site | base | head |
|---|---|---|---|---|---|
| `attrs-boundary-07--fix` | `attrs` | boundary | `src/attr/_compat.py:11` | `8530fe03` | `8f767776` |
| `attrs-boundary-07--forward` | `attrs` | boundary | `src/attr/_compat.py:11` | `8f767776` | `8530fe03` |
| `attrs-boundary-08--fix` | `attrs` | boundary | `src/attr/_compat.py:12` | `209f81c6` | `8f767776` |
| `attrs-boundary-08--forward` | `attrs` | boundary | `src/attr/_compat.py:12` | `8f767776` | `209f81c6` |
| `attrs-boundary-09--fix` | `attrs` | boundary | `src/attr/_compat.py:13` | `207ef89d` | `8f767776` |
| `attrs-boundary-09--forward` | `attrs` | boundary | `src/attr/_compat.py:13` | `8f767776` | `207ef89d` |
| `attrs-boundary-10--fix` | `attrs` | boundary | `src/attr/_compat.py:14` | `f3f85416` | `8f767776` |
| `attrs-boundary-10--forward` | `attrs` | boundary | `src/attr/_compat.py:14` | `8f767776` | `f3f85416` |
| `attrs-boundary-11--fix` | `attrs` | boundary | `src/attr/_make.py:714` | `d791b2f7` | `8f767776` |
| `attrs-boundary-11--forward` | `attrs` | boundary | `src/attr/_make.py:714` | `8f767776` | `d791b2f7` |
| `attrs-boundary-12--fix` | `attrs` | boundary | `src/attr/_make.py:1801` | `b2cfba79` | `8f767776` |
| `attrs-boundary-12--forward` | `attrs` | boundary | `src/attr/_make.py:1801` | `8f767776` | `b2cfba79` |
| `attrs-guard_raise-01--fix` | `attrs` | guard_raise | `src/attr/_funcs.py:117` | `62c96c04` | `8f767776` |
| `attrs-guard_raise-01--forward` | `attrs` | guard_raise | `src/attr/_funcs.py:117` | `8f767776` | `62c96c04` |
| `attrs-guard_raise-02--fix` | `attrs` | guard_raise | `src/attr/_funcs.py:312` | `486c0480` | `8f767776` |
| `attrs-guard_raise-02--forward` | `attrs` | guard_raise | `src/attr/_funcs.py:312` | `8f767776` | `486c0480` |
| `attrs-guard_raise-03--fix` | `attrs` | guard_raise | `src/attr/_make.py:423` | `b5ea1f4f` | `8f767776` |
| `attrs-guard_raise-03--forward` | `attrs` | guard_raise | `src/attr/_make.py:423` | `8f767776` | `b5ea1f4f` |
| `attrs-guard_raise-04--fix` | `attrs` | guard_raise | `src/attr/_make.py:2871` | `4844ae8e` | `8f767776` |
| `attrs-guard_raise-04--forward` | `attrs` | guard_raise | `src/attr/_make.py:2871` | `8f767776` | `4844ae8e` |
| `attrs-guard_raise-05--fix` | `attrs` | guard_raise | `src/attr/_version_info.py:62` | `f6318db3` | `8f767776` |
| `attrs-guard_raise-05--forward` | `attrs` | guard_raise | `src/attr/_version_info.py:62` | `8f767776` | `f6318db3` |
| `attrs-guard_raise-06--fix` | `attrs` | guard_raise | `src/attr/_version_info.py:65` | `10d6f846` | `8f767776` |
| `attrs-guard_raise-06--forward` | `attrs` | guard_raise | `src/attr/_version_info.py:65` | `8f767776` | `10d6f846` |
| `attrs-none_guard-13--fix` | `attrs` | none_guard | `src/attr/_make.py:1613` | `481a9fab` | `8f767776` |
| `attrs-none_guard-13--forward` | `attrs` | none_guard | `src/attr/_make.py:1613` | `8f767776` | `481a9fab` |
| `attrs-none_guard-14--fix` | `attrs` | none_guard | `src/attr/_next_gen.py:424` | `55e92021` | `8f767776` |
| `attrs-none_guard-14--forward` | `attrs` | none_guard | `src/attr/_next_gen.py:424` | `8f767776` | `55e92021` |
| `attrs-none_guard-15--fix` | `attrs` | none_guard | `src/attr/converters.py:37` | `42fee5d2` | `8f767776` |
| `attrs-none_guard-15--forward` | `attrs` | none_guard | `src/attr/converters.py:37` | `8f767776` | `42fee5d2` |
| `attrs-none_guard-16--fix` | `attrs` | none_guard | `src/attr/converters.py:44` | `2822c372` | `8f767776` |
| `attrs-none_guard-16--forward` | `attrs` | none_guard | `src/attr/converters.py:44` | `8f767776` | `2822c372` |
| `attrs-none_guard-17--fix` | `attrs` | none_guard | `src/attr/validators.py:206` | `2f867208` | `8f767776` |
| `attrs-none_guard-17--forward` | `attrs` | none_guard | `src/attr/validators.py:206` | `8f767776` | `2f867208` |
| `click-boundary-07--fix` | `click` | boundary | `src/click/_termui_impl.py:183` | `0714cef0` | `6aabf099` |
| `click-boundary-07--forward` | `click` | boundary | `src/click/_termui_impl.py:183` | `6aabf099` | `0714cef0` |
| `click-boundary-08--fix` | `click` | boundary | `src/click/_termui_impl.py:283` | `eb06c203` | `6aabf099` |
| `click-boundary-08--forward` | `click` | boundary | `src/click/_termui_impl.py:283` | `6aabf099` | `eb06c203` |
| `click-boundary-09--fix` | `click` | boundary | `src/click/_termui_impl.py:298` | `26c30212` | `6aabf099` |
| `click-boundary-09--forward` | `click` | boundary | `src/click/_termui_impl.py:298` | `6aabf099` | `26c30212` |
| `click-boundary-10--fix` | `click` | boundary | `src/click/_termui_impl.py:339` | `42f1769d` | `6aabf099` |
| `click-boundary-10--forward` | `click` | boundary | `src/click/_termui_impl.py:339` | `6aabf099` | `42f1769d` |
| `click-boundary-11--fix` | `click` | boundary | `src/click/_termui_impl.py:541` | `df8ab213` | `6aabf099` |
| `click-boundary-11--forward` | `click` | boundary | `src/click/_termui_impl.py:541` | `6aabf099` | `df8ab213` |
| `click-boundary-12--fix` | `click` | boundary | `src/click/_textwrap.py:18` | `8a5a3118` | `6aabf099` |
| `click-boundary-12--forward` | `click` | boundary | `src/click/_textwrap.py:18` | `6aabf099` | `8a5a3118` |
| `click-guard_raise-01--fix` | `click` | guard_raise | `src/click/_compat.py:321` | `12d88f66` | `6aabf099` |
| `click-guard_raise-01--forward` | `click` | guard_raise | `src/click/_compat.py:321` | `6aabf099` | `12d88f66` |
| `click-guard_raise-02--fix` | `click` | guard_raise | `src/click/_compat.py:328` | `c2fa96af` | `6aabf099` |
| `click-guard_raise-02--forward` | `click` | guard_raise | `src/click/_compat.py:328` | `6aabf099` | `c2fa96af` |
| `click-guard_raise-03--fix` | `click` | guard_raise | `src/click/_compat.py:400` | `be7e9bb8` | `6aabf099` |
| `click-guard_raise-03--forward` | `click` | guard_raise | `src/click/_compat.py:400` | `6aabf099` | `be7e9bb8` |
| `click-guard_raise-04--fix` | `click` | guard_raise | `src/click/_compat.py:407` | `3e1df8c0` | `6aabf099` |
| `click-guard_raise-04--forward` | `click` | guard_raise | `src/click/_compat.py:407` | `6aabf099` | `3e1df8c0` |
| `click-guard_raise-05--fix` | `click` | guard_raise | `src/click/_compat.py:409` | `c57544a2` | `6aabf099` |
| `click-guard_raise-05--forward` | `click` | guard_raise | `src/click/_compat.py:409` | `6aabf099` | `c57544a2` |
| `click-guard_raise-06--fix` | `click` | guard_raise | `src/click/_termui_impl.py:97` | `52d05a47` | `6aabf099` |
| `click-guard_raise-06--forward` | `click` | guard_raise | `src/click/_termui_impl.py:97` | `6aabf099` | `52d05a47` |
| `click-none_guard-13--fix` | `click` | none_guard | `src/click/_compat.py:266` | `4c47d9f8` | `6aabf099` |
| `click-none_guard-13--forward` | `click` | none_guard | `src/click/_compat.py:266` | `6aabf099` | `4c47d9f8` |
| `click-none_guard-14--fix` | `click` | none_guard | `src/click/_compat.py:556` | `9ca58469` | `6aabf099` |
| `click-none_guard-14--forward` | `click` | none_guard | `src/click/_compat.py:556` | `6aabf099` | `9ca58469` |
| `click-none_guard-15--fix` | `click` | none_guard | `src/click/_termui_impl.py:484` | `3d3af6be` | `6aabf099` |
| `click-none_guard-15--forward` | `click` | none_guard | `src/click/_termui_impl.py:484` | `6aabf099` | `3d3af6be` |
| `click-none_guard-16--fix` | `click` | none_guard | `src/click/core.py:3596` | `fac11978` | `6aabf099` |
| `click-none_guard-16--forward` | `click` | none_guard | `src/click/core.py:3596` | `6aabf099` | `fac11978` |
| `click-none_guard-17--fix` | `click` | none_guard | `src/click/core.py:3613` | `5e70adbd` | `6aabf099` |
| `click-none_guard-17--forward` | `click` | none_guard | `src/click/core.py:3613` | `6aabf099` | `5e70adbd` |
| `click-none_guard-18--fix` | `click` | none_guard | `src/click/core.py:3803` | `961b3500` | `6aabf099` |
| `click-none_guard-18--forward` | `click` | none_guard | `src/click/core.py:3803` | `6aabf099` | `961b3500` |
| `itsdangerous-boundary-07--fix` | `itsdangerous` | boundary | `src/itsdangerous/timed.py:141` | `c16c5a40` | `672971d6` |
| `itsdangerous-boundary-07--forward` | `itsdangerous` | boundary | `src/itsdangerous/timed.py:141` | `672971d6` | `c16c5a40` |
| `itsdangerous-boundary-08--fix` | `itsdangerous` | boundary | `src/itsdangerous/timed.py:148` | `71dd47e7` | `672971d6` |
| `itsdangerous-boundary-08--forward` | `itsdangerous` | boundary | `src/itsdangerous/timed.py:148` | `672971d6` | `71dd47e7` |
| `itsdangerous-guard_raise-01--fix` | `itsdangerous` | guard_raise | `src/itsdangerous/signer.py:146` | `65283cff` | `672971d6` |
| `itsdangerous-guard_raise-01--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/signer.py:146` | `672971d6` | `65283cff` |
| `itsdangerous-guard_raise-02--fix` | `itsdangerous` | guard_raise | `src/itsdangerous/signer.py:248` | `ba7d2af8` | `672971d6` |
| `itsdangerous-guard_raise-02--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/signer.py:248` | `672971d6` | `ba7d2af8` |
| `itsdangerous-guard_raise-03--fix` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:103` | `4cf0acd7` | `672971d6` |
| `itsdangerous-guard_raise-03--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:103` | `672971d6` | `4cf0acd7` |
| `itsdangerous-guard_raise-04--fix` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:134` | `87f693ec` | `672971d6` |
| `itsdangerous-guard_raise-04--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:134` | `672971d6` | `87f693ec` |
| `itsdangerous-guard_raise-05--fix` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:141` | `811ab320` | `672971d6` |
| `itsdangerous-guard_raise-05--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:141` | `672971d6` | `811ab320` |
| `itsdangerous-guard_raise-06--fix` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:148` | `fc687dde` | `672971d6` |
| `itsdangerous-guard_raise-06--forward` | `itsdangerous` | guard_raise | `src/itsdangerous/timed.py:148` | `672971d6` | `fc687dde` |
| `itsdangerous-none_guard-09--fix` | `itsdangerous` | none_guard | `src/itsdangerous/serializer.py:383` | `405c9523` | `672971d6` |
| `itsdangerous-none_guard-09--forward` | `itsdangerous` | none_guard | `src/itsdangerous/serializer.py:383` | `672971d6` | `405c9523` |
| `jinja-boundary-07--fix` | `jinja` | boundary | `src/jinja2/compiler.py:953` | `0c7fd57b` | `5ef70112` |
| `jinja-boundary-07--forward` | `jinja` | boundary | `src/jinja2/compiler.py:953` | `5ef70112` | `0c7fd57b` |
| `jinja-boundary-08--fix` | `jinja` | boundary | `src/jinja2/compiler.py:1002` | `5b1b8ff3` | `5ef70112` |
| `jinja-boundary-08--forward` | `jinja` | boundary | `src/jinja2/compiler.py:1002` | `5ef70112` | `5b1b8ff3` |
| `jinja-boundary-09--fix` | `jinja` | boundary | `src/jinja2/debug.py:162` | `13538881` | `5ef70112` |
| `jinja-boundary-09--forward` | `jinja` | boundary | `src/jinja2/debug.py:162` | `5ef70112` | `13538881` |
| `jinja-boundary-10--fix` | `jinja` | boundary | `src/jinja2/environment.py:90` | `a3fb61b5` | `5ef70112` |
| `jinja-boundary-10--forward` | `jinja` | boundary | `src/jinja2/environment.py:90` | `5ef70112` | `a3fb61b5` |
| `jinja-boundary-11--fix` | `jinja` | boundary | `src/jinja2/environment.py:1481` | `f396b385` | `5ef70112` |
| `jinja-boundary-11--forward` | `jinja` | boundary | `src/jinja2/environment.py:1481` | `5ef70112` | `f396b385` |
| `jinja-boundary-12--fix` | `jinja` | boundary | `src/jinja2/environment.py:1637` | `a809dc95` | `5ef70112` |
| `jinja-boundary-12--forward` | `jinja` | boundary | `src/jinja2/environment.py:1637` | `5ef70112` | `a809dc95` |
| `jinja-guard_raise-01--fix` | `jinja` | guard_raise | `src/jinja2/bccache.py:84` | `101f798c` | `5ef70112` |
| `jinja-guard_raise-01--forward` | `jinja` | guard_raise | `src/jinja2/bccache.py:84` | `5ef70112` | `101f798c` |
| `jinja-guard_raise-04--fix` | `jinja` | guard_raise | `src/jinja2/compiler.py:111` | `53edcf54` | `5ef70112` |
| `jinja-guard_raise-04--forward` | `jinja` | guard_raise | `src/jinja2/compiler.py:111` | `5ef70112` | `53edcf54` |
| `jinja-guard_raise-05--fix` | `jinja` | guard_raise | `src/jinja2/compiler.py:282` | `89feec71` | `5ef70112` |
| `jinja-guard_raise-05--forward` | `jinja` | guard_raise | `src/jinja2/compiler.py:282` | `5ef70112` | `89feec71` |
| `jinja-guard_raise-06--fix` | `jinja` | guard_raise | `src/jinja2/compiler.py:1515` | `9ef8c5be` | `5ef70112` |
| `jinja-guard_raise-06--forward` | `jinja` | guard_raise | `src/jinja2/compiler.py:1515` | `5ef70112` | `9ef8c5be` |
| `jinja-none_guard-13--fix` | `jinja` | none_guard | `src/jinja2/compiler.py:119` | `af0ce597` | `5ef70112` |
| `jinja-none_guard-13--forward` | `jinja` | none_guard | `src/jinja2/compiler.py:119` | `5ef70112` | `af0ce597` |
| `jinja-none_guard-14--fix` | `jinja` | none_guard | `src/jinja2/environment.py:100` | `c3046286` | `5ef70112` |
| `jinja-none_guard-14--forward` | `jinja` | none_guard | `src/jinja2/environment.py:100` | `5ef70112` | `c3046286` |
| `jinja-none_guard-15--fix` | `jinja` | none_guard | `src/jinja2/environment.py:1488` | `70e1f396` | `5ef70112` |
| `jinja-none_guard-15--forward` | `jinja` | none_guard | `src/jinja2/environment.py:1488` | `5ef70112` | `70e1f396` |
| `jinja-none_guard-16--fix` | `jinja` | none_guard | `src/jinja2/filters.py:130` | `ed5a3d24` | `5ef70112` |
| `jinja-none_guard-16--forward` | `jinja` | none_guard | `src/jinja2/filters.py:130` | `5ef70112` | `ed5a3d24` |
| `jinja-none_guard-17--fix` | `jinja` | none_guard | `src/jinja2/nodes.py:887` | `4f78b7ab` | `5ef70112` |
| `jinja-none_guard-17--forward` | `jinja` | none_guard | `src/jinja2/nodes.py:887` | `5ef70112` | `4f78b7ab` |
| `jinja-none_guard-18--fix` | `jinja` | none_guard | `src/jinja2/utils.py:625` | `b99d6327` | `5ef70112` |
| `jinja-none_guard-18--forward` | `jinja` | none_guard | `src/jinja2/utils.py:625` | `5ef70112` | `b99d6327` |
| `more-itertools-boundary-07--fix` | `more-itertools` | boundary | `more_itertools/more.py:234` | `38fe50e3` | `9ed3dbb0` |
| `more-itertools-boundary-07--forward` | `more-itertools` | boundary | `more_itertools/more.py:234` | `9ed3dbb0` | `38fe50e3` |
| `more-itertools-boundary-08--fix` | `more-itertools` | boundary | `more_itertools/more.py:453` | `dec0c468` | `9ed3dbb0` |
| `more-itertools-boundary-08--forward` | `more-itertools` | boundary | `more_itertools/more.py:453` | `9ed3dbb0` | `dec0c468` |
| `more-itertools-boundary-09--fix` | `more-itertools` | boundary | `more_itertools/more.py:456` | `5aa02ea5` | `9ed3dbb0` |
| `more-itertools-boundary-09--forward` | `more-itertools` | boundary | `more_itertools/more.py:456` | `9ed3dbb0` | `5aa02ea5` |
| `more-itertools-boundary-10--fix` | `more-itertools` | boundary | `more_itertools/more.py:464` | `69773b4d` | `9ed3dbb0` |
| `more-itertools-boundary-10--forward` | `more-itertools` | boundary | `more_itertools/more.py:464` | `9ed3dbb0` | `69773b4d` |
| `more-itertools-boundary-11--fix` | `more-itertools` | boundary | `more_itertools/more.py:464` | `afdecdde` | `9ed3dbb0` |
| `more-itertools-boundary-11--forward` | `more-itertools` | boundary | `more_itertools/more.py:464` | `9ed3dbb0` | `afdecdde` |
| `more-itertools-boundary-12--fix` | `more-itertools` | boundary | `more_itertools/more.py:471` | `e50149eb` | `9ed3dbb0` |
| `more-itertools-boundary-12--forward` | `more-itertools` | boundary | `more_itertools/more.py:471` | `9ed3dbb0` | `e50149eb` |
| `more-itertools-guard_raise-01--fix` | `more-itertools` | guard_raise | `more_itertools/more.py:234` | `18cc8e81` | `9ed3dbb0` |
| `more-itertools-guard_raise-01--forward` | `more-itertools` | guard_raise | `more_itertools/more.py:234` | `9ed3dbb0` | `18cc8e81` |
| `more-itertools-guard_raise-02--fix` | `more-itertools` | guard_raise | `more_itertools/more.py:239` | `9c2b967a` | `9ed3dbb0` |
| `more-itertools-guard_raise-02--forward` | `more-itertools` | guard_raise | `more_itertools/more.py:239` | `9ed3dbb0` | `9c2b967a` |
| `more-itertools-guard_raise-03--fix` | `more-itertools` | guard_raise | `more_itertools/more.py:244` | `bb4f2920` | `9ed3dbb0` |
| `more-itertools-guard_raise-03--forward` | `more-itertools` | guard_raise | `more_itertools/more.py:244` | `9ed3dbb0` | `bb4f2920` |
| `more-itertools-guard_raise-04--fix` | `more-itertools` | guard_raise | `more_itertools/more.py:272` | `b3815a7c` | `9ed3dbb0` |
| `more-itertools-guard_raise-04--forward` | `more-itertools` | guard_raise | `more_itertools/more.py:272` | `9ed3dbb0` | `b3815a7c` |
| `more-itertools-guard_raise-05--fix` | `more-itertools` | guard_raise | `more_itertools/more.py:297` | `aa3e41fa` | `9ed3dbb0` |
| `more-itertools-guard_raise-05--forward` | `more-itertools` | guard_raise | `more_itertools/more.py:297` | `9ed3dbb0` | `aa3e41fa` |
| `more-itertools-guard_raise-06--fix` | `more-itertools` | guard_raise | `more_itertools/more.py:406` | `a9fa118e` | `9ed3dbb0` |
| `more-itertools-guard_raise-06--forward` | `more-itertools` | guard_raise | `more_itertools/more.py:406` | `9ed3dbb0` | `a9fa118e` |
| `more-itertools-none_guard-13--fix` | `more-itertools` | none_guard | `more_itertools/more.py:2157` | `d999f40f` | `9ed3dbb0` |
| `more-itertools-none_guard-13--forward` | `more-itertools` | none_guard | `more_itertools/more.py:2157` | `9ed3dbb0` | `d999f40f` |
| `more-itertools-none_guard-14--fix` | `more-itertools` | none_guard | `more_itertools/more.py:2588` | `82e3ef58` | `9ed3dbb0` |
| `more-itertools-none_guard-14--forward` | `more-itertools` | none_guard | `more_itertools/more.py:2588` | `9ed3dbb0` | `82e3ef58` |
| `more-itertools-none_guard-15--fix` | `more-itertools` | none_guard | `more_itertools/more.py:4152` | `b7470a20` | `9ed3dbb0` |
| `more-itertools-none_guard-15--forward` | `more-itertools` | none_guard | `more_itertools/more.py:4152` | `9ed3dbb0` | `b7470a20` |
| `more-itertools-none_guard-16--fix` | `more-itertools` | none_guard | `more_itertools/more.py:4476` | `184a42c4` | `9ed3dbb0` |
| `more-itertools-none_guard-16--forward` | `more-itertools` | none_guard | `more_itertools/more.py:4476` | `9ed3dbb0` | `184a42c4` |
| `more-itertools-none_guard-17--fix` | `more-itertools` | none_guard | `more_itertools/recipes.py:336` | `7328a873` | `9ed3dbb0` |
| `more-itertools-none_guard-17--forward` | `more-itertools` | none_guard | `more_itertools/recipes.py:336` | `9ed3dbb0` | `7328a873` |
| `more-itertools-none_guard-18--fix` | `more-itertools` | none_guard | `more_itertools/recipes.py:516` | `ce100669` | `9ed3dbb0` |
| `more-itertools-none_guard-18--forward` | `more-itertools` | none_guard | `more_itertools/recipes.py:516` | `9ed3dbb0` | `ce100669` |
| `packaging-boundary-07--fix` | `packaging` | boundary | `src/packaging/_manylinux.py:199` | `64683eb7` | `10590c19` |
| `packaging-boundary-07--forward` | `packaging` | boundary | `src/packaging/_manylinux.py:199` | `10590c19` | `64683eb7` |
| `packaging-boundary-08--fix` | `packaging` | boundary | `src/packaging/_musllinux.py:28` | `29ce4df0` | `10590c19` |
| `packaging-boundary-08--forward` | `packaging` | boundary | `src/packaging/_musllinux.py:28` | `10590c19` | `29ce4df0` |
| `packaging-boundary-09--fix` | `packaging` | boundary | `src/packaging/_ranges.py:104` | `ba910fa0` | `10590c19` |
| `packaging-boundary-09--forward` | `packaging` | boundary | `src/packaging/_ranges.py:104` | `10590c19` | `ba910fa0` |
| `packaging-boundary-10--fix` | `packaging` | boundary | `src/packaging/_ranges.py:149` | `1d8530dc` | `10590c19` |
| `packaging-boundary-10--forward` | `packaging` | boundary | `src/packaging/_ranges.py:149` | `10590c19` | `1d8530dc` |
| `packaging-boundary-11--fix` | `packaging` | boundary | `src/packaging/_ranges.py:152` | `f14542c4` | `10590c19` |
| `packaging-boundary-11--forward` | `packaging` | boundary | `src/packaging/_ranges.py:152` | `10590c19` | `f14542c4` |
| `packaging-boundary-12--fix` | `packaging` | boundary | `src/packaging/_ranges.py:160` | `34e77fae` | `10590c19` |
| `packaging-boundary-12--forward` | `packaging` | boundary | `src/packaging/_ranges.py:160` | `10590c19` | `34e77fae` |
| `packaging-guard_raise-01--fix` | `packaging` | guard_raise | `src/packaging/_elffile.py:53` | `dc9899c2` | `10590c19` |
| `packaging-guard_raise-01--forward` | `packaging` | guard_raise | `src/packaging/_elffile.py:53` | `10590c19` | `dc9899c2` |
| `packaging-guard_raise-02--fix` | `packaging` | guard_raise | `src/packaging/_parser.py:36` | `f51f833a` | `10590c19` |
| `packaging-guard_raise-02--forward` | `packaging` | guard_raise | `src/packaging/_parser.py:36` | `10590c19` | `f51f833a` |
| `packaging-guard_raise-03--fix` | `packaging` | guard_raise | `src/packaging/_tokenizer.py:145` | `c5db07b5` | `10590c19` |
| `packaging-guard_raise-03--forward` | `packaging` | guard_raise | `src/packaging/_tokenizer.py:145` | `10590c19` | `c5db07b5` |
| `packaging-guard_raise-04--fix` | `packaging` | guard_raise | `src/packaging/direct_url.py:51` | `97216f09` | `10590c19` |
| `packaging-guard_raise-04--forward` | `packaging` | guard_raise | `src/packaging/direct_url.py:51` | `10590c19` | `97216f09` |
| `packaging-guard_raise-05--fix` | `packaging` | guard_raise | `src/packaging/direct_url.py:62` | `f4c4d2c8` | `10590c19` |
| `packaging-guard_raise-05--forward` | `packaging` | guard_raise | `src/packaging/direct_url.py:62` | `10590c19` | `f4c4d2c8` |
| `packaging-guard_raise-06--fix` | `packaging` | guard_raise | `src/packaging/direct_url.py:182` | `aff234b0` | `10590c19` |
| `packaging-guard_raise-06--forward` | `packaging` | guard_raise | `src/packaging/direct_url.py:182` | `10590c19` | `aff234b0` |
| `packaging-none_guard-13--fix` | `packaging` | none_guard | `src/packaging/_manylinux.py:178` | `9953c0fe` | `10590c19` |
| `packaging-none_guard-13--forward` | `packaging` | none_guard | `src/packaging/_manylinux.py:178` | `10590c19` | `9953c0fe` |
| `packaging-none_guard-14--fix` | `packaging` | none_guard | `src/packaging/_manylinux.py:203` | `1e08a41e` | `10590c19` |
| `packaging-none_guard-14--forward` | `packaging` | none_guard | `src/packaging/_manylinux.py:203` | `10590c19` | `1e08a41e` |
| `packaging-none_guard-15--fix` | `packaging` | none_guard | `src/packaging/_musllinux.py:71` | `5035eb6d` | `10590c19` |
| `packaging-none_guard-15--forward` | `packaging` | none_guard | `src/packaging/_musllinux.py:71` | `10590c19` | `5035eb6d` |
| `packaging-none_guard-16--fix` | `packaging` | none_guard | `src/packaging/_ranges.py:222` | `101d5a5f` | `10590c19` |
| `packaging-none_guard-16--forward` | `packaging` | none_guard | `src/packaging/_ranges.py:222` | `10590c19` | `101d5a5f` |
| `packaging-none_guard-17--fix` | `packaging` | none_guard | `src/packaging/_ranges.py:224` | `c26bf071` | `10590c19` |
| `packaging-none_guard-17--forward` | `packaging` | none_guard | `src/packaging/_ranges.py:224` | `10590c19` | `c26bf071` |
| `packaging-none_guard-18--fix` | `packaging` | none_guard | `src/packaging/_ranges.py:286` | `bc6e8de8` | `10590c19` |
| `packaging-none_guard-18--forward` | `packaging` | none_guard | `src/packaging/_ranges.py:286` | `10590c19` | `bc6e8de8` |
| `python-dotenv-boundary-05--fix` | `python-dotenv` | boundary | `src/dotenv/parser.py:78` | `9f98d243` | `a00cb2ee` |
| `python-dotenv-boundary-05--forward` | `python-dotenv` | boundary | `src/dotenv/parser.py:78` | `a00cb2ee` | `9f98d243` |
| `python-dotenv-boundary-06--fix` | `python-dotenv` | boundary | `src/dotenv/parser.py:164` | `0fdde500` | `a00cb2ee` |
| `python-dotenv-boundary-06--forward` | `python-dotenv` | boundary | `src/dotenv/parser.py:164` | `a00cb2ee` | `0fdde500` |
| `python-dotenv-boundary-07--fix` | `python-dotenv` | boundary | `src/dotenv/variables.py:78` | `622c7408` | `a00cb2ee` |
| `python-dotenv-boundary-07--forward` | `python-dotenv` | boundary | `src/dotenv/variables.py:78` | `a00cb2ee` | `622c7408` |
| `python-dotenv-boundary-08--fix` | `python-dotenv` | boundary | `src/dotenv/variables.py:85` | `6d4bcc0e` | `a00cb2ee` |
| `python-dotenv-boundary-08--forward` | `python-dotenv` | boundary | `src/dotenv/variables.py:85` | `a00cb2ee` | `6d4bcc0e` |
| `python-dotenv-guard_raise-01--fix` | `python-dotenv` | guard_raise | `src/dotenv/main.py:211` | `af005097` | `a00cb2ee` |
| `python-dotenv-guard_raise-01--forward` | `python-dotenv` | guard_raise | `src/dotenv/main.py:211` | `a00cb2ee` | `af005097` |
| `python-dotenv-guard_raise-02--fix` | `python-dotenv` | guard_raise | `src/dotenv/main.py:323` | `8d263ded` | `a00cb2ee` |
| `python-dotenv-guard_raise-02--forward` | `python-dotenv` | guard_raise | `src/dotenv/main.py:323` | `a00cb2ee` | `8d263ded` |
| `python-dotenv-guard_raise-03--fix` | `python-dotenv` | guard_raise | `src/dotenv/main.py:382` | `49c39f32` | `a00cb2ee` |
| `python-dotenv-guard_raise-03--forward` | `python-dotenv` | guard_raise | `src/dotenv/main.py:382` | `a00cb2ee` | `49c39f32` |
| `python-dotenv-guard_raise-04--fix` | `python-dotenv` | guard_raise | `src/dotenv/parser.py:101` | `20b059bd` | `a00cb2ee` |
| `python-dotenv-guard_raise-04--forward` | `python-dotenv` | guard_raise | `src/dotenv/parser.py:101` | `a00cb2ee` | `20b059bd` |
| `urllib3-boundary-07--fix` | `urllib3` | boundary | `src/urllib3/_collections.py:114` | `12511f72` | `5f2a6a84` |
| `urllib3-boundary-07--forward` | `urllib3` | boundary | `src/urllib3/_collections.py:114` | `5f2a6a84` | `12511f72` |
| `urllib3-boundary-08--fix` | `urllib3` | boundary | `src/urllib3/_collections.py:335` | `cc6f818f` | `5f2a6a84` |
| `urllib3-boundary-08--forward` | `urllib3` | boundary | `src/urllib3/_collections.py:335` | `5f2a6a84` | `cc6f818f` |
| `urllib3-boundary-09--fix` | `urllib3` | boundary | `src/urllib3/_collections.py:346` | `ce663977` | `5f2a6a84` |
| `urllib3-boundary-09--forward` | `urllib3` | boundary | `src/urllib3/_collections.py:346` | `5f2a6a84` | `ce663977` |
| `urllib3-boundary-10--fix` | `urllib3` | boundary | `src/urllib3/_collections.py:350` | `636bc6c0` | `5f2a6a84` |
| `urllib3-boundary-10--forward` | `urllib3` | boundary | `src/urllib3/_collections.py:350` | `5f2a6a84` | `636bc6c0` |
| `urllib3-boundary-11--fix` | `urllib3` | boundary | `src/urllib3/connection.py:276` | `6ea1590e` | `5f2a6a84` |
| `urllib3-boundary-11--forward` | `urllib3` | boundary | `src/urllib3/connection.py:276` | `5f2a6a84` | `6ea1590e` |
| `urllib3-boundary-12--fix` | `urllib3` | boundary | `src/urllib3/connection.py:292` | `1e1f5a24` | `5f2a6a84` |
| `urllib3-boundary-12--forward` | `urllib3` | boundary | `src/urllib3/connection.py:292` | `5f2a6a84` | `1e1f5a24` |
| `urllib3-guard_raise-01--fix` | `urllib3` | guard_raise | `src/urllib3/_collections.py:346` | `d358bb13` | `5f2a6a84` |
| `urllib3-guard_raise-01--forward` | `urllib3` | guard_raise | `src/urllib3/_collections.py:346` | `5f2a6a84` | `d358bb13` |
| `urllib3-guard_raise-02--fix` | `urllib3` | guard_raise | `src/urllib3/_request_methods.py:114` | `9a2f8252` | `5f2a6a84` |
| `urllib3-guard_raise-02--forward` | `urllib3` | guard_raise | `src/urllib3/_request_methods.py:114` | `5f2a6a84` | `9a2f8252` |
| `urllib3-guard_raise-03--fix` | `urllib3` | guard_raise | `src/urllib3/_request_methods.py:258` | `d733b544` | `5f2a6a84` |
| `urllib3-guard_raise-03--forward` | `urllib3` | guard_raise | `src/urllib3/_request_methods.py:258` | `5f2a6a84` | `d733b544` |
| `urllib3-guard_raise-04--fix` | `urllib3` | guard_raise | `src/urllib3/connection.py:269` | `20389d76` | `5f2a6a84` |
| `urllib3-guard_raise-04--forward` | `urllib3` | guard_raise | `src/urllib3/connection.py:269` | `5f2a6a84` | `20389d76` |
| `urllib3-guard_raise-05--fix` | `urllib3` | guard_raise | `src/urllib3/connection.py:353` | `b164ec8a` | `5f2a6a84` |
| `urllib3-guard_raise-05--forward` | `urllib3` | guard_raise | `src/urllib3/connection.py:353` | `5f2a6a84` | `b164ec8a` |
| `urllib3-guard_raise-06--fix` | `urllib3` | guard_raise | `src/urllib3/connection.py:366` | `13420b93` | `5f2a6a84` |
| `urllib3-guard_raise-06--forward` | `urllib3` | guard_raise | `src/urllib3/connection.py:366` | `5f2a6a84` | `13420b93` |
| `urllib3-none_guard-13--fix` | `urllib3` | none_guard | `src/urllib3/_collections.py:467` | `e1829e5b` | `5f2a6a84` |
| `urllib3-none_guard-13--forward` | `urllib3` | none_guard | `src/urllib3/_collections.py:467` | `5f2a6a84` | `e1829e5b` |
| `urllib3-none_guard-14--fix` | `urllib3` | none_guard | `src/urllib3/_collections.py:476` | `14b34e2c` | `5f2a6a84` |
| `urllib3-none_guard-14--forward` | `urllib3` | none_guard | `src/urllib3/_collections.py:476` | `5f2a6a84` | `14b34e2c` |
| `urllib3-none_guard-15--fix` | `urllib3` | none_guard | `src/urllib3/_collections.py:486` | `fd4ac76c` | `5f2a6a84` |
| `urllib3-none_guard-15--forward` | `urllib3` | none_guard | `src/urllib3/_collections.py:486` | `5f2a6a84` | `fd4ac76c` |
| `urllib3-none_guard-16--fix` | `urllib3` | none_guard | `src/urllib3/connection.py:420` | `cf63e1b2` | `5f2a6a84` |
| `urllib3-none_guard-16--forward` | `urllib3` | none_guard | `src/urllib3/connection.py:420` | `5f2a6a84` | `cf63e1b2` |
| `urllib3-none_guard-17--fix` | `urllib3` | none_guard | `src/urllib3/connectionpool.py:568` | `4b08dea6` | `5f2a6a84` |
| `urllib3-none_guard-17--forward` | `urllib3` | none_guard | `src/urllib3/connectionpool.py:568` | `5f2a6a84` | `4b08dea6` |
| `urllib3-none_guard-18--fix` | `urllib3` | none_guard | `src/urllib3/poolmanager.py:418` | `bde0e2c0` | `5f2a6a84` |
| `urllib3-none_guard-18--forward` | `urllib3` | none_guard | `src/urllib3/poolmanager.py:418` | `5f2a6a84` | `bde0e2c0` |

